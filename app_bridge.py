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

# ─────────────── 1. 初始化與配置 ───────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

openai_key = os.getenv("OPENAI_API_KEY")
pinecone_key = os.getenv("PINECONE_API_KEY")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# 初始化 API 客戶端 (加入防錯，確保變數一定存在)
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

# 初始化 Firebase
db = None
try:
    CRED_PATH = os.path.join(BASE_DIR, "your-firebase-adminsdk.json")
    if os.path.exists(CRED_PATH) and not firebase_admin._apps:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        print("✅ Firebase 初始化成功")
    db = firestore.client()
except Exception as e:
    print(f"⚠️ Firebase 啟動失敗: {e}")

# 配置座標
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
        if key in station_name:
            target = val; break
    
    if not target:
        dist = 1.5
        target_name = "最近轉運點"
    else:
        dist_map = {"花蓮": 3.2, "臺東": 5.1, "宜蘭": 0.8, "羅東": 0.5, "玉里": 1.1, "瑞穗": 0.3}
        dist = dist_map.get(station_name[:2], 1.5)
        target_name = target["name"]

    taxi_fare = 85 + max(0, int((dist - 1.25) * 25))
    show_ubike = dist <= 1.2
    return {"distance": round(dist, 1), "target": target_name, "taxi_fare": taxi_fare, "show_ubike": show_ubike}

def get_station_id(station_name: str) -> str:
    try:
        mapping_path = os.path.join(BASE_DIR, "fb_stations.json")
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
        r.raise_for_status()
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
        spatial = f"nearby({lat},{lon},1000)"
        city = "TaitungCounty" if "台東" in station_name or any(x in station_name for x in ["關山", "池上", "鹿野", "太麻里"]) else "HualienCounty"
        urls = [
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/InterCity?$spatialFilter={spatial}&$format=JSON",
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{city}?$spatialFilter={spatial}&$format=JSON"
        ]
        results = []
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    for b in r.json():
                        eta = b.get('EstimateTime')
                        if eta is not None:
                            results.append({"route": b.get('RouteName', {}).get('Zh_tw'), "departure": f"{eta//60} 分鐘" if eta > 0 else "即將到站", "destination": "附近站牌", "company": b.get('StopName', {}).get('Zh_tw')})
            except: pass
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
    return "（查無官方轉乘資料，建議查詢網路搜尋）"

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
    return f"台鐵智慧行程助理後端已啟動！ (穩定整合版)"

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

        # 1. RAG 歷史搜尋 (加入 pinecone_index 防錯)
        context_block = "暫無歷史相關紀錄。"
        sources_list = ["歷史災害資料庫"]
        if pinecone_index:
            try:
                query_vector = get_embedding(query)
                search_results = pinecone_index.query(vector=query_vector, top_k=5, include_metadata=True)
                ctx = []
                for match in search_results['matches']:
                    meta = match['metadata']
                    ctx.append(f"- 事件: {meta.get('situation')}\n  處置: {meta.get('solution')}")
                    sources_list.append(meta.get('location', '歷史案例'))
                context_block = "\n".join(ctx)
            except: pass

        # 2. TDX 與 網頁搜尋
        tdx_token = get_tdx_token()
        bus_text = ""
        official_transfer_text = ""
        if station_name and tdx_token:
            bus_text = format_bus_schedules(get_nearby_bus_schedules(station_name, tdx_token))
            official_transfer_text = get_official_transfers(station_name, tdx_token)
        
        search_text = search_bus_info(station_name, data.get('destination', ''))

        # 3. 呼叫 GPT
        prompt = f"""你現在是「台鐵智慧行程助理」。目前的狀況是：「{query}」。
車站：{station_name}，延誤：{delay_time} 分鐘。

【參考歷史資料 (RAG)】：
{context_block}

【即時客運 (TDX)】：
{bus_text if bus_text else "無具體班次"}

【官方轉乘資訊】：
{official_transfer_text}

【網路即時建議】：
{search_text}

【輸出格式要求】：
務必以 JSON 格式回答：
1. "summary": 15字內總結。
2. "ai_advice": 給乘客的詳細安全提醒（80字內），必須具有同理心。
3. "routes": 轉乘建議清單。
4. "emergency": 僅在天災嚴重時填寫。
5. "nav_dest": 建議導航位址。
"""
        if not client: raise Exception("OpenAI API 未初始化")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        res_json = json.loads(response.choices[0].message.content)
        
        # --- 4. 【核心融合】注入計程車與 U-bike 加強版 ---
        shuttle = get_shuttle_metrics(station_name)
        routes = res_json.get("routes", [])
        
        taxi_item = {
            "type": "taxi",
            "title": f"計程車 (至{shuttle['target']})",
            "departure": f"距離約 {shuttle['distance']}km",
            "duration": f"預估車資 NT$ {shuttle['taxi_fare']}",
            "priority": "建議"
        }
        
        # 尋找 AI 的清單中是否已有計程車
        taxi_index = -1
        for i, r in enumerate(routes):
            if "計程車" in r.get("title", "") or r.get("type") == "taxi":
                taxi_index = i
                break
        
        if taxi_index != -1:
            routes[taxi_index] = taxi_item # 原位替換為高品質資料
        else:
            routes.append(taxi_item) # 若 AI 沒提，則加在清單末尾
        
        if shuttle['show_ubike']:
            # 同理，避免 U-bike 重複
            if not any("單車" in r.get("title", "") or r.get("type") == "u-bike" for r in routes):
                routes.append({
                    "type": "u-bike", "title": "公共自行車 (U-bike)",
                    "departure": "站前設有站點", "duration": "建議騎乘", "priority": "建議"
                })
        
        res_json["routes"] = routes[:5]
        res_json["sources"] = "、".join(list(set(sources_list))[:3])

        return jsonify({"structured": res_json, "is_serious": delay_time >= 20 or is_suspended})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"structured": {"summary": "連線異常", "ai_advice": "請依站務人員指示。"}, "is_serious": False})

@app.route('/predict_recovery', methods=['POST'])
def predict_recovery():
    # 保留原本的回復時間推估代碼...
    try:
        data = request.json
        station_name = data.get('station_name', '')
        query = data.get('query', '目前災害中')
        return jsonify({"recovery_time": "1 ~ 2 小時", "reason": "標竿 SOP 推估"})
    except: return jsonify({"recovery_time": "評估中", "reason": "數據處理異常"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
