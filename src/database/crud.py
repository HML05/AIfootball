"""数据库连接与CRUD操作"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Optional, List
from config.settings import settings
from src.database.models import Base, League, Team, Player, Match, Transfer, Prediction

# 创建引擎
# SQLite 默认等 5 秒就抛 "database is locked": 本系统里有多个进程会写同一个库
# (API + 两个 Streamlit + 控制台轮询), 并发写时容易偶发 500。把忙等放宽到 30 秒,
# 让后来的写操作排队而不是直接报错。
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=({"check_same_thread": False, "timeout": 30}
                  if "sqlite" in settings.DATABASE_URL else {})
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """获取数据库会话（FastAPI依赖注入用，不需要@contextmanager装饰器）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============ 联赛操作 ============

def create_league(db: Session, name: str, name_en: str = "", country: str = "",
                  season: str = "", logo_url: str = "") -> League:
    league = League(name=name, name_en=name_en, country=country,
                    season=season, logo_url=logo_url)
    db.add(league)
    db.commit()
    db.refresh(league)
    return league


def get_all_leagues(db: Session) -> List[League]:
    return db.query(League).all()


def get_league_by_name(db: Session, name: str) -> Optional[League]:
    return db.query(League).filter(League.name == name).first()


# ============ 球队操作 ============

def create_team(db: Session, league_id: int, name: str, name_en: str = "",
                short_name: str = "", **kwargs) -> Team:
    team = Team(league_id=league_id, name=name, name_en=name_en,
                short_name=short_name, **kwargs)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def get_team_by_name(db: Session, name: str) -> Optional[Team]:
    return db.query(Team).filter(
        (Team.name == name) | (Team.name_en == name) | (Team.short_name == name)
    ).first()


def get_teams_by_league(db: Session, league_id: int) -> List[Team]:
    return db.query(Team).filter(Team.league_id == league_id).all()


def update_team_elo(db: Session, team_id: int, elo: float):
    team = db.query(Team).filter(Team.team_id == team_id).first()
    if team:
        team.elo_rating = elo
        db.commit()


# ============ 球员操作 ============

def create_player(db: Session, team_id: int, name: str, **kwargs) -> Player:
    player = Player(team_id=team_id, name=name, **kwargs)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def get_player_by_name(db: Session, name: str) -> Optional[Player]:
    return db.query(Player).filter(
        (Player.name == name) | (Player.name_en == name)
    ).first()


def get_players_by_team(db: Session, team_id: int) -> List[Player]:
    return db.query(Player).filter(Player.team_id == team_id).all()


# ============ 比赛操作 ============

def create_match(db: Session, **kwargs) -> Match:
    match = Match(**kwargs)
    db.add(match)
    db.commit()
    db.refresh(match)
    return match


def get_matches_by_league_season(db: Session, league_id: int, season: str) -> List[Match]:
    return db.query(Match).filter(
        Match.league_id == league_id, Match.season == season
    ).order_by(Match.date).all()


def get_upcoming_matches(db: Session, league_id: int = None, days: int = 7) -> List[Match]:
    from datetime import datetime, timedelta
    now = datetime.now()
    end = now + timedelta(days=days)
    query = db.query(Match).filter(
        Match.date >= now, Match.date <= end, Match.status.in_(["NS", "scheduled"])
    )
    if league_id:
        query = query.filter(Match.league_id == league_id)
    return query.order_by(Match.date).all()


def update_match_result(db: Session, match_id: int, home_goals: int, away_goals: int):
    match = db.query(Match).filter(Match.match_id == match_id).first()
    if match:
        match.home_goals = home_goals
        match.away_goals = away_goals
        match.status = "finished"
        db.commit()


# ============ 预测记录操作 ============

def create_prediction(db: Session, **kwargs) -> Prediction:
    pred = Prediction(**kwargs)
    db.add(pred)
    db.commit()
    db.refresh(pred)
    return pred


def get_predictions_by_match(db: Session, match_id: int) -> List[Prediction]:
    return db.query(Prediction).filter(Prediction.match_id == match_id).all()
