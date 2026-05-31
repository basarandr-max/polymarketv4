import requests

# Farkli API endpoint dene
urls = [
    "https://gamma-api.polymarket.com/markets?slug=new-rhianna-album-before-gta-vi-926",
    "https://gamma-api.polymarket.com/markets?id=926",
    "https://gamma-api.polymarket.com/events?slug=what-will-happen-before-gta-vi",
]

for url in urls:
    try:
        resp = requests.get(url, timeout=10)
        print(f"\nURL: {url}")
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:300]}")
    except Exception as e:
        print(f"Hata: {e}")
