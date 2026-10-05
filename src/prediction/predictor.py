"""预测器与SHAP可解释性分析
- 加载训练好的XGBoost模型
- 对单场比赛进行预测
- 用SHAP分析各特征对预测结果的贡献（解决AI黑盒问题）
"""
import pandas as pd
import numpy as np
import joblib
import shap
from typing import Dict, Optional
from pathlib import Path


class MatchPredictor:
    """比赛预测器"""

    LABEL_MAP = {0: "主胜", 1: "平局", 2: "客胜"}

    def __init__(self, model_path: str):
        """
        Args:
            model_path: 训练好的模型文件路径(.joblib)
        """
        data = joblib.load(model_path)
        self.model = data["model"]
        self.feature_names = data["features"]
        self.label_map = data.get("label_map", self.LABEL_MAP)
        self._explainer = None

    def predict(self, features: Dict) -> Dict:
        """预测单场比赛

        Args:
            features: 特征工程输出的特征dict

        Returns:
            预测结果dict（含概率分布、置信度）
        """
        X = pd.DataFrame([features])
        # 确保特征顺序一致
        for col in self.feature_names:
            if col not in X.columns:
                X[col] = 0.0
        X = X[self.feature_names]

        proba = self.model.predict_proba(X)[0]
        pred = int(np.argmax(proba))

        return {
            "prediction": self.label_map.get(pred, str(pred)),
            "prediction_code": ["H", "D", "A"][pred],
            "probabilities": {
                "home_win": round(float(proba[0]), 4),
                "draw": round(float(proba[1]), 4),
                "away_win": round(float(proba[2]), 4),
            },
            "confidence": round(float(max(proba)), 4),
            "features_used": features,
        }

    def explain(self, features: Dict, top_n: int = 10) -> Dict:
        """SHAP可解释性分析

        展示每个特征对预测结果的贡献度，解决"AI黑盒"问题。
        正值表示支持预测结果，负值表示反对。

        Args:
            features: 特征dict
            top_n: 返回前N个最重要特征

        Returns:
            SHAP分析结果
        """
        X = pd.DataFrame([features])
        for col in self.feature_names:
            if col not in X.columns:
                X[col] = 0.0
        X = X[self.feature_names]

        # 延迟初始化explainer
        if self._explainer is None:
            self._explainer = shap.TreeExplainer(self.model)

        shap_values = self._explainer.shap_values(X)
        pred_class = int(np.argmax(self.model.predict_proba(X)[0]))

        # 对预测类别提取特征贡献
        # shap_values shape: (n_features, n_samples, n_classes) 或 (n_samples, n_features, n_classes)
        if isinstance(shap_values, list):
            # 多分类时shap_values是list，每个元素对应一个类别
            class_shap = shap_values[pred_class][0]
        elif len(np.array(shap_values).shape) == 3:
            class_shap = np.array(shap_values)[0, :, pred_class]
        else:
            class_shap = np.array(shap_values)[0]

        contributions = dict(zip(self.feature_names, class_shap))

        # 按贡献绝对值排序
        sorted_contrib = sorted(contributions.items(),
                               key=lambda x: abs(x[1]), reverse=True)

        # 特征值映射（用于展示）
        feature_values = {k: features.get(k, 0) for k in self.feature_names}

        return {
            "predicted_class": self.label_map.get(pred_class, str(pred_class)),
            "base_value": float(self._explainer.expected_value[pred_class])
            if isinstance(self._explainer.expected_value, (list, np.ndarray))
            else float(self._explainer.expected_value),
            "top_positive_factors": [
                {"feature": k, "shap_value": round(float(v), 4),
                 "feature_value": round(float(feature_values.get(k, 0)), 4)}
                for k, v in sorted_contrib if v > 0
            ][:top_n],
            "top_negative_factors": [
                {"feature": k, "shap_value": round(float(v), 4),
                 "feature_value": round(float(feature_values.get(k, 0)), 4)}
                for k, v in sorted_contrib if v < 0
            ][:top_n],
            "all_contributions": {
                k: {"shap_value": round(float(v), 4),
                    "feature_value": round(float(feature_values.get(k, 0)), 4)}
                for k, v in sorted_contrib
            },
        }

    def predict_with_explanation(self, features: Dict) -> Dict:
        """预测 + 可解释性分析（一次调用）"""
        prediction = self.predict(features)
        explanation = self.explain(features)
        return {
            "prediction": prediction,
            "explanation": explanation,
        }

    def batch_predict(self, features_list: list) -> list:
        """批量预测"""
        results = []
        for features in features_list:
            results.append(self.predict(features))
        return results
