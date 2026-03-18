import os
import pandas as pd
import ast
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

# Load the API keys from .env file
# Load the API keys from .env file
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=env_path)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

try:
    if not PINECONE_API_KEY:
        # 嘗試從環境變數讀取 (Render 模式)
        PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY")
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY is not set.")
    pc = Pinecone(api_key=PINECONE_API_KEY)
except Exception as e:
    print(f"初始化 Pinecone 失敗: {e}")
    exit(1)

INDEX_NAME = "disaster-rag"
# 改為相對路徑，建議放在專案根目錄下
CSV_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "accidents_with_embeddings.csv")

def init_pinecone_index():
    print(f"正在檢查 Pinecone 中是否已經有名為 '{INDEX_NAME}' 的 Index...")
    try:
        existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]
        if INDEX_NAME not in existing_indexes:
            print(f"找不到 '{INDEX_NAME}'。正在為您建立一個新 Index (維度: 1536)...")
            pc.create_index(
                name=INDEX_NAME,
                dimension=1536, # OpenAI text-embedding-3-small 的固定維度
                metric='cosine',
                spec=ServerlessSpec(
                    cloud='aws',
                    region='us-east-1' # 免費版預設區域
                )
            )
            print("✅ Index 建立成功！")
        else:
            print(f"✅ 發現 '{INDEX_NAME}'！將直接使用現有的 Index。")
        return pc.Index(INDEX_NAME)
    except Exception as e:
        print(f"存取 Pinecone Index 時發生錯誤: {e}")
        exit(1)

def upload_vectors(index):
    print(f"準備讀取向量檔案: {CSV_FILE_PATH} ...")
    try:
        df = pd.read_csv(CSV_FILE_PATH)
    except FileNotFoundError:
        print(f"❌ 找不到檔案 {CSV_FILE_PATH}")
        return

    print(f"共有 {len(df)} 筆資料準備上傳...")
    
    batch_size = 50
    vectors_batch = []
    success_count = 0
    
    for i, row in df.iterrows():
        # 取出該有的 Metadata 資訊，讓 AI 之後可以根據這些資訊回答
        time = str(row.get('標準發生時間', '未知'))
        location = str(row.get('發生地點', '未知'))
        cause_category = str(row.get('分類_原因', '未分類'))
        situation = str(row.get('事故(件)概況', ''))
        solution = str(row.get('改善對策', ''))
        
        # 把欄位格式化當作 ID
        doc_id = f"acc_{i}"
        
        # 取得文字型態的 List "[0.12, 0.44...]" 並還原成真正的 Python list
        emb_str = row.get('embedding')
        if pd.isna(emb_str) or not isinstance(emb_str, str):
            continue
            
        try:
            import json
            emb_list = json.loads(emb_str)
            
            metadata = {
                "time": time,
                "location": location,
                "category": cause_category,
                "situation": situation,
                "solution": solution,
                "source": "railway_history"
            }
            
            vectors_batch.append({
                "id": doc_id,
                "values": emb_list, # 高維度向量數據
                "metadata": metadata # 攜帶的實際內容
            })
            
            # 每累積 batch_size 筆資料，就批次上傳一次到 Pinecone
            if len(vectors_batch) >= batch_size:
                print(f"[{i}/{len(df)}] Sending batch of {len(vectors_batch)} to Pinecone...")
                index.upsert(vectors=vectors_batch)
                success_count += len(vectors_batch)
                vectors_batch = []
                
        except Exception as e:
            print(f"Error processing row {i}: {e}")
            
    # 上傳剩下不滿的碎塊資料
    if len(vectors_batch) > 0:
        print(f"Sending final batch of {len(vectors_batch)} to Pinecone...")
        index.upsert(vectors=vectors_batch)
        success_count += len(vectors_batch)
        
    print(f"\n🎉 太棒了！所有的向量資料都上傳完畢了！共成功傳送 {success_count} 筆。")

if __name__ == "__main__":
    idx = init_pinecone_index()
    upload_vectors(idx)
