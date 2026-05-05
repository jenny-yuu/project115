import requests
import json

def test_ask_ai():
    url = "http://127.0.0.1:5000/ask_ai"
    
    # 測試一個包含特定車站名稱的案例，這最能體現 Hybrid Search 的威力
    payload = {
        "query": "瑞芳車站 淹水 怎麼辦",
        "station_name": "瑞芳",
        "delay_time": 0,
        "is_suspended": True,
        "sim_type": "豪大雨",
        "sim_intensity": 50
    }
    
    print(f"🚀 正在發送測試請求到: {url}")
    print(f"📝 測試問題: {payload['query']}")
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            print("\n✅ 測試成功！AI 回答如下：")
            print("-" * 50)
            structured = result.get("structured", {})
            print(f"【總結】: {structured.get('summary')}")
            print(f"【建議】: {structured.get('ai_advice')}")
            print(f"【推薦路線】:")
            for r in structured.get('routes', []):
                print(f"  - [{r.get('priority')}] {r.get('title')}: {r.get('departure')} ({r.get('duration')})")
            print(f"【資料來源】: {structured.get('sources')}")
            print("-" * 50)
        else:
            print(f"❌ 測試失敗，狀態碼: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ 無法連線至伺服器: {e}")
        print("💡 請確認你是否已經執行了 'python app_bridge.py'")

if __name__ == "__main__":
    test_ask_ai()
