#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYMARKET COPY TRADING BOT v5.0
- Trader takip et
- Otomatik BUY/SELL
- Telegram bildirimleri
- Portföy takibi
"""

import asyncio
import aiohttp
import time
import threading
import os
import logging
import sys
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIG ====================
class Config:
    # Polymarket
    CLOB_HOST     = "https://clob.polymarket.com"
    DATA_API      = "https://data-api.polymarket.com"
    CHAIN_ID      = 137
    FUNDER        = os.environ.get("WALLET_ADDRESS", "0x18766bb5568165Ea390d8D0197D657b0347e9965")
    PRIVATE_KEY   = os.environ.get("PRIVATE_KEY", "")

    # Telegram
    TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # Trading
    TRADE_SIZE    = Decimal('5')
    MIN_CASH      = Decimal('5')
    SCAN_INTERVAL = 60
    MIN_USDC_SIZE = Decimal('1')
    TEST_MODE     = os.environ.get("TEST_MODE", "true").lower() == "true"

    TRACKED_USERS: List[Dict] = [
        {"name": "Oddn",              "wallet": "0xa53c26443fb636d8ae31ac24f62fc1d5ef8f67a5"},
        {"name": "Swisstony",         "wallet": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
        {"name": "LaBradfordSmith22", "wallet": "0x9495425feeb0c250accb89275c97587011b19a27"},
        {"name": "Mosley1",           "wallet": "0x5bec79df9add70a3892041ab1a5516b60f53b215"},
        {"name": "wan123",            "wallet": "0xde7be6d489bce070a959e0cb813128ae659b5f4b"},
        {"name": "Tiger200",          "wallet": "0x6211f97a76ed5c4b1d658f637041ac5f293db89e"},
    ]

# ==================== POLYMARKET CLIENT ====================
class PolymarketClient:
    def __init__(self):
        self.client = None
        self._init_client()

    def _init_client(self):
        if not Config.PRIVATE_KEY:
            logging.warning("PRIVATE_KEY eksik - TEST modunda calisiyor")
            return
        try:
            from py_clob_client.client import ClobClient
            self.client = ClobClient(
                Config.CLOB_HOST,
                key=Config.PRIVATE_KEY,
                chain_id=Config.CHAIN_ID,
                signature_type=0,
                funder=Config.FUNDER,
            )
            # MetaMask EOA için allowance kontrolü
            try:
                self.client.update_balance_allowance()
                self.client.update_collateral_allowance()
                logging.info("Allowance ayarlandi!")
            except Exception as e:
                logging.warning(f"Allowance hatasi (normal olabilir): {e}")
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            logging.info("Polymarket CLOB baglantisi OK!")
        except Exception as e:
            logging.error(f"CLOB baglanti hatasi: {e}")
            self.client = None

    def get_clob_token_id(self, condition_id: str, outcome_index: int) -> Optional[str]:
        """Gamma API'den doğru CLOB token ID'sini al"""
        import requests
        try:
            url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data:
                return None
            market = data[0] if isinstance(data, list) else data
            clob_token_ids = market.get("clobTokenIds", "[]")
            if isinstance(clob_token_ids, str):
                import json
                clob_token_ids = json.loads(clob_token_ids)
            if len(clob_token_ids) > outcome_index:
                return clob_token_ids[outcome_index]
            return None
        except Exception as e:
            logging.error(f"Token ID alma hatasi: {e}")
            return None

    def buy(self, condition_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] BUY: cond={condition_id[:20]} fiyat=${price:.3f} boyut=${size}")
            return {"test": True, "side": "BUY", "price": price, "size": size}
        if not self.client:
            logging.error("CLOB client yok!")
            return None
        try:
            token_id = self.get_clob_token_id(condition_id, outcome_index)
            if not token_id:
                logging.error(f"Token ID bulunamadi: {condition_id}")
                return None
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY
            order_args = OrderArgs(
                token_id=token_id,
                price=round(price, 3),
                size=round(size, 2),
                side=BUY,
            )
            signed = self.client.create_order(order_args)
            from py_clob_client.clob_types import OrderType
            resp = self.client.post_order(signed, OrderType.GTC)
            logging.info(f"BUY emri gonderildi: {resp}")
            return resp
        except Exception as e:
            logging.error(f"BUY hatasi: {e}")
            return None

    def sell(self, condition_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] SELL: cond={condition_id[:20]} fiyat=${price:.3f} boyut=${size}")
            return {"test": True, "side": "SELL", "price": price, "size": size}
        if not self.client:
            return None
        try:
            token_id = self.get_clob_token_id(condition_id, outcome_index)
            if not token_id:
                logging.error(f"Token ID bulunamadi: {condition_id}")
                return None
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import SELL
            order_args = OrderArgs(
                token_id=token_id,
                price=round(price, 3),
                size=round(size, 2),
                side=SELL,
            )
            signed = self.client.create_order(order_args)
            from py_clob_client.clob_types import OrderType
            resp = self.client.post_order(signed, OrderType.GTC)
            logging.info(f"SELL emri gonderildi: {resp}")
            return resp
        except Exception as e:
            logging.error(f"SELL hatasi: {e}")
            return None

# ==================== STATE ====================
@dataclass
class Position:
    position_id: str
    trader_name: str
    market_title: str
    token_id: str
    side: str
    entry_price: Decimal
    size_usd: Decimal
    opened_at: datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "position_id":  self.position_id,
            "trader_name":  self.trader_name,
            "market_title": self.market_title,
            "side":         self.side,
            "entry_price":  float(self.entry_price),
            "size_usd":     float(self.size_usd),
            "opened_at":    self.opened_at.strftime("%H:%M %d/%m"),
        }

@dataclass
class Portfolio:
    initial_capital: Decimal = field(default_factory=lambda: Decimal(os.environ.get("INITIAL_CAPITAL", "23")))
    cash: Decimal = field(default_factory=lambda: Decimal(os.environ.get("INITIAL_CAPITAL", "23")))
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

    def to_dict(self):
        wr = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        return {
            "initial_capital": float(self.initial_capital),
            "cash":            float(self.cash),
            "open_value":      float(self.open_value),
            "total_value":     float(self.total_value),
            "realized_pnl":    float(self.realized_pnl),
            "total_pnl":       float(self.total_pnl),
            "pnl_percent":     float(self.pnl_percent),
            "total_trades":    self.total_trades,
            "winning_trades":  self.winning_trades,
            "losing_trades":   self.losing_trades,
            "win_rate":        round(wr, 1),
            "open_positions":  [p.to_dict() for p in self.open_positions.values()],
        }

app_state = {
    "running":       False,
    "scan_count":    0,
    "portfolio":     Portfolio(),
    "trade_history": [],
    "tracked_users": list(Config.TRACKED_USERS),
    "poly_client":   None,
}

# ==================== TELEGRAM ====================
class TelegramNotifier:
    def __init__(self):
        self.token   = os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = None

    async def __aenter__(self):
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    async def __aexit__(self, *_):
        if self.session: await self.session.close()

    async def send(self, msg: str):
        if not self.token or not self.chat_id:
            logging.warning("Telegram token/chat_id eksik!")
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
                    logging.warning(f"Telegram {resp.status}: {await resp.json()}")
        except Exception as e:
            logging.error(f"Telegram hatasi: {e}")

# ==================== TRACKER ====================
class UserTracker:
    def __init__(self, users):
        self.users       = users
        self.session     = None
        self.last_req    = 0
        self.seen_tx     = {u["wallet"]: set() for u in users}
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
        w    = user["wallet"]
        url  = f"{Config.DATA_API}/activity?user={w}&limit=50&type=TRADE"
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
            act["tracked_user"]   = user["name"]
            act["tracked_wallet"] = w
            new.append(act)
        if not self.initialized[w]:
            self.initialized[w] = True
            logging.info(f"Init {user['name']}: {len(self.seen_tx[w])} tx cache")
        return new

    async def scan_all(self):
        trades = []
        for u in list(self.users):
            trades.extend(await self.get_new_trades(u))
        return trades

# ==================== BOT ====================
async def run_bot():
    app_state["running"] = True
    portfolio = app_state["portfolio"]
    poly = PolymarketClient()
    app_state["poly_client"] = poly

    mod = "TEST" if Config.TEST_MODE else "GERCEK"
    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"BOT v5.0 BASLADI\n"
            f"Mod: *{mod}*\n"
            f"Trade boyutu: ${Config.TRADE_SIZE}\n"
            f"Trader sayisi: {len(app_state['tracked_users'])}\n"
            f"Cuzdan: `{Config.FUNDER[:10]}...`"
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
                    side       = act.get("side", "").upper()
                    name       = act.get("tracked_user", "?")
                    title      = str(act.get("title", act.get("question", "Bilinmiyor")))[:60]
                    token_id   = act.get("tokenId", act.get("conditionId", ""))
                    outcome_i  = act.get("outcomeIndex", 1)
                    outcome    = "YES" if outcome_i == 1 else "NO"

                    try:
                        price = float(act.get("price", 0.5))
                        price = min(max(price, 0.01), 0.99)
                    except:
                        price = 0.5

                    pos_id = f"{act.get('tracked_wallet','')[:8]}_{str(token_id)[:20]}_{outcome}"

                    if side == "BUY":
                        if pos_id in portfolio.open_positions:
                            continue
                        if portfolio.cash < Config.MIN_CASH:
                            await notifier.send(f"[NAKİT YETERSİZ] ${portfolio.cash:.2f}")
                            continue

                        # Gerçek emir gönder
                        result = poly.buy(token_id, outcome_i, price, float(Config.TRADE_SIZE))

                        if result is not None:
                            pos = Position(
                                position_id=pos_id,
                                trader_name=name,
                                market_title=title,
                                token_id=token_id,
                                side=outcome,
                                entry_price=Decimal(str(price)),
                                size_usd=Config.TRADE_SIZE,
                            )
                            portfolio.open_positions[pos_id] = pos
                            portfolio.cash -= Config.TRADE_SIZE

                            sign = "+" if portfolio.total_pnl >= 0 else ""
                            await notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON AÇILDI\n\n"
                                f"Trader: *{name}*\n"
                                f"Market: {title}\n"
                                f"Yön: *{outcome}*\n"
                                f"Fiyat: ${price:.3f}\n"
                                f"Boyut: ${Config.TRADE_SIZE}\n\n"
                                f"Nakit: ${portfolio.cash:.2f}\n"
                                f"PnL: {sign}${portfolio.total_pnl:.2f}"
                            )

                    elif side == "SELL":
                        if pos_id not in portfolio.open_positions:
                            continue
                        pos = portfolio.open_positions[pos_id]

                        # Gerçek emir gönder
                        result = poly.sell(token_id, outcome_i, price, float(pos.size_usd))

                        if result is not None:
                            shares = pos.size_usd / pos.entry_price
                            pnl    = shares * (Decimal(str(price)) - pos.entry_price)

                            portfolio.cash          += pos.size_usd + pnl
                            portfolio.realized_pnl  += pnl
                            portfolio.total_trades  += 1
                            if pnl >= 0: portfolio.winning_trades += 1
                            else:        portfolio.losing_trades  += 1

                            app_state["trade_history"].insert(0, {
                                "time":    datetime.now().strftime("%H:%M"),
                                "trader":  pos.trader_name,
                                "market":  pos.market_title,
                                "side":    pos.side,
                                "entry":   float(pos.entry_price),
                                "exit":    price,
                                "pnl":     float(pnl),
                            })

                            del portfolio.open_positions[pos_id]
                            ts = "+" if pnl >= 0 else ""
                            wr = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
                            await notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON KAPANDI\n\n"
                                f"Trader: *{pos.trader_name}*\n"
                                f"Market: {pos.market_title}\n"
                                f"PnL: {ts}${abs(float(pnl)):.2f}\n\n"
                                f"Nakit: ${portfolio.cash:.2f}\n"
                                f"Win Rate: {wr:.0f}% ({portfolio.winning_trades}W/{portfolio.losing_trades}L)"
                            )

            # 20 taramada bir rapor
            if app_state["scan_count"] % 20 == 0:
                async with TelegramNotifier() as notifier:
                    sign = "+" if portfolio.total_pnl >= 0 else ""
                    await notifier.send(
                        f"[RAPOR] Tarama #{app_state['scan_count']}\n"
                        f"Toplam: ${portfolio.total_value:.2f}\n"
                        f"PnL: {sign}${portfolio.total_pnl:.2f} ({sign}{portfolio.pnl_percent:.1f}%)\n"
                        f"Acik: {len(portfolio.open_positions)} | Trade: {portfolio.total_trades}"
                    )

        except Exception as e:
            logging.error(f"Scan hatasi: {e}")

        await asyncio.sleep(Config.SCAN_INTERVAL)

    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"[BOT DURDURULDU]\n"
            f"Toplam: ${portfolio.total_value:.2f}\n"
            f"PnL: ${portfolio.total_pnl:.2f}\n"
            f"Trade: {portfolio.total_trades}"
        )

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

# ==================== FLASK ====================
flask_app = Flask(__name__, static_folder=".")

@flask_app.route("/")
def index():
    return send_from_directory(".", "index.html")

@flask_app.route("/api/status")
def status():
    return jsonify({
        "running":       app_state["running"],
        "scan_count":    app_state["scan_count"],
        "test_mode":     Config.TEST_MODE,
        "portfolio":     app_state["portfolio"].to_dict(),
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
    data   = request.json or {}
    name   = data.get("name", "").strip()
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=" * 50)
    print("  POLYMARKET BOT v5.0")
    print(f"  Token: {'OK' if os.environ.get('TELEGRAM_TOKEN') else 'EKSIK'}")
    print(f"  Private Key: {'OK' if os.environ.get('PRIVATE_KEY') else 'EKSIK'}")
    print(f"  Mod: {'TEST' if Config.TEST_MODE else 'GERCEK'}")
    print("=" * 50)

    if os.environ.get("RAILWAY_ENVIRONMENT"):
        t = threading.Thread(target=start_bot_thread, daemon=True)
        t.start()

    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

