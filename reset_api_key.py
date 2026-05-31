from py_clob_client_v2 import ClobClient, ApiCreds, SignatureTypeV2
import os
from dotenv import load_dotenv

load_dotenv()

PK = os.environ.get('PRIVATE_KEY')
DEPOSIT = os.environ.get('DEPOSIT_WALLET', '')
CLOB_API_KEY = os.environ.get('CLOB_API_KEY', '')
CLOB_SECRET = os.environ.get('CLOB_SECRET', '')
CLOB_PASS = os.environ.get('CLOB_PASS_PHRASE', '')

print(f"Mevcut key: {CLOB_API_KEY[:10]}...")

creds = ApiCreds(api_key=CLOB_API_KEY, api_secret=CLOB_SECRET, api_passphrase=CLOB_PASS)
client = ClobClient(
    host='https://clob.polymarket.com',
    chain_id=137,
    key=PK,
    creds=creds,
    signature_type=SignatureTypeV2.POLY_1271,
    funder=DEPOSIT,
)

# Mevcut key ile sil
try:
    client.delete_api_key()
    print("Eski key silindi!")
except Exception as e:
    print(f"Silme: {e}")

# Credentials olmadan yeni key oluştur
client2 = ClobClient(
    host='https://clob.polymarket.com',
    chain_id=137,
    key=PK,
    signature_type=SignatureTypeV2.POLY_1271,
    funder=DEPOSIT,
)

try:
    new_creds = client2.create_api_key()
    print(f"\nYeni API Key: {new_creds.api_key}")
    print(f"Secret: {new_creds.api_secret[:10]}...")
    print(f"Passphrase: {new_creds.api_passphrase[:10]}...")

    env_path = '.env'
    with open(env_path, 'r') as f:
        content = f.read()
    lines = [l for l in content.splitlines() if not l.startswith('CLOB_')]
    lines.append(f'CLOB_API_KEY={new_creds.api_key}')
    lines.append(f'CLOB_SECRET={new_creds.api_secret}')
    lines.append(f'CLOB_PASS_PHRASE={new_creds.api_passphrase}')
    with open(env_path, 'w') as f:
        f.write('\n'.join(lines))
    print("\n.env guncellendi!")
except Exception as e:
    print(f"Yeni key hatasi: {e}")
