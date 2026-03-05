import os
import requests
from dotenv import load_dotenv

env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
load_dotenv(dotenv_path=env_path)

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

def get_tdx_token():
    r = requests.post(
        "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token",
        data={"grant_type": "client_credentials", "client_id": TDX_CLIENT_ID, "client_secret": TDX_CLIENT_SECRET},
        timeout=10
    )
    if r.status_code == 200:
        print("✅ Token OK")
        return r.json().get("access_token")
    print(f"❌ Token 失敗: {r.status_code}")
    return None

token = get_tdx_token()
if token:
    headers = {"Authorization": f"Bearer {token}", "Accept-Encoding": "gzip"}

    # 測試 DailyTimeTable
    url = "https://tdx.transportdata.tw/api/basic/v2/Bus/DailyTimeTable/InterCity?$top=5&$format=JSON"
    r = requests.get(url, headers=headers, timeout=10)
    print(f"\n[DailyTimeTable] HTTP {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"✅ 成功！筆數: {len(data)}")
        if data:
            print(f"第一筆 keys: {list(data[0].keys())}")
            print(f"第一筆: {data[0]}")
    else:
        print(f"❌ {r.text[:300]}")

    # 測試帶 filter
    url2 = "https://tdx.transportdata.tw/api/basic/v2/Bus/DailyTimeTable/InterCity?$filter=contains(OriginStopName/Zh_tw,'花蓮')&$top=5&$format=JSON"
    r2 = requests.get(url2, headers=headers, timeout=10)
    print(f"\n[DailyTimeTable + filter 花蓮] HTTP {r2.status_code}")
    if r2.status_code == 200:
        data2 = r2.json()
        print(f"✅ 成功！筆數: {len(data2)}")
        for item in data2[:3]:
            dep = item.get("DepartureTime", item.get("OriginStopName", {}).get("Zh_tw","?"))
            print(f"  → {item}")
    else:
        print(f"❌ {r2.text[:300]}")
