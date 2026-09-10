"""Mutual attestation helpers (v0 local)."""
from __future__ import annotations
import json, os, time

def save_acceptance(user_data_dir: str, subject: dict) -> str:
    path = os.path.join(user_data_dir, "human_attestations")
    os.makedirs(path, exist_ok=True)
    fn = os.path.join(path, f"accept_{int(time.time())}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"type": "human_accept", "subject": subject, "accepted_at": int(time.time())}, f, indent=2)
    return fn
