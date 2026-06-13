#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYMARKET COPY TRADING BOT v7.0 - SIFIRDAN TEMİZ
- Tüm bilinen hatalar giderildi
- seen_conditions dosyaya kaydediliyor (restart'ta kaybolmuyor)
- Slippage %5 kontrolü
- Tek Telegram
- 15 trader
"""

import asyncio
import aiohttp
import json
import time
import threading
import os
import logging
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from flask import Flask, jsonify, request, send_from_directory
try:
    from flask_cors import CORS
    _CORS_AVAILABLE = True
except ImportError:
    _CORS_AVAILABLE = False
from dotenv import load_dotenv

load_dotenv()

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ==================== STORAGE ====================
def _init_data_dir() -> str:
    candidates = [
        os.environ.get("DATA_DIR", ""),
        "/data",
        ".",
        tempfile.gettempdir(),
    ]
    for d in candidates:
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            logging.info(f"Storage klasoru: {d}")
            return d
        except Exception:
            continue
    return "."

_DATA_DIR      = _init_data_dir()
PORTFOLIO_FILE = os.path.join(_DATA_DIR, "portfolio_state.json")
SEEN_TX_FILE   = os.path.join(_DATA_DIR, "seen_tx.json")
CONDITIONS_FILE = os.path.join(_DATA_DIR, "seen_conditions.json")

# ==================== CONFIG ====================
class Config:
    CLOB_HOST    = "https://clob.polymarket.com"
    DATA_API     = "https://data-api.polymarket.com"
    CHAIN_ID     = 137
    EOA_ADDRESS  = os.environ.get("EOA_ADDRESS", "")
    PRIVATE_KEY  = os.environ.get("PRIVATE_KEY", "")
    CLOB_API_KEY = os.environ.get("CLOB_API_KEY", "")
    CLOB_SECRET  = os.environ.get("CLOB_SECRET", "")
    CLOB_PASS_PHRASE  = os.environ.get("CLOB_PASS_PHRASE", "")
    DEPOSIT_WALLET    = os.environ.get("DEPOSIT_WALLET", "")
    TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
    TRADE_SIZE        = Decimal(os.environ.get("TRADE_SIZE", "5"))
    MIN_CASH          = Decimal(os.environ.get("MIN_CASH", "5"))
    INITIAL_CAPITAL   = Decimal(os.environ.get("INITIAL_CAPITAL", "1000"))
    SCAN_INTERVAL     = int(os.environ.get("SCAN_INTERVAL", "60"))
    MIN_USDC_SIZE     = Decimal("1")
    TEST_MODE         = os.environ.get("TEST_MODE", "true").lower() == "true"
    SLIPPAGE_LIMIT    = float(os.environ.get("SLIPPAGE_LIMIT", "0.05"))  # %5
    TRADE_AGE_LIMIT   = int(os.environ.get("TRADE_AGE_LIMIT", "300"))    # 5 dakika
    MIN_TRADE_PRICE   = float(os.environ.get("MIN_TRADE_PRICE", "0.05"))
    MARKET_WIN_PRICE  = Decimal("0.99")
    MARKET_LOSE_PRICE = Decimal("0.01")
    COMMISSION_RATE   = Decimal("0.02")
    STOP_LOSS_ENABLED = False
    STOP_LOSS_PCT     = 40
    BLACKLIST_MARKETS = ["rihanna", "gta vi", "new rihanna"]
    BLACKLIST_CONDITION_IDS = [
        "0x1fad72fae204143ff1c3035e99e7c0f65ea8d5cd9bd1070987bd1a3316f772be",
    ]
    TRACKED_USERS: List[Dict] = [
        {"name": "ewelmealt",            "wallet": "0x07921379f7b31ef93da634b688b2fe36897db778"},
        {"name": "HorizonSplendidView",  "wallet": "0x02227b8f5a9636e895607edd3185ed6ee5598ff7"},
        {"name": "majorexploiter",       "wallet": "0x019782cab5d844f02bafb71f512758be78579f3c"},
        {"name": "reachingthesky",       "wallet": "0xefbc5fec8d7b0acdc8911bdd9a98d6964308f9a2"},
        {"name": "bcda",                 "wallet": "0xb45a797faa52b0fd8adc56d30382022b7b12192c"},
        {"name": "geniusMC",             "wallet": "0x0b9cae2b0dfe7a71c413e0604eaac1c352f87e44"},
        {"name": "Countryside",          "wallet": "0xbddf61af533ff524d27154e589d2d7a81510c684"},
        {"name": "gatorr",               "wallet": "0x93abbc022ce98d6f45d4444b594791cc4b7a9723"},
        {"name": "gopfan2",              "wallet": "0xf2f6af4f27ec2dcf4072095ab804016e14cd5817"},
        {"name": "Theo4",                "wallet": "0x56687bf447db6ffa42ffe2204a05edaa20f55839"},
        {"name": "Fredi9999",            "wallet": "0x1f2dd6d473f3e824cd2f8a89d9c69fb96f6ad0cf"},
        {"name": "ferrariChampions2026", "wallet": "0xfe787d2da716d60e8acff57fb87eb13cd4d10319"},
        {"name": "kch123",               "wallet": "0x6a72f61820b26b1fe4d956e17b6dc2a1ea3033ee"},
        {"name": "rn1",                  "wallet": "0x2005d16a84ceefa912d4e380cd32e7ff827875ea"},
        {"name": "Swisstony",            "wallet": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
    ]

# ==================== LOCK ====================
_portfolio_lock = threading.Lock()

# ==================== ASYNC HTTP ====================
async def async_get(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> Optional[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None
            text = await resp.text()
            if not text or text.strip() in ("null", ""):
                return None
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return None
    except asyncio.TimeoutError:
        logging.warning(f"Timeout: {url[:60]}")
        return None
    except Exception as e:
        logging.debug(f"async_get hata: {e}")
        return None

async def async_get_token_id(session: aiohttp.ClientSession, condition_id: str, outcome_index: int) -> Optional[str]:
    # CLOB API
    data = await async_get(session, f"{Config.CLOB_HOST}/markets/{condition_id}")
    if data:
        tokens = data.get("tokens", [])
        if isinstance(tokens, list) and len(tokens) > outcome_index:
            token_id = tokens[outcome_index].get("token_id", "")
            if token_id:
                return token_id
    # Gamma API fallback
    data = await async_get(session, f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}")
    if data:
        mkt = data[0] if isinstance(data, list) else data
        clob_ids = mkt.get("clobTokenIds", "[]")
        if clob_ids is None or clob_ids == "null":
            return None
        if isinstance(clob_ids, str):
            try:
                clob_ids = json.loads(clob_ids)
            except json.JSONDecodeError:
                return None
        if isinstance(clob_ids, list) and len(clob_ids) > outcome_index:
            return clob_ids[outcome_index]
    return None

async def async_get_last_price(session: aiohttp.ClientSession, token_id: str, fallback: float) -> float:
    data = await async_get(session, f"{Config.CLOB_HOST}/last-trade-price?token_id={token_id}", timeout=5)
    if data:
        try:
            return float(data.get("price", fallback))
        except (ValueError, TypeError):
            pass
    return fallback

# ==================== STATE ====================
@dataclass
class Position:
    position_id:   str
    trader_name:   str
    market_title:  str
    token_id:      str
    side:          str
    entry_price:   Decimal
    size_usd:      Decimal
    outcome_index: int = 0
    opened_at:     datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "position_id":   self.position_id,
            "trader_name":   self.trader_name,
            "market_title":  self.market_title,
            "token_id":      self.token_id,
            "side":          self.side,
            "outcome_index": self.outcome_index,
            "entry_price":   float(self.entry_price),
            "size_usd":      float(self.size_usd),
            "opened_at":     self.opened_at.strftime("%H:%M %d/%m"),
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
    def open_value(self):  return sum(p.size_usd for p in self.open_positions.values())
    @property
    def total_value(self): return self.cash + self.open_value
    @property
    def total_pnl(self):   return self.total_value - self.initial_capital
    @property
    def win_rate(self):
        return (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

    def to_dict(self):
        return {
            "initial_capital": float(self.initial_capital),
            "cash":            float(self.cash),
            "open_value":      float(self.open_value),
            "total_value":     float(self.total_value),
            "realized_pnl":    float(self.realized_pnl),
            "total_pnl":       float(self.total_pnl),
            "total_trades":    self.total_trades,
            "winning_trades":  self.winning_trades,
            "losing_trades":   self.losing_trades,
            "win_rate":        round(self.win_rate, 1),
            "open_positions":  [p.to_dict() for p in self.open_positions.values()],
        }

# ==================== PERSISTENCE ====================
def save_seen_tx(seen_tx: Dict):
    try:
        with _portfolio_lock:
            data = {w: list(txs) for w, txs in seen_tx.items()}
            with open(SEEN_TX_FILE, "w") as f:
                json.dump(data, f)
    except Exception as e:
        logging.error(f"seen_tx kayit hatasi: {e}")

def load_seen_tx() -> Dict:
    try:
        if not os.path.exists(SEEN_TX_FILE):
            return {}
        with open(SEEN_TX_FILE) as f:
            data = json.load(f)
        return {w: set(txs) for w, txs in data.items()}
    except Exception as e:
        logging.error(f"seen_tx yukle hatasi: {e}")
        return {}

def save_seen_conditions(conditions: set):
    try:
        with _portfolio_lock:
            with open(CONDITIONS_FILE, "w") as f:
                json.dump(list(conditions), f)
    except Exception as e:
        logging.error(f"seen_conditions kayit hatasi: {e}")

def load_seen_conditions() -> set:
    try:
        if not os.path.exists(CONDITIONS_FILE):
            return set()
        with open(CONDITIONS_FILE) as f:
            data = json.load(f)
        return set(data)
    except Exception as e:
        logging.error(f"seen_conditions yukle hatasi: {e}")
        return set()

def save_portfolio(portfolio: Portfolio):
    with _portfolio_lock:
        try:
            state = {
                "cash":            float(portfolio.cash),
                "initial_capital": float(portfolio.initial_capital),
                "realized_pnl":    float(portfolio.realized_pnl),
                "total_trades":    portfolio.total_trades,
                "winning_trades":  portfolio.winning_trades,
                "losing_trades":   portfolio.losing_trades,
                "open_positions":  {k: {
                    "position_id":   v.position_id,
                    "trader_name":   v.trader_name,
                    "market_title":  v.market_title,
                    "token_id":      v.token_id,
                    "side":          v.side,
                    "outcome_index": v.outcome_index,
                    "entry_price":   float(v.entry_price),
                    "size_usd":      float(v.size_usd),
                    "opened_at":     v.opened_at.strftime("%Y-%m-%d %H:%M:%S"),
                } for k, v in portfolio.open_positions.items()}
            }
            with open(PORTFOLIO_FILE, "w") as f:
                json.dump(state, f)
        except Exception as e:
            logging.error(f"Portfolio kayit hatasi: {e}")

def load_portfolio() -> Optional[Portfolio]:
    try:
        if not os.path.exists(PORTFOLIO_FILE):
            return None
        with open(PORTFOLIO_FILE) as f:
            state = json.load(f)
        p = Portfolio()
        p.cash            = Decimal(str(state.get("cash", Config.INITIAL_CAPITAL)))
        p.initial_capital = Decimal(str(state.get("initial_capital", Config.INITIAL_CAPITAL)))
        p.realized_pnl    = Decimal(str(state.get("realized_pnl", 0)))
        p.total_trades    = int(state.get("total_trades", 0))
        p.winning_trades  = int(state.get("winning_trades", 0))
        p.losing_trades   = int(state.get("losing_trades", 0))
        for k, v in state.get("open_positions", {}).items():
            try:
                p.open_positions[k] = Position(
                    position_id=v["position_id"],
                    trader_name=v["trader_name"],
                    market_title=v["market_title"],
                    token_id=v["token_id"],
                    side=v["side"],
                    outcome_index=int(v.get("outcome_index", 0)),
                    entry_price=Decimal(str(v["entry_price"])),
                    size_usd=Decimal(str(v["size_usd"])),
                    opened_at=datetime.strptime(v["opened_at"], "%Y-%m-%d %H:%M:%S"),
                )
            except Exception as e:
                logging.warning(f"Pozisyon yukle hatasi ({k}): {e}")
        logging.info(f"Portfolio yuklendi: {len(p.open_positions)} pozisyon, ${p.cash:.2f} nakit")
        return p
    except Exception as e:
        logging.error(f"Portfolio yukle hatasi: {e}")
        return None

def _init_tracked_users():
    try:
        traders_file = os.path.join(_DATA_DIR, "traders.json")
        if os.path.exists(traders_file):
            with open(traders_file) as f:
                return json.load(f)
    except Exception:
        pass
    return list(Config.TRACKED_USERS)

def save_traders(users):
    try:
        traders_file = os.path.join(_DATA_DIR, "traders.json")
        with open(traders_file, "w") as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logging.error(f"Trader kayit hatasi: {e}")

# ==================== APP STATE ====================
app_state = {
    "running":           False,
    "scan_count":        0,
    "portfolio":         Portfolio(),
    "trade_history":     [],
    "tracked_users":     _init_tracked_users(),
    "seen_conditions":   load_seen_conditions(),
    "day_trades":        [],
    "day_start_capital": Decimal("0"),
    "eod_sent_today":    False,
    "no_cash_notified":  False,
    "last_report_scan":  0,
}

# ==================== TELEGRAM ====================
class TelegramNotifier:
    def __init__(self, token=None, chat_id=None):
        self.token   = token   or Config.TELEGRAM_TOKEN
        self.chat_id = chat_id or Config.TELEGRAM_CHAT_ID
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(ssl=True)
        self.session = aiohttp.ClientSession(connector=connector, connector_owner=True)
        return self

    async def __aexit__(self, *_):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    async def send(self, msg: str):
        if not self.token or not self.chat_id:
            logging.warning("Telegram token/chat_id eksik!")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with self.session.post(url, json={
                "chat_id":    self.chat_id,
                "text":       msg[:4096],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logging.warning(f"Telegram {resp.status}: {body[:100]}")
        except Exception as e:
            logging.error(f"Telegram hatasi: {e}")

# ==================== TRACKER ====================
class UserTracker:
    def __init__(self, users):
        self.users       = users
        self.session     = None
        self.last_req    = 0
        saved_tx         = load_seen_tx()
        self.seen_tx     = {u["wallet"]: saved_tx.get(u["wallet"], set()) for u in users}
        self.initialized = {u["wallet"]: False for u in users}
        total = sum(len(v) for v in self.seen_tx.values())
        logging.info(f"seen_tx yuklendi: {total} tx")

    async def _get(self, url) -> Optional[list]:
        wait = 0.5 - (time.time() - self.last_req)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_req = time.time()
        return await async_get(self.session, url)

    async def get_new_trades(self, user) -> list:
        w    = user["wallet"]
        url  = f"{Config.DATA_API}/activity?user={w}&limit=10&type=TRADE"
        data = await self._get(url)
        if not data or not isinstance(data, list):
            return []
        new    = []
        now_ts = time.time()
        for act in data:
            tx = act.get("transactionHash", "")
            if not tx:
                continue
            if not self.initialized[w]:
                self.seen_tx[w].add(tx)
                continue
            if tx in self.seen_tx[w]:
                continue
            self.seen_tx[w].add(tx)
            # Timestamp kontrolü
            try:
                trade_ts = act.get("timestamp") or act.get("createdAt") or act.get("blockTimestamp") or 0
                if isinstance(trade_ts, str):
                    trade_ts = datetime.fromisoformat(trade_ts.replace("Z", "+00:00")).timestamp()
                age = now_ts - float(trade_ts)
                if age > Config.TRADE_AGE_LIMIT or age < -60:
                    logging.info(f"Eski islem atlandi ({age:.0f}s): {tx[:10]}")
                    continue
            except Exception as e:
                logging.warning(f"Timestamp hatasi, atlaniyor: {e}")
                continue
            # Min size kontrolü
            try:
                size = Decimal(str(act.get("usdcSize", "0")))
            except (InvalidOperation, ValueError):
                size = Decimal("0")
            if size < Config.MIN_USDC_SIZE:
                continue
            act["tracked_user"]   = user["name"]
            act["tracked_wallet"] = w
            new.append(act)
        if not self.initialized[w]:
            self.initialized[w] = True
            logging.info(f"Init {user['name']}: {len(self.seen_tx[w])} tx cache")
        return new

    async def scan_all(self) -> list:
        trades = []
        for u in list(self.users):
            trades.extend(await self.get_new_trades(u))
        return trades

# ==================== POZISYON KONTROLÜ ====================
async def check_closed_positions(portfolio: Portfolio, notifier: TelegramNotifier, session: aiohttp.ClientSession):
    if not portfolio.open_positions:
        return
    checked = {}
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            if not pos.token_id:
                continue
            if pos.token_id not in checked:
                checked[pos.token_id] = await async_get_last_price(session, pos.token_id, float(pos.entry_price))
            cur = Decimal(str(checked[pos.token_id]))
            result = None
            if cur >= Config.MARKET_WIN_PRICE:
                pnl = pos.size_usd / pos.entry_price * (Config.MARKET_WIN_PRICE - pos.entry_price)
                with _portfolio_lock:
                    portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
                    portfolio.realized_pnl += pnl
                    portfolio.winning_trades += 1
                    del portfolio.open_positions[pos_id]
                result = ("KAZANDI ✅", pos, float(pnl))
            elif cur <= Config.MARKET_LOSE_PRICE:
                pnl = pos.size_usd / pos.entry_price * (Config.MARKET_LOSE_PRICE - pos.entry_price)
                with _portfolio_lock:
                    portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                    portfolio.realized_pnl += pnl
                    portfolio.losing_trades += 1
                    del portfolio.open_positions[pos_id]
                result = ("KAYBETTI ❌", pos, float(pnl))
            if result:
                label, p, pnl_val = result
                app_state["day_trades"].append({
                    "time":   datetime.now().strftime("%H:%M"),
                    "trader": p.trader_name,
                    "market": p.market_title,
                    "side":   p.side,
                    "pnl":    pnl_val,
                })
                save_portfolio(portfolio)
                sign = "+" if pnl_val >= 0 else ""
                wr   = portfolio.win_rate
                await notifier.send(
                    f"{label} POZISYON KAPANDI\n\n"
                    f"Trader: *{p.trader_name}*\n"
                    f"Market: {p.market_title[:50]}\n"
                    f"Yon: {p.side}\n"
                    f"PnL: {sign}${abs(pnl_val):.2f}\n"
                    f"Nakit: ${float(portfolio.cash):.2f}\n"
                    f"Win rate: {wr:.0f}% ({portfolio.winning_trades}K/{portfolio.losing_trades}L)"
                )
        except Exception as e:
            logging.error(f"Pozisyon kontrol hatasi ({pos_id}): {e}")

# ==================== RAPORLAR ====================
async def _build_live_stats(portfolio: Portfolio, session: aiohttp.ClientSession):
    live_value   = Decimal("0")
    trader_stats = {}
    price_cache  = {}
    for pos in list(portfolio.open_positions.values()):
        try:
            if pos.token_id not in price_cache:
                price_cache[pos.token_id] = await async_get_last_price(session, pos.token_id, float(pos.entry_price))
            cur      = Decimal(str(price_cache[pos.token_id]))
            pos_val  = pos.size_usd / pos.entry_price * cur
            pos_pnl  = pos_val - pos.size_usd
            live_value += pos_val
            t = pos.trader_name
            if t not in trader_stats:
                trader_stats[t] = {"count": 0, "value": Decimal("0"), "pnl": Decimal("0")}
            trader_stats[t]["count"] += 1
            trader_stats[t]["value"] += pos_val
            trader_stats[t]["pnl"]   += pos_pnl
        except Exception as e:
            logging.debug(f"Live stats hatasi: {e}")
            live_value += pos.size_usd
    return live_value, trader_stats

async def send_periodic_report(portfolio: Portfolio, session: aiohttp.ClientSession):
    live_value, trader_stats = await _build_live_stats(portfolio, session)
    live_total   = portfolio.cash + live_value
    open_cost    = sum(p.size_usd for p in portfolio.open_positions.values())
    open_pnl     = live_value - open_cost
    open_sign    = "+" if open_pnl >= 0 else ""
    now_str      = datetime.now().strftime("%H:%M")

    trader_lines = ""
    for t, s in sorted(trader_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        ts = "+" if s["pnl"] >= 0 else ""
        trader_lines += f"  {t}: {s['count']} acik | ${float(s['value']):.2f} | {ts}${float(s['pnl']):.2f}\n"
    if not trader_lines:
        trader_lines = "  Acik pozisyon yok\n"

    msg = (
        f"📊 YARIM SAATLIK OZET — {now_str}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 *TOPLAM PARAM: ${float(live_total):.2f}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Nakit: ${float(portfolio.cash):.2f}\n"
        f"📦 Acik poz. degeri: ${float(live_value):.2f}\n"
        f"📈 Acik poz. K/Z: {open_sign}${float(open_pnl):.2f}\n"
        f"✅ Kapanan PnL: ${float(portfolio.realized_pnl):+.2f}\n"
        f"🎯 Win rate: {portfolio.win_rate:.0f}% ({portfolio.winning_trades}K/{portfolio.losing_trades}L)\n"
        f"━━━━━━━━━━━━━━\n"
        f"TRADER BAZLI ACIK POZISYONLAR\n"
        f"{trader_lines}"
    )
    async with TelegramNotifier() as n:
        await n.send(msg)

async def send_eod_report(portfolio: Portfolio, session: aiohttp.ClientSession):
    live_value, trader_stats = await _build_live_stats(portfolio, session)
    live_total  = portfolio.cash + live_value
    day_start   = app_state.get("day_start_capital") or portfolio.initial_capital
    day_pnl     = live_total - day_start
    day_pnl_pct = float(day_pnl / day_start * 100) if day_start else 0
    pnl_sign    = "+" if day_pnl >= 0 else ""
    open_cost   = sum(p.size_usd for p in portfolio.open_positions.values())
    open_pnl    = live_value - open_cost
    date_str    = datetime.now().strftime("%d %B %Y")

    # Trader performansı (kapanan + açık)
    all_stats = {}
    for trade in app_state.get("day_trades", []):
        t = trade.get("trader", "?")
        if t not in all_stats:
            all_stats[t] = {"count": 0, "pnl": Decimal("0")}
        all_stats[t]["count"] += 1
        all_stats[t]["pnl"]   += Decimal(str(trade.get("pnl", 0)))
    for t, s in trader_stats.items():
        if t not in all_stats:
            all_stats[t] = {"count": 0, "pnl": Decimal("0")}
        all_stats[t]["pnl"] += s["pnl"]

    trader_lines = ""
    for t, s in sorted(all_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        ts = "+" if s["pnl"] >= 0 else ""
        trader_lines += f"  {t}: {s['count']} islem | {ts}${float(s['pnl']):.2f}\n"
    if not trader_lines:
        trader_lines = "  Islem yok\n"

    msg = (
        f"🌙 GUNUN OZETI — {date_str}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💵 *TOPLAM PARAM: ${float(live_total):.2f}*\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Nakit: ${float(portfolio.cash):.2f}\n"
        f"📦 Acik poz. degeri: ${float(live_value):.2f}\n"
        f"📈 Acik poz. K/Z: ${float(open_pnl):+.2f}\n"
        f"📊 Gunluk PnL: {pnl_sign}${float(day_pnl):.2f} ({pnl_sign}{day_pnl_pct:.1f}%)\n"
        f"━━━━━━━━━━━━━━\n"
        f"📋 Toplam islem: {portfolio.total_trades}\n"
        f"✅ Kazanan: {portfolio.winning_trades}\n"
        f"❌ Kaybeden: {portfolio.losing_trades}\n"
        f"🎯 Win rate: {portfolio.win_rate:.0f}%\n"
        f"━━━━━━━━━━━━━━\n"
        f"TRADER PERFORMANSI\n"
        f"{trader_lines}"
    )
    async with TelegramNotifier() as n:
        await n.send(msg)

    # Günü sıfırla
    app_state["day_trades"]        = []
    app_state["day_start_capital"] = live_total
    app_state["eod_sent_today"]    = True

# ==================== BOT ANA DÖNGÜ ====================
async def run_bot():
    app_state["running"] = True
    logging.info("Bot basliyor...")

    # Tek kalici session
    connector  = aiohttp.TCPConnector(ssl=True, limit=20)
    session    = aiohttp.ClientSession(connector=connector)

    # Portfolio yukle
    saved = load_portfolio()
    if saved:
        app_state["portfolio"] = saved
    else:
        app_state["portfolio"] = Portfolio()
        app_state["portfolio"].cash = Config.INITIAL_CAPITAL
        app_state["portfolio"].initial_capital = Config.INITIAL_CAPITAL

    portfolio = app_state["portfolio"]
    app_state["day_start_capital"] = portfolio.cash + portfolio.open_value

    # seen_conditions yukle
    app_state["seen_conditions"] = load_seen_conditions()
    logging.info(f"seen_conditions yuklendi: {len(app_state['seen_conditions'])} adet")

    # Baslangic mesaji
    mod = "TEST" if Config.TEST_MODE else "GERCEK"
    async with TelegramNotifier() as n:
        await n.send(
            f"🤖 BOT BASLADI v7.0\n"
            f"Mod: *{mod}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 *Toplam: ${float(portfolio.total_value):.2f}*\n"
            f"💰 Nakit: ${float(portfolio.cash):.2f}\n"
            f"📌 Acik: {len(portfolio.open_positions)} pozisyon\n"
            f"👥 Takip: {len(app_state['tracked_users'])} trader\n"
            f"⚡ Slippage limiti: %{Config.SLIPPAGE_LIMIT*100:.0f}"
        )

    tracker = UserTracker(list(app_state["tracked_users"]))

    try:
        while app_state["running"]:
            app_state["scan_count"] += 1
            sc = app_state["scan_count"]

            try:
                # Trader'ları tara
                tracker.session = session
                trades = await tracker.scan_all()
                if trades:
                    logging.info(f"Tarama #{sc}: {len(trades)} yeni trade")

                async with TelegramNotifier() as notifier:

                    # Her 3 taramada pozisyon kontrol
                    if sc % 3 == 0:
                        await check_closed_positions(portfolio, notifier, session)

                    for act in trades:
                        side      = act.get("side", "").upper()
                        name      = act.get("tracked_user", "?")
                        outcome_i = int(act.get("outcomeIndex", 0))
                        outcome   = "YES" if outcome_i == 0 else "NO"

                        # Fiyat
                        try:
                            price = float(act.get("price", 0.5))
                            price = min(max(price, 0.01), 0.99)
                        except (ValueError, TypeError):
                            price = 0.5

                        # Min fiyat filtresi
                        if price < Config.MIN_TRADE_PRICE:
                            logging.info(f"Ucuz market atlandi (${price:.3f}): {act.get('title','?')[:40]}")
                            continue

                        # condition_id ve seen_key -- hem BUY hem SELL için tanımla
                        condition_id       = act.get("conditionId", "")
                        condition_id_short = str(condition_id or act.get("tokenId", ""))[:20]
                        seen_key           = f"{condition_id}_{outcome_i}" if condition_id else ""

                        if side == "BUY":
                            # Title
                            raw_title = (act.get("title") or act.get("question") or
                                         act.get("marketTitle") or
                                         act.get("slug", "").replace("-", " "))
                            title = str(raw_title).strip()[:120] if raw_title else ""
                            if not title:
                                logging.warning("Bos title, atlaniyor")
                                continue

                            # Kara liste
                            title_lower = title.lower()
                            if any(b in title_lower for b in Config.BLACKLIST_MARKETS):
                                logging.info(f"Kara liste (title): {title[:40]}")
                                continue
                            if condition_id in Config.BLACKLIST_CONDITION_IDS:
                                logging.info(f"Kara liste (conditionId): {condition_id[:20]}")
                                continue

                            # Duplicate kontrolü (dosyadan yüklü seen_conditions)
                            if seen_key and seen_key in app_state["seen_conditions"]:
                                logging.debug(f"Duplicate, atlaniyor: {seen_key[:30]}")
                                continue

                            # Nakit kontrolü (komisyon dahil)
                            min_required = Config.TRADE_SIZE * (Decimal("1") + Config.COMMISSION_RATE)
                            real_cash    = portfolio.cash
                            if real_cash < min_required:
                                if not app_state["no_cash_notified"]:
                                    await notifier.send(f"💸 NAKİT YETERSİZ: ${float(real_cash):.2f}")
                                    app_state["no_cash_notified"] = True
                                continue
                            app_state["no_cash_notified"] = False

                            # Slippage kontrolü
                            direct_asset   = act.get("asset", act.get("tokenId", ""))
                            final_token_id = direct_asset
                            if condition_id:
                                fetched = await async_get_token_id(session, condition_id, outcome_i)
                                if fetched:
                                    final_token_id = fetched

                            if not final_token_id:
                                logging.warning(f"Token ID bulunamadi: {condition_id[:20]}")
                                continue

                            # Anlık fiyat vs trader fiyatı (slippage)
                            current_price = await async_get_last_price(session, final_token_id, price)
                            slippage      = abs(current_price - price) / price if price > 0 else 0
                            if slippage > Config.SLIPPAGE_LIMIT:
                                logging.info(f"Slippage %{slippage*100:.1f} > %{Config.SLIPPAGE_LIMIT*100:.0f}, atlaniyor: {title[:40]}")
                                await notifier.send(
                                    f"⚠️ SLIPPAGE ATLANDI\n"
                                    f"Market: {title[:50]}\n"
                                    f"Trader fiyati: ${price:.3f} → Anlık: ${current_price:.3f}\n"
                                    f"Kayma: %{slippage*100:.1f}"
                                )
                                continue

                            # seen_conditions'a ekle ve kaydet
                            if seen_key:
                                app_state["seen_conditions"].add(seen_key)
                                save_seen_conditions(app_state["seen_conditions"])

                            # Pozisyon ID (timestamp suffix ile çakışma önlenir)
                            ts_suffix = str(int(time.time()))[-6:]
                            pos_id    = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}_{ts_suffix}"

                            # TEST modunda işlem simüle et
                            if Config.TEST_MODE:
                                result = {"test": True}
                                logging.info(f"[TEST] BUY: ${Config.TRADE_SIZE} @ ${price:.3f} - {title[:40]}")
                            else:
                                # Gerçek mod - CLOB V2
                                result = {"real": True}  # gerçek impl için CLOB client eklenecek
                                logging.info(f"[GERCEK] BUY: ${Config.TRADE_SIZE} @ ${price:.3f}")

                            if result is not None:
                                pos = Position(
                                    position_id=pos_id,
                                    trader_name=name,
                                    market_title=title,
                                    token_id=final_token_id,
                                    side=outcome,
                                    outcome_index=outcome_i,
                                    entry_price=Decimal(str(price)),
                                    size_usd=Config.TRADE_SIZE,
                                )
                                with _portfolio_lock:
                                    portfolio.open_positions[pos_id] = pos
                                    portfolio.total_trades += 1
                                    portfolio.cash -= Config.TRADE_SIZE * (Decimal("1") + Config.COMMISSION_RATE)
                                save_portfolio(portfolio)

                                pnl_sign = "+" if portfolio.total_pnl >= 0 else ""
                                await notifier.send(
                                    f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON AÇILDI\n\n"
                                    f"Trader: *{name}*\n"
                                    f"Market: {title}\n"
                                    f"Yön: *{outcome}*\n"
                                    f"Fiyat: ${price:.3f}\n"
                                    f"Boyut: ${Config.TRADE_SIZE}\n\n"
                                    f"Nakit: ${float(portfolio.cash):.2f}\n"
                                    f"PnL: {pnl_sign}${float(portfolio.total_pnl):.2f}"
                                )

                        elif side == "SELL":
                            # SELL: base_id ile eşleş
                            base_id     = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}"
                            matching    = next(
                                ((pid, p) for pid, p in portfolio.open_positions.items() if pid.startswith(base_id)),
                                None
                            )
                            if not matching:
                                continue
                            pos_id, pos = matching

                            if Config.TEST_MODE:
                                result = {"test": True}
                            else:
                                result = {"real": True}

                            if result is not None:
                                shares = pos.size_usd / pos.entry_price
                                pnl    = shares * (Decimal(str(price)) - pos.entry_price)
                                with _portfolio_lock:
                                    portfolio.realized_pnl += pnl
                                    portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
                                    if pnl >= 0:
                                        portfolio.winning_trades += 1
                                    else:
                                        portfolio.losing_trades += 1
                                    del portfolio.open_positions[pos_id]
                                app_state["day_trades"].append({
                                    "time":   datetime.now().strftime("%H:%M"),
                                    "trader": pos.trader_name,
                                    "market": pos.market_title,
                                    "side":   pos.side,
                                    "pnl":    float(pnl),
                                })
                                app_state["trade_history"].insert(0, {
                                    "time":   datetime.now().strftime("%H:%M"),
                                    "trader": pos.trader_name,
                                    "market": pos.market_title,
                                    "side":   pos.side,
                                    "entry":  float(pos.entry_price),
                                    "exit":   price,
                                    "pnl":    float(pnl),
                                })
                                save_portfolio(portfolio)

                                ts      = "+" if pnl >= 0 else ""
                                emoji   = "✅" if pnl >= 0 else "❌"
                                await notifier.send(
                                    f"{emoji} {'[TEST] ' if Config.TEST_MODE else ''}POZISYON KAPANDI\n\n"
                                    f"Trader: *{pos.trader_name}*\n"
                                    f"Market: {pos.market_title[:50]}\n"
                                    f"Yon: {pos.side}\n"
                                    f"PnL: {ts}${abs(float(pnl)):.2f}\n"
                                    f"Nakit: ${float(portfolio.cash):.2f}\n"
                                    f"Win rate: {portfolio.win_rate:.0f}% ({portfolio.winning_trades}K/{portfolio.losing_trades}L)"
                                )

                # seen_tx kaydet (her 5 taramada)
                if sc % 5 == 0:
                    save_seen_tx(tracker.seen_tx)

                # Yarım saatlik rapor (her 30 taramada = 30 dakika)
                if sc % 30 == 0:
                    await send_periodic_report(portfolio, session)

                # Gece 00:00 gün sonu raporu
                now = datetime.now()
                if now.hour == 0 and now.minute < 1 and not app_state.get("eod_sent_today"):
                    await send_eod_report(portfolio, session)
                elif now.hour != 0:
                    app_state["eod_sent_today"] = False

            except Exception as e:
                logging.error(f"Scan hatasi: {e}", exc_info=True)

            await asyncio.sleep(Config.SCAN_INTERVAL)

    finally:
        await session.close()
        logging.info("Session kapatildi")

    async with TelegramNotifier() as n:
        await n.send(
            f"🛑 BOT DURDURULDU\n"
            f"Toplam: ${float(portfolio.total_value):.2f}\n"
            f"PnL: ${float(portfolio.total_pnl):.2f}\n"
            f"Trade: {portfolio.total_trades}"
        )

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except Exception as e:
        logging.error(f"Bot thread hatasi: {e}", exc_info=True)
        app_state["running"] = False
    finally:
        loop.close()

# ==================== FLASK ====================
flask_app = Flask(__name__, static_folder=".")
if _CORS_AVAILABLE:
    CORS(flask_app)
else:
    @flask_app.after_request
    def add_cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://clob.polymarket.com"
        return response

@flask_app.route("/")
def index():
    try:
        return send_from_directory(".", "index.html")
    except Exception:
        return jsonify({"status": "running", "scan_count": app_state["scan_count"]})

@flask_app.route("/api/status")
def api_status():
    portfolio = app_state["portfolio"]
    d = portfolio.to_dict()
    return jsonify({
        "running":       app_state["running"],
        "scan_count":    app_state["scan_count"],
        "test_mode":     Config.TEST_MODE,
        "portfolio":     d,
        "tracked_users": app_state["tracked_users"],
    })

@flask_app.route("/api/position-prices")
def api_position_prices():
    """Her pozisyon icin anlik fiyat, PnL ve pnl_pct dondur"""
    portfolio = app_state["portfolio"]
    result    = {}
    for pos_id, pos in list(portfolio.open_positions.items()):
        if not pos.token_id:
            continue
        try:
            resp = sync_requests.get(
                f"{Config.CLOB_HOST}/last-trade-price?token_id={pos.token_id}",
                timeout=3
            )
            if resp.status_code == 200:
                price = float(resp.json().get("price", float(pos.entry_price)))
                entry = float(pos.entry_price)
                size  = float(pos.size_usd)
                shares = size / entry if entry > 0 else 0
                if pos.side == "YES":
                    pnl = shares * (price - entry)
                else:
                    pnl = shares * ((1 - price) - entry)
                result[pos_id] = {
                    "current_price": round(price, 4),
                    "estimated_pnl": round(pnl, 2),
                    "pnl_pct":       round((pnl / size * 100) if size > 0 else 0, 1),
                }
        except Exception as e:
            logging.error(f"Fiyat cekme hatasi {pos_id}: {e}")
    return jsonify(result)

@flask_app.route("/api/history")
def api_history():
    return jsonify(app_state["trade_history"][:50])

@flask_app.route("/api/start", methods=["POST"])
def api_start():
    if app_state["running"]:
        return jsonify({"ok": False, "msg": "Bot zaten calisiyor"})
    threading.Thread(target=start_bot_thread, daemon=True).start()
    return jsonify({"ok": True, "msg": "Bot baslatildi"})

@flask_app.route("/api/stop", methods=["POST"])
def api_stop():
    app_state["running"] = False
    return jsonify({"ok": True, "msg": "Bot durduruldu"})

@flask_app.route("/api/traders", methods=["GET"])
def api_get_traders():
    return jsonify(app_state["tracked_users"])

@flask_app.route("/api/traders", methods=["POST"])
def api_add_trader():
    data   = request.json or {}
    name   = data.get("name", "").strip()
    wallet = data.get("wallet", "").strip().lower()
    if not name or not wallet:
        return jsonify({"ok": False, "msg": "Isim ve cuzdan gerekli"})
    if any(u["wallet"] == wallet for u in app_state["tracked_users"]):
        return jsonify({"ok": False, "msg": "Bu trader zaten listede"})
    app_state["tracked_users"].append({"name": name, "wallet": wallet})
    save_traders(app_state["tracked_users"])
    return jsonify({"ok": True, "msg": f"{name} eklendi"})

@flask_app.route("/api/traders/<wallet>", methods=["DELETE"])
def api_del_trader(wallet):
    app_state["tracked_users"] = [u for u in app_state["tracked_users"] if u["wallet"] != wallet]
    save_traders(app_state["tracked_users"])
    return jsonify({"ok": True, "msg": "Trader silindi"})

@flask_app.route("/api/prices", methods=["POST"])
def api_prices():
    """Token ID listesi alır, anlık fiyatları döner"""
    import requests as req
    data      = request.json or {}
    token_ids = data.get("token_ids", [])
    prices    = {}
    for tid in token_ids[:30]:
        try:
            r = req.get(
                f"https://clob.polymarket.com/last-trade-price?token_id={tid}",
                timeout=5
            )
            if r.status_code == 200:
                prices[tid] = float(r.json().get("price", 0))
        except Exception:
            prices[tid] = None
    return jsonify({"prices": prices})

@flask_app.route("/api/close-position", methods=["POST"])
def api_close_position():
    import requests as req
    data      = request.json or {}
    pos_id    = data.get("position_id", "")
    portfolio = app_state["portfolio"]
    if pos_id not in portfolio.open_positions:
        return jsonify({"ok": False, "msg": "Pozisyon bulunamadi"})
    pos = portfolio.open_positions[pos_id]
    # Anlık fiyatı çek
    try:
        r = req.get(f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}", timeout=5)
        cur_price = Decimal(str(r.json().get("price", float(pos.entry_price)))) if r.status_code == 200 else pos.entry_price
    except Exception:
        cur_price = pos.entry_price
    # PnL hesapla
    shares = pos.size_usd / pos.entry_price
    pnl    = shares * (cur_price - pos.entry_price)
    with _portfolio_lock:
        portfolio.cash         += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
        portfolio.realized_pnl += pnl
        if pnl >= 0:
            portfolio.winning_trades += 1
        else:
            portfolio.losing_trades  += 1
        app_state["day_trades"].append({
            "time":   datetime.now().strftime("%H:%M"),
            "trader": pos.trader_name,
            "market": pos.market_title,
            "side":   pos.side,
            "pnl":    float(pnl),
        })
        del portfolio.open_positions[pos_id]
    save_portfolio(portfolio)
    sign = "+" if pnl >= 0 else ""
    logging.info(f"Pozisyon manuel kapatildi: {pos.market_title[:40]} PnL:{sign}${float(pnl):.2f}")
    return jsonify({
        "ok":      True,
        "msg":     f"{pos.market_title[:40]} kapatildi",
        "pnl":     float(pnl),
        "cash":    float(portfolio.cash),
        "sign":    sign,
    })

@flask_app.route("/api/close-all", methods=["POST"])
def api_close_all():
    portfolio = app_state["portfolio"]
    if not portfolio.open_positions:
        return jsonify({"ok": False, "msg": "Acik pozisyon yok"})
    count = len(portfolio.open_positions)
    with _portfolio_lock:
        for pos_id, pos in list(portfolio.open_positions.items()):
            portfolio.realized_pnl += Decimal("0")
            portfolio.cash += pos.size_usd
            del portfolio.open_positions[pos_id]
    save_portfolio(portfolio)
    return jsonify({"ok": True, "msg": f"{count} pozisyon kapatildi", "count": count})

# ==================== MAIN ====================
if __name__ == "__main__":
    print("=" * 55)
    print("  POLYMARKET BOT v7.0 - SIFIRDAN TEMİZ")
    print(f"  Mod:         {'TEST' if Config.TEST_MODE else 'GERCEK'}")
    print(f"  Telegram:    {'OK' if Config.TELEGRAM_TOKEN else 'EKSIK'}")
    print(f"  Storage:     {_DATA_DIR}")
    print(f"  Trader:      {len(Config.TRACKED_USERS)} adet")
    print(f"  Trade boyut: ${Config.TRADE_SIZE}")
    print(f"  Slippage:    %{Config.SLIPPAGE_LIMIT*100:.0f}")
    print("=" * 55)

    threading.Thread(target=start_bot_thread, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
