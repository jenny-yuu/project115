import os
import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime
import urllib3
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =================設定區=================
CREDENTIAL_PATH = "your-firebase-adminsdk.json"
COLLECTION_NAME = "stations"

# 氣象署 API
CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
RAIN_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
WX_URL   = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0003-001"
FCST_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"

# 對應表（需要知道哪個車站對應哪個最近的氣象站）
MAP_RAIN_CSV = "el_segments_to_rain_station.csv"
MAP_WX_CSV   = "el_segments_to_weather_station.csv"
# ========================================

def init_firebase():
    try:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
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
        if v <= -90: return 0.0 # 排除缺測代碼
        return v
    except Exception:
        return 0.0

def cwa_get_json(url: str):
    params = {"Authorization": CWA_KEY, "format": "JSON"}
    r = requests.get(url, params=params, timeout=30, verify=False)
    r.raise_for_status()
    return r.json()

def fetch_rain_data():
    """抓取全台即時雨量並轉為 DataFrame"""
    print("下載即時雨量...")
    data = cwa_get_json(RAIN_URL)
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
    """抓取全台天氣觀測實測 (風速、溫度等)"""
    print("下載即時綜觀氣象...")
    data = cwa_get_json(WX_URL)
    stations = data.get("records", {}).get("Station", [])
    rows = []
    for s in stations:
        sid = s.get("StationId")
        we = s.get("WeatherElement") or {}
        gust = (we.get("GustInfo") or {}).get("PeakGustSpeed")
        weather_str = str(we.get("Weather") or "多雲").strip()
        # 清除奇怪的代碼(如 -99)
        if weather_str == "-99" or weather_str == "": weather_str = "多雲"
        
        rows.append({
            "StationId": sid,
            "WindSpeed": safe_float(we.get("WindSpeed")),
            "PeakGustSpeed": safe_float(gust),
            "AirTemperature": safe_float(we.get("AirTemperature")),
            "WeatherDesc": weather_str
        })
    return pd.DataFrame(rows).drop_duplicates(subset=["StationId"])

def fetch_forecast_data():
    """抓取全台三十六小時天氣預報 (縣市層級)"""
    print("下載三十六小時預報...")
    data = cwa_get_json(FCST_URL)
    locs = data.get("records", {}).get("location", [])
    forecast_map = {}
    for loc in locs:
        c_name = loc.get("locationName")
        elems = loc.get("weatherElement", [])
        try:
            wx = next(e for e in elems if e["elementName"] == "Wx")["time"][0]["parameter"]["parameterName"]
            pop_str = next(e for e in elems if e["elementName"] == "PoP")["time"][0]["parameter"]["parameterName"]
            min_t_str = next(e for e in elems if e["elementName"] == "MinT")["time"][0]["parameter"]["parameterName"]
            max_t_str = next(e for e in elems if e["elementName"] == "MaxT")["time"][0]["parameter"]["parameterName"]
            
            forecast_map[c_name] = {
                "wx": wx,
                "pop": int(pop_str) if pop_str.isdigit() else 0,
                "min_t": int(min_t_str) if min_t_str.isdigit() else 0,
                "max_t": int(max_t_str) if max_t_str.isdigit() else 0
            }
        except StopIteration:
            continue
    return forecast_map

def get_county_for_station(station_name):
    s = station_name.replace("台", "臺")
    if s in ["八堵", "暖暖"]: return "基隆市"
    if s in ["四腳亭", "瑞芳", "猴硐", "三貂嶺", "牡丹", "雙溪", "貢寮", "福隆"]: return "新北市"
    if s in ["石城", "大里", "大溪", "龜山", "外澳", "頭城", "頂埔", "礁溪", "四城", "宜蘭", "二結", "中里", "羅東", "冬山", "新馬", "蘇澳新", "蘇澳", "永樂", "東澳", "南澳", "武塔", "漢本"]: return "宜蘭縣"
    if s in ["和平", "和仁", "崇德", "新城", "景美", "北埔", "花蓮", "吉安", "志學", "平和", "壽豐", "豐田", "林榮新光", "南平", "鳳林", "萬榮", "光復", "大富", "富源", "瑞穗", "三民", "玉里", "東里", "東竹", "富里"]: return "花蓮縣"
    if s in ["池上", "海端", "關山", "瑞和", "瑞源", "鹿野", "山里", "臺東", "康樂", "知本"]: return "臺東縣"
    return "花蓮縣"

