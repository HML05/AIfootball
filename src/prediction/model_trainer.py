"""模型训练 - XGBoost三分类（主胜/平局/客胜）
关键注意事项:
1. 必须用时间序列分割，不能随机分割（防止数据泄露）
2. 特征工程必须在训练集上拟合，不能用未来数据
3. 评估指标: 准确率 + LogLoss + 分类报告
"""
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import accuracy_score, log_loss, classification_report, confusion_matrix
import joblib
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
from config.settings import settings


class ModelTrainer:
    """比赛结果预测模型训练器"""

    LABEL_MAP = {0: "主胜", 1: "平局", 2: "客胜"}

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or settings.MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model = None
        self.feature_names = None

    def train(self, X: pd.DataFrame, y: np.ndarray,
              test_size: float = 0.2,
              model_params: dict = None) -> Dict:
        """训练XGBoost模型

        Args:
            X: 特征DataFrame
            y: 标签数组 (0=主胜, 1=平局, 2=客胜)
            test_size: 测试集比例（按时间顺序取最后test_size）
            model_params: XGBoost参数（None则用默认）

        Returns:
            训练结果评估dict
        """
        self.feature_names = list(X.columns)

        # 时间序列分割（按时间顺序，不能随机！）
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        print(f"训练集: {len(X_train)} 场, 测试集: {len(X_test)} 场")
        print(f"训练集标签分布: 主胜={np.sum(y_train==0)}, 平局={np.sum(y_train==1)}, 客胜={np.sum(y_train==2)}")

        # 默认参数
        default_params = dict(
            objective="multi:softprob",
            num_class=3,
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            eval_metric="mlogloss",
            early_stopping_rounds=50,
        )
        if model_params:
            default_params.update(model_params)

        # 训练
        self.model = xgb.XGBClassifier(**default_params)
        self.model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        # 评估
        y_pred = self.model.predict(X_test)
        y_proba = self.model.predict_proba(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        logloss = log_loss(y_test, y_proba)
        conf_matrix = confusion_matrix(y_test, y_pred)

        # 各类别准确率
        class_acc = {}
        for i, label in self.LABEL_MAP.items():
            mask = y_test == i
            if mask.sum() > 0:
                class_acc[label] = round(accuracy_score(y_test[mask], y_pred[mask]), 4)

        # 保存模型
        model_path = self.model_dir / "xgb_match_predictor.joblib"
        joblib.dump({
            "model": self.model,
            "features": self.feature_names,
            "label_map": self.LABEL_MAP,
            "train_date": pd.Timestamp.now().isoformat(),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "accuracy": accuracy,
        }, model_path)

        # 保存特征重要性
        importance = self.model.feature_importances_
        feature_importance = sorted(
            zip(self.feature_names, importance),
            key=lambda x: x[1], reverse=True
        )
        importance_path = self.model_dir / "feature_importance.json"
        with open(importance_path, "w", encoding="utf-8") as f:
            json.dump([{"feature": k, "importance": round(float(v), 6)}
                       for k, v in feature_importance], f, ensure_ascii=False, indent=2)

        result = {
            "accuracy": round(accuracy, 4),
            "log_loss": round(logloss, 4),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "class_accuracy": class_acc,
            "confusion_matrix": conf_matrix.tolist(),
            "classification_report": classification_report(
                y_test, y_pred,
                target_names=list(self.LABEL_MAP.values()),
                output_dict=True
            ),
            "top_features": [{"feature": k, "importance": round(float(v), 6)}
                            for k, v in feature_importance[:10]],
            "model_path": str(model_path),
            "importance_path": str(importance_path),
        }

        print(f"\n训练完成! 测试集准确率: {accuracy:.2%}, LogLoss: {logloss:.4f}")
        print(f"各类别准确率: {class_acc}")
        print(f"Top5重要特征: {[f['feature'] for f in result['top_features'][:5]]}")

        return result

    def cross_validate(self, X: pd.DataFrame, y: np.ndarray,
                       n_splits: int = 5) -> Dict:
        """时间序列交叉验证"""
        tscv = TimeSeriesSplit(n_splits=n_splits)
        scores = cross_val_score(self.model, X, y, cv=tscv, scoring="accuracy")
        return {
            "mean_accuracy": round(scores.mean(), 4),
            "std_accuracy": round(scores.std(), 4),
            "fold_scores": [round(s, 4) for s in scores.tolist()],
        }

    def hyperparameter_tuning(self, X: pd.DataFrame, y: np.ndarray) -> Dict:
        """简单的超参数搜索（网格搜索）"""
        from sklearn.model_selection import GridSearchCV

        param_grid = {
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.05, 0.1],
            "n_estimators": [100, 200, 300],
            "subsample": [0.7, 0.8, 0.9],
        }

        base_model = xgb.XGBClassifier(
            objective="multi:softprob", num_class=3,
            random_state=42, eval_metric="mlogloss"
        )

        # 用时间序列分割
        tscv = TimeSeriesSplit(n_splits=3)
        grid_search = GridSearchCV(
            base_model, param_grid, cv=tscv,
            scoring="accuracy", n_jobs=-1, verbose=1
        )
        grid_search.fit(X, y)

        return {
            "best_params": grid_search.best_params_,
            "best_score": round(grid_search.best_score_, 4),
        }

    @staticmethod
    def load_model(model_path: str):
        """加载已训练模型"""
        data = joblib.load(model_path)
        trainer = ModelTrainer()
        trainer.model = data["model"]
        trainer.feature_names = data["features"]
        return trainer
