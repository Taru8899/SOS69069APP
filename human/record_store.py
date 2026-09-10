"""Local PQID data only — never touches main chain caches."""
from __future__ import annotations
import json, os, shutil, time
from typing import List

RECORDS_DIR = "human_records"
ATTEST_DIR = "human_attestations"
IDENTITY_FILE = "human_identity.json"
SESSION_NOTE = "human_session_note.json"

def clear_human_data(user_data_dir: str) -> list:
    removed = []
    for name in (IDENTITY_FILE, SESSION_NOTE):
        path = os.path.join(user_data_dir, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(name)
            except Exception:
                pass
    for dname in (RECORDS_DIR, ATTEST_DIR):
        path = os.path.join(user_data_dir, dname)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
                removed.append(dname + "/")
            except Exception:
                pass
    return removed

def list_records(user_data_dir: str) -> List[dict]:
    path = os.path.join(user_data_dir, RECORDS_DIR)
    if not os.path.isdir(path):
        return []
    out = []
    for fn in os.listdir(path):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    out.sort(key=lambda x: x.get("saved_at") or 0, reverse=True)
    return out

def save_record(user_data_dir: str, record: dict) -> str:
    path = os.path.join(user_data_dir, RECORDS_DIR)
    os.makedirs(path, exist_ok=True)
    rid = record.get("id") or record.get("hash") or str(int(time.time()))
    record = dict(record)
    record["saved_at"] = int(time.time())
    fp = os.path.join(path, f"{rid}.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return fp
