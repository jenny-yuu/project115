import sys
import os
import json

sys.path.append(r"c:\Users\jenny\OneDrive\桌面\115 專題")
from app_bridge import app, ask_ai

client = app.test_client()
# Simulate a POST request with the same body the Android app sends
response = client.post('/ask_ai', json={
    'query': '目前人在關山，遇到延誤，天氣陰，溫度21°C。',
    'delay_time': 1,
    'is_suspended': False,
    'station_name': '關山'
})
print("STATUS CODE:", response.status_code)
print("JSON DATA:")
print(json.dumps(response.get_json(), indent=2, ensure_ascii=False))
