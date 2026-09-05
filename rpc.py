"""
JSON-RPC + Etherscan helper for Ethereum view calls and event logs.
Pure requests + pure_crypto. No web3.py.
"""
import requests
from pure_crypto import keccak256

# ── Config ───────────────────────────────────────────────────
ETHERSCAN_API_KEY = "RU99NEJZV9F2EWS7A97RWVHDJN1ZQ29Q99"
ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1

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
    return "0x" + _encode_address(addr).hex()


def _decode_uint256(data: bytes, offset: int = 0) -> int:
    return int.from_bytes(data[offset:offset + 32], "big")


def _decode_int256(data: bytes, offset: int = 0) -> int:
    raw = int.from_bytes(data[offset:offset + 32], "big")
    if raw >= 2**255:
        raw -= 2**256
    return raw


# ── Low-level RPC ────────────────────────────────────────────

def _eth_call(to: str, data: bytes, rpc_url: str, timeout: float = 10.0) -> bytes:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [{"to": to, "data": "0x" + data.hex()}, "latest"],
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


def call_with_fallback(fn):
    last_err = None
    for url in RPC_LIST:
        try:
            return fn(url)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All RPCs failed. Last: {last_err}")


# ── Etherscan helpers ────────────────────────────────────────

def _etherscan_get(params: dict, timeout: float = 15.0) -> dict:
    params = dict(params)
    params["chainid"] = CHAIN_ID
    params["apikey"] = ETHERSCAN_API_KEY
    r = requests.get(ETHERSCAN_BASE, params=params, timeout=timeout)
    r.raise_for_status()
    body = r.json()
    # status "1" = ok, "0" can still contain useful data (e.g. no results)
    return body


def etherscan_get_logs(address: str, topic0: str, topic1=None, topic2=None,
                       from_block: int = 0, to_block: str | int = "latest",
                       page: int = 1, offset: int = 100) -> list:
    """
    Fetch event logs via Etherscan V2 API.
    topic1/topic2 can be full 32-byte topics or None.
    """
    params = {
        "module": "logs",
        "action": "getLogs",
        "address": address,
        "fromBlock": from_block if isinstance(from_block, int) else from_block,
        "toBlock": to_block,
        "topic0": topic0,
        "page": page,
        "offset": offset,
    }
    if topic1 is not None:
        params["topic1"] = topic1
        params["topic0_1_opr"] = "and"
    if topic2 is not None:
        params["topic2"] = topic2
        params["topic0_2_opr"] = "and"
        if topic1 is not None:
            params["topic1_2_opr"] = "and"

    body = _etherscan_get(params)
    if body.get("status") == "1" and isinstance(body.get("result"), list):
        return body["result"]
    # No results or soft error
    if isinstance(body.get("result"), list):
        return body["result"]
    msg = body.get("message") or body.get("result") or "Etherscan error"
    if "no records" in str(msg).lower() or "no logs" in str(msg).lower():
        return []
    raise RuntimeError(str(msg))


# ── High-level API ───────────────────────────────────────────

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


def _parse_signature_recorded(log: dict) -> dict | None:
    """
    Parse a SignatureRecorded log (RPC or Etherscan format).
    topics: [topic0, signer, intendedTo, submitter]
    """
    try:
        topics = log.get("topics", [])
        if len(topics) < 4:
            return None
        signer = "0x" + topics[1][-40:]
        intended_to = "0x" + topics[2][-40:]
        submitter = "0x" + topics[3][-40:]

        data_hex = log.get("data", "0x")
        if data_hex.startswith("0x"):
            data_hex = data_hex[2:]
        data = bytes.fromhex(data_hex)

        payload_hash = "0x" + data[0:32].hex()
        timestamp = _decode_uint256(data, 64)

        sig_offset = _decode_uint256(data, 32)
        sig_len = _decode_uint256(data, sig_offset)
        signature = "0x" + data[sig_offset + 32:sig_offset + 32 + sig_len].hex()

        meta_offset = _decode_uint256(data, 96)
        meta_len = _decode_uint256(data, meta_offset)
        metadata = data[meta_offset + 32:meta_offset + 32 + meta_len].decode("utf-8", errors="replace")

        tx_hash = log.get("transactionHash") or log.get("hash") or ""
        block_num = log.get("blockNumber", "0x0")
        if isinstance(block_num, str):
            block_num = int(block_num, 16) if block_num.startswith("0x") else int(block_num)
        log_index = log.get("logIndex", "0x0")
        if isinstance(log_index, str):
            log_index = int(log_index, 16) if str(log_index).startswith("0x") else int(log_index)

        # Etherscan sometimes returns timeStamp in the log
        if not timestamp and log.get("timeStamp"):
            ts = log["timeStamp"]
            timestamp = int(ts, 16) if isinstance(ts, str) and ts.startswith("0x") else int(ts)

        return {
            "signer": signer,
            "intendedTo": intended_to,
            "submitter": submitter,
            "payloadHash": payload_hash,
            "signature": signature,
            "timestamp": timestamp,
            "metadata": metadata,
            "txHash": tx_hash,
            "blockNumber": block_num,
            "logIndex": log_index,
        }
    except Exception:
        return None


