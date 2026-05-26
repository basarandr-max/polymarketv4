# Polymarket Bot v4.0 — Kurulum Talimatları

## 1. Gereksinimler

Python 3.9+ yüklü olmalı. Kontrol etmek için:
```
python --version
```

## 2. Kütüphaneleri Yükle

```
pip install flask aiohttp
```

## 3. Telegram Token Ayarla

`bot.py` dosyasını aç, şu satırları bul ve kendi bilgilerini gir:

```python
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "BURAYA_TOKEN_GİR")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "BURAYA_CHAT_ID_GİR")
```

Token almak için: Telegram'da @BotFather → /newbot → token kopyala
Chat ID için: @userinfobot'a yaz, sana ID'ni verir

## 4. Botu Çalıştır

```
python bot.py
```

Terminalde şunu görmelisin:
```
==================================================
  POLYMARKET BOT v4.0
  Dashboard: http://localhost:5000
==================================================
```

## 5. Web Arayüzünü Aç

Tarayıcıda: http://localhost:5000

## 6. Gerçek Para Modu

Dashboard'da "Test Modu" toggle'ını kapat → Kaydet.
VEYA bot.py içinde:
```python
TEST_MODE = False
```

⚠️ Gerçek mod açıkken bot Telegram'a bildirim gönderir ama
Polymarket'te doğrudan işlem AÇMAZ (bu bot sadece copy-tracking yapıyor,
yani sen manuel kopyalıyorsun — bot seni bilgilendiriyor).

## Dosya Yapısı

```
polymarket-bot/
├── bot.py        ← Ana bot + Flask API
└── index.html    ← Web dashboard
```

## Sık Karşılaşılan Sorunlar

**Port 5000 meşgul:** bot.py sonundaki port numarasını değiştir (örn. 5001)
**Module not found:** pip install flask aiohttp
**Telegram bildirimi gelmiyor:** Token ve Chat ID'yi kontrol et
