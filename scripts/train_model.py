"""模型训练脚本
功能:
1. 加载历史比赛数据
2. 构建训练特征（防止数据泄露）
3. 训练XGBoost三分类模型
4. 评估模型性能
5. 保存模型和特征重要性

用法: python scripts/train_model.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import json
from pathlib import Path
from config.settings import settings
from src.prediction.feature_engineer import FeatureEngineer
from src.prediction.model_trainer import ModelTrainer
from src.analysis.elo_rating import EloRating


def load_match_data() -> pd.DataFrame:
    """加载比赛数据"""
    processed_path = settings.DATA_DIR / "processed" / "all_matches.csv"
    if not processed_path.exists():
        raise FileNotFoundError(
            f"未找到比赛数据: {processed_path}\n"
            f"请先运行数据初始化: python scripts/init_data.py"
        )

    df = pd.read_csv(processed_path, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR"])
    df = df.sort_values("Date").reset_index(drop=True)

    print(f"已加载 {len(df)} 场比赛数据")
    print(f"时间范围: {df['Date'].min().strftime('%Y-%m-%d')} ~ {df['Date'].max().strftime('%Y-%m-%d')}")
    print(f"联赛分布: {df['league'].value_counts().to_dict()}")
    print(f"结果分布: 主胜={np.sum(df['FTR']=='H')}, 平局={np.sum(df['FTR']=='D')}, 客胜={np.sum(df['FTR']=='A')}")
    return df


def build_training_dataset(df: pd.DataFrame) -> tuple:
    """构建训练数据集
    关键: 按时间顺序构建特征，防止数据泄露
    """
    print("\n" + "=" * 60)
    print("构建训练数据集（按时间顺序，防止数据泄露）...")
    print("=" * 60)

    # 先用全量数据训练Elo（作为初始评级）
    base_elo = EloRating()
    base_elo.batch_update(df)

    fe = FeatureEngineer(df, base_elo)
    X, y, info = fe.build_training_dataset(min_history=100)

    print(f"\n训练集构建完成:")
    print(f"  有效样本数: {len(X)}")
    print(f"  特征维度: {X.shape[1]}")
    print(f"  标签分布: 主胜={np.sum(y==0)}, 平局={np.sum(y==1)}, 客胜={np.sum(y==2)}")
    print(f"  特征列表: {list(X.columns)}")

    # 保存训练集
    train_path = settings.DATA_DIR / "processed" / "training_features.csv"
    X_with_label = X.copy()
    X_with_label["label"] = y
    X_with_label.to_csv(train_path, index=False, encoding="utf-8-sig")
    print(f"  训练特征已保存: {train_path}")

    return X, y


def train_and_evaluate(X: pd.DataFrame, y: np.ndarray) -> dict:
    """训练并评估模型"""
    print("\n" + "=" * 60)
    print("训练XGBoost模型...")
    print("=" * 60)

    trainer = ModelTrainer(model_dir=settings.MODEL_DIR)

    # 训练
    result = trainer.train(X, y, test_size=0.2)

    print(f"\n模型训练完成!")
    print(f"  测试集准确率: {result['accuracy']:.2%}")
    print(f"  测试集LogLoss: {result['log_loss']:.4f}")
    print(f"  各类别准确率: {result['class_accuracy']}")

    print(f"\n  Top 10 重要特征:")
    for i, f in enumerate(result["top_features"][:10]):
        print(f"    {i+1}. {f['feature']}: {f['importance']:.6f}")

    # 混淆矩阵
    print(f"\n  混淆矩阵:")
    cm = result["confusion_matrix"]
    print(f"    实际\\预测  主胜  平局  客胜")
    print(f"    主胜      {cm[0][0]:4d}  {cm[0][1]:4d}  {cm[0][2]:4d}")
    print(f"    平局      {cm[1][0]:4d}  {cm[1][1]:4d}  {cm[1][2]:4d}")
    print(f"    客胜      {cm[2][0]:4d}  {cm[2][1]:4d}  {cm[2][2]:4d}")

    # 保存评估结果
    eval_path = settings.MODEL_DIR / "evaluation_result.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump({
            "accuracy": result["accuracy"],
            "log_loss": result["log_loss"],
            "class_accuracy": result["class_accuracy"],
            "confusion_matrix": result["confusion_matrix"],
            "top_features": result["top_features"],
            "train_samples": result["train_samples"],
            "test_samples": result["test_samples"],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  评估结果已保存: {eval_path}")

    return result


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  足球比赛预测模型 - 训练脚本")
    print("=" * 60 + "\n")

    try:
        # 1. 加载数据
        df = load_match_data()

        # 2. 构建训练集
        X, y = build_training_dataset(df)

        if len(X) < 100:
            print("\n警告: 训练样本不足100，模型效果可能不佳")
            print("建议增加更多历史赛季数据")

        # 3. 训练模型
        result = train_and_evaluate(X, y)

        print("\n" + "=" * 60)
        print("  模型训练完成!")
        print("=" * 60)
        print(f"\n模型文件: {settings.MODEL_DIR / 'xgb_match_predictor.joblib'}")
        print(f"特征重要性: {settings.MODEL_DIR / 'feature_importance.json'}")
        print(f"评估结果: {settings.MODEL_DIR / 'evaluation_result.json'}")
        print("\n下一步:")
        print("  1. 启动后端服务: uvicorn src.main:app --reload")
        print("  2. 启动前端: streamlit run frontend/app.py")
        print("  3. 在前端'比赛预测'页面测试预测功能")
        print()

    except Exception as e:
        print(f"\n训练失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
