import requests
import json
import os

CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"

def print_keys(data, indent=0):
    if isinstance(data, dict):
        for k, v in data.items():
            print("  " * indent + str(k))
            if k in ["Intensity", "EarthquakeInfo", "Epicenter", "ShakingArea"]:
                 print_keys(v, indent + 1)
    elif isinstance(data, list) and len(data) > 0:
        print("  " * indent + "[List Item]")
        print_keys(data[0], indent + 1)

def check():
    headers = {"Authorization": CWA_KEY, "Accept": "application/json"}
    r = requests.get(EQ_URL, params={"format": "JSON"}, headers=headers, timeout=60, verify=False)
    if r.status_code == 200:
        data = r.json()
        records = data.get("records", {})
        for k, v in records.items():
            if isinstance(v, list) and len(v) > 0:
                print(f"Structure for key: {k}")
                print_keys(v[0])
                
                # Also print the value of common intensity candidates
                event = v[0]
                print("\nCandidate Values:")
                print(f"Intensity: {event.get('Intensity')}")
                if "EarthquakeInfo" in event:
                    print(f"Info -> Intensity: {event['EarthquakeInfo'].get('Intensity')}")
                return
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    check()
