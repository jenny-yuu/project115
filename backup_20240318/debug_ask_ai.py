import os
import json
import openai
import requests
from dotenv import load_dotenv

env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
load_dotenv(dotenv_path=env_path)

# Mock Flask request for testing
class MockRequest:
    def __init__(self, data):
        self.json = data

# Import or Copy the logic from app_bridge.py
from app_bridge import get_embedding, pinecone_index, get_tdx_token, search_bus_info, get_nearby_bus_schedules, format_bus_schedules, get_official_transfers, client

def test_ask_ai_logic(station_name):
    print(f"--- 測試邏輯: {station_name} ---")
    query = f"目前人在{station_name}，遇到延誤，天氣陰，溫度21°C。"
    
    try:
        print("1. RAG...")
        query_vector = get_embedding(query)
        search_results = pinecone_index.query(vector=query_vector, top_k=5, include_metadata=True)
        print(f"   RAG 找到 {len(search_results['matches'])} 筆")

        print("2. TDX & Web...")
        tdx_token = get_tdx_token()
        search_text = search_bus_info(station_name, "")
        
        bus_text = ""
        official_transfer_text = ""
        if tdx_token:
            bus_schedules = get_nearby_bus_schedules(station_name, tdx_token)
            bus_text = format_bus_schedules(bus_schedules)
            official_transfer_text = get_official_transfers(station_name, tdx_token)
        
        print("3. GPT-4o-mini...")
        prompt = f"狀況: {query}\nTDX: {official_transfer_text}\nBus: {bus_text}\nWeb: {search_text}\n格式: JSON"
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=800
        )
        print("✅ 成功回傳 JSON:")
        print(response.choices[0].message.content)

    except Exception as e:
        import traceback
        print(f"❌ 捕獲到異常: {e}")
        traceback.print_exc()

test_ask_ai_logic("關山")
