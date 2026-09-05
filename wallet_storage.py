"""
Password-encrypted private key storage. Pure stdlib only (hashlib, hmac,
os, json) — no C-extension dependencies, so this stays safe for
python-for-android cross-compilation.

Design: PBKDF2-HMAC-SHA256 derives two separate keys from the user's
password (one for encryption, one for authentication — never reuse a
single key for both). Encryption is HMAC-SHA256 used as a counter-mode
keystream generator (a standard, sound construction — this is exactly
how many stream ciphers built from a PRF work). Encrypt-then-MAC:
the authentication tag is computed over the ciphertext, so a wrong
password or tampered file is detected before any decrypted bytes
are trusted.
"""

import os
import json
import hmac
import hashlib
import base64

PBKDF2_ITERATIONS = 200_000
SALT_LEN = 16
NONCE_LEN = 16


def _pbkdf2(password: str, salt: bytes, length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS, dklen=length)


def _derive_keys(password: str, salt: bytes):
    # 64 bytes total -> 32 for encryption key, 32 for MAC key
    material = _pbkdf2(password, salt, 64)
    enc_key = material[:32]
    mac_key = material[32:]
    return enc_key, mac_key


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

    keystream = _keystream(enc_key, nonce, len(plaintext))
    ciphertext = _xor(plaintext, keystream)

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

    keystream = _keystream(enc_key, nonce, len(ciphertext))
    return _xor(ciphertext, keystream)


# ---------------- wallet file management ----------------

def wallet_file_path(app_data_dir: str) -> str:
    return os.path.join(app_data_dir, "wallet.json")


def wallet_exists(app_data_dir: str) -> bool:
    return os.path.isfile(wallet_file_path(app_data_dir))


def save_wallet(app_data_dir: str, privkey_hex: str, address: str, password: str):
    plaintext = privkey_hex.encode()
    blob = encrypt(plaintext, password)
    blob["address"] = address  # address itself isn't secret, stored openly for display

    path = wallet_file_path(app_data_dir)
    with open(path, "w") as f:
        json.dump(blob, f)


def load_wallet(app_data_dir: str, password: str) -> str:
    """Returns the decrypted private key hex string, or raises
    WrongPasswordOrTampered."""
    path = wallet_file_path(app_data_dir)
    with open(path, "r") as f:
        blob = json.load(f)
    plaintext = decrypt(blob, password)
    return plaintext.decode()


def peek_address(app_data_dir: str) -> str:
    """Read the (non-secret) address without needing the password."""
    path = wallet_file_path(app_data_dir)
    with open(path, "r") as f:
        blob = json.load(f)
    return blob.get("address", "")
