import os
import json
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from dotenv import load_dotenv

# Load environment variables
env_path = r"C:\Users\jenny\OneDrive\桌面\大專生計畫\.env"
if not os.path.exists(env_path):
    env_path = r"C:\Users\jenny\OneDrive\桌面\115 專題\.env"
load_dotenv(dotenv_path=env_path)

# Firebase setup
CREDENTIAL_PATH = r"C:\Users\jenny\OneDrive\桌面\115 專題\your-firebase-adminsdk.json"
COLLECTION_NAME = "stations"

def init_firebase():
    try:
        cred = credentials.Certificate(CREDENTIAL_PATH)
        firebase_admin.initialize_app(cred)
        return firestore.client()
    except ValueError:
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        exit()

def upload_scraped_data(db):
    json_path = r"d:\Android_Project\project115\scraped_transfers.json"
    if not os.path.exists(json_path):
        print(f"❌ File not found: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        scraped_data = json.load(f)

    print(f"Loaded data for {len(scraped_data)} stations.")

    # Get all stations from Firestore to match
    stations_ref = db.collection(COLLECTION_NAME)
    docs = stations_ref.stream()

    success_count = 0
    for doc in docs:
        details = doc.to_dict()
        # Firebase documents use StationID or ID. Let's find a match.
        station_id = str(details.get("StationID", doc.id))
        
        # Check if we have scraped data for this station
        if station_id in scraped_data:
            data = scraped_data[station_id]
            transfers = data.get("transfers", {})
            
            # Check if all categories are empty
            has_data = any(transfers.values())
            
            if not has_data:
                # For "empty" stations, we can provide a default message or handle in AI
                # We'll upload the empty structure so the field exists
                update_payload = {
                    "official_transfers": {
                        "status": "No official transfer data listed on TRA website.",
                        "data": transfers
                    }
                }
            else:
                update_payload = {
                    "official_transfers": {
                        "status": "Available",
                        "data": transfers
                    }
                }

            try:
                stations_ref.document(doc.id).update(update_payload)
                success_count += 1
                if success_count % 10 == 0:
                    print(f"Updated {success_count} stations...")
            except Exception as e:
                print(f"Failed to update station {station_id}: {e}")

    print(f"Successfully updated {success_count} stations in Firebase.")

if __name__ == "__main__":
    db = init_firebase()
    upload_scraped_data(db)
