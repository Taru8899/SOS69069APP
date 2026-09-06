from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
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
import re
import threading
from datetime import datetime

from sos_core import sign_record, address_from_private_key, CONTRACT_ADDRESS
import wallet_storage as ws
import rpc
import tx as txmod

CHAIN_ID = 1
MAX_META = 64

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
    """Multi-line input for batch addresses / messages."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.multiline = True
        self.size_hint_y = None
        self.height = dp(110)
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


def _logo_path():
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ("icon.png", "icon-192.png", "presplash.png"):
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path
    return "icon.png"


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
        logo = Image(
            source=_logo_path(),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(logo)
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
        self.padding = [HeaderBar.LEFT, 0, dp(8), 0]
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
        payer = app.get_payer_key()
        if payer:
            try:
                self.addr_lbl.text = "Gas payer: " + address_from_private_key(payer)
            except Exception:
                self.addr_lbl.text = "Gas payer: (error)"
        else:
            self.addr_lbl.text = "Gas payer: (locked — unlock a wallet)"
        n = sum(1 for k in (app.keys or {}).values() if k)
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
            ("check", "CHECK", BLUE_SOFT),
            ("messages", "MSGS", GREEN_BR),
            ("presence", "PRES", YELLOW),
            ("sign", "SIGN", GREEN_BR),
            ("ss", "S&S", ORANGE),
            ("gas", "GAS", TEXT_MUTED),
            ("legacy", "LEGACY", get_color_from_hex("#a78bfa")),
            ("wallet", "KEY", TEXT_MUTED),
        ]
        for name, label, color in items:
            btn = Button(
                text=label, background_normal="",
                background_color=color if name == current else INPUT_BG,
                color=TEXT, bold=True, font_size=dp(12), size_hint_x=1,
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

class LoadingScreen(Screen):
    """Startup splash: logo + Loading ... / Activity and Signatures."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20))
        root.add_widget(Label())  # flex top

        block = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(14))
        block.bind(minimum_height=block.setter("height"))
        logo_row = BoxLayout(size_hint_y=None, height=dp(128))
        logo_row.add_widget(Label())
        logo = Image(
            source=_logo_path(),
            size_hint=(None, None),
            size=(dp(128), dp(128)),
            allow_stretch=True,
            keep_ratio=True,
        )
        logo_row.add_widget(logo)
        logo_row.add_widget(Label())
        block.add_widget(logo_row)

        for text, sz, col, h in (
            ("Loading ...", dp(18), TEXT, dp(30)),
            ("Activity and Signatures", dp(15), TEXT_SEC, dp(28)),
        ):
            lbl = Label(
                text=text, color=col, bold=True, font_size=sz,
                size_hint_y=None, height=h, halign="center",
            )
            lbl.bind(size=lambda *a, w=lbl: setattr(w, "text_size", w.size))
            block.add_widget(lbl)

        root.add_widget(block)
        root.add_widget(Label())  # flex bottom
        self.add_widget(root)

    def on_enter(self, *a):
        Clock.schedule_once(self._go_next, 5.0)

    def _go_next(self, *_):
        app = App.get_running_app()
        if ws.wallet_exists(app.user_data_dir):
            self.manager.current = "unlock"
        else:
            self.manager.current = "welcome"


class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        root.add_widget(Label(size_hint_y=0.15))  # top spacer

        # Centered logo block
        center = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        center.bind(minimum_height=center.setter("height"))
        logo = Image(
            source=_logo_path(),
            size_hint=(None, None),
            size=(dp(120), dp(120)),
            allow_stretch=True,
            keep_ratio=True,
            pos_hint={"center_x": 0.5},
        )
        # wrap logo to center horizontally
        logo_row = BoxLayout(size_hint_y=None, height=dp(120))
        logo_row.add_widget(Label())  # left flex
        logo_row.add_widget(logo)
        logo_row.add_widget(Label())  # right flex
        center.add_widget(logo_row)

        title = Label(
            text="SOS 69069",
            color=TEXT,
            bold=True,
            font_size=dp(24),
            size_hint_y=None,
            height=dp(32),
            halign="center",
        )
        title.bind(size=lambda *a: setattr(title, "text_size", title.size))
        center.add_widget(title)

        sub = Label(
            text="Activity and Signatures",
            color=TEXT_SEC,
            font_size=dp(15),
            size_hint_y=None,
            height=dp(26),
            halign="center",
        )
        sub.bind(size=lambda *a: setattr(sub, "text_size", sub.size))
        center.add_widget(sub)

        tag = Label(
            text="Whatever you do. SOS records.\nWhatever you do. Continue ...",
            color=TEXT_MUTED,
            font_size=dp(13),
            size_hint_y=None,
            height=dp(44),
            halign="center",
        )
        tag.bind(size=lambda *a: setattr(tag, "text_size", tag.size))
        center.add_widget(tag)

        root.add_widget(center)
        root.add_widget(Label(size_hint_y=0.08))

        card = Card()
        card.add_widget(SubLabel(text="No wallet found on this device.", color=TEXT_SEC))
        create_btn = BrandButton(text="CREATE NEW WALLET", bg_color=GREEN)
        create_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "create"))
        card.add_widget(create_btn)
        import_btn = BrandButton(text="IMPORT EXISTING KEY", bg_color=BLUE)
        import_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "import"))
        card.add_widget(import_btn)
        root.add_widget(card)
        root.add_widget(Label())
        self.add_widget(root)



class CreateWalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        root.add_widget(HeaderBar(title="Create New Wallet"))
        card = Card()
        self.pw = BrandInput(hint_text="Set a password", password=True)
        self.cf = BrandInput(hint_text="Confirm password", password=True)
        card.add_widget(self.pw)
        card.add_widget(self.cf)
        btn = BrandButton(text="GENERATE & SAVE", bg_color=GREEN)
        btn.bind(on_release=self.do_create)
        card.add_widget(btn)
        back = BrandButton(text="BACK", bg_color=INPUT_BG)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "welcome"))
        card.add_widget(back)
        root.add_widget(card)
        root.add_widget(Label())
        self.add_widget(root)

    def do_create(self, *_):
        if len(self.pw.text) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if self.pw.text != self.cf.text:
            show_popup("Error", "Passwords do not match.")
            return
        priv = "0x" + os.urandom(32).hex()
        addr = address_from_private_key(priv)
        app = App.get_running_app()
        slot = 1 if not ws.wallet_exists(app.user_data_dir, 1) else 2
        ws.save_wallet(app.user_data_dir, priv, addr, self.pw.text, slot=slot)
        show_popup("Wallet Created", f"Saved to slot {slot}.\n{addr}\n\nBack up this device securely.")
        if app.keys is None:
            app.keys = {1: None, 2: None}
        app.keys[slot] = priv
        app.payer_slot = slot
        app.go_to_wallet_screen(addr)


class ImportWalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
        root.add_widget(HeaderBar(title="Import Wallet"))
        card = Card()
        self.key = BrandInput(hint_text="Private key (0x...)")
        self.pw = BrandInput(hint_text="Set a password", password=True)
        self.cf = BrandInput(hint_text="Confirm password", password=True)
        card.add_widget(self.key)
        card.add_widget(self.pw)
        card.add_widget(self.cf)
        btn = BrandButton(text="IMPORT & SAVE", bg_color=GREEN)
        btn.bind(on_release=self.do_import)
        card.add_widget(btn)
        back = BrandButton(text="BACK", bg_color=INPUT_BG)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "welcome"))
        card.add_widget(back)
        root.add_widget(card)
        root.add_widget(Label())
        self.add_widget(root)

    def do_import(self, *_):
        if len(self.pw.text) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if self.pw.text != self.cf.text:
            show_popup("Error", "Passwords do not match.")
            return
        try:
            raw = self.key.text.strip().replace("0x", "")
            n = int(raw, 16)
            if not (0 < n < 2**256):
                raise ValueError()
            priv = "0x" + raw.zfill(64)
            addr = address_from_private_key(priv)
        except Exception:
            show_popup("Error", "Invalid private key format.")
            return
        app = App.get_running_app()
        slot = 1 if not ws.wallet_exists(app.user_data_dir, 1) else 2
        if ws.wallet_exists(app.user_data_dir, 1) and ws.wallet_exists(app.user_data_dir, 2):
            show_popup("Error", "Both wallet slots are full. Logout and remove one first.")
            return
        slot = 1 if not ws.wallet_exists(app.user_data_dir, 1) else 2
        ws.save_wallet(app.user_data_dir, priv, addr, self.pw.text, slot=slot)
        show_popup("Wallet Imported", f"Saved to slot {slot}.\n{addr}")
        if app.keys is None:
            app.keys = {1: None, 2: None}
        app.keys[slot] = priv
        app.payer_slot = slot
        app.go_to_wallet_screen(addr)


class UnlockScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(8))
        root.add_widget(HeaderBar(title="Unlock Wallet"))
        self.slots_lbl = SubLabel(text="", color=TEXT_MUTED)
        self.slots_lbl.halign = "left"
        root.add_widget(self.slots_lbl)

        card = Card()
        self.slot_btn = BrandButton(text="Slot 1", bg_color=BLUE)
        self.slot_btn.bind(on_release=self.toggle_slot)
        card.add_widget(self.slot_btn)
        self.addr_lbl = SubLabel(text="", color=YELLOW)
        self.addr_lbl.halign = "left"
        card.add_widget(self.addr_lbl)
        self.pw = BrandInput(hint_text="Password", password=True)
        card.add_widget(self.pw)
        btn = BrandButton(text="UNLOCK THIS SLOT", bg_color=GREEN)
        btn.bind(on_release=self.do_unlock)
        card.add_widget(btn)
        root.add_widget(card)

        self.status = SubLabel(text="", color=TEXT_SEC)
        self.status.halign = "left"
        root.add_widget(self.status)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        go = BrandButton(text="CONTINUE", bg_color=BLUE_SOFT)
        go.bind(on_release=lambda *_: setattr(self.manager, "current", "sign"))
        chk = BrandButton(text="CHECK", bg_color=INPUT_BG)
        chk.bind(on_release=lambda *_: setattr(self.manager, "current", "check"))
        row.add_widget(go)
        row.add_widget(chk)
        root.add_widget(row)

        add = BrandButton(text="ADD / IMPORT 2nd WALLET", bg_color=INPUT_BG)
        add.bind(on_release=lambda *_: setattr(self.manager, "current", "import"))
        root.add_widget(add)

        root.add_widget(Label())
        root.add_widget(NavBar(current="wallet"))
        self.add_widget(root)
        self.active_slot = 1

    def toggle_slot(self, *_):
        self.active_slot = 2 if self.active_slot == 1 else 1
        self._refresh_slot_ui()

    def _refresh_slot_ui(self):
        app = App.get_running_app()
        self.slot_btn.text = f"Slot {self.active_slot} (tap to switch)"
        try:
            addr = ws.peek_address(app.user_data_dir, self.active_slot)
            self.addr_lbl.text = addr if addr else "(empty slot — import a key)"
        except Exception:
            self.addr_lbl.text = "(empty slot — import a key)"
        unlocked = []
        for s in (1, 2):
            if app.keys and app.keys.get(s):
                unlocked.append(f"S{s}")
        self.slots_lbl.text = "Unlocked: " + (", ".join(unlocked) if unlocked else "none")
        if app.get_payer_key():
            try:
                self.status.text = "Gas payer: " + address_from_private_key(app.get_payer_key())
            except Exception:
                self.status.text = ""
        else:
            self.status.text = "Unlock at least one slot to send txs"

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        slots = ws.list_slots(app.user_data_dir)
        if not slots:
            self.manager.current = "welcome"
            return
        self.active_slot = slots[0]["slot"]
        self._refresh_slot_ui()

    def do_unlock(self, *_):
        app = App.get_running_app()
        if not ws.wallet_exists(app.user_data_dir, self.active_slot):
            show_popup("Empty", "This slot is empty. Import a wallet into it.")
            return
        try:
            priv = ws.load_wallet(app.user_data_dir, self.pw.text, self.active_slot)
        except ws.WrongPasswordOrTampered:
            show_popup("Error", "Wrong password.")
            return
        except Exception as e:
            show_popup("Error", str(e))
            return
        if app.keys is None:
            app.keys = {1: None, 2: None}
        app.keys[self.active_slot] = priv
        app.payer_slot = self.active_slot
        self.pw.text = ""
        self._refresh_slot_ui()
        show_popup("Unlocked", f"Slot {self.active_slot} unlocked.\nGas payer set to this wallet.")



class CheckScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        root.add_widget(HeaderBar(title="SOS 69069"))
        motto = Label(
            text="SOS 69069 originates from verified Activity and Signatures.\nWhatever you do. SOS records.\nWhatever you do. Continue ...",
            color=TEXT,
            bold=True,
            font_size=dp(14),
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(72),
        )
        motto.bind(size=lambda *a: setattr(motto, "text_size", motto.size))
        motto.padding_x = dp(HeaderBar.LEFT)
        root.add_widget(motto)
        root.add_widget(SubLabel(text="Check Presence", color=TEXT_MUTED))
        card = Card()
        self.addr_input = BrandInput(hint_text="0x address")
        card.add_widget(self.addr_input)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b1 = BrandButton(text="CHECK", bg_color=BLUE)
        b1.bind(on_release=self.do_check)
        b2 = BrandButton(text="MINE", bg_color=INPUT_BG)
        b2.bind(on_release=self.use_mine)
        row.add_widget(b1)
        row.add_widget(b2)
        card.add_widget(row)
        root.add_widget(card)

        metrics = Card()
        self.eff = Label(text="Effective: —", color=BLUE_SOFT, bold=True,
                         font_size=dp(26), size_hint_y=None, height=dp(36), halign="center")
        self.eff.bind(size=lambda *a: setattr(self.eff, "text_size", self.eff.size))
        metrics.add_widget(self.eff)
        row2 = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(10))
        self.trust = Label(text="Trust: —", color=GREEN_BR, bold=True, font_size=dp(15), halign="center")
        self.trust.bind(size=lambda *a: setattr(self.trust, "text_size", self.trust.size))
        self.push = Label(text="Push: —", color=ORANGE, bold=True, font_size=dp(15),halign="center")
        self.push.bind(size=lambda *a: setattr(self.push, "text_size", self.push.size))
        row2.add_widget(self.trust)
        row2.add_widget(self.push)
        metrics.add_widget(row2)
        self.status = SubLabel(text="", color=TEXT_MUTED)
        metrics.add_widget(self.status)
        root.add_widget(metrics)

        trends_card = Card()
        trends_card.add_widget(SubLabel(text="Trends — most used words", color=TEXT_MUTED))
        row_a = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.win_24h = Button(text="24H", background_normal="", background_color=BLUE,
                               color=TEXT, bold=True, font_size=dp(12))
        self.win_week = Button(text="WEEK", background_normal="", background_color=INPUT_BG,
                                color=TEXT, bold=True, font_size=dp(12))
        self.win_month = Button(text="MONTH", background_normal="", background_color=INPUT_BG,
                                 color=TEXT, bold=True, font_size=dp(12))
        self.win_year = Button(text="YEAR", background_normal="", background_color=INPUT_BG,
                                color=TEXT, bold=True, font_size=dp(12))
        self.win_all = Button(text="ALL TIME", background_normal="", background_color=INPUT_BG,
                               color=TEXT, bold=True, font_size=dp(12))
        for btn, w in ((self.win_24h, "24h"), (self.win_week, "week"),
                       (self.win_month, "month"), (self.win_year, "year"),
                       (self.win_all, "all")):
            btn.bind(on_release=lambda b, ww=w: self.select_window(ww))
            row_a.add_widget(btn)
        trends_card.add_widget(row_a)

        row_b = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.year_input = BrandInput(hint_text="Year, e.g. 2025")
        year_btn = Button(text="YEAR N", background_normal="", background_color=INPUT_BG,
                           color=TEXT, bold=True, font_size=dp(12), size_hint_x=0.4)
        year_btn.bind(on_release=self.select_year_n)
        row_b.add_widget(self.year_input)
        row_b.add_widget(year_btn)
        trends_card.add_widget(row_b)

        load_trends_btn = BrandButton(text="LOAD TRENDS", bg_color=GREEN)
        load_trends_btn.bind(on_release=self.load_trends)
        trends_card.add_widget(load_trends_btn)

        self.trends_status = SubLabel(text="Select a time window and tap LOAD TRENDS", color=TEXT_MUTED)
        trends_card.add_widget(self.trends_status)
        root.add_widget(trends_card)

        self.trends_scroll = ScrollView(size_hint=(1, 1))
        self.trends_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
        self.trends_box.bind(minimum_height=self.trends_box.setter("height"))
        self.trends_scroll.add_widget(self.trends_box)
        root.add_widget(self.trends_scroll)

        self._trend_window = "24h"
        self._trend_year = None
        self._all_window_buttons = (self.win_24h, self.win_week, self.win_month, self.win_year, self.win_all)
        root.add_widget(NavBar(current="check"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
        elif not self.addr_input.text:
            try:
                self.addr_input.text = ws.peek_address(app.user_data_dir)
            except Exception:
                self.addr_input.text = "0x1C10e6574ee696f54b21A611a21313E4714628ad"

    def use_mine(self, *_):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
        else:
            try:
                self.addr_input.text = ws.peek_address(app.user_data_dir)
            except Exception:
                show_popup("Info", "Unlock or create a wallet first.")
                return
        self.do_check()

    def do_check(self, *_):
        addr = self.addr_input.text.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter a valid 0x address.")
            return
        self.status.text = "Loading…"
        self.eff.text = "Effective: …"
        self.trust.text = "Trust: …"
        self.push.text = "Push: …"

        def worker():
            try:
                s = rpc.stats_of(addr)
                Clock.schedule_once(lambda dt: self._show(s, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show(None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _show(self, s, err):
        if err:
            self.status.text = err
            self.eff.text = "Effective: —"
            self.trust.text = "Trust: —"
            self.push.text = "Push: —"
            return
        self.eff.text = f"Effective: {s['effective']}"
        self.trust.text = f"Trust: {s['trust']}"
        self.push.text = f"Push: {s['push']}"
        self.status.text = "Live on Ethereum Mainnet"
        # remember for Messages screen
        App.get_running_app().last_check_address = self.addr_input.text.strip()

    def select_window(self, window):
        self._trend_window = window
        self._trend_year = None
        self.year_input.text = ""
        for btn in self._all_window_buttons:
            btn.background_color = INPUT_BG
        mapping = {
            "24h": self.win_24h, "week": self.win_week, "month": self.win_month,
            "year": self.win_year, "all": self.win_all,
        }
        mapping[window].background_color = BLUE

    def select_year_n(self, *_):
        raw = self.year_input.text.strip()
        try:
            year = int(raw)
            if year < 1970 or year > 9999:
                raise ValueError()
        except ValueError:
            show_popup("Error", "Enter a valid 4-digit year, e.g. 2025.")
            return
        self._trend_window = "year_n"
        self._trend_year = year
        for btn in self._all_window_buttons:
            btn.background_color = INPUT_BG

    def load_trends(self, *_):
        self.trends_status.text = "Loading messages from the whole contract history…"
        self.trends_box.clear_widgets()
        window = self._trend_window
        year = self._trend_year

        def worker():
            try:
                events = rpc.fetch_all_metadata_events()
                trends = rpc.compute_word_trends(events, window, year=year)
                Clock.schedule_once(lambda dt: self._show_trends(trends, len(events), None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show_trends([], 0, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _show_trends(self, trends, total_events, err):
        self.trends_box.clear_widgets()
        if err:
            self.trends_status.text = err
            return
        if not trends:
            self.trends_status.text = f"No words found in this window ({total_events} total messages scanned)."
            return
        self.trends_status.text = f"Top words ({total_events} total messages scanned)"
        for rank, (word, count) in enumerate(trends, start=1):
            row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
            row.add_widget(Label(text=f"{rank}. {word}", color=TEXT, bold=True,
                                  font_size=dp(14), halign="left", size_hint_x=0.7))
            row.add_widget(Label(text=str(count), color=GREEN_BR, bold=True,
                                  font_size=dp(14), halign="right", size_hint_x=0.3))
            self.trends_box.add_widget(row)


class MessagesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        root.add_widget(HeaderBar(title="Messages"))
        self.addr_input = BrandInput(hint_text="0x address to load messages")
        root.add_widget(self.addr_input)

        tabs = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.tab_trust = BrandButton(text="TRUST", bg_color=BLUE)
        self.tab_push = BrandButton(text="PUSH", bg_color=INPUT_BG)
        self.tab_trust.bind(on_release=lambda *_: self.switch_tab("trust"))
        self.tab_push.bind(on_release=lambda *_: self.switch_tab("push"))
        tabs.add_widget(self.tab_trust)
        tabs.add_widget(self.tab_push)
        root.add_widget(tabs)

        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        load = BrandButton(text="LOAD", bg_color=GREEN)
        load.bind(on_release=self.load_messages)
        mine = BrandButton(text="MINE", bg_color=INPUT_BG)
        mine.bind(on_release=self.use_mine)
        row.add_widget(load)
        row.add_widget(mine)
        root.add_widget(row)

        self.status = SubLabel(text="Enter address and tap LOAD", color=TEXT_MUTED)
        root.add_widget(self.status)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=[0, dp(4)])
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)

        root.add_widget(NavBar(current="messages"))
        self.add_widget(root)
        self.direction = "trust"

    def switch_tab(self, d):
        self.direction = d
        if d == "trust":
            self.tab_trust.background_color = BLUE
            self.tab_push.background_color = INPUT_BG
        else:
            self.tab_push.background_color = ORANGE
            self.tab_trust.background_color = INPUT_BG

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if getattr(app, "last_check_address", None):
            self.addr_input.text = app.last_check_address
        elif app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)

    def use_mine(self, *_):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
        else:
            try:
                self.addr_input.text = ws.peek_address(app.user_data_dir)
            except Exception:
                show_popup("Info", "Unlock or create a wallet first.")
                return
        self.load_messages()

    def load_messages(self, *_):
        addr = self.addr_input.text.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter a valid 0x address.")
            return
        self.status.text = "Loading messages…"
        self.list_box.clear_widgets()

        def worker():
            try:
                events = rpc.fetch_messages(addr, direction=self.direction)
                Clock.schedule_once(lambda dt: self._render(events, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._render([], str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _render(self, events, err):
        self.list_box.clear_widgets()
        if err:
            self.status.text = err
            return
        if not events:
            self.status.text = "No messages with metadata found in recent blocks."
            return
        self.status.text = f"Showing {len(events)} message(s)"
        for ev in events:
            self.list_box.add_widget(self._msg_card(ev))

    def _msg_card(self, ev):
        card = Card()
        meta = (ev.get("metadata") or "").strip()
        party = ev["signer"] if self.direction == "trust" else ev["intendedTo"]
        dir_label = "TRUST Received 1 SOS" if self.direction == "trust" else "PUSH Sent 1 SOS"
        dir_color = GREEN_BR if self.direction == "trust" else ORANGE

        if meta:
            m = Label(text=meta, color=TEXT, bold=True, font_size=dp(15),
                      size_hint_y=None, halign="left", valign="top")
            m.bind(size=lambda *a, w=m: setattr(w, "text_size", (w.width, None)))
            m.bind(texture_size=lambda *a, w=m: setattr(w, "height", w.texture_size[1]))
            card.add_widget(m)

        card.add_widget(Label(
            text=short_addr(party), color=YELLOW, font_size=dp(12),
            size_hint_y=None, height=dp(18), halign="left",
        ))
        when = fmt_time(ev.get("timestamp", 0))
        card.add_widget(Label(
            text=f"tx{ev['txHash'][:18]}…  ·  block {ev['blockNumber']}  ·  {when}",
            color=TEXT_MUTED, font_size=dp(11), size_hint_y=None, height=dp(16),
        ))

        row = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(8))
        row.add_widget(Label(text=dir_label, color=dir_color, bold=True,
                             font_size=dp(12), size_hint_x=0.6, halign="left"))
        code = extract_conv_code(meta) or (ev["txHash"][2:10].lower() if ev.get("txHash") else "")
        if code:
            reply = Button(text="REPLY", background_normal="", background_color=BLUE_SOFT,
                           color=TEXT, bold=True, font_size=dp(12), size_hint_x=0.4)
            reply.bind(on_release=lambda b, c=code, p=party: self._reply(c, p))
            row.add_widget(reply)
        card.add_widget(row)
        return card

    def _reply(self, code, party):
        app = App.get_running_app()
        app.reply_code = code
        app.reply_to = party
        if not app.private_key:
            show_popup("Info", "Unlock wallet first to reply.")
            self.manager.current = "unlock"
            return
        self.manager.current = "sign"


class SignScreen(Screen):
    """Single sign with optional reply code."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        root.add_widget(HeaderBar(title="Sign Presence"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        self.my_lbl = SubLabel(text="", color=YELLOW)
        self.my_lbl.halign = "left"
        root.add_widget(self.my_lbl)

        card = Card()
        self.recipient = BrandInput(hint_text="Recipient address (0x...)")
        card.add_widget(self.recipient)
        self.payload = BrandInput(hint_text="Payload hash (optional 0x...)")
        card.add_widget(self.payload)
        self.code = BrandInput(hint_text="Conversation code (8 hex, optional)")
        card.add_widget(self.code)
        self.metadata = BrandInput(hint_text="Metadata / message (max 64 chars)")
        card.add_widget(self.metadata)
        self.counter = SubLabel(text="0/64 characters", color=TEXT_MUTED)
        card.add_widget(self.counter)
        self.metadata.bind(text=self._update_count)
        self.code.bind(text=self._update_count)

        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        sign_btn = BrandButton(text="SIGN ONLY", bg_color=INPUT_BG)
        sign_btn.bind(on_release=lambda *_: self.do_sign(send=False))
        send_btn = BrandButton(text="SIGN & SEND", bg_color=GREEN)
        send_btn.bind(on_release=lambda *_: self.do_sign(send=True))
        btn_row.add_widget(sign_btn)
        btn_row.add_widget(send_btn)
        card.add_widget(btn_row)
        root.add_widget(card)

        self.result = CopyableText(text="", color=GREEN_BR, font_size=dp(12), height=dp(100))
        root.add_widget(self.result)
        root.add_widget(NavBar(current="sign"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if hasattr(self, "payer_bar"):
            self.payer_bar.refresh()
        signer = app.get_signer_key()
        payer = app.get_payer_key()
        if signer:
            self.my_lbl.text = "Signer: " + address_from_private_key(signer)
        else:
            self.my_lbl.text = "Signer: (locked)"
        if getattr(app, "reply_code", None):
            self.code.text = app.reply_code
            app.reply_code = None
        if getattr(app, "reply_to", None):
            self.recipient.text = app.reply_to
            app.reply_to = None
        self._update_count()

    def _update_count(self, *a):
        code = self.code.text.strip()
        has_code = bool(re.fullmatch(r"[a-fA-F0-9]{8}", code))
        limit = 56 if has_code else MAX_META
        n = utf8_len(self.metadata.text)
        self.counter.text = f"{n}/{limit} characters"
        self.counter.color = DANGER if n > limit else TEXT_MUTED

    def _prepare(self):
        app = App.get_running_app()
        if not app.get_signer_key():
            show_popup("Error", "Unlock a wallet first.")
            return None
        to = self.recipient.text.strip()
        payload = self.payload.text.strip() or ("0x" + os.urandom(32).hex())
        code = self.code.text.strip().lower()
        text = self.metadata.text.strip()
        has_code = bool(re.fullmatch(r"[a-fA-F0-9]{8}", code))
        if has_code:
            meta = f"{text} {code}".strip() if text else code
            if utf8_len(meta) > MAX_META:
                show_popup("Error", "Message + code exceeds 64 characters.")
                return None
        else:
            meta = text
            if utf8_len(meta) > MAX_META:
                show_popup("Error", "Metadata exceeds 64 characters.")
                return None
        if not (to.startswith("0x") and len(to) == 42):
            show_popup("Error", "Invalid recipient address.")
            return None
        return app, to, payload, meta

    def do_sign(self, send=False):
        prep = self._prepare()
        if not prep:
            return
        app, to, payload, meta = prep

        def start():
            self.result.text = "Signing…" if not send else "Signing & sending…"
            signer_key = app.get_signer_key()
            payer_key = app.get_payer_key() or signer_key
            def worker():
                try:
                    result = sign_record(signer_key, CHAIN_ID, to, payload, meta)
                    if not send:
                        Clock.schedule_once(lambda dt: self._done_sign(result, meta, None), 0)
                        return
                    if not payer_key:
                        raise RuntimeError("No gas-payer wallet unlocked")
                    txr = txmod.send_record_signature(
                        payer_key, to, payload, result["signature"], meta,
                        signer=result.get("signer"),
                    )
                    Clock.schedule_once(lambda dt: self._done_send(result, meta, txr, None), 0)
                except Exception as e:
                    Clock.schedule_once(lambda dt: self._done_sign(None, meta, str(e)), 0)
            threading.Thread(target=worker, daemon=True).start()

        if send:
            confirm_gas_then(start, title="Confirm Sign & Send")
        else:
            start()

    def _done_sign(self, result, meta, err):
        if err:
            self.result.text = f"Error: {err}"
            show_popup("Error", err)
            return
        self.result.text = f"Signature:\n{result['signature']}\n\nMetadata: {meta}"

    def _done_send(self, result, meta, txr, err):
        if err:
            self.result.text = f"Error: {err}"
            show_popup("Error", err)
            return
        txh = txr["txHash"]
        self.result.text = (
            f"SENT on-chain\n"
            f"Tx: {txh}\n"
            f"Metadata: {meta}\n"
            f"Gas limit: {txr['gasLimit']}"
        )
        show_popup("Sent", f"Transaction submitted.\n{txh[:22]}…")


class BatchScreen(Screen):
    """Paste many addresses + messages, sign all."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        root.add_widget(HeaderBar(title="Batch Sign"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        root.add_widget(SubLabel(text="One address and one message per line", color=TEXT_MUTED))

        card = Card()
        card.add_widget(SubLabel(text="Addresses", color=TEXT_SEC))
        self.addrs = MultiInput(hint_text="0xabc...\n0xdef...")
        card.add_widget(self.addrs)
        card.add_widget(SubLabel(text="Messages (max 64 chars each)", color=TEXT_SEC))
        self.msgs = MultiInput(hint_text="hello\nworld")
        card.add_widget(self.msgs)
        self.info = SubLabel(text="0 pairs", color=TEXT_MUTED)
        card.add_widget(self.info)
        self.addrs.bind(text=self._count)
        self.msgs.bind(text=self._count)

        load = BrandButton(text="LOAD & PREVIEW", bg_color=BLUE)
        load.bind(on_release=self.load_pairs)
        card.add_widget(load)
        root.add_widget(card)

        self.preview = Label(text="", color=TEXT_SEC, font_size=dp(12),
                             size_hint_y=None, height=dp(80),
                             halign="left", valign="top")
        self.preview.bind(size=lambda *a: setattr(self.preview, "text_size", self.preview.size))
        root.add_widget(self.preview)

        btn_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.sign_btn = BrandButton(text="SIGN ALL", bg_color=INPUT_BG)
        self.sign_btn.bind(on_release=lambda *_: self.run_batch(send=False))
        self.sign_btn.disabled = True
        self.send_btn = BrandButton(text="SIGN & SEND ALL", bg_color=GREEN)
        self.send_btn.bind(on_release=lambda *_: self.run_batch(send=True))
        self.send_btn.disabled = True
        btn_row.add_widget(self.sign_btn)
        btn_row.add_widget(self.send_btn)
        root.add_widget(btn_row)

        self.result = Label(text="", color=GREEN_BR, font_size=dp(11),
                            size_hint_y=None, height=dp(80),
                            halign="left", valign="top")
        self.result.bind(size=lambda *a: setattr(self.result, "text_size", self.result.size))
        root.add_widget(self.result)
        root.add_widget(NavBar(current="batch"))
        self.add_widget(root)
        self.pairs = []

    def _count(self, *a):
        a = [x.strip() for x in self.addrs.text.splitlines() if x.strip()]
        m = [x.strip() for x in self.msgs.text.splitlines() if x.strip()]
        self.info.text = f"{len(a)} addresses · {len(m)} messages"

    def load_pairs(self, *_):
        addrs = [x.strip() for x in self.addrs.text.splitlines() if x.strip()]
        msgs = [x.strip() for x in self.msgs.text.splitlines() if x.strip()]
        if not addrs or not msgs:
            show_popup("Error", "Paste at least one address and one message.")
            return
        if len(addrs) != len(msgs):
            show_popup("Error", f"Line count mismatch: {len(addrs)} addresses vs {len(msgs)} messages.")
            return
        if len(addrs) > 30:
            show_popup("Error", "Max 30 pairs per batch on mobile.")
            return
        bad = []
        for i, (a, m) in enumerate(zip(addrs, msgs)):
            if not (a.startswith("0x") and len(a) == 42):
                bad.append(f"Line {i+1}: invalid address")
            if utf8_len(m) > MAX_META:
                bad.append(f"Line {i+1}: message > 64 chars")
        if bad:
            show_popup("Error", bad[0])
            return
        self.pairs = list(zip(addrs, msgs))
        preview = "\n".join(f"{i+1}. {short_addr(a)} → {m[:40]}" for i, (a, m) in enumerate(self.pairs[:8]))
        if len(self.pairs) > 8:
            preview += f"\n… +{len(self.pairs)-8} more"
        self.preview.text = preview
        self.sign_btn.disabled = False
        self.send_btn.disabled = False
        self.info.text = f"{len(self.pairs)} pairs ready"
        self.result.text = ""

    def run_batch(self, send=False):
        app = App.get_running_app()
        if not app.get_signer_key():
            show_popup("Error", "Unlock a wallet first.")
            return
        if not self.pairs:
            show_popup("Error", "Load pairs first.")
            return
        if send and len(self.pairs) > 10:
            show_popup("Warning", "Sending more than 10 txs from mobile may take a while and cost gas. Continue only if you have enough ETH.")

        def start():
            self.sign_btn.disabled = True
            self.send_btn.disabled = True
            self.result.text = "Sending…" if send else "Signing…"
            signer_key = app.get_signer_key()
            payer_key = app.get_payer_key() or signer_key

            def worker():
                out = []
                try:
                    nonce = None
                    gas_price = None
                    if send:
                        from pure_crypto import pubkey_to_address, privkey_to_pubkey
                        pk = int(payer_key.replace("0x", ""), 16)
                        from_addr = pubkey_to_address(privkey_to_pubkey(pk))
                        nonce = txmod.get_nonce(from_addr)
                        gas_price = txmod.get_gas_price()
                    for i, (to, meta) in enumerate(self.pairs):
                        payload = "0x" + os.urandom(32).hex()
                        r = sign_record(signer_key, CHAIN_ID, to, payload, meta)
                        entry = {"to": to, "metadata": meta, "signature": r["signature"], "payload": payload}
                        if send:
                            txr = txmod.send_record_signature(
                                payer_key, to, payload, r["signature"], meta,
                                signer=r.get("signer"),
                                nonce=nonce, gas_price=gas_price,
                            )
                            entry["txHash"] = txr["txHash"]
                            nonce = txr["nonce"] + 1
                        out.append(entry)
                    Clock.schedule_once(lambda dt: self._done(out, send, None), 0)
                except Exception as e:
                    Clock.schedule_once(lambda dt: self._done(out, send, str(e)), 0)
            threading.Thread(target=worker, daemon=True).start()

        if send:
            confirm_gas_then(start, title="Confirm batch send")
        else:
            start()

    def _done(self, results, send, err):
        self.sign_btn.disabled = False
        self.send_btn.disabled = False
        if err:
            self.result.text = f"Error after {len(results)} ok: {err}"
            show_popup("Error", err)
            return
        if send:
            lines = [f"{i+1}. {short_addr(r['to'])}  {r.get('txHash','')[:18]}…" for i, r in enumerate(results)]
            self.result.text = f"Sent {len(results)} txs:\n" + "\n".join(lines[:6])
            show_popup("Done", f"Broadcast {len(results)} transactions.")
        else:
            lines = [f"{i+1}. {short_addr(r['to'])}  sig={r['signature'][:18]}…" for i, r in enumerate(results)]
            self.result.text = f"Signed {len(results)} messages:\n" + "\n".join(lines[:6])
            show_popup("Done", f"Signed {len(results)} messages.")
        if len(results) > 6:
            self.result.text += f"\n… +{len(results)-6} more"
        App.get_running_app().last_batch_results = results



class PresenceScreen(Screen):
    """Create and manage presence offers (O/A/D/X protocol)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        root.add_widget(HeaderBar(title="Presence"))

        # Create offer card
        create = Card()
        create.add_widget(SubLabel(text="Create offer", color=TEXT_SEC))
        self.offer_type = BrandInput(hint_text="Type: T (trust) or P (push)")
        self.offer_type.text = "T"
        create.add_widget(self.offer_type)
        self.offer_qty = BrandInput(hint_text="Quantity (default 1)")
        self.offer_qty.text = "1"
        create.add_widget(self.offer_qty)
        self.offer_ret = BrandInput(hint_text="Return / exchange (optional)")
        create.add_widget(self.offer_ret)
        self.meta_preview = SubLabel(text="", color=TEXT_MUTED)
        create.add_widget(self.meta_preview)
        self.offer_type.bind(text=self._preview)
        self.offer_qty.bind(text=self._preview)
        self.offer_ret.bind(text=self._preview)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        cbtn = BrandButton(text="CREATE & SEND", bg_color=GREEN)
        cbtn.bind(on_release=self.create_offer)
        row.add_widget(cbtn)
        create.add_widget(row)
        root.add_widget(create)

        # Filters + load
        filt = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))
        self.filter = "ALL"
        for name in ("ALL", "OPEN", "T", "P", "DONE"):
            b = Button(text=name, background_normal="", font_size=dp(11), bold=True,
                       background_color=BLUE if name == "ALL" else INPUT_BG, color=TEXT)
            b.bind(on_release=lambda btn, n=name: self.set_filter(n))
            filt.add_widget(b)
        self.filter_btns = filt
        root.add_widget(filt)

        load_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        load_btn = BrandButton(text="LOAD OFFERS", bg_color=BLUE)
        load_btn.bind(on_release=self.load_offers)
        load_row.add_widget(load_btn)
        root.add_widget(load_row)

        self.status = SubLabel(text="Tap LOAD OFFERS", color=TEXT_MUTED)
        root.add_widget(self.status)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.scroll.add_widget(self.list_box)
        root.add_widget(self.scroll)

        root.add_widget(NavBar(current="presence"))
        self.add_widget(root)
        self.offers = []
        self._preview()

    def _preview(self, *a):
        try:
            import presence as pres
            typ = self.offer_type.text.strip().upper() or "T"
            qty = int(self.offer_qty.text.strip() or "1")
            ret = self.offer_ret.text.strip()
            meta = pres.build_offer_metadata(typ, qty, ret)
            self.meta_preview.text = meta[:60] + ("…" if len(meta) > 60 else "")
        except Exception:
            self.meta_preview.text = ""

    def set_filter(self, name):
        self.filter = name
        for btn in self.filter_btns.children:
            btn.background_color = BLUE if btn.text == name else INPUT_BG
        self._render()

    def create_offer(self, *_):
        app = App.get_running_app()
        if not app.private_key:
            show_popup("Error", "Unlock wallet first.")
            self.manager.current = "unlock"
            return
        import presence as pres
        typ = self.offer_type.text.strip().upper() or "T"
        if typ not in ("T", "P"):
            show_popup("Error", "Type must be T or P.")
            return
        try:
            qty = int(self.offer_qty.text.strip() or "1")
        except ValueError:
            show_popup("Error", "Quantity must be a number.")
            return
        ret = self.offer_ret.text.strip()
        meta = pres.build_offer_metadata(typ, qty, ret)
        self.status.text = "Creating offer…"

        def worker():
            try:
                me = address_from_private_key(app.private_key)
                payload = "0x" + os.urandom(32).hex()
                # intendedTo = self (poster records to self, same as website)
                result = sign_record(app.private_key, CHAIN_ID, me, payload, meta)
                txr = txmod.send_record_signature(
                    app.private_key, me, payload, result["signature"], meta
                )
                Clock.schedule_once(lambda dt: self._created(txr, meta, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._created(None, meta, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _created(self, txr, meta, err):
        if err:
            self.status.text = err
            show_popup("Error", err)
            return
        self.status.text = f"Offer sent: {txr['txHash'][:18]}…"
        show_popup("Created", f"Offer on-chain.\n{txr['txHash'][:22]}…")
        self.load_offers()

    def load_offers(self, *_):
        self.status.text = "Loading offers…"
        self.list_box.clear_widgets()

        def worker():
            try:
                events = rpc.fetch_presence_events()
                offers = rpc.build_presence_offers(events)
                Clock.schedule_once(lambda dt: self._loaded(offers, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._loaded([], str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _loaded(self, offers, err):
        if err:
            self.status.text = err
            return
        self.offers = offers
        self.status.text = f"{len(offers)} offers found"
        self._render()

    def _render(self):
        self.list_box.clear_widgets()
        app = App.get_running_app()
        me = ""
        if app.private_key:
            try:
                me = address_from_private_key(app.private_key).lower()
            except Exception:
                pass
        f = self.filter
        shown = 0
        for o in self.offers:
            if f == "OPEN" and o.get("status") != "OPEN":
                continue
            if f == "DONE" and o.get("status") != "DONE":
                continue
            if f == "T" and o.get("type") != "T":
                continue
            if f == "P" and o.get("type") != "P":
                continue
            self.list_box.add_widget(self._offer_card(o, me))
            shown += 1
            if shown >= 20:
                break
        if shown == 0:
            self.status.text = "No offers match filter."

    def _offer_card(self, o, me):
        card = Card()
        title = ("PUSH" if o.get("type") == "P" else "TRUST") + f"  #{o.get('id','')[:8]}"
        st = o.get("status", "?")
        card.add_widget(Label(
            text=f"{title}  [{st}]", color=GREEN_BR if st == "OPEN" else TEXT,
            bold=True, font_size=dp(13), size_hint_y=None, height=dp(22),
        ))
        card.add_widget(Label(
            text=f"Poster {short_addr(o.get('signer',''))}  qty={o.get('qty','1')}  ret={o.get('ret') or '—'}",
            color=TEXT_MUTED, font_size=dp(11), size_hint_y=None, height=dp(18),
        ))
        if o.get("accepter"):
            card.add_widget(Label(
                text=f"Accepter {short_addr(o['accepter'])}",
                color=YELLOW, font_size=dp(11), size_hint_y=None, height=dp(16),
            ))

        is_mine = me and o.get("signer", "").lower() == me
        is_acc = me and (o.get("accepter") or "").lower() == me
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(4))

        if st == "OPEN" and me and not is_mine:
            b = BrandButton(text="ACCEPT", bg_color=GREEN)
            b.bind(on_release=lambda btn, off=o: self.do_action("accept", off))
            row.add_widget(b)
        if st in ("OPEN", "ACCEPTED") and me and (is_mine or is_acc):
            b = BrandButton(text="CANCEL", bg_color=DANGER)
            b.bind(on_release=lambda btn, off=o: self.do_action("cancel", off))
            row.add_widget(b)
        if st == "ACCEPTED" and me and (is_mine or is_acc):
            b = BrandButton(text="DONE", bg_color=BLUE)
            b.bind(on_release=lambda btn, off=o: self.do_action("done", off))
            row.add_widget(b)
        if len(row.children):
            card.add_widget(row)
        return card

    def do_action(self, action, offer):
        app = App.get_running_app()
        if not app.private_key:
            show_popup("Error", "Unlock wallet first.")
            return
        import presence as pres
        typ = offer.get("type", "T")
        oid = offer.get("id", "")
        if action == "accept":
            meta = pres.build_accept_metadata(typ, oid)
            to = offer.get("signer")
        elif action == "done":
            meta = pres.build_done_metadata(typ, oid)
            me = address_from_private_key(app.private_key).lower()
            to = offer.get("accepter") if offer.get("signer", "").lower() == me else offer.get("signer")
            to = to or offer.get("signer")
        else:
            meta = pres.build_cancel_metadata(typ, oid)
            me = address_from_private_key(app.private_key).lower()
            to = offer.get("accepter") if offer.get("signer", "").lower() == me else offer.get("signer")
            to = to or offer.get("signer")

        self.status.text = f"{action}…"

        def worker():
            try:
                payload = "0x" + os.urandom(32).hex()
                result = sign_record(app.private_key, CHAIN_ID, to, payload, meta)
                txr = txmod.send_record_signature(
                    app.private_key, to, payload, result["signature"], meta
                )
                Clock.schedule_once(lambda dt: self._action_done(action, txr, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._action_done(action, None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _action_done(self, action, txr, err):
        if err:
            self.status.text = err
            show_popup("Error", err)
            return
        self.status.text = f"{action} tx {txr['txHash'][:18]}…"
        show_popup("OK", f"{action.upper()} submitted.\n{txr['txHash'][:22]}…")
        self.load_offers()





class LegacyScreen(Screen):
    """Legacy claim: CHECK old address, START / FINISH claim."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(HeaderBar(title="Legacy"))
        root.add_widget(SubLabel(text="Claim by signing +1 to an old address", color=TEXT_MUTED))

        card = Card()
        self.old_input = BrandInput(hint_text="Old address (0x...)")
        self.old_input.text = "0x1C10e6574ee696f54b21A611a21313E4714628ad"
        card.add_widget(self.old_input)
        check_btn = BrandButton(text="CHECK", bg_color=BLUE)
        check_btn.bind(on_release=self.do_check)
        card.add_widget(check_btn)
        root.add_widget(card)

        vals = Card()
        self.lbl_new = SubLabel(text="Connected: —", color=YELLOW)
        self.lbl_new_eff = SubLabel(text="Connected effective: —", color=TEXT)
        self.lbl_old = SubLabel(text="Old: —", color=TEXT_MUTED)
        self.lbl_old_eff = SubLabel(text="Old effective now: —", color=TEXT)
        self.lbl_old_after = SubLabel(text="Old effective after +1: —", color=GREEN_BR)
        for w in (self.lbl_new, self.lbl_new_eff, self.lbl_old, self.lbl_old_eff, self.lbl_old_after):
            vals.add_widget(w)
        root.add_widget(vals)

        actions = Card()
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.start_btn = BrandButton(text="START", bg_color=GREEN)
        self.start_btn.bind(on_release=lambda *_: self.do_claim("S"))
        self.finish_btn = BrandButton(text="FINISH", bg_color=get_color_from_hex("#a78bfa"))
        self.finish_btn.bind(on_release=lambda *_: self.do_claim("F"))
        row.add_widget(self.start_btn)
        row.add_widget(self.finish_btn)
        actions.add_widget(row)
        self.status = SubLabel(text="", color=TEXT_MUTED)
        actions.add_widget(self.status)
        root.add_widget(actions)

        root.add_widget(Label())
        root.add_widget(NavBar(current="legacy"))
        self.add_widget(root)
        self._snapshot = None

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if app.private_key:
            self.lbl_new.text = "Connected: " + short_addr(address_from_private_key(app.private_key))
        else:
            self.lbl_new.text = "Connected: (unlock wallet)"

    def do_check(self, *_):
        old = self.old_input.text.strip()
        if not (old.startswith("0x") and len(old) == 42):
            show_popup("Error", "Invalid old address.")
            return
        app = App.get_running_app()
        new_addr = None
        if app.private_key:
            new_addr = address_from_private_key(app.private_key)
        self.status.text = "Reading chain…"

        def worker():
            try:
                old_stats = rpc.stats_of(old)
                new_eff = 0
                if new_addr:
                    new_stats = rpc.stats_of(new_addr)
                    new_eff = new_stats["effective"]
                snap = {
                    "old": old,
                    "new": new_addr,
                    "old_eff": old_stats["effective"],
                    "new_eff": new_eff,
                }
                Clock.schedule_once(lambda dt: self._checked(snap, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._checked(None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _checked(self, snap, err):
        if err:
            self.status.text = err
            show_popup("Error", err)
            return
        self._snapshot = snap
        self.lbl_old.text = "Old: " + short_addr(snap["old"])
        self.lbl_old_eff.text = f"Old effective now: {snap['old_eff']}"
        self.lbl_old_after.text = f"Old effective after +1: {snap['old_eff'] + 1}"
        if snap["new"]:
            self.lbl_new.text = "Connected: " + short_addr(snap["new"])
            self.lbl_new_eff.text = f"Connected effective: {snap['new_eff']}"
        self.status.text = "Ready — you can START or FINISH"
        show_popup("Checked", "Ledger values loaded.\nYou can claim this address.")

    def do_claim(self, kind):
        app = App.get_running_app()
        if not app.private_key:
            show_popup("Error", "Unlock wallet first.")
            self.manager.current = "unlock"
            return
        old = self.old_input.text.strip()
        if not (old.startswith("0x") and len(old) == 42):
            show_popup("Error", "Invalid old address.")
            return
        new_addr = address_from_private_key(app.private_key)
        if new_addr.lower() == old.lower():
            show_popup("Error", "New and old address must be different.")
            return
        self.status.text = "Reading latest effective…"
        label = "START" if kind == "S" else "FINISH"

        def worker():
            try:
                import legacy as leg
                old_stats = rpc.stats_of(old)
                new_stats = rpc.stats_of(new_addr)
                meta = leg.make_legacy_metadata(
                    kind, new_addr, old,
                    new_stats["effective"], old_stats["effective"],
                )
                payload = "0x" + os.urandom(32).hex()
                # intendedTo = old address (gives +1 to old)
                result = sign_record(app.private_key, CHAIN_ID, old, payload, meta)
                txr = txmod.send_record_signature(
                    app.private_key, old, payload, result["signature"], meta
                )
                Clock.schedule_once(
                    lambda dt: self._claimed(label, meta, txr, old_stats["effective"], None), 0
                )
            except Exception as e:
                Clock.schedule_once(lambda dt: self._claimed(label, "", None, 0, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _claimed(self, label, meta, txr, old_before, err):
        if err:
            self.status.text = err
            show_popup("Error", err)
            return
        self.status.text = f"{label} sent {txr['txHash'][:18]}…"
        show_popup(
            f"{label} recorded",
            f"Old effective before: {old_before}\n"
            f"Expected after +1: {old_before + 1}\n\n"
            f"Metadata:\n{meta}\n\n"
            f"Tx:\n{txr['txHash'][:28]}…"
        )
        # refresh numbers
        self.do_check()





class GasScreen(Screen):
    """Gas cost panel: Push / Trust / Effective / Total (Etherscan)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(HeaderBar(title="Gas Costs"))
        root.add_widget(SubLabel(text="ETH spent on Push / Trust / Effective", color=TEXT_MUTED))

        card = Card()
        self.addr_input = BrandInput(hint_text="0x address")
        card.add_widget(self.addr_input)
        self.api_key_input = BrandInput(hint_text="Etherscan API key (optional)")
        try:
            cur = rpc.get_etherscan_api_key()
            # show blank if still the built-in default (user can paste own)
            from rpc import DEFAULT_ETHERSCAN_API_KEY
            if cur != DEFAULT_ETHERSCAN_API_KEY:
                self.api_key_input.text = cur
        except Exception:
            pass
        card.add_widget(self.api_key_input)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b1 = BrandButton(text="CALCULATE", bg_color=ORANGE)
        b1.bind(on_release=self.do_calc)
        b2 = BrandButton(text="MINE", bg_color=INPUT_BG)
        b2.bind(on_release=self.use_mine)
        row.add_widget(b1)
        row.add_widget(b2)
        card.add_widget(row)
        root.add_widget(card)

        res = Card()
        self.lbl_eff = Label(text="Effective: —", color=BLUE_SOFT, bold=True,
                             font_size=dp(15), size_hint_y=None, height=dp(24), halign="left")
        self.lbl_eff.bind(size=lambda *a: setattr(self.lbl_eff, "text_size", self.lbl_eff.size))
        self.lbl_trust = Label(text="Trust: —", color=GREEN_BR, bold=True,
                               font_size=dp(15), size_hint_y=None, height=dp(24), halign="left")
        self.lbl_trust.bind(size=lambda *a: setattr(self.lbl_trust, "text_size", self.lbl_trust.size))
        self.lbl_push = Label(text="Push: —", color=ORANGE, bold=True,
                              font_size=dp(15), size_hint_y=None, height=dp(24), halign="left")
        self.lbl_push.bind(size=lambda *a: setattr(self.lbl_push, "text_size", self.lbl_push.size))
        self.lbl_total = Label(text="Total: —", color=YELLOW, bold=True,
                               font_size=dp(16), size_hint_y=None, height=dp(26), halign="left")
        self.lbl_total.bind(size=lambda *a: setattr(self.lbl_total, "text_size", self.lbl_total.size))
        for w in (self.lbl_eff, self.lbl_trust, self.lbl_push, self.lbl_total):
            res.add_widget(w)
        self.status = SubLabel(text="", color=TEXT_MUTED)
        res.add_widget(self.status)
        root.add_widget(res)

        root.add_widget(Label())
        root.add_widget(NavBar(current="gas"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
        elif getattr(app, "last_check_address", None):
            self.addr_input.text = app.last_check_address

    def use_mine(self, *_):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
            self.do_calc()
        else:
            try:
                self.addr_input.text = ws.peek_address(app.user_data_dir)
                self.do_calc()
            except Exception:
                show_popup("Info", "Unlock or create a wallet first.")

    def do_calc(self, *_):
        addr = self.addr_input.text.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter a valid 0x address.")
            return
        # optional user API key
        try:
            rpc.set_etherscan_api_key(self.api_key_input.text.strip())
        except Exception:
            pass
        self.status.text = "Fetching txs from Etherscan… (may take a bit)"
        for lbl in (self.lbl_eff, self.lbl_trust, self.lbl_push, self.lbl_total):
            lbl.text = lbl.text.split(":")[0] + ": …"

        def worker():
            try:
                data = rpc.gas_costs_for(addr)
                Clock.schedule_once(lambda dt: self._show(data, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show(None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _fmt(self, eth, usd, count, label_count):
        s = f"{eth:.6f} ETH"
        if usd is not None:
            s += f"  (${usd:.2f})"
        s += f"  · {count} {label_count}"
        return s

    def _show(self, data, err):
        if err:
            self.status.text = err
            show_popup("Error", err)
            return
        self.lbl_eff.text = "Effective: " + self._fmt(
            data["effectiveEth"], data["effectiveUsd"], data["effectiveCount"], "txs")
        self.lbl_trust.text = "Trust: " + self._fmt(
            data["trustEth"], data["trustUsd"], data["trustCount"], "txs")
        self.lbl_push.text = "Push: " + self._fmt(
            data["pushEth"], data["pushUsd"], data["pushCount"], "txs")
        self.lbl_total.text = "Total: " + self._fmt(
            data["totalEth"], data["totalUsd"],
            data["pushCount"] + data["trustCount"], "txs")
        price = data.get("ethUsd")
        self.status.text = f"ETH price: ${price:.0f}" if price else "Done (no USD price)"






class SignSubmitScreen(Screen):
    """
    Split flow: sign offline, submit with gas wallet.
    Address field: up to 200 lines (use 1 or 2).
    Metadata field: up to 200 lines (use 1 or 2) — must match address count.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="Sign & Submit"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        root.add_widget(SubLabel(text="1–2 lines used · fields hold up to 200", color=TEXT_MUTED))

        sign_card = Card()
        sign_card.add_widget(SubLabel(text="Addresses (1 or 2 lines)", color=YELLOW))
        self.ss_addrs = MultiInput(hint_text="0xabc...\n0xdef...")
        self.ss_addrs.height = dp(70)
        sign_card.add_widget(self.ss_addrs)
        sign_card.add_widget(SubLabel(text="Metadata messages (1 or 2 lines)", color=YELLOW))
        self.ss_metas = MultiInput(hint_text="message one\nmessage two")
        self.ss_metas.height = dp(70)
        sign_card.add_widget(self.ss_metas)
        sbtn = BrandButton(text="SIGN PAYLOAD(S)", bg_color=BLUE)
        sbtn.bind(on_release=self.do_ss_sign)
        sign_card.add_widget(sbtn)
        root.add_widget(sign_card)

        self.payload_box = CopyableText(
            text="Signed payload JSON will appear here — long-press to select & copy",
            color=GREEN_BR,
            font_size=dp(11),
            height=dp(90),
        )
        root.add_widget(self.payload_box)

        sub_card = Card()
        sub_card.add_widget(SubLabel(text="Step 2 — Paste payload(s) & submit", color=ORANGE))
        self.ss_paste = MultiInput(hint_text="Paste signed payload JSON (or JSON array)")
        self.ss_paste.height = dp(72)
        sub_card.add_widget(self.ss_paste)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        loadb = BrandButton(text="LOAD", bg_color=INPUT_BG)
        loadb.bind(on_release=self.load_payload)
        sendb = BrandButton(text="SUBMIT ON-CHAIN", bg_color=GREEN)
        sendb.bind(on_release=self.do_ss_submit)
        row.add_widget(loadb)
        row.add_widget(sendb)
        sub_card.add_widget(row)
        self.ss_status = CopyableText(text="", color=TEXT_MUTED, height=dp(36))
        sub_card.add_widget(self.ss_status)
        root.add_widget(sub_card)

        root.add_widget(NavBar(current="ss"))
        self.add_widget(root)
        self._payloads = []

    def on_pre_enter(self, *a):
        if hasattr(self, "payer_bar"):
            self.payer_bar.refresh()

    def _parse_lines(self, text, max_lines=200):
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        if len(lines) > max_lines:
            raise ValueError(f"Max {max_lines} lines")
        return lines

    def do_ss_sign(self, *_):
        app = App.get_running_app()
        signer_key = app.get_signer_key()
        if not signer_key:
            show_popup("Error", "Unlock a wallet first to sign.")
            self.manager.current = "unlock"
            return
        try:
            addrs = self._parse_lines(self.ss_addrs.text)
            metas = self._parse_lines(self.ss_metas.text)
        except ValueError as e:
            show_popup("Error", str(e))
            return
        if not addrs or not metas:
            show_popup("Error", "Enter at least one address and one metadata line.")
            return
        if len(addrs) != len(metas):
            show_popup("Error", f"Line count mismatch: {len(addrs)} addresses vs {len(metas)} messages.")
            return
        if len(addrs) > 2:
            show_popup("Error", "Submit 1 or 2 pairs only (fields accept up to 200 lines for pasting).")
            return
        for a in addrs:
            if not (a.startswith("0x") and len(a) == 42):
                show_popup("Error", f"Invalid address: {a[:16]}…")
                return
        for m in metas:
            if utf8_len(m) > 64:
                show_popup("Error", "Each metadata line max 64 characters.")
                return

        self.ss_status.text = "Signing…"

        def worker():
            try:
                import json
                blobs = []
                for to, meta in zip(addrs, metas):
                    payload_hash = "0x" + os.urandom(32).hex()
                    result = sign_record(signer_key, CHAIN_ID, to, payload_hash, meta)
                    blobs.append({
                        "signer": result["signer"],
                        "intendedTo": to,
                        "payloadHash": payload_hash,
                        "metadata": meta,
                        "signature": result["signature"],
                        "chainId": str(CHAIN_ID),
                        "contract": CONTRACT_ADDRESS,
                    })
                Clock.schedule_once(lambda dt: self._signed(blobs, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._signed(None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _signed(self, blobs, err):
        if err:
            self.ss_status.text = err
            show_popup("Error", err)
            return
        import json
        self._payloads = blobs
        raw = json.dumps(blobs if len(blobs) > 1 else blobs[0], indent=2)
        self.payload_box.text = raw
        self.ss_paste.text = raw
        self.ss_status.text = f"Signed {len(blobs)} payload(s). Long-press JSON to copy."
        show_popup("Signed", f"Created {len(blobs)} payload(s).\nNo transaction was sent.\nLong-press the JSON to copy.")

    def load_payload(self, *_):
        import json
        try:
            raw = self.ss_paste.text.strip()
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list) or not data:
                raise ValueError("Expect JSON object or array")
            if len(data) > 2:
                raise ValueError("Max 2 payloads to submit at once")
            for blob in data:
                for k in ("signer", "intendedTo", "payloadHash", "signature", "metadata"):
                    if k not in blob:
                        raise ValueError(f"Missing field: {k}")
            self._payloads = data
            self.ss_status.text = f"Loaded {len(data)} payload(s) — ready to submit"
            show_popup("Loaded", f"{len(data)} payload(s) OK.")
        except Exception as e:
            self._payloads = []
            show_popup("Error", f"Invalid payload: {e}")

    def do_ss_submit(self, *_):
        app = App.get_running_app()
        payer_key = app.get_payer_key()
        if not payer_key:
            show_popup("Error", "Unlock the gas-payer wallet first.")
            self.manager.current = "unlock"
            return
        if not self._payloads:
            self.load_payload()
            if not self._payloads:
                return
        blobs = list(self._payloads)

        def start():
            self.ss_status.text = "Submitting…"
            def worker():
                try:
                    from pure_crypto import pubkey_to_address, privkey_to_pubkey
                    pk = int(payer_key.replace("0x", ""), 16)
                    from_addr = pubkey_to_address(privkey_to_pubkey(pk))
                    nonce = txmod.get_nonce(from_addr)
                    gas_price = txmod.get_gas_price()
                    hashes = []
                    for blob in blobs:
                        txr = txmod.send_record_signature(
                            payer_key,
                            blob["intendedTo"],
                            blob["payloadHash"],
                            blob["signature"],
                            blob["metadata"],
                            signer=blob.get("signer"),
                            nonce=nonce,
                            gas_price=gas_price,
                        )
                        hashes.append(txr["txHash"])
                        nonce = txr["nonce"] + 1
                    Clock.schedule_once(lambda dt: self._submitted(hashes, None), 0)
                except Exception as e:
                    Clock.schedule_once(lambda dt: self._submitted(None, str(e)), 0)
            threading.Thread(target=worker, daemon=True).start()

        confirm_gas_then(start, title="Confirm submit")

    def _submitted(self, hashes, err):
        if err:
            self.ss_status.text = err
            show_popup("Error", err)
            return
        text = "\\n".join(hashes)
        self.ss_status.text = text
        show_popup("Submitted", f"{len(hashes)} tx(s) on-chain:\\n" + "\\n".join(h[:28] + "…" for h in hashes))



class WalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(10))
        root.add_widget(HeaderBar(title="Wallets"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        self.info = Label(text="", color=TEXT_SEC, font_size=dp(13),
                          size_hint_y=None, height=dp(120),
                          halign="left", valign="top")
        self.info.bind(size=lambda *a: setattr(self.info, "text_size", self.info.size))
        root.add_widget(self.info)
        card = Card()
        unlock = BrandButton(text="MANAGE / UNLOCK SLOTS", bg_color=BLUE)
        unlock.bind(on_release=lambda *_: setattr(self.manager, "current", "unlock"))
        card.add_widget(unlock)
        logout = BrandButton(text="LOGOUT ALL", bg_color=DANGER)
        logout.bind(on_release=lambda *_: App.get_running_app().logout())
        card.add_widget(logout)
        root.add_widget(card)

        motto = Label(
            text="SOS 69069 originates from verified Activity and Signatures.\nWhatever you do. SOS records.\nWhatever you do. Continue ...",
            color=TEXT,
            bold=True,
            font_size=dp(14),
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(72),
        )
        motto.bind(size=lambda *a: setattr(motto, "text_size", motto.size))
        motto.padding_x = dp(HeaderBar.LEFT)
        root.add_widget(motto)

        root.add_widget(Label())
        root.add_widget(NavBar(current="wallet"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        self.payer_bar.refresh()
        lines = []
        for s in (1, 2):
            try:
                addr = ws.peek_address(app.user_data_dir, s)
            except Exception:
                addr = None
            st = "unlocked" if app.keys and app.keys.get(s) else ("saved" if addr else "empty")
            payer = " ← gas payer" if app.payer_slot == s and app.keys and app.keys.get(s) else ""
            lines.append(f"Slot {s}: {st}{payer}")
            if addr:
                lines.append(f"  {addr}")
        self.info.text = "\n".join(lines)



class SOSApp(App):
    # keys: {1: priv_hex or None, 2: priv_hex or None}
    keys = None
    payer_slot = 1
    last_check_address = None
    reply_code = None
    reply_to = None
    last_batch_results = None

    @property
    def private_key(self):
        """Back-compat: primary unlocked key (signer preference = payer or first)."""
        if not self.keys:
            return None
        return self.get_payer_key() or self.keys.get(1) or self.keys.get(2)

    @private_key.setter
    def private_key(self, value):
        if self.keys is None:
            self.keys = {1: None, 2: None}
        if value is None:
            self.keys = {1: None, 2: None}
            return
        # set into current payer slot
        self.keys[self.payer_slot] = value

    def get_payer_key(self):
        if not self.keys:
            return None
        return self.keys.get(self.payer_slot) or self.keys.get(1) or self.keys.get(2)

    def get_signer_key(self):
        """Prefer slot 1 for EIP-712 signing if both unlocked, else any."""
        if not self.keys:
            return None
        return self.keys.get(1) or self.keys.get(2) or self.get_payer_key()

    def cycle_payer_slot(self):
        if not self.keys:
            return
        other = 2 if self.payer_slot == 1 else 1
        if self.keys.get(other):
            self.payer_slot = other

    def logout(self):
        self.keys = {1: None, 2: None}
        self.payer_slot = 1
        if getattr(self, "sm", None):
            self.sm.current = "unlock"

    def build(self):

        os.makedirs(self.user_data_dir, exist_ok=True)
        sm = ScreenManager()
        sm.add_widget(LoadingScreen(name="loading"))
        sm.add_widget(WelcomeScreen(name="welcome"))
        sm.add_widget(CreateWalletScreen(name="create"))
        sm.add_widget(ImportWalletScreen(name="import"))
        sm.add_widget(UnlockScreen(name="unlock"))
        sm.add_widget(CheckScreen(name="check"))
        sm.add_widget(MessagesScreen(name="messages"))
        sm.add_widget(SignScreen(name="sign"))
        sm.add_widget(BatchScreen(name="batch"))
        sm.add_widget(PresenceScreen(name="presence"))
        sm.add_widget(LegacyScreen(name="legacy"))
        sm.add_widget(GasScreen(name="gas"))
        sm.add_widget(SignSubmitScreen(name="ss"))
        sm.add_widget(WalletScreen(name="wallet"))
        sm.current = "loading"
        self.sm = sm
        return sm

    def go_to_wallet_screen(self, address):
        self.sm.current = "sign"


if __name__ == "__main__":
    SOSApp().run()
