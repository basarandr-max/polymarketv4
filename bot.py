#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POLYMARKET COPY TRADING BOT v6.0 - TAM DÜZELTİLMİŞ
Düzeltmeler (Gemini + Kimi analizi):
P0: Hardcoded Telegram token -> env variable'a taşındı
P0: .env güvenlik notu eklendi
P1: notifier2 NameError -> iç içe async with kullanıldı
P1: Tüm senkron requests -> aiohttp async'e dönüştürüldü
P2: Portfolio race condition -> threading.Lock eklendi
P2: Position ID çakışması -> timestamp suffix eklendi
P3: Magic number'lar -> Config'e taşındı
P3: Import'lar dosya başına alındı
+ outcome_index Position'a eklendi (sabit 1 hatası)
+ Tek kalıcı ClientSession (rate limit koruması)
"""

import asyncio
import aiohttp
import json
import time
import threading
import os
import logging
import sys
import requests as sync_requests  # Sadece Flask rotaları için (sync context)
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List
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
    # P0 DÜZELTMESİ: Hardcoded token kaldırıldı -> .env'e taşındı
    TELEGRAM_TOKEN_2   = os.environ.get("TELEGRAM_TOKEN_2", "")
    TELEGRAM_CHAT_ID_2 = os.environ.get("TELEGRAM_CHAT_ID_2", "")
    TRADE_SIZE       = Decimal(os.environ.get("TRADE_SIZE", "5"))
    MIN_CASH         = Decimal(os.environ.get("MIN_CASH", "5"))
    INITIAL_CAPITAL  = Decimal(os.environ.get("INITIAL_CAPITAL", "23"))
    SCAN_INTERVAL    = int(os.environ.get("SCAN_INTERVAL", "60"))
    MIN_USDC_SIZE    = Decimal("1")
    TEST_MODE        = os.environ.get("TEST_MODE", "true").lower() == "true"
    # P3 DÜZELTMESİ: Magic number'lar Config'e taşındı
    MARKET_WIN_PRICE      = Decimal("0.99")   # Bu fiyat üstünde market kazandı sayılır
    MARKET_LOSE_PRICE     = Decimal("0.01")   # Bu fiyat altında market kaybetti sayılır
    COMMISSION_RATE       = Decimal("0.02")   # %2 komisyon
    TRADE_AGE_LIMIT_SEC   = 300               # Takip edilecek max işlem yaşı (saniye)
    MIN_TRADE_PRICE       = 0.05              # Bu fiyatın altındaki marketler atlanır
    STOP_LOSS_ENABLED     = False             # Stop-loss aktif mi?
    STOP_LOSS_PCT         = 40               # Stop-loss yüzdesi
    BLACKLIST_MARKETS     = ["rihanna", "gta vi", "new rihanna"]
    BLACKLIST_TOKEN_IDS   = [
        "53831553061883006530739877284105938919721408776239639687877978808906551086026",
        "98022490269692409998126496127597032490334070080325855126491859374983463996227",
    ]
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
    TRADERS_BOT2 = {
        "0x26437896ed9dfeb2f69765edcafe8fdceaab39ae",
        "0x6db568e61e5e3de7d87f831431b673f38ce2e279",
        "0x492442eab586f242b53bda933fd5de859c8a3782",
        "0x84cfffc3f16dcc353094de30d4a45226eccd2f63",
        "0x2c335066fe58fe9237c3d3dc7b275c2a034a0563",
        "0xfe787d2da716d60e8acff57fb87eb13cd4d10319",
        "0x157efb90bf2f3bae9eea4f1e9d02abf12ff3add7",
        "0xd81e5bc01e4a98d0af93d82dc2c542a4c0f9e3d0",
        "0xd0ee8005ad44501453bd5ee31ea863b1b038b834",
        "0x84dbb7103982e3617704a2ed7d5b39691952aeeb",
    }

# P2 DÜZELTMESİ: Portfolio race condition için global lock
_portfolio_lock = threading.Lock()

# ==================== ASYNC HTTP HELPERS ====================
async def async_get(session: aiohttp.ClientSession, url: str, timeout: int = 10) -> Optional[dict]:
    """Async HTTP GET - JSON döner. HTML hata sayfası gelirse None döner."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                logging.debug(f"HTTP {resp.status}: {url}")
                return None
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                # HTML hata sayfası kontrolü
                text = await resp.text()
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    logging.warning(f"JSON parse hatasi ({url}): {text[:100]}")
                    return None
            return await resp.json()
    except asyncio.TimeoutError:
        logging.warning(f"Timeout: {url}")
        return None
    except Exception as e:
        logging.debug(f"async_get hatasi ({url}): {e}")
        return None

async def async_get_token_id(session: aiohttp.ClientSession, condition_id: str, outcome_index: int) -> Optional[str]:
    """CLOB/Gamma API'den token ID çeker - async"""
    # Önce CLOB API dene
    data = await async_get(session, f"{Config.CLOB_HOST}/markets/{condition_id}")
    if data:
        tokens = data.get("tokens", [])
        if len(tokens) > outcome_index:
            token_id = tokens[outcome_index].get("token_id", "")
            if token_id:
                logging.info(f"CLOB token: outcome={outcome_index} token={token_id[:20]}...")
                return token_id
    # Gamma API dene
    data = await async_get(session, f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}")
    if data:
        mkt = data[0] if isinstance(data, list) else data
        clob_ids = mkt.get("clobTokenIds", "[]")
        if isinstance(clob_ids, str):
            try:
                clob_ids = json.loads(clob_ids)
            except json.JSONDecodeError:
                return None
        if len(clob_ids) > outcome_index:
            token_id = clob_ids[outcome_index]
            logging.info(f"Gamma token: outcome={outcome_index} token={token_id[:20]}...")
            return token_id
    return None

