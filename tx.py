"""
Minimal pure-Python Ethereum transaction builder + sender.
Supports legacy (type-0) transactions for maximum RPC compatibility.
Uses existing pure_crypto for keccak + secp256k1 signing.
"""
import requests
from pure_crypto import keccak256, sign as ecdsa_sign, privkey_to_pubkey, N

RPC_LIST = [
    "https://eth.drpc.org",
    "https://rpc.mevblocker.io",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.flashbots.net",
    "https://cloudflare-eth.com",
]

CONTRACT = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"
CHAIN_ID = 1

# recordSignature(address,address,bytes32,bytes,string)
RECORD_SELECTOR = bytes.fromhex("1c7c27c8")


# ── minimal RLP ──────────────────────────────────────────────

def _rlp_encode_length(length: int, offset: int) -> bytes:
    if length < 56:
        return bytes([offset + length])
    bl = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([offset + 55 + len(bl)]) + bl


def rlp_encode(item) -> bytes:
    if item is None:
        return b"\x80"
    if isinstance(item, int):
        if item == 0:
            return b"\x80"
        b = item.to_bytes((item.bit_length() + 7) // 8, "big")
        return rlp_encode(b)
    if isinstance(item, bytes):
        if len(item) == 1 and item[0] < 0x80:
            return item
        return _rlp_encode_length(len(item), 0x80) + item
    if isinstance(item, str):
        if item.startswith("0x"):
            h = item[2:]
            if len(h) % 2:
                h = "0" + h
            return rlp_encode(bytes.fromhex(h) if h else b"")
        return rlp_encode(item.encode())
    if isinstance(item, (list, tuple)):
        payload = b"".join(rlp_encode(x) for x in item)
        return _rlp_encode_length(len(payload), 0xc0) + payload
    raise TypeError(f"Cannot RLP-encode {type(item)}")


# ── ABI helpers ──────────────────────────────────────────────

def _pad32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00")


def _encode_address(addr: str) -> bytes:
    return _pad32(bytes.fromhex(addr.lower().replace("0x", "")))


def _encode_bytes32(h: str) -> bytes:
    h = h.lower().replace("0x", "").zfill(64)
    return bytes.fromhex(h)


def _encode_bytes(b: bytes) -> bytes:
    return _pad32(len(b).to_bytes(32, "big")) + b + (b"\x00" * ((32 - len(b) % 32) % 32))


def _encode_string(s: str) -> bytes:
    return _encode_bytes(s.encode("utf-8"))


def encode_record_signature(signer: str, intended_to: str,
                            payload_hash: str, signature: bytes,
                            metadata: str) -> bytes:
    """ABI-encode recordSignature(...) calldata."""
    # head: 4 static/dynamic slots after selector
    # address, address, bytes32, offset_sig, offset_meta
    head = (
        _encode_address(signer)
        + _encode_address(intended_to)
        + _encode_bytes32(payload_hash)
        + _pad32((5 * 32).to_bytes(32, "big"))          # offset of signature
        + _pad32((5 * 32 + 32 + ((len(signature) + 31) // 32) * 32).to_bytes(32, "big"))
    )
    # Actually compute offsets properly
    # static part = 5 * 32 bytes
    static_len = 5 * 32
    sig_part = _encode_bytes(signature)
    meta_part = _encode_string(metadata)
    head = (
        _encode_address(signer)
        + _encode_address(intended_to)
        + _encode_bytes32(payload_hash)
        + _pad32((static_len).to_bytes(32, "big"))
        + _pad32((static_len + len(sig_part)).to_bytes(32, "big"))
    )
    return RECORD_SELECTOR + head + sig_part + meta_part


# ── RPC helpers ──────────────────────────────────────────────

def _rpc(method: str, params: list, timeout: float = 12.0):
    last = None
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    for url in RPC_LIST:
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise RuntimeError(body["error"].get("message", str(body["error"])))
            return body["result"]
        except Exception as e:
            last = e
            continue
    raise RuntimeError(f"RPC {method} failed: {last}")


def get_nonce(address: str) -> int:
    result = _rpc("eth_getTransactionCount", [address, "pending"])
    return int(result, 16)


def get_gas_price() -> int:
    result = _rpc("eth_gasPrice", [])
    # bump 10% for faster inclusion
    return int(int(result, 16) * 1.1)


def get_gas_price_info() -> dict:
    """Return current gas price in wei and gwei (with 10% bump)."""
    result = _rpc("eth_gasPrice", [])
    base = int(result, 16)
    bumped = int(base * 1.1)
    return {
        "wei": bumped,
        "baseWei": base,
        "gwei": bumped / 1e9,
        "baseGwei": base / 1e9,
    }


def estimate_gas(from_addr: str, to: str, data: bytes) -> int:
    try:
        result = _rpc("eth_estimateGas", [{
            "from": from_addr,
            "to": to,
            "data": "0x" + data.hex(),
        }])
        # add 20% buffer
        return int(int(result, 16) * 1.2)
    except Exception:
        return 250000  # safe fallback for recordSignature


def send_raw_tx(raw_hex: str) -> str:
    result = _rpc("eth_sendRawTransaction", [raw_hex], timeout=20.0)
    return result


# ── Transaction signing ──────────────────────────────────────

def _sign_legacy_tx(privkey_int: int, nonce: int, gas_price: int,
                    gas_limit: int, to: str, value: int, data: bytes) -> str:
    """
    EIP-155 legacy transaction.
    Returns 0x-prefixed raw tx hex.
    """
    to_bytes = bytes.fromhex(to.lower().replace("0x", ""))

    # unsigned fields for signing
    fields = [
        nonce,
        gas_price,
        gas_limit,
        to_bytes,
        value,
        data,
        CHAIN_ID,
        0,
        0,
    ]
    rlp_unsigned = rlp_encode(fields)
    msg_hash = keccak256(rlp_unsigned)

    r, s, v_raw = ecdsa_sign(privkey_int, msg_hash)
    # EIP-155 v
    v = v_raw + CHAIN_ID * 2 + 8  # v_raw is 27/28 → 37/38 for mainnet

    signed_fields = [
        nonce,
        gas_price,
        gas_limit,
        to_bytes,
        value,
        data,
        v,
        r,
        s,
    ]
    raw = rlp_encode(signed_fields)
    return "0x" + raw.hex()


def send_record_signature(privkey_hex: str, intended_to: str,
                          payload_hash: str, signature_hex: str,
                          metadata: str, signer: str = None,
                          nonce: int = None, gas_price: int = None) -> dict:
    """
    Build, sign and broadcast recordSignature tx.
    privkey_hex = wallet that pays gas (tx sender).
    signer = address that produced the EIP-712 signature (defaults to sender).
    nonce / gas_price: optional overrides (for safe batching).
    Returns {"txHash": "...", "from": "...", "gasLimit": int, "gasPrice": int, "nonce": int}
    """
    privkey_int = int(privkey_hex.replace("0x", ""), 16)
    pub = privkey_to_pubkey(privkey_int)
    from pure_crypto import pubkey_to_address
    from_addr = pubkey_to_address(pub)
    signer_addr = signer if signer else from_addr

    sig_bytes = bytes.fromhex(signature_hex.replace("0x", ""))
    if len(sig_bytes) != 65:
        raise ValueError("Signature must be 65 bytes")

    data = encode_record_signature(
        signer_addr, intended_to, payload_hash, sig_bytes, metadata
    )

    if nonce is None:
        nonce = get_nonce(from_addr)
    if gas_price is None:
        gas_price = get_gas_price()
    gas_limit = estimate_gas(from_addr, CONTRACT, data)

    raw = _sign_legacy_tx(
        privkey_int, nonce, gas_price, gas_limit,
        CONTRACT, 0, data
    )
    tx_hash = send_raw_tx(raw)
    return {
        "txHash": tx_hash,
        "from": from_addr,
        "gasLimit": gas_limit,
        "gasPrice": gas_price,
        "nonce": nonce,
    }
