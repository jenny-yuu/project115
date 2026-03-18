import os
import openai
from dotenv import load_dotenv
from pinecone import Pinecone

# 載入環境變數 (API Keys)
env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
if not os.path.exists(env_path):
    env_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\.env"
load_dotenv(dotenv_path=env_path)

# 初始化 OpenAI 與 Pinecone
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("disaster-rag")

def get_embedding(text):
    """將使用者的提問轉換成向量"""
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def get_rag_recommendation(query):
    print(f"\n💬 【收到的災情通報】：{query}")
    print("⏳ 正在大腦中搜尋最相關的歷史 SOP 與類似事故...\n")
    
    # 1. 將通報文字轉成向量
    query_vector = get_embedding(query)
    
    # 2. 去 Pinecone 尋找最相近的 Top-5 歷史資料
    search_results = index.query(
        vector=query_vector,
        top_k=5,
        include_metadata=True
    )
    
    # 3. 整理找出來的歷史資料 (Context)
    context_texts = []
    print("🔍 【大腦檢索到的參考資料】：")
    for i, match in enumerate(search_results['matches']):
        meta = match['metadata']
        score = match['score']
        source = meta.get('source', '未知來源')
        
        if source == "cwa_earthquake_history":
            info = f"[地震] 發生時間: {meta.get('time')}, 規模: {meta.get('magnitude')}"
        else:
            info = f"[台鐵事故] 時間: {meta.get('time')}, 地點: {meta.get('location')}, 狀況: {meta.get('situation')}"
            
        solution = meta.get('solution', '無特定解法')
        context_texts.append(f"{info}\n-> 歷史應變對策: {solution}")
        print(f"  {i+1}. (信心度: {score:.2f}) {info}")
        
    context_block = "\n\n".join(context_texts)
    
    # 4. 把資料餵給 GPT-4o-mini 進行總結
    prompt = f"""
你是一個專為「台鐵乘客」設計的「智慧行程與延誤預測 AI 助手」。
請根據下方【歷史類似事故參考資料】，分析目前發生的即時災情，並提供一般乘客：
1. 預測可能的「停駛恢復時間」或「潛在延誤長度」（請參考歷史資料中類似事故所花費的處理時間或嚴重程度來推算出一個可能的時間範圍，若有困難也請從嚴重程度解釋）。
2. 給乘客的「行程轉乘或應變建議」（例如：在花蓮可以改搭哪種客運、是否建議退換票、接駁車等具體且適用的台灣在地建議）。
如果參考資料中沒有明確解答，請運用你的台灣交通地理常識補充，但必須優先基於歷史事實來推斷恢復難度。

【歷史類似事故參考資料】：
{context_block}

【目前即時災情通報（乘客視角）】：
{query}

請提供給「一般旅客」即時延誤預測與行程替代建議（請使用繁體中文，語意清晰且具有安撫效果）：
"""
    print("\n🧠 正在呼叫 GPT-4o-mini 預測延誤時間及規劃行程...\n")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是溫暖且專業的台鐵 AI 旅運顧問，擅長分析災情並預測延誤時間，給予乘客最佳轉乘建議。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4 # 保留一點點彈性，讓建議更有人性
    )
    
    return response.choices[0].message.content

if __name__ == "__main__":
    # 這裡就是未來 Android APP 傳過來的字串！
    test_scenario = "我是乘客，目前人在花蓮站。剛剛發生規模 6.0 地震，聽說吉安那邊有落石，原本要搭回台北的自強號停駛了。請問大概會延誤多久？我該怎麼辦？"
    
    answer = get_rag_recommendation(test_scenario)
    
    print("==================================================")
    print("🤖 【AI 應變中心指示】：")
    print(answer)
    print("==================================================")
