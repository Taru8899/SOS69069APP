"""
Password-encrypted private key storage. Supports up to 2 wallet slots.
Pure stdlib only — safe for python-for-android.
"""

import os
import json
import hmac
import hashlib
import base64

PBKDF2_ITERATIONS = 200_000
SALT_LEN = 16
NONCE_LEN = 16
MAX_SLOTS = 2


def _pbkdf2(password: str, salt: bytes, length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=length)


def _derive_keys(password: str, salt: bytes):
    material = _pbkdf2(password, salt, 64)
    return material[:32], material[32:]


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def encrypt(plaintext: bytes, password: str) -> dict:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    enc_key, mac_key = _derive_keys(password, salt)
    ciphertext = _xor(plaintext, _keystream(enc_key, nonce, len(plaintext)))
    tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "tag": base64.b64encode(tag).decode(),
    }


class WrongPasswordOrTampered(Exception):
    pass


def decrypt(blob: dict, password: str) -> bytes:
    salt = base64.b64decode(blob["salt"])
    nonce = base64.b64decode(blob["nonce"])
    ciphertext = base64.b64decode(blob["ciphertext"])
    tag = base64.b64decode(blob["tag"])
    enc_key, mac_key = _derive_keys(password, salt)
    expected_tag = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise WrongPasswordOrTampered("Wrong password or corrupted wallet file.")
    return _xor(ciphertext, _keystream(enc_key, nonce, len(ciphertext)))


def _slot_path(app_data_dir: str, slot: int) -> str:
    if slot == 1:
        # legacy single-wallet file stays slot 1
        legacy = os.path.join(app_data_dir, "wallet.json")
        if os.path.isfile(legacy):
            return legacy
    return os.path.join(app_data_dir, f"wallet_{slot}.json")


def wallet_file_path(app_data_dir: str) -> str:
    return _slot_path(app_data_dir, 1)


def wallet_exists(app_data_dir: str, slot: int = None) -> bool:
    if slot is not None:
        return os.path.isfile(_slot_path(app_data_dir, slot))
    return any(os.path.isfile(_slot_path(app_data_dir, s)) for s in (1, 2))


def list_slots(app_data_dir: str) -> list:
    """Return list of {slot, address} for existing wallets."""
    out = []
    for s in (1, 2):
        path = _slot_path(app_data_dir, s)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r") as f:
                blob = json.load(f)
            out.append({"slot": s, "address": blob.get("address", "")})
        except Exception:
            out.append({"slot": s, "address": ""})
    return out


def save_wallet(app_data_dir: str, privkey_hex: str, address: str, password: str, slot: int = 1):
    if slot not in (1, 2):
        raise ValueError("slot must be 1 or 2")
    plaintext = privkey_hex.encode()
    blob = encrypt(plaintext, password)
    blob["address"] = address
    blob["slot"] = slot
    path = _slot_path(app_data_dir, slot)
    # prefer wallet_N.json naming for new saves
    if slot == 1 and path.endswith("wallet.json"):
        path = os.path.join(app_data_dir, "wallet_1.json")
    with open(path, "w") as f:
        json.dump(blob, f)
    # migrate away from legacy name if both would exist
    legacy = os.path.join(app_data_dir, "wallet.json")
    if slot == 1 and os.path.isfile(legacy) and path != legacy:
        try:
            os.remove(legacy)
        except Exception:
            pass


def load_wallet(app_data_dir: str, password: str, slot: int = 1) -> str:
    path = _slot_path(app_data_dir, slot)
    with open(path, "r") as f:
        blob = json.load(f)
    return decrypt(blob, password).decode()


def peek_address(app_data_dir: str, slot: int = 1) -> str:
    path = _slot_path(app_data_dir, slot)
    with open(path, "r") as f:
        blob = json.load(f)
    return blob.get("address", "")


def delete_wallet(app_data_dir: str, slot: int):
    for path in (
        os.path.join(app_data_dir, f"wallet_{slot}.json"),
        os.path.join(app_data_dir, "wallet.json") if slot == 1 else None,
    ):
        if path and os.path.isfile(path):
            os.remove(path)