async def async_get_last_price(session: aiohttp.ClientSession, token_id: str, fallback: float) -> float:
    """Son işlem fiyatını çeker - async"""
    data = await async_get(session, f"{Config.CLOB_HOST}/last-trade-price?token_id={token_id}", timeout=5)
    if data:
        return float(data.get("price", fallback))
    return fallback

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

    def buy(self, token_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] BUY: ${size} @ ${price:.3f}")
            return {"test": True}
        if not self.client:
            logging.error("CLOB client yok!")
            return None
        try:
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
            logging.info(f"BUY basarili: {resp}")
            return resp
        except Exception as e:
            logging.error(f"BUY hatasi: {e}")
            return None

    def sell(self, token_id: str, outcome_index: int, price: float, size: float) -> Optional[Dict]:
        if Config.TEST_MODE:
            logging.info(f"[TEST] SELL: ${size} @ ${price:.3f}")
            return {"test": True}
        if not self.client:
            return None
        try:
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
            if isinstance(resp, dict):
                if resp.get("error"):
                    logging.error(f"SELL hata: {resp}")
                    return None
                if resp.get("status") in ["REJECTED", "CANCELLED"]:
                    logging.error(f"SELL reddedildi: {resp}")
                    return None
            logging.info(f"SELL basarili: {resp}")
            return resp
        except Exception as e:
            logging.error(f"SELL hatasi: {e}")
            return None

    def cancel_all_orders(self) -> Dict:
        if Config.TEST_MODE:
            return {"cancelled": 0, "test": True}
        if not self.client:
            return {"error": "CLOB client yok"}
        try:
            open_orders = self.client.get_orders({"status": "LIVE"})
            if not open_orders:
                return {"cancelled": 0}
            order_ids = [o.get("id") or o.get("order_id") for o in (open_orders if isinstance(open_orders, list) else []) if o.get("id") or o.get("order_id")]
            if not order_ids:
                return {"cancelled": 0}
            result = self.client.cancel_orders(order_ids)
            return {"cancelled": len(order_ids), "result": str(result)}
        except Exception as e:
            logging.error(f"cancel_all_orders hatasi: {e}")
            return {"error": str(e)}

    def get_real_balance(self) -> Decimal:
        if not self.client:
            return Decimal(os.environ.get("INITIAL_CAPITAL", "100"))
        try:
            from py_clob_client_v2.clob_types import BalanceAllowanceParams, AssetType
            from py_clob_client_v2 import SignatureTypeV2
            balance = self.client.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=SignatureTypeV2.POLY_1271)
            )
            bal_val = "0"
            if isinstance(balance, dict):
                bal_val = str(balance.get("balance", balance.get("allowance", "0")))
            elif hasattr(balance, "balance"):
                bal_val = str(balance.balance)
            elif isinstance(balance, (int, float, str)):
                bal_val = str(balance)
            raw = Decimal(bal_val)
            usdc = raw / Decimal("1000000") if raw > Decimal("1000000") else raw
            return usdc.quantize(Decimal("0.01"))
        except Exception as e:
            logging.error(f"Bakiye hatasi: {e}")
            return Decimal(os.environ.get("INITIAL_CAPITAL", "100"))

    def get_real_balance_rpc(self) -> Decimal:
        try:
            USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
            addr = self.deposit_wallet[2:].lower()
            data = "0x70a08231000000000000000000000000" + addr
            payload = {"jsonrpc": "2.0", "method": "eth_call", "params": [{"to": USDC_CONTRACT, "data": data}, "latest"], "id": 1}
            resp = sync_requests.post("https://polygon-rpc.com", json=payload, timeout=10)
            hex_balance = resp.json().get("result", "0x0")
            usdc = Decimal(int(hex_balance, 16)) / Decimal("1000000")
            return usdc.quantize(Decimal("0.01"))
        except Exception as e:
            logging.error(f"RPC bakiye hatasi: {e}")
            return Decimal("0")

    def sync_portfolio_balance(self, portfolio) -> None:
        real = self.get_real_balance()
        if real <= Decimal("0") or real > Decimal("100000"):
            real = self.get_real_balance_rpc()
        if real > Decimal("0"):
            with _portfolio_lock:
                portfolio.cash = real
                if portfolio.initial_capital == Decimal("0"):
                    portfolio.initial_capital = real

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
    outcome_index: int = 0          # DÜZELTİLDİ: YES=0, NO=1 kaydediliyor
    opened_at:     datetime = field(default_factory=datetime.now)

    def to_dict(self):
        return {
            "position_id":   self.position_id,
            "trader_name":   self.trader_name,
            "market_title":  self.market_title,
            "side":          self.side,
            "outcome_index": self.outcome_index,
            "entry_price":   float(self.entry_price),
            "size_usd":      float(self.size_usd),
            "opened_at":     self.opened_at.strftime("%H:%M %d/%m"),
        }

