# (Same content as app_bridge.py above)
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import traceback
import requests
from openai import OpenAI
from pinecone import Pinecone

# ─────────────── 設定區 ───────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATHS = {
    "RESEARCH_DIR": r"C:\Users\jenny\OneDrive\桌面\115 專題",
    "PROJECT_DIR": r"D:\Android_Project\project115",
    "BACKEND_scripts": r"D:\Android_Project\project115\backend_scripts"
}

app = Flask(__name__)
CORS(app)

# 初始化 API Clients
client = None
pc = None
pinecone_index = None

try:
    openai_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=openai_key)
    
    pinecone_key = os.getenv("PINECONE_API_KEY")
    if pinecone_key:
        pc = Pinecone(api_key=pinecone_key)
        pinecone_index = pc.Index("disaster-rag")
        print("✅ OpenAI 與 Pinecone 初始化成功")
    else:
        print("⚠️ 未偵測到 PINECONE_API_KEY，RAG 功能將受限")
except Exception as e:
    print(f"❌ 初始化 API Clients 失敗: {e}")

# 載入車站里程資料 (用於計算計程車資)
STATION_DISTANCES = {}
try:
    # 在 D 槽執行時優先檢查本地目錄
    csv_path = os.path.join(BASE_DIR, "tra_eastern_mainline_EL_stations.csv")
    if not os.path.exists(csv_path):
        csv_path = r"D:\Android_Project\project115\tra_eastern_mainline_EL_stations.csv"
        
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
    """估算到鄰近車站與主要轉運站的計程車資"""
    if not station_name: return ""
    
    # 支援模糊匹配（處理 瑞芳 vs 瑞芳車站）
    clean_name = station_name.replace("車站", "").replace("臺", "台")
    target_key = next((k for k in STATION_DISTANCES.keys() if clean_name in k.replace("臺", "台")), None)
    
    if not target_key:
        print(f"⚠️ 計程車資估算跳過：找不到車站 '{station_name}'")
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
            if abs(STATION_DISTANCES[hub] - STATION_DISTANCES[target_key]) <= 30:
                targets.append(hub)
    
    import math
    for t in targets:
        dist = abs(STATION_DISTANCES[t] - STATION_DISTANCES[target_key])
        # 費率：1.25km(85元) + 每200m(5元)
        fare = 85 + (math.ceil((dist - 1.25) / 0.2) * 5 if dist > 1.25 else 0)
        notes.append(f"至 {t} 約 {dist:.1f}km / 估計車資 {int(fare)} 元")
    
    print(f"✅ 生成計程車資估算 ({target_key}): {len(notes)} 筆建議")
    return "\n".join(notes) if notes else ""

# ─────────────── 轉乘邏輯 ───────────────

def get_station_id(name: str) -> str:
    # 優先檢查當前目錄下的 fb_stations.json
    path = os.path.join(BASE_DIR, "fb_stations.json")
    if not os.path.exists(path):
        path = r"D:\Android_Project\project115\fb_stations.json"
    if not os.path.exists(path): return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for s in data:
                if name in s['Name']: return str(s['ID'])
    except: pass
    return None

def get_official_transfers(station_name: str, token: str) -> str:
    """整合 Firebase (Cloud), D 槽 (Project), OneDrive (Research) 的多方轉乘資料"""
    if not station_name: return ""
    
    output = []
    mapping = {"taxi": "計程車", "bus": "公路運輸/公車", "rail": "軌道運輸/火車", "bike": "公共自行車"}
    sid = get_station_id(station_name)
    fare_note = get_taxi_fare_str(station_name)

    # 1. 【最強優先】Firebase Cloud 資料
    
    # 2. 【二級優先】Local scraped_transfers.json
    try:
        scraped_path = os.path.join(BASE_DIR, "scraped_transfers.json")
        if not os.path.exists(scraped_path):
            scraped_path = r"D:\Android_Project\project115\scraped_transfers.json"
            
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
                    if output: return "\n\n".join(output)
    except: pass

    # 3. 【三級優先】StationTransfer.json
    try:
        research_path = r"D:\Android_Project\project115\StationTransfer.json"
        if not os.path.exists(research_path):
            research_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\StationTransfer.json"
            
        if os.path.exists(research_path):
            with open(research_path, 'r', encoding='utf-8') as f:
                static_data = json.loads(f.read()).get('StationTransfers', [])
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
                        if output: return "\n\n".join(output)
    except: pass

    if output: return "\n\n".join(output)
    return "（查無官方轉乘資料，建議查詢網路搜尋結果）"

# ─────────────── API 路由 ───────────────

@app.route('/')
def index():
    return f"台鐵智慧行程助理後端已啟動！[VERSION 5.0-PROOF] (API 正常運作中)"

@app.route('/debug', methods=['GET'])
def debug_version():
    return jsonify({"version": "v5-SYNC-PROOF", "status": "online", "file": __file__})

@app.route('/ask_ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        if not data: return jsonify({"error": "empty request"}), 400
        
        query = data.get('query', '')
        delay_time = data.get('delay_time', 0)
        is_suspended = data.get('is_suspended', False)
        station_name = data.get('station_name', '')
        sim_type = data.get('sim_type', '')
        sim_intensity = data.get('sim_intensity', 0)
        
        # 1. 取得背景資料 (RAG)
        context_block = "（目前無歷史案例參考）"
        if client and pinecone_index:
            try:
                emb_res = client.embeddings.create(input=query, model="text-embedding-3-small")
                vec = emb_res.data[0].embedding
                search_results = pinecone_index.query(vector=vec, top_k=3, include_metadata=True)
                if search_results.matches:
                    context_block = "\n".join([f"案列: {m.metadata.get('situation','')}\n處置: {m.metadata.get('solution','')}" for m in search_results.matches])
            except: pass

        # 2. 取得轉乘資訊
        fare_note = get_taxi_fare_str(station_name)
        official_transfer_text = get_official_transfers(station_name, None)

        # 3. 判定狀態與設定 Prompt
        is_earthquake = "地震" in query or (sim_type == "地震" and sim_intensity >= 3)
        if is_suspended:
            situation_desc = f"模擬災害：{sim_type}"
            focus = "列車停駛，推薦替代交通工具。"
        else:
            situation_desc = f"列車延誤 {delay_time} 分鐘" if delay_time > 0 else "目前正常"
            focus = f"狀態：{situation_desc}。僅基於轉乘資訊提供建議。"
        
        prompt = f"""
你現在是台鐵智慧行程助理。目前狀況：{query}
{focus}
【歷史資料】: {context_block}
【官方轉乘】: {official_transfer_text}
輸出格式：JSON
1. "summary": 15字總結（請包含 [v5-SYNC-PROOF] 標籤）。
2. "ai_advice": 60字建議。
3. "routes": 建議列表（type, title, departure, duration, priority）。
即使沒地震也請勿提到避難。
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        structured_data = json.loads(response.choices[0].message.content)
        
        # --- 強制注入與驗證 ---
        structured_data["summary"] = f"[v5-SYNC-PROOF] {structured_data.get('summary', '')}"
        
        if fare_note and "routes" in structured_data:
            for r in structured_data["routes"]:
                if "計程車" in r.get("title", ""):
                    r["duration"] = fare_note.split("\n")[0]
                    r["title"] = f"{r.get('title')} (包含車資)"

        return jsonify({
            "structured": structured_data,
            "is_serious": is_suspended or delay_time >= 20
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
