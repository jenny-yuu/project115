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
SEG_LIVE_WEATHER_CSV = "el_segments_with_live_weather.csv"
OUT_CSV = "el_segments_with_live_weather_and_delay.csv"

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
    # 1) 讀 EL station list
    el = pd.read_csv(EL_STATIONS_CSV, encoding="utf-8-sig")
    el_station_ids = set(el["StationID"].astype(str))

    # 2) 讀「路段+即時氣象」表
    seg = pd.read_csv(SEG_LIVE_WEATHER_CSV, encoding="utf-8-sig")

    # 嘗試找出 From/To StationID 欄位（你檔案有 _rainMap/_wxMap 時也能吃）
    from_col = "FromStationID" if "FromStationID" in seg.columns else "FromStationID_rainMap"
    to_col   = "ToStationID"   if "ToStationID"   in seg.columns else "ToStationID_rainMap"
    if from_col not in seg.columns or to_col not in seg.columns:
        raise RuntimeError(f"找不到 From/To StationID 欄位，請檢查 {SEG_LIVE_WEATHER_CSV} 欄位名稱")

    seg[from_col] = seg[from_col].astype(str)
    seg[to_col] = seg[to_col].astype(str)

    # 3) 抓 LiveTrainDelay
    token = get_token()
    headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
    r = requests.get(LIVE_DELAY_URL, headers=headers, params={"$format":"JSON"}, timeout=30)
    r.raise_for_status()
    data = r.json()

    # 4) 篩 EL + DelayTime>0，整理成 station -> (max delay, count, trains)
    station_delay = {}  # sid -> dict
    for x in data:
        sid = str(x.get("StationID"))
        delay = x.get("DelayTime")
        if sid not in el_station_ids:
            continue
        if delay is None or int(delay) <= 0:
            continue

        train = str(x.get("TrainNo"))
        info = station_delay.get(sid, {"max_delay": 0, "count": 0, "trains": []})
        info["count"] += 1
        info["max_delay"] = max(info["max_delay"], int(delay))
        info["trains"].append(train)
        station_delay[sid] = info

    # 5) 掛回路段（From 或 To 站只要有延誤就算）
    delay_max_list = []
    delay_count_list = []
    delay_trains_list = []

    for _, row in seg.iterrows():
        from_id = row[from_col]
        to_id = row[to_col]

        infos = []
        if from_id in station_delay:
            infos.append(station_delay[from_id])
        if to_id in station_delay and to_id != from_id:
            infos.append(station_delay[to_id])

        if not infos:
            delay_max_list.append(0)
            delay_count_list.append(0)
            delay_trains_list.append("")
        else:
            delay_max_list.append(max(i["max_delay"] for i in infos))
            delay_count_list.append(sum(i["count"] for i in infos))
            trains = []
            for i in infos:
                trains.extend(i["trains"])
            # 去重、保持可讀
            trains = sorted(set(trains), key=lambda x: (len(x), x))
            delay_trains_list.append(",".join(trains))

    seg["DelayMaxMin"] = delay_max_list
    seg["DelayCount"] = delay_count_list
    seg["DelayedTrainNos"] = delay_trains_list

    seg.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print("✅ 已輸出：", OUT_CSV)
    print(seg[["DelayMaxMin","DelayCount","DelayedTrainNos"]].describe())
    print("\n--- 目前有延誤的路段（前 10 筆）---")
    print(seg[seg["DelayCount"]>0][[from_col,to_col,"DelayMaxMin","DelayCount","DelayedTrainNos"]].head(10))

if __name__ == "__main__":
    main()