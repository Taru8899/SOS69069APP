from __future__ import annotations
import json, secrets, time
from pure_crypto import keccak256

def new_serial() -> str:
    return secrets.token_hex(16)

def build_record(issuer_pk: str, activity_type: str = "presence", value: int = 1, previous=None) -> dict:
    return {
        "protocol": "SOS69069",
        "version": 1,
        "type": "record",
        "serial": new_serial(),
        "issuer": {"algorithm": "secp256k1-interim", "public_key": issuer_pk},
        "activity": {"type": activity_type, "value": value, "timestamp": int(time.time())},
        "previous": previous,
    }

def record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "signature"}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return "0x" + keccak256(raw).hex()
