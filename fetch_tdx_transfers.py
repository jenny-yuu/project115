import os
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import time
from dotenv import load_dotenv

# 載入環境變數
env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
if not os.path.exists(env_path):
    env_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\.env"
load_dotenv(dotenv_path=env_path)

# =================設定區=================
CREDENTIAL_PATH = r"C:\Users\jenny\OneDrive\桌面\115 專題\your-firebase-adminsdk.json" 
COLLECTION_NAME = "stations" 
# TDX API ID & Key (需從 .env 讀取或直接填寫)
TDX_APP_ID = os.getenv("TDX_CLIENT_ID", "YOUR_TDX_APP_ID")
TDX_APP_KEY = os.getenv("TDX_CLIENT_SECRET", "YOUR_TDX_APP_KEY")
# ========================================

def init_firebase():
    """初始化 Firebase 連線"""
    try:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except ValueError:
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {e}")
        exit()

def get_tdx_token():
    """取得 TDX Access Token"""
    token_url = 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': TDX_APP_ID,
        'client_secret': TDX_APP_KEY
    }
    
    if TDX_APP_ID == "YOUR_TDX_APP_ID":
        print("⚠️ 警告：未設定 TDX APP ID，將嘗試無 Token 存取 (可能受限)")
        return None

    try:
        response = requests.post(token_url, data=data)
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            print(f"❌ 取得 TDX Token 失敗: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ 取得 TDX Token 發生例外錯誤: {e}")
        return None

def fetch_tdx_data(url, token):
    """取得 TDX 資料"""
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
        
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
             print("⚠️ TDX API 速率限制，等待 5 秒後重試...")
             time.sleep(5)
             return fetch_tdx_data(url, token)
        else:
            print(f"❌ 取得資料失敗 {url}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 網路連線錯誤 {url}: {e}")
        return None

def process_and_upload(db):
    print("1. 取得 TDX Auth Token...")
    token = get_tdx_token()
    
    print("2. 下載 [跨運具轉乘資訊] StationTransfer...")
    station_transfer_url = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/StationTransfer?$format=JSON"
    station_transfers = fetch_tdx_data(station_transfer_url, token)
    
    print("3. 下載 [內部路線轉乘] LineTransfer...")
    line_transfer_url = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/LineTransfer?$format=JSON"
    line_transfers = fetch_tdx_data(line_transfer_url, token)
    
    if not station_transfers or not line_transfers:
        print("❌ 無法取得完整 TDX 轉乘資料，腳本終止。")
        return

    # 建立一個字典，用 StationName 當作 Key
    transfers_map = {}
    
    print("4. 整理 [跨運具轉乘] 資料...")
    for item in station_transfers.get('StationTransfers', []):
        station_name_dict = item.get('StationName', {})
        station_name = station_name_dict.get('Zh_tw', '')
        # 移除 '車站' 兩個字以方便比對 (例如: "花蓮車站" -> "花蓮")
        if station_name.endswith('車站') or station_name.endswith('車站'):
            station_name = station_name[:-2]
        elif station_name.endswith('站'):
            station_name = station_name[:-1]
            
        if not station_name: continue
        
        if station_name not in transfers_map:
            transfers_map[station_name] = {"external": [], "internal": []}
            
        for trans in item.get('Transfers', []):
            route_name = trans.get('RouteName', {}).get('Zh_tw', '')
            mode = trans.get('TransferMode', '') # Bus, Metro, etc.
            if route_name:
                transfers_map[station_name]["external"].append(f"{mode}:{route_name}")
                
    print("5. 整理 [台鐵內部轉乘] 資料...")
    for item in line_transfers.get('LineTransfers', []):
        station_name_dict = item.get('StationName', {})
        station_name = station_name_dict.get('Zh_tw', '')
        if station_name.endswith('車站'):
            station_name = station_name[:-2]
        elif station_name.endswith('站'):
            station_name = station_name[:-1]
            
        if not station_name: continue
        
        if station_name not in transfers_map:
            transfers_map[station_name] = {"external": [], "internal": []}
            
        for trans in item.get('Transfers', []):
            to_line = trans.get('ToLineName', {}).get('Zh_tw', '')
            if to_line:
                transfers_map[station_name]["internal"].append(to_line)
                
    # 去除重複項
    for sname in transfers_map:
        transfers_map[sname]["external"] = list(set(transfers_map[sname]["external"]))
        transfers_map[sname]["internal"] = list(set(transfers_map[sname]["internal"]))

    # 秘密印出 TDX 前 20 個車站名字讓我們看看長怎樣並存成檔案
    sample_names = list(transfers_map.keys())
    with open('tdx_names.json', 'w', encoding='utf-8') as f:
        import json
        json.dump(sample_names, f, ensure_ascii=False, indent=2)
    
    success_count = 0
    for doc in db.collection(COLLECTION_NAME).stream():
        doc_id = doc.id
        fb_station_name = doc.to_dict().get("StationName", "")
        
        # 尋找匹配
        match_data = None
        for t_name, t_data in transfers_map.items():
            if t_name in fb_station_name or fb_station_name in t_name:
                match_data = t_data
                break
        
        if match_data:
            try:
                db.collection(COLLECTION_NAME).document(doc_id).update({
                    "transfers": match_data
                })
                success_count += 1
                if success_count % 10 == 0:
                    print(f"   已更新 {success_count} 個車站...")
            except Exception as e:
                print(f"   更新車站 {doc_id} 失敗: {e}")
                
    print(f"\n🎉 恭喜！成功為 {success_count} 個現有車站增加了 `transfers` 屬性。")

if __name__ == "__main__":
    db = init_firebase()
    process_and_upload(db)
