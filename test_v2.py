from py_clob_client_v2 import ClobClient, SignatureTypeV2
import os
from dotenv import load_dotenv

load_dotenv()

PK             = os.environ.get('PRIVATE_KEY')
DEPOSIT_WALLET = os.environ.get('DEPOSIT_WALLET', '')
HOST           = 'https://clob.polymarket.com'
CHAIN_ID       = 137

print(f"Private key: {PK[:6]}...")
print(f"Deposit wallet: {DEPOSIT_WALLET}")

# Signature type 2 = POLY_1271 (proxy/deposit wallet)
client = ClobClient(
    host=HOST,
    chain_id=CHAIN_ID,
    key=PK,
    signature_type=SignatureTypeV2.POLY_1271,
    funder=DEPOSIT_WALLET,
)

try:
    creds = client.create_or_derive_api_key()
    print(f"\nAPI Key: {creds.api_key}")
    print(f"API Secret: {creds.api_secret[:10]}...")
    print(f"Passphrase: {creds.api_passphrase[:10]}...")

    env_path = '.env'
    with open(env_path, 'r') as f:
        content = f.read()

    lines = [l for l in content.splitlines() if not l.startswith('CLOB_')]
    lines.append(f'CLOB_API_KEY={creds.api_key}')
    lines.append(f'CLOB_SECRET={creds.api_secret}')
    lines.append(f'CLOB_PASS_PHRASE={creds.api_passphrase}')

    with open(env_path, 'w') as f:
        f.write('\n'.join(lines))

    print("\n.env guncellendi!")
except Exception as e:
    print(f"Hata: {e}")
