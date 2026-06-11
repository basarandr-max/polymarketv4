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
    INITIAL_CAPITAL  = Decimal(os.environ.get("INITIAL_CAPITAL", "23"))
    SCAN_INTERVAL    = 60
    MIN_USDC_SIZE    = Decimal("1")
    TEST_MODE        = os.environ.get("TEST_MODE", "true").lower() == "true"
    BLACKLIST_MARKETS = ["rihanna", "gta vi", "new rihanna"]
    BLACKLIST_TOKEN_IDS = [
        "53831553061883006530739877284105938919721408776239639687877978808906551086026",
        "98022490269692409998126496127597032490334070080325855126491859374983463996227",
    ]
    BLACKLIST_CONDITION_IDS = [
        "0x1fad72fae204143ff1c3035e99e7c0f65ea8d5cd9bd1070987bd1a3316f772be",
    ]
    TRACKED_USERS: List[Dict] = [
        {"name": "Swisstony",              "wallet": "0x204f72f35326db932158cba6adff0b9a1da95e14"},
        {"name": "Latina",                "wallet": "0x26437896ed9dfeb2f69765edcafe8fdceaab39ae"},
        {"name": "Anon2",                 "wallet": "0x6db568e61e5e3de7d87f831431b673f38ce2e279"},
        {"name": "Anon3",                 "wallet": "0x492442eab586f242b53bda933fd5de859c8a3782"},
        {"name": "mooseborzoi",           "wallet": "0x84cfffc3f16dcc353094de30d4a45226eccd2f63"},
        {"name": "Anon5",                 "wallet": "0x2c335066fe58fe9237c3d3dc7b275c2a034a0563"},
        {"name": "ferrariChampions2026",  "wallet": "0xfe787d2da716d60e8acff57fb87eb13cd4d10319"},
        {"name": "resadasdasd",           "wallet": "0x157efb90bf2f3bae9eea4f1e9d02abf12ff3add7"},
        {"name": "beet420",              "wallet": "0xd81e5bc01e4a98d0af93d82dc2c542a4c0f9e3d0"},
        {"name": "izebel",               "wallet": "0xd0ee8005ad44501453bd5ee31ea863b1b038b834"},
        {"name": "Soarin22",             "wallet": "0x84dbb7103982e3617704a2ed7d5b39691952aeeb"},
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
        import requests, json
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
            return {"test": True}
        if not self.client:
            logging.error("CLOB client yok!")
            return None
        try:
            # Eger condition_id zaten bir token ID ise (64+ haneli hex), direkt kullan
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
            return {"test": True}
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
        """Tüm açık BUY emirlerini iptal et"""
        if Config.TEST_MODE:
            logging.info("[TEST] Tüm emirler iptal edildi (simülasyon)")
            return {"cancelled": 0, "test": True}
        if not self.client:
            logging.error("CLOB client yok!")
            return {"error": "CLOB client yok"}
        try:
            # Açık emirleri listele
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
            # Toplu iptal
            result = self.client.cancel_orders(order_ids)
            logging.info(f"İptal sonucu: {result}")
            return {"cancelled": len(order_ids), "result": str(result)}
        except Exception as e:
            logging.error(f"cancel_all_orders hatasi: {e}")
            return {"error": str(e)}

    def get_real_balance(self) -> Decimal:
        """Polymarket CLOB API'den bakiye çek"""
        if not self.client:
            return Decimal(os.environ.get("INITIAL_CAPITAL", "100"))
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
            return Decimal(os.environ.get("INITIAL_CAPITAL", "100"))

    def get_real_balance_rpc(self) -> Decimal:
        """Polygon RPC'den direkt USDC bakiyesi çek"""
        try:
            import requests
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
        # API yanlış dönerse RPC'den dene
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

PORTFOLIO_FILE = "portfolio_state.json"
SEEN_TX_FILE = "seen_tx.json"

# Railway Variables API - kalici storage
RAILWAY_TOKEN = os.environ.get("RAILWAY_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_ENV_ID = os.environ.get("RAILWAY_ENVIRONMENT_ID", "")

def save_state_to_env(key: str, value: str):
    """Railway Variables'a kaydet (kalici)"""
    if not RAILWAY_TOKEN or not RAILWAY_PROJECT_ID:
        return False
    try:
        import requests as req
        url = f"https://backboard.railway.app/graphql/v2"
        query = """
        mutation UpsertVariables($input: VariableCollectionUpsertInput!) {
            variableCollectionUpsert(input: $input)
        }
        """
        variables = {
            "input": {
                "projectId": RAILWAY_PROJECT_ID,
                "environmentId": RAILWAY_ENV_ID,
                "serviceId": os.environ.get("RAILWAY_SERVICE_ID", ""),
                "variables": {key: value}
            }
        }
        resp = req.post(url, 
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {RAILWAY_TOKEN}"},
            timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logging.error(f"Railway env kayit hatasi: {e}")
        return False

def load_state_from_env(key: str) -> Optional[str]:
    """Railway Variables'dan oku"""
    return os.environ.get(key, None)

def save_seen_tx(seen_tx):
    try:
        import json
        data = {w: list(txs) for w, txs in seen_tx.items()}
        json_str = json.dumps(data)
        with open(SEEN_TX_FILE, "w") as f:
            f.write(json_str)
        # Railway Variables boyut siniri nedeniyle atlandi
    except Exception as e:
        logging.error(f"seen_tx kayit hatasi: {e}")

def load_seen_tx():
    try:
        import json
        # Önce Railway Variables'dan oku
        railway_state = load_state_from_env("SEEN_TX_STATE")
        if railway_state:
            try:
                data = json.loads(railway_state)
                logging.info(f"seen_tx Railway Variables'dan yuklendi: {sum(len(v) for v in data.values())} tx")
                return {w: set(txs) for w, txs in data.items()}
            except:
                pass
        # Dosyadan oku
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
        import json
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
            } for k, v in portfolio.open_positions.items()}
        }
        json_str = json.dumps(state)
        # Dosyaya kaydet
        with open(PORTFOLIO_FILE, "w") as f:
            f.write(json_str)
        # Railway Variables kaydi devre disi (redeploy dongusunu onlemek icin)
    except Exception as e:
        logging.error(f"Portfolio kayit hatasi: {e}")

