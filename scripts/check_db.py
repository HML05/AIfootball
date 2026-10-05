import sqlite3
conn = sqlite3.connect('data/database/football.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print('=== 数据库表 ===')
for t in tables:
    cur.execute(f'SELECT COUNT(*) FROM {t[0]}')
    cnt = cur.fetchone()[0]
    print(f'  {t[0]}: {cnt} 条')
print()
for t in tables:
    cur.execute(f'PRAGMA table_info({t[0]})')
    cols = cur.fetchall()
    print(f'=== {t[0]} 结构 ===')
    for c in cols:
        print(f'  {c[1]} ({c[2]})')
    print()
conn.close()
