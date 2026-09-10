"""Submit record commitment — bridge to main eth payer when embedded."""
from __future__ import annotations

def describe_submit_bridge() -> str:
    return (
        "When embedded in main SOS 69069: use unlocked Ethereum payer "
        "(App.get_payer_key) + existing tx helpers to commit H(T).\n"
        "Standalone PQID: configure local gas key or export hash for external submit."
    )

def try_get_main_payer_address():
    try:
        from kivy.app import App
        from sos_core import address_from_private_key
        app = App.get_running_app()
        key = None
        if hasattr(app, "get_payer_key"):
            key = app.get_payer_key()
        if not key and getattr(app, "private_key", None):
            key = app.private_key
        if not key:
            return None
        return address_from_private_key(key)
    except Exception:
        return None
