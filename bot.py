
code = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYMARKET COPY TRADING BOT v5.4
- Trader takip et
- Otomatik BUY/SELL
- Telegram bildirimleri
- Portföy takibi
- GERÇEK MOD desteği
"""

import asyncio
import aiohttp
import time
import threading
import os
import logging
import sys
import json
import requests
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Set, List
from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIG ====================
class Config:
    CLOB_HOST        = "https://clob.polymarket.com"
    DATA_API         = "https://data-api.polymarket.com"
    CHAIN_ID         = 137
    EOA_ADDRESS      = os.environ.get("EOA_ADDRESS", "")
    PRIVATE_KEY      = os.environ.get("PRIVATE_KEY", "")
    CLOB_API_KEY     = os.environ.get("CLOB_API_KEY", "")
    CLOB_SECRET      = os.environ.get("CLOB_SECRET", "")
    CLOB_PASS_PHRASE = os.environ.get("CLOB_PASS_PHRASE", "")
    DEPOSIT_WALLET   = os.environ.get("DEPOSIT_WALLET", "")
    BUILDER_API_KEY  = os.environ.get("BUILDER_API_KEY", "")
    BUILDER_SECRET   = os.environ.get("BUILDER_SECRET", "")
    BUILDER_PASS_PHRASE = os.environ.get("BUILDER_PASS_PHRASE", "")
    RELAYER_URL      = os.environ.get("RELAYER_URL", "https://relayer.polymarket.com")
    TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    TRADE_SIZE       = Decimal(os.environ.get("TRADE_SIZE", "5"))
    MIN_CASH         = Decimal(os.environ.get("MIN_CASH", "5"))
    INITIAL_CAPITAL  = Decimal(os.environ.get("INITIAL_CAPITAL", "100"))
    SCAN_INTERVAL    = 60
    MIN_USDC_SIZE    = Decimal("1")
    TEST_MODE        = os.environ.get("TEST_MODE", "false").lower() == "true"
    BLACKLIST_MARKETS = ["rihanna", "gta vi", "new rihanna"]
    BLACKLIST_TOKEN_IDS = [
        "53831553061883006530739877284105938919721408776239639687877978808906551086026",
        "98022490269692409998126496127597032490334070080325855126491859374983463996227",
    ]
    BLACKLIST_CONDITION_IDS = [
        "0x1fad72fae204143ff1c3035e99e7c0f65ea8d5cd9bd1070987bd1a3316f772be",
    ]
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
        self.deposit_wallet = None
        self._init_client()

    def _get_deposit_wallet(self):
        if Config.DEPOSIT_WALLET:
            logging.info(f"Deposit wallet: {Config.DEPOSIT_WALLET[:10]}...")
            return Config.DEPOSIT_WALLET
        if Config.BUILDER_API_KEY and Config.PRIVATE_KEY:
            try:
                from py_builder_relayer_client.client import RelayClient
                from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig
                builder_config = BuilderConfig(
                    local_builder_creds=BuilderApiKeyCreds(
                        key=Config.BUILDER_API_KEY,
                        secret=Config.BUILDER_SECRET,
                        passphrase=Config.BUILDER_PASS_PHRASE,
                    )
                )
                relayer = RelayClient(Config.RELAYER_URL, Config.CHAIN_ID, Config.PRIVATE_KEY, builder_config)
                deposit_wallet = relayer.get_expected_deposit_wallet()
                logging.info(f"Relayer deposit wallet: {deposit_wallet[:10]}...")
                try:
                    response = relayer.deploy_deposit_wallet()
                    response.wait()
                    logging.info("Deposit wallet deploy edildi!")
                except Exception as e:
                    logging.warning(f"Deploy (zaten var olabilir): {e}")
                return deposit_wallet
            except ImportError:
                logging.warning("py-builder-relayer-client kurulu degil")
            except Exception as e:
                logging.error(f"Relayer hatasi: {e}")
        if Config.EOA_ADDRESS:
            logging.warning("EOA adresi kullaniliyor - Polymarket reddedebilir!")
            return Config.EOA_ADDRESS
        return None

    def _init_client(self):
        if Config.TEST_MODE:
            logging.info("TEST modu - CLOB client atlaniyor")
            return
        if not Config.PRIVATE_KEY:
            logging.warning("PRIVATE_KEY eksik")
            return
        try:
            from py_clob_client_v2 import ClobClient, ApiCreds, SignatureTypeV2
            from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
            self.deposit_wallet = self._get_deposit_wallet()
            if not self.deposit_wallet:
                logging.error("Deposit wallet bulunamadi!")
                return
            creds = ApiCreds(
                api_key=Config.CLOB_API_KEY,
                api_secret=Config.CLOB_SECRET,
                api_passphrase=Config.CLOB_PASS_PHRASE,
            )
            self.client = ClobClient(
                host=Config.CLOB_HOST,
                chain_id=Config.CHAIN_ID,
                key=Config.PRIVATE_KEY,
                creds=creds,
                signature_type=SignatureTypeV2.POLY_1271,
                funder=self.deposit_wallet,
            )
            logging.info("Balance allowance guncelleniyor...")
            self.client.update_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=SignatureTypeV2.POLY_1271,
                )
            )
            logging.info(f"Polymarket V2 OK! Deposit: {self.deposit_wallet[:10]}...")
        except Exception as e:
            logging.error(f"CLOB baglanti hatasi: {e}")
            self.client = None

    def get_clob_token_id(self, condition_id: str, outcome_index: int) -> Optional[str]:
        try:
            url = f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}"
            logging.info(f"get_clob_token_id: cond={condition_id[:20]} outcome={outcome_index}")
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200: return None
            data = resp.json()
            if not data: return None
            market = data[0] if isinstance(data, list) else data
            market_title = market.get("question", market.get("title", "?"))
            logging.info(f"API market title: {market_title}")
            clob_token_ids = market.get("clobTokenIds", "[]")
            if isinstance(clob_token_ids, str):
                clob_token_ids = json.loads(clob_token_ids)
            if len(clob_token_ids) > outcome_index:
                return clob_token_ids[outcome_index]
            return None
        except Exception as e:
            logging.error(f"Token ID hatasi: {e}")
            return None

    def buy(self, condition_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] BUY: ${size} @ ${price:.3f}")
            return {"test": True, "orderID": f"test_{int(time.time())}"}
        if not self.client:
            logging.error("CLOB client yok!")
            return None
        try:
            if len(condition_id) > 50 and not condition_id.startswith("0x"):
                token_id = condition_id
                logging.info(f"Direkt token ID kullaniliyor: {token_id[:20]}...")
            else:
                token_id = self.get_clob_token_id(condition_id, outcome_index)
            if not token_id: return None
            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
            from py_clob_client_v2.order_builder.constants import BUY
            order_args = OrderArgs(token_id=token_id, price=round(price, 3), size=round(size, 2), side=BUY)
            resp = self.client.create_and_post_order(
                order_args=order_args,
                options=PartialCreateOrderOptions(tick_size="0.01"),
                order_type=OrderType.GTC,
            )
            if resp is None:
                logging.error("BUY None dondu")
                return None
            if isinstance(resp, dict):
                if resp.get("error") or resp.get("errorMsg"):
                    logging.error(f"BUY hata: {resp}")
                    return None
                if resp.get("status") in ["REJECTED", "CANCELLED"]:
                    logging.error(f"BUY reddedildi: {resp}")
                    return None
                if not resp.get("success", True):
                    logging.error(f"BUY basarisiz: {resp}")
                    return None
            logging.info(f"BUY basarili: {resp}")
            return resp
        except Exception as e:
            logging.error(f"BUY hatasi: {e}")
            return None

    def sell(self, condition_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] SELL: ${size} @ ${price:.3f}")
            return {"test": True, "orderID": f"test_{int(time.time())}"}
        if not self.client: return None
        try:
            token_id = self.get_clob_token_id(condition_id, outcome_index)
            if not token_id: return None
            from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions
            from py_clob_client_v2.order_builder.constants import SELL
            order_args = OrderArgs(token_id=token_id, price=round(price, 3), size=round(size, 2), side=SELL)
            resp = self.client.create_and_post_order(
                order_args=order_args,
                options=PartialCreateOrderOptions(tick_size="0.01"),
                order_type=OrderType.GTC,
            )
            if resp is None:
                logging.error("SELL None dondu")
                return None
            if isinstance(resp, dict) and resp.get("error"):
                logging.error(f"SELL hata: {resp}")
                return None
            if isinstance(resp, dict) and resp.get("status") in ["REJECTED", "CANCELLED"]:
                logging.error(f"SELL reddedildi: {resp}")
                return None
            logging.info(f"SELL basarili: {resp}")
            return resp
        except Exception as e:
            logging.error(f"SELL hatasi: {e}")
            return None

    def cancel_all_orders(self) -> Dict:
        if Config.TEST_MODE:
            logging.info("[TEST] Tüm emirler iptal edildi (simülasyon)")
            return {"cancelled": 0, "test": True}
        if not self.client:
            logging.error("CLOB client yok!")
            return {"error": "CLOB client yok"}
        try:
            open_orders = self.client.get_orders({"status": "LIVE"})
            if not open_orders:
                logging.info("İptal edilecek açık emir yok")
                return {"cancelled": 0}
            order_ids = []
            for o in (open_orders if isinstance(open_orders, list) else []):
                oid = o.get("id") or o.get("order_id")
                if oid:
                    order_ids.append(oid)
            if not order_ids:
                return {"cancelled": 0}
            result = self.client.cancel_orders(order_ids)
            logging.info(f"İptal sonucu: {result}")
            return {"cancelled": len(order_ids), "result": str(result)}
        except Exception as e:
            logging.error(f"cancel_all_orders hatasi: {e}")
            return {"error": str(e)}

    def get_real_balance(self) -> Decimal:
        if not self.client:
            return Decimal(os.environ.get("INITIAL_CAPITAL", "0"))
        try:
            from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
            from py_clob_client_v2 import SignatureTypeV2
            balance = self.client.get_balance_allowance(
                BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=SignatureTypeV2.POLY_1271,
                )
            )
            logging.info(f"CLOB raw: {balance}")
            bal_val = "0"
            if isinstance(balance, dict):
                bal_val = str(balance.get("balance", balance.get("allowance", "0")))
            elif hasattr(balance, "balance"):
                bal_val = str(balance.balance)
            elif isinstance(balance, (int, float, str)):
                bal_val = str(balance)
            raw = Decimal(bal_val)
            if raw > Decimal("1000000"):
                usdc = raw / Decimal("1000000")
            else:
                usdc = raw
            logging.info(f"Bakiye: {usdc:.2f} USDC")
            return usdc.quantize(Decimal("0.01"))
        except Exception as e:
            logging.error(f"Bakiye hatasi: {e}")
            return Decimal(os.environ.get("INITIAL_CAPITAL", "0"))

    def get_real_balance_rpc(self) -> Decimal:
        try:
            USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            addr = self.deposit_wallet[2:].lower()
            data = "0x70a08231000000000000000000000000" + addr
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": USDC_CONTRACT, "data": data}, "latest"],
                "id": 1
            }
            resp = requests.post("https://polygon-rpc.com", json=payload, timeout=10)
            result = resp.json()
            hex_balance = result.get("result", "0x0")
            wei = int(hex_balance, 16)
            usdc = Decimal(wei) / Decimal("1000000")
            logging.info(f"RPC bakiye: {usdc:.2f} USDC")
            return usdc.quantize(Decimal("0.01"))
        except Exception as e:
            logging.error(f"RPC bakiye hatasi: {e}")
            return Decimal("0")

    def sync_portfolio_balance(self, portfolio) -> None:
        real = self.get_real_balance()
        if real <= Decimal("0") or real > Decimal("100000"):
            logging.warning("API bakiye hatalı, RPC'den deneniyor...")
            real = self.get_real_balance_rpc()
        if real > Decimal("0"):
            old_cash = portfolio.cash
            portfolio.cash = real
            if portfolio.initial_capital == Decimal("0"):
                portfolio.initial_capital = real
            logging.info(f"Bakiye senkronize edildi: ${old_cash:.2f} -> ${real:.2f}")

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
    condition_id: str = ""

    def to_dict(self):
        return {
            "position_id":  self.position_id,
            "trader_name":  self.trader_name,
            "market_title": self.market_title,
            "side":         self.side,
            "entry_price":  float(self.entry_price),
            "size_usd":     float(self.size_usd),
            "opened_at":    self.opened_at.strftime("%H:%M %d/%m"),
            "condition_id": self.condition_id,
        }

PORTFOLIO_FILE = "portfolio_state.json"
SEEN_TX_FILE = "seen_tx.json"

def save_seen_tx(seen_tx):
    try:
        data = {w: list(txs) for w, txs in seen_tx.items()}
        with open(SEEN_TX_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"seen_tx kayit hatasi: {e}")

def load_seen_tx():
    try:
        if not os.path.exists(SEEN_TX_FILE):
            return {}
        with open(SEEN_TX_FILE) as f:
            data = json.load(f)
        return {w: set(txs) for w, txs in data.items()}
    except Exception as e:
        logging.error(f"seen_tx yukle hatasi: {e}")
        return {}

def save_portfolio(portfolio):
    try:
        state = {
            "cash": float(portfolio.cash),
            "initial_capital": float(portfolio.initial_capital),
            "realized_pnl": float(portfolio.realized_pnl),
            "total_trades": portfolio.total_trades,
            "winning_trades": portfolio.winning_trades,
            "losing_trades": portfolio.losing_trades,
            "open_positions": {k: {
                "position_id": v.position_id,
                "trader_name": v.trader_name,
                "market_title": v.market_title,
                "token_id": v.token_id,
                "side": v.side,
                "entry_price": float(v.entry_price),
                "size_usd": float(v.size_usd),
                "opened_at": v.opened_at.strftime("%Y-%m-%d %H:%M:%S"),
                "condition_id": v.condition_id,
            } for k, v in portfolio.open_positions.items()}
        }
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(state, f)
        logging.info(f"Portfolio kaydedildi: {len(portfolio.open_positions)} pozisyon, Nakit: ${portfolio.cash:.2f}")
    except Exception as e:
        logging.error(f"Portfolio kayit hatasi: {e}")

def load_portfolio():
    try:
        if not os.path.exists(PORTFOLIO_FILE):
            return None
        with open(PORTFOLIO_FILE) as f:
            state = json.load(f)
        p = Portfolio()
        p.cash = Decimal(str(state["cash"]))
        p.initial_capital = Decimal(str(state["initial_capital"]))
        p.realized_pnl = Decimal(str(state["realized_pnl"]))
        p.total_trades = state["total_trades"]
        p.winning_trades = state["winning_trades"]
        p.losing_trades = state["losing_trades"]
        for k, v in state["open_positions"].items():
            pos = Position(
                position_id=v["position_id"],
                trader_name=v["trader_name"],
                market_title=v["market_title"],
                token_id=v["token_id"],
                side=v["side"],
                entry_price=Decimal(str(v["entry_price"])),
                size_usd=Decimal(str(v["size_usd"])),
                opened_at=datetime.strptime(v["opened_at"], "%Y-%m-%d %H:%M:%S"),
                condition_id=v.get("condition_id", ""),
            )
            p.open_positions[k] = pos
        logging.info(f"Portfolio yuklendi: {len(p.open_positions)} pozisyon, Nakit: ${p.cash:.2f}")
        return p
    except Exception as e:
        logging.error(f"Portfolio yukle hatasi: {e}")
        return None

@dataclass
class Portfolio:
    initial_capital: Decimal = field(default_factory=lambda: Decimal(os.environ.get("INITIAL_CAPITAL", "100")))
    cash: Decimal = field(default_factory=lambda: Decimal(os.environ.get("INITIAL_CAPITAL", "100")))
    realized_pnl: Decimal = field(default_factory=Decimal)
    open_positions: Dict[str, Position] = field(default_factory=dict)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0

    @property
    def open_value(self): 
        return sum(p.size_usd for p in self.open_positions.values())
    
    @property
    def total_value(self): 
        return self.cash + self.open_value
    
    @property
    def total_pnl(self): 
        return self.total_value - self.initial_capital
    
    @property
    def pnl_percent(self):
        if self.initial_capital == 0: 
            return Decimal('0')
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

def _init_tracked_users():
    try:
        if os.path.exists("traders.json"):
            with open("traders.json") as f:
                return json.load(f)
    except:
        pass
    return list(Config.TRACKED_USERS)

app_state = {
    "running":       False,
    "scan_count":    0,
    "portfolio":     Portfolio(),
    "trade_history": [],
    "tracked_users": _init_tracked_users(),
    "poly_client":   None,
    "no_cash_notified": False,
    "seen_conditions": set(),
}

# ==================== TELEGRAM ====================
class TelegramNotifier:
    def __init__(self):
        self.token   = os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(ssl=True)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, *_):
        if self.session: 
            await self.session.close()

    async def send(self, msg: str):
        if not self.token or not self.chat_id:
            logging.warning("Telegram token/chat_id eksik!")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            async with self.session.post(
                url, 
                json={
                    "chat_id": self.chat_id,
                    "text": msg[:4096],
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                },
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                result = await resp.json()
                if resp.status == 200:
                    logging.info("Telegram mesaji gonderildi!")
                else:
                    logging.error(f"Telegram API hatasi {resp.status}: {result}")
        except Exception as e:
            logging.error(f"Telegram hatasi: {e}")

# ==================== TRACKER ====================
class UserTracker:
    def __init__(self, users):
        self.users       = users
        self.session     = None
        self.last_req    = 0
        saved_tx = load_seen_tx()
        self.seen_tx = {u["wallet"]: saved_tx.get(u["wallet"], set()) for u in users}
        if saved_tx:
            total = sum(len(v) for v in self.seen_tx.values())
            logging.info(f"seen_tx yuklendi: {total} tx")
        self.initialized = {u["wallet"]: False for u in users}

    async def _get(self, url):
        now = time.time()
        wait = 0.5 - (now - self.last_req)
        if wait > 0: 
            await asyncio.sleep(wait)
        self.last_req = time.time()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as e:
            logging.debug(f"Request error: {e}")
            return None

    async def get_new_trades(self, user):
        w    = user["wallet"]
        url  = f"{Config.DATA_API}/activity?user={w}&limit=10&type=TRADE"
        data = await self._get(url)
        if not data or not isinstance(data, list): 
            return []
        new = []
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
            try:
                trade_ts = act.get("timestamp") or act.get("createdAt") or act.get("blockTimestamp") or 0
                if isinstance(trade_ts, str):
                    from datetime import datetime
                    trade_ts = datetime.fromisoformat(trade_ts.replace("Z", "+00:00")).timestamp()
                trade_ts = float(trade_ts)
                age = now_ts - trade_ts
                logging.debug(f"Trade yasi: {age:.0f}s - {tx[:10]}")
                if age > 300 or age < -60:
                    logging.info(f"Eski/gecersiz islem atlandi ({age:.0f}s): {tx[:10]}...")
                    continue
            except Exception as ts_err:
                logging.warning(f"Timestamp hatasi, islem atlaniyor: {ts_err}")
                continue
            try:
                size = Decimal(str(act.get("usdcSize", "0")))
            except:
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

    async def scan_all(self):
        trades = []
        for u in list(self.users):
            trades.extend(await self.get_new_trades(u))
        return trades

# ==================== POZISYON KONTROL ====================
async def check_closed_positions(poly, portfolio, notifier):
    """Polymarket'ten pozisyon durumunu kontrol et ve kapananlari temizle"""
    if not portfolio.open_positions:
        return
    
    closed = []
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            # 1. Son fiyati kontrol et
            url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
            resp = requests.get(url, timeout=5)
            current_price = 0.5
            if resp.status_code == 200:
                data = resp.json()
                current_price = float(data.get("price", 0.5))
            
            # Market kapandi mi? (fiyat 0.99+ veya 0.01-)
            if current_price >= 0.99:
                pnl = pos.size_usd / pos.entry_price * (Decimal("0.99") - pos.entry_price)
                portfolio.cash += pos.size_usd + pnl
                portfolio.realized_pnl += pnl
                portfolio.winning_trades += 1
                closed.append((pos.market_title, float(pnl), "KAZANDI"))
                del portfolio.open_positions[pos_id]
                logging.info(f"Pozisyon kapandi (KAZANDI): {pos.market_title}")
                
            elif current_price <= 0.01:
                pnl = pos.size_usd / pos.entry_price * (Decimal("0.01") - pos.entry_price)
                portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                portfolio.realized_pnl += pnl
                portfolio.losing_trades += 1
                closed.append((pos.market_title, float(pnl), "KAYBETTI"))
                del portfolio.open_positions[pos_id]
                logging.info(f"Pozisyon kapandi (KAYBETTI): {pos.market_title}")
            else:
                # 2. Gamma API'den pozisyon hala acik mi kontrol et
                if pos.condition_id:
                    gamma_url = f"https://gamma-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET or Config.EOA_ADDRESS}&conditionId={pos.condition_id}"
                    try:
                        gamma_resp = requests.get(gamma_url, timeout=5)
                        if gamma_resp.status_code == 200:
                            gamma_data = gamma_resp.json()
                            if not gamma_data or len(gamma_data) == 0:
                                # Pozisyon manuel kapatilmis
                                pnl = pos.size_usd / pos.entry_price * (Decimal(str(current_price)) - pos.entry_price)
                                portfolio.cash += pos.size_usd + pnl
                                portfolio.realized_pnl += pnl
                                if pnl >= 0:
                                    portfolio.winning_trades += 1
                                else:
                                    portfolio.losing_trades += 1
                                status = "KAZANDI" if pnl >= 0 else "KAYBETTI"
                                closed.append((pos.market_title, float(pnl), f"MANUEL_{status}"))
                                del portfolio.open_positions[pos_id]
                                logging.info(f"Pozisyon manuel kapandi: {pos.market_title}")
                    except Exception as e:
                        logging.debug(f"Gamma kontrol hatasi: {e}")
                        
        except Exception as e:
            logging.error(f"Pozisyon kontrol hatasi ({pos_id}): {e}")
    
    if closed:
        save_portfolio(portfolio)
        msg = "📊 POZISYONLAR KAPANDI\\n"
        for title, pnl, result in closed:
            sign = "+" if pnl >= 0 else ""
            emoji = "✅" if "KAZANDI" in result else "❌"
            msg += f"{emoji} {result}: {title[:30]} ({sign}${pnl:.2f})\\n"
        await notifier.send(msg)

