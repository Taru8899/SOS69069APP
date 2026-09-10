"""
SOS 69069 Presence protocol helpers.
Metadata formats mirror presence.js on the website.
"""
import os
import re
from pure_crypto import keccak256

MAX_META = 64


def make_offer_id() -> str:
    return os.urandom(12).hex()  # 24 hex chars


def build_offer_metadata(typ: str, qty: int, ret: str = "", contact: str = "", offer_id: str = None) -> str:
    """O|1|{T|P}|{id24}|{qty}|{return}|{contact}"""
    t = "P" if typ == "P" else "T"
    q = str(max(1, int(qty)))
    r = (ret or "").strip()
    c = (contact or "").strip()
    oid = (offer_id or make_offer_id()).replace("0x", "").lower()[:24].ljust(24, "0")
    meta = f"O|1|{t}|{oid}|{q}|{r}|{c}"
    if len(meta.encode()) > MAX_META:
        # trim return/contact if needed
        while len(meta.encode()) > MAX_META and len(r) > 0:
            r = r[:-1]
            meta = f"O|1|{t}|{oid}|{q}|{r}|{c}"
        while len(meta.encode()) > MAX_META and len(c) > 0:
            c = c[:-1]
            meta = f"O|1|{t}|{oid}|{q}|{r}|{c}"
    return meta


def build_accept_metadata(typ: str, offer_id: str) -> str:
    """A|1|{T|P}|{id24}|{t1a|p1a}"""
    t = "P" if typ == "P" else "T"
    code = "p1a" if t == "P" else "t1a"
    oid = offer_id.replace("0x", "").lower()[:24].ljust(24, "0")
    return f"A|1|{t}|{oid}|{code}"


def build_done_metadata(typ: str, offer_id: str) -> str:
    """D|1|{T|P}|{id24}|c1"""
    t = "P" if typ == "P" else "T"
    oid = offer_id.replace("0x", "").lower()[:24].ljust(24, "0")
    return f"D|1|{t}|{oid}|c1"


def build_cancel_metadata(typ: str, offer_id: str) -> str:
    """X|1|{T|P}|{id24}|x1"""
    t = "P" if typ == "P" else "T"
    oid = offer_id.replace("0x", "").lower()[:24].ljust(24, "0")
    return f"X|1|{t}|{oid}|x1"


def parse_offer_metadata(meta: str):
    if not meta or not isinstance(meta, str):
        return None
    parts = meta.split("|")
    if parts[0] != "O" or len(parts) < 5:
        return None
    typ = parts[2]
    if typ not in ("T", "P"):
        return None
    return {
        "kind": "O",
        "version": parts[1] if len(parts) > 1 else "1",
        "type": typ,
        "id": parts[3] if len(parts) > 3 else "",
        "qty": parts[4] if len(parts) > 4 else "1",
        "ret": parts[5] if len(parts) > 5 else "",
        "contact": parts[6] if len(parts) > 6 else "",
        "raw": meta,
    }


def parse_action_metadata(meta: str):
    if not meta or not isinstance(meta, str):
        return None
    parts = meta.split("|")
    if len(parts) < 5:
        return None
    kind = parts[0]
    if kind not in ("A", "D", "X"):
        return None
    typ = parts[2]
    if typ not in ("T", "P"):
        return None
    return {
        "kind": kind,
        "version": parts[1],
        "type": typ,
        "id": parts[3],
        "code": parts[4],
        "raw": meta,
    }


def classify_action(action) -> str | None:
    if not action:
        return None
    if action["kind"] == "A":
        if action["code"] == "t1a":
            return "trustAccepted"
        if action["code"] == "p1a":
            return "pushAccepted"
    elif action["kind"] == "D" and action["code"] == "c1":
        return "completed"
    elif action["kind"] == "X" and action["code"] == "x1":
        return "canceled"
    return None