def _fetch_via_etherscan(address: str, direction: str, max_results: int) -> list:
    """Prefer Etherscan for reliability and deeper history."""
    address = address.lower()
    topic_addr = _topic_address(address)

    if direction == "trust":
        # intendedTo = topic2
        logs = etherscan_get_logs(
            CONTRACT, EVENT_TOPIC0,
            topic1=None, topic2=topic_addr,
            from_block=0, to_block="latest",
            page=1, offset=min(max_results * 3, 200),
        )
    else:
        # signer = topic1
        logs = etherscan_get_logs(
            CONTRACT, EVENT_TOPIC0,
            topic1=topic_addr, topic2=None,
            from_block=0, to_block="latest",
            page=1, offset=min(max_results * 3, 200),
        )

    parsed = []
    seen = set()
    for log in logs:
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


def _fetch_via_rpc(address: str, direction: str, lookback_blocks: int, max_results: int) -> list:
    address = address.lower()

    def _do(rpc_url):
        latest = _eth_block_number(rpc_url)
        from_block = max(0, latest - lookback_blocks)

        topics = [EVENT_TOPIC0]
        if direction == "trust":
            topics.append(None)
            topics.append(_topic_address(address))
        else:
            topics.append(_topic_address(address))

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


def fetch_messages(address: str, direction: str = "trust",
                   lookback_blocks: int = 12000, max_results: int = 15) -> list:
    """
    direction: "trust" = intendedTo == address (received)
               "push"  = signer == address (sent)
    Tries Etherscan first (deeper history), falls back to public RPCs.
    """
    address = address.strip()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("Invalid address")

    # 1) Prefer Etherscan
    try:
        results = _fetch_via_etherscan(address, direction, max_results)
        if results:
            return results
    except Exception:
        pass

    # 2) Fallback to public RPCs
    return _fetch_via_rpc(address, direction, lookback_blocks, max_results)


# ── Presence offer loading ───────────────────────────────────

def fetch_presence_events(lookback_blocks: int = 30000, max_logs: int = 300) -> list:
    """
    Fetch recent SignatureRecorded logs (any address) and return parsed events
    that look like presence protocol messages (O/A/D/X).
    Uses Etherscan first for depth.
    """
    try:
        logs = etherscan_get_logs(
            CONTRACT, EVENT_TOPIC0,
            from_block=0, to_block="latest",
            page=1, offset=max_logs,
        )
    except Exception:
        # RPC fallback – narrower window
        def _do(rpc_url):
            latest = _eth_block_number(rpc_url)
            from_block = max(0, latest - lookback_blocks)
            params = {
                "address": CONTRACT,
                "fromBlock": hex(from_block),
                "toBlock": hex(latest),
                "topics": [EVENT_TOPIC0],
            }
            return _eth_get_logs(params, rpc_url)
        try:
            logs = call_with_fallback(_do)
        except Exception:
            logs = []

    events = []
    for log in logs:
        ev = _parse_signature_recorded(log)
        if not ev:
            continue
        meta = (ev.get("metadata") or "").strip()
        if not meta:
            continue
        if meta[0] in ("O", "A", "D", "X") and "|" in meta:
            events.append(ev)
    return events


def build_presence_offers(events: list) -> list:
    """
    Turn raw presence events into offer objects with status.
    Mirrors presence.js logic.
    """
    from presence import parse_offer_metadata, parse_action_metadata

    offers = []
    actions_by_id = {}

    for ev in events:
        meta = ev.get("metadata") or ""
        action = parse_action_metadata(meta)
        if action and action.get("id"):
            oid = action["id"]
            if oid not in actions_by_id:
                actions_by_id[oid] = {"accepts": [], "dones": [], "cancels": []}
            entry = {
                "kind": action["kind"],
                "type": action["type"],
                "code": action["code"],
                "signer": ev["signer"],
                "intendedTo": ev["intendedTo"],
                "timestamp": ev["timestamp"],
                "txHash": ev["txHash"],
            }
            if action["kind"] == "A":
                actions_by_id[oid]["accepts"].append(entry)
            elif action["kind"] == "D":
                actions_by_id[oid]["dones"].append(entry)
            elif action["kind"] == "X":
                actions_by_id[oid]["cancels"].append(entry)

        parsed = parse_offer_metadata(meta)
        if not parsed:
            continue
        offers.append({
            **parsed,
            "signer": ev["signer"],
            "timestamp": ev["timestamp"],
            "txHash": ev["txHash"],
            "payloadHash": ev.get("payloadHash", ""),
        })

    for o in offers:
        acts = actions_by_id.get(o["id"], {"accepts": [], "dones": [], "cancels": []})
        o["accepter"] = acts["accepts"][0]["signer"] if acts["accepts"] else None
        o["acceptTx"] = acts["accepts"][0]["txHash"] if acts["accepts"] else None
        o["doneBy"] = acts["dones"][0]["signer"] if acts["dones"] else None
        o["doneTx"] = acts["dones"][0]["txHash"] if acts["dones"] else None
        o["canceledBy"] = acts["cancels"][0]["signer"] if acts["cancels"] else None
        o["cancelTx"] = acts["cancels"][0]["txHash"] if acts["cancels"] else None
        if acts["cancels"]:
            o["status"] = "CANCELED"
        elif acts["dones"]:
            o["status"] = "DONE"
        elif acts["accepts"]:
            o["status"] = "ACCEPTED"
        else:
            o["status"] = "OPEN"

    offers.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return offers
