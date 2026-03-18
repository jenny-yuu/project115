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

# ─────────────── 1. 初始化與配置 (還原 Step 1000 版本並防錯) ───────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

openai_key = os.getenv("OPENAI_API_KEY")
pinecone_key = os.getenv("PINECONE_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

client = None
pinecone_index = None
try:
    if openai_key:
        client = openai.OpenAI(api_key=openai_key)
    if pinecone_key:
        pc = Pinecone(api_key=pinecone_key)
        pinecone_index = pc.Index("disaster-rag")
    print("✅ OpenAI 與 Pinecone 初始化成功")
except Exception as init_e:
    print(f"❌ API 客戶端初始化失敗: {init_e}")

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

db = None
try:
    CRED_PATH = os.path.join(BASE_DIR, "your-firebase-adminsdk.json")
    if os.path.exists(CRED_PATH) and not firebase_admin._apps:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase 初始化成功")
    db = firestore.client()
except Exception as e:
    print(f"⚠️ Firebase 初始化失敗: {e}")

PATHS = {
    "PROJECT_DIR": BASE_DIR,
    "MAPPING_FILE": os.path.join(BASE_DIR, "fb_stations.json")
}

# 💡 教授建議：主要站點到「市區或轉運站」的參考座標
CITY_CENTERS = {
    "花蓮": {"lat": 23.978, "lon": 121.611, "name": "花蓮市區(東大門)"},
    "臺東": {"lat": 22.793, "lon": 121.123, "name": "台東轉運站/市區"},
    "宜蘭": {"lat": 24.754, "lon": 121.758, "name": "宜蘭市區"},
    "羅東": {"lat": 24.677, "lon": 121.772, "name": "羅東夜市/市區"},
    "玉里": {"lat": 23.332, "lon": 121.312, "name": "玉里鎮中心"},
    "瑞穗": {"lat": 23.497, "lon": 121.376, "name": "瑞穗市區"}
}

# ─────────────── 2. 工具函數 ───────────────

def get_shuttle_metrics(station_name: str):
    """計算計程車費與 U-bike 門檻"""
    target = None
    for key, val in CITY_CENTERS.items():
        if key in station_name: target = val; break
    if not target:
        dist, target_name = 1.5, "最近轉運點"
    else:
        dist_map = {"花蓮": 3.2, "臺東": 5.1, "宜蘭": 0.8, "羅東": 0.5, "玉里": 1.1, "瑞穗": 0.3}
        dist = dist_map.get(station_name[:2], 1.5)
        target_name = target["name"]
    return {"distance": round(dist, 1), "target": target_name, "taxi_fare": 85 + max(0, int((dist - 1.25) * 25)), "show_ubike": dist <= 1.2}

def get_station_id(station_name: str) -> str:
    try:
        mapping_path = PATHS["MAPPING_FILE"]
        if os.path.exists(mapping_path):
            with open(mapping_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for s in data:
                    if station_name in s.get("Name", ""): return str(s.get("ID"))
    except: pass
    return None

def get_embedding(text):
    if not client: return [0.0]*1536
    response = client.embeddings.create(input=[text], model="text-embedding-3-small")
    return response.data[0].embedding

def get_tdx_token():
    try:
        url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
        data = {"grant_type": "client_credentials", "client_id": TDX_CLIENT_ID, "client_secret": TDX_CLIENT_SECRET}
        r = requests.post(url, data=data, timeout=10)
        return r.json().get("access_token")
    except: return None

def get_nearby_bus_schedules(station_name: str, token: str) -> list:
    if not token: return []
    try:
        url_sta = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/Station?$format=JSON"
        headers = {"Authorization": f"Bearer {token}"}
        r_sta = requests.get(url_sta, headers=headers, timeout=10)
        stations = r_sta.json().get('Stations', [])
        sta = next((s for s in stations if station_name in s['StationName']['Zh_tw']), None)
        if not sta: return []
        lon, lat = sta['StationPosition']['PositionLon'], sta['StationPosition']['PositionLat']
        city = "TaitungCounty" if "台東" in station_name or any(x in station_name for x in ["關山", "池上", "鹿野", "太麻里"]) else "HualienCounty"
        url = f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{city}?$spatialFilter=nearby({lat},{lon},1000)&$format=JSON"
        r = requests.get(url, headers=headers, timeout=10)
        results = []
        if r.status_code == 200:
            for b in r.json():
                eta = b.get('EstimateTime')
                if eta is not None:
                    results.append({"route": b.get('RouteName', {}).get('Zh_tw'), "departure": f"{eta//60} 分鐘" if eta > 0 else "即將到站", "destination": "附近站牌", "company": b.get('StopName', {}).get('Zh_tw')})
        return sorted(results, key=lambda x: x['departure'])[:5]
    except: return []

def format_bus_schedules(schedules: list) -> str:
    if not schedules: return ""
    return "\n".join([f"- [{s['departure']}] {s['route']} → {s['destination']}（{s['company']}）" for s in schedules])

def get_official_transfers(station_name: str, token: str) -> str:
    if not station_name: return ""
    output = []
    mapping = {"taxi": "計程車", "bus": "公車", "rail": "火車", "bike": "單車"}
    sid = get_station_id(station_name)
    if db:
        try:
            if sid:
                doc = db.collection("scraped_transfers").document(sid).get()
                if doc.exists:
                    data = doc.to_dict().get("transfers", {})
                    for k, v in mapping.items():
                        if data.get(k): output.append(f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]]))
                    if output: return "\n\n".join(output)
        except: pass
    return "（建議參考即時班次與地圖）"

