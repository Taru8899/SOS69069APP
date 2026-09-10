"""
Central place to edit app labels and text styles.

Change only values here — screens import LABEL / style helpers.
Do not put logic here.

Keys are stable IDs; "text" is what the user sees.
Optional style keys: font_size (dp), bold (bool), color (hex string like "#ffffff").
"""

# Default colors (hex) used when a label sets "color"
COLORS = {
    "text": "#ffffff",
    "text_sec": "#bbbbbb",
    "text_muted": "#9ca3af",
    "green": "#22c55e",
    "yellow": "#facc15",
    "blue": "#5b8bff",
    "orange": "#f97316",
    "danger": "#ef4444",
}

# ---- Editable labels ----
# font_size is in dp (number). bold True/False. color = key from COLORS or "#rrggbb".
LABELS = {
    # Nav
    "nav.truth": {"text": "TRUTH", "font_size": 13, "bold": True},
    "nav.msg": {"text": "MSG", "font_size": 13, "bold": True},
    "nav.sign": {"text": "SIGN", "font_size": 13, "bold": True},
    "nav.gas": {"text": "GAS", "font_size": 13, "bold": True},
    "nav.pres": {"text": "PRES", "font_size": 13, "bold": True},
    "nav.bt": {"text": "BT", "font_size": 13, "bold": True},
    "nav.ss": {"text": "S&S", "font_size": 13, "bold": True},
    "nav.lsf": {"text": "LSF", "font_size": 13, "bold": True},
    "nav.id": {"text": "ID", "font_size": 13, "bold": True},

    # Loading / welcome
    "load.loading": {"text": "Loading ...", "font_size": 18, "bold": True},
    "load.title": {"text": "SOS 69069", "font_size": 16, "bold": True},
    "load.tagline": {"text": "Activity and Signatures", "font_size": 15, "bold": True, "color": "text_sec"},

    # Common
    "common.gas_payer_prefix": {"text": "Gas payer: ", "font_size": 12, "bold": False, "color": "yellow"},
    "common.connected_prefix": {"text": "Connected: ", "font_size": 13, "bold": True, "color": "green"},
    "common.old_prefix": {"text": "Old: ", "font_size": 13, "bold": True, "color": "green"},
    "common.poster_prefix": {"text": "Poster ", "font_size": 14, "bold": True, "color": "text_sec"},
    "common.accepter_prefix": {"text": "Accepter ", "font_size": 11, "bold": False, "color": "yellow"},

    # S&S
    "ss.tab_sign": {"text": "1. SIGN", "font_size": 13, "bold": True},
    "ss.tab_submit": {"text": "2. SUBMIT", "font_size": 13, "bold": True},
    "ss.address": {"text": "Address", "font_size": 17, "bold": True, "color": "yellow"},
    "ss.messages": {"text": "Messages (one per line, max 200)", "font_size": 17, "bold": True, "color": "yellow"},
    "ss.sign_btn": {"text": "SIGN PAYLOAD(S)", "font_size": 15, "bold": True},
    "ss.payload_placeholder": {
        "text": "Signed payload JSON will appear here — long-press to select & copy",
        "font_size": 11,
        "bold": False,
        "color": "green",
    },

    # ID
    "id.title": {"text": "SOS 69069", "font_size": 22, "bold": True},
    "id.motto": {
        "text": "Originates from verified Activity and Signatures.\nWhatever you do. SOS records.\nWhatever you do. Continue ...",
        "font_size": 14,
        "bold": True,
    },
}


def label(key: str, default: str = "") -> str:
    """Return display text for key."""
    item = LABELS.get(key)
    if not item:
        return default
    return item.get("text", default)


def style(key: str) -> dict:
    """
    Return kivy-oriented style dict:
      font_size (float dp value — caller wraps with dp()),
      bold (bool),
      color_hex (str or None)
    """
    item = LABELS.get(key) or {}
    color = item.get("color")
    if color and not str(color).startswith("#"):
        color = COLORS.get(color, color)
    return {
        "font_size": item.get("font_size"),
        "bold": item.get("bold"),
        "color_hex": color,
    }
