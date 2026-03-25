import requests
from bs4 import BeautifulSoup
import json
import time
import os

def scrape_station_transfers(station_id):
    url = f"https://tip.railway.gov.tw/tra-tip-web/tip/tip00H/tipH41/viewTransfer/{station_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        print(f"Scraping station {station_id}...")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch {url}: {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Determine station name
        station_name_tag = soup.find('h2')
        station_name = station_name_tag.text.strip() if station_name_tag else f"Station {station_id}"
        
        transfers = {
            "taxi": [],
            "bus": [],
            "rail": [],
            "bike": []
        }
        
        # Mapping Chinese headers to our keys
        header_map = {
            "計程車": "taxi",
            "公路運輸": "bus",
            "軌道運輸": "rail",
            "公共自行車": "bike"
        }
        
        # Find based on the actual tab-pane structure seen in the HTML
        # Header text to key mapping
        transport_types = {
            "計程車": "taxi",
            "公路運輸": "bus",
            "軌道運輸": "rail",
            "公共自行車": "bike"
        }
        
        panes = soup.find_all('div', class_='tab-pane')
        for pane in panes:
            header = pane.find('h3')
            if not header: continue
            
            header_text = header.text.strip()
            key = None
            for ch_name, en_key in transport_types.items():
                if ch_name in header_text:
                    key = en_key
                    break
            
            if not key: continue
            
            content = []
            traffic_blocks = pane.find_all('div', class_='st-traffic-text')
            for block in traffic_blocks:
                title_tag = block.find('h4')
                title = title_tag.text.strip() if title_tag else "資訊"
                
                details = []
                # Check for address
                addr_li = block.find('ul', class_='offer-add')
                if addr_li:
                    details.append(addr_li.get_text(strip=True, separator=' '))
                
                # Check for description
                desc_ol = block.find('ol', class_='decimal')
                if desc_ol:
                    details.append(desc_ol.get_text(strip=True, separator=' '))
                
                if details:
                    content.append(f"{title}: " + " | ".join(details))
            
            transfers[key] = content
            
        return {
            "station_id": station_id,
            "station_name": station_name,
            "transfers": transfers
        }
        
    except Exception as e:
        print(f"Error scraping station {station_id}: {e}")
        return None

def main():
    # Load station IDs from fb_stations.json
    try:
        with open('fb_stations.json', 'r', encoding='utf-8') as f:
            stations = json.load(f)
    except FileNotFoundError:
        print("fb_stations.json not found.")
        return

    # Filter for Eastern Line / Relevant stations (e.g., ID >= 6000 or specific list)
    # For now, let's just do a subset to test, then expand
    target_ids = [s['ID'] for s in stations if s['ID'] >= 6000 or s['ID'] == 920 or (s['ID'] >= 7000 and s['ID'] <= 7390)]
    
    # Sort and remove duplicates
    target_ids = sorted(list(set(target_ids)))
    
    print(f"Found {len(target_ids)} target stations.")
    
    all_results = {}
    for sid in target_ids:
        data = scrape_station_transfers(sid)
        if data:
            all_results[str(sid)] = data
        time.sleep(1) # Be nice to the server
        
    with open('scraped_transfers.json', 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print(f"Scraping complete. Results saved to scraped_transfers.json")

if __name__ == "__main__":
    main()
