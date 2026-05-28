#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import aiohttp
import time
import threading
import os
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List
import logging
import sys
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
load_dotenv()

class Config:
    TEST_MODE        = True
    INITIAL_CAPITAL  = Decimal('50')
    TRADE_SIZE       = Decimal('5')
    MIN_CASH         = Decimal('5')
    SCAN_INTERVAL    = 60
    MIN_USDC_SIZE    = Decimal('1')
    DATA_API  = "https://data-api.polymarket.com"
    TRACKED_USERS: List[Dict] = [
        {"name": "Oddn",              "wallet": "0xa53c26443fb636d8ae31ac24f62fc1d5ef8f67a5"},
        {"name": "Swisstony",         "wallet": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
        {"name": "LaBradfordSmith22", "wallet": "0x9495425feeb0c250accb89275c97587011b19a27"},
        {"name": "Mosley1",           "wallet": "0x5bec79df9add70a3892041ab1a5516b60f53b215"},
        {"name": "wan123",            "wallet": "0xde7be6d489bce070a959e0cb813128ae659b5f4b"},
        {"name": "Tiger200",          "wallet": "0x6211f97a76ed5c4b1d658f637041ac5f293db89e"},
    ]

@dataclass
class Position:
    position_id: str
    trader_name: str
    market_title: str
    side: str
    entry_price: Decimal
    size_usd: Decimal
    opened_at: datetime = field(default_factory=datetime.now)

@dataclass
class Portfolio:
    initial_capital: Decimal = field(default_factory=lambda: Config.INITIAL_CAPITAL)
    cash: Decimal = field(default_factory=lambda: Config.INITIAL_CAPITAL)
    realized_pnl: Decimal = field(default_factory=Decimal)
    open_positions: Dict[str, Position] = field(default_factory=dict)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    @property
    def open_value(self): return sum(p.size_usd for p in self.open_positions.values())
    @property
    def total_value(self): return self.cash + self.open_value
    @property
    def total_pnl(self): return self.total_value - self.initial_capital
    @property
    def pnl_percent(self):
        if self.initial_capital == 0: return Decimal('0')
        return (self.total_pnl / self.initial_capital) * 100

app_state = {
    "running": False,
    "scan_count": 0,
    "portfolio": Portfolio(),
    "trade_history": [],
    "tracked_users": list(Config.TRACKED_USERS),
}

class TelegramNotifier:
    def __init__(self):
        self.token   = os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(); return self
    async def __aexit__(self, *_):
        if self.session: await self.session.close()

    async def send(self, msg: str):
        if not self.token or not self.chat_id:
            logging.warning("Token veya Chat ID eksik!")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with self.session.post(url, json={
                "chat_id": self.chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logging.info("Telegram mesaji gonderildi!")
                else:
                    result = await resp.json()
                    logging.warning(f"Telegram {resp.status}: {result}")
        except Exception as e:
            logging.error(f"Telegram hatasi: {e}")

class UserTracker:
    def __init__(self, users):
        self.users = users
        self.session = None
        self.last_req = 0
        self.seen_tx = {u["wallet"]: set() for u in users}
        self.initialized = {u["wallet"]: False for u in users}

    async def _get(self, url):
        now = time.time()
        wait = 0.5 - (now - self.last_req)
        if wait > 0: await asyncio.sleep(wait)
        self.last_req = time.time()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as e:
            logging.debug(f"Request error: {e}"); return None

    async def get_new_trades(self, user):
        w = user["wallet"]
        url = f"{Config.DATA_API}/activity?user={w}&limit=50&type=TRADE"
        data = await self._get(url)
        if not data or not isinstance(data, list): return []
        new = []
        for act in data:
            tx = act.get("transactionHash", "")
            if not tx: continue
            if not self.initialized[w]:
                self.seen_tx[w].add(tx); continue
            if tx in self.seen_tx[w]: continue
            self.seen_tx[w].add(tx)
            try:
                size = Decimal(str(act.get("usdcSize", "0")))
            except:
                size = Decimal("0")
            if size < Config.MIN_USDC_SIZE: continue
            act["tracked_user"] = user["name"]
            act["tracked_wallet"] = w
            new.append(act)
        if not self.initialized[w]:
            self.initialized[w] = True
            logging.info(f"Init {user['name']}: {len(self.seen_tx[w])} tx cache")
        return new

    async def scan_all(self):
        trades = []
        for u in list(self.users): trades.extend(await self.get_new_trades(u))
        return trades

async def run_bot():
    app_state["running"] = True
    portfolio = app_state["portfolio"]

    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"BOT v4.0 BASLADI\n"
            f"Kapital: ${Config.INITIAL_CAPITAL} | Trade: ${Config.TRADE_SIZE}\n"
            f"Trader sayisi: {len(app_state['tracked_users'])}"
        )

    tracker = UserTracker(list(app_state["tracked_users"]))

    while app_state["running"]:
        app_state["scan_count"] += 1
        try:
            async with aiohttp.ClientSession() as sess:
                tracker.session = sess
                trades = await tracker.scan_all()

            async with TelegramNotifier() as notifier:
                for act in trades:
                    side = act.get("side", "").upper()
                    name = act.get("tracked_user", "?")
                    title = str(act.get("title", act.get("question", "Bilinmiyor")))[:60]
                    try:
                        price = Decimal(str(act.get("price", "0.5")))
                        price = min(max(price, Decimal("0.01")), Decimal("0.99"))
                    except:
                        price = Decimal("0.5")

                    if side == "BUY":
                        await notifier.send(
                            f"YENİ İŞLEM\n\n"
                            f"Trader: *{name}*\n"
                            f"Market: {title}\n"
                            f"Yön: *YES* (BUY)\n"
                            f"Fiyat: ${price:.3f}"
                        )
                    elif side == "SELL":
                        await notifier.send(
                            f"İŞLEM KAPANDI\n\n"
                            f"Trader: *{name}*\n"
                            f"Market: {title}\n"
                            f"Fiyat: ${price:.3f}"
                        )

        except Exception as e:
            logging.error(f"Scan hatasi: {e}")

        await asyncio.sleep(Config.SCAN_INTERVAL)

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except Exception as e:
        logging.error(f"Bot hatasi: {e}")
        app_state["running"] = False
    finally:
        loop.close()

flask_app = Flask(__name__, static_folder=".")

@flask_app.route("/")
def index():
    return send_from_directory(".", "index.html")

@flask_app.route("/api/status")
def status():
    p = app_state["portfolio"]
    return jsonify({
        "running": app_state["running"],
        "scan_count": app_state["scan_count"],
        "test_mode": Config.TEST_MODE,
        "portfolio": {
            "initial_capital": float(p.initial_capital),
            "cash": float(p.cash),
            "open_value": float(p.open_value),
            "total_value": float(p.total_value),
            "total_pnl": float(p.total_pnl),
            "pnl_percent": float(p.pnl_percent),
            "total_trades": p.total_trades,
            "winning_trades": p.winning_trades,
            "losing_trades": p.losing_trades,
            "win_rate": round((p.winning_trades / p.total_trades * 100) if p.total_trades > 0 else 0, 1),
            "open_positions": [],
        },
        "tracked_users": app_state["tracked_users"],
    })

@flask_app.route("/api/history")
def history():
    return jsonify(app_state["trade_history"])

@flask_app.route("/api/start", methods=["POST"])
def start():
    if app_state["running"]:
        return jsonify({"ok": False, "msg": "Bot zaten calisiyor"})
    t = threading.Thread(target=start_bot_thread, daemon=True)
    t.start()
    return jsonify({"ok": True, "msg": "Bot baslatildi"})

@flask_app.route("/api/stop", methods=["POST"])
def stop():
    app_state["running"] = False
    return jsonify({"ok": True, "msg": "Bot durduruldu"})

@flask_app.route("/api/traders", methods=["POST"])
def add_trader():
    data = request.json or {}
    name = data.get("name", "").strip()
    wallet = data.get("wallet", "").strip().lower()
    if not name or not wallet:
        return jsonify({"ok": False, "msg": "Isim ve cuzdan gerekli"})
    app_state["tracked_users"].append({"name": name, "wallet": wallet})
    return jsonify({"ok": True, "msg": f"{name} eklendi"})

@flask_app.route("/api/traders/<wallet>", methods=["DELETE"])
def del_trader(wallet):
    app_state["tracked_users"] = [u for u in app_state["tracked_users"] if u["wallet"] != wallet]
    return jsonify({"ok": True, "msg": "Trader silindi"})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
    print("=" * 50)
    print("  POLYMARKET BOT v4.0")
    print(f"  Token: {'OK' if os.environ.get('TELEGRAM_TOKEN') else 'EKSIK'}")
    print(f"  Chat ID: {'OK' if os.environ.get('TELEGRAM_CHAT_ID') else 'EKSIK'}")
    print("=" * 50)
    # Railway'de otomatik başlat
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        t = threading.Thread(target=start_bot_thread, daemon=True)
        t.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)
