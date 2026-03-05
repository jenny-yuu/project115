import os
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

def test_rag(query, delay_time):
    print(f"\n💬 【測試提問】：{query}")
    print(f"⏰ 【延誤時間】：{delay_time} 分鐘")
    
    query_vector = get_embedding(query)
    search_results = index.query(
        vector=query_vector,
        top_k=3,
        include_metadata=True
    )
    
    context_texts = []
    print("🔍 【檢索到的參考資料】：")
    for match in search_results['matches']:
        meta = match['metadata']
        cat = meta.get('category', '未知')
        if cat == "自然災害-颱風":
            info = f"[颱風歷史] 名稱: {meta.get('name')}, 時間: {meta.get('start_time')}"
        elif cat == "自然災害-雨量紀錄":
            info = f"[雨量紀錄] 測站: {meta.get('station_no')}, 颱風: {meta.get('name')}"
        elif cat == "自然災害-地震":
            info = f"[地震歷史] 規模: {meta.get('magnitude')}, 時間: {meta.get('time')}"
        else:
            info = f"[事故歷史] 地點: {meta.get('location')}, 狀況: {meta.get('situation')}"
        
        print(f"  - {info}")
        solution = meta.get('solution', '按照氣象預報及災防規定停駛或慢行。')
        context_texts.append(f"{info}\n歷史應變建議: {solution}")
        
    context_block = "\n\n".join(context_texts)
    
    prompt = f"""
你是一個受過專業訓練的「台鐵智慧行程助理」。
現在有颱風或強降雨災情："{query}"。延誤時間已達 {delay_time} 分鐘。
請參考以下歷史事故或災情紀錄，給予乘客具體的行程應變建議（如轉乘、退票等在地化建議）：

【參考歷史資料】：
{context_block}

請以繁體中文回答，預測恢復難度並建議乘客該如何轉乘。
"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    
    print("\n🤖 【AI 建議內容】：")
    print(response.choices[0].message.content)

if __name__ == "__main__":
    test_rag("我是乘客，人在台北。目前凱米颱風登陸，北迴線聽說多處坍方，我的車延誤了 15 分鐘，我該等嗎？還是去搭客運？", 15)