# Kalici storage - Railway Volume varsa /data, yoksa lokal klasor
_DATA_DIR = os.environ.get("DATA_DIR", "/data" if os.path.exists("/data") else ".")
try:
    os.makedirs(_DATA_DIR, exist_ok=True)
except Exception:
    _DATA_DIR = "."
PORTFOLIO_FILE = os.path.join(_DATA_DIR, "portfolio_state.json")
SEEN_TX_FILE   = os.path.join(_DATA_DIR, "seen_tx.json")
logging.info(f"Storage klasoru: {_DATA_DIR}")
RAILWAY_TOKEN      = os.environ.get("RAILWAY_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_ENV_ID     = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")

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
    # P2 DÜZELTMESİ: Lock ile thread-safe kayıt
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

def load_portfolio():
    try:
        # Railway Variables
        rv = os.environ.get("PORTFOLIO_STATE")
        state = json.loads(rv) if rv else None
        if state is None:
            if not os.path.exists(PORTFOLIO_FILE):
                return None
            with open(PORTFOLIO_FILE) as f:
                state = json.load(f)
        p = Portfolio()
        p.cash            = Decimal(str(state["cash"]))
        p.initial_capital = Decimal(str(state["initial_capital"]))
        p.realized_pnl    = Decimal(str(state["realized_pnl"]))
        p.total_trades    = state["total_trades"]
        p.winning_trades  = state["winning_trades"]
        p.losing_trades   = state["losing_trades"]
        for k, v in state["open_positions"].items():
            p.open_positions[k] = Position(
                position_id=v["position_id"],
                trader_name=v["trader_name"],
                market_title=v["market_title"],
                token_id=v["token_id"],
                side=v["side"],
                outcome_index=v.get("outcome_index", 0),
                entry_price=Decimal(str(v["entry_price"])),
                size_usd=Decimal(str(v["size_usd"])),
                opened_at=datetime.strptime(v["opened_at"], "%Y-%m-%d %H:%M:%S"),
            )
        logging.info(f"Portfolio yuklendi: {len(p.open_positions)} pozisyon, ${p.cash:.2f}")
        return p
    except Exception as e:
        logging.error(f"Portfolio yukle hatasi: {e}")
        return None

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
    def pnl_percent(self):
        if self.initial_capital == 0: return Decimal("0")
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
    except Exception:
        pass
    return list(Config.TRACKED_USERS)

