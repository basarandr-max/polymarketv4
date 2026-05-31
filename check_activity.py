import requests
import os
from dotenv import load_dotenv
load_dotenv()

# LaBradfordSmith22 aktivitesi
wallet = "0x9495425feeb0c250accb89275c97587011b19a27"
url = f"https://data-api.polymarket.com/activity?user={wallet}&limit=3&type=TRADE"
resp = requests.get(url, timeout=10)
data = resp.json()

if data:
    print("İlk işlemin alanları:")
    for key, val in data[0].items():
        print(f"  {key}: {str(val)[:80]}")
