import traceback
import sys

sys.path.append(r"c:\Users\jenny\OneDrive\桌面\115 專題")
from app_bridge import app, ask_ai

with app.test_request_context('/ask_ai', method='POST', json={'query': '目前人在三民，遇到正常/延誤，天氣陰，溫度22°C。', 'delay_time': 4, 'is_suspended': False, 'station_name': '三民'}):
    try:
        ask_ai()
    except Exception as e:
        with open("error_out.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
