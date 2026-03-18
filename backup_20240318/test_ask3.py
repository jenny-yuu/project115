import sys
import traceback
import json
sys.path.append(r"c:\Users\jenny\OneDrive\æ¡Œé¢\115 å°ˆé?")
from app_bridge import app

def test():
    client = app.test_client()
    response = client.post('/ask_ai', json={
        'query': '?®å?äººåœ¨ä¸‰æ?ï¼Œé??°æ­£å¸?å»¶èª¤ï¼Œå¤©æ°?™°ï¼Œæº«åº?2Â°C??,
        'delay_time': 4,
        'is_suspended': False,
        'station_name': 'ä¸‰æ?'
    })
    print(response.get_json())

test()

