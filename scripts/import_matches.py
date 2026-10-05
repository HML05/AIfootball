"""
比赛数据导入脚本
从 data/processed/all_matches.csv 导入比赛数据到数据库 matches 表
支持增量更新：已存在的比赛会跳过
"""
import csv
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'database' / 'football.db'
CSV_PATH = Path(__file__).parent.parent / 'data' / 'processed' / 'all_matches.csv'

# 联赛代码映射
LEAGUE_CODE_MAP = {
    'E0': '英超', 'SP1': '西甲', 'D1': '德甲', 'I1': '意甲', 'F1': '法甲'
}

def get_team_id_by_name(cur, name_en):
    """根据英文队名获取球队ID"""
    cur.execute("SELECT team_id FROM teams WHERE name_en = ?", (name_en,))
    row = cur.fetchone()
    return row[0] if row else None

def get_league_id_by_name(cur, name):
    """根据联赛名获取联赛ID"""
    cur.execute("SELECT league_id FROM leagues WHERE name = ?", (name,))
    row = cur.fetchone()
    return row[0] if row else None

def match_exists(cur, home_id, away_id, date_str):
    """检查比赛是否已存在"""
    cur.execute(
        "SELECT match_id FROM matches WHERE home_team_id = ? AND away_team_id = ? AND date = ?",
        (home_id, away_id, date_str)
    )
    return cur.fetchone() is not None

def import_matches():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 读取CSV
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    imported = 0
    skipped = 0
    no_team = 0
    errors = 0

    print(f"共读取 {total} 场比赛，开始导入...")

    for i, row in enumerate(rows):
        try:
            league_name = row.get('league', '')
            league_code = row.get('league_code', '')
            if not league_name:
                league_name = LEAGUE_CODE_MAP.get(league_code, '')

            home_name = row['HomeTeam'].strip()
            away_name = row['AwayTeam'].strip()
            date_str = row['Date'].strip()
            time_str = row.get('Time', '00:00').strip()
            season = row.get('season', '')

            # 获取球队ID
            home_id = get_team_id_by_name(cur, home_name)
            away_id = get_team_id_by_name(cur, away_name)

            if home_id is None or away_id is None:
                no_team += 1
                if no_team <= 5:
                    print(f"  球队未找到: {home_name}({home_id}) vs {away_name}({away_id})")
                continue

            # 检查是否已存在
            if match_exists(cur, home_id, away_id, date_str):
                skipped += 1
                continue

            def safe_int(val):
                """安全转换为int，处理'1.0'格式"""
                if not val or val == '':
                    return 0
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return 0

            def safe_float(val):
                """安全转换为float"""
                if not val or val == '':
                    return 0.0
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0

            # 解析比分
            fthg = safe_int(row['FTHG'])
            ftag = safe_int(row['FTAG'])
            ftr = row.get('FTR', '')

            # 详细统计
            stats = {
                'half_time_home_goals': safe_int(row.get('HTHG')),
                'half_time_away_goals': safe_int(row.get('HTAG')),
                'half_time_result': row.get('HTR', ''),
                'home_shots': safe_float(row.get('HS')),
                'away_shots': safe_float(row.get('AS')),
                'home_shots_on_target': safe_float(row.get('HST')),
                'away_shots_on_target': safe_float(row.get('AST')),
                'home_fouls': safe_float(row.get('HF')),
                'away_fouls': safe_float(row.get('AF')),
                'home_corners': safe_float(row.get('HC')),
                'away_corners': safe_float(row.get('AC')),
                'home_yellow_cards': safe_float(row.get('HY')),
                'away_yellow_cards': safe_float(row.get('AY')),
                'home_red_cards': safe_float(row.get('HR')),
                'away_red_cards': safe_float(row.get('AR')),
                'home_xg': safe_float(row.get('HxG')) if row.get('HxG') else None,
                'away_xg': safe_float(row.get('AxG')) if row.get('AxG') else None,
            }

            # 获取联赛ID
            league_id = get_league_id_by_name(cur, league_name)

            # 插入比赛
            cur.execute("""
                INSERT INTO matches (
                    league_id, season, matchday, date, home_team_id, away_team_id,
                    home_goals, away_goals, status, home_xg, away_xg, stats_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                league_id, season, 0,
                f"{date_str} {time_str}",
                home_id, away_id,
                fthg, ftag,
                'FT',  # Full Time
                stats.get('home_xg'),
                stats.get('away_xg'),
                json.dumps(stats, ensure_ascii=False),
                datetime.now().isoformat()
            ))
            imported += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  错误: {e} | 行: {row.get('HomeTeam')} vs {row.get('AwayTeam')}")

        if (i + 1) % 1000 == 0:
            print(f"  进度: {i+1}/{total}, 已导入 {imported}, 跳过 {skipped}")
            conn.commit()

    conn.commit()
    conn.close()

    print(f"\n=== 导入完成 ===")
    print(f"  总计: {total}")
    print(f"  成功导入: {imported}")
    print(f"  已存在跳过: {skipped}")
    print(f"  球队未找到: {no_team}")
    print(f"  错误: {errors}")

if __name__ == '__main__':
    import_matches()
