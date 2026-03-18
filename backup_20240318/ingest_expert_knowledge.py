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

def ingest_expert_knowledge(file_path):
    print(f"🚀 Ingesting expert knowledge from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    vectors_batch = []
    
    for i, item in enumerate(data):
        # 建立豐富的描述，提高 RAG 命中率
        description = f"類型：{item.get('category')}。情境：{item.get('situation', '通用')}。地點：{item.get('location', '全線')}。描述：{item.get('description', '')}。處置建議：{item.get('solution', '巡查')}。預估恢復時間：{item.get('recovery_time', '評估中')}。來源：{item.get('source')}。"
        
        emb = get_embedding(description)
        doc_id = f"expert_{item.get('id')}_{i}"
        
        metadata = {
            "name": str(item.get('location', '官方SOP')),
            "category": str(item.get('category')),
            "situation": str(item.get('situation')),
            "solution": str(item.get('solution')),
            "recovery_time": str(item.get('recovery_time')),
            "source": str(item.get('source')),
            "type": "expert_guideline"
        }
        
        vectors_batch.append({
            "id": doc_id,
            "values": emb,
            "metadata": metadata
        })
        
    if vectors_batch:
        print(f"Uploading {len(vectors_batch)} expert rules to Pinecone...")
        index.upsert(vectors=vectors_batch)
        print("✅ Expert knowledge uploaded successfully!")

if __name__ == "__main__":
    knowledge_path = r"c:\Users\jenny\OneDrive\桌面\115 專題\expert_knowledge.json"
    if os.path.exists(knowledge_path):
        ingest_expert_knowledge(knowledge_path)
    else:
        print("❌ Expert knowledge file not found.")
