import requests
import json

print("=== 预测模型信息 ===")
try:
    resp = requests.get("http://127.0.0.1:8000/api/predictions/model/info", timeout=5)
    info = resp.json()
    for k, v in info.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        elif isinstance(v, list):
            print(f"  {k}: {v[:5]}..." if len(v)>5 else f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")
except Exception as e:
    print(f"  获取失败: {e}")

print("\n=== 测试比赛预测 (曼城 vs 阿森纳) ===")
try:
    resp = requests.post("http://127.0.0.1:8000/api/predictions/predict",
        json={"home_team": "Man City", "away_team": "Arsenal"}, timeout=10)
    pred = resp.json()
    print(f"  预测结果: {pred.get('prediction', 'N/A')}")
    probs = pred.get("probabilities", {})
    if probs:
        print(f"  主胜概率: {probs.get('home', 0):.1%}")
        print(f"  平局概率: {probs.get('draw', 0):.1%}")
        print(f"  客胜概率: {probs.get('away', 0):.1%}")
    features = pred.get("top_features", [])
    if features:
        print(f"  Top特征: {[f.get('feature') for f in features[:3]]}")
except Exception as e:
    print(f"  预测失败: {e}")

print("\n=== 系统健康检查 ===")
try:
    resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
    health = resp.json()
    for k, v in health.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"  健康检查失败: {e}")
