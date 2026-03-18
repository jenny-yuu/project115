import requests
import json
import urllib3
urllib3.disable_warnings()

url = "https://rdc28.cwa.gov.tw/TDB/public/warning_typhoon_list/get_warning_typhoon"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}
data = {
    "year": "all"
}

print(f"Fetching data from {url}...")
try:
    response = requests.post(url, data=data, headers=headers, verify=False)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        try:
            content = response.text.lstrip('\ufeff')
            typhoon_list = json.loads(content)
            print(f"Successfully fetched {len(typhoon_list)} typhoon records.")
            
            # Save to local file
            filename = "historical_typhoons.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(typhoon_list, f, ensure_ascii=False, indent=4)
            print(f"Data saved to {filename}")
        except json.JSONDecodeError:
            print("Response is not JSON. Snippet:")
            print(response.text[:1000])
    else:
        print(f"Failed to fetch data. Status code: {response.status_code}")
        print("Response:", response.text[:1000])
except Exception as e:
    print(f"An error occurred: {e}")
