# [v21-FINAL-STABLE-DEPLOYED] - TRA AI Travel Assistant Backend
import os
import json
import openai
import requests
import traceback
import math
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pinecone import Pinecone
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import re
import firebase_admin
from firebase_admin import credentials, firestore

# 取得當前腳本所在的目錄
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
print(f"--- [STARTUP] BASE_DIR: {BASE_DIR} ---")
print(f"--- [STARTUP] Files in directory: {os.listdir(BASE_DIR)} ---")

# 載入環境變數 (本地端使用 .env，雲端由 Render 提供)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 驗證關鍵變數
openai_key = os.getenv("OPENAI_API_KEY")
pinecone_key = os.getenv("PINECONE_API_KEY")
print(f"   OpenAI Key 載入狀態: {'已載入' if openai_key else '未載入'}")
print(f"   Pinecone Key 載入狀態: {'已載入' if pinecone_key else '未載入'}")

app = Flask(__name__)
# 允許跨網域請求 (重要：讓 Android 手機連線)
CORS(app, resources={r"/*": {"origins": "*"}})

# 初始化 API 客戶端
client = None
pinecone_index = None
try:
    client = openai.OpenAI(api_key=openai_key)
    pc = Pinecone(api_key=pinecone_key)
    pinecone_index = pc.Index("disaster-rag")
    print(" OpenAI 與 Pinecone 初始化成功")
except Exception as init_e:
    print(f" API 客戶端初始化失敗: {init_e}")

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# 初始化 Firebase
try:
    if not firebase_admin._apps:
        # 優先從環境變數載入 (適合 Render/生產環境，保護金鑰不外流)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if service_account_json:
            try:
                # 預處理 1：移除所有不可見控制字元 (如 \r 之類)
                import re
                service_account_json = service_account_json.replace("\r", "").strip()
                
                # 預處理 2：確保 private_key 內部的 \n 是正確轉義的
                # 如果使用者直接貼上了換行，或者雙重轉義了 \\n，我們要將其標準化
                if "\\\\n" in service_account_json:
                    service_account_json = service_account_json.replace("\\\\n", "\\n")
                
                service_account_info = json.loads(service_account_json, strict=False)
                
                # 預處理 3：Firebase 私鑰通常需要真正的換行符
                if "private_key" in service_account_info:
                    pk = service_account_info["private_key"]
                    if "\\n" in pk:
                        service_account_info["private_key"] = pk.replace("\\n", "\n")
                
                cred = credentials.Certificate(service_account_info)
                firebase_admin.initialize_app(cred)
                print(" Firebase 初始化成功 (從環境變數 [v24])")
            except Exception as e_json:
                print(f" 環境變數 Firebase JSON 解析失敗: {e_json}")
        else:
            # 本地端尋找檔案
            found = False
            for f in ["serviceAccount.json", "your-firebase-adminsdk.json", "firebase_key.json"]:
                cred_path = os.path.join(BASE_DIR, f)
                if os.path.exists(cred_path):
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                    print(f" Firebase 初始化成功 (自檔案: {f} [v22])")
                    found = True
                    break
            if not found:
                print(" 找不到 Firebase 金鑰檔案，且未設定環境變數 FIREBASE_SERVICE_ACCOUNT_JSON")

    db = firestore.client()
    print(" Firestore Client 已啟動")
except Exception as firebase_e:
    print(f" Firebase 初始化出現異常: {firebase_e}")
    db = None

# 配置相對路徑
PATHS = {
    "PROJECT_DIR": BASE_DIR,
    "MAPPING_FILE": os.path.join(BASE_DIR, "fb_stations.json")
}

#  基礎資料載入 (里程與車資) 
STATION_DISTANCES = {}
try:
    csv_path = os.path.join(BASE_DIR, "backend_scripts", "tra_eastern_mainline_EL_stations.csv")
    if os.path.exists(csv_path):
        import csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                STATION_DISTANCES[row['StationName']] = float(row['TraveledDistance'])
        print(f" 已載入 {len(STATION_DISTANCES)} 筆車站里程資料")
