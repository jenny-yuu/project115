import os
import sys
import traceback

sys.path.append(r"c:\Users\jenny\OneDrive\桌面\115 專題")

from app_bridge import ask_ai, app

with app.test_request_context(json={'query': '目前人在三民，遇到正常/延誤，天氣陰，溫度22°C。', 'delay_time': 4, 'is_suspended': False, 'station_name': '三民'}):
    try:
        res = ask_ai()
        print(res.get_data(as_text=True))
    except Exception as e:
        traceback.print_exc()
