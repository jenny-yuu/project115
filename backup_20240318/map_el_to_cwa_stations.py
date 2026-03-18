import math
import requests
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====== 你只要改這裡 ======
CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
SEGMENTS_CSV = "tra_eastern_mainline_EL_segments.csv"

RAIN_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
WEATHER_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
# =========================

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def safe_float(x):
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "" or s.lower() == "nan":
            return None
        v = float(s)
        # CWA 常見缺測代碼（如 -990 / -999），當 None
        if v <= -90:
            return None
        return v
    except Exception:
        return None

def pick_wgs84_latlon(geo_info: dict):
    coords = (geo_info or {}).get("Coordinates") or []
    for c in coords:
        if c.get("CoordinateName") == "WGS84":
            lat = safe_float(c.get("StationLatitude"))
            lon = safe_float(c.get("StationLongitude"))
            if lat is not None and lon is not None:
                return lat, lon
    return None, None

def fetch_cwa_station_list(url: str, kind: str) -> pd.DataFrame:
    params = {"Authorization": CWA_KEY, "format": "JSON"}

    # ✅ 這裡加 verify=False 避免 SSL 憑證驗證失敗
    r = requests.get(url, params=params, timeout=30, verify=False)
    r.raise_for_status()
    data = r.json()

    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        name = s.get("StationName")
        obs_time = (s.get("ObsTime") or {}).get("DateTime")
        lat, lon = pick_wgs84_latlon(s.get("GeoInfo") or {})

        if not sid or lat is None or lon is None:
            continue

        rows.append({
            f"{kind}_StationId": sid,
            f"{kind}_StationName": name,
            f"{kind}_Lat": lat,
            f"{kind}_Lon": lon,
            f"{kind}_ObsTime": obs_time,
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=[f"{kind}_StationId"])
    return df

def map_segments_to_nearest(seg_df: pd.DataFrame, station_df: pd.DataFrame, kind: str) -> pd.DataFrame:
    station_records = station_df.to_dict("records")
    out_rows = []

    for _, seg in seg_df.iterrows():
        mid_lat = safe_float(seg.get("MidLat"))
        mid_lon = safe_float(seg.get("MidLon"))

        best = None
        best_d = 1e18

        if mid_lat is not None and mid_lon is not None:
            for s in station_records:
                d = haversine_km(mid_lat, mid_lon, s[f"{kind}_Lat"], s[f"{kind}_Lon"])
                if d < best_d:
                    best_d = d
                    best = s

        out = seg.to_dict()
        if best is None:
            out[f"Nearest_{kind}_StationId"] = None
            out[f"Nearest_{kind}_StationName"] = None
            out[f"DistTo_{kind}_KM"] = None
            out[f"{kind}_ObsTime"] = None
        else:
            out[f"Nearest_{kind}_StationId"] = best[f"{kind}_StationId"]
            out[f"Nearest_{kind}_StationName"] = best[f"{kind}_StationName"]
            out[f"DistTo_{kind}_KM"] = round(best_d, 3)
            out[f"{kind}_ObsTime"] = best.get(f"{kind}_ObsTime")

        out_rows.append(out)

    return pd.DataFrame(out_rows)

def main():
    seg = pd.read_csv(SEGMENTS_CSV, encoding="utf-8-sig")

    print("下載雨量站清單（O-A0002-001）...")
    rain_st = fetch_cwa_station_list(RAIN_URL, kind="RAIN")
    print("雨量站數：", len(rain_st))

    print("下載綜觀氣象站清單（O-A0003-001）...")
    wx_st = fetch_cwa_station_list(WEATHER_URL, kind="WEATHER")
    print("綜觀氣象站數：", len(wx_st))

    print("建立 路段→最近雨量站 對應表...")
    seg_to_rain = map_segments_to_nearest(seg, rain_st, kind="RAIN")
    out1 = "el_segments_to_rain_station.csv"
    seg_to_rain.to_csv(out1, index=False, encoding="utf-8-sig")
    print("✅ 已輸出：", out1)

    print("建立 路段→最近綜觀氣象站 對應表...")
    seg_to_wx = map_segments_to_nearest(seg, wx_st, kind="WEATHER")
    out2 = "el_segments_to_weather_station.csv"
    seg_to_wx.to_csv(out2, index=False, encoding="utf-8-sig")
    print("✅ 已輸出：", out2)

    print("\n--- 驗收：距離統計（km）---")
    print("雨量站距離：")
    print(seg_to_rain["DistTo_RAIN_KM"].describe())
    print("\n綜觀站距離：")
    print(seg_to_wx["DistTo_WEATHER_KM"].describe())

    print("\n--- 驗收：前 5 筆（雨量站對應）---")
    print(seg_to_rain[[
        "FromStationName", "ToStationName",
        "Nearest_RAIN_StationName", "DistTo_RAIN_KM"
    ]].head(5))

    print("\n--- 驗收：前 5 筆（綜觀站對應）---")
    print(seg_to_wx[[
        "FromStationName", "ToStationName",
        "Nearest_WEATHER_StationName", "DistTo_WEATHER_KM"
    ]].head(5))

if __name__ == "__main__":
    main()