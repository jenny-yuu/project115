import os
import math
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime
import urllib3
import pandas as pd
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =================設定區=================
CREDENTIAL_PATH = "your-firebase-adminsdk.json"
COLLECTION_NAME = "stations"

# 氣象署 API (優先從環境變數讀取，若無則使用預設)
CWA_KEY = os.getenv("CWA_KEY")
if not CWA_KEY:
    CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
    print(f"ℹ️ 未偵測到 CWA_KEY 環境變數，使用預設金鑰。")
else:
    print(f"✅ 已從環境變數載入 CWA_KEY (前四碼: {CWA_KEY[:4]}...)")
RAIN_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
WX_URL   = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
FCST_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"

# 對應表
MAP_RAIN_CSV = "el_segments_to_rain_station.csv"
MAP_WX_CSV   = "el_segments_to_weather_station.csv"
MAP_STATIONS_CSV = "tra_eastern_mainline_EL_stations.csv"

# 地震 API
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"
EQ_URL_SMALL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001"
# ========================================

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def cwa_get_json(url: str):
    headers = {"Authorization": CWA_KEY, "Accept": "application/json"}
    session = requests.Session()
    try:
        r = session.get(url, params={"format": "JSON"}, headers=headers, timeout=60, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ CWA API 請求失敗: {e}")
        return None

def fetch_eq_data():
    all_events = []
    for url, label in [(EQ_URL, "顯著有感"), (EQ_URL_SMALL, "小區域")]:
        data = cwa_get_json(url)
        if not data: continue
        records = data.get("records", {})
        for k, v in records.items():
            if isinstance(v, list):
                all_events.extend(v)
                break
    all_events.sort(key=lambda x: x.get("OriginTime") or x.get("EarthquakeInfo", {}).get("OriginTime") or "", reverse=True)
    return all_events

def parse_intensity(s):
    if not s: return 0
    try:
        for char in str(s):
            if char.isdigit(): return int(char)
    except: pass
    return 0

def extract_eq_info(event):
    try:
        info = event.get("EarthquakeInfo", {})
        epi = info.get("Epicenter", {})
        lat = float(epi.get("EpicenterLatitude") or epi.get("Latitude") or 0)
        lon = float(epi.get("EpicenterLongitude") or epi.get("Longitude") or 0)
        county_intensities = {}
        intensity_data = event.get("Intensity", {})
        shaking_areas = intensity_data.get("ShakingArea", [])
        global_max = 0
        for area in shaking_areas:
            c_name = area.get("CountyName", "")
            if not c_name: continue
            inten_str = area.get("AreaIntensity", "0")
            val = parse_intensity(inten_str)
            county_intensities[c_name] = max(county_intensities.get(c_name, 0), val)
            global_max = max(global_max, val)
        t = event.get("OriginTime") or info.get("OriginTime") or event.get("EarthquakeTime") or ""
        return {"lat": lat, "lon": lon, "max_intensity": global_max, "county_intensities": county_intensities, "time": t}
    except: return None

def init_firebase():
    try:
        # 1. 優先嘗試從環境變數讀取 (適合 GitHub Actions / Render)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            import json
            # 處理可能出現的轉義字元問題
            service_account_info = json.loads(service_account_json, strict=False)
            if "private_key" in service_account_info:
                service_account_info["private_key"] = service_account_info["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase 初始化成功 (從環境變數)！")
        else:
            # 2. 如果沒有環境變數，則從本地檔案讀取
            if os.path.exists(CREDENTIAL_PATH):
                cred = credentials.Certificate(CREDENTIAL_PATH)
                firebase_admin.initialize_app(cred)
                print(f"✅ Firebase 初始化成功 (從檔案: {CREDENTIAL_PATH})！")
            else:
                raise FileNotFoundError(f"找不到金鑰檔案 {CREDENTIAL_PATH} 且未設定環境變數")
        
        return firestore.client()
    except ValueError: 
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {e}")
        exit()

def safe_float(x):
    try:
        if x is None: return 0.0
        s = str(x).strip()
        if s == "" or s.lower() == "nan": return 0.0
        v = float(s)
        return v if v > -90 else 0.0
    except: return 0.0

def fetch_rain_data():
    data = cwa_get_json(RAIN_URL)
    if not data: return pd.DataFrame(columns=["StationId", "RainPast1Hr", "RainPast24Hr"])
    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        rf = s.get("RainfallElement") or {}
        rows.append({
            "StationId": sid,
            "RainPast1Hr": safe_float(((rf.get("Past1hr") or {}).get("Precipitation"))),
            "RainPast24Hr": safe_float(((rf.get("Past24hr") or {}).get("Precipitation")))
        })
    return pd.DataFrame(rows).drop_duplicates(subset=["StationId"])

def fetch_wx_data():
    data = cwa_get_json(WX_URL)
    if not data: return pd.DataFrame(columns=["StationId", "WindSpeed", "PeakGustSpeed", "AirTemperature", "WeatherDesc"])
    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        we = s.get("WeatherElement") or {}
        gust = (we.get("GustInfo") or {}).get("PeakGustSpeed")
        rows.append({
            "StationId": sid,
            "WindSpeed": safe_float(we.get("WindSpeed")),
            "PeakGustSpeed": safe_float(gust),
            "AirTemperature": safe_float(we.get("AirTemperature")),
            "WeatherDesc": str(we.get("Weather") or "多雲").strip()
        })
    return pd.DataFrame(rows).drop_duplicates(subset=["StationId"])

def fetch_forecast_data():
    data = cwa_get_json(FCST_URL)
    if not data: return {}
    locs = data.get("records", {}).get("location", [])
    f_map = {}
    for loc in locs:
        c_name = loc.get("locationName")
        elems = loc.get("weatherElement", [])
        try:
            wx = next(e for e in elems if e["elementName"] == "Wx")["time"][0]["parameter"]["parameterName"]
            pop = next(e for e in elems if e["elementName"] == "PoP")["time"][0]["parameter"]["parameterName"]
            min_t = next(e for e in elems if e["elementName"] == "MinT")["time"][0]["parameter"]["parameterName"]
            max_t = next(e for e in elems if e["elementName"] == "MaxT")["time"][0]["parameter"]["parameterName"]
            f_map[c_name] = {"wx": wx, "pop": int(pop) if pop.isdigit() else 0, "min_t": int(min_t) if min_t.isdigit() else 0, "max_t": int(max_t) if max_t.isdigit() else 0}
        except: continue
    return f_map

def get_county_for_station(station_name):
    s = station_name.replace("台", "臺")
    if any(x in s for x in ["八堵", "暖暖"]): return "基隆市"
    if any(x in s for x in ["四腳亭", "瑞芳", "猴硐", "三貂嶺", "牡丹", "雙溪", "貢寮", "福隆"]): return "新北市"
    if any(x in s for x in ["石城", "大里", "大溪", "龜山", "外澳", "頭城", "頂埔", "礁溪", "四城", "宜蘭", "二結", "中里", "羅東", "冬山", "新馬", "蘇澳新", "蘇澳", "永樂", "東澳", "南澳", "武塔", "漢本"]): return "宜蘭縣"
    if any(x in s for x in ["池上", "海端", "關山", "瑞和", "瑞源", "鹿野", "山里", "臺東", "康樂", "知本"]): return "臺東縣"
    return "花蓮縣"

def update_firebase_weather(db):
    try:
        map_rain = pd.read_csv(MAP_RAIN_CSV)
        map_wx = pd.read_csv(MAP_WX_CSV)
        stations_df = pd.read_csv(MAP_STATIONS_CSV)
    except: return
    
    rain_df, wx_df, forecast_map, eq_events = fetch_rain_data(), fetch_wx_data(), fetch_forecast_data(), fetch_eq_data()
    valid_eqs = [extract_eq_info(e) for e in eq_events if extract_eq_info(e)]

    id_to_name = {str(row["StationID"]): str(row["StationName"]) for _, row in stations_df.iterrows()}
    id_to_coords = {str(row["StationID"]): (float(row["Lat"]), float(row["Lon"])) for _, row in stations_df.iterrows()}
    
    station_weather = {}
    for _, row in map_rain.iterrows():
        for sid in [str(row["FromStationID"]), str(row["ToStationID"])]:
            r_id = str(row["Nearest_RAIN_StationId"])
            m = rain_df[rain_df["StationId"] == r_id]
            if not m.empty:
                if sid not in station_weather: station_weather[sid] = {}
                station_weather[sid].update({"Rain1h": float(m.iloc[0]["RainPast1Hr"]), "Rain24h": float(m.iloc[0]["RainPast24Hr"])})

    for _, row in map_wx.iterrows():
        for sid in [str(row["FromStationID"]), str(row["ToStationID"])]:
            w_id = str(row["Nearest_WEATHER_StationId"])
            m = wx_df[wx_df["StationId"] == w_id]
            if not m.empty:
                if sid not in station_weather: station_weather[sid] = {}
                station_weather[sid].update({"Wind": float(m.iloc[0]["WindSpeed"]), "Temp": float(m.iloc[0]["AirTemperature"]), "Desc": str(m.iloc[0]["WeatherDesc"])})

    batch = db.batch()
    now_str = datetime.datetime.now().isoformat()
    count = 0
    for sid, info in station_weather.items():
        doc = db.collection(COLLECTION_NAME).document(sid)
        r1h = info.get("Rain1h", 0)
        risk = "Normal"
        light = "正常"
        if r1h >= 80: risk, light = "Critical", "紅燈"
        elif r1h >= 30: risk, light = "Alert", "黃燈"
        
        county = get_county_for_station(id_to_name.get(sid, ""))
        fcst = forecast_map.get(county, {"wx": "多雲", "pop": 0, "min_t": 20, "max_t": 25})
        
        best_eq = {"intensity": 0, "origin_time": "", "dist_km": 999}
        s_pos = id_to_coords.get(sid)
        if valid_eqs and s_pos:
            min_d = 1e18
            for eq in valid_eqs:
                try:
                    diff = (datetime.datetime.now() - datetime.datetime.strptime(eq["time"], "%Y-%m-%d %H:%M:%S")).total_seconds()
                    if diff > 7200: continue
                    d = haversine_km(s_pos[0], s_pos[1], eq["lat"], eq["lon"])
                    if d < min_d:
                        min_d = d
                        best_eq = {"intensity": eq["county_intensities"].get(county, 0) or (eq["max_intensity"] if d < 50 else 0), "origin_time": eq["time"], "dist_km": round(d, 1)}
                except: continue
        
        if best_eq["intensity"] >= 4: risk, light = ("Critical", "紅燈") if best_eq["intensity"] >= 5 else ("Alert", "黃燈")
        
        # ⚡ 教授建議修正：宜人文字避開太陽，重點在降雨與溫度
        # 根據溫度產生體感描述 (更自然的詞彙)
        temp = info.get("Temp", 0)
        if temp >= 33: temp_feel = "酷熱"
        elif temp >= 28: temp_feel = "悶熱"
        elif temp >= 22: temp_feel = "舒適"
        elif temp >= 17: temp_feel = "微涼"
        elif temp >= 10: temp_feel = "寒冷"
        else: temp_feel = "極寒"

        desc = info.get("Desc", "多雲").replace("正常", "舒適")
        payload = {
            "has_issue": light != "正常",
            "health_light": light,
            "weather": {
                "rain_1hr": r1h, "rain_24hr": info.get("Rain24h", 0),
                "wind_speed": info.get("Wind", 0), 
                "wind_desc": "微風" if info.get("Wind", 0) < 5 else f"{info.get('Wind', 0)}m/s",
                "temperature": temp, 
                "temp_feel": temp_feel, # 新增供前端顯示：暖和/冷
                "description": desc, "updated_at": now_str, "risk_level": risk
            },
            "forecast": fcst, "earthquake": best_eq
        }
        batch.update(doc, payload)
        count += 1
        if count % 20 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    print(f"🎉 Updated {count} stations.")

if __name__ == "__main__":
    update_firebase_weather(init_firebase())
