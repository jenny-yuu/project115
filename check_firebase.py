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
    count_with_transfers = 0
    total = 0
    results = []
    
    for doc in docs:
        total += 1
        data = doc.to_dict()
        if 'transfers' in data:
            count_with_transfers += 1
            results.append({
                "StationName": data.get('StationName'),
                "StationID": data.get('StationID'),
                "ExternalCount": len(data['transfers'].get('external', [])),
                "InternalCount": len(data['transfers'].get('internal', []))
            })

    output_data = {
        "Total": total,
        "TransfersCount": count_with_transfers,
        "Results": results
    }
    
    with open('result.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    check_firebase()
