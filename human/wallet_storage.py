"""PQID session flag (identity file is the store; logout clears memory only)."""
# Identity persistence is human/identity.py. This module marks in-app session.
_session_unlocked = False

def set_unlocked(v: bool):
    global _session_unlocked
    _session_unlocked = bool(v)

def is_unlocked() -> bool:
    return _session_unlocked

def logout_session():
    set_unlocked(False)
