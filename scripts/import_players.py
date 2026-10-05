"""
球员数据导入脚本
基于 API-Football 免费 tier (100请求/天)
支持：配置API key、断点续传、增量更新、球队映射

使用方法：
1. 注册 API-Football 免费账号获取 key: https://www.api-football.com/
2. 在项目根目录创建 .env 文件，写入: API_FOOTBALL_KEY=你的key
3. 运行: python scripts/import_players.py
4. 免费tier 100请求/天，五大联赛约5000球员，需分批多天导入
"""
import os
import sys
import json
import time
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'data' / 'database' / 'football.db'
ENV_PATH = BASE_DIR / '.env'
PROGRESS_PATH = BASE_DIR / 'data' / 'player_import_progress.json'

# API-Football 配置
API_BASE = 'https://v3.football.api-sports.io'
API_HEADERS = {}

# 五大联赛 API-Football ID
LEAGUE_IDS = {
    '英超': 39,
    '西甲': 140,
    '德甲': 78,
    '意甲': 135,
    '法甲': 61,
}

CURRENT_SEASON = 2025  # 2025/26赛季


def load_api_key():
    """从.env或环境变量加载API key"""
    # 先从环境变量
    key = os.environ.get('API_FOOTBALL_KEY', '')
    if key:
        return key
    # 再从.env文件
    if ENV_PATH.exists():
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('API_FOOTBALL_KEY='):
                    key = line.split('=', 1)[1].strip().strip('"').strip("'")
                    return key
    return ''


def init_api(key):
    """初始化API headers"""
    global API_HEADERS
    API_HEADERS = {
        'x-apisports-key': key,
        'x-rapidapi-host': 'v3.football.api-sports.io'
    }


def api_get(endpoint, params=None):
    """发送API请求，带限流处理"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, headers=API_HEADERS, params=params, timeout=30)
        data = resp.json()
        # 检查限流
        if resp.status_code == 429:
            print("  达到API限流，等待60秒...")
            time.sleep(60)
            return api_get(endpoint, params)
        if data.get('errors'):
            print(f"  API错误: {data['errors']}")
            return None
        return data
    except Exception as e:
        print(f"  请求异常: {e}")
        return None


def get_remaining_requests():
    """获取剩余请求数（通过/status端点）"""
    data = api_get('/status')
    if data and 'response' in data:
        account = data['response'].get('account', {})
        return account.get('requests', {}).get('current', 0), account.get('requests', {}).get('limit_day', 100)
    return 0, 100


def load_progress():
    """加载导入进度"""
    if PROGRESS_PATH.exists():
        with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'completed_teams': [], 'total_players': 0, 'last_update': None}


def save_progress(progress):
    """保存导入进度"""
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_PATH, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def get_team_id_mapping(cur):
    """获取数据库中所有球队，建立英文队名到team_id的映射"""
    cur.execute("SELECT team_id, name_en, name, league_id FROM teams")
    teams = cur.fetchall()
    mapping = {}
    for t in teams:
        mapping[t[1].lower()] = t[0]  # name_en -> team_id
    return mapping, teams


def find_team_id_by_api_name(api_team_name, db_mapping, db_teams):
    """根据API返回的球队名匹配数据库team_id"""
    name_lower = api_team_name.lower().strip()
    # 精确匹配
    if name_lower in db_mapping:
        return db_mapping[name_lower]
    # 模糊匹配（包含关系）
    for db_name, tid in db_mapping.items():
        if name_lower in db_name or db_name in name_lower:
            return tid
    return None


def import_players_for_team(api_team_id, team_name, db_team_id, cur, conn):
    """导入单支球队的球员"""
    players_imported = 0
    page = 1

    while True:
        data = api_get('/players', {
            'team': api_team_id,
            'season': CURRENT_SEASON,
            'page': page
        })

        if not data or 'response' not in data:
            break

        players = data['response']
        if not players:
            break

        for p in players:
            try:
                player_info = p.get('player', {})
                stats_list = p.get('statistics', [])
                stats = stats_list[0] if stats_list else {}

                player_id = player_info.get('id')
                name = player_info.get('name', '')
                firstname = player_info.get('firstname', '')
                lastname = player_info.get('lastname', '')
                position = stats.get('games', {}).get('position', '')
                nationality = player_info.get('nationality', '')
                age = player_info.get('age', 0)
                height_str = player_info.get('height', '')
                weight_str = player_info.get('weight', '')
                number = stats.get('games', {}).get('number', 0)
                photo = player_info.get('photo', '')

                # 解析身高体重（"185 cm" -> 185）
                height = 0
                if height_str and 'cm' in height_str:
                    try:
                        height = float(height_str.replace('cm', '').strip())
                    except:
                        pass
                weight = 0
                if weight_str and 'kg' in weight_str:
                    try:
                        weight = float(weight_str.replace('kg', '').strip())
                    except:
                        pass

                # 球员赛季统计
                player_stats = {
                    'appearances': stats.get('games', {}).get('appearences', 0),
                    'lineups': stats.get('games', {}).get('lineups', 0),
                    'minutes': stats.get('games', {}).get('minutes', 0),
                    'goals': stats.get('goals', {}).get('total', 0),
                    'assists': stats.get('goals', {}).get('assists', 0),
                    'yellow_cards': stats.get('cards', {}).get('yellow', 0),
                    'red_cards': stats.get('cards', {}).get('red', 0),
                    'shots_total': stats.get('shots', {}).get('total', 0),
                    'shots_on': stats.get('shots', {}).get('on', 0),
                    'passes_total': stats.get('passes', {}).get('total', 0),
                    'passes_accuracy': stats.get('passes', {}).get('accuracy', None),
                    'tackles_total': stats.get('tackles', {}).get('total', 0),
                    'duels_total': stats.get('duels', {}).get('total', 0),
                    'duels_won': stats.get('duels', {}).get('won', 0),
                    'rating': stats.get('games', {}).get('rating', None),
                }

                # 检查是否已存在
                cur.execute("SELECT player_id FROM players WHERE player_id = ?", (player_id,))
                exists = cur.fetchone()

                if exists:
                    # 更新
                    cur.execute("""
                        UPDATE players SET team_id=?, name=?, name_en=?, position=?,
                        nationality=?, age=?, height=?, weight=?, number=?,
                        photo_url=?, stats_json=? WHERE player_id=?
                    """, (
                        db_team_id, name, f"{firstname} {lastname}".strip(),
                        position, nationality, age, height, weight, number,
                        photo, json.dumps(player_stats, ensure_ascii=False),
                        player_id
                    ))
                else:
                    # 插入
                    cur.execute("""
                        INSERT INTO players (
                            player_id, team_id, name, name_en, position, nationality,
                            age, height, weight, number, market_value, photo_url,
                            stats_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        player_id, db_team_id, name, f"{firstname} {lastname}".strip(),
                        position, nationality, age, height, weight, number,
                        0, photo, json.dumps(player_stats, ensure_ascii=False),
                        datetime.now().isoformat()
                    ))
                    players_imported += 1

            except Exception as e:
                print(f"    球员导入错误: {e}")
                continue

        conn.commit()

        # 检查是否还有下一页
        paging = data.get('paging', {})
        if paging.get('current', 0) >= paging.get('total', 0):
            break
        page += 1
        time.sleep(0.5)  # 避免限流

    return players_imported