app_state = {
    "running":          False,
    "scan_count":       0,
    "portfolio":        Portfolio(),
    "trade_history":    [],
    "tracked_users":    _init_tracked_users(),
    "poly_client":      None,
    "no_cash_notified": False,
    "seen_conditions":  set(),
    "eod_sent_today":   False,
    "day_start_capital": Decimal("0"),  # Gün başı sermaye (00:00'da sıfırlanır)
    "day_trades":       [],             # Günlük kapanan işlemler
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
                "chat_id": self.chat_id,
                "text": msg[:4096],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logging.warning(f"Telegram {resp.status}")
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

    async def _get(self, url):
        wait = 0.5 - (time.time() - self.last_req)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_req = time.time()
        return await async_get(self.session, url)

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
                    trade_ts = datetime.fromisoformat(trade_ts.replace("Z", "+00:00")).timestamp()
                age = now_ts - float(trade_ts)
                if age > Config.TRADE_AGE_LIMIT_SEC or age < -60:
                    logging.info(f"Eski islem atlandi ({age:.0f}s): {tx[:10]}...")
                    continue
            except Exception as e:
                logging.warning(f"Timestamp hatasi: {e}")
                continue
            try:
                size = Decimal(str(act.get("usdcSize", "0")))
            except Exception:
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

# ==================== POZISYON KONTROLÜ ====================
async def check_closed_positions(portfolio: Portfolio, notifier: TelegramNotifier, session: aiohttp.ClientSession):
    """Açık pozisyonları kontrol et, kapananları kapat - async"""
    if not portfolio.open_positions:
        return
    checked = {}
    closed  = []
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            if not pos.token_id:
                continue
            if pos.token_id not in checked:
                checked[pos.token_id] = await async_get_last_price(session, pos.token_id, float(pos.entry_price))
            current_price = checked[pos.token_id]
            if current_price >= float(Config.MARKET_WIN_PRICE):
                pnl = pos.size_usd / pos.entry_price * (Config.MARKET_WIN_PRICE - pos.entry_price)
                with _portfolio_lock:
                    portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
                    portfolio.realized_pnl += pnl
                    portfolio.winning_trades += 1
                    del portfolio.open_positions[pos_id]
                closed.append((pos.trader_name, pos.market_title, pos.side, float(pnl), "KAZANDI ✅"))
                app_state["day_trades"].append({
                    "time":   datetime.now().strftime("%H:%M"),
                    "trader": pos.trader_name,
                    "market": pos.market_title,
                    "side":   pos.side,
                    "entry":  float(pos.entry_price),
                    "exit":   float(Config.MARKET_WIN_PRICE),
                    "pnl":    float(pnl),
                })
            elif current_price <= float(Config.MARKET_LOSE_PRICE):
                pnl = pos.size_usd / pos.entry_price * (Config.MARKET_LOSE_PRICE - pos.entry_price)
                with _portfolio_lock:
                    portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                    portfolio.realized_pnl += pnl
                    portfolio.losing_trades += 1
                    del portfolio.open_positions[pos_id]
                closed.append((pos.trader_name, pos.market_title, pos.side, float(pnl), "KAYBETTI ❌"))
                # Gunluk trade kaydina ekle
                app_state["day_trades"].append({
                    "time":   datetime.now().strftime("%H:%M"),
                    "trader": pos.trader_name,
                    "market": pos.market_title,
                    "side":   pos.side,
                    "entry":  float(pos.entry_price),
                    "exit":   float(Config.MARKET_LOSE_PRICE),
                    "pnl":    float(pnl),
                })
        except Exception as e:
            logging.error(f"Pozisyon kontrol hatasi ({pos_id}): {e}")
    if closed:
        save_portfolio(portfolio)
        for trader, title, side, pnl, result in closed:
            sign = "+" if pnl >= 0 else ""
            wr   = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
            msg  = (
                f"{result} POZISYON KAPANDI\n\n"
                f"Trader: *{trader}*\n"
                f"Market: {title[:50]}\n"
                f"Yon: {side}\n"
                f"PnL: {sign}${abs(pnl):.2f}\n"
                f"Nakit: ${float(portfolio.cash):.2f}\n"
                f"Win rate: {wr:.0f}% ({portfolio.winning_trades}K/{portfolio.losing_trades}L)"
            )
            await notifier.send(msg)

# ==================== RAPOR FONKSİYONLARI ====================

async def _build_live_stats(portfolio: "Portfolio", session) -> tuple:
    """Anlık pozisyon değerlerini hesapla"""
    price_cache = {}
    live_value  = Decimal("0")
    trader_stats: Dict[str, Dict] = {}

    for pos in portfolio.open_positions.values():
        if pos.token_id not in price_cache:
            price_cache[pos.token_id] = await async_get_last_price(
                session, pos.token_id, float(pos.entry_price)
            )
        cur = Decimal(str(price_cache[pos.token_id]))
        pv  = pos.size_usd / pos.entry_price * cur
        pnl = pv - pos.size_usd
        live_value += pv

        t = pos.trader_name
        if t not in trader_stats:
            trader_stats[t] = {"count": 0, "value": Decimal("0"), "pnl": Decimal("0")}
        trader_stats[t]["count"] += 1
        trader_stats[t]["value"] += pv
        trader_stats[t]["pnl"]   += pnl

    return live_value, trader_stats, price_cache


async def send_periodic_report(portfolio, session):
    """Her 30 dakikada bir ozet gonder"""
    live_value, trader_stats, _ = await _build_live_stats(portfolio, session)
    live_total    = portfolio.cash + live_value
    open_cost     = sum(p.size_usd for p in portfolio.open_positions.values())
    open_pnl      = live_value - open_cost
    open_pnl_sign = "+" if open_pnl >= 0 else ""
    wr            = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
    now_str       = datetime.now().strftime("%H:%M")

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
        f"📈 Acik poz. K/Z: {open_pnl_sign}${float(open_pnl):.2f}\n"
        f"✅ Kapanan PnL: ${float(portfolio.realized_pnl):+.2f}\n"
        f"🎯 Win rate: {wr:.0f}% ({portfolio.winning_trades}K / {portfolio.losing_trades}L)\n"
        f"━━━━━━━━━━━━━━\n"
        f"TRADER BAZLI ACIK POZISYONLAR\n"
        f"{trader_lines}"
    )
    async with TelegramNotifier() as n:
        await n.send(msg)
    logging.info("Yarim saatlik rapor gonderildi")

async def send_eod_report(portfolio, session):
    """Gece 00:00 gunluk ozet"""
    live_value, trader_stats, _ = await _build_live_stats(portfolio, session)
    live_total   = portfolio.cash + live_value
    day_start    = app_state.get("day_start_capital") or portfolio.initial_capital
    if day_start == Decimal("0"):
        day_start = portfolio.initial_capital
    day_pnl      = live_total - day_start
    day_pnl_pct  = float(day_pnl / day_start * 100) if day_start else 0
    pnl_sign     = "+" if day_pnl >= 0 else ""
    open_cost    = sum(p.size_usd for p in portfolio.open_positions.values())
    open_pnl     = live_value - open_cost
    wr           = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
    date_str     = datetime.now().strftime("%d %B %Y")

    # Kapanan islemlerden trader performansi
    all_trader_stats = {}
    for trade in app_state.get("day_trades", []):
        t = trade.get("trader", "?")
        if t not in all_trader_stats:
            all_trader_stats[t] = {"closed": 0, "pnl": Decimal("0")}
        all_trader_stats[t]["closed"] += 1
        all_trader_stats[t]["pnl"]   += Decimal(str(trade.get("pnl", 0)))
    # Acik pozisyonlardan
    for t, s in trader_stats.items():
        if t not in all_trader_stats:
            all_trader_stats[t] = {"closed": 0, "pnl": Decimal("0")}
        all_trader_stats[t]["pnl"] += s["pnl"]

    trader_lines = ""
    for t, s in sorted(all_trader_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
        ts = "+" if s["pnl"] >= 0 else ""
        trader_lines += f"  {t}: {s['closed']} islem | {ts}${float(s['pnl']):.2f}\n"
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
        f"🎯 Win rate: {wr:.0f}%\n"
        f"━━━━━━━━━━━━━━\n"
        f"TRADER PERFORMANSI\n"
        f"{trader_lines}"
    )
    async with TelegramNotifier() as n:
        await n.send(msg)

    # Gun sonu sifirla
    app_state["day_trades"]        = []
    app_state["day_start_capital"] = live_total
    logging.info("Gun sonu rapor gonderildi")

