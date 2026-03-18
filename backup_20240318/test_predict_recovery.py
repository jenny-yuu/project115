import requests
import json

def test_recovery(station="瑞芳", query="瑞芳車站因地震停駛，請推估恢復時間"):
    url = "http://127.0.0.1:5000/predict_recovery"
    payload = {
        "station_name": station,
        "query": query
    }
    
    print(f"🚀 正在發送模擬請求：{station} - {query}")
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print("✅ 接收到預估結果：")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"❌ 請求失敗，狀態碼：{response.status_code}")
    except Exception as e:
        print(f"❌ 發生錯誤：{e}")

if __name__ == "__main__":
    # 測試瑞芳強震情境 (驗證是否命中剛補入的官方 SOP 與專家知識)
    # 關鍵字：震度 5 級、電化區間、巡軌
    test_recovery("瑞芳", "目前偵測到瑞芳車站震度達 5 級，變電站斷電，列車立即停車，請依照 SOP 推估恢復所需時間。")
    print("-" * 30)
    # 測試光復站大雨情境 (驗證是否命中低窪地形特徵)
    test_recovery("光復", "光復車站目前強降雨累積達 100mm，疑似受到堰塞湖溢流影響，請推估恢復時間。")
