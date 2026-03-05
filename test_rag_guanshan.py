import os
import json
import openai
from pinecone import Pinecone
from dotenv import load_dotenv

env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
load_dotenv(dotenv_path=env_path)

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index("disaster-rag")

def test_rag(query):
    print(f"1. 生成 Embedding: {query}")
    res = client.embeddings.create(input=[query], model="text-embedding-3-small")
    vec = res.data[0].embedding
    
    print("2. 查詢 Pinecone...")
    results = pinecone_index.query(vector=vec, top_k=5, include_metadata=True)
    print(f"   找到 {len(results['matches'])} 筆資料")
    for m in results['matches']:
        print(f"   - {m['metadata'].get('category')}: {m['metadata'].get('location','')}")

test_rag("目前人在關山，遇到延誤，天氣陰，溫度21°C。")