def load_portfolio():
    try:
        import json
        # Önce Railway Variables'dan oku
        railway_state = load_state_from_env("PORTFOLIO_STATE")
        if railway_state:
            try:
                state = json.loads(railway_state)
                logging.info("Portfolio Railway Variables'dan yuklendi")
            except:
                state = None
        else:
            state = None
        # Railway'de yoksa dosyadan oku
        if state is None:
            if not os.path.exists(PORTFOLIO_FILE):
                return None
            with open(PORTFOLIO_FILE) as f:
                state = json.load(f)
            logging.info("Portfolio dosyadan yuklendi")
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
            )
            p.open_positions[k] = pos
        logging.info(f"Portfolio yuklendi: {len(p.open_positions)} pozisyon, Nakit: ${p.cash:.2f}")
        return p
    except Exception as e:
        logging.error(f"Portfolio yukle hatasi: {e}")
        return None

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

def _init_tracked_users():
    import json
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
    def __init__(self, token=None, chat_id=None):
        self.token   = token or os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.session = None

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(ssl=True)
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
                "text": msg[:4096],
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    logging.info("Telegram mesaji gonderildi!")
                else:
                    logging.warning(f"Telegram {resp.status}: {await resp.json()}")
        except Exception as e:
            logging.error(f"Telegram hatasi: {e}")

# ==================== TRACKER ====================

# 2. Telegram botu - yeni traderlar için
TELEGRAM_TOKEN_2   = "8871608668:AAGlB43XPp3Bg0fGvcb443FGbrUas8ht6RQ"
TELEGRAM_CHAT_ID_2 = "-5183465250"

