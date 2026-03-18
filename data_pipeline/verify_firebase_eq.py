import firebase_admin
from firebase_admin import credentials, firestore
import os

CREDENTIAL_PATH = "your-firebase-adminsdk.json"

def check():
    if not firebase_admin._apps:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    doc = db.collection("stations").document("7330").get()
    if doc.exists:
        data = doc.to_dict()
        eq = data.get("earthquake")
        print(f"Station: {data.get('StationName')}")
        print(f"Earthquake: {eq}")
    else:
        print("Document not found")

if __name__ == "__main__":
    check()
