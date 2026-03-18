import requests
import json
import os

CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"

def check():
    headers = {"Authorization": CWA_KEY, "Accept": "application/json"}
    r = requests.get(EQ_URL, params={"format": "JSON"}, headers=headers, timeout=60, verify=False)
    if r.status_code == 200:
        data = r.json()
        records = data.get("records", {})
        print(f"Success: {data.get('success')}")
        for k, v in records.items():
            if isinstance(v, list) and len(v) > 0:
                print(f"Found {len(v)} events in key: {k}")
                # Print the first one's time and magnitude
                first = v[0]
                info = first.get("EarthquakeInfo", {}) or first.get("Epicenter", {})
                print(f"Latest Event: Time={first.get('OriginTime')}, Mag={info.get('EarthquakeMagnitude', {}).get('MagnitudeValue')}")
                return
        print("No earthquake events found in records.")
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    check()
