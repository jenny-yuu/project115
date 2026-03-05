import math
import requests
import pandas as pd
import urllib3

# ====== 設定區 ======
CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"

SEGMENTS_CSV = "tra_eastern_mainline_EL_segments.csv"
OUT_CSV = "el_segments_with_eq.csv"

AREA_NAMES = ["宜蘭縣", "花蓮縣", "臺東縣"]
INSECURE_SSL = True  # 先 True 跑通；之後 SSL 修好改 False
# ====================


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def lzone_from_dist_km(d):
    if d <= 5:
        return "Station"
    elif d <= 20:
        return "Adjacent"
    else:
        return "Regional"


def slevel_from_intensity(intensity):
    if intensity is None:
        return "Normal"
    if intensity < 3:
        return "Normal"
    elif intensity < 5:
        return "Alert"
    else:
        return "Critical"


def fetch_eq(limit=50, offset=0):
    params = [
        ("Authorization", CWA_KEY),
        ("format", "JSON"),
        ("limit", limit),
        ("offset", offset),
        ("sort", "OriginTime"),
    ]
    for a in AREA_NAMES:
        params.append(("AreaName", a))

    if INSECURE_SSL:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(EQ_URL, params=params, timeout=30, verify=False)
    else:
        r = requests.get(EQ_URL, params=params, timeout=30)

    r.raise_for_status()
    data = r.json()

    # 讓你確定不是拿到空/錯誤格式
    print("✅ 地震API success =", data.get("success"))
    print("✅ records keys =", list(data.get("records", {}).keys()))
    return data


def extract_events(payload):
    records = payload.get("records", {})
    list_key = None
    for k, v in records.items():
        if isinstance(v, list):
            list_key = k
            break
    if list_key is None:
        return []
    return records[list_key]


def get_epicenter_and_intensity(event):
    """
    這裡先用「容錯」寫法，等你印出 event 結構後我再幫你精準對欄位。
    """
    lat = None
    lon = None
    intensity = None
    origin_time = None

    origin_time = event.get("OriginTime") or event.get("EarthquakeTime") or None

    epi = event.get("Epicenter") or event.get("EarthquakeInfo") or {}
    if isinstance(epi, dict):
        lat = epi.get("EpicenterLatitude") or epi.get("Latitude") or lat
        lon = epi.get("EpicenterLongitude") or epi.get("Longitude") or lon

    geo = event.get("GeoInfo") or {}
    if isinstance(geo, dict):
        lat = geo.get("Latitude") or lat
        lon = geo.get("Longitude") or lon

    intensity = event.get("MaxIntensity") or event.get("Intensity") or event.get("ShakingLevel") or None

    def to_f(x):
        try:
            return float(x)
        except:
            return None

    return to_f(lat), to_f(lon), to_f(intensity), origin_time


def main():
    seg = pd.read_csv(SEGMENTS_CSV, encoding="utf-8-sig")

    # 你 segments 的 midpoint 欄位名稱可能不同，這邊做相容
    if "MidLat" in seg.columns and "MidLon" in seg.columns:
        mid_lat_col, mid_lon_col = "MidLat", "MidLon"
    elif "MidpointLat" in seg.columns and "MidpointLon" in seg.columns:
        mid_lat_col, mid_lon_col = "MidpointLat", "MidpointLon"
    else:
        raise RuntimeError("找不到路段 midpoint 欄位：MidLat/MidLon 或 MidpointLat/MidpointLon")

    payload = fetch_eq(limit=50, offset=0)
    events = extract_events(payload)
    print("✅ 抓到地震事件筆數 =", len(events))

    if len(events) > 0:
        print("=== 第一筆事件 keys ===")
        print(list(events[0].keys()))
        print("=== 第一筆事件（簡略）===")
        print(str(events[0])[:800], "...")  # 太長先截斷

    # 事件整理
    evs = []
    for e in events:
        lat, lon, inten, t = get_epicenter_and_intensity(e)
        if lat is None or lon is None:
            continue
        evs.append({"eq_lat": lat, "eq_lon": lon, "intensity": inten, "origin_time": t})

    print("✅ 可用（有震央座標）的地震筆數 =", len(evs))

    # 掛到每個路段：找最近的地震
    eq_dist = []
    eq_lzone = []
    eq_slevel = []
    eq_time = []
    eq_intensity = []

    for _, row in seg.iterrows():
        lat = float(row[mid_lat_col])
        lon = float(row[mid_lon_col])

        if not evs:
            eq_dist.append(None)
            eq_lzone.append("Regional")
            eq_slevel.append("Normal")
            eq_time.append("")
            eq_intensity.append(None)
            continue

        best = None
        best_d = 1e18
        for e in evs:
            d = haversine_km(lat, lon, e["eq_lat"], e["eq_lon"])
            if d < best_d:
                best_d = d
                best = e

        eq_dist.append(best_d)
        eq_lzone.append(lzone_from_dist_km(best_d))
        eq_slevel.append(slevel_from_intensity(best["intensity"]))
        eq_time.append(best["origin_time"] or "")
        eq_intensity.append(best["intensity"])

    seg["EQ_DistKm"] = eq_dist
    seg["EQ_Lzone"] = eq_lzone
    seg["EQ_Slevel"] = eq_slevel
    seg["EQ_OriginTime"] = eq_time
    seg["EQ_Intensity"] = eq_intensity

    seg.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print("✅ 已輸出：", OUT_CSV)
    print(seg[["EQ_Slevel", "EQ_Lzone", "EQ_DistKm", "EQ_OriginTime", "EQ_Intensity"]].head(10))


if __name__ == "__main__":
    main()