def main():
    print("=" * 60)
    print("球员数据导入工具 (API-Football)")
    print("=" * 60)

    # 加载API key
    api_key = load_api_key()
    if not api_key:
        print("\n[错误] 未找到 API_FOOTBALL_KEY")
        print("\n请按以下步骤配置：")
        print("1. 访问 https://www.api-football.com/ 注册免费账号")
        print("2. 在 Dashboard 复制你的 API Key")
        print(f"3. 在项目根目录创建 .env 文件，写入：")
        print(f"   API_FOOTBALL_KEY=你的key")
        print(f"\n或者运行: set API_FOOTBALL_KEY=你的key")
        print("\n免费 tier: 100请求/天，可导入约20-30支球队的球员")
        return

    init_api(api_key)
    print(f"\nAPI Key 已加载: {api_key[:8]}...")

    # 检查剩余请求
    current, limit = get_remaining_requests()
    remaining = limit - current
    print(f"今日剩余请求: {remaining}/{limit}")

    if remaining < 10:
        print("\n[警告] 剩余请求不足，建议明天再运行")
        return

    # 连接数据库
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 获取数据库球队
    db_mapping, db_teams = get_team_id_mapping(cur)
    print(f"\n数据库中球队数: {len(db_teams)}")

    # 加载进度
    progress = load_progress()
    completed = set(progress.get('completed_teams', []))
    print(f"已完成球队: {len(completed)}")
    print(f"已导入球员: {progress.get('total_players', 0)}")

    # 获取五大联赛的球队列表（API-Football）
    print("\n开始从 API-Football 获取球队列表...")
    api_teams = []
    for league_name, league_id in LEAGUE_IDS.items():
        print(f"  获取 {league_name} 球队...")
        data = api_get('/teams', {'league': league_id, 'season': CURRENT_SEASON})
        if data and 'response' in data:
            for t in data['response']:
                api_teams.append({
                    'api_id': t['team']['id'],
                    'name': t['team']['name'],
                    'league': league_name,
                })
        time.sleep(1)

    print(f"API 返回球队总数: {len(api_teams)}")

    # 匹配并导入
    total_imported = 0
    teams_processed = 0

    for api_team in api_teams:
        api_id = api_team['api_id']
        api_name = api_team['name']

        # 跳过已完成
        if str(api_id) in completed:
            continue

        # 匹配数据库team_id
        db_team_id = find_team_id_by_api_name(api_name, db_mapping, db_teams)
        if db_team_id is None:
            print(f"  跳过 (未匹配): {api_name}")
            continue

        # 检查剩余请求
        current, limit = get_remaining_requests()
        remaining = limit - current
        if remaining < 5:
            print(f"\n[提示] 剩余请求不足({remaining})，已保存进度，明天可继续运行")
            break

        print(f"\n导入: {api_name} (API ID: {api_id}, DB ID: {db_team_id})")
        print(f"  剩余请求: {remaining}")

        try:
            count = import_players_for_team(api_id, api_name, db_team_id, cur, conn)
            total_imported += count
            teams_processed += 1
            completed.add(str(api_id))
            print(f"  成功导入 {count} 名球员")
        except Exception as e:
            print(f"  导入失败: {e}")

        # 保存进度
        progress['completed_teams'] = list(completed)
        progress['total_players'] = progress.get('total_players', 0) + total_imported
        progress['last_update'] = datetime.now().isoformat()
        save_progress(progress)

        time.sleep(1)  # 避免限流

    conn.close()

    print("\n" + "=" * 60)
    print("导入完成")
    print(f"  本次处理球队: {teams_processed}")
    print(f"  本次导入球员: {total_imported}")
    print(f"  累计导入球员: {progress.get('total_players', 0)}")
    print(f"  进度已保存，下次运行将自动跳过已完成球队")
    print("=" * 60)


if __name__ == '__main__':
    main()
