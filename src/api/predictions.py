"""API路由 - 比赛预测"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
import pandas as pd
from pathlib import Path
from config.settings import settings
from src.prediction.feature_engineer import FeatureEngineer
from src.prediction.predictor import MatchPredictor
from src.analysis.elo_rating import EloRating

router = APIRouter()

# 全局变量（实际项目中用依赖注入）
_matches_df: Optional[pd.DataFrame] = None
_predictor: Optional[MatchPredictor] = None
_feature_engineer: Optional[FeatureEngineer] = None


class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    league: str = "英超"


def _get_predictor() -> MatchPredictor:
    """获取预测器（懒加载）"""
    global _predictor
    if _predictor is None:
        model_path = settings.MODEL_DIR / "xgb_match_predictor.joblib"
        if not model_path.exists():
            raise HTTPException(status_code=503,
                detail="预测模型未训练，请先运行模型训练脚本 scripts/train_model.py")
        _predictor = MatchPredictor(str(model_path))
    return _predictor


def _get_feature_engineer() -> FeatureEngineer:
    """获取特征工程器"""
    global _feature_engineer, _matches_df
    if _feature_engineer is None:
        if _matches_df is None:
            raise HTTPException(status_code=503,
                detail="比赛数据未加载，请先初始化数据")
        elo = EloRating()
        elo.batch_update(_matches_df)
        _feature_engineer = FeatureEngineer(_matches_df, elo)
    return _feature_engineer


@router.post("/predict")
async def predict_match(req: PredictRequest):
    """预测比赛结果"""
    try:
        fe = _get_feature_engineer()
        predictor = _get_predictor()

        features = fe.build_features(req.home_team, req.away_team)
        result = predictor.predict_with_explanation(features)

        return {
            "home_team": req.home_team,
            "away_team": req.away_team,
            "prediction": result["prediction"]["prediction"],
            "probabilities": result["prediction"]["probabilities"],
            "confidence": result["prediction"]["confidence"],
            "explanation": {
                "top_positive_factors": result["explanation"]["top_positive_factors"],
                "top_negative_factors": result["explanation"]["top_negative_factors"],
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}")


@router.get("/features/{home_team}/{away_team}")
async def get_features(home_team: str, away_team: str):
    """获取比赛特征向量（用于调试和展示）"""
    try:
        fe = _get_feature_engineer()
        features = fe.build_features(home_team, away_team)
        return {"home_team": home_team, "away_team": away_team,
                "features": features, "feature_count": len(features)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model/info")
async def model_info():
    """获取模型信息"""
    model_path = settings.MODEL_DIR / "xgb_match_predictor.joblib"
    if not model_path.exists():
        return {"status": "not_trained",
                "message": "模型未训练，请运行 scripts/train_model.py"}
    import joblib
    data = joblib.load(model_path)
    return {
        "status": "ready",
        "train_date": data.get("train_date"),
        "train_samples": data.get("train_samples"),
        "test_samples": data.get("test_samples"),
        "accuracy": data.get("accuracy"),
        "feature_count": len(data.get("features", [])),
        "features": data.get("features", []),
    }
