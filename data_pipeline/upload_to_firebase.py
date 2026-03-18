import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import pandas as pd
import numpy as np

# =================設定區=================
# 1. 替換為您的 Firebase 服務帳號金鑰檔案名稱 (從 Firebase 主控台下載的 JSON 檔)
CREDENTIAL_PATH = "your-firebase-adminsdk.json" 

# 2. 替換為您要上傳的 CSV 檔案名稱 (這裡以您專題內的車站檔為例)
CSV_FILE_PATH = "tra_eastern_mainline_EL_stations.csv"

# 3. 選擇要在 Firestore 中建立的「集合 (Collection)」名稱
COLLECTION_NAME = "stations" 
# ========================================

def init_firebase():
    """初始化 Firebase 連線"""
    try:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase 初始化成功！")
        return db
    except FileNotFoundError:
        print(f"❌ 找不到金鑰檔案：{CREDENTIAL_PATH}")
        print("請確保您已從 Firebase 下載金鑰 JSON 檔，並放在與此程式碼相同的資料夾。")
        exit()
    except ValueError:
         print("Firebase 已經初始化過。")
         return firestore.client()
    except Exception as e:
        print(f"❌ Firebase 初始化失敗: {e}")
        exit()

def upload_data(db):
    """讀取 CSV 並上傳到 Firestore"""
    print(f"準備讀取 {CSV_FILE_PATH}...")
    try:
        df = pd.read_csv(CSV_FILE_PATH)
    except FileNotFoundError:
        print(f"❌ 找不到資料檔：{CSV_FILE_PATH}")
        return

    # 重要：Firestore 不支援 Pandas 的 NaN 值，必須轉為 None
    df = df.replace({np.nan: None})
    
    print(f"正在將資料上傳至 Firestore 集合：【{COLLECTION_NAME}】...")
    
    success_count = 0
    # 遍歷 DataFrame 每一行並上傳
    for index, row in df.iterrows():
        # 將 DataFrame 該列轉為 Python 字典
        data = row.to_dict()
        
        # 我們使用 StationID (例如：'0900') 作為 Firestore Document 的 ID
        # 這樣App尋找特定車站時會非常快！
        doc_id = str(data.get("StationID"))
        
        # 防呆機制：萬一沒有 StationID 則自編 ID
        if not doc_id or doc_id == "None":
             doc_id = f"auto_id_{index}"

        # 根據各路線車站劃分
        def get_route(station_name):
            yilan = ["八堵", "暖暖", "四腳亭", "瑞芳", "猴硐", "三貂嶺", "牡丹", "雙溪", "貢寮", "福隆", "石城", "大里", "大溪", "龜山", "外澳", "頭城", "頂埔", "礁溪", "四城", "宜蘭", "二結", "中里", "羅東", "冬山", "新馬", "蘇澳新", "蘇澳"]
            north = ["永樂", "東澳", "南澳", "武塔", "漢本", "和平", "和仁", "崇德", "新城", "景美", "北埔", "花蓮"]
            taitung = ["吉安", "志學", "平和", "壽豐", "豐田", "林榮新光", "南平", "鳳林", "萬榮", "光復", "大富", "富源", "瑞穗", "三民", "玉里", "東里", "東竹", "富里", "池上", "海端", "關山", "瑞和", "瑞源", "鹿野", "山里", "臺東"]
            
            # 使用 in 判斷確切名稱
            for name in yilan:
                if name in station_name: return "宜蘭線"
            for name in north:
                if name in station_name: return "北迴線"
            for name in taitung:
                if name in station_name: return "臺東線"
            return "東部幹線" # 預設或未知
            
        data["Route"] = get_route(str(data.get("StationName", "")))

        try:
            # 寫入 Firestore: Collection -> Document -> Data (使用 merge=True 避免覆蓋其他欄位)
            db.collection(COLLECTION_NAME).document(doc_id).set(data, merge=True)
            success_count += 1
            
            # 每上傳 10 筆印出一次進度
            if success_count % 10 == 0:
                print(f"已上傳 {success_count} / {len(df)} 筆...")
                
        except Exception as e:
            print(f"上傳 StationID: {doc_id} 時發生錯誤: {e}")
            
    print(f"\n🎉 恭喜！資料上傳完成，總共成功上傳了 {success_count} 筆車站資料！")
    print("現在您可以打開 Firebase 主控台 (Firestore Database 分頁) 檢查看看了！")

if __name__ == "__main__":
    db = init_firebase()
    upload_data(db)
