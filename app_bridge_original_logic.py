# [v21-ORIGINAL-BACKUP] - TRA AI Travel Assistant Backend
# 這個檔案保留了 get_nearby_bus_schedules 最原始的 nearby() 調用邏輯
import os
import json
import openai
import requests
import traceback
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pinecone import Pinecone
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import re
import firebase_admin
from firebase_admin import credentials, firestore

# ... (其餘代碼與 app_bridge.py 相同)
# 這裡特別保留舊版的 get_nearby_bus_schedules

def get_nearby_bus_schedules(station_name: str, token: str) -> list:
    """[原始版本] 使用空間過濾 (Nearby) 查詢車站附近的公車預估到站時間 (ETA)"""
    if not token: return []
    try:
        # 1. 先從 TDX 取得車站座標
        url_sta = "https://tdx.transportdata.tw/api/basic/v3/Rail/TRA/Station?$format=JSON"
        headers = {"Authorization": f"Bearer {token}"}
        r_sta = requests.get(url_sta, headers=headers, timeout=10)
        stations = r_sta.json().get('Stations', [])
        sta = next((s for s in stations if station_name in s['StationName']['Zh_tw']), None)
        if not sta: return []
        lon, lat = sta['StationPosition']['PositionLon'], sta['StationPosition']['PositionLat']
        
        # 2. 同時查詢客運(InterCity)與市區公車(City)
        results = []
        spatial = f"nearby({lat},{lon},1000)"
        
        # 判斷縣市
        city = "TaitungCounty" if "台東" in station_name or any(x in station_name for x in ["關山", "池上", "鹿野", "太麻里"]) else "HualienCounty"
        
        urls = [
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/InterCity?$spatialFilter={spatial}&$format=JSON",
            f"https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/City/{city}?$spatialFilter={spatial}&$format=JSON"
        ]
        
        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    for b in r.json():
                        eta = b.get('EstimateTime')
                        if eta is not None:
                            results.append({
                                "route": b.get('RouteName', {}).get('Zh_tw'),
                                "destination": "附近站牌", 
                                "departure": f"{eta//60} 分鐘" if eta > 0 else "即將到站",
                                "company": b.get('StopName', {}).get('Zh_tw')
                            })
            except: pass
        return sorted(results, key=lambda x: x['departure'])[:5]
    except Exception as e:
        print(f"TDX Nearby 查詢失敗: {e}")
        return []

# ... (後續代碼省略，僅示意備份邏輯)
