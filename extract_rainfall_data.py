import requests
import json
import urllib3
import time

urllib3.disable_warnings()

# Configuration
BASE_URL = "https://rdc28.cwa.gov.tw/TDB/public/precipitation_statistics/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://rdc28.cwa.gov.tw/TDB/public/precipitation_statistics/"
}

# Major stations in Taiwan
STATIONS = [
    "466920", # Taipei
    "467490", # Taichung
    "467440", # Kaohsiung
    "466940", # Keelung
    "467080", # Yilan
    "466990", # Hualien
    "467660", # Taitung
    "467570", # Hsinchu
    "467050"  # New Taipei (Banqiao)
]

def fetch_rainfall_for_typhoon(year, eng_name, typhoon_id):
    """Fetches rainfall stats for a specific typhoon."""
    # The API might expect a specific format for typhoon_name in rainfall query
    # Looking at subagent info: "2024GAEMI"
    typhoon_name_query = f"{year}{eng_name.upper()}"
    
    payload = {
        "stno[]": STATIONS,
        "rain_average": "1h",
        "accu_value": "0.1",
        "radio_typhoon_year": "typhoon_year",
        "typhoon_year": year,
        "typhoon_name": typhoon_name_query,
        "measure_type": "CWA"
    }
    
    print(f"  Fetching rainfall for {eng_name} ({year})...")
    try:
        response = requests.post(BASE_URL, data=payload, headers=HEADERS, verify=False)
        if response.status_code == 200:
            content = response.text.lstrip('\ufeff')
            return json.loads(content)
        else:
            print(f"    Failed (Status {response.status_code})")
            return []
    except Exception as e:
        print(f"    Error: {e}")
        return []

def main():
    # Load filtered typhoon list (2020-2024)
    with open("historical_typhoons.json", "r", encoding="utf-8") as f:
        all_typhoons = json.load(f)
    
    recent_typhoons = [t for t in all_typhoons if 2020 <= int(t['id'][:4]) <= 2024]
    print(f"Found {len(recent_typhoons)} typhoons from 2020 to 2024.")
    
    results = {}
    for t in recent_typhoons:
        year = t['id'][:4]
        eng_name = t['eng_name']
        typhoon_id = t['id']
        
        data = fetch_rainfall_for_typhoon(year, eng_name, typhoon_id)
        if data:
            results[typhoon_id] = {
                "name": t['cht_name'],
                "eng_name": eng_name,
                "rainfall_records": data
            }
        # Be nice to the server
        time.sleep(1)
        
    # Save the data
    output_file = "recent_typhoon_rainfall.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    
    print(f"\nSuccessfully saved rainfall data for {len(results)} typhoons to {output_file}")

if __name__ == "__main__":
    main()
