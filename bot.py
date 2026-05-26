#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYMARKET COPY TRADING BOT v4.0
=================================
- Flask web dashboard (port 5000)
- Trader ekle/çıkar (runtime)
- Bot başlat/durdur
- Canlı portföy + işlem geçmişi
- Tüm v3.3 bugfix'leri dahil
"""

import asyncio
import aiohttp
import time
import threading
import json
import os
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List
import logging
import sys

from flask import Flask, jsonify, request, send_from_directory

# ==================== CONFIG ====================
class Config:
    TEST_MODE        = True           # False yapınca gerçek işlem modu
    INITIAL_CAPITAL  = Decimal('50')
    TRADE_SIZE       = Decimal('5')
    MIN_CASH         = Decimal('5')
    SCAN_INTERVAL    = 15
    MIN_USDC_SIZE    = Decimal('1')

    DATA_API  = "https://data-api.polymarket.com"
    GAMMA_API = "https://gamma-api.polymarket.com"

    # ⚠ Token'ı ortam değişkeninden al; yoksa .env'den yükle
    TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "BURAYA_TOKEN_GİR")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "BURAYA_CHAT_ID_GİR")

    # Başlangıç trader listesi — web arayüzünden değiştirilebilir
    TRACKED_USERS: List[Dict] = [
        {"name": "Oddn",              "wallet": "0xa53c26443fb636d8ae31ac24f62fc1d5ef8f67a5"},
        {"name": "Swisstony",         "wallet": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
        {"name": "LaBradfordSmith22", "wallet": "0x9495425feeb0c250accb89275c97587011b19a27"},
        {"name": "Mosley1",           "wallet": "0x5bec79df9add70a3892041ab1a5516b60f53b215"},
        {"name": "wan123",            "wallet": "0xde7be6d489bce070a959e0cb813128ae659b5f4b"},
        {"name": "Tiger200",          "wallet": "0x6211f97a76ed5c4b1d658f637041ac5f293db89e"},
    ]

# ==================== STATE ====================
@dataclass
class Position:
    position_id:  str
    trader_name:  str
    market_title: str
    market_slug:  str
    side:         str
    entry_price:  Decimal
    size_usd:     Decimal
    opened_at:    datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "position_id":  self.position_id,
            "trader_name":  self.trader_name,
            "market_title": self.market_title,
            "side":         self.side,
            "entry_price":  float(self.entry_price),
            "size_usd":     float(self.size_usd),
            "opened_at":    self.opened_at.strftime("%H:%M:%S %d/%m"),
        }

@dataclass
class Portfolio:
    initial_capital: Decimal = field(default_factory=lambda: Config.INITIAL_CAPITAL)
    cash:            Decimal = field(default_factory=lambda: Config.INITIAL_CAPITAL)
    realized_pnl:    Decimal = field(default_factory=Decimal)
    open_positions:  Dict[str, Position] = field(default_factory=dict)
    total_trades:    int = 0
    winning_trades:  int = 0
    losing_trades:   int = 0

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
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
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
            "win_rate":        round(win_rate, 1),
            "open_positions":  [p.to_dict() for p in self.open_positions.values()],
        }

# Global paylaşımlı durum
app_state = {
    "running":      False,
    "scan_count":   0,
    "portfolio":    Portfolio(),
    "trade_history": [],          # [{...}, ...]
    "tracked_users": list(Config.TRACKED_USERS),
    "bot_thread":   None,
    "loop":         None,
}

# ==================== TELEGRAM ====================
class TelegramNotifier:
    def __init__(self):
        self.token   = Config.TELEGRAM_TOKEN
        self.chat_id = Config.TELEGRAM_CHAT_ID
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(); return self
    async def __aexit__(self, *_):
        if self.session: await self.session.close()

    async def send(self, msg: str):
        if self.token in ("BURAYA_TOKEN_GİR", ""):
            logging.debug("Telegram token ayarlanmadı, bildirim atlandı.")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with self.session.post(url, json={
                "chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"
            }) as resp:
                if resp.status != 200:
                    logging.warning(f"Telegram {resp.status}: {await resp.text()}")
        except Exception as e:
            logging.error(f"Telegram hatası: {e}")

    async def send_open(self, pos: Position, p: Portfolio):
        sign = "+" if p.total_pnl >= 0 else ""
        await self.send(
            f"[POZİSYON AÇILDI]\n\n"
            f"Trader: *{pos.trader_name}*\n"
            f"Market: {pos.market_title[:50]}\n"
            f"Yön: *{pos.side}*\n"
            f"Giriş: ${pos.entry_price:.3f}\n"
            f"Boyut: ${pos.size_usd:.2f}\n"
            f"Saat: {pos.opened_at.strftime('%H:%M:%S')}\n\n"
            f"💼 Nakit: ${p.cash:.2f} | Açık: {len(p.open_positions)}\n"
            f"📊 Toplam: ${p.total_value:.2f} | PnL: {sign}${p.total_pnl:.2f}"
        )

    async def send_close(self, pos: Position, pnl: Decimal, exit_price: Decimal, p: Portfolio):
        ts = "+" if pnl >= 0 else ""
        ps = "+" if p.total_pnl >= 0 else ""
        wr = (p.winning_trades / p.total_trades * 100) if p.total_trades > 0 else 0
        await self.send(
            f"[POZİSYON KAPANDI]\n\n"
            f"Trader: *{pos.trader_name}*\n"
            f"Market: {pos.market_title[:50]}\n"
            f"Giriş: ${pos.entry_price:.3f} → Çıkış: ${exit_price:.3f}\n"
            f"Trade PnL: {ts}${pnl:.2f}\n\n"
            f"💼 Nakit: ${p.cash:.2f}\n"
            f"📊 Toplam: ${p.total_value:.2f} | PnL: {ps}${p.total_pnl:.2f}\n"
            f"🏆 Win Rate: {wr:.0f}% ({p.winning_trades}W/{p.losing_trades}L)"
        )

# ==================== TRACKER ====================
class UserTracker:
    def __init__(self, users: List[Dict]):
        self.users    = users
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_req = 0
        self.seen_tx: Dict[str, Set[str]]  = {u["wallet"]: set() for u in users}
        self.initialized: Dict[str, bool]  = {u["wallet"]: False for u in users}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(); return self
    async def __aexit__(self, *_):
        if self.session: await self.session.close()

    def add_user(self, user: Dict):
        w = user["wallet"]
        if w not in self.seen_tx:
            self.seen_tx[w]     = set()
            self.initialized[w] = False
            self.users.append(user)

    def remove_user(self, wallet: str):
        self.users = [u for u in self.users if u["wallet"] != wallet]
        self.seen_tx.pop(wallet, None)
        self.initialized.pop(wallet, None)

    async def _get(self, url: str):
        now = time.time()
        wait = 0.5 - (now - self.last_req)
        if wait > 0: await asyncio.sleep(wait)
        self.last_req = time.time()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as e:
            logging.debug(f"Request error: {e}"); return None

    async def get_new_trades(self, user: Dict) -> List[Dict]:
        w   = user["wallet"]
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
            act["tracked_user"]   = user["name"]
            act["tracked_wallet"] = w
            new.append(act)

        if not self.initialized[w]:
            self.initialized[w] = True
            logging.info(f"Init {user['name']}: {len(self.seen_tx[w])} tx cache")
        return new

    async def scan_all(self) -> List[Dict]:
        trades = []
        for u in list(self.users):
            trades.extend(await self.get_new_trades(u))
        return trades

# ==================== MAIN BOT ====================
class PolymarketBot:
    def __init__(self):
        self.portfolio      = app_state["portfolio"]
        self.no_cash_noted  = False

    def _pos_id(self, wallet, cid, oi):
        side = "YES" if oi == 1 else "NO"
        return f"{wallet[:8]}_{str(cid)[:30]}_{side}"

    async def open_pos(self, act: Dict, notifier: TelegramNotifier, tracker: UserTracker):
        wallet = act.get("tracked_wallet", "")
        cid    = act.get("conditionId", "")
        oi     = act.get("outcomeIndex", 1)
        pid    = self._pos_id(wallet, cid, oi)

        if pid in self.portfolio.open_positions: return
        if self.portfolio.cash < Config.MIN_CASH:
            if not self.no_cash_noted:
                await notifier.send(f"[NAKİT YETERSİZ] ${self.portfolio.cash:.2f} - yeni pozisyon açılamıyor.")
                self.no_cash_noted = True
            return
        self.no_cash_noted = False

        side  = "YES" if oi == 1 else "NO"
        name  = act.get("tracked_user", "?")
        title = str(act.get("title", act.get("question", "Bilinmiyor")))[:60]
        try:
            price = Decimal(str(act.get("price", "0.5")))
            price = min(max(price, Decimal("0.01")), Decimal("0.99"))
        except:
            price = Decimal("0.5")

        pos = Position(
            position_id=pid, trader_name=name, market_title=title,
            market_slug=str(cid)[:30], side=side,
            entry_price=price, size_usd=Config.TRADE_SIZE,
        )
        self.portfolio.open_positions[pid] = pos
        self.portfolio.cash -= Config.TRADE_SIZE
        logging.info(f"AÇILDI: {name} | {side} | ${Config.TRADE_SIZE} | Nakit: ${self.portfolio.cash:.2f}")
        await notifier.send_open(pos, self.portfolio)

    async def close_pos(self, act: Dict, notifier: TelegramNotifier):
        wallet = act.get("tracked_wallet", "")
        cid    = act.get("conditionId", "")
        oi     = act.get("outcomeIndex", 1)
        pid    = self._pos_id(wallet, cid, oi)
        if pid not in self.portfolio.open_positions: return

        pos = self.portfolio.open_positions[pid]
        try:
            ep = Decimal(str(act.get("price", "0.5")))
            ep = min(max(ep, Decimal("0.01")), Decimal("0.99"))
        except:
            ep = pos.entry_price

        shares = pos.size_usd / pos.entry_price
        pnl    = shares * (ep - pos.entry_price)

        self.portfolio.cash          += pos.size_usd + pnl
        self.portfolio.realized_pnl  += pnl
        self.portfolio.total_trades  += 1
        if pnl >= 0: self.portfolio.winning_trades += 1
        else:        self.portfolio.losing_trades  += 1

        # Geçmişe ekle
        app_state["trade_history"].insert(0, {
            "time":        datetime.now().strftime("%H:%M:%S"),
            "date":        datetime.now().strftime("%d/%m/%Y"),
            "trader":      pos.trader_name,
            "market":      pos.market_title,
            "side":        pos.side,
            "entry":       float(pos.entry_price),
            "exit":        float(ep),
            "size":        float(pos.size_usd),
            "pnl":         float(pnl),
            "pnl_percent": float((pnl / pos.size_usd) * 100),
        })
        if len(app_state["trade_history"]) > 200:
            app_state["trade_history"] = app_state["trade_history"][:200]

        del self.portfolio.open_positions[pid]
        logging.info(f"KAPANDI: {pos.trader_name} | PnL: ${pnl:.2f} | Nakit: ${self.portfolio.cash:.2f}")
        await notifier.send_close(pos, pnl, ep, self.portfolio)

    async def run_loop(self):
        app_state["running"] = True
        tracker = UserTracker(list(app_state["tracked_users"]))

        async with TelegramNotifier() as notifier:
            await notifier.send(
                f"[BOT v4.0 BAŞLADI]\n"
                f"Kapital: ${Config.INITIAL_CAPITAL} | Trade: ${Config.TRADE_SIZE}\n"
                f"Trader: {len(app_state['tracked_users'])} kişi\n"
                f"Mod: {'🧪 TEST' if Config.TEST_MODE else '🟢 GERÇEK'}"
            )

        while app_state["running"]:
            app_state["scan_count"] += 1
            # Tracker'ı güncel kullanıcı listesiyle senkronize et
            current_wallets  = {u["wallet"] for u in app_state["tracked_users"]}
            tracker_wallets  = {u["wallet"] for u in tracker.users}
            for u in app_state["tracked_users"]:
                if u["wallet"] not in tracker_wallets:
                    tracker.add_user(u)
            for w in tracker_wallets - current_wallets:
                tracker.remove_user(w)

            try:
                async with aiohttp.ClientSession() as sess:
                    tracker.session = sess
                    trades = await tracker.scan_all()

                async with TelegramNotifier() as notifier:
                    for act in trades:
                        side = act.get("side", "").upper()
                        if side == "BUY":
                            await self.open_pos(act, notifier, tracker)
                        elif side == "SELL":
                            await self.close_pos(act, notifier)

                if app_state["scan_count"] % 20 == 0:
                    async with TelegramNotifier() as notifier:
                        p = self.portfolio
                        sign = "+" if p.total_pnl >= 0 else ""
                        await notifier.send(
                            f"[PERİYODİK RAPOR]\n"
                            f"Toplam: ${p.total_value:.2f} | PnL: {sign}${p.total_pnl:.2f} ({sign}{p.pnl_percent:.1f}%)\n"
                            f"Açık: {len(p.open_positions)} | Trade: {p.total_trades}"
                        )
            except Exception as e:
                logging.error(f"Scan hatası: {e}")

            await asyncio.sleep(Config.SCAN_INTERVAL)

        async with TelegramNotifier() as notifier:
            p = self.portfolio
            sign = "+" if p.total_pnl >= 0 else ""
            await notifier.send(
                f"[BOT DURDURULDU]\n"
                f"Toplam: ${p.total_value:.2f} | PnL: {sign}${p.total_pnl:.2f}\n"
                f"Trade: {p.total_trades} ({p.winning_trades}W/{p.losing_trades}L)"
            )

def start_bot():
    loop = asyncio.new_event_loop()
    app_state["loop"] = loop
    bot = PolymarketBot()
    loop.run_until_complete(bot.run_loop())
    loop.close()

# ==================== FLASK API ====================
flask_app = Flask(__name__, static_folder=".")

@flask_app.route("/")
def index():
    return send_from_directory(".", "index.html")

@flask_app.route("/api/status")
def status():
    p = app_state["portfolio"]
    return jsonify({
        "running":      app_state["running"],
        "scan_count":   app_state["scan_count"],
        "test_mode":    Config.TEST_MODE,
        "portfolio":    p.to_dict(),
        "tracked_users": app_state["tracked_users"],
    })

@flask_app.route("/api/history")
def history():
    return jsonify(app_state["trade_history"])

@flask_app.route("/api/start", methods=["POST"])
def start():
    if app_state["running"]:
        return jsonify({"ok": False, "msg": "Bot zaten çalışıyor"})
    t = threading.Thread(target=start_bot, daemon=True)
    app_state["bot_thread"] = t
    t.start()
    return jsonify({"ok": True, "msg": "Bot başlatıldı"})

@flask_app.route("/api/stop", methods=["POST"])
def stop():
    if not app_state["running"]:
        return jsonify({"ok": False, "msg": "Bot zaten durmuş"})
    app_state["running"] = False
    return jsonify({"ok": True, "msg": "Bot durduruldu"})

@flask_app.route("/api/traders", methods=["GET"])
def get_traders():
    return jsonify(app_state["tracked_users"])

@flask_app.route("/api/traders", methods=["POST"])
def add_trader():
    data = request.json or {}
    name   = data.get("name", "").strip()
    wallet = data.get("wallet", "").strip().lower()
    if not name or not wallet:
        return jsonify({"ok": False, "msg": "İsim ve cüzdan gerekli"})
    if not wallet.startswith("0x") or len(wallet) != 42:
        return jsonify({"ok": False, "msg": "Geçersiz cüzdan adresi (0x... 42 karakter)"})
    if any(u["wallet"] == wallet for u in app_state["tracked_users"]):
        return jsonify({"ok": False, "msg": "Bu cüzdan zaten takip ediliyor"})
    app_state["tracked_users"].append({"name": name, "wallet": wallet})
    logging.info(f"Trader eklendi: {name} ({wallet})")
    return jsonify({"ok": True, "msg": f"{name} eklendi"})

@flask_app.route("/api/traders/<wallet>", methods=["DELETE"])
def del_trader(wallet):
    before = len(app_state["tracked_users"])
    app_state["tracked_users"] = [u for u in app_state["tracked_users"] if u["wallet"] != wallet]
    if len(app_state["tracked_users"]) == before:
        return jsonify({"ok": False, "msg": "Bulunamadı"})
    logging.info(f"Trader silindi: {wallet}")
    return jsonify({"ok": True, "msg": "Trader silindi"})

@flask_app.route("/api/config", methods=["POST"])
def update_config():
    data = request.json or {}
    try:
        if "trade_size" in data:
            Config.TRADE_SIZE = Decimal(str(data["trade_size"]))
        if "min_cash" in data:
            Config.MIN_CASH = Decimal(str(data["min_cash"]))
        if "scan_interval" in data:
            Config.SCAN_INTERVAL = int(data["scan_interval"])
        if "test_mode" in data:
            Config.TEST_MODE = bool(data["test_mode"])
        return jsonify({"ok": True, "msg": "Ayarlar güncellendi"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=" * 50)
    print("  POLYMARKET BOT v4.0")
    print("  Dashboard: http://localhost:5000")
    print("=" * 50)
    flask_app.run(host="0.0.0.0", port=5000, debug=False)
