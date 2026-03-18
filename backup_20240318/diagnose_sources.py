import sys
import os
import json

sys.path.append(r"c:\Users\jenny\OneDrive\桌面\115 專題")
from app_bridge import app, ask_ai, get_tdx_token, get_nearby_bus_schedules, get_official_transfers, search_bus_info, db

def diagnose(station_name):
    print(f"--- 診斷車站: {station_name} ---")
    token = get_tdx_token()
    print(f"TDX Token: {'取得成功' if token else '失敗'}")
    
    # 官方資訊
    official = get_official_transfers(station_name, token)
    print(f"\n【官方轉乘資訊】:\n{official if official else '(空)'}")
    
    # 客運即時
    bus = get_nearby_bus_schedules(station_name, token)
    print(f"\n【客運班次】數量: {len(bus)}")
    for b in bus:
        print(f"  - {b['departure']} {b['route']} -> {b['destination']}")
        
    # 網頁搜尋
    search = search_bus_info(station_name)
    print(f"\n【網頁搜尋結果】:\n{search}")

diagnose("關山")
