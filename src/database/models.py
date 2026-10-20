"""数据库模型 - SQLAlchemy ORM"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, ForeignKey, Boolean, Index
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class League(Base):
    """联赛表"""
    __tablename__ = "leagues"

    league_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="联赛中文名")
    name_en = Column(String(50), comment="联赛英文名")
    country = Column(String(30), comment="国家")
    season = Column(String(20), comment="当前赛季")
    logo_url = Column(String(255))
    created_at = Column(DateTime, default=datetime.now)

    teams = relationship("Team", back_populates="league")


class Team(Base):
    """球队表"""
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.league_id"))
    name = Column(String(100), nullable=False, comment="中文名")
    name_en = Column(String(100), comment="英文名")
    short_name = Column(String(20), comment="简称")
    founded = Column(Integer, comment="成立年份")
    stadium = Column(String(100), comment="主场")
    capacity = Column(Integer, comment="容量")
    manager = Column(String(50), comment="主教练")
    logo_url = Column(String(255))
    elo_rating = Column(Float, default=1500.0, comment="Elo评级")
    created_at = Column(DateTime, default=datetime.now)

    league = relationship("League", back_populates="teams")
    players = relationship("Player", back_populates="team")


class Player(Base):
    """球员表"""
    __tablename__ = "players"

    player_id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.team_id"))
    name = Column(String(100), nullable=False)
    name_en = Column(String(100))
    position = Column(String(20), comment="位置 GK/DF/MF/FW")
    nationality = Column(String(50))
    age = Column(Integer)
    height = Column(Float, comment="身高cm")
    weight = Column(Float, comment="体重kg")
    number = Column(Integer, comment="号码")
    market_value = Column(Float, comment="身价万欧元")
    photo_url = Column(String(255))
    stats_json = Column(Text, comment="详细统计JSON")
    created_at = Column(DateTime, default=datetime.now)

    team = relationship("Team", back_populates="players")


class Match(Base):
    """比赛表"""
    __tablename__ = "matches"

    match_id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.league_id"))
    season = Column(String(20))
    matchday = Column(Integer, comment="轮次")
    date = Column(DateTime, comment="比赛时间")
    home_team_id = Column(Integer, ForeignKey("teams.team_id"))
    away_team_id = Column(Integer, ForeignKey("teams.team_id"))
    home_goals = Column(Integer, nullable=True, comment="主队进球")
    away_goals = Column(Integer, nullable=True)
    status = Column(String(20), default="scheduled", comment="scheduled/live/finished")
    home_xg = Column(Float, comment="主队预期进球")
    away_xg = Column(Float)
    stats_json = Column(Text, comment="详细比赛统计")
    created_at = Column(DateTime, default=datetime.now)

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])


class Transfer(Base):
    """转会表"""
    __tablename__ = "transfers"

    transfer_id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.player_id"))
    player_name = Column(String(100), comment="球员名（冗余，方便查询）")
    from_team_id = Column(Integer, ForeignKey("teams.team_id"))
    from_team_name = Column(String(100))
    to_team_id = Column(Integer, ForeignKey("teams.team_id"))
    to_team_name = Column(String(100))
    transfer_date = Column(Date)
    transfer_fee = Column(Float, comment="转会费万欧元")
    transfer_type = Column(String(20), comment="永久/租借/自由转会")
    created_at = Column(DateTime, default=datetime.now)


class Prediction(Base):
    """预测记录表"""
    __tablename__ = "predictions"

    pred_id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.match_id"))
    model_version = Column(String(20), default="v1.0")
    pred_home_win = Column(Float)
    pred_draw = Column(Float)
    pred_away_win = Column(Float)
    pred_result = Column(String(10), comment="H/D/A")
    actual_result = Column(String(10), nullable=True, comment="赛后回填")
    features_json = Column(Text, comment="预测时特征快照")
    created_at = Column(DateTime, default=datetime.now)


class Standing(Base):
    """积分榜表"""
    __tablename__ = "standings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.league_id"))
    season = Column(String(20), comment="赛季代码, 如 2627")
    team_id = Column(Integer, ForeignKey("teams.team_id"))
    rank = Column(Integer, comment="排名")
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    draw = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    goal_diff = Column(Integer, default=0)
    points = Column(Integer, default=0)
    form = Column(String(50), nullable=True, comment="近5场形式, 如 WWDLL")
    updated_at = Column(DateTime, default=datetime.now)

    team = relationship("Team")


# ============ 登录认证(账号密码 + 二维码轮询) ============

class AuthUser(Base):
    """登录用户"""
    __tablename__ = "auth_users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="登录账号")
    display_name = Column(String(50), comment="显示名")
    role = Column(String(20), default="user", comment="user=用户端 / admin=管理后台")
    pwd_hash = Column(String(255), nullable=False,
                      comment="pbkdf2_sha256$轮数$盐$哈希, 见 src/auth/security.py")
    phone = Column(String(20), nullable=True, comment="可选, 仅作展示")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, nullable=True)


class AuthSession(Base):
    """登录会话(浏览器/客户端持有 token)"""
    __tablename__ = "auth_sessions"

    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("auth_users.user_id"))
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    user_agent = Column(String(200), nullable=True)
    client_ip = Column(String(45), nullable=True)


class QrTicket(Base):
    """二维码登录票据: PC 出码 -> 手机确认 -> PC 轮询换 token"""
    __tablename__ = "auth_qr_tickets"

    qr_id = Column(String(32), primary_key=True)
    secret = Column(String(64), nullable=False, comment="轮询/确认都要带, 防止猜 id")
    status = Column(String(12), default="pending",
                    comment="pending/scanned/confirmed/consumed/expired")
    user_id = Column(Integer, ForeignKey("auth_users.user_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    confirmed_at = Column(DateTime, nullable=True)
    # PC 侧的请求信息, 手机上显示出来让用户确认「是不是这台机器」
    pc_user_agent = Column(String(200), nullable=True)
    pc_ip = Column(String(45), nullable=True)


class AuthResetCode(Base):
    """忘记密码: 一次性重置码(本机/内网部署, 没有邮件通道, 码直接给页面显示)"""
    __tablename__ = "auth_reset_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, comment="申请重置的账号")
    code_hash = Column(String(64), nullable=False, comment="sha256(重置码), 不存明文")
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, comment="用过一次就作废")
    tries = Column(Integer, default=0, comment="连续试错次数, 超上限作废")
    client_ip = Column(String(45), nullable=True)


# ============ 视觉(YOLOv8 球员检测跟踪) ============
# 只增不改: 视频 -> 处理任务 -> 抽样轨迹 -> 指标摘要。
# 推理要 torch/ultralytics(约 2.5 GB), 主应用与云主机都不装, 由
# scripts/run_vision_jobs.py 在 .venv-vision 里领任务跑; 这四张表只负责
# 「排队 + 存结果」, 所以 src/api/vision.py 可以完全不知道 cv2/ultralytics。

class VisionVideo(Base):
    """上传的视频(落 data/vision/videos/, 已在 .gitignore 里)"""
    __tablename__ = "vision_videos"

    video_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="原始文件名")
    path = Column(String(400), nullable=False, comment="相对仓库根的文件路径")
    size_bytes = Column(Integer, default=0)
    duration = Column(Float, nullable=True, comment="秒")
    fps = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    frames = Column(Integer, nullable=True, comment="总帧数")
    status = Column(String(12), default="uploaded",
                    comment="uploaded/queued/running/done/failed")
    message = Column(String(400), nullable=True, comment="给界面看的一句话说明")
    owner_id = Column(Integer, ForeignKey("auth_users.user_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisionJob(Base):
    """一次检测跟踪任务: 排队 -> 处理中 -> 出指标"""
    __tablename__ = "vision_jobs"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("vision_videos.video_id"), nullable=False)
    status = Column(String(12), default="queued",
                    comment="queued/running/done/failed/canceled")
    progress = Column(Float, default=0.0, comment="0~100")
    frames_done = Column(Integer, default=0)
    frames_total = Column(Integer, nullable=True)
    step = Column(Integer, default=5, comment="每 N 帧存一条轨迹(抽样入库)")
    model = Column(String(80), default="yolov8s.pt")
    conf = Column(Float, default=0.25)
    imgsz = Column(Integer, default=960)
    message = Column(String(400), nullable=True)
    error = Column(Text, nullable=True)
    worker = Column(String(80), nullable=True, comment="哪个进程领走的")
    overlay_path = Column(String(400), nullable=True, comment="带框视频(可选, 只做下载)")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)


class VisionTrack(Base):
    """抽样轨迹: 每 step 帧存该帧所有框, 前端 canvas 叠加用"""
    __tablename__ = "vision_tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("vision_jobs.job_id"), nullable=False)
    frame = Column(Integer, nullable=False)
    track_id = Column(Integer, nullable=True, comment="跟踪 ID, 检测模式为 NULL")
    cls = Column(Integer, nullable=False, comment="COCO 类别: 0=人, 32=球")
    conf = Column(Float, nullable=True)
    x1 = Column(Float, nullable=False)
    y1 = Column(Float, nullable=False)
    x2 = Column(Float, nullable=False)
    y2 = Column(Float, nullable=False)

    __table_args__ = (Index("ix_vision_tracks_job_frame", "job_id", "frame"),)


class VisionSummary(Base):
    """任务指标: metrics.summarize 的 JSON + verdict 逐条判定"""
    __tablename__ = "vision_summaries"

    job_id = Column(Integer, ForeignKey("vision_jobs.job_id"), primary_key=True)
    video_id = Column(Integer, ForeignKey("vision_videos.video_id"), nullable=False)
    payload = Column(Text, nullable=False,
                     comment="JSON: {'summary': {...}, 'verdict': [[标记, 文字]], 'elapsed': 秒}")
    created_at = Column(DateTime, default=datetime.now)

