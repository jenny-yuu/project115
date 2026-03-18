import os
import json
import openai
from dotenv import load_dotenv
from pinecone import Pinecone

# 載入環境變數
env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
load_dotenv(dotenv_path=env_path)

# 初始化 API 客戶端
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("disaster-rag")

def get_embedding(text):
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def ingest_historical_typhoons(file_path):
    print(f"Ingesting historical typhoons from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    batch_size = 50
    vectors_batch = []
    
    for i, item in enumerate(data):
        description = f"颱風名稱：{item.get('cht_name')} ({item.get('eng_name')})。海上警報開始時間：{item.get('sea_start_datetime')}。海上警報結束時間：{item.get('sea_end_datetime')}。強度：{item.get('max_intensity')}。最低氣壓：{item.get('min_pressure')} hPa。最大風速：{item.get('max_wind_speed')} m/s。警報發布次數：{item.get('warning_count')}。路徑分類：{item.get('official_path_category')}。"
        
        emb = get_embedding(description)
        doc_id = f"typhoon_{item.get('id')}_{i}"
        
        metadata = {
            "name": str(item.get('cht_name')),
            "category": "自然災害-颱風",
            "start_time": str(item.get('sea_start_datetime')),
            "end_time": str(item.get('sea_end_datetime')),
            "intensity": str(item.get('max_intensity')),
            "source": "historical_typhoons_json"
        }
        
        vectors_batch.append({
            "id": doc_id,
            "values": emb,
            "metadata": metadata
        })
        
        if len(vectors_batch) >= batch_size:
            print(f"Uploading batch of {len(vectors_batch)} typhoons...")
            index.upsert(vectors=vectors_batch)
            vectors_batch = []
            
    if vectors_batch:
        print(f"Uploading final batch of {len(vectors_batch)} typhoons...")
        index.upsert(vectors=vectors_batch)

def ingest_recent_rainfall(file_path):
    print(f"Ingesting recent rainfall data from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    batch_size = 20 # 降雨資料較碎，稍微縮小 batch 避免 API 過載
    vectors_batch = []
    
    # 根據 view_file 結果，這是一個字典，鍵是 ID
    for typhoon_id, info in data.items():
        name = info.get('name', '未知颱風')
        records = info.get('rainfall_records', [])
        
        # 由於雨量紀錄非常多，我們按測站分組或抽樣，否則 Embedding 會爆炸
        # 這裡我們按測站名稱與時間整合文字
        print(f"Processing {name} ({len(records)} records)...")
        
        # 為了效能與成本，我們將每個測站的紀錄整理在一起
        station_data = {}
        for r in records:
            st_name = r.get('typhoon_cht_name', name)
            st_no = r.get('stno', '未知測站')
            st_val = r.get('accu_value', '0')
            st_time = r.get('accu_end_time', '')
            
            key = (st_name, st_no)
            if key not in station_data:
                station_data[key] = []
            station_data[key].append(f"{st_time} 累積雨量 {st_val}mm")

        for (st_name, st_no), logs in station_data.items():
            # 取最末端或具代表性的數據即可，避免文字太長
            logs_summary = "；".join(logs[-3:]) # 只取最後三筆紀錄代表趨勢
            description = f"{st_name} 颱風期間，測站編號 {st_no} 的降雨紀錄彙整：{logs_summary}。"
            
            emb = get_embedding(description)
            doc_id = f"rain_{typhoon_id}_{st_no}"
            
            metadata = {
                "name": str(st_name),
                "category": "自然災害-雨量紀錄",
                "station_no": str(st_no),
                "source": "recent_typhoon_rainfall_json"
            }
            
            vectors_batch.append({
                "id": doc_id,
                "values": emb,
                "metadata": metadata
            })
            
            if len(vectors_batch) >= batch_size:
                print(f"Uploading batch of {len(vectors_batch)} rainfall records...")
                index.upsert(vectors=vectors_batch)
                vectors_batch = []
                
    if vectors_batch:
        print(f"Uploading final batch of {len(vectors_batch)} rainfall records...")
        index.upsert(vectors=vectors_batch)

if __name__ == "__main__":
    typhoons_path = r"D:\Android_Project\project115\historical_typhoons.json"
    rainfall_path = r"D:\Android_Project\project115\recent_typhoon_rainfall.json"
    
    if os.path.exists(typhoons_path):
        ingest_historical_typhoons(typhoons_path)
    
    if os.path.exists(rainfall_path):
        # 注意：降雨資料檔案很大且紀錄極多，只處理最近的一部分或進行彙整
        ingest_recent_rainfall(rainfall_path)