# ==================== GERCEK POZISYON DEGERI ====================
def get_real_open_positions_value() -> Decimal:
    """Polymarket'ten gercek acik pozisyon degerini cek"""
    wallet = Config.DEPOSIT_WALLET or Config.EOA_ADDRESS
    if not wallet:
        return Decimal("0")
    try:
        url = f"https://data-api.polymarket.com/positions?user={wallet}&sizeThreshold=0.01"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            positions = resp.json()
            total_value = Decimal("0")
            for p in positions:
                value = Decimal(str(p.get("value", 0) or 0))
                total_value += value
            logging.info(f"Gercek pozisyon degeri: ${total_value:.2f}")
            return total_value.quantize(Decimal("0.01"))
    except Exception as e:
        logging.error(f"Gercek pozisyon degeri hatasi: {e}")
    return Decimal("0")

def get_real_positions() -> List[Dict]:
    """Polymarket'ten gercek acik pozisyonlari cek"""
    wallet = Config.DEPOSIT_WALLET or Config.EOA_ADDRESS
    if not wallet:
        return []
    try:
        url = f"https://data-api.polymarket.com/positions?user={wallet}&sizeThreshold=0.01"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        logging.error(f"Gercek pozisyon cekme hatasi: {e}")
    return []

# ==================== BOT ====================
async def run_bot():
    app_state["running"] = True
    poly = PolymarketClient()
    app_state["poly_client"] = poly

    # Portfolio dosyadan yukle (HER MODDA)
    saved = load_portfolio()
    if saved:
        app_state["portfolio"] = saved
        for pos_id in saved.open_positions:
            app_state["seen_conditions"].add(pos_id)
        logging.info(f"Portfolio yuklendi: {len(saved.open_positions)} pozisyon, Nakit: ${saved.cash:.2f}")
    else:
        logging.info("Yeni portfolio olusturuluyor")
        app_state["portfolio"].cash = Config.INITIAL_CAPITAL
        app_state["portfolio"].initial_capital = Config.INITIAL_CAPITAL
        save_portfolio(app_state["portfolio"])

    portfolio = app_state["portfolio"]

    # Baslangicta gercek bakiyeyi cek
    if not Config.TEST_MODE and poly.client:
        poly.sync_portfolio_balance(portfolio)
        # Gercek pozisyonlari cek ve senkronize et
        try:
            real_positions = get_real_positions()
            logging.info(f"Polymarket'te {len(real_positions)} gercek pozisyon bulundu")
            for p in real_positions:
                cond_id = p.get("conditionId", "")
                if cond_id:
                    app_state["seen_conditions"].add(cond_id)
        except Exception as e:
            logging.error(f"Pozisyon senkronizasyon hatasi: {e}")
        open_value = sum(p.size_usd for p in portfolio.open_positions.values())
        portfolio.initial_capital = portfolio.cash + open_value
        logging.info(f"Portfoy senkronize: Cash=${portfolio.cash:.2f}, Toplam=${portfolio.initial_capital:.2f}")

    mod = "TEST" if Config.TEST_MODE else "GERCEK"
    wallet_display = Config.DEPOSIT_WALLET[:10] + "..." if Config.DEPOSIT_WALLET else (Config.EOA_ADDRESS[:10] + "..." if Config.EOA_ADDRESS else "Bilinmiyor")
    
    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"🤖 BOT v5.4 BASLADI\\n"
            f"Mod: *{mod}*\\n"
            f"Trade boyutu: ${Config.TRADE_SIZE}\\n"
            f"Trader sayisi: {len(app_state['tracked_users'])}\\n"
            f"Cuzdan: `{wallet_display}`"
        )

    tracker = UserTracker(list(app_state["tracked_users"]))

    while app_state["running"]:
        app_state["scan_count"] += 1

        try:
            async with aiohttp.ClientSession() as sess:
                tracker.session = sess
                trades = await tracker.scan_all()
                logging.info(f"scan_all() returned {len(trades)} trades")
                for i, t in enumerate(trades):
                    logging.info(f"Trade #{i}: user={t.get('tracked_user','?')} side={t.get('side','?')} title={t.get('title','?')} tx={t.get('transactionHash','?')[:15]}")

            async with TelegramNotifier() as notifier:
                # ONCE pozisyon kontrolu yap
                await check_closed_positions(poly, portfolio, notifier)
                
                for act in trades:
                    side       = act.get("side", "").upper()
                    name       = act.get("tracked_user", "?")
                    title      = str(act.get("title", act.get("question", "Bilinmiyor")))[:60]
                    token_id   = act.get("tokenId", act.get("conditionId", ""))
                    outcome_i  = act.get("outcomeIndex", 0)
                    outcome    = "YES" if outcome_i == 0 else "NO"
                    condition_id = act.get("conditionId", "")

                    try:
                        price = float(act.get("price", 0.5))
                        price = min(max(price, 0.01), 0.99)
                    except:
                        price = 0.5
                    
                    if price < 0.05:
                        logging.info(f"Cok ucuz market atlaniyor: fiyat=${price:.3f}")
                        continue

                    condition_id_short = str(condition_id)[:20] if condition_id else str(token_id)[:20]
                    pos_id = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}"

                    if side == "BUY":
                        raw_title = act.get("title") or act.get("question") or act.get("marketTitle") or act.get("slug", "").replace("-", " ")
                        title = str(raw_title).strip()[:120] if raw_title else ""

                        logging.info(f"RAW ACT: conditionId={condition_id or 'YOK'} tokenId={act.get('tokenId','YOK')} title={act.get('title','YOK')} outcome={outcome_i} trader={name}")
                        logging.info(f"BLACKLIST CHECK: title='{title}'")

                        if not title:
                            logging.warning("Bos title, atlaniyor")
                            continue

                        title_lower = title.lower()
                        blacklisted = False
                        for banned in Config.BLACKLIST_MARKETS:
                            if banned in title_lower:
                                logging.info(f"KARA LISTE (title): '{banned}' bulundu: '{title}'")
                                blacklisted = True
                                break
                        if blacklisted:
                            continue

                        slug = str(act.get("slug", "")).lower()
                        for banned in Config.BLACKLIST_MARKETS:
                            if banned in slug:
                                logging.info(f"KARA LISTE (slug): '{banned}' bulundu")
                                blacklisted = True
                                break
                        if blacklisted:
                            continue

                        actual_token_id = act.get("tokenId", "")
                        actual_condition_id = act.get("conditionId", "")
                        if actual_token_id and actual_token_id in Config.BLACKLIST_TOKEN_IDS:
                            logging.info("KARA LISTE (tokenId)")
                            continue
                        if actual_condition_id and actual_condition_id in Config.BLACKLIST_CONDITION_IDS:
                            logging.info(f"KARA LISTE (conditionId): {actual_condition_id[:20]}")
                            continue

                        if pos_id in portfolio.open_positions:
                            continue
                            
                        condition_key = condition_id or ""
                        if condition_key and condition_key in app_state["seen_conditions"]:
                            logging.debug(f"Ayni conditionId zaten islendi, atlaniyor")
                            continue
                        if condition_key:
                            app_state["seen_conditions"].add(condition_key)
                            
                        real_cash = poly.get_real_balance() if not Config.TEST_MODE else portfolio.cash
                        if real_cash < Config.MIN_CASH:
                            if not app_state["no_cash_notified"]:
                                await notifier.send(f"⚠️ [NAKİT YETERSİZ] Gercek bakiye: ${real_cash:.2f}")
                                app_state["no_cash_notified"] = True
                            continue
                        app_state["no_cash_notified"] = False

                        direct_token = act.get("asset", "")
                        if direct_token:
                            token_id = direct_token
                            logging.info(f"Direkt asset kullaniliyor: {token_id[:20]}...")
                            
                        trade_amount = float(Config.TRADE_SIZE)
                        logging.info(f"Trade boyutu: ${trade_amount:.2f} (sabit TRADE_SIZE)")
                        result = poly.buy(token_id, outcome_i, price, trade_amount)

                        if result is not None:
                            pos = Position(
                                position_id=pos_id,
                                trader_name=name,
                                market_title=title,
                                token_id=token_id,
                                side=outcome,
                                entry_price=Decimal(str(price)),
                                size_usd=Config.TRADE_SIZE,
                                condition_id=condition_id or "",
                            )
                            portfolio.open_positions[pos_id] = pos
                            portfolio.total_trades += 1

                            if not Config.TEST_MODE:
                                portfolio.cash = poly.get_real_balance()
                            else:
                                portfolio.cash -= Config.TRADE_SIZE
                            
                            save_portfolio(portfolio)  # HER ZAMAN KAYDET

                            sign = "+" if portfolio.total_pnl >= 0 else ""
                            await notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}📈 POZİSYON AÇILDI\\n\\n"
                                f"Trader: *{name}*\\n"
                                f"Market: {title}\\n"
                                f"Yön: *{outcome}*\\n"
                                f"Fiyat: ${price:.3f}\\n"
                                f"Boyut: ${Config.TRADE_SIZE}\\n\\n"
                                f"💰 Nakit: ${portfolio.cash:.2f}\\n"
                                f"📊 PnL: {sign}${portfolio.total_pnl:.2f}"
                            )

                    elif side == "SELL":
                        if pos_id not in portfolio.open_positions:
                            continue
                        pos = portfolio.open_positions[pos_id]

                        result = poly.sell(token_id, outcome_i, price, float(pos.size_usd))

                        if result is not None:
                            shares = pos.size_usd / pos.entry_price
                            pnl = shares * (Decimal(str(price)) - pos.entry_price)
                            portfolio.realized_pnl += pnl
                            if pnl >= 0:
                                portfolio.winning_trades += 1
                            else:
                                portfolio.losing_trades += 1

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

                            if not Config.TEST_MODE:
                                portfolio.cash = poly.get_real_balance()
                            else:
                                portfolio.cash += pos.size_usd + pnl
                            
                            save_portfolio(portfolio)  # HER ZAMAN KAYDET

                            ts = "+" if pnl >= 0 else ""
                            wr = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
                            await notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}📉 POZİSYON KAPANDI\\n\\n"
                                f"Trader: *{pos.trader_name}*\\n"
                                f"Market: {pos.market_title}\\n"
                                f"PnL: {ts}${abs(float(pnl)):.2f}\\n\\n"
                                f"💰 Nakit: ${portfolio.cash:.2f}\\n"
                                f"🏆 Win Rate: {wr:.0f}% ({portfolio.winning_trades}W/{portfolio.losing_trades}L)"
                            )

            # STOP-LOSS kontrolu
            if not Config.TEST_MODE and poly.client:
                async with TelegramNotifier() as sl_notifier:
                    for pos_id, pos in list(portfolio.open_positions.items()):
                        try:
                            url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
                            resp = requests.get(url, timeout=5)
                            if resp.status_code == 200:
                                data = resp.json()
                                current_price = float(data.get("price", pos.entry_price))
                                loss_pct = (float(pos.entry_price) - current_price) / float(pos.entry_price) * 100
                                if loss_pct >= 50:
                                    logging.info(f"STOP-LOSS: {pos.market_title} %{loss_pct:.0f} zarar, satiliyor...")
                                    sl_result = poly.sell(pos.token_id, 1, current_price, float(pos.size_usd))
                                    if sl_result:
                                        pnl = Decimal(str(current_price - float(pos.entry_price))) * (pos.size_usd / pos.entry_price)
                                        portfolio.cash += pos.size_usd + pnl
                                        portfolio.realized_pnl += pnl
                                        if pnl >= 0:
                                            portfolio.winning_trades += 1
                                        else:
                                            portfolio.losing_trades += 1
                                        del portfolio.open_positions[pos_id]
                                        save_portfolio(portfolio)
                                        await sl_notifier.send(
                                            f"🛑 STOP-LOSS TETIKLENDI\\n"
                                            f"Market: {pos.market_title}\\n"
                                            f"Zarar: %{loss_pct:.0f}\\n"
                                            f"PnL: -${abs(float(pnl)):.2f}"
                                        )
                        except Exception as e:
                            logging.error(f"Stop-loss kontrol hatasi: {e}")

            # Bakiye senkronizasyonu (her 10 taramada bir)
            if app_state["scan_count"] % 10 == 0 and not Config.TEST_MODE and poly.client:
                poly.sync_portfolio_balance(portfolio)

            # seen_tx kaydet (her 5 taramada bir)
            if app_state["scan_count"] % 5 == 0:
                save_seen_tx(tracker.seen_tx)

            # Rapor (her 20 taramada bir)
            if app_state["scan_count"] % 20 == 0:
                async with TelegramNotifier() as notifier:
                    # Gercek pozisyon degerini hesapla
                    real_open_value = get_real_open_positions_value() if not Config.TEST_MODE else portfolio.open_value
                    total_val = portfolio.cash + real_open_value
                    sign = "+" if portfolio.total_pnl >= 0 else ""
                    await notifier.send(
                        f"📊 [RAPOR] Tarama #{app_state['scan_count']}\\n"
                        f"💰 Nakit: ${portfolio.cash:.2f}\\n"
                        f"📈 Acik Pozisyon: ${real_open_value:.2f}\\n"
                        f"💵 Toplam: ${total_val:.2f}\\n"
                        f"📉 PnL: {sign}${total_val - float(portfolio.initial_capital):.2f}\\n"
                        f"🎯 Acik: {len(portfolio.open_positions)} | Trade: {portfolio.total_trades}"
                    )

        except Exception as e:
            logging.error(f"Scan hatasi: {e}")

        await asyncio.sleep(Config.SCAN_INTERVAL)

    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"🛑 [BOT DURDURULDU]\\n"
            f"Toplam: ${portfolio.total_value:.2f}\\n"
            f"PnL: ${portfolio.total_pnl:.2f}\\n"
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
    portfolio = app_state["portfolio"]
    poly = app_state.get("poly_client")
    
    real_cash = float(portfolio.cash)
    if poly and poly.client and not Config.TEST_MODE:
        try:
            real_cash = float(poly.get_real_balance())
            portfolio.cash = Decimal(str(real_cash))
        except:
            pass
    
    real_positions = get_real_positions()
    real_positions_value = sum(float(p.get("value", 0) or 0) for p in real_positions)
    
    portfolio_dict = portfolio.to_dict()
    portfolio_dict["cash"] = real_cash
    portfolio_dict["real_positions_count"] = len(real_positions)
    portfolio_dict["real_positions_value"] = real_positions_value
    portfolio_dict["total_value"] = real_cash + real_positions_value
    
    return jsonify({
        "running":       app_state["running"],
        "scan_count":    app_state["scan_count"],
        "test_mode":     Config.TEST_MODE,
        "portfolio":     portfolio_dict,
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

def save_traders():
    try:
        with open("traders.json", "w") as f:
            json.dump(app_state["tracked_users"], f, indent=2)
    except Exception as e:
        logging.error(f"Trader kayit hatasi: {e}")

def load_traders():
    try:
        if os.path.exists("traders.json"):
            with open("traders.json") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Trader yukle hatasi: {e}")
    return list(Config.TRACKED_USERS)

@flask_app.route("/api/traders", methods=["POST"])
def add_trader():
    data   = request.json or {}
    name   = data.get("name", "").strip()
    wallet = data.get("wallet", "").strip().lower()
    if not name or not wallet:
        return jsonify({"ok": False, "msg": "Isim ve cuzdan gerekli"})
    if any(u["wallet"] == wallet for u in app_state["tracked_users"]):
        return jsonify({"ok": False, "msg": "Bu trader zaten listede"})
    app_state["tracked_users"].append({"name": name, "wallet": wallet})
    save_traders()
    return jsonify({"ok": True, "msg": f"{name} eklendi"})

@flask_app.route("/api/traders/<wallet>", methods=["DELETE"])
def del_trader(wallet):
    app_state["tracked_users"] = [u for u in app_state["tracked_users"] if u["wallet"] != wallet]
    save_traders()
    return jsonify({"ok": True, "msg": "Trader silindi"})

@flask_app.route("/api/close-all", methods=["POST"])
def close_all_positions():
    portfolio = app_state["portfolio"]
    if not portfolio.open_positions:
        return jsonify({"ok": False, "msg": "Açık pozisyon yok"})
    count = len(portfolio.open_positions)
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                current_price = float(resp.json().get("price", float(pos.entry_price)))
            else:
                current_price = float(pos.entry_price)
        except:
            current_price = float(pos.entry_price)
        pnl = pos.size_usd / pos.entry_price * (Decimal(str(current_price)) - pos.entry_price)
        portfolio.cash += pos.size_usd + pnl
        portfolio.realized_pnl += pnl
        if pnl >= 0:
            portfolio.winning_trades += 1
        else:
            portfolio.losing_trades += 1
        del portfolio.open_positions[pos_id]
    save_portfolio(portfolio)
    msg = f"{count} pozisyon kapatıldı"
    logging.info(msg)
    return jsonify({"ok": True, "msg": msg, "count": count})

@flask_app.route("/api/cancel-all", methods=["POST"])
def cancel_all():
    poly = app_state.get("poly_client")
    if not poly:
        poly = PolymarketClient()
    result = poly.cancel_all_orders()
    if "error" in result:
        return jsonify({"ok": False, "msg": result["error"]})
    cancelled = result.get("cancelled", 0)
    test_suffix = " (TEST)" if result.get("test") else ""
    msg = f"{cancelled} adet emir iptal edildi{test_suffix}"
    logging.info(msg)
    async def _notify():
        async with TelegramNotifier() as n:
            await n.send(f"🚫 TÜM EMİRLER İPTAL EDİLDİ\\n{cancelled} emir iptal edildi{test_suffix}")
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_notify())
        loop.close()
    except Exception as e:
        logging.warning(f"Telegram bildirim hatasi: {e}")
    return jsonify({"ok": True, "msg": msg, "cancelled": cancelled})

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=" * 50)
    print("  POLYMARKET BOT v5.4")
    print(f"  EOA Address: {'OK' if Config.EOA_ADDRESS else 'EKSIK'}")
    print(f"  Deposit Wallet: {'OK' if Config.DEPOSIT_WALLET else 'AUTO/Otomatik'}")
    print(f"  Private Key: {'OK' if Config.PRIVATE_KEY else 'EKSIK'}")
    print(f"  CLOB API: {'OK' if Config.CLOB_API_KEY else 'EKSIK'}")
    print(f"  Builder API: {'OK' if Config.BUILDER_API_KEY else 'EKSIK (Opsiyonel)'}")
    print(f"  Telegram: {'OK' if Config.TELEGRAM_TOKEN else 'EKSIK'}")
    print(f"  Mod: {'TEST' if Config.TEST_MODE else 'GERCEK'}")
    print("=" * 50)
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        t = threading.Thread(target=start_bot_thread, daemon=True)
        t.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False)
'''

print(f"Boyut: {len(code)} karakter")
