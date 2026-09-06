"""Shared UI theme, widgets, and helpers for SOS 69069."""
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.graphics import Color, RoundedRectangle
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
import os
import webbrowser
import re
import threading
from datetime import datetime

from sos_core import address_from_private_key, CONTRACT_ADDRESS
import tx as txmod

CHAIN_ID = 1
MAX_META = 64

APP_DISPLAY_VERSION = "1.9.8.7.6"


def get_app_version() -> str:
    """User-facing version (display)."""
    return APP_DISPLAY_VERSION


def get_package_version() -> str:
    """Version string from buildozer.spec (Android versionName)."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "buildozer.spec")
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("version") and "=" in line and "numeric" not in line:
                    val = line.split("=", 1)[1].strip()
                    if len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
                        val = val[1:-1]
                    return val
    except Exception:
        pass
    return "1.9.8"


def get_build_fingerprint() -> str:
    """SHA-256 of BUILD_FINGERPRINT file (full APK hash written at release), else local source tag."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "BUILD_FINGERPRINT")
        if os.path.isfile(path):
            with open(path, "r") as f:
                return f.read().strip().split()[0][:64]
    except Exception:
        pass
    return "unknown"

# Brand colors
BG          = get_color_from_hex("#0a0e0b")
CARD_BG     = get_color_from_hex("#141b16")
INPUT_BG    = get_color_from_hex("#232f27")
BORDER      = get_color_from_hex("#2c3830")
TEXT        = get_color_from_hex("#ffffff")
TEXT_SEC    = get_color_from_hex("#bbbbbb")
TEXT_MUTED  = get_color_from_hex("#9ca3af")
GREEN       = get_color_from_hex("#04aa34")
GREEN_BR    = get_color_from_hex("#22c55e")
BLUE        = get_color_from_hex("#0038fe")
BLUE_SOFT   = get_color_from_hex("#5b8bff")
YELLOW      = get_color_from_hex("#facc15")
ORANGE      = get_color_from_hex("#f97316")
DANGER      = get_color_from_hex("#ef4444")

Window.clearcolor = BG


def utf8_len(s: str) -> int:
    return len(s.encode("utf-8"))


def extract_conv_code(metadata: str):
    m = re.search(r"(?:^|\s)([a-fA-F0-9]{8})$", (metadata or "").strip())
    return m.group(1).lower() if m else None


def short_addr(a: str) -> str:
    if not a or len(a) < 12:
        return a or "—"
    return a[:6] + "…" + a[-4:]



def open_url(url: str):
    try:
        webbrowser.open(str(url))
    except Exception:
        pass


def etherscan_address(addr: str) -> str:
    return "https://etherscan.io/address/" + (addr or "").strip()


def etherscan_tx(txh: str) -> str:
    h = (txh or "").strip()
    if h and not h.startswith("0x"):
        h = "0x" + h
    return "https://etherscan.io/tx/" + h


class LinkButton(Button):
    """Tappable green link-style control (all app links)."""
    def __init__(self, text="", url=None, color=None, font_size=None,
                 height=None, halign="left", **kwargs):
        kwargs.pop("halign", None)
        super().__init__(**kwargs)
        self.text = text
        self.background_normal = ""
        self.background_down = ""
        self.background_color = (0, 0, 0, 0)
        self.color = color or GREEN_BR
        self.bold = True
        self.font_size = font_size or dp(13)
        self.size_hint_y = None
        self.height = height or dp(28)
        try:
            self.halign = halign
        except Exception:
            pass
        self.url = url
        try:
            self.bind(size=lambda *a: setattr(self, "text_size", (self.width, None)))
        except Exception:
            pass
        self.bind(on_release=lambda *_: open_url(self.url) if self.url else None)