# Hangi traderlar 2. bota bildirim gönderir
TRADERS_BOT2 = {
    "0x26437896ed9dfeb2f69765edcafe8fdceaab39ae",  # Latina
    "0x6db568e61e5e3de7d87f831431b673f38ce2e279",  # Anon2
    "0x492442eab586f242b53bda933fd5de859c8a3782",  # Anon3
    "0x84cfffc3f16dcc353094de30d4a45226eccd2f63",  # mooseborzoi
    "0x2c335066fe58fe9237c3d3dc7b275c2a034a0563",  # Anon5
    "0xfe787d2da716d60e8acff57fb87eb13cd4d10319",  # ferrariChampions2026
    "0x157efb90bf2f3bae9eea4f1e9d02abf12ff3add7",  # resadasdasd
    "0xd81e5bc01e4a98d0af93d82dc2c542a4c0f9e3d0",  # beet420
    "0xd0ee8005ad44501453bd5ee31ea863b1b038b834",  # izebel
    "0x84dbb7103982e3617704a2ed7d5b39691952aeeb",  # Soarin22
}

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
        if wait > 0: await asyncio.sleep(wait)
        self.last_req = time.time()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json() if r.status == 200 else None
        except Exception as e:
            logging.debug(f"Request error: {e}"); return None

    async def get_new_trades(self, user):
        w    = user["wallet"]
        url  = f"{Config.DATA_API}/activity?user={w}&limit=10&type=TRADE"
        data = await self._get(url)
        if not data or not isinstance(data, list): return []
        new = []
        now_ts = time.time()
        for act in data:
            tx = act.get("transactionHash", "")
            if not tx: continue
            if not self.initialized[w]:
                self.seen_tx[w].add(tx); continue
            if tx in self.seen_tx[w]: continue
            self.seen_tx[w].add(tx)
            # Timestamp kontrolu - sadece son 5 dakika
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
async def sync_open_positions_from_ui(poly, portfolio):
    """Polymarket UI'dan açık pozisyonları çek ve senkronize et"""
    try:
        import requests
        url = f"https://gamma-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET}&active=true"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            positions = resp.json()
            logging.info(f"UI'dan {len(positions)} acik pozisyon bulundu")
            # Bot'un takip etmediği pozisyonları temizle
            if not positions:
                portfolio.open_positions.clear()
                logging.info("Acik pozisyon yok, portfoy temizlendi")
        else:
            logging.warning(f"Pozisyon cekme hatasi: {resp.status_code}")
    except Exception as e:
        logging.error(f"Pozisyon senkronizasyon hatasi: {e}")


async def check_closed_positions(portfolio, notifier):
    """Her taramada pozisyonları kontrol et - kapananları kapat"""
    import requests as req
    if not portfolio.open_positions:
        return
    # Benzersiz token_id'leri topla - tekrar sorgu yapma
    checked_tokens = {}
    closed = []
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            if not pos.token_id:
                continue
            # Aynı token'ı birden fazla sorgulama
            if pos.token_id in checked_tokens:
                current_price = checked_tokens[pos.token_id]
            else:
                url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
                resp = req.get(url, timeout=5)
                if resp.status_code != 200:
                    continue
                current_price = float(resp.json().get("price", 0))
                checked_tokens[pos.token_id] = current_price
            if current_price >= 0.99:
                pnl = pos.size_usd / pos.entry_price * (Decimal("0.99") - pos.entry_price)
                portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
                portfolio.realized_pnl += pnl
                portfolio.winning_trades += 1
                closed.append((pos.market_title, float(pnl), "KAZANDI ✅"))
                del portfolio.open_positions[pos_id]
                logging.info(f"Pozisyon kapandi KAZANDI: {pos.market_title} PnL: +${float(pnl):.2f}")
            elif current_price <= 0.01:
                pnl = pos.size_usd / pos.entry_price * (Decimal("0.01") - pos.entry_price)
                portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                portfolio.realized_pnl += pnl
                portfolio.losing_trades += 1
                closed.append((pos.market_title, float(pnl), "KAYBETTI ❌"))
                del portfolio.open_positions[pos_id]
                logging.info(f"Pozisyon kapandi KAYBETTI: {pos.market_title} PnL: ${float(pnl):.2f}")
        except Exception as e:
            logging.error(f"Pozisyon kontrol hatasi ({pos_id}): {e}")
    if closed:
        save_portfolio(portfolio)
        msg = "📊 POZİSYONLAR KAPANDI\n"
        for title, pnl, result in closed:
            sign = "+" if pnl >= 0 else ""
            msg += f"{result}: {title[:35]} ({sign}${pnl:.2f})\n"
        await notifier.send(msg)

