"""
Per-page local caches under app user_data_dir.

  trends_events.json  — TRUTH
  msg_events.json     — MSG
  pres_offers.json    — PRES
  lsf_snapshots.json  — LSF

Each LOAD/recheck merges network data into that page's file, then caps size.
ID page can wipe all of these via clear_all_caches().
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

# --- file names (separate per page) ---
FILE_TRUTH = "trends_events.json"
FILE_MSG = "msg_events.json"
FILE_PRES = "pres_offers.json"
FILE_LSF = "lsf_snapshots.json"

ALL_CACHE_FILES = (FILE_TRUTH, FILE_MSG, FILE_PRES, FILE_LSF)

# --- caps ---
CAP_TRUTH = 12000
CAP_MSG = 2000
CAP_PRES = 500
CAP_LSF = 20


def _path(user_data_dir: str, name: str) -> str:
    return os.path.join(user_data_dir, name)


def _read(user_data_dir: str, name: str) -> tuple[list, dict]:
    path = _path(user_data_dir, name)
    if not os.path.isfile(path):
        return [], {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("items")
        if items is None:
            items = data.get("events") or []
        if not isinstance(items, list):
            return [], {}
        meta = {
            "updated_at": int(data.get("updated_at") or 0),
            "count": len(items),
            "source": data.get("source") or "cache",
        }
        return items, meta
    except Exception:
        return [], {}


def _write(user_data_dir: str, name: str, items: list, source: str = "network") -> str:
    os.makedirs(user_data_dir, exist_ok=True)
    path = _path(user_data_dir, name)
    payload = {
        "updated_at": int(time.time()),
        "source": source,
        "count": len(items),
        "items": items,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path


def clear_all_caches(user_data_dir: str) -> list:
    """Delete all page cache files. Returns list of removed names."""
    removed = []
    for name in ALL_CACHE_FILES:
        path = _path(user_data_dir, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed.append(name)
            for suffix in (".tmp",):
                p2 = path + suffix
                if os.path.isfile(p2):
                    os.remove(p2)
        except Exception:
            pass
    return removed


def cache_age_seconds(user_data_dir: str, name: str) -> int | None:
    _, meta = _read(user_data_dir, name)
    ts = meta.get("updated_at") or 0
    if not ts:
        return None
    return max(0, int(time.time()) - int(ts))


# ----- generic merge -----

def _event_key(ev: dict) -> tuple:
    return (
        str(ev.get("txHash") or ""),
        str(ev.get("logIndex") if ev.get("logIndex") is not None else ""),
        str(ev.get("blockNumber") if ev.get("blockNumber") is not None else ""),
    )


def _compact_event(ev: dict) -> dict:
    return {
        "signer": ev.get("signer") or "",
        "intendedTo": ev.get("intendedTo") or "",
        "metadata": ev.get("metadata") or "",
        "timestamp": int(ev.get("timestamp") or 0),
        "txHash": ev.get("txHash") or "",
        "blockNumber": int(ev.get("blockNumber") or 0),
        "logIndex": int(ev.get("logIndex") or 0),
        "direction": ev.get("direction") or "",
        "address": ev.get("address") or "",
    }


def merge_events(existing: list, incoming: list, max_events: int) -> list:
    by_key = {}
    for ev in existing or []:
        if isinstance(ev, dict):
            by_key[_event_key(ev)] = _compact_event(ev)
    for ev in incoming or []:
        if isinstance(ev, dict):
            by_key[_event_key(ev)] = _compact_event(ev)
    merged = list(by_key.values())
    merged.sort(
        key=lambda e: (int(e.get("timestamp") or 0), int(e.get("blockNumber") or 0)),
        reverse=True,
    )
    return merged[:max_events]


def merge_offers(existing: list, incoming: list, max_items: int = CAP_PRES) -> list:
    """Merge presence offers by id; incoming status wins."""
    by_id = {}
    for o in existing or []:
        if isinstance(o, dict) and o.get("id"):
            by_id[str(o["id"])] = o
    for o in incoming or []:
        if isinstance(o, dict) and o.get("id"):
            by_id[str(o["id"])] = o
    merged = list(by_id.values())
    merged.sort(key=lambda x: int(x.get("timestamp") or 0), reverse=True)
    return merged[:max_items]


# ----- TRUTH -----

def truth_load(user_data_dir: str):
    return _read(user_data_dir, FILE_TRUTH)


def truth_save(user_data_dir: str, events: list, source: str = "network"):
    items = [_compact_event(e) for e in events]
    return _write(user_data_dir, FILE_TRUTH, items, source)


def truth_merge_save(user_data_dir: str, fresh: list, source: str = "network+merge"):
    cached, _ = truth_load(user_data_dir)
    merged = merge_events(cached, fresh, CAP_TRUTH)
    truth_save(user_data_dir, merged, source)
    return merged


# ----- MSG -----

def msg_load(user_data_dir: str):
    return _read(user_data_dir, FILE_MSG)


def msg_save(user_data_dir: str, events: list, source: str = "network"):
    items = [_compact_event(e) for e in events]
    return _write(user_data_dir, FILE_MSG, items, source)


def msg_merge_save(user_data_dir: str, fresh: list, address: str = "", direction: str = "", source: str = "network+merge"):
    tagged = []
    for e in fresh or []:
        c = _compact_event(e)
        c["address"] = (address or c.get("address") or "").lower()
        c["direction"] = direction or c.get("direction") or ""
        tagged.append(c)
    cached, _ = msg_load(user_data_dir)
    merged = merge_events(cached, tagged, CAP_MSG)
    msg_save(user_data_dir, merged, source)
    return merged


def msg_filter(events: list, address: str, direction: str) -> list:
    addr = (address or "").lower()
    direction = (direction or "").lower()
    out = []
    for e in events or []:
        if direction and (e.get("direction") or "").lower() not in ("", direction):
            # allow untagged legacy rows matching addr only
            if e.get("direction"):
                continue
        if addr:
            # trust: intendedTo; push: signer; or stored address bucket
            bucket = (e.get("address") or "").lower()
            if bucket and bucket != addr:
                continue
            if not bucket:
                if direction == "trust" and (e.get("intendedTo") or "").lower() != addr:
                    continue
                if direction == "push" and (e.get("signer") or "").lower() != addr:
                    continue
        out.append(e)
    return out


# ----- PRES -----

def pres_load(user_data_dir: str):
    return _read(user_data_dir, FILE_PRES)


def pres_save(user_data_dir: str, offers: list, source: str = "network"):
    return _write(user_data_dir, FILE_PRES, list(offers or []), source)


def pres_merge_save(user_data_dir: str, fresh_offers: list, source: str = "network+merge"):
    cached, _ = pres_load(user_data_dir)
    merged = merge_offers(cached, fresh_offers, CAP_PRES)
    pres_save(user_data_dir, merged, source)
    return merged


# ----- LSF -----

def lsf_load(user_data_dir: str):
    return _read(user_data_dir, FILE_LSF)


def lsf_save(user_data_dir: str, snapshots: list, source: str = "local"):
    return _write(user_data_dir, FILE_LSF, list(snapshots or [])[:CAP_LSF], source)


def lsf_add_snapshot(user_data_dir: str, snap: dict, source: str = "check"):
    cached, _ = lsf_load(user_data_dir)
    row = dict(snap or {})
    row["saved_at"] = int(time.time())
    items = [row] + [x for x in cached if isinstance(x, dict)]
    # cap
    items = items[:CAP_LSF]
    lsf_save(user_data_dir, items, source)
    return items