def search_bus_info(station_name: str, destination: str = "") -> str:
    query = f'從 {station_name}車站 到 {destination} 怎麼搭客運' if destination else f'{station_name}車站 轉乘 附近客運站'
    url = f'https://duckduckgo.com/html/?q={urllib.parse.quote(query)}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        results = [f"- {div.find('a', class_='result__snippet').get_text().strip()}" for div in soup.find_all('div', class_='result__body', limit=3) if div.find('a', class_='result__snippet')]
        return "\n".join(results) if results else "（建議告知乘客前往站前尋找客運/公車站牌）"
    except: return "（無法執行網頁搜尋）"

# ─────────────── 3. Flask 路由 ───────────────

@app.route('/', methods=['GET'])
def index():
    return f"台鐵智慧行程助理後端已啟動！ (穩定版)"

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json or {}
        query = data.get('query', '')
        delay_time = data.get('delay_time', 0)
        is_suspended = data.get('is_suspended', False)
        station_name = data.get('station_name', '')
        sim_type = data.get('sim_type', '')
        sim_intensity = data.get('sim_intensity', 0)

        # 1. RAG 歷史搜尋
        context_block = "暫無歷史相關紀錄。"
        sources_summary = "歷史災害資料庫"
        if pinecone_index:
            try:
                query_vector = get_embedding(query)
                search_results = pinecone_index.query(vector=query_vector, top_k=5, include_metadata=True)
                ctx = [f"- 事件: {m['metadata'].get('situation')}\n  處置: {m['metadata'].get('solution')}" for m in search_results['matches']]
                context_block = "\n".join(ctx)
            except: pass

        # 2. TDX 與 搜尋
        tdx_token = get_tdx_token()
        bus_text = format_bus_schedules(get_nearby_bus_schedules(station_name, tdx_token)) if tdx_token else ""
        official_transfer_text = get_official_transfers(station_name, tdx_token)
        search_text = search_bus_info(station_name, data.get('destination', ''))

        # 3. 呼叫 GPT (還原 Step 1000 原始 Prompt)
        advice_focus = f"目前的狀況是 {'停駛' if is_suspended else '延誤'}。請推薦轉乘方案。"
        prompt = f"""你現在是「台鐵智慧行程助理」。目前的狀況是：「{query}」。
{advice_focus}

【參考歷史資料】：
{context_block}

【目前可搭乘的客運即時班次】：
{bus_text if bus_text else "無具體班次時間"}

【TDX 台鐵官方轉乘資訊】：
{official_transfer_text}

【網路即時搜尋替代路線建議】：
{search_text}

【輸出格式要求】：
請「務必」以 JSON 格式回答，包含以下欄位：
1. "summary": 15字以內的簡短狀況總結。
2. "ai_advice": 給乘客的詳細安全提醒（80字內），必須具有同理心。
3. "routes": 列表，包含 3~5 個建議項目（type: train/bus/other, title, departure, duration, priority: 急件/建議）。
4. "emergency": 嚴重警示文字。
5. "nav_dest": 建議導航位址。
"""
        if not client: raise Exception("OpenAI 未初始化")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        res_json = json.loads(response.choices[0].message.content)
        
        # --- 4. 【核心補強】不改 Prompt，改由代碼注入計程車與修復標題 ---
        shuttle = get_shuttle_metrics(station_name)
        routes = res_json.get("routes", [])
        
        # (1) 標題救援機制：如果 AI 給了空標題，就拿內容來補
        for r in routes:
            if not r.get("title") or r["title"].strip() == "":
                r["title"] = r.get("departure", "大眾運輸轉乘")[:15]
        
        # (2) 計程車注入：尊重 AI 排序
        taxi_item = {
            "type": "taxi", "title": f"計程車 (至{shuttle['target']})",
            "departure": f"距離約 {shuttle['distance']}km",
            "duration": f"預估車資 NT$ {shuttle['taxi_fare']}", "priority": "建議"
        }
        
        taxi_idx = -1
        for i, r in enumerate(routes):
            if any(k in r.get("title", "") or r.get("type") == "taxi" for k in ["計程車", "taxi"]):
                taxi_idx = i; break
        
        if taxi_idx != -1: routes[taxi_idx] = taxi_item
        else: routes.append(taxi_item)
        
        # (3) U-bike (如果近)
        if shuttle['show_ubike'] and not any("單車" in r.get("title", "") for r in routes):
            routes.append({"type": "u-bike", "title": "公共自行車 (U-bike)", "departure": "站前設有站點", "duration": "建議騎乘", "priority": "建議"})
            
        res_json["routes"] = routes[:5]
        res_json["sources"] = sources_summary

        return jsonify({"structured": res_json, "is_serious": delay_time >= 20 or is_suspended})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"structured": {"summary": "連線異常", "ai_advice": "請依站務人員指示行動。"}, "is_serious": False})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
