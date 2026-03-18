import os
import requests
import time
from dotenv import load_dotenv

env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
if not os.path.exists(env_path):
    env_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\.env"
load_dotenv(dotenv_path=env_path)

TDX_APP_ID = os.getenv("TDX_CLIENT_ID", "YOUR_TDX_APP_ID")
TDX_APP_KEY = os.getenv("TDX_CLIENT_SECRET", "YOUR_TDX_APP_KEY")

def get_tdx_token():
    token_url = 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
    data = {
        'grant_type': 'client_credentials',
        'client_id': TDX_APP_ID,
        'client_secret': TDX_APP_KEY
    }
    response = requests.post(token_url, data=data)
    return response.json()['access_token']

def test_api():
    token = get_tdx_token()
    headers = {'Authorization': f'Bearer {token}'}
    
    print("請求 TDX [跨運具轉乘資訊] API...")
    url = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/StationTransfer?$format=JSON"
    res = requests.get(url, headers=headers).json()
    
    stations = []
    for item in res.get('StationTransfers', []):
        sname = item.get('StationName', {}).get('Zh_tw', '')
        if sname:
            stations.append(sname)
            
    print(f"驚人發現：TDX 全台灣『有跨運具轉乘』的車站總共只有 {len(stations)} 個！")
    
    # 檢查羅東有沒有在裡面
    if any("羅東" in s for s in stations):
        print("✅ 羅東在名單內！")
    else:
        print("❌ 羅東竟然不在 TDX 的跨運具轉乘名單內！")

if __name__ == "__main__":
    test_api()
