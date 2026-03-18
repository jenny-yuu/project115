import requests
from bs4 import BeautifulSoup

def debug_scrape(station_id):
    url = f"https://tip.railway.gov.tw/tra-tip-web/tip/tip00H/tipH41/viewTransfer/{station_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    print(f"Fetching {url}...")
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    with open('debug_station.html', 'w', encoding='utf-8') as f:
        f.write(response.text)
    
    # Check for panel IDs
    ids = ["taxiPanel", "busPanel", "railPanel", "bikePanel"]
    for pid in ids:
        panel = soup.find('div', id=pid)
        print(f"Panel {pid}: {'Found' if panel else 'NOT Found'}")
        if panel:
            rows = panel.find_all('div', class_='row')
            print(f"  Rows in {pid}: {len(rows)}")

if __name__ == "__main__":
    debug_scrape(7360)
