"""PQID rpc facade — re-exports main rpc when available for chain checks."""
try:
    import rpc as main_rpc
except Exception:
    main_rpc = None

def available() -> bool:
    return main_rpc is not None
