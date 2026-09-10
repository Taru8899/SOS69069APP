"""
SOS 69069 Legacy claim helpers.
Metadata format mirrors legacy.js:
  L1|S|newShort|oldShort|newEff|oldEff|oldEffAfter
  L1|F|...
"""
MAX_META = 64


def short_id(addr: str) -> str:
    a = addr.lower().replace("0x", "")
    return a[:4] + a[-4:]


def make_legacy_metadata(kind: str, new_addr: str, old_addr: str,
                         new_effective: int, old_effective: int) -> str:
    """
    kind: "S" (START) or "F" (FINISH)
    oldAfter = old_effective + 1  (this tx itself adds +1 to old)
    """
    if kind not in ("S", "F"):
        raise ValueError("kind must be S or F")
    new_s = short_id(new_addr)
    old_s = short_id(old_addr)
    old_after = int(old_effective) + 1
    meta = (
        f"L1|{kind}|{new_s}|{old_s}|"
        f"{int(new_effective)}|{int(old_effective)}|{old_after}"
    )
    if len(meta.encode("utf-8")) > MAX_META:
        raise ValueError("Legacy metadata exceeds 64 bytes")
    return meta