except Exception as e:
    print(f" 里程資料載入失敗: {e}")

def get_taxi_fare_str(station_name: str) -> str:
    """估算到鄰近車站與主要轉運站的計程車資"""
    if not station_name: return ""
    
    # 支援模糊匹配（處理 瑞芳 vs 瑞芳車站）
    clean_name = station_name.replace("車站", "").replace("臺", "台")
    target_key = next((k for k in STATION_DISTANCES.keys() if clean_name in k.replace("臺", "台")), None)
    
    if not target_key:
        print(f" 計程車資估算跳過：找不到車站 '{station_name}'")
        return ""
    
    names = list(STATION_DISTANCES.keys())
    idx = names.index(target_key)
    notes = []
    
    # 1. 鄰近車站 (前後站)
    targets = []
    if idx > 0: targets.append(names[idx-1])
    if idx < len(names) - 1: targets.append(names[idx+1])
    
    # 2. 主要轉運站 (Hubs)
    HUBS = ["八堵", "瑞芳", "宜蘭", "羅東", "花蓮", "玉里", "臺東"]
    for hub in HUBS:
        if hub in STATION_DISTANCES and hub != target_key and hub not in targets:
            # 只有在 30km 以內的轉運站才列入建議
            if abs(STATION_DISTANCES[hub] - STATION_DISTANCES[target_key]) <= 30:
                targets.append(hub)
    
    import math
    for t in targets:
        dist = abs(STATION_DISTANCES[t] - STATION_DISTANCES[target_key])
        # 費率：1.25km(85元) + 每200m(5元)
        fare = 85 + (math.ceil((dist - 1.25) / 0.2) * 5 if dist > 1.25 else 0)
        notes.append(f"至 {t} 約 {dist:.1f}km / 估計車資 {int(fare)} 元")
    
    print(f" 生成計程車資估算 ({target_key}): {len(notes)} 筆建議")
    return "\n".join(notes) if notes else ""

#  工具函數 

def get_station_id(station_name: str) -> str:
    """從 fb_stations.json 或 tdx_names 尋找車站 ID"""
    try:
        mapping_path = PATHS["MAPPING_FILE"]
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for s in data:
                    if station_name in s.get("Name", ""):
                        return str(s.get("ID"))
    except: pass
    return None

def get_embedding(text):
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding


def get_tdx_token():
    """取得 TDX OAuth access token"""
    try:
        url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": TDX_CLIENT_ID,
            "client_secret": TDX_CLIENT_SECRET,
        }
        r = requests.post(url, data=data, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as e:
        print(f" TDX 取得 token 失敗: {e}")
        return None



def get_nearby_bus_schedules(station_name: str, token: str) -> list:
    """[優化版] 二階段空間查詢"""
    if not token: return []
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url_sta = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/Station?$format=JSON"
        r_sta = requests.get(url_sta, headers=headers, timeout=10)
        stations = r_sta.json().get('Stations', [])
        # 終極過濾：精確比對名稱，如果是東里，強行鎖定 ID 6100 (花蓮)
        sta = next((s for s in stations if s['StationName']['Zh_tw'] == station_name or s['StationName']['Zh_tw'] == f"{station_name}車站"), None)
        if station_name == "東里":
            sta = next((s for s in stations if s['StationID'] == "6100"), sta)
        if not sta: return []
        lon, lat = sta['StationPosition']['PositionLon'], sta['StationPosition']['PositionLat']
        
        if any(x in station_name for x in ["台北", "板橋", "瑞芳", "猴硐", "三貂嶺"]): city = "NewTaipei"
        elif "基隆" in station_name: city = "Keelung"
        elif "台東" in station_name or any(x in station_name for x in ["關山", "池上", "鹿野", "太麻里"]): city = "TaitungCounty"
        else: city = "HualienCounty"

        spatial = f"nearby({lat},{lon},1000)"
        url_nearby = f"https://tdx.transportdata.tw/api/basic/v2/Bus/Station/City/{city}?$spatialFilter={spatial}&$format=JSON"
        r_nearby = requests.get(url_nearby, headers=headers, timeout=10)
        if r_nearby.status_code != 200: return []
        
        nearby_data = r_nearby.json()
        if not nearby_data: return []
        stop_names = list(set([s['StationName']['Zh_tw'] for s in nearby_data]))[:5]
        
        results = []
        filter_str = " or ".join([f"StopName/Zh_tw eq '{name}'" for name in stop_names])
        urls = [
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{city}?$filter={filter_str}&$format=JSON",
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/InterCity?$filter={filter_str}&$format=JSON"
        ]
        
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    for b in r.json():
                        eta = b.get('EstimateTime')
                        if eta is not None:
                            results.append({
                                "route": b.get('RouteName', {}).get('Zh_tw'),
                                "destination": "附近站牌", 
                                "departure": f"{eta//60} 分鐘" if eta > 0 else "即將到站",
                                "company": b.get('StopName', {}).get('Zh_tw')
                            })
            except: pass
        return sorted(results, key=lambda x: x['departure'])[:5]
    except Exception as e:
        print(f"TDX 查詢失敗: {e}")
        return []

def get_official_transfers(station_name: str, token: str) -> dict:
    if not station_name: return {}
    sid = get_station_id(station_name)
    if db:
        try:
            if sid:
                doc = db.collection("scraped_transfers").document(sid).get()
                if doc.exists: return doc.to_dict().get("transfers", {})
        except: pass
    try:
        scraped_path = os.path.join(PATHS["PROJECT_DIR"], "scraped_transfers.json")
        if os.path.exists(scraped_path):
            with open(scraped_path, 'r', encoding='utf-8') as f:
                data = json.load(f).get(sid if sid else "", {}).get("transfers", {})
                if data: return data
    except: pass
    return {}

def format_transfer_text(data: dict, fare_note: str = "") -> str:
    if not data: return "(查無官方轉乘資料)"
    mapping = {"taxi": "計程車", "bus": "客運", "rail": "火車", "bike": "YouBike"}
    lines = []
    for k, v in mapping.items():
        if data.get(k):
            lines.append(f"[{v}]\n" + "\n".join([f"- {i}" for i in data[k]]))
    return "\n\n".join(lines)

@app.route('/', methods=['GET'])
def index():
    return "台鐵智慧行程助理後端 [v4.0-Two-Stage-Final] - 系統已優化二階段查詢與計程車資功能"

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        if not data: return jsonify({"structured": {"summary": "請求無效"}}, 400)
        
        query = data.get('query', '')
        delay_time = data.get('delay_time', 0)
        is_suspended = data.get('is_suspended', False)
        station_name = data.get('station_name', '')
        
        print(f"接收新請求: {station_name}", flush=True)
        fare_note = get_taxi_fare_str(station_name)
        
        # 1. RAG
        query_vector = get_embedding(query)
        search_results = {'matches': []}
        if pinecone_index:
            search_results = pinecone_index.query(vector=query_vector, top_k=3, include_metadata=True)
            
        context_texts = []
        for match in search_results['matches']:
            meta = match['metadata']
            context_texts.append(f"- {meta.get('situation')}\n  建議: {meta.get('solution')}")
        
        context_block = "\n\n".join(context_texts)
        
        # 2. TDX & Transfers
        tdx_token = get_tdx_token()
        bus_text = ""
        official_transfer_data = {}
        official_transfer_text = ""
        
        if station_name and tdx_token:
            bus_schedules = get_nearby_bus_schedules(station_name, tdx_token)
            if bus_schedules:
                bus_text = "\n".join([f"- {b['route']}: {b['departure']}" for b in bus_schedules])
            official_transfer_data = get_official_transfers(station_name, tdx_token)
            official_transfer_text = format_transfer_text(official_transfer_data, fare_note)

        # 3. GPT
        prompt = f"情境:{query}\n延誤:{delay_time}\n歷史:{context_block}\n公車:{bus_text}\n轉乘:{official_transfer_text}\n格式:JSON(summary, ai_advice, routes, emergency, nav_dest)"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=500
        )
        structured_data = json.loads(response.choices[0].message.content)
        
        # 後端強制注入 (計程車)
        if "routes" in structured_data:
            if not any("計程車" in str(r.get("title")) for r in structured_data["routes"]):
                structured_data["routes"].insert(0, {"type": "other", "title": "計程車", "departure": "站前", "duration": fare_note.split("\n")[0] if fare_note else "現場叫車", "priority": "建議"})

        return jsonify({"structured": structured_data, "is_serious": is_suspended})
    except Exception as e:
        print(f"錯誤: {e}", flush=True)
        return jsonify({"structured": {"summary": "服務異常"}}, 200)

        # 3. 呼叫 GPT
        # 判定是否為地震急件
        is_earthquake = "地震" in query or (sim_type == "地震" and sim_intensity >= 3)
        
        if is_suspended:
            situation_desc = f"模擬災害：{sim_type} (強度: {sim_intensity})" if sim_type else "列車停駛（紅燈警示）"
            advice_focus = f"目前的狀況是 {situation_desc}。重點推薦替代交通工具（客運或計程車），並參照官方轉乘資訊。"
        else:
            if delay_time > 0:
                situation_desc = f"列車延誤 {delay_time} 分鐘"
                advice_focus = f"目前有 {delay_time} 分鐘延誤，請依據底下官方轉乘資訊提供轉乘建議。"
            else:
                situation_desc = "目前正常行駛"
                advice_focus = "目前營運正常，請直接給予簡短正面建議即可。"
            
            if is_earthquake:
                advice_focus += " 注意：因有地震紀錄，請務必包含必要的地震避難指引與安全提醒。"
            else:
                advice_focus += " 注意：目前並無地震災害，請「絕對不要」提到任何避難、找堅固物體躲避等無關建議。"
        prompt = f"""
你現在是「台鐵智慧行程助理」。目前的狀況是：「{query}」。
{advice_focus}
15字總結請反映目前的真實狀態（如：{situation_desc}）。
即使有 RAG 歷史案例，若目前並無地震，也請不要提到避難。

【參考歷史資料（RAG）】：
{context_block}

【目前可搭乘的客運即時班次】：
{bus_text if bus_text else "無具體班次時間"}

【TDX 台鐵官方轉乘資訊】：
{official_transfer_text if official_transfer_text else "無官方轉乘資料"}

【網路即時搜尋替代路線建議】：
{search_text if search_text else "無"}

【輸出格式要求】：
請「務必」以 JSON 格式回答，且必須極度簡潔（不要廢話、不要『親愛的乘客』或道歉字眼），包含以下欄位：
1. "summary": 15字以內的簡短狀況總結。
2. "ai_advice": 直接給予安全提醒或建議（60字以內），禁止包含冗贅問候語，若有地震請包含避難指引。
3. "routes": 列表，包含 3~5 個建議項目（type: train/bus/other, title, departure, duration, priority: 急件/建議）。
4. "emergency": 嚴重警示文字，僅在地震或天災嚴重時填寫。
5. "nav_dest": 建議導航的目的地關鍵字（必須包含「台灣」與「縣市」，且優先使用官方標註的地址）。
6. **嚴禁推薦任何外部「App」或「下載」建議 (如 Moovit, Google Maps, 下一班火車等)**。
7. 將建議按優先級（建議/急件）分組。
"""

        print("4. 呼叫 GPT-4o-mini...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=800,
            temperature=0.3,
            timeout=25
        )
        raw_json = response.choices[0].message.content
        structured_data = json.loads(raw_json)
            
        if not is_suspended:
            # 即使沒停駛，如果有強震也強行加入 emergency 警告
            if sim_intensity >= 4 or "震度 4" in query or "震度 5" in query:
                if not structured_data.get("emergency"):
                    structured_data["emergency"] = "強震警報：請注意掉落物並配合站務人員視導軌道。"
            else:
                structured_data["emergency"] = ""
        # --- 後端強制注入機制 ---
        # 2. 多重轉乘模式注入與去重
        if "routes" in structured_data:
            existing_routes = structured_data["routes"]
            
            # --- 模式注入 (Bike, Bus, Rail) ---
            mapping_info = {
                "bike": ("公共自行車 (YouBike)", "車站週邊", "現場租借"),
                "bus": ("公路運輸 (公車/客運)", "站前轉運站", "依現場班次"),
                "rail": ("鐵路運輸 (火車)", "車站月台", "依車站公告")
            }
            
            for key, (title, depart, dur) in mapping_info.items():
                # 判定 AI 是否已經提過此類
                is_mentioned = False
                for r in existing_routes:
                    r_title = str(r.get("title", "")).lower()
                    r_type = str(r.get("type", "")).lower()
                    if key == "bike" and ("bike" in r_type or "自行車" in r_title): is_mentioned = True
                    if key == "bus" and ("bus" in r_type or "公車" in r_title or "客運" in r_title): is_mentioned = True
                    if key == "rail" and ("rail" in r_type or "火車" in r_title or "台鐵" in r_title): is_mentioned = True
                
                if not is_mentioned and official_transfer_data.get(key):
                    existing_routes.append({
                        "type": "other",
                        "title": title,
                        "departure": f"{station_name}{depart}",
                        "duration": dur,
                        "priority": "建議"
                    })

            # --- 計程車專項修補 (確保車資且防止重複) ---
            has_taxi = False
            for r in existing_routes:
                if "計程車" in str(r.get("title", "")):
                    r["title"] = f"{station_name}計程車"
                    r["departure"] = f"{station_name}站前"
                    if fare_note:
                        r["duration"] = fare_note.split("\n")[0] if "\n" in fare_note else fare_note
                    has_taxi = True

            if not has_taxi:
                f_lines = fare_note.split("\n") if fare_note else ["估計中"]
                existing_routes.insert(0, {
                    "type": "other",
                    "title": f"計程車 (估計車資)",
                    "departure": f"{station_name}車站站前廣場",
                    "duration": f_lines[0],
                    "priority": "急件" if (delay_time >= 20 or is_suspended) else "建議"
                })
            
            # --- 最終去重 (以 title 為準) ---
            seen_titles = set()
            new_routes = []
            for r in existing_routes:
                t = r.get("title")
                if t not in seen_titles:
                    new_routes.append(r)
                    seen_titles.add(t)
            structured_data["routes"] = new_routes
        
        structured_data["sources"] = sources_summary

        return jsonify({
            "structured": structured_data,
            "is_serious": delay_time >= 20 or is_suspended
        })

    except Exception as e:
        print(f" ask_ai 發生錯誤: {e}")
        traceback.print_exc()
        return jsonify({
            "structured": {
                "summary": "後端服務異常",
                "ai_advice": f"抱歉，後端發生錯誤：{str(e)[:50]}... 請稍後再試。",
                "routes": [],
                "emergency": "請依站務人員指示行動",
                "nav_dest": "台灣台東縣瑞穗鄉瑞穗車站",
                "sources": "系統診斷模式"
            },
            "is_serious": False
        }), 200


