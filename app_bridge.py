import os
import json
import openai
import requests
import traceback
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
    print("✅ OpenAI 與 Pinecone 初始化成功")
except Exception as init_e:
    print(f"❌ API 客戶端初始化失敗: {init_e}")

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# 初始化 Firebase
try:
    # 使用相對路徑尋找金鑰
    CRED_PATH = os.path.join(BASE_DIR, "your-firebase-adminsdk.json")
    
    if os.path.exists(CRED_PATH) and not firebase_admin._apps:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase 初始化成功")
    db = firestore.client()
except Exception as e:
    print(f"⚠️ Firebase 初始化失敗 (可能是缺少 JSON 金鑰): {e}")
    db = None

# 配置相對路徑
PATHS = {
    "PROJECT_DIR": BASE_DIR,
    "MAPPING_FILE": os.path.join(BASE_DIR, "fb_stations.json")
}

# ─────────────── 基礎資料載入 (里程與車資) ───────────────
STATION_DISTANCES = {}
try:
    csv_path = os.path.join(BASE_DIR, "tra_eastern_mainline_EL_stations.csv")
    if os.path.exists(csv_path):
        import csv
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                STATION_DISTANCES[row['StationName']] = float(row['TraveledDistance'])
        print(f"✅ 已載入 {len(STATION_DISTANCES)} 筆車站里程資料")
except Exception as e:
    print(f"⚠️ 里程資料載入失敗: {e}")

def get_taxi_fare_str(station_name: str) -> str:
    """估算到鄰近車站的計程車資"""
    if not station_name or station_name not in STATION_DISTANCES:
        return ""
    
    names = list(STATION_DISTANCES.keys())
    idx = names.index(station_name)
    notes = []
    
    # 找前後站
    targets = []
    if idx > 0: targets.append(names[idx-1])
    if idx < len(names) - 1: targets.append(names[idx+1])
    
    for t in targets:
        dist = abs(STATION_DISTANCES[t] - STATION_DISTANCES[station_name])
        # 費率：1.25km(85元) + 每200m(5元)
        import math
        fare = 85 + (math.ceil((dist - 1.25) / 0.2) * 5 if dist > 1.25 else 0)
        notes.append(f"至 {t} 約 {dist:.1f}km / 估計車資 {int(fare)} 元")
    
    return "\n".join(notes) if notes else ""

# ─────────────── 工具函數 ───────────────

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
        print(f"⚠️ TDX 取得 token 失敗: {e}")
        return None