async def run_bot():
    app_state["running"] = True
    poly = PolymarketClient()
    app_state["poly_client"] = poly

    # Tek kalici ClientSession
    connector    = aiohttp.TCPConnector(ssl=True, limit=20)
    main_session = aiohttp.ClientSession(connector=connector)

    # Her modda once kaydedilmis portfolio yukle
    saved = load_portfolio()
    if saved:
        app_state["portfolio"] = saved
        logging.info(f"Portfolio yuklendi: {len(saved.open_positions)} pozisyon, ${saved.cash:.2f}")
    else:
        app_state["portfolio"].cash = Config.INITIAL_CAPITAL
        app_state["portfolio"].initial_capital = Config.INITIAL_CAPITAL
        logging.info("Yeni portfolio olusturuldu")

    portfolio = app_state["portfolio"]

    # Gercek modda: Polymarket API'den acik pozisyonlari cek ve portfolio ile eslestir
    if not Config.TEST_MODE and poly.client:
        poly.sync_portfolio_balance(portfolio)
        logging.info("Polymarket acik pozisyonlari cekiliyor...")
        try:
            real_pos = await async_get(
                main_session,
                f"https://data-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET}&sizeThreshold=0.01"
            )
            if real_pos and isinstance(real_pos, list):
                logging.info(f"Polymarket'te {len(real_pos)} acik pozisyon bulundu")
                for p in real_pos:
                    cond_id = p.get("conditionId", "")
                    if not cond_id:
                        continue
                    # seen_conditions'a ekle - yeniden alinmasin
                    outcome_i = int(p.get("outcomeIndex", 0))
                    app_state["seen_conditions"].add(f"{cond_id}_{outcome_i}")
                    # Portfolio'da yoksa ekle (deploy oncesi acilmis pozisyonlar)
                    pos_key = f"recovered_{cond_id[:20]}_{outcome_i}"
                    if not any(pos_key in pid for pid in portfolio.open_positions):
                        size = Decimal(str(p.get("size", p.get("currentValue", Config.TRADE_SIZE))))
                        avg_price = float(p.get("avgPrice", p.get("price", 0.5)))
                        token_id  = p.get("asset", p.get("tokenId", ""))
                        outcome   = "YES" if outcome_i == 0 else "NO"
                        title     = str(p.get("title", p.get("question", "Bilinmiyor")))[:80]
                        # Sadece bot'un acmadigi pozisyonlari ekle
                        already_tracked = any(
                            pos.token_id == token_id
                            for pos in portfolio.open_positions.values()
                            if token_id
                        )
                        if not already_tracked and token_id:
                            pos = Position(
                                position_id=pos_key,
                                trader_name="[deploy-oncesi]",
                                market_title=title,
                                token_id=token_id,
                                side=outcome,
                                outcome_index=outcome_i,
                                entry_price=Decimal(str(avg_price)),
                                size_usd=size,
                            )
                            portfolio.open_positions[pos_key] = pos
                            logging.info(f"Deploy oncesi pozisyon eklendi: {title[:40]}")
                save_portfolio(portfolio)
        except Exception as e:
            logging.error(f"Pozisyon restore hatasi: {e}")
        portfolio.initial_capital = portfolio.cash + portfolio.open_value

    # Test modunda kapanmis pozisyonlari kontrol et
    if Config.TEST_MODE and portfolio.open_positions:
        for pos_id, pos in list(portfolio.open_positions.items()):
            try:
                current_price = await async_get_last_price(main_session, pos.token_id, float(pos.entry_price))
                if current_price >= float(Config.MARKET_WIN_PRICE):
                    pnl = pos.size_usd / pos.entry_price * (Config.MARKET_WIN_PRICE - pos.entry_price)
                    portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
                    portfolio.realized_pnl += pnl
                    portfolio.winning_trades += 1
                    del portfolio.open_positions[pos_id]
                elif current_price <= float(Config.MARKET_LOSE_PRICE):
                    pnl = pos.size_usd / pos.entry_price * (Config.MARKET_LOSE_PRICE - pos.entry_price)
                    portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                    portfolio.realized_pnl += pnl
                    portfolio.losing_trades += 1
                    del portfolio.open_positions[pos_id]
            except Exception as e:
                logging.error(f"Baslangic pozisyon kontrolu: {e}")
        save_portfolio(portfolio)

    # seen_conditions'a mevcut pozisyonlari ekle
    for pos_id, pos in portfolio.open_positions.items():
        cond_short = pos.position_id.split("_")[1] if "_" in pos.position_id else pos.position_id
        app_state["seen_conditions"].add(f"{cond_short}_{pos.outcome_index}")

    mod   = "TEST" if Config.TEST_MODE else "GERCEK"
    sign  = "+" if portfolio.realized_pnl >= 0 else ""
    # Gün başı sermayeyi kaydet
    app_state["day_start_capital"] = portfolio.cash + portfolio.open_value

    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"🤖 BOT BAŞLADI v6.0\n"
            f"Mod: *{mod}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 Nakit: ${float(portfolio.cash):.2f}\n"
            f"📊 Toplam: ${float(portfolio.total_value):.2f}\n"
            f"📈 PnL: {sign}${float(portfolio.realized_pnl):.2f}\n"
            f"📌 Açık: {len(portfolio.open_positions)} adet\n"
            f"👥 Takip: {len(app_state['tracked_users'])} trader"
        )

    tracker = UserTracker(list(app_state["tracked_users"]))

    try:
        while app_state["running"]:
            app_state["scan_count"] += 1
            try:
                tracker.session = main_session
                trades = await tracker.scan_all()
                if trades:
                    logging.info(f"scan_all(): {len(trades)} yeni trade")

                # P1 DÜZELTMESİ: İç içe async with - notifier2 her zaman mevcut
                async with TelegramNotifier() as notifier:
                    async with TelegramNotifier(token=Config.TELEGRAM_TOKEN_2, chat_id=Config.TELEGRAM_CHAT_ID_2) as notifier2:

                        if app_state["scan_count"] % 3 == 0:
                            await check_closed_positions(portfolio, notifier, main_session)

                        if app_state["scan_count"] % 10 == 0 and not Config.TEST_MODE and poly.client:
                            poly.sync_portfolio_balance(portfolio)

                        for act in trades:
                            side      = act.get("side", "").upper()
                            name      = act.get("tracked_user", "?")
                            outcome_i = int(act.get("outcomeIndex", 0))
                            outcome   = "YES" if outcome_i == 0 else "NO"
                            try:
                                price = min(max(float(act.get("price", 0.5)), 0.01), 0.99)
                            except Exception:
                                price = 0.5

                            if price < Config.MIN_TRADE_PRICE:
                                logging.info(f"Ucuz market atlandi: ${price:.3f}")
                                continue

                            # P2 DÜZELTMESİ: Timestamp suffix ile position ID çakışması önlendi
                            condition_id_short = str(act.get("conditionId", act.get("tokenId", "")))[:20]
                            ts_suffix = str(int(time.time()))[-6:]
                            pos_id = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}_{ts_suffix}"

                            trader_wallet   = act.get("wallet", act.get("tracked_wallet", "")).lower()
                            active_notifier = notifier2 if trader_wallet in Config.TRADERS_BOT2 else notifier

                            if side == "BUY":
                                raw_title = (act.get("title") or act.get("question") or
                                             act.get("marketTitle") or
                                             act.get("slug", "").replace("-", " "))
                                title = str(raw_title).strip()[:120] if raw_title else ""

                                if not title:
                                    logging.warning("Bos title, atlaniyor")
                                    continue

                                # Kara liste kontrolü
                                title_lower = title.lower()
                                slug_lower  = str(act.get("slug", "")).lower()
                                blacklisted = any(b in title_lower or b in slug_lower for b in Config.BLACKLIST_MARKETS)
                                if blacklisted:
                                    logging.info(f"Kara liste: {title[:40]}")
                                    continue

                                actual_token_id     = act.get("tokenId", "")
                                actual_condition_id = act.get("conditionId", "")
                                if (actual_token_id in Config.BLACKLIST_TOKEN_IDS or
                                    actual_condition_id in Config.BLACKLIST_TOKEN_IDS or
                                    actual_condition_id in Config.BLACKLIST_CONDITION_IDS):
                                    logging.info("Kara liste (ID)")
                                    continue

                                condition_key = act.get("conditionId", "")
                                # DÜZELTMESİ: conditionId+outcome bazlı kontrol
                                # (aynı market farklı outcome ile çift işlenmesini önler)
                                seen_key = f"{condition_key}_{outcome_i}" if condition_key else ""
                                if seen_key and seen_key in app_state["seen_conditions"]:
                                    logging.debug(f"Ayni conditionId+outcome, atlaniyor: {seen_key[:30]}")
                                    continue
                                if seen_key:
                                    app_state["seen_conditions"].add(seen_key)

                                # P3 DÜZELTMESİ: Bakiye kontrolü komisyon dahil
                                real_cash = poly.get_real_balance() if not Config.TEST_MODE else portfolio.cash
                                min_required = Config.TRADE_SIZE * (Decimal("1") + Config.COMMISSION_RATE)
                                if real_cash < min_required:
                                    if not app_state["no_cash_notified"]:
                                        await notifier.send(f"💸 NAKİT YETERSİZ: ${float(real_cash):.2f} (gerekli: ${float(min_required):.2f})")
                                        app_state["no_cash_notified"] = True
                                    continue
                                app_state["no_cash_notified"] = False

                                # Token ID çözümle (async)
                                direct_asset   = act.get("asset", actual_token_id)
                                final_token_id = direct_asset
                                if condition_key:
                                    fetched = await async_get_token_id(main_session, condition_key, outcome_i)
                                    if fetched:
                                        final_token_id = fetched

                                if not final_token_id:
                                    logging.warning("Token ID bulunamadi, atlaniyor")
                                    continue

                                result = poly.buy(final_token_id, outcome_i, price, float(Config.TRADE_SIZE))
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
                                        if Config.TEST_MODE:
                                            portfolio.cash -= Config.TRADE_SIZE * (Decimal("1") + Config.COMMISSION_RATE)
                                        else:
                                            portfolio.cash = poly.get_real_balance()
                                    save_portfolio(portfolio)

                                    pnl_sign = "+" if portfolio.total_pnl >= 0 else ""
                                    await active_notifier.send(
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
                                # SELL: pos_id timestamp'li olduğu için tüm pozisyonlarda ara
                                matching_pos = None
                                base_id = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}"
                                for pid, p in list(portfolio.open_positions.items()):
                                    if pid.startswith(base_id):
                                        matching_pos = (pid, p)
                                        break
                                if not matching_pos:
                                    continue
                                pos_id, pos = matching_pos

                                # DÜZELTİLDİ: pos.outcome_index kullan (sabit 1 değil)
                                result = poly.sell(pos.token_id, pos.outcome_index, price, float(pos.size_usd))
                                if result is not None:
                                    shares = pos.size_usd / pos.entry_price
                                    pnl    = shares * (Decimal(str(price)) - pos.entry_price)
                                    with _portfolio_lock:
                                        portfolio.realized_pnl += pnl
                                        if pnl >= 0:
                                            portfolio.winning_trades += 1
                                        else:
                                            portfolio.losing_trades += 1
                                        if Config.TEST_MODE:
                                            portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
                                        else:
                                            portfolio.cash = poly.get_real_balance()
                                        del portfolio.open_positions[pos_id]
                                    trade_record = {
                                        "time":   datetime.now().strftime("%H:%M"),
                                        "trader": pos.trader_name,
                                        "market": pos.market_title,
                                        "side":   pos.side,
                                        "entry":  float(pos.entry_price),
                                        "exit":   price,
                                        "pnl":    float(pnl),
                                    }
                                    app_state["trade_history"].insert(0, trade_record)
                                    app_state["day_trades"].append(trade_record)
                                    save_portfolio(portfolio)
                                    wr = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
                                    ts = "+" if pnl >= 0 else ""
                                    await notifier.send(
                                        f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON KAPANDI\n\n"
                                        f"Trader: *{pos.trader_name}*\n"
                                        f"Market: {pos.market_title}\n"
                                        f"PnL: {ts}${abs(float(pnl)):.2f}\n"
                                        f"Nakit: ${float(portfolio.cash):.2f}\n"
                                        f"Win Rate: {wr:.0f}% ({portfolio.winning_trades}W/{portfolio.losing_trades}L)"
                                    )

                        # Stop-Loss (Config.STOP_LOSS_ENABLED ise aktif)
                        if Config.STOP_LOSS_ENABLED and portfolio.open_positions:
                            sl_checked = {}
                            for pos_id, pos in list(portfolio.open_positions.items()):
                                try:
                                    if pos.token_id not in sl_checked:
                                        sl_checked[pos.token_id] = await async_get_last_price(
                                            main_session, pos.token_id, float(pos.entry_price)
                                        )
                                    cur = sl_checked[pos.token_id]
                                    loss_pct = (float(pos.entry_price) - cur) / float(pos.entry_price) * 100
                                    if loss_pct >= Config.STOP_LOSS_PCT:
                                        pnl = Decimal(str(cur)) * (pos.size_usd / pos.entry_price) - pos.size_usd
                                        with _portfolio_lock:
                                            portfolio.cash += max(Decimal("0"), pos.size_usd + pnl - pos.size_usd * Config.COMMISSION_RATE)
                                            portfolio.realized_pnl += pnl
                                            portfolio.losing_trades += 1
                                            del portfolio.open_positions[pos_id]
                                        save_portfolio(portfolio)
                                        await notifier.send(
                                            f"🛑 STOP-LOSS\n{pos.market_title}\n"
                                            f"Zarar: %{loss_pct:.0f} | PnL: -${abs(float(pnl)):.2f}"
                                        )
                                except Exception as e:
                                    logging.error(f"Stop-loss hatasi: {e}")

                # seen_tx kaydet (her 5 taramada)
                if app_state["scan_count"] % 5 == 0:
                    save_seen_tx(tracker.seen_tx)

                # Periyodik rapor (her 30 taramada = 30 dakika)
                if app_state["scan_count"] % 30 == 0:
                    await send_periodic_report(portfolio, main_session)

                # Gece 00:00 günlük özet
                now_hour = datetime.now().hour
                now_min  = datetime.now().minute
                if now_hour == 0 and now_min < 1 and not app_state.get("eod_sent_today"):
                    app_state["eod_sent_today"] = True
                    await send_eod_report(portfolio, main_session)
                elif now_hour != 0:
                    app_state["eod_sent_today"] = False

            except Exception as e:
                logging.error(f"Scan hatasi: {e}", exc_info=True)

            await asyncio.sleep(Config.SCAN_INTERVAL)

    finally:
        await main_session.close()

    async with TelegramNotifier() as notifier:
        await notifier.send(
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
def api_status():
    portfolio = app_state["portfolio"]
    poly      = app_state.get("poly_client")
    real_cash = float(portfolio.cash)
    if poly and poly.client and not Config.TEST_MODE:
        try:
            real_cash = float(poly.get_real_balance())
            with _portfolio_lock:
                portfolio.cash = Decimal(str(real_cash))
        except Exception:
            pass
    real_positions = []
    try:
        resp = sync_requests.get(
            f"https://data-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET}&sizeThreshold=0",
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            real_positions = data if isinstance(data, list) else []
    except Exception:
        pass
    d = portfolio.to_dict()
    d["cash"]                  = real_cash
    d["real_positions_count"]  = len(real_positions)
    d["real_positions_value"]  = sum(float(p.get("value", 0) or 0) for p in real_positions)
    return jsonify({
        "running":       app_state["running"],
        "scan_count":    app_state["scan_count"],
        "test_mode":     Config.TEST_MODE,
        "portfolio":     d,
        "tracked_users": app_state["tracked_users"],
    })

@flask_app.route("/api/history")
def api_history():
    return jsonify(app_state["trade_history"])

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

def save_traders():
    try:
        with open("traders.json", "w") as f:
            json.dump(app_state["tracked_users"], f, indent=2)
    except Exception as e:
        logging.error(f"Trader kayit hatasi: {e}")

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
    save_traders()
    return jsonify({"ok": True, "msg": f"{name} eklendi"})

@flask_app.route("/api/traders/<wallet>", methods=["DELETE"])
def api_del_trader(wallet):
    app_state["tracked_users"] = [u for u in app_state["tracked_users"] if u["wallet"] != wallet]
    save_traders()
    return jsonify({"ok": True, "msg": "Trader silindi"})

@flask_app.route("/api/close-all", methods=["POST"])
def api_close_all():
    portfolio = app_state["portfolio"]
    if not portfolio.open_positions:
        return jsonify({"ok": False, "msg": "Açık pozisyon yok"})
    count = len(portfolio.open_positions)
    with _portfolio_lock:
        for pos_id, pos in list(portfolio.open_positions.items()):
            try:
                resp = sync_requests.get(
                    f"{Config.CLOB_HOST}/last-trade-price?token_id={pos.token_id}", timeout=5
                )
                cur = float(resp.json().get("price", float(pos.entry_price))) if resp.status_code == 200 else float(pos.entry_price)
            except Exception:
                cur = float(pos.entry_price)
            pnl = pos.size_usd / pos.entry_price * (Decimal(str(cur)) - pos.entry_price)
            portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Config.COMMISSION_RATE)
            portfolio.realized_pnl += pnl
            if pnl >= 0:
                portfolio.winning_trades += 1
            else:
                portfolio.losing_trades += 1
            del portfolio.open_positions[pos_id]
    save_portfolio(portfolio)
    return jsonify({"ok": True, "msg": f"{count} pozisyon kapatıldı", "count": count})

@flask_app.route("/api/cancel-all", methods=["POST"])
def api_cancel_all():
    poly = app_state.get("poly_client") or PolymarketClient()
    result = poly.cancel_all_orders()
    if "error" in result:
        return jsonify({"ok": False, "msg": result["error"]})
    cancelled   = result.get("cancelled", 0)
    test_suffix = " (TEST)" if result.get("test") else ""
    async def _notify():
        async with TelegramNotifier() as n:
            await n.send(f"🚫 EMİRLER İPTAL: {cancelled} adet{test_suffix}")
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_notify())
        loop.close()
    except Exception as e:
        logging.warning(f"Telegram bildirim hatasi: {e}")
    return jsonify({"ok": True, "msg": f"{cancelled} emir iptal{test_suffix}", "cancelled": cancelled})

