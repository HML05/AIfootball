# -*- coding: utf-8 -*-
"""训练 v2 部署模型(全量数据) 并保存

用法: python scripts/train_v2.py
"""
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.prediction import vector_features_v2 as v2  # noqa: E402

BASE = Path(__file__).parent.parent
PARAMS = dict(objective="multi:softprob", num_class=3, n_estimators=300, max_depth=5,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              reg_alpha=0.1, reg_lambda=1.0, random_state=42, eval_metric="mlogloss")

df = v2.load_matches()
X, y, dates, divs, leagues = v2.build_features_v2(df)
print(f"训练样本: {len(X)} | 特征: {X.shape[1]} 维")
model = xgb.XGBClassifier(**PARAMS)
model.fit(X, y, verbose=False)

bundle = {
    "model": model,
    "features": list(X.columns),
    "version": "v2",
    "feature_module": "src.prediction.vector_features_v2",
    "train_samples": int(len(X)),
    "train_until": str(dates.max())[:10],
}
out = BASE / "models" / "xgb_v2.joblib"
joblib.dump(bundle, str(out))
print(f"已保存: {out}")

imp = sorted(zip(X.columns, model.feature_importances_), key=lambda x: -x[1])[:15]
print("\nTop15 重要特征:")
for k, v in imp:
    print(f"  {k:<26} {v:.4f}")
with open(BASE / "models" / "v2_feature_importance.json", "w", encoding="utf-8") as f:
    json.dump([{"feature": k, "importance": round(float(v), 6)} for k, v in imp],
              f, ensure_ascii=False, indent=1)
