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

# ─────────────── 初始化與配置 ───────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

openai_key = os.getenv("OPENAI_API_KEY")
pinecone_key = os.getenv("PINECONE_API_KEY")

app = Flask(__name__)
CORS(app)

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
except Exception as e:
    print(f"❌ API 初始化失敗: {e}")

# 初始化 Firebase
db = None
try:
    CRED_PATH = os.path.join(BASE_DIR, "your-firebase-adminsdk.json")
    if os.path.exists(CRED_PATH) and not firebase_admin._apps:
        cred = credentials.Certificate(CRED_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase 初始化成功")
except Exception as e:
    print(f"⚠️ Firebase 啟動失敗: {e}")

TDX_CLIENT_ID = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

# 💡 教授建議：主要站點到「市區或轉運站」的參考座標
CITY_CENTERS = {
    "花蓮": {"lat": 23.978, "lon": 121.611, "name": "花蓮市區(東大門)"},
    "臺東": {"lat": 22.793, "lon": 121.123, "name": "台東轉運站/市區"},
    "宜蘭": {"lat": 24.754, "lon": 121.758, "name": "宜蘭市區"},
    "羅東": {"lat": 24.677, "lon": 121.772, "name": "羅東夜市/市區"},
    "玉里": {"lat": 23.332, "lon": 121.312, "name": "玉里鎮中心"},
    "瑞穗": {"lat": 23.497, "lon": 121.376, "name": "瑞穗市區"}
}

# ─────────────── 核心邏輯 ───────────────

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
        return r.json().get("access_token")
    except: return None

def get_official_transfers(station_name: str) -> str:
    """從 Firebase 取得官方轉乘資料"""
    if not db: return ""
    sid = get_station_id(station_name)
    try:
        if sid:
            doc = db.collection("scraped_transfers").document(sid).get()
            if doc.exists:
                data = doc.to_dict().get("transfers", {})
                res = []
                for k, v in {"taxi": "計程車", "bus": "公車", "bike": "單車"}.items():
                    if data.get(k): res.append(f"【{v}】\n" + "\n".join([f"- {i}" for i in data[k]]))
                return "\n\n".join(res)
    except: pass
    return ""

# ─────────────── Flask 路由 ───────────────

@app.route('/', methods=['GET'])
def index():
    return "台鐵智慧行程助理後端運轉中 (新舊融合版)"

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        query = data.get('query', '')
        delay_time = data.get('delay_time', 0)
        is_suspended = data.get('is_suspended', False)
        station_name = data.get('station_name', '')
        
        # 1. RAG 歷史搜尋
        context_block = "暫無歷史相關紀錄。"
        sources_summary = "歷史災害資料庫"
        if pinecone_index:
            try:
                query_vector = get_embedding(query)
                search_results = pinecone_index.query(vector=query_vector, top_k=3, include_metadata=True)
                ctx = []
                for m in search_results['matches']:
                    meta = m['metadata']
                    ctx.append(f"- 事件: {meta.get('situation')}\n  處置: {meta.get('solution')}")
                context_block = "\n".join(ctx)
            except: pass

        # 2. 獲取轉乘與接駁指標
        shuttle = get_shuttle_metrics(station_name)
        official_info = get_official_transfers(station_name)

        # 3. 呼叫 GPT
        prompt = f"""你現在是「台鐵智慧行程助理」。目前的狀況是：「{query}」。
車站：{station_name}，延誤：{delay_time} 分鐘。

【參考歷史資料】：
{context_block}

【官方轉乘資訊】：
{official_info}

【輸出格式要求】：
請以 JSON 格式回答：
1. "summary": 15字內總結。
2. "ai_advice": 內容豐富且有同理心的建議（包含安全提醒）。
3. "routes": 轉乘路徑清單（包含公車、客運等）。
4. "emergency": 僅在嚴重災害時顯示警告。
5. "nav_dest": 推薦導航位址。
"""
        if not client: raise Exception("OpenAI API 未初始化")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        res_json = json.loads(response.choices[0].message.content)
        
        # --- 絕對修復：注入計程車與 U-bike ---
        routes = res_json.get("routes", [])
        
        # 強制計程車
        taxi_item = {
            "type": "taxi",
            "title": f"計程車 (至{shuttle['target']})",
            "departure": f"距離約 {shuttle['distance']}km",
            "duration": f"預估車資 NT$ {shuttle['taxi_fare']}",
            "priority": "建議"
        }
        # 移除重複
        routes = [r for r in routes if "計程車" not in r.get("title", "") and r.get("type") != "taxi"]
        routes.insert(0, taxi_item)
        
        # 加入 U-bike
        if shuttle['show_ubike']:
            routes.append({
                "type": "u-bike", "title": "公共自行車 (U-bike)", "departure": "站前設有站點",
                "duration": "距離市區近，建議騎乘", "priority": "建議"
            })
            
        res_json["routes"] = routes[:5]
        res_json["sources"] = sources_summary

        return jsonify({"structured": res_json, "is_serious": delay_time >= 20 or is_suspended})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"structured": {"summary": "連線異常", "ai_advice": "系統暫時忙碌中，請依站務人員指示。"}, "is_serious": False})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