def fmt_time(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


# ── Widgets ──────────────────────────────────────────────────

class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = [dp(12), dp(12)]
        self.spacing = dp(8)
        self.size_hint_y = None
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*CARD_BG)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class BrandButton(Button):
    def __init__(self, text="", bg_color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.size_hint_y = None
        self.height = dp(48)
        self.background_normal = ""
        self.background_color = bg_color or BLUE
        self.color = TEXT
        self.bold = True
        self.font_size = dp(15)


class BrandInput(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(46)
        self.background_normal = ""
        self.background_active = ""
        self.background_color = INPUT_BG
        self.foreground_color = TEXT
        self.cursor_color = BLUE_SOFT
        self.padding = [dp(12), dp(12)]
        self.font_size = dp(14)
        self.write_tab = False


class MultiInput(TextInput):
    """Multi-line input; fixed height, scrolls internally when content is longer."""
    def __init__(self, **kwargs):
        h = kwargs.pop("height", dp(55))
        kwargs.setdefault("multiline", True)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = h
        self.background_normal = ""
        self.background_active = ""
        self.background_color = INPUT_BG
        self.foreground_color = TEXT
        self.cursor_color = BLUE_SOFT
        self.padding = [dp(10), dp(8)]
        self.font_size = dp(13)



class TitleLabel(Label):
    def __init__(self, text="", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = TEXT
        self.bold = True
        self.font_size = dp(20)
        self.size_hint_y = None
        self.height = dp(32)
        self.halign = "center"
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


class SubLabel(Label):
    def __init__(self, text="", color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = color or TEXT_SEC
        self.font_size = dp(13)
        self.size_hint_y = None
        self.height = dp(24)
        self.halign = "center"
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


class SectionLabel(Label):
    """Larger bold section titles (Create offer, Trends, etc.)."""
    def __init__(self, text="", color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = color or TEXT
        self.bold = True
        self.font_size = dp(17)
        self.size_hint_y = None
        self.height = dp(30)
        self.halign = "left"
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


def _logo_path():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("icon.png", "logo_smooth.png", "icon-192.png", "presplash.png", "sos69069.png"):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path
    return ""


def _logo_image(size_dp=40):
    src = _logo_path()
    if not src:
        return Label(text="SOS", color=GREEN_BR, bold=True, font_size=dp(14),
                     size_hint=(None, None), size=(dp(size_dp), dp(size_dp)))
    return Image(
        source=src,
        size_hint=(None, None),
        size=(dp(size_dp), dp(size_dp)),
        allow_stretch=True,
        keep_ratio=True,
    )


class HeaderBar(BoxLayout):
    """SOS logo top-left + title. Same inset on every page."""
    LEFT = 12   # dp applied below
    TOP = 8

    def __init__(self, title="SOS 69069", **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(52)
        self.spacing = dp(10)
        self.padding = [dp(HeaderBar.LEFT), dp(HeaderBar.TOP), dp(8), dp(4)]
        self.add_widget(_logo_image(40))
        lbl = Label(
            text=title,
            color=TEXT,
            bold=True,
            font_size=dp(18),
            halign="left",
            valign="middle",
            size_hint_x=1,
        )
        lbl.bind(size=lambda *a: setattr(lbl, "text_size", lbl.size))
        self.add_widget(lbl)


class PayerBar(BoxLayout):
    """Shows which unlocked wallet pays gas + logout."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.height = dp(52)
        self.spacing = dp(2)
        self.padding = [dp(HeaderBar.LEFT), 0, dp(8), 0]
        self.addr_lbl = Label(
            text="Gas payer: —",
            color=YELLOW,
            font_size=dp(12),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(20),
        )
        self.addr_lbl.bind(size=lambda *a: setattr(self.addr_lbl, "text_size", self.addr_lbl.size))
        self.add_widget(self.addr_lbl)
        row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(6))
        self.pick_btn = Button(
            text="Switch payer", background_normal="", background_color=INPUT_BG,
            color=TEXT, font_size=dp(11), bold=True, size_hint_x=0.55,
        )
        self.pick_btn.bind(on_release=self._cycle_payer)
        self.logout_btn = Button(
            text="LOGOUT", background_normal="", background_color=DANGER,
            color=TEXT, font_size=dp(11), bold=True, size_hint_x=0.45,
        )
        self.logout_btn.bind(on_release=self._logout)
        row.add_widget(self.pick_btn)
        row.add_widget(self.logout_btn)
        self.add_widget(row)
        Clock.schedule_once(lambda dt: self.refresh(), 0)

    def refresh(self):
        app = App.get_running_app()
        if app is None or not hasattr(app, "get_payer_key"):
            return
        try:
            payer = app.get_payer_key()
        except Exception:
            payer = None
        if payer:
            try:
                self.addr_lbl.text = "Gas payer: " + address_from_private_key(payer)
            except Exception:
                self.addr_lbl.text = "Gas payer: (error)"
        else:
            self.addr_lbl.text = "Gas payer: (locked — unlock a wallet)"
        try:
            n = sum(1 for k in (app.keys or {}).values() if k)
        except Exception:
            n = 0
        self.pick_btn.disabled = n < 2
        self.pick_btn.opacity = 1 if n >= 2 else 0.4

    def _cycle_payer(self, *_):
        app = App.get_running_app()
        app.cycle_payer_slot()
        self.refresh()

    def _logout(self, *_):
        app = App.get_running_app()
        app.logout()



class CopyableText(TextInput):
    """Selectable / copyable text (read-only). Use instead of Label for any value user may copy."""
    def __init__(self, text="", color=None, font_size=None, height=None, **kwargs):
        kwargs.setdefault("multiline", True)
        kwargs.setdefault("readonly", True)
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_active", "")
        super().__init__(**kwargs)
        self.text = text
        self.background_color = (0, 0, 0, 0)
        self.foreground_color = color or TEXT
        self.cursor_color = BLUE_SOFT
        self.font_size = font_size or dp(13)
        self.size_hint_y = None
        self.height = height or dp(40)
        self.padding = [0, dp(4)]
        self.write_tab = False


def show_popup(title, message):
    """Reliable popup: title + body as Labels inside content (always visible)."""
    content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
    title_l = Label(
        text=str(title),
        color=YELLOW,
        bold=True,
        font_size=dp(17),
        size_hint_y=None,
        height=dp(28),
        halign="center",
        valign="middle",
    )
    title_l.bind(size=lambda *a: setattr(title_l, "text_size", title_l.size))
    content.add_widget(title_l)

    body = CopyableText(
        text=str(message),
        color=TEXT,
        font_size=dp(15),
        height=dp(110),
    )
    content.add_widget(body)

    close = BrandButton(text="OK", bg_color=BLUE)
    content.add_widget(close)

    popup = Popup(
        title="",
        separator_height=0,
        content=content,
        size_hint=(0.92, None),
        height=dp(280),
        background="",
        auto_dismiss=True,
    )
    with popup.canvas.before:
        Color(*CARD_BG)
        popup._bg = RoundedRectangle(pos=popup.pos, size=popup.size, radius=[dp(14)])
    popup.bind(
        pos=lambda *a: setattr(popup._bg, "pos", popup.pos),
        size=lambda *a: setattr(popup._bg, "size", popup.size),
    )
    close.bind(on_release=popup.dismiss)
    popup.open()


def confirm_gas_then(callback, title="Confirm gas"):
    """Fetch gas price, show confirm popup with visible text + buttons."""
    def worker():
        try:
            info = txmod.get_gas_price_info()
            gwei = info["gwei"]
            msg = "Network gas ~ %.2f gwei\n(with 10%% buffer)\n\nContinue and send transaction?" % gwei

            def show(_dt=None):
                content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
                title_l = Label(
                    text=str(title),
                    color=YELLOW,
                    bold=True,
                    font_size=dp(17),
                    size_hint_y=None,
                    height=dp(28),
                    halign="center",
                )
                title_l.bind(size=lambda *a: setattr(title_l, "text_size", title_l.size))
                content.add_widget(title_l)

                body = Label(
                    text=msg,
                    color=TEXT,
                    font_size=dp(15),
                    bold=True,
                    halign="center",
                    valign="middle",
                    size_hint_y=None,
                    height=dp(100),
                )
                body.bind(size=lambda *a: setattr(body, "text_size", body.size))
                content.add_widget(body)

                row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
                cancel = BrandButton(text="CANCEL", bg_color=INPUT_BG)
                ok = BrandButton(text="CONTINUE", bg_color=GREEN)
                row.add_widget(cancel)
                row.add_widget(ok)
                content.add_widget(row)

                popup = Popup(
                    title="",
                    separator_height=0,
                    content=content,
                    size_hint=(0.92, None),
                    height=dp(260),
                    background="",
                    auto_dismiss=False,
                )
                with popup.canvas.before:
                    Color(*CARD_BG)
                    popup._bg = RoundedRectangle(pos=popup.pos, size=popup.size, radius=[dp(14)])
                popup.bind(
                    pos=lambda *a: setattr(popup._bg, "pos", popup.pos),
                    size=lambda *a: setattr(popup._bg, "size", popup.size),
                )
                cancel.bind(on_release=popup.dismiss)
                def _ok(*_):
                    popup.dismiss()
                    callback()
                ok.bind(on_release=_ok)
                popup.open()

            Clock.schedule_once(show, 0)
        except Exception as e:
            Clock.schedule_once(lambda dt: show_popup("Gas check failed", str(e)), 0)
    threading.Thread(target=worker, daemon=True).start()


class NavBar(BoxLayout):
    def __init__(self, current="", **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(46)
        self.spacing = dp(4)
        self.padding = [dp(2), 0]
        items = [
            ("check", "TRUTH", BLUE_SOFT),
            ("messages", "MSG", GREEN_BR),
            ("sign", "SIGN", GREEN_BR),
            ("gas", "GAS", ORANGE),
            ("presence", "PRES", YELLOW),
            ("batch", "BT", BLUE),
            ("ss", "S&S", get_color_from_hex("#a78bfa")),
            ("legacy", "LSF", get_color_from_hex("#c084fc")),
            ("wallet", "ID", TEXT_MUTED),
        ]
        for name, label, color in items:
            btn = Button(
                text=label, background_normal="",
                background_color=color if name == current else INPUT_BG,
                color=TEXT, bold=True, font_size=dp(13), size_hint_x=1,
            )
            btn.bind(on_release=lambda b, n=name: self._go(n))
            self.add_widget(btn)

    def _go(self, name):
        app = App.get_running_app()
        if name in ("sign", "batch", "presence") and not app.private_key and name != "presence":
            # presence can be viewed locked; actions require unlock
            pass
        if name in ("sign", "batch") and not app.private_key:
            app.sm.current = "unlock"
        elif name == "wallet":
            app.sm.current = "unlock" if not app.private_key else "wallet"
        else:
            app.sm.current = name


# ── Screens ──────────────────────────────────────────────────

