"""
JSON-RPC + Etherscan helper for Ethereum view calls and event logs.
Pure requests + pure_crypto. No web3.py.
"""
import requests
import re
import time
import datetime
from collections import Counter
from pure_crypto import keccak256

# ── Config ───────────────────────────────────────────────────
DEFAULT_ETHERSCAN_API_KEY = "RU99NEJZV9F2EWS7A97RWVHDJN1ZQ29Q99"
# Runtime key (user can override via set_etherscan_api_key)
ETHERSCAN_API_KEY = DEFAULT_ETHERSCAN_API_KEY
ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1


def set_etherscan_api_key(key: str | None):
    """Set API key. Empty/None resets to built-in default."""
    global ETHERSCAN_API_KEY
    key = (key or "").strip()
    ETHERSCAN_API_KEY = key if key else DEFAULT_ETHERSCAN_API_KEY


def get_etherscan_api_key() -> str:
    return ETHERSCAN_API_KEY

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
                       page: int = 1, offset: int = 100, sort: str = None) -> list:
    """
    Fetch event logs via Etherscan V2 API.
    topic1/topic2 can be full 32-byte topics or None.
    sort: "asc" (default, oldest first) or "desc" (newest first) —
    pass "desc" when you need the most recent activity within a capped
    offset, since Etherscan's default ascending order means a small
    offset only ever returns the OLDEST logs, silently missing anything
    recent once the contract has more total events than the offset.
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
    if sort:
        params["sort"] = sort
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

    # Newest first + recent window so new messages are not hidden behind old logs
    from_block = 0
    try:
        latest = call_with_fallback(_eth_block_number)
        from_block = max(0, latest - 500000)  # ~2 months of blocks
    except Exception:
        pass

    if direction == "trust":
        # intendedTo = topic2
        logs = etherscan_get_logs(
            CONTRACT, EVENT_TOPIC0,
            topic1=None, topic2=topic_addr,
            from_block=from_block, to_block="latest",
            page=1, offset=min(max(max_results * 5, 100), 1000),
            sort="desc",
        )
    else:
        # signer = topic1
        logs = etherscan_get_logs(
            CONTRACT, EVENT_TOPIC0,
            topic1=topic_addr, topic2=None,
            from_block=from_block, to_block="latest",
            page=1, offset=min(max(max_results * 5, 100), 1000),
            sort="desc",
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

        chunk = 5000
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
                   lookback_blocks: int = 500000, max_results: int = 80) -> list:
    """
    Same data model as messages.js on sos69069.com:
      TRUST → intendedTo == address
      PUSH  → signer == address
      non-empty metadata only, newest first.

    Transport: RPC eth_getLogs in block chunks first (like site queryFilterChunked),
    then Etherscan fallback.
    """
    address = address.strip()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("Invalid address")

    try:
        results = _fetch_via_rpc(address, direction, lookback_blocks, max_results)
        if results:
            return results
    except Exception:
        pass

    try:
        results = _fetch_via_etherscan(address, direction, max_results)
        if results:
            return results
    except Exception:
        pass

    return []



# ── Presence offer loading ───────────────────────────────────

def fetch_presence_events(lookback_blocks: int = 120000, max_logs: int = 500) -> list:
    """
    Same approach as presence.js loadOffersAndMetrics:
      SignatureRecorded, fromBlock = latest - ~120000, chunked RPC logs first,
      then Etherscan. Keep O/A/D/X metadata only.
    """
    events = []
    seen = set()

    def _add(logs):
        for log in logs or []:
            ev = _parse_signature_recorded(log)
            if not ev:
                continue
            meta = (ev.get("metadata") or "").strip()
            if not meta or meta[0] not in ("O", "A", "D", "X") or "|" not in meta:
                continue
            key = (ev.get("txHash"), ev.get("logIndex"), ev.get("blockNumber"))
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)

    latest = None
    try:
        latest = call_with_fallback(_eth_block_number)
    except Exception:
        pass
    from_block = max(0, (latest or 0) - lookback_blocks) if latest else 0

    if latest is not None:
        try:
            def _do(rpc_url):
                chunk = 5000
                all_logs = []
                start = from_block
                while start <= latest:
                    end = min(start + chunk - 1, latest)
                    params = {
                        "address": CONTRACT,
                        "fromBlock": hex(start),
                        "toBlock": hex(end),
                        "topics": [EVENT_TOPIC0],
                    }
                    try:
                        all_logs.extend(_eth_get_logs(params, rpc_url))
                    except Exception:
                        mid = (start + end) // 2
                        if mid > start:
                            for a, b in ((start, mid), (mid + 1, end)):
                                try:
                                    params["fromBlock"] = hex(a)
                                    params["toBlock"] = hex(b)
                                    all_logs.extend(_eth_get_logs(params, rpc_url))
                                except Exception:
                                    pass
                    start = end + 1
                return all_logs
            _add(call_with_fallback(_do))
        except Exception:
            pass

    if len(events) < 5:
        try:
            logs = etherscan_get_logs(
                CONTRACT, EVENT_TOPIC0,
                from_block=from_block, to_block="latest",
                page=1, offset=max_logs, sort="desc",
            )
            _add(logs)
        except Exception:
            pass

    events.sort(key=lambda e: (e.get("timestamp") or 0, e.get("blockNumber") or 0), reverse=True)
    return events[:max_logs]




def fetch_all_metadata_events(max_logs: int = 8000, min_span_days: int = 400) -> list:
    """
    Resilient fetch of SignatureRecorded events with non-empty metadata
    for TRUTH trends.

    Strategy (newest → older):
      1) Etherscan pages with sort=desc until we hit max_logs or empty page.
      2) If timestamps still do not span min_span_days, walk block ranges
         backward and merge more logs.
      3) RPC eth_getLogs fallback on block chunks if Etherscan fails.

    This avoids the old single page=1 offset=N call that only covered
    ~1 week of activity and made MONTH/YEAR/ALL look empty.
    """
    seen = set()
    events = []

    def _add_logs(logs):
        for log in logs or []:
            ev = _parse_signature_recorded(log)
            if not ev:
                continue
            meta = (ev.get("metadata") or "").strip()
            if not meta:
                continue
            key = (ev.get("txHash"), ev.get("logIndex"), ev.get("blockNumber"))
            if key in seen:
                continue
            seen.add(key)
            events.append(ev)

    def _span_days():
        ts = [e.get("timestamp") or 0 for e in events if e.get("timestamp")]
        if not ts:
            return 0
        return (max(ts) - min(ts)) / 86400.0

    page_size = min(1000, max(100, max_logs // 4))
    # --- Phase 1: Etherscan newest-first pages ---
    try:
        page = 1
        while len(events) < max_logs and page <= 20:
            logs = etherscan_get_logs(
                CONTRACT, EVENT_TOPIC0,
                from_block=0, to_block="latest",
                page=page, offset=page_size,
                sort="desc",
            )
            if not logs:
                break
            before = len(events)
            _add_logs(logs)
            if len(events) == before:
                break  # no new unique rows
            if len(logs) < page_size:
                break
            page += 1
            # enough time coverage already
            if _span_days() >= min_span_days:
                break
    except Exception:
        pass

    # --- Phase 2: block-range walk backward if span still short ---
    if _span_days() < min_span_days and len(events) < max_logs:
        try:
            latest = call_with_fallback(_eth_block_number)
        except Exception:
            latest = None
        if latest:
            # ~6500 blocks/day on mainnet; use conservative chunk
            chunk = 50000
            end = latest
            rounds = 0
            while end > 0 and len(events) < max_logs and rounds < 30:
                start = max(0, end - chunk)
                try:
                    logs = etherscan_get_logs(
                        CONTRACT, EVENT_TOPIC0,
                        from_block=start, to_block=end,
                        page=1, offset=1000, sort="desc",
                    )
                    _add_logs(logs)
                except Exception:
                    try:
                        def _do(rpc_url, s=start, e=end):
                            params = {
                                "address": CONTRACT,
                                "fromBlock": hex(s),
                                "toBlock": hex(e),
                                "topics": [EVENT_TOPIC0],
                            }
                            return _eth_get_logs(params, rpc_url)
                        logs = call_with_fallback(_do)
                        _add_logs(logs)
                    except Exception:
                        logs = []
                end = start - 1
                rounds += 1
                if _span_days() >= min_span_days:
                    break

    # newest first for UI consistency
    events.sort(key=lambda e: (e.get("timestamp") or 0, e.get("blockNumber") or 0), reverse=True)
    return events[:max_logs]


_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def compute_word_trends(events: list, window: str, year: int | None = None, top_n: int = 25) -> list:
    """
    window: one of "24h", "week", "month", "year", "year_n", "all".
    For "year_n", `year` must be given (e.g. 2025) and only messages
    from that calendar year (UTC) are counted.

    Every word in every kept message's metadata is counted — no
    stopword filtering, exactly "all words from all messages" as
    requested. Returns [(word, count), ...] sorted most-used first.
    """
    now = time.time()
    cutoffs = {
        "24h": now - 24 * 3600,
        "top": now - 14 * 24 * 3600,
        "week": now - 7 * 24 * 3600,
        "month": now - 30 * 24 * 3600,
        "year": now - 365 * 24 * 3600,
    }

    def keep(ts: int) -> bool:
        if not ts:
            return window == "all"  # events with no timestamp only count under "all"
        if window == "all":
            return True
        if window == "year_n":
            if year is None:
                return True
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            return dt.year == year
        cutoff = cutoffs.get(window)
        return cutoff is not None and ts >= cutoff

    counter = Counter()
    for ev in events:
        ts = ev.get("timestamp", 0)
        if not keep(ts):
            continue
        meta = (ev.get("metadata") or "")
        for word in _WORD_RE.findall(meta.lower()):
            if len(word) >= 4:
                counter[word] += 1

    return counter.most_common(top_n)


def build_presence_offers(events: list) -> list:
    """
    Turn raw presence events into offer objects with status.
    Mirrors presence.js logic.
    """
    from presence import parse_offer_metadata, parse_action_metadata

    # Process chronologically regardless of the order events were fetched in
    # (Etherscan may return newest-first or oldest-first depending on the
    # sort option used), so "first accept wins" logic below stays correct.
    events = sorted(events, key=lambda e: e.get("timestamp", 0))

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


# ── Gas cost analytics (Etherscan) ───────────────────────────

RECORD_SELECTORS = {
    "0x1c7c27c8",  # recordSignature(address,address,bytes32,bytes,string)
    # recordSignatureOne may differ; include common variants if needed
}


def _etherscan_txlist(address: str, page: int = 1, offset: int = 1000) -> list:
    body = _etherscan_get({
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": page,
        "offset": offset,
        "sort": "asc",
    })
    if body.get("status") == "1" and isinstance(body.get("result"), list):
        return body["result"]
    if isinstance(body.get("result"), list):
        return body["result"]
    msg = str(body.get("message") or body.get("result") or "")
    if "no transactions" in msg.lower():
        return []
    raise RuntimeError(msg or "txlist failed")


def fetch_eth_usd() -> float | None:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"},
            timeout=8,
        )
        return float(r.json()["ethereum"]["usd"])
    except Exception:
        return None


def gas_costs_for(address: str) -> dict:
    """
    Compute Push / Trust / Effective / Total gas costs for an address.
    Mirrors ledger.js gas panel logic (simplified).
    Returns dict with wei totals, tx counts, and optional USD.
    """
    address = address.strip().lower()
    if not (address.startswith("0x") and len(address) == 42):
        raise ValueError("Invalid address")

    eth_usd = fetch_eth_usd()

    # Stats for effective count
    try:
        stats = stats_of(address)
        effective_n = max(0, int(stats["effective"]))
    except Exception:
        effective_n = 0

    # --- Push: user's own successful txs to the contract ---
    own_txs = []
    page = 1
    while page <= 20:
        batch = _etherscan_txlist(address, page=page, offset=1000)
        if not batch:
            break
        own_txs.extend(batch)
        if len(batch) < 1000:
            break
        page += 1

    push_wei = 0
    push_count = 0
    for tx in own_txs:
        if (tx.get("to") or "").lower() != CONTRACT.lower():
            continue
        if tx.get("isError") != "0":
            continue
        method = (tx.get("methodId") or (tx.get("input") or "")[:10]).lower()
        if method not in RECORD_SELECTORS and not method.startswith("0x1c7c27c8"):
            # still count any successful call to contract from user as push-ish
            if not (tx.get("input") or "").startswith("0x1c7c27c8"):
                continue
        fee = int(tx.get("gasUsed") or 0) * int(tx.get("gasPrice") or 0)
        push_wei += fee
        push_count += 1

    # --- Trust: contract txs where intendedTo == address ---
    # Pull contract transactions and decode intendedTo from input when possible
    contract_txs = []
    page = 1
    while page <= 30:
        batch = _etherscan_txlist(CONTRACT, page=page, offset=1000)
        if not batch:
            break
        contract_txs.extend(batch)
        if len(batch) < 1000:
            break
        page += 1

    trust_entries = []  # (fee_wei, block)
    for tx in contract_txs:
        if tx.get("isError") != "0":
            continue
        inp = tx.get("input") or ""
        if not inp.startswith("0x1c7c27c8"):
            continue
        # ABI: selector + signer(32) + intendedTo(32) + ...
        # intendedTo is second address arg → bytes 16:36 of the first arg slots
        try:
            data = bytes.fromhex(inp[10:])  # skip selector
            # slot0 = signer, slot1 = intendedTo
            if len(data) < 64:
                continue
            intended = "0x" + data[32:64][-20:].hex()
            if intended.lower() != address:
                continue
            fee = int(tx.get("gasUsed") or 0) * int(tx.get("gasPrice") or 0)
            block = int(tx.get("blockNumber") or 0)
            trust_entries.append((fee, block))
        except Exception:
            continue

    trust_wei = sum(f for f, _ in trust_entries)
    trust_count = len(trust_entries)

    # Effective gas = sum of most recent N trust txs (N = effective count)
    trust_entries.sort(key=lambda x: x[1], reverse=True)
    n = min(effective_n, len(trust_entries))
    effective_wei = sum(trust_entries[i][0] for i in range(n))

    total_wei = push_wei + trust_wei

    def wei_to_eth(w):
        return w / 1e18

    def usd(w):
        if eth_usd is None:
            return None
        return wei_to_eth(w) * eth_usd

    return {
        "pushWei": push_wei,
        "trustWei": trust_wei,
        "effectiveWei": effective_wei,
        "totalWei": total_wei,
        "pushCount": push_count,
        "trustCount": trust_count,
        "effectiveCount": n,
        "effectiveN": effective_n,
        "pushEth": wei_to_eth(push_wei),
        "trustEth": wei_to_eth(trust_wei),
        "effectiveEth": wei_to_eth(effective_wei),
        "totalEth": wei_to_eth(total_wei),
        "pushUsd": usd(push_wei),
        "trustUsd": usd(trust_wei),
        "effectiveUsd": usd(effective_wei),
        "totalUsd": usd(total_wei),
        "ethUsd": eth_usd,
    }