def get_nearby_bus_schedules(station_name: str, token: str) -> list:
    """使用空間過濾 (Nearby) 查詢車站附近的公車預估到站時間 (ETA)"""
    if not token: return []
    try:
        # 1. 先從 TDX 取得車站座標
        url_sta = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/Station?$format=JSON"
        headers = {"Authorization": f"Bearer {token}"}
        r_sta = requests.get(url_sta, headers=headers, timeout=10)
        stations = r_sta.json().get('Stations', [])
        sta = next((s for s in stations if station_name in s['StationName']['Zh_tw']), None)
        if not sta: return []
        lon, lat = sta['StationPosition']['PositionLon'], sta['StationPosition']['PositionLat']
        
        # 2. 同時查詢客運(InterCity)與市區公車(City)
        results = []
        spatial = f"nearby({lat},{lon},1000)"
        
        # 判斷縣市
        city = "TaitungCounty" if "台東" in station_name or any(x in station_name for x in ["關山", "池上", "鹿野", "太麻里"]) else "HualienCounty"
        
        urls = [
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/InterCity?$spatialFilter={spatial}&$format=JSON",
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{city}?$spatialFilter={spatial}&$format=JSON"
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
        print(f"⚠️ TDX Nearby 查詢失敗: {e}")
        return []


def format_bus_schedules(schedules: list) -> str:
    """將班次列表格式化為 prompt 用的文字"""
    if not schedules:
        return ""
    lines = []
    for s in schedules:
        note = f"【{s.get('note', '')}】" if s.get("note") else ""
        lines.append(f"- {note}[{s['departure']}] {s['route']} → {s['destination']}（{s['company']}）")
    return "\n".join(lines)


def get_official_transfers(station_name: str, token: str) -> str:
    """整合 Firebase (Cloud), D 槽 (Project), OneDrive (Research) 的多方轉乘資料"""
    if not station_name: return ""
    
    output = []
    mapping = {"taxi": "計程車", "bus": "公路運輸/公車", "rail": "軌道運輸/火車", "bike": "公共自行車"}
    sid = get_station_id(station_name)
    fare_note = get_taxi_fare_str(station_name)

    # 1. 【最強優先】Firebase Cloud 資料
    if db:
        try:
            if sid:
                doc = db.collection("scraped_transfers").document(sid).get()
                if doc.exists:
                    data = doc.to_dict().get("transfers", {})
                    for k, v in mapping.items():
                        if data.get(k):
                            text = f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]])
                            if k == "taxi" and fare_note:
                                text += f"\n- (預估車資：\n{fare_note})"
                            output.append(text)
                    if output:
                        print(f"   [Cloud] 從 Firebase/scraped_transfers 取得 {station_name}({sid}) 資料")
                        return "\n\n".join(output)

            docs = db.collection("stations").stream()
            for doc in docs:
                d = doc.to_dict()
                if station_name in d.get("StationName", ""):
                    official = d.get("official_transfers")
                    if official and official.get("status") == "Available":
                        data = official.get("data", {})
                        for k, v in mapping.items():
                            if data.get(k):
                                text = f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]])
                                if k == "taxi" and fare_note:
                                    text += f"\n- (預估車資：\n{fare_note})"
                                output.append(text)
                        if output:
                            print(f"   [Cloud] 從 Firebase/stations 取得 {station_name} 資料")
                            return "\n\n".join(output)
        except Exception as e:
            print(f"⚠️ Firebase 雲端查詢異常: {e}")

    # 2. 【二級優先】scraped_transfers.json
    try:
        scraped_path = os.path.join(PATHS["PROJECT_DIR"], "scraped_transfers.json")
        if os.path.exists(scraped_path):
            with open(scraped_path, 'r', encoding='utf-8') as f:
                scraped_data = json.load(f)
                target_data = scraped_data.get(sid) if sid else None
                if not target_data:
                    target_data = next((v for v in scraped_data.values() if station_name in v.get("station_name", "")), None)
                if target_data:
                    trans = target_data.get("transfers", {})
                    for k, v in mapping.items():
                        if trans.get(k):
                            text = f"【{v}】\n" + "\n".join([f"- {i}" for i in trans[k]])
                            if k == "taxi" and fare_note:
                                text += f"\n- (預估車資：\n{fare_note})"
                            output.append(text)
                    if output:
                        print(f"   [Local] 從 D 槽 scraped_transfers.json 取得 {station_name} 資料")
                        return "\n\n".join(output)
    except Exception as e:
        print(f"⚠️ D 槽資料讀取異常: {e}")

    # 3. 【三級優先】StationTransfer.json
    try:
        research_path = os.path.join(BASE_DIR, "StationTransfer.json")
        if os.path.exists(research_path):
            with open(research_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "{" in content:
                    static_data = json.loads(content).get('StationTransfers', [])
                    for s in static_data:
                        if station_name in s.get('StationName', {}).get('Zh_tw', ''):
                            for mode in s.get('TransferModes', []):
                                m_type = mode.get('TransferMode')
                                cat_name = "【公路運輸】"
                                if "Taxi" in m_type: cat_name = "【計程車】"
                                elif "Bicycle" in m_type: cat_name = "【公共自行車】"
                                elif m_type in ["MRT", "HSR", "Train"]: cat_name = "【軌道運輸】"
                                descs = [d.get('Description') for d in mode.get('Descriptions', []) if d.get('Description')]
                                if descs:
                                    text = f"{cat_name}\n" + "\n".join([f"- {i}" for i in descs])
                                    if cat_name == "【計程車】" and fare_note:
                                        text += f"\n- (預估車資：\n{fare_note})"
                                    output.append(text)
                            if output:
                                print(f"   [Research] 從 OneDrive/StationTransfer.json 取得 {station_name} 資料")
                                return "\n\n".join(output)
    except Exception as e:
        print(f"⚠️ OneDrive 研究資料讀取異常: {e}")

    if output:
        return "\n\n".join(output)

    return "（查無官方轉乘資料，建議查詢網路搜尋結果）"


def search_bus_info(station_name: str, destination: str = "") -> str:
    """使用 DuckDuckGo 搜尋替代客運路線"""
    if destination:
        query = f'從 {station_name}車站 到 {destination} 怎麼搭車 客運'
    else:
        query = f'{station_name}車站 轉乘 附近客運站'
    
    url = f'https://duckduckgo.com/html/?q={urllib.parse.quote(query)}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
    try:
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        # 嘗試抓取搜尋結果的標題或內容
        for div in soup.find_all('div', class_='result__body', limit=3):
            snippet = div.find('a', class_='result__snippet')
            if snippet:
                text = snippet.get_text().strip()
                if len(text) > 10: results.append(f"- {text}")
        return "\n".join(results) if results else "（建議告知乘客前往站前尋找客運/公車站牌，或聯絡當地計程車）"
    except Exception as e:
        print(f"⚠️ 搜尋失敗: {e}")
        return "（無法執行網頁搜尋）"

# ─────────────── Flask 路由 ───────────────

@app.route('/', methods=['GET'])
def index():
    print(f"--- [DEBUG: VERSION 4.0] ROOT INDEX HIT from {__file__} ---")
    return f"台鐵智慧行程助理後端已啟動！[DEBUG: VERSION 4.0] (API 正常運作中) - File: {__file__}"

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        if not data:
            return jsonify({
                "structured": {
                    "summary": "請求無效",
                    "ai_advice": "接收到空請求，請重試。",
                    "routes": [],
                    "emergency": "",
                    "nav_dest": "",
                    "sources": ""
                },
                "is_serious": False
            }), 400
            
        query = data.get('query', '')
        delay_time = data.get('delay_time', 0)
        is_suspended = data.get('is_suspended', False)
        station_name = data.get('station_name', '')
        sim_type = data.get('sim_type', '')
        sim_intensity = data.get('sim_intensity', 0)

        print(f"--- [DEBUG] 新請求: {station_name} (延誤: {delay_time}m, 停駛: {is_suspended}, Sim: {sim_type} {sim_intensity}) ---")

        # 1. RAG 向量搜尋
        print("1. 生成 Embedding...")
        try:
            query_vector = get_embedding(query)
        except Exception as e:
            print(f"❌ OpenAI Embedding 失敗: {e}")
            raise e

        print("2. 查詢 Pinecone...")
        try:
            search_results = pinecone_index.query(
                vector=query_vector,
                top_k=5,
                include_metadata=True
            )
        except Exception as e:
            print(f"❌ Pinecone 查詢失敗: {e}")
            raise e

        context_texts = []
        sources_list = []
        for match in search_results['matches']:
            meta = match['metadata']
            cat = meta.get('category', '未知')
            if "颱風" in cat:
                info = f"[歷史颱風] {meta.get('name')}: {meta.get('start_time')} 強度 {meta.get('intensity')}"
                sources_list.append(f"颱風：{meta.get('name', '')}")
            elif "雨量" in cat:
                info = f"[歷史雨量] 測站 {meta.get('station_no')}: {meta.get('name')} 颱風期間"
                sources_list.append("雨量記錄")
            elif "地震" in cat:
                info = f"[歷史地震] 規模 {meta.get('magnitude')}: {meta.get('time')}"
                sources_list.append(f"地震 M{meta.get('magnitude', '')}")
            else:
                info = f"[歷史事故] {meta.get('location')}: {meta.get('situation')}"
                sources_list.append(f"事故：{meta.get('location', '')}")

            solution = meta.get('solution', '請依站務人員指示慢行/停駛。')
            context_texts.append(f"- {info}\n  歷年處置建議: {solution}")

        context_block = "\n\n".join(context_texts)
        sources_summary = "、".join(list(set(sources_list))[:3]) if sources_list else "歷史災害資料庫"
        
        # --- 新增：從專家知識庫取得 SOP (作為 RAG 補充) ---
        try:
            expert_path = os.path.join(BASE_DIR, "expert_knowledge.json")
            if os.path.exists(expert_path):
                with open(expert_path, 'r', encoding='utf-8') as f:
                    expert_data = json.load(f)
                    expert_context = []
                    for item in expert_data:
                        match = False
                        if "地震" in query and "地震" in item.get("category", ""): match = True
                        if station_name and item.get("location") and station_name in item["location"]: match = True
                        if match:
                            expert_context.append(f"【官方SOP】{item.get('situation','')}: {item.get('solution','')}")
                            sources_summary += "、" + item.get("source", "專家SOP")
                    if expert_context:
                        context_block += "\n\n" + "\n".join(expert_context)
        except Exception as e:
            print(f"⚠️ 讀取專家知識失敗: {e}")

        print(f"   找到 {len(context_texts)} 筆參考資料 + 專家 SOP")

        # 2. 查詢 TDX 真實班次與網頁搜尋
        print(f"3. 查詢 {station_name} 的即時交通資訊...")
        try:
            tdx_token = get_tdx_token()
        except:
            tdx_token = None
            
        bus_text = ""
        official_transfer_text = ""
        user_dest = data.get('destination', '')
        
        try:
            search_text = search_bus_info(station_name, user_dest)
        except:
            search_text = "（網路搜尋暫時無法使用）"

        if station_name:
            if tdx_token:
                try:
                    bus_schedules = get_nearby_bus_schedules(station_name, tdx_token)
                    if bus_schedules:
                        bus_text = format_bus_schedules(bus_schedules)
                except: pass
                
                try:
                    official_transfer_text = get_official_transfers(station_name, tdx_token)
                except: pass
            else:
                official_transfer_text = get_official_transfers(station_name, None)

        # 3. 呼叫 GPT
        # 判定是否為地震急件
        is_earthquake = "地震" in query or (sim_type == "地震" and sim_intensity >= 3)
        
        if is_suspended:
            situation_desc = f"模擬災害：{sim_type} (強度: {sim_intensity})" if sim_type else "列車停駛（紅燈警示）"
            advice_focus = f"目前的狀況是 {situation_desc}。重點推薦替代交通工具（客運或計程車），並參照官方轉乘資訊。"
        else:
            situation_desc = f"列車延誤 {delay_time} 分鐘" if delay_time > 0 else "目前正常行駛"
            advice_focus = "目前營運正常，但請依據底下官方轉乘資訊 or 網頁搜尋結果，推薦轉乘方案。"
            if is_earthquake:
                advice_focus += " 注意：雖然尚未停駛，但因有地震紀錄，請提醒乘客注意安全與巡軌可能的延誤。"

        prompt = f"""
你現在是「台鐵智慧行程助理」。目前的狀況是：「{query}」。
{advice_focus}

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
        structured_data["sources"] = sources_summary

        return jsonify({
            "structured": structured_data,
            "is_serious": delay_time >= 20 or is_suspended
        })

    except Exception as e:
        print(f"❌ ask_ai 發生錯誤: {e}")
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
        expert_path = os.path.join(os.path.dirname(__file__), "expert_knowledge.json")
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
            print(f"   ⚠️ RAG 檢索異常: {rag_e}")

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

        print(f"✅ 推估結果: {prediction.get('recovery_time')} ({prediction.get('reason')})")
        return jsonify(prediction)

    except Exception as e:
        print(f"❌ 推估失敗: {e}")
        return jsonify({"recovery_time": "2 ~ 4 小時 (系統預估)", "reason": "連線異常，採標竿 SOP 推估"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
