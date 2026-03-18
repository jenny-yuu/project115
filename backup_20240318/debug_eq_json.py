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
        for k, v in records.items():
            if isinstance(v, list) and len(v) > 0:
                first = v[0]
                print(f"Keys in event: {list(first.keys())}")
                if "EarthquakeInfo" in first:
                    print(f"Keys in EarthquakeInfo: {list(first['EarthquakeInfo'].keys())}")
                    # Look for Intensity or Shaking
                    print(f"EarthquakeInfo content preview: {str(first['EarthquakeInfo'])[:500]}")
                print(f"Intensity info: {first.get('Intensity')}")
                return
    else:
        print(f"Error: {r.status_code}")

if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    check()
