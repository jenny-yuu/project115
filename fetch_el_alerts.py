import os
import requests
import pandas as pd

# =================設定區=================
# 請填入你的 ID 和 Secret
TDX_ID = 'u11216031-bc7bb8bf-ed67-4bc6'
TDX_SECRET = '50ced1f4-73d3-462c-ba09-4eebae7e9d4a'
# =======================================


AUTH_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
ALERT_URL = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/Alert"

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
    # 1) EL 站清單
    el = pd.read_csv(EL_STATIONS_CSV, encoding="utf-8-sig")
    el_station_ids = set(el["StationID"].astype(str))

    # 2) 抓 Alert
    token = get_token()
    headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
    r = requests.get(ALERT_URL, headers=headers, params={"$format": "JSON"}, timeout=30)
    r.raise_for_status()
    data = r.json()

    alerts = data.get("Alerts", [])
    rows = []
    
    # 抓 Alert 後，加這段
    alerts = data.get("Alerts", [])
    print("目前 Alert 總筆數：", len(alerts))

    # # 印前 5 則（只印標題/範圍）
    # for a in alerts[:5]:
    #     scope = a.get("Scope") or {}
    #     stations = scope.get("Stations") or []
    #     line_sections = scope.get("LineSections") or []
    #     print("----")
    #     print("Title:", a.get("Title"))
    #     print("Reason:", a.get("Reason"))
    #     print("Level:", a.get("Level"))
    #     print("Status:", a.get("Status"))
    #     print("Stations:", [s.get("StationName") for s in stations[:10]])
    #     print("LineSections:", [(sec.get("LineID"), sec.get("StartingStationName"), sec.get("EndingStationName")) for sec in line_sections[:5]])

    for a in alerts:
        scope = a.get("Scope") or {}
        stations = scope.get("Stations") or []
        line_sections = scope.get("LineSections") or []

        hit_station_ids = []
        for s in stations:
            sid = str(s.get("StationID", ""))
            if sid in el_station_ids:
                hit_station_ids.append(sid)

        # line section 也檢查（有些公告不一定列出 Stations，但會列 LineSections）
        hit_by_section = False
        for sec in line_sections:
            st = str(sec.get("StartingStationID", ""))
            ed = str(sec.get("EndingStationID", ""))
            if st in el_station_ids or ed in el_station_ids:
                hit_by_section = True

        if hit_station_ids or hit_by_section:
            rows.append({
                "AlertID": a.get("AlertID"),
                "Title": a.get("Title"),
                "Reason": a.get("Reason"),
                "Level": a.get("Level"),
                "Effect": a.get("Effect"),
                "Status": a.get("Status"),
                "StartTime": a.get("StartTime"),
                "EndTime": a.get("EndTime"),
                "PublishTime": a.get("PublishTime"),
                "UpdateTime": a.get("UpdateTime"),
                "HitStations": ",".join(hit_station_ids),
                "Description": (a.get("Description") or "").replace("\n", " ").strip(),
                "AlertURL": a.get("AlertURL"),
            })
    df = pd.DataFrame(rows)

    if df.empty:
        print("目前沒有影響東部幹線（EL）的營運通阻公告。")
    else:
        df = df.sort_values(["Level", "UpdateTime"], ascending=[False, False])
        print("影響東部幹線（EL）的公告筆數：", len(df))
        print(df[["Title","Level","Status","StartTime","EndTime","HitStations"]].head(20))
        df.to_csv("el_alerts.csv", index=False, encoding="utf-8-sig")
        print("已輸出：el_alerts.csv")
        out = "el_alerts.csv"
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print("已輸出：", out)

if __name__ == "__main__":
    main()