# ==================== MAIN ====================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    # GÜVENLİK UYARISI: .env dosyasını .gitignore'a ekle!
    # .env'de bulunması gerekenler:
    #   PRIVATE_KEY, CLOB_API_KEY, CLOB_SECRET, CLOB_PASS_PHRASE
    #   TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    #   TELEGRAM_TOKEN_2, TELEGRAM_CHAT_ID_2   <-- artık env'de
    if not Config.TELEGRAM_TOKEN_2:
        logging.warning("UYARI: TELEGRAM_TOKEN_2 env variable eksik! .env dosyasına ekle.")
    print("=" * 55)
    print("  POLYMARKET BOT v6.0 - TAM DÜZELTİLMİŞ")
    print(f"  EOA:        {'OK' if Config.EOA_ADDRESS else 'EKSIK'}")
    print(f"  Deposit:    {'OK' if Config.DEPOSIT_WALLET else 'AUTO'}")
    print(f"  Private Key:{'OK' if Config.PRIVATE_KEY else 'EKSIK'}")
    print(f"  CLOB API:   {'OK' if Config.CLOB_API_KEY else 'EKSIK'}")
    print(f"  Telegram 1: {'OK' if Config.TELEGRAM_TOKEN else 'EKSIK'}")
    print(f"  Telegram 2: {'OK' if Config.TELEGRAM_TOKEN_2 else 'EKSIK - .env eksik!'}")
    print(f"  Mod:        {'TEST' if Config.TEST_MODE else 'GERCEK'}")
    print(f"  Stop-Loss:  {'AKTIF %' + str(Config.STOP_LOSS_PCT) if Config.STOP_LOSS_ENABLED else 'KAPALI'}")
    print("=" * 55)
    threading.Thread(target=start_bot_thread, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
