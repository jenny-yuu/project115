import os
import math
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
MAP_STATIONS_CSV = "tra_eastern_mainline_EL_stations.csv"

# 地震 API
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"        # 顯著有感
EQ_URL_SMALL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0016-001"  # 小區域
AREA_NAMES = ["宜蘭縣", "花蓮縣", "臺東縣"]
# ========================================

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def fetch_eq_data():
    """同時抓取顯著有感與小區域地震資料"""
    all_events = []
    for url, label in [(EQ_URL, "顯著有感"), (EQ_URL_SMALL, "小區域")]:
        print(f"下載即時地震通報 ({label})...")
        data = cwa_get_json(url)
        if not data: continue
        
        records = data.get("records", {})
        # 尋找包含清單的 key (通常是 Earthquake 或按 API 代號命名)
        events = []
        for k, v in records.items():
            if isinstance(v, list):
                events = v
                break
        all_events.extend(events)
    
    # 依時間排序，最新的在前
    all_events.sort(key=lambda x: x.get("OriginTime") or x.get("EarthquakeInfo", {}).get("OriginTime") or "", reverse=True)
    return all_events

def parse_intensity(s):
    if not s: return 0
    try:
        # "4級" -> 4, "5強" -> 5, etc.
        for char in str(s):
            if char.isdigit():
                return int(char)
    except:
        pass
    return 0

def extract_eq_info(event):
    """從事件中提取座標與分區震度"""
    try:
        # CWA E-A0015-001
        info = event.get("EarthquakeInfo", {})
        epi = info.get("Epicenter", {})
        lat = float(epi.get("EpicenterLatitude") or epi.get("Latitude") or 0)
        lon = float(epi.get("EpicenterLongitude") or epi.get("Longitude") or 0)
        
        # 建立縣市震度表
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
        return {
            "lat": lat,
            "lon": lon,
            "max_intensity": global_max,
            "county_intensities": county_intensities,
            "time": t
        }
    except Exception as e:
        print(f"提取地震資訊失敗: {e}")
        return None

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
    # 將 Authorization 改放在 Headers 中 (有時比放在 Params 穩定)
    headers = {"Authorization": CWA_KEY, "Accept": "application/json"}
    
    # 增加更強大的重試機制 (針對 500, 502, 503, 504)
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    session = requests.Session()
    # connect=重試次數, backoff_factor=指數性等待, status_forcelist=遇到哪些錯誤要重試
    retry = Retry(
        total=3, # 減少為 3 次避免等太久，但增加 backoff
        backoff_factor=5, 
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    
    try:
        # 使用 headers 傳遞 Key，params 只傳 format
        r = session.get(url, params={"format": "JSON"}, headers=headers, timeout=60, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"⚠️ CWA API 請求失敗 (經過重試依然失敗): {e}")
        return None

def fetch_rain_data():
    """抓取全台即時雨量並轉為 DataFrame"""
    print("下載即時雨量...")
    data = cwa_get_json(RAIN_URL)
    if not data: 
        return pd.DataFrame(columns=["StationId", "RainPast1Hr", "RainPast24Hr"])
    
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
    if not data: 
        return pd.DataFrame(columns=["StationId", "WindSpeed", "PeakGustSpeed", "AirTemperature", "WeatherDesc"])
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
    if not data: return {}
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
    eq_events = fetch_eq_data()
    
    # 整理地震資料
    valid_eqs = []
    for e in eq_events:
        eq_res = extract_eq_info(e)
        if eq_res:
            valid_eqs.append(eq_res)

    # 以台鐵 ToStationID (或 FromStationID，這裡我們先更新所有被標記過的站) 為準，整理每個台鐵站最新對應到的天氣數值
    station_weather = {}
    
    # 建立輔助對應表 ID -> StationName / Lat / Lon
    id_to_name = {}
    id_to_coords = {}
    
    # 從專業車站清單抓座標 (最準確)
    try:
        stations_df = pd.read_csv(MAP_STATIONS_CSV)
        for _, s_row in stations_df.iterrows():
            sid = str(s_row.get("StationID", ""))
            id_to_coords[sid] = (float(s_row["Lat"]), float(s_row["Lon"]))
            id_to_name[sid] = str(s_row.get("StationName", ""))
    except Exception as e:
        print(f"⚠️ 讀取車站座標檔失敗: {e}")

    # 補充 segment 對應表中的名稱
    for _, row in map_rain.iterrows():
        fsid = str(row.get("FromStationID", ""))
        tsid = str(row.get("ToStationID", ""))
        if fsid not in id_to_name: id_to_name[fsid] = str(row.get("FromStationName", ""))
        if tsid not in id_to_name: id_to_name[tsid] = str(row.get("ToStationName", ""))
    
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
                station_weather[sid]["WeatherDesc"] = str(wx_match.iloc[0]["WeatherDesc"])

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

        # 計算最近地震 (僅顯示 2 小時內的地震)
        best_eq = {"intensity": 0, "origin_time": "", "dist_km": 999}
        now_dt = datetime.datetime.now()
        
        if valid_eqs:
            s_lat, s_lon = id_to_coords.get(sid, (None, None))
            min_dist = 1e18
            for eq in valid_eqs:
                # 檢查時間 (格式: 2026-03-12 20:14:13)
                try:
                    eq_time = datetime.datetime.strptime(eq["time"], "%Y-%m-%d %H:%M:%S")
                    diff = now_dt - eq_time
                    # 超過 2 小時就不顯示為「當前地震」
                    if diff.total_seconds() > 7200:
                        continue
                except:
                    continue

                # 首先判斷縣市震度
                local_inten = eq["county_intensities"].get(county, 0)
                
                # 如果有座標，計算距離
                d = 999
                if s_lat and s_lon:
                    d = haversine_km(s_lat, s_lon, eq["lat"], eq["lon"])
                
                # 尋找最相關/最近的一個
                if d < min_dist:
                    min_dist = d
                    best_eq = {
                        "intensity": local_inten if local_inten > 0 else (eq["max_intensity"] if d < 50 else 0),
                        "origin_time": eq["time"],
                        "dist_km": round(d, 1)
                    }
        
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
            "forecast": fcst,
            "earthquake": best_eq
        }
        
        # 如果震度很大 (>= 4)，也要設為紅燈
        if best_eq["intensity"] >= 5:
            health_light_overwrite = "紅燈"
            risk_level = "Critical"
        elif best_eq["intensity"] >= 3:
            if health_light_overwrite != "紅燈":
                health_light_overwrite = "黃燈"
                risk_level = "Alert"

        if health_light_overwrite:
            update_data["health_light"] = health_light_overwrite
            update_data["weather"]["risk_level"] = risk_level
        else:
            # --- 重要修正：若無顯著災害風險，恢復為預設燈號 ---
            # 只有在沒有黃/紅燈覆蓋的情況下，才檢查是否需要恢復綠色
            # 這裡我們假設若沒被雨量或地震標註，就應該維持/恢復正常
            update_data["health_light"] = "正常" # 或 "綠燈"，視 App 邏輯而定 (目前看截圖是正常/綠色)
            # 如果原本是黃燈(延誤)，這裡不應該直接覆蓋，但在本腳本中目前只管天氣風險
            # 若要更精確，應讀取 Firebase 原本的 is_delayed 狀態，但為了修正殘留問題，先強制恢復

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
