"""
Minimal JSON-RPC helper for Ethereum view calls + event logs.
Pure requests + pure_crypto. No web3.py.
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

# SignatureRecorded(address,address,bytes32,bytes,address,uint256,string)
EVENT_TOPIC0 = "0x" + keccak256(
    b"SignatureRecorded(address,address,bytes32,bytes,address,uint256,string)"
).hex()


def _pad32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00")


def _encode_address(addr: str) -> bytes:
    addr = addr.lower().replace("0x", "")
    return _pad32(bytes.fromhex(addr))


def _selector(sig: str) -> bytes:
    return keccak256(sig.encode())[:4]


def _topic_address(addr: str) -> str:
    """Indexed address topic (32-byte left-padded)."""
    return "0x" + _encode_address(addr).hex()


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


def _eth_get_logs(filter_params: dict, rpc_url: str, timeout: float = 15.0) -> list:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getLogs",
        "params": [filter_params],
    }
    r = requests.post(rpc_url, json=payload, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))
    return body.get("result", [])


def _eth_block_number(rpc_url: str, timeout: float = 8.0) -> int:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
    r = requests.post(rpc_url, json=payload, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"].get("message", str(body["error"])))
    return int(body["result"], 16)


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


def _decode_abi_string(data: bytes, offset: int) -> str:
    """Decode a dynamic string from ABI-encoded data at the given offset."""
    str_offset = _decode_uint256(data, offset)
    length = _decode_uint256(data, str_offset)
    start = str_offset + 32
    return data[start:start + length].decode("utf-8", errors="replace")


def _parse_signature_recorded(log: dict) -> dict | None:
    """
    Parse a SignatureRecorded log into a friendly dict.
    topics: [topic0, signer, intendedTo, submitter]
    data: payloadHash (32) + signature offset + timestamp (32) + metadata offset...
    """
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        signer = "0x" + topics[1][-40:]
        intended_to = "0x" + topics[2][-40:]
        submitter = "0x" + topics[3][-40:]

        data_hex = log.get("data", "0x")[2:]
        data = bytes.fromhex(data_hex)

        # static: payloadHash (0), offset_sig (32), timestamp (64), offset_meta (96)
        payload_hash = "0x" + data[0:32].hex()
        timestamp = _decode_uint256(data, 64)

        # signature is dynamic bytes
        sig_offset = _decode_uint256(data, 32)
        sig_len = _decode_uint256(data, sig_offset)
        signature = "0x" + data[sig_offset + 32:sig_offset + 32 + sig_len].hex()

        # metadata is dynamic string
        meta_offset = _decode_uint256(data, 96)
        meta_len = _decode_uint256(data, meta_offset)
        metadata = data[meta_offset + 32:meta_offset + 32 + meta_len].decode("utf-8", errors="replace")

        return {
            "signer": signer,
            "intendedTo": intended_to,
            "submitter": submitter,
            "payloadHash": payload_hash,
            "signature": signature,
            "timestamp": timestamp,
            "metadata": metadata,
            "txHash": log.get("transactionHash", ""),
            "blockNumber": int(log.get("blockNumber", "0x0"), 16),
            "logIndex": int(log.get("logIndex", "0x0"), 16),
        }
    except Exception:
        return None


def fetch_messages(address: str, direction: str = "trust", lookback_blocks: int = 8000, max_results: int = 15) -> list:
    """
    direction: "trust" = intendedTo == address (received)
               "push"  = signer == address (sent)
    Returns list of parsed events, newest first, metadata non-empty only.
    """
    address = address.strip().lower()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("Invalid address")

    def _do(rpc_url):
        latest = _eth_block_number(rpc_url)
        from_block = max(0, latest - lookback_blocks)

        # Build filter
        topics = [EVENT_TOPIC0]
        if direction == "trust":
            # signer = any, intendedTo = address
            topics.append(None)
            topics.append(_topic_address(address))
        else:
            # signer = address
            topics.append(_topic_address(address))

        # Query in chunks to avoid RPC limits
        chunk = 2500
        all_logs = []
        start = from_block
        while start <= latest:
            end = min(start + chunk - 1, latest)
            params = {
                "address": CONTRACT,
                "fromBlock": hex(start),
                "toBlock": hex(end),
                "topics": topics,
            }
            try:
                logs = _eth_get_logs(params, rpc_url)
                all_logs.extend(logs)
            except Exception:
                # try smaller chunk
                mid = (start + end) // 2
                if mid > start:
                    for a, b in [(start, mid), (mid + 1, end)]:
                        try:
                            params["fromBlock"] = hex(a)
                            params["toBlock"] = hex(b)
                            all_logs.extend(_eth_get_logs(params, rpc_url))
                        except Exception:
                            pass
            start = end + 1

        parsed = []
        seen = set()
        for log in all_logs:
            ev = _parse_signature_recorded(log)
            if not ev:
                continue
            meta = (ev.get("metadata") or "").strip()
            if not meta:
                continue
            key = (ev["txHash"], ev["logIndex"])
            if key in seen:
                continue
            seen.add(key)
            parsed.append(ev)

        parsed.sort(key=lambda e: (e["timestamp"], e["blockNumber"]), reverse=True)
        return parsed[:max_results]

    return call_with_fallback(_do)
