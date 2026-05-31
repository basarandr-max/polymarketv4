import requests
import os
from dotenv import load_dotenv
load_dotenv()

DEPOSIT = os.environ.get("DEPOSIT_WALLET", "")
print(f"Deposit wallet: {DEPOSIT}")

# Data API'den pozisyonları çek
url = f"https://data-api.polymarket.com/positions?user={DEPOSIT}&sizeThreshold=0"
resp = requests.get(url, timeout=10)
print(f"\nStatus: {resp.status_code}")
data = resp.json()
print(f"Pozisyon sayisi: {len(data) if isinstance(data, list) else 'N/A'}")
if isinstance(data, list):
    for p in data:
        print(f"  Market: {str(p.get('title',''))[:50]} | Size: {p.get('size')} | Value: {p.get('value')}")
else:
    print(data)
