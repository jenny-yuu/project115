import os
import time
import schedule

# 匯入我們寫好的兩個更新腳本 (不需要加 .py)
import update_live_delay_to_firebase
import update_weather_to_firebase

def job_update_delay():
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 🚂 開始更新【台鐵即時誤點】資料...")
        # 建立共用 DB 連線
        db = update_live_delay_to_firebase.init_firebase()
        # 抓取並更新
        data = update_live_delay_to_firebase.fetch_live_delay()
        update_live_delay_to_firebase.update_firebase_delay(db, data)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ 誤點資料更新完畢！")
    except Exception as e:
        print(f"❌ 誤點更新發生錯誤: {e}")

def job_update_weather():
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] ⛅ 開始更新【氣象署即時天氣與雨量】資料...")
        # 建立共用 DB 連線
        db = update_weather_to_firebase.init_firebase()
        # 抓取並更新
        update_weather_to_firebase.update_firebase_weather(db)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ✅ 天氣資料更新完畢！")
    except Exception as e:
         print(f"❌ 天氣更新發生錯誤: {e}")

if __name__ == "__main__":
    print("========================================")
    print("🚀 台鐵東部幹線 App - 背景資料更新程式啟動")
    print("========================================")
    
    # 程式一啟動先強制執行一次
    job_update_delay()
    job_update_weather()
    
    # 設定排程 (Schedule)
    # 台鐵誤點狀況變化快，我們設定每 2 分鐘更新一次
    schedule.every(2).minutes.do(job_update_delay)
    
    # 天氣觀測資料 (時雨量、風速) 大約每 10~15 分鐘氣象署才會有一筆新資料，我們設定每 10 分鐘更新一次
    schedule.every(10).minutes.do(job_update_weather)
    
    print("\n⏳ 進入自動排程模式... 請保持此視窗開啟 (按 Ctrl+C 可強制結束)\n")
    
    # 無窮迴圈，讓程式永遠活著並檢查時間是否到了
    while True:
        schedule.run_pending()
        time.sleep(1) # 每秒檢查一次
