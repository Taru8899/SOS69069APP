"""Human identity (PQ-ready API; interim secp256k1 via pure_crypto)."""
from __future__ import annotations
import json, os, time, secrets
from typing import Optional
from pure_crypto import privkey_to_pubkey, keccak256

IDENTITY_FILE = "human_identity.json"
ALG = "secp256k1-interim"
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

def _path(user_data_dir: str) -> str:
    return os.path.join(user_data_dir, IDENTITY_FILE)

def fingerprint_from_pubkey_bytes(pub_bytes: bytes) -> str:
    h = keccak256(pub_bytes)
    hx = h.hex().upper()
    return "-".join(hx[i:i+4] for i in range(0, 16, 4))

def generate_identity() -> dict:
    sk_int = secrets.randbits(256) % N or 1
    x, y = privkey_to_pubkey(sk_int)
    pub_bytes = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return {
        "protocol": "SOS69069",
        "type": "identity",
        "version": 1,
        "algorithm": ALG,
        "private_key": hex(sk_int),
        "public_key": pub_bytes.hex(),
        "fingerprint": fingerprint_from_pubkey_bytes(pub_bytes),
        "created": int(time.time()),
    }

def save_identity(user_data_dir: str, identity: dict) -> None:
    os.makedirs(user_data_dir, exist_ok=True)
    path = _path(user_data_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(identity, f, indent=2)
    os.replace(tmp, path)

def load_identity(user_data_dir: str) -> Optional[dict]:
    path = _path(user_data_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def public_card(identity: dict) -> dict:
    return {
        "type": "identity",
        "version": identity.get("version", 1),
        "protocol": "SOS69069",
        "algorithm": identity.get("algorithm", ALG),
        "pk": identity.get("public_key", ""),
        "fingerprint": identity.get("fingerprint", ""),
        "created": identity.get("created", 0),
    }

def has_identity(user_data_dir: str) -> bool:
    return load_identity(user_data_dir) is not None
