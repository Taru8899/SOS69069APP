"""
Minimal JSON-RPC helper for Ethereum view calls.
Uses requests + our pure_crypto keccak. No web3.py.
"""
import requests
from pure_crypto import keccak256

RPC_LIST = [
    "https://eth.drpc.org",
    "https://rpc.mevblocker.io",
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.flashbots.net",
    "https://cloudflare-eth.com",
]

CONTRACT = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"


def _pad32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00")


def _encode_address(addr: str) -> bytes:
    addr = addr.lower().replace("0x", "")
    return _pad32(bytes.fromhex(addr))


def _selector(sig: str) -> bytes:
    return keccak256(sig.encode())[:4]


def _eth_call(to: str, data: bytes, rpc_url: str, timeout: float = 10.0) -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": to, "data": "0x" + data.hex()},
            "latest",
        ],
    }
    r = requests.post(rpc_url, json=payload, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))
    result = body.get("result", "0x")
    h = result[2:] if result.startswith("0x") else result
    return bytes.fromhex(h)


def _decode_uint256(data: bytes, offset: int = 0) -> int:
    return int.from_bytes(data[offset:offset + 32], "big")


def _decode_int256(data: bytes, offset: int = 0) -> int:
    raw = int.from_bytes(data[offset:offset + 32], "big")
    if raw >= 2**255:
        raw -= 2**256
    return raw


def call_with_fallback(fn):
    last_err = None
    for url in RPC_LIST:
        try:
            return fn(url)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All RPCs failed. Last: {last_err}")


def stats_of(address: str) -> dict:
    """Return {"push": int, "trust": int, "effective": int}"""
    address = address.strip()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("Invalid address (need 0x + 40 hex chars)")

    data = _selector("statsOf(address)") + _encode_address(address)

    def _do(rpc_url):
        raw = _eth_call(CONTRACT, data, rpc_url)
        if len(raw) < 96:
            raise RuntimeError("Unexpected return data")
        return {
            "push": _decode_uint256(raw, 0),
            "trust": _decode_uint256(raw, 32),
            "effective": _decode_int256(raw, 64),
        }

    return call_with_fallback(_do)
