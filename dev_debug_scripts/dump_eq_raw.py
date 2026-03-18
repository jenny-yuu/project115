import requests
import json
import os

CWA_KEY = "CWA-6DCD2E73-0932-4887-BF32-5D8190D54AF3"
EQ_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"

def check():
    headers = {"Authorization": CWA_KEY, "Accept": "application/json"}
    r = requests.get(EQ_URL, params={"format": "JSON"}, headers=headers, timeout=60, verify=False)
    if r.status_code == 200:
        with open("eq_raw_debug.json", "w", encoding="utf-8") as f:
            json.dump(r.json(), f, indent=2, ensure_ascii=False)
        print("Raw JSON dumped to eq_raw_debug.json")
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    check()
