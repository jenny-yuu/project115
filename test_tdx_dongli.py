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

def test_dongli():
    token = get_tdx_token()
    headers = {'Authorization': f'Bearer {token}'}
    
    # 測試東里站
    station_transfer_url = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/StationTransfer?$format=JSON"
    res = requests.get(station_transfer_url, headers=headers).json()
    
    print("尋找東里的轉乘資料...")
    found = False
    for item in res.get('StationTransfers', []):
        sname = item.get('StationName', {}).get('Zh_tw', '')
        if '東里' in sname:
            found = True
            print(f"找到 {sname} 的轉乘資料:")
            for trans in item.get('Transfers', []):
                mode = trans.get('TransferMode', '')
                rname = trans.get('RouteName', {}).get('Zh_tw', '')
                print(f"  - {mode}: {rname}")
                
    if not found:
        print("❌ 在 TDX 跨運具轉乘 API 中找不到【東里】的任何轉乘路線！")
        
    print("\n尋找東里內部路線轉乘...")
    line_transfer_url = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/LineTransfer?$format=JSON"
    res2 = requests.get(line_transfer_url, headers=headers).json()
    found2 = False
    for item in res2.get('LineTransfers', []):
        sname = item.get('StationName', {}).get('Zh_tw', '')
        if '東里' in sname:
            found2 = True
            print(f"找到 {sname} 的內部路線轉乘:")
            for trans in item.get('Transfers', []):
                 print(f"  - {trans.get('ToLineName', {}).get('Zh_tw', '')}")
                 
    if not found2:
        print("❌ 在 TDX 內部路線轉乘 API 中找不到【東里】的任何資料！")

if __name__ == "__main__":
    test_dongli()
