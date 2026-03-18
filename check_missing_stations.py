import os
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

CREDENTIAL_PATH = r"C:\Users\jenny\OneDrive\桌面\115 專題\your-firebase-adminsdk.json" 
COLLECTION_NAME = "stations" 

def check_firebase():
    cred = credentials.Certificate(CREDENTIAL_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    docs = db.collection(COLLECTION_NAME).stream()
    
    missing = []
    has_transfers = []
    
    for doc in docs:
        data = doc.to_dict()
        sname = data.get('StationName', '')
        if 'transfers' in data:
            has_transfers.append(sname)
        else:
            missing.append(sname)

    output_data = {
        "HasTransfersCount": len(has_transfers),
        "HasTransfers": has_transfers,
        "MissingTransfersCount": len(missing),
        "MissingTransfers": missing
    }
    
    with open('missing.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    check_firebase()
