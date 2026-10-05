"""API路由 - 球员"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.database.crud import get_db, get_player_by_name

router = APIRouter()


@router.get("/search")
async def search_player(name: str, db: Session = Depends(get_db)):
    """搜索球员"""
    player = get_player_by_name(db, name)
    if not player:
        raise HTTPException(status_code=404, detail=f"未找到球员: {name}")
    return {
        "id": player.player_id, "name": player.name, "name_en": player.name_en,
        "team": player.team.name if player.team else None,
        "position": player.position, "nationality": player.nationality,
        "age": player.age, "height": player.height, "weight": player.weight,
        "number": player.number, "market_value": player.market_value,
        "stats": player.stats_json,
    }


@router.get("/{player_id}/radar")
async def player_radar(player_id: int, db: Session = Depends(get_db)):
    """获取球员能力雷达图数据"""
    # 实际项目中从球员统计计算八大能力维度
    return {"player_id": player_id,
            "note": "从球员赛季统计数据计算能力维度后返回"}
