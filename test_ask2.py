import sys
import traceback
import json
sys.path.append(r"c:\Users\jenny\OneDrive\桌面\115 專題")
from app_bridge import app

def test():
    client = app.test_client()
    response = client.post('/ask_ai', json={
        'query': '目前人在三民，遇到正常/延誤，天氣陰，溫度22°C。',
        'delay_time': 4,
        'is_suspended': False,
        'station_name': '三民'
    })
    print(response.get_json())

test()
