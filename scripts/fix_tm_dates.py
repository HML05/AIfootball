# -*- coding: utf-8 -*-
"""把 tm_player_market_value.date_unix(实为 YYYYMMDD) 规范为 ISO 日期列 value_date

用法: python scripts/fix_tm_dates.py
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
EXT = BASE / "data" / "external"
DB = BASE / "data" / "database" / "football.db"


def main():
    c = sqlite3.connect(str(DB))
    c.execute("PRAGMA journal_mode=WAL")
    df = pd.read_csv(EXT / "player_market_value" / "player_market_value.csv",
                     encoding="utf-8", on_bad_lines="skip", dtype=str)
    df["player_id"] = df["player_id"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    # 原始就是 'YYYY-MM-DD' 文本
    df["value_date"] = df["date_unix"].astype(str).str.slice(0, 10)
    ymd = pd.to_numeric(df["value_date"].str.replace("-", "", regex=False),
                        errors="coerce").astype("Int64")
    out = pd.DataFrame({
        "player_id": df["player_id"],
        "date_unix": ymd,
        "value_date": df["value_date"],
        "value": df["value"],
    })
    out = out.dropna(subset=["date_unix", "value"])
    out.to_sql("tm_player_market_value", c, if_exists="replace", index=False)
    c.execute("CREATE INDEX IF NOT EXISTS idx_tmmv_pid ON tm_player_market_value(player_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tmmv_date ON tm_player_market_value(value_date)")
    c.commit()
    q = lambda s: c.execute(s).fetchone()[0]
    print(f"写入 {q('SELECT COUNT(*) FROM tm_player_market_value'):,} 行")
    print("日期范围:", q("SELECT MIN(value_date) FROM tm_player_market_value"),
          "~", q("SELECT MAX(value_date) FROM tm_player_market_value"))
    print("\n当前身价 Top8:")
    for r in c.execute("""
        SELECT p.player_name, v.value, v.value_date FROM tm_player_market_value v
        JOIN tm_players p ON p.player_id=v.player_id
        ORDER BY v.value DESC LIMIT 8"""):
        print(f"   {r[0]:<26} {float(r[1])/1e6:6.0f}M€  {r[2]}")
    c.close()


if __name__ == "__main__":
    main()
