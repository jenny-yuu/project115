import os
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime

# =================設定區=================
# 1. 替換為您的 Firebase 服務帳號金鑰檔案名稱
CREDENTIAL_PATH = "your-firebase-adminsdk.json"
COLLECTION_NAME = "stations"

# 2. TDX API 的 ID 和 Secret
TDX_ID = 'u11216031-bc7bb8bf-ed67-4bc6'
TDX_SECRET = '50ced1f4-73d3-462c-ba09-4eebae7e9d4a'

AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
LIVE_DELAY_URL = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/LiveTrainDelay"
# ========================================

def init_firebase():
    """初始化 Firebase 連線"""
    try:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase 初始化成功！")
        return db
    except ValueError:
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {e}")
        exit()

def get_token():
    """取得 TDX API token"""
    r = requests.post(
        AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": TDX_ID,
            "client_secret": TDX_SECRET,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def fetch_live_delay():
    """抓取 TDX 台鐵即時誤點資料"""
    try:
        token = get_token()
        headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
        r = requests.get(LIVE_DELAY_URL, headers=headers, params={"$format": "JSON"}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ TDX API 請求失敗: {e}")
        return None

def update_firebase_delay(db, delay_data):
    """將即時誤點資料更新回 Firebase 的 stations 集合內"""
    if delay_data is None:
        print("⚠️ 無法獲取即時誤點資料，跳過更新。")
        return
        
    print(f"準備分析 {len(delay_data)} 筆全台即時列車狀態...")
    
    # 用字典整理每個車站的誤點資訊：我們記錄該站「最大的誤點時間」及「受影響車次清單」
    # 資料結構: station_id -> { "max_delay": 0, "delayed_trains": [] }
    station_delays = {}
    
    for train in delay_data:
        sid = str(train.get("StationID"))
        delay_time = train.get("DelayTime")
        train_no = train.get("TrainNo")
        
        # 排除空值或沒有誤點的列車 (DelayTime <= 0)
        if not sid or delay_time is None or int(delay_time) <= 0:
            continue
            
        delay_time = int(delay_time)
        
        if sid not in station_delays:
            station_delays[sid] = {"max_delay": 0, "delayed_trains": []}
            
        # 更新該站的最大誤點時間
        if delay_time > station_delays[sid]["max_delay"]:
            station_delays[sid]["max_delay"] = delay_time
            
        # 加入延誤車次
        station_delays[sid]["delayed_trains"].append({
            "TrainNo": train_no,
            "DelayTime": delay_time
        })

    print(f"👉 共有 {len(station_delays)} 個車站目前有列車延誤事件。開始更新 Firebase...")
    
    # 批次更新 Firebase (Batch write 可以加快速度並減少 API 呼叫次數)
    batch = db.batch()
    stations_ref = db.collection(COLLECTION_NAME)
    update_count = 0
    current_time = datetime.datetime.now().isoformat()
    
    # 策略：因為並非所有車站都在東部幹線（我們只匯入了 64 站），
    # 所以要先抓取目前 Firebase 中的所有車站 ID 來過濾
    existing_stations = [doc.id for doc in stations_ref.stream()]
    
    # 1. 先把所有 Firebase 裡的車站誤點歸零 (避免前一班車誤點，但這班車沒誤點時，狀態沒更新回來)
    for sid in existing_stations:
        doc_ref = stations_ref.document(sid)
        
        # 檢查這個站現在有沒有誤點
        if sid in station_delays:
            # 發生誤點
            info = station_delays[sid]
            batch.update(doc_ref, {
                "live_delay_max_minutes": info["max_delay"],
                "live_delay_trains": info["delayed_trains"],
                "live_status_updated_at": current_time,
                "is_delayed": True,
                "health_light": "黃燈" # 根據企劃書，誤點為黃燈
            })
            update_count += 1
        else:
            # 沒誤點，狀態歸零
            batch.update(doc_ref, {
                "live_delay_max_minutes": 0,
                "live_delay_trains": [],
                "live_status_updated_at": current_time,
                "is_delayed": False,
                "health_light": "正常"
            })
            
        # Firestore batch 上限是 500 筆，我們數量少所以不用分批 commit
        
    # 執行更新
    batch.commit()
    print(f"🎉 成功更新了 {update_count} 個車站的誤點狀態到 Firebase！")
    print(f"其餘 {len(existing_stations) - update_count} 個車站標示為正常。")

if __name__ == "__main__":
    db = init_firebase()
    data = fetch_live_delay()
    update_firebase_delay(db, data)