async def run_bot():
    app_state["running"] = True
    poly = PolymarketClient()
    app_state["poly_client"] = poly

    # Test modunda portfolio dosyadan yukle
    if Config.TEST_MODE:
        saved = load_portfolio()
        if saved:
            app_state["portfolio"] = saved
            # Seen conditions guncelle
            for pos_id in saved.open_positions:
                app_state["seen_conditions"].add(pos_id)
            logging.info(f"Test portfolio yuklendi: {len(saved.open_positions)} pozisyon, Nakit: ${saved.cash:.2f}")
        else:
            logging.info("Yeni test portfolio olusturuluyor")
            app_state["portfolio"].cash = Config.INITIAL_CAPITAL
            app_state["portfolio"].initial_capital = Config.INITIAL_CAPITAL

    portfolio = app_state["portfolio"]

    # Test modunda acik pozisyonlari kontrol et - kapananları kapat
    if Config.TEST_MODE and portfolio.open_positions:
        import requests
        logging.info(f"Acik pozisyonlar kontrol ediliyor: {len(portfolio.open_positions)} adet")
        closed = []
        for pos_id, pos in list(portfolio.open_positions.items()):
            try:
                # Market sonucunu kontrol et
                url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    current_price = float(data.get("price", 0))
                    # Fiyat 0.99+ ise kazandı, 0.01- ise kaybetti - market kapandı
                    if current_price >= 0.99:
                        pnl = pos.size_usd / pos.entry_price * (Decimal("0.99") - pos.entry_price)
                        portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
                        portfolio.realized_pnl += pnl
                        portfolio.winning_trades += 1
                        closed.append((pos.market_title, float(pnl), "KAZANDI"))
                        del portfolio.open_positions[pos_id]
                        logging.info(f"Pozisyon kapandi (KAZANDI): {pos.market_title} PnL: +${float(pnl):.2f}")
                    elif current_price <= 0.01:
                        pnl = pos.size_usd / pos.entry_price * (Decimal("0.01") - pos.entry_price)
                        portfolio.cash += max(Decimal("0"), pos.size_usd + pnl)
                        portfolio.realized_pnl += pnl
                        portfolio.losing_trades += 1
                        closed.append((pos.market_title, float(pnl), "KAYBETTI"))
                        del portfolio.open_positions[pos_id]
                        logging.info(f"Pozisyon kapandi (KAYBETTI): {pos.market_title} PnL: ${float(pnl):.2f}")
            except Exception as e:
                logging.error(f"Pozisyon kontrol hatasi: {e}")
        if closed:
            save_portfolio(portfolio)
            msg = "POZISYONLAR KAPANDI\n"
            for title, pnl, result in closed:
                sign = "+" if pnl >= 0 else ""
                msg += f"{result}: {title[:30]} ({sign}${pnl:.2f})\n"
            logging.info(msg)

    # Başlangıçta gerçek bakiyeyi çek, pozisyonları TEMIZLEME
    logging.info("Bot basliyor, mevcut pozisyonlar korunuyor...")
    if not Config.TEST_MODE and poly.client:
        poly.sync_portfolio_balance(portfolio)
        # Polymarket'ten açık pozisyonları çek ve seen_conditions'a ekle
        try:
            import requests
            url = f"https://data-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET}&sizeThreshold=0.01"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                positions = resp.json()
                logging.info(f"Polymarket'te {len(positions)} acik pozisyon bulundu")
                for p in positions:
                    cond_id = p.get("conditionId", "")
                    if cond_id:
                        app_state["seen_conditions"].add(cond_id)
                logging.info(f"seen_conditions guncellendi: {len(app_state['seen_conditions'])} pozisyon")
        except Exception as e:
            logging.error(f"Pozisyon senkronizasyon hatasi: {e}")
        open_value = sum(p.size_usd for p in portfolio.open_positions.values())
        portfolio.initial_capital = portfolio.cash + open_value
        logging.info(f"Portföy senkronize: Cash=${portfolio.cash:.2f}, Toplam=${portfolio.initial_capital:.2f}")

    mod = "TEST" if Config.TEST_MODE else "GERCEK"
    portfolio = app_state["portfolio"]
    acik = len(portfolio.open_positions)
    nakit = float(portfolio.cash)
    toplam = float(portfolio.cash) + sum(float(p.size_usd) for p in portfolio.open_positions.values())
    pnl = float(portfolio.realized_pnl)
    sign = "+" if pnl >= 0 else ""
    async with TelegramNotifier() as notifier:
        await notifier.send(
            f"🤖 BOT BAŞLADI\n"
            f"Mod: *{mod}*\n"
            f"━━━━━━━━━━━━━━\n"
            f"💰 Nakit: ${nakit:.2f}\n"
            f"📊 Toplam: ${toplam:.2f}\n"
            f"📈 PnL: {sign}${pnl:.2f}\n"
            f"📌 Açık Pozisyon: {acik} adet\n"
            f"━━━━━━━━━━━━━━\n"
            f"👥 Takip: {len(app_state['tracked_users'])} trader"
        )
    logging.info(f"Bot basliyor - Mod: {mod}, Trader: {len(app_state['tracked_users'])}")

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
                # 2. bot notifier
                notifier2 = TelegramNotifier(token=TELEGRAM_TOKEN_2, chat_id=TELEGRAM_CHAT_ID_2)
                await notifier2.__aenter__()
                
                # Her 3 taramada bir pozisyonları kontrol et (API yükü azalt)
                if app_state["scan_count"] % 3 == 0:
                    await check_closed_positions(portfolio, notifier)

                # Gerçek modda bakiye senkronize et (her 10 taramada)
                if app_state["scan_count"] % 10 == 0 and not Config.TEST_MODE and poly.client:
                    poly.sync_portfolio_balance(portfolio)

                for act in trades:
                    side       = act.get("side", "").upper()
                    name       = act.get("tracked_user", "?")
                    title      = str(act.get("title", act.get("question", "Bilinmiyor")))[:60]
                    token_id   = act.get("tokenId", act.get("conditionId", ""))
                    outcome_i  = act.get("outcomeIndex", 0)
                    outcome    = "YES" if outcome_i == 0 else "NO"
                    
                    # Trader wallet'ına göre doğru notifier seç
                    trader_wallet = act.get("wallet", "").lower()
                    active_notifier = notifier2 if trader_wallet in TRADERS_BOT2 else notifier

                    try:
                        price = float(act.get("price", 0.5))
                        price = min(max(price, 0.01), 0.99)
                    except:
                        price = 0.5
                    
                    # Cok ucuz marketleri atla (fiyat < 0.05)
                    if price < 0.05:
                        logging.info(f"Cok ucuz market atlaniyor: fiyat=${price:.3f}")
                        continue

                    # Aynı market için tek pozisyon — conditionId bazlı
                    condition_id_short = str(act.get("conditionId", token_id))[:20]
                    pos_id = f"{act.get('tracked_wallet','')[:8]}_{condition_id_short}_{outcome}"

                    if side == "BUY":
                        # ===== KARA LISTE KONTROLU =====
                        raw_title = act.get("title")
                        if raw_title is None or raw_title == "":
                            raw_title = act.get("question")
                        if raw_title is None or raw_title == "":
                            raw_title = act.get("marketTitle")
                        if raw_title is None or raw_title == "":
                            raw_title = act.get("slug", "").replace("-", " ")
                        title = str(raw_title).strip()[:120] if raw_title else ""

                        logging.info(f"RAW ACT: conditionId={act.get('conditionId','YOK')} tokenId={act.get('tokenId','YOK')} title={act.get('title','YOK')} outcome={act.get('outcomeIndex','YOK')} trader={act.get('tracked_user','?')}")
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
                        if actual_condition_id and actual_condition_id in Config.BLACKLIST_TOKEN_IDS:
                            logging.info("KARA LISTE (conditionId in tokenIds)")
                            continue
                        if actual_condition_id and actual_condition_id in Config.BLACKLIST_CONDITION_IDS:
                            logging.info(f"KARA LISTE (conditionId): {actual_condition_id[:20]}")
                            continue
                        # ===== KARA LISTE SONU =====

                        if pos_id in portfolio.open_positions:
                            continue
                        # Ayni conditionId icin sadece 1 pozisyon
                        condition_key = act.get("conditionId", "")
                        if condition_key and condition_key in app_state["seen_conditions"]:
                            logging.debug(f"Ayni conditionId zaten islendi, atlaniyor")
                            continue
                        if condition_key:
                            app_state["seen_conditions"].add(condition_key)
                        # Gerçek bakiyeyi kontrol et
                        real_cash = poly.get_real_balance() if not Config.TEST_MODE else portfolio.cash
                        if real_cash < Config.MIN_CASH:
                            if not app_state["no_cash_notified"]:
                                await notifier.send(f"[NAKİT YETERSİZ] Gercek bakiye: ${real_cash:.2f}")
                                app_state["no_cash_notified"] = True
                            continue
                        app_state["no_cash_notified"] = False

                        # CLOB API'den doğrudan token bul
                        condition_id = act.get("conditionId", "")
                        direct_asset = act.get("asset", "")
                        token_id = direct_asset  # default
                        
                        if condition_id:
                            try:
                                import requests as req_clob
                                # CLOB API'den market token'larını çek
                                clob_r = req_clob.get(
                                    f"https://clob.polymarket.com/markets/{condition_id}",
                                    timeout=5
                                )
                                if clob_r.status_code == 200:
                                    clob_data = clob_r.json()
                                    tokens = clob_data.get("tokens", [])
                                    if len(tokens) > outcome_i:
                                        token_id = tokens[outcome_i].get("token_id", direct_asset)
                                        logging.info(f"CLOB token: outcome={outcome_i} ({outcome}) token={token_id[:20]}...")
                                    else:
                                        logging.warning(f"CLOB token bulunamadi, asset kullaniliyor")
                                else:
                                    # CLOB de başarısız - Gamma dene
                                    import json as json_mod
                                    g = req_clob.get(
                                        f"https://gamma-api.polymarket.com/markets?conditionId={condition_id}",
                                        timeout=5
                                    )
                                    if g.status_code == 200 and g.json():
                                        mkt = g.json()[0] if isinstance(g.json(), list) else g.json()
                                        clob_ids = mkt.get("clobTokenIds", "[]")
                                        if isinstance(clob_ids, str):
                                            clob_ids = json_mod.loads(clob_ids)
                                        if len(clob_ids) > outcome_i:
                                            token_id = clob_ids[outcome_i]
                                            logging.info(f"Gamma token: outcome={outcome_i} ({outcome}) token={token_id[:20]}...")
                            except Exception as token_err:
                                logging.warning(f"Token hatasi: {token_err}, asset kullaniliyor")
                        
                        logging.info(f"Final token: {token_id[:20] if token_id else 'YOK'}... outcome={outcome_i} ({outcome})")
                        # Sabit TRADE_SIZE kullan
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
                            )
                            portfolio.open_positions[pos_id] = pos
                            portfolio.total_trades += 1

                            # Gerçek bakiyeyi çek
                            if not Config.TEST_MODE:
                                portfolio.cash = poly.get_real_balance()
                            else:
                                # %2 komisyon dahil maliyet
                                commission = Config.TRADE_SIZE * Decimal("0.02")
                                portfolio.cash -= (Config.TRADE_SIZE + commission)
                                save_portfolio(portfolio)  # Test modunda kaydet

                            sign = "+" if portfolio.total_pnl >= 0 else ""
                            await active_notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON AÇILDI\n\n"
                                f"Trader: *{name}*\n"
                                f"Market: {title}\n"
                                f"Yön: *{outcome}*\n"
                                f"Fiyat: ${price:.3f}\n"
                                f"Boyut: ${Config.TRADE_SIZE}\n\n"
                                f"Gercek Nakit: ${portfolio.cash:.2f}\n"
                                f"PnL: {sign}${portfolio.total_pnl:.2f}"
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

                            # Gerçek bakiyeyi çek
                            if not Config.TEST_MODE:
                                portfolio.cash = poly.get_real_balance()
                            else:
                                portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
                                save_portfolio(portfolio)  # Test modunda kaydet

                            ts = "+" if pnl >= 0 else ""
                            wr = (portfolio.winning_trades / portfolio.total_trades * 100) if portfolio.total_trades > 0 else 0
                            await notifier.send(
                                f"{'[TEST] ' if Config.TEST_MODE else ''}POZİSYON KAPANDI\n\n"
                                f"Trader: *{pos.trader_name}*\n"
                                f"Market: {pos.market_title}\n"
                                f"PnL: {ts}${abs(float(pnl)):.2f}\n\n"
                                f"Gercek Nakit: ${portfolio.cash:.2f}\n"
                                f"Win Rate: {wr:.0f}% ({portfolio.winning_trades}W/{portfolio.losing_trades}L)"
                            )

            # STOP-LOSS devre disi
            if False:
             async with TelegramNotifier() as sl_notifier:
                sl_checked = {}
                for pos_id, pos in list(portfolio.open_positions.items()):
                    try:
                        import requests
                        if not pos.token_id:
                            continue
                        if pos.token_id in sl_checked:
                            resp_data = sl_checked[pos.token_id]
                            class FakeResp:
                                status_code = 200
                                def json(self): return resp_data
                            resp = FakeResp()
                        else:
                            url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
                            resp = requests.get(url, timeout=5)
                            if resp.status_code == 200:
                                sl_checked[pos.token_id] = resp.json()
                        if resp.status_code == 200:
                            current_price = float(resp.json().get("price", pos.entry_price))
                            loss_pct = (float(pos.entry_price) - current_price) / float(pos.entry_price) * 100
                            if loss_pct >= 40:
                                logging.info(f"STOP-LOSS: {pos.market_title} %{loss_pct:.0f} zarar")
                                pnl = Decimal(str(current_price)) * (pos.size_usd / pos.entry_price) - pos.size_usd
                                if Config.TEST_MODE:
                                    # Test modunda simüle et
                                    portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
                                    portfolio.realized_pnl += pnl
                                    portfolio.losing_trades += 1
                                    del portfolio.open_positions[pos_id]
                                    save_portfolio(portfolio)
                                else:
                                    # Gerçek modda sat
                                    sl_result = poly.sell(pos.token_id, 1, current_price, float(pos.size_usd))
                                    if sl_result:
                                        portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
                                        portfolio.realized_pnl += pnl
                                        portfolio.losing_trades += 1
                                        del portfolio.open_positions[pos_id]
                                        save_portfolio(portfolio)
                                await sl_notifier.send(
                                    f"🛑 STOP-LOSS TETIKLENDI\n"
                                    f"Market: {pos.market_title}\n"
                                    f"Zarar: %{loss_pct:.0f}\n"
                                    f"PnL: -${abs(float(pnl)):.2f}"
                                )
                    except Exception as e:
                        logging.error(f"Stop-loss kontrol hatasi: {e}")

            # 20 taramada bir rapor
            # seen_tx kaydet (her 5 taramada bir)
            if app_state["scan_count"] % 5 == 0:
                save_seen_tx(tracker.seen_tx)

            if app_state["scan_count"] % 20 == 0:
                async with TelegramNotifier() as notifier:
                    # Açık pozisyonların anlık değerini hesapla
                    import requests as req_report
                    live_value = Decimal("0")
                    checked = {}
                    for pos in portfolio.open_positions.values():
                        try:
                            if pos.token_id in checked:
                                cur = checked[pos.token_id]
                            else:
                                r = req_report.get(f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}", timeout=3)
                                cur = float(r.json().get("price", float(pos.entry_price))) if r.status_code == 200 else float(pos.entry_price)
                                checked[pos.token_id] = cur
                            live_value += pos.size_usd / pos.entry_price * Decimal(str(cur))
                        except:
                            live_value += pos.size_usd
                    live_total = portfolio.cash + live_value
                    live_pnl = live_total - portfolio.initial_capital
                    sign = "+" if live_pnl >= 0 else ""
                    # Trader bazında istatistik
                    trader_stats = {}
                    for pos in portfolio.open_positions.values():
                        t = pos.trader_name
                        if t not in trader_stats:
                            trader_stats[t] = {"count": 0, "value": Decimal("0"), "pnl": Decimal("0")}
                        trader_stats[t]["count"] += 1
                        # Anlık değer
                        try:
                            cur_price = checked.get(pos.token_id)
                            if cur_price is None:
                                r2 = req_report.get(f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}", timeout=3)
                                cur_price = float(r2.json().get("price", float(pos.entry_price))) if r2.status_code == 200 else float(pos.entry_price)
                            pos_value = pos.size_usd / pos.entry_price * Decimal(str(cur_price))
                            pos_pnl = pos_value - pos.size_usd
                            trader_stats[t]["value"] += pos_value
                            trader_stats[t]["pnl"] += pos_pnl
                        except:
                            trader_stats[t]["value"] += pos.size_usd

                    trader_lines = ""
                    for t, s in sorted(trader_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
                        sign = "+" if s["pnl"] >= 0 else ""
                        trader_lines += f"👤 {t}: {s['count']} işlem | ${float(s['value']):.0f} | {sign}${float(s['pnl']):.2f}\n"

                    await notifier.send(
                        f"📊 RAPOR Tarama #{app_state['scan_count']}\n"
                        f"💰 Nakit: ${portfolio.cash:.2f}\n"
                        f"📦 Pozisyon Değeri: ${live_value:.2f}\n"
                        f"📊 Toplam: ${live_total:.2f}\n"
                        f"📈 PnL: {sign}${live_pnl:.2f} ({sign}{float(live_pnl/portfolio.initial_capital*100):.1f}%)\n"
                        f"📌 Açık: {len(portfolio.open_positions)} | Trade: {portfolio.total_trades}\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"{trader_lines}"
                    )
                
                await notifier2.__aexit__(None, None, None)

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
    portfolio = app_state["portfolio"]
    poly = app_state.get("poly_client")
    
    # Gercek bakiyeyi cek
    real_cash = float(portfolio.cash)
    if poly and poly.client and not Config.TEST_MODE:
        try:
            real_cash = float(poly.get_real_balance())
            portfolio.cash = Decimal(str(real_cash))
        except:
            pass
    
    # Gercek pozisyonlari cek
    real_positions = []
    try:
        import requests
        url = f"https://data-api.polymarket.com/positions?user={Config.DEPOSIT_WALLET}&sizeThreshold=0"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            real_positions = data if isinstance(data, list) else []
    except:
        pass
    
    portfolio_dict = portfolio.to_dict()
    portfolio_dict["cash"] = real_cash
    portfolio_dict["real_positions_count"] = len(real_positions)
    portfolio_dict["real_positions_value"] = sum(float(p.get("value", 0) or 0) for p in real_positions)
    
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
    """Trader listesini dosyaya kaydet"""
    import json
    try:
        with open("traders.json", "w") as f:
            json.dump(app_state["tracked_users"], f, indent=2)
    except Exception as e:
        logging.error(f"Trader kayit hatasi: {e}")

def load_traders():
    """Trader listesini dosyadan yukle"""
    import json
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
    # Duplicate kontrolu
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
    # Her pozisyonu kapat - anlık fiyatla simüle et
    import requests as req
    for pos_id, pos in list(portfolio.open_positions.items()):
        try:
            url = f"https://clob.polymarket.com/last-trade-price?token_id={pos.token_id}"
            resp = req.get(url, timeout=5)
            if resp.status_code == 200:
                current_price = float(resp.json().get("price", float(pos.entry_price)))
            else:
                current_price = float(pos.entry_price)
        except:
            current_price = float(pos.entry_price)
        pnl = pos.size_usd / pos.entry_price * (Decimal(str(current_price)) - pos.entry_price)
        portfolio.cash += pos.size_usd + pnl - (pos.size_usd * Decimal("0.02"))  # %2 komisyon
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
        # Bot çalışmıyorsa geçici client oluştur
        poly = PolymarketClient()
    result = poly.cancel_all_orders()
    if "error" in result:
        return jsonify({"ok": False, "msg": result["error"]})
    cancelled = result.get("cancelled", 0)
    test_suffix = " (TEST)" if result.get("test") else ""
    msg = f"{cancelled} adet emir iptal edildi{test_suffix}"
    logging.info(msg)
    # Telegram bildirimi gönder
    async def _notify():
        async with TelegramNotifier() as n:
            await n.send(f"🚫 TÜM EMİRLER İPTAL EDİLDİ\n{cancelled} emir iptal edildi{test_suffix}")
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_notify())
        loop.close()
    except Exception as e:
        logging.warning(f"Telegram bildirim hatasi: {e}")
    return jsonify({"ok": True, "msg": msg, "cancelled": cancelled})

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    print("=" * 50)
    print("  POLYMARKET BOT v5.3")
    print(f"  EOA Address: {'OK' if Config.EOA_ADDRESS else 'EKSIK'}")
    print(f"  Deposit Wallet: {'OK' if Config.DEPOSIT_WALLET else 'AUTO/Otomatik'}")
    print(f"  Private Key: {'OK' if Config.PRIVATE_KEY else 'EKSIK'}")
    print(f"  CLOB API: {'OK' if Config.CLOB_API_KEY else 'EKSIK'}")
    print(f"  Builder API: {'OK' if Config.BUILDER_API_KEY else 'EKSIK (Opsiyonel)'}")
    print(f"  Telegram: {'OK' if Config.TELEGRAM_TOKEN else 'EKSIK'}")
    print(f"  Mod: {'TEST' if Config.TEST_MODE else 'GERCEK'}")
    print("=" * 50)
    # Bot thread her zaman başlasın
    t = threading.Thread(target=start_bot_thread, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)
