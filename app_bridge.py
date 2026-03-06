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

    # 1. 【最強優先】Firebase Cloud 資料 (與 D 槽 project 同步)
    if db:
        try:
            # 優先查 scraped_transfers 專屬集合 (以 ID 索引)
            if sid:
                doc = db.collection("scraped_transfers").document(sid).get()
                if doc.exists:
                    data = doc.to_dict().get("transfers", {})
                    for k, v in mapping.items():
                        if data.get(k):
                            output.append(f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]]))
                    if output:
                        print(f"   [Cloud] 從 Firebase/scraped_transfers 取得 {station_name}({sid}) 資料")
                        return "\n\n".join(output)

            # 其次查 stations 通用集合 (以名稱/模糊匹配)
            docs = db.collection("stations").stream()
            for doc in docs:
                d = doc.to_dict()
                if station_name in d.get("StationName", ""):
                    official = d.get("official_transfers")
                    if official and official.get("status") == "Available":
                        data = official.get("data", {})
                        for k, v in mapping.items():
                            if data.get(k):
                                output.append(f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]]))
                        if output:
                            print(f"   [Cloud] 從 Firebase/stations 取得 {station_name} 資料")
                            return "\n\n".join(output)
        except Exception as e:
            print(f"⚠️ Firebase 雲端查詢異常: {e}")

    # 2. 【二級優先】D 槽 Project 資料 (scraped_transfers.json)
    try:
        scraped_path = os.path.join(PATHS["PROJECT_DIR"], "scraped_transfers.json")
        if os.path.exists(scraped_path):
            with open(scraped_path, 'r', encoding='utf-8') as f:
                scraped_data = json.load(f)
                # 使用 ID 或名稱查詢
                target_data = scraped_data.get(sid) if sid else None
                if not target_data:
                    target_data = next((v for v in scraped_data.values() if station_name in v.get("station_name", "")), None)
                
                if target_data:
                    trans = target_data.get("transfers", {})
                    for k, v in mapping.items():
                        if trans.get(k):
                            output.append(f"【{v}】\n" + "\n".join([f"- {i}" for i in trans[k]]))
                    if output:
                        print(f"   [Local] 從 D 槽 scraped_transfers.json 取得 {station_name} 資料")
                        return "\n\n".join(output)
    except Exception as e:
        print(f"⚠️ D 槽資料讀取異常: {e}")

    # 3. 【三級優先】OneDrive Research 資料 (StationTransfer.json)
    try:
        research_path = os.path.join(PATHS["RESEARCH_DIR"], "StationTransfer.json")
        if not os.path.exists(research_path):
            research_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\StationTransfer.json"
            
        if os.path.exists(research_path):
            with open(research_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "{" in content: # 簡單檢查是否為合法的 JSON
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
                                    output.append(f"{cat_name}\n" + "\n".join([f"- {i}" for i in descs]))
                            if output:
                                print(f"   [Research] 從 OneDrive/StationTransfer.json 取得 {station_name} 資料")
                                return "\n\n".join(output)
    except Exception as e:
        print(f"⚠️ OneDrive 研究資料讀取異常: {e}")

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
    data = request.json
    query = data.get('query', '')
    delay_time = data.get('delay_time', 0)
    is_suspended = data.get('is_suspended', False)
    station_name = data.get('station_name', '')
    sim_type = data.get('sim_type', '')
    sim_intensity = data.get('sim_intensity', 0)

    print(f"--- [DEBUG] 新請求: {station_name} (延誤: {delay_time}m, 停駛: {is_suspended}, Sim: {sim_type} {sim_intensity}) ---")

    try:
        # 1. RAG 向量搜尋
        print("1. 生成 Embedding...")
        query_vector = get_embedding(query)

        print("2. 查詢 Pinecone...")
        search_results = pinecone_index.query(
            vector=query_vector,
            top_k=5,
            include_metadata=True
        )

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
        sources_summary = "、".join(sources_list[:3]) if sources_list else "歷史災害資料庫"
        print(f"   找到 {len(context_texts)} 筆參考資料")

        # 2. 查詢 TDX 真實班次與網頁搜尋
        print(f"3. 查詢 {station_name} 的即時交通資訊...")
        try:
            tdx_token = get_tdx_token()
            print(f"   TDX Token: {'取得成功' if tdx_token else '失敗'}")
        except Exception as tdx_e:
            print(f"   ❌ TDX Token 取得異常: {tdx_e}")
            tdx_token = None
            
        bus_text = ""
        official_transfer_text = ""
        user_dest = data.get('destination', '')
        
        print(f"   正在搜尋網頁資訊... (目的地: {user_dest})")
        try:
            search_text = search_bus_info(station_name, user_dest)
            print(f"   網頁搜尋成功，結果長度: {len(search_text)}")
        except Exception as search_e:
            print(f"   ❌ 網頁搜尋異常: {search_e}")
            search_text = "（無法執行網頁搜尋）"

        if station_name:
            if tdx_token:
                print(f"   正在查詢 {station_name} 的即時公車...")
                bus_schedules = get_nearby_bus_schedules(station_name, tdx_token)
                if bus_schedules:
                    bus_text = format_bus_schedules(bus_schedules)
                    print(f"   找到 {len(bus_schedules)} 筆公車資訊")
                
                # 取得台鐵官方內部/跨運具指南
                official_transfer_text = get_official_transfers(station_name, tdx_token)
            else:
                print("   ⚠️ 無 TDX Token，僅依賴網頁搜尋與靜態資料")
                # 嘗試在無 token 情況下讀取本地靜態資料
                official_transfer_text = get_official_transfers(station_name, None)

        # 3. 呼叫 GPT
        print("4. 呼叫 GPT-4o-mini...")

        if is_suspended:
            if sim_type:
                situation_desc = f"模擬災害：{sim_type} (強度: {sim_intensity})"
            else:
                situation_desc = "列車停駛（紅燈警示）"
            advice_focus = f"目前的狀況是 {situation_desc}。重點推薦替代交通工具（客運或計程車），並參照官方轉乘資訊。"
        else:
            situation_desc = f"列車延誤 {delay_time} 分鐘" if delay_time > 0 else "目前正常行駛"
            advice_focus = "目前營運正常，但請依據底下官方轉乘資訊或網頁搜尋結果，推薦轉乘方案。"

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
請「務必」以 JSON 格式回答，包含以下欄位：
1. "summary": 15字以內的簡短狀況總結。
2. "ai_advice": 給乘客的提醒（40字以內），必須具有同理心，提醒安全。
3. "routes": 列表，作為畫面的「應變建議」，【數量要求】：必須提供 3~5 個建議項目。每個元素：
    - "type": "train", "bus", or "other"
    - "title": 路線名稱（若有真實班次則包含路線號碼，例如：846 客運 → 平溪；若無班次則描述行為，例如：前往站前區民廣場搭公車）
    - "departure": 發車時間，若無預估則留空
    - "duration": 預估車程
    - "priority": "急件" 或 "建議"
4. "emergency": 嚴重警示文字，僅在天災停駛時填寫。
5. "nav_dest": **極重要：建議導航的目的地關鍵字**。
   【規則】：必須是具體的店名、站牌地址或地標，且必須包含「台灣」和「縣市」名稱，以確保 Google Maps 不會定位到國外。
   例如：「台灣新北市瑞芳區明燈路三段19號（區民廣場）」或「台灣台東縣關山鎮關山轉運站」。

【重要：生成建議規則】
1. **資料優先權**：請務必細讀【TDX 台鐵官方轉乘資訊】中的地址。若資料中有出現完整地址（通常在括號內，例如：瑞芳區明燈路...），請**優先且完整地**填入 `nav_dest` 欄位。
2. **導航精準度**：`nav_dest` 必須是能讓 Google Maps 直接定位的地點或地址。如果官方資料有地址，請直接使用該地址；若無地址，則使用「台灣 + 縣市 + 具體站牌名」。
3. **數量保證**：至少生成 3 個建議項目，嚴禁空回。
4. **網路援引**：若即時班次不足，請參考網頁建議（例如瑞芳往平溪可能搭公車）。
"""

        print(f"4. 呼叫 GPT-4o-mini... (Prompt 長度: {len(prompt)})")
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=800,
                temperature=0.3,
                timeout=25
            )
            raw_json = response.choices[0].message.content
            print(f"✅ AI 原始回覆: {raw_json}")
        except Exception as ai_e:
            print(f"❌ OpenAI API 呼叫失敗: {ai_e}")
            raise ai_e

        try:
            structured_data = json.loads(raw_json)
        except Exception as json_e:
            print(f"❌ JSON 解析 AI 回覆失敗: {json_e}")
            raise json_e
            
        # 強制過濾非停駛狀態的警語，避免 AI 產生多餘的紅字
        if not is_suspended:
            structured_data["emergency"] = ""
            
        structured_data["sources"] = sources_summary

        return jsonify({
            "structured": structured_data,
            "is_serious": delay_time >= 20 or is_suspended
        })

    except Exception as e:
        print(f"❌ 錯誤詳情: {e}")
        import traceback
        traceback.print_exc()
        try:
            with open("error_trace.txt", "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except: pass
        return jsonify({
            "structured": {
                "summary": "系統連線中",
                "ai_advice": "建議向站務人員詢問替代方案。",
                "routes": [],
                "emergency": "",
                "nav_dest": "",
                "sources": ""
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
                            "solution": item.get('solution', '標竿處置方案'),
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
  "reason": "簡短說明依據何種案例或 SOP 推估"
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