def update_firebase_weather(db):
    print("開始整理車站與氣象的對應關係...")
    
    # 讀取本機已經算好的 KNN 對應表 (台鐵站 <-> 最近氣象站)
    try:
        map_rain = pd.read_csv(MAP_RAIN_CSV)
        map_wx = pd.read_csv(MAP_WX_CSV)
    except FileNotFoundError:
        print("❌ 找不到氣象對應表 CSV 檔案，請確保有 el_segments_to_rain_station.csv 與 el_segments_to_weather_station.csv")
        return

    # 取得最新氣象資料
    rain_df = fetch_rain_data()
    wx_df = fetch_wx_data()
    forecast_map = fetch_forecast_data()

    # 以台鐵 ToStationID (或 FromStationID，這裡我們先更新所有被標記過的站) 為準，整理每個台鐵站最新對應到的天氣數值
    station_weather = {}
    
    # 建立輔助對應表 ID -> StationName，讓我們知道這個 ID 叫什麼站
    id_to_name = {}
    for _, row in map_rain.iterrows():
        id_to_name[str(row.get("FromStationID", ""))] = str(row.get("FromStationName", ""))
        id_to_name[str(row.get("ToStationID", ""))] = str(row.get("ToStationName", ""))
    
    # 處理雨量
    for _, row in map_rain.iterrows():
        # 因為對應表是 "路段"，所以起始站和終點站都會受該路段的氣象站影響，我們兩邊都更新
        for sid in [str(row.get("FromStationID", "")), str(row.get("ToStationID", ""))]:
            if not sid: continue
            nearest_rain_id = str(row.get("Nearest_RAIN_StationId", ""))
            
            # 從最新雨量 DataFrame 找數值
            rain_match = rain_df[rain_df["StationId"] == nearest_rain_id]
            if not rain_match.empty:
                if sid not in station_weather: station_weather[sid] = {}
                station_weather[sid]["RainPast1Hr"] = float(rain_match.iloc[0]["RainPast1Hr"])
                station_weather[sid]["RainPast24Hr"] = float(rain_match.iloc[0]["RainPast24Hr"])

    # 處理風速/溫度
    for _, row in map_wx.iterrows():
        for sid in [str(row.get("FromStationID", "")), str(row.get("ToStationID", ""))]:
            if not sid: continue
            nearest_wx_id = str(row.get("Nearest_WEATHER_StationId", ""))
            
            wx_match = wx_df[wx_df["StationId"] == nearest_wx_id]
            if not wx_match.empty:
                if sid not in station_weather: station_weather[sid] = {}
                station_weather[sid]["WindSpeed"] = float(wx_match.iloc[0]["WindSpeed"])
                station_weather[sid]["PeakGustSpeed"] = float(wx_match.iloc[0]["PeakGustSpeed"])
                station_weather[sid]["AirTemperature"] = float(wx_match.iloc[0]["AirTemperature"])
                # 如果過去一小時有雨，強制加上標示
                w_desc = str(wx_match.iloc[0]["WeatherDesc"])
                if station_weather[sid].get("RainPast1Hr", 0) > 0.0 and "雨" not in w_desc:
                    w_desc += " (降雨中)"
                station_weather[sid]["WeatherDesc"] = w_desc

    print(f"👉 共有 {len(station_weather)} 個台鐵車站找到對應的天氣更新。開始寫入 Firebase...")
    
    # 開始批次更新 Firebase
    batch = db.batch()
    stations_ref = db.collection(COLLECTION_NAME)
    current_time = datetime.datetime.now().isoformat()
    update_count = 0
    
    for sid, info in station_weather.items():
        doc_ref = stations_ref.document(sid)
        
        # 簡單的風險判斷規則 (依據您的企劃書 表三 語義強度等級)
        # 例如：時雨量 > 30mm 為 Alert (中度影響)，> 80mm 為 Critical (高影響)
        rain_1hr = info.get("RainPast1Hr", 0)
        risk_level = "Normal"
        health_light_overwrite = None
        
        if rain_1hr >= 80:
            risk_level = "Critical"
            health_light_overwrite = "紅燈" # 停駛/高風險
        elif rain_1hr >= 30:
            risk_level = "Alert"
            if health_light_overwrite != "紅燈":
                health_light_overwrite = "黃燈" # 延誤/中風險
                
        # 新增 Forecast 縣市級距預報
        s_name = id_to_name.get(sid, "")
        county = get_county_for_station(s_name)
        fcst = forecast_map.get(county, {"wx": "多雲", "pop": 0, "min_t": 20, "max_t": 25})

        # 更新 Payload
        update_data = {
            "weather": {
                "rain_1hr": rain_1hr,
                "rain_24hr": info.get("RainPast24Hr", 0),
                "wind_speed": info.get("WindSpeed", 0),
                "peak_gust_speed": info.get("PeakGustSpeed", 0),
                "temperature": info.get("AirTemperature", 0),
                "description": info.get("WeatherDesc", "多雲"),
                "updated_at": current_time,
                "risk_level": risk_level
            },
            "forecast": fcst
        }
        
        # 如果天氣達到警報等級，我們覆蓋原本的 health_light (因為天氣爛一定會影響車站健康度)
        if health_light_overwrite:
            update_data["health_light"] = health_light_overwrite

        batch.update(doc_ref, update_data)
        update_count += 1
        
        if update_count % 20 == 0:
            batch.commit()
            batch = db.batch() # 重新開一個 batch
            
    # commit 剩下的
    batch.commit()
    print(f"🎉 成功更新了 {update_count} 個車站的最新天氣狀態到 Firebase！")

if __name__ == "__main__":
    db = init_firebase()
    update_firebase_weather(db)