@app.route('/predict_recovery', methods=['POST'])
def predict_recovery():
    """專門為計畫中的『災害回復時間推估』設計的獨立接口"""
    data = request.json
    station_name = data.get('station_name', '')
    query = data.get('query', '目前因災害停駛')
    is_simulation = data.get('is_simulation', False)
    sim_type = data.get('sim_type', '')
    sim_intensity = data.get('sim_intensity', 0)
    
    print(f"--- [DEBUG] 正在推估 {station_name} 的回復時間 (Simulation: {is_simulation}) ---")
    
    try:
        history_context = []
        evidence_list = []

        # 1. 【新增】優先讀取本地專家知識 (Expert Knowledge)
        expert_path = os.path.join(BASE_DIR, "expert_knowledge.json")
        if os.path.exists(expert_path):
            with open(expert_path, 'r', encoding='utf-8') as f:
                expert_data = json.load(f)
                # 簡單的關鍵字匹配
                for item in expert_data:
                    match_found = False
                    # 匹配車站名稱
                    if station_name and item.get("location") and station_name in item.get("location"): match_found = True
                    # 匹配災情關鍵字 (地震/淹水/土石流)
                    if "地震" in query and "地震" in item.get("category", ""): match_found = True
                    if "雨" in query and ("淹水" in item.get("category", "") or "豪大雨" in item.get("situation", "")): match_found = True
                    
                    if match_found:
                        case_text = f"【專家知識/SOP】\n- 情境: {item.get('situation')}\n  處置: {item.get('solution')}\n  預估時間: {item.get('recovery_time')}"
                        history_context.append(case_text)
                        evidence_list.append({
                            "situation": item.get('situation', '專家定義情境'),
                            "solution": item.get('solution', '標竿處處置方案'),
                            "recovery_time": item.get('recovery_time', 'N/A'),
                            "source": item.get('source', '專家知識庫')
                        })

        # 2. RAG 檢索歷史災害情境 (作為補充)
        try:
            query_vector = get_embedding(query)
            search_results = pinecone_index.query(
                vector=query_vector,
                top_k=3,
                include_metadata=True
            )
            for match in search_results['matches']:
                meta = match['metadata']
                case_text = f"【歷史案例】\n- 事件: {meta.get('situation', '未知')}\n  處置與恢復: {meta.get('solution', '未知')}"
                history_context.append(case_text)
                evidence_list.append({
                    "situation": meta.get('situation', '歷史情境'),
                    "solution": meta.get('solution', '當時處置'),
                    "recovery_time": meta.get('recovery_time', 'N/A'),
                    "source": "歷史災害資料庫(RAG)"
                })
        except Exception as rag_e:
            print(f"    RAG 檢索異常: {rag_e}")

        context_block = "\n\n".join(history_context) if history_context else "無直接相關歷史案例。"
        
        # 3. 呼叫 AI 進行情境比對與時間推估
        prompt = f"""
你現在是台鐵災害應變專家的決議助手。
目前災害：『{query}』(地點：{station_name})

【參考資料（歷史/SOP/專家知識）】：
{context_block}

【推估規則】：
1. 若目前情境與【參考資料】高度相似（例如震度相同、地點相同），請「直接優先參考」該資料的回復時間。
2. 回復時間必須是一個具體區間（例如：2~3 小時）。
3. 如果是地震且震度 4 級以上，通常巡軌需至少 1.5 ~ 2 小時。
4. 如果是強降雨導致路線淹水，通常需等雨勢減緩後巡軌 1 小時方可恢復。

【輸出格式】：
僅輸出 JSON 格式：
{{
  "recovery_time": "請給出具體時間，絕不可只寫評估中 (例如: 1.5 ~ 3 小時)",
  "reason": "簡短說明依據何種案例 or SOP 推估"
}}
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.2
        )
        prediction = json.loads(response.choices[0].message.content)
        prediction["evidence"] = evidence_list[:5] # 限制回傳數量
        
        # 二次檢查：若 AI 仍頑皮回傳評估中，設定保底值
        if "評估中" in prediction.get("recovery_time", "") and "地震" in query:
             prediction["recovery_time"] = "2 ~ 4 小時"
             prediction["reason"] = "參考震度 4 級以上巡軌 SOP 保底推估"

        print(f" 推估結果: {prediction.get('recovery_time')} ({prediction.get('reason')})")
        return jsonify(prediction)

    except Exception as e:
        print(f" 推估失敗: {e}")
        return jsonify({"recovery_time": "2 ~ 4 小時 (系統預估)", "reason": "連線異常，採標竿 SOP 推估"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
