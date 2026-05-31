import os
from dotenv import load_dotenv
load_dotenv()

PK = os.environ.get("PRIVATE_KEY")
DEPOSIT = os.environ.get("DEPOSIT_WALLET", "")
CLOB_API_KEY = os.environ.get("CLOB_API_KEY", "")
CLOB_SECRET = os.environ.get("CLOB_SECRET", "")
CLOB_PASS = os.environ.get("CLOB_PASS_PHRASE", "")

from py_clob_client_v2 import ClobClient, ApiCreds, SignatureTypeV2

creds = ApiCreds(api_key=CLOB_API_KEY, api_secret=CLOB_SECRET, api_passphrase=CLOB_PASS)
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    key=PK,
    creds=creds,
    signature_type=SignatureTypeV2.POLY_1271,
    funder=DEPOSIT,
)

try:
    result = client.cancel_all()
    print(f"Tüm emirler iptal edildi: {result}")
except Exception as e:
    print(f"Hata: {e}")
