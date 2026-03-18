import os
import requests
import pandas as pd


# =================設定區=================
# 請填入你的 ID 和 Secret
TDX_ID = 'u11216031-bc7bb8bf-ed67-4bc6'
TDX_SECRET = '50ced1f4-73d3-462c-ba09-4eebae7e9d4a'
# =======================================

AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
LIVE_DELAY_URL = "https://tdx.transportdata.tw/api/basic/v2/Rail/TRA/LiveTrainDelay"

EL_STATIONS_CSV = "tra_eastern_mainline_EL_stations.csv"

def get_token():
    r = requests.post(
        AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": TDX_ID,
            "client_secret": TDX_SECRET,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    # 1) 讀 EL 站清單
    el = pd.read_csv(EL_STATIONS_CSV, encoding="utf-8-sig")
    el_station_ids = set(el["StationID"].astype(str))

    # 2) 抓 LiveTrainDelay
    token = get_token()
    headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
    r = requests.get(LIVE_DELAY_URL, headers=headers, params={"$format": "JSON"}, timeout=30)
    r.raise_for_status()
    data = r.json()

    # 3) 篩 EL + DelayTime > 0
    rows = []
    for x in data:
        sid = str(x.get("StationID"))
        delay = x.get("DelayTime")
        if sid in el_station_ids and delay is not None and int(delay) > 0:
            rows.append({
                "TrainNo": x.get("TrainNo"),
                "StationID": sid,
                "StationName": (x.get("StationName") or {}).get("Zh_tw"),
                "DelayTime": int(delay),
                "SrcUpdateTime": x.get("SrcUpdateTime"),
                "UpdateTime": x.get("UpdateTime"),
            })

    df = pd.DataFrame(rows).sort_values("DelayTime", ascending=False)
    print("東部幹線（EL）目前延誤列車筆數：", len(df))
    print(df.head(20))

if __name__ == "__main__":
    main()