from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
import os
import threading

from sos_core import sign_record, address_from_private_key, CONTRACT_ADDRESS
import wallet_storage as ws
import rpc

CHAIN_ID = 1

# Brand colors from style.css
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


class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = [dp(18), dp(14)]
        self.spacing = dp(10)
        self.size_hint_y = None
        self.bind(minimum_height=self.setter("height"))
        with self.canvas.before:
            Color(*CARD_BG)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(15)])
        self.bind(pos=self._upd, size=self._upd)

    def _upd(self, *a):
        self._bg.pos = self.pos
        self._bg.size = self.size


class BrandButton(Button):
    def __init__(self, text="", bg_color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.size_hint_y = None
        self.height = dp(52)
        self.background_normal = ""
        self.background_color = bg_color or BLUE
        self.color = TEXT
        self.bold = True
        self.font_size = dp(16)


class BrandInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(48)
        self.background_normal = ""
        self.background_active = ""
        self.background_color = INPUT_BG
        self.foreground_color = TEXT
        self.cursor_color = BLUE_SOFT
        self.padding = [dp(14), dp(12)]
        self.font_size = dp(15)
        self.multiline = False
        self.write_tab = False


class TitleLabel(Label):
    def __init__(self, text="", **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = TEXT
        self.bold = True
        self.font_size = dp(22)
        self.size_hint_y = None
        self.height = dp(36)
        self.halign = "center"
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


class SubLabel(Label):
    def __init__(self, text="", color=None, **kwargs):
        super().__init__(**kwargs)
        self.text = text
        self.color = color or TEXT_SEC
        self.font_size = dp(14)
        self.size_hint_y = None
        self.height = dp(28)
        self.halign = "center"
        self.bind(size=lambda *a: setattr(self, "text_size", self.size))


def show_popup(title, message):
    content = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
    msg = Label(text=message, color=TEXT, font_size=dp(14),
                halign="center", valign="middle")
    msg.bind(size=lambda *a: setattr(msg, "text_size", msg.size))
    content.add_widget(msg)
    close = BrandButton(text="OK", bg_color=BLUE)
    popup = Popup(title=title, title_color=TEXT, title_size=dp(16),
                  content=content, size_hint=(0.88, 0.38),
                  background="", separator_color=BORDER, auto_dismiss=True)
    with popup.canvas.before:
        Color(*CARD_BG)
        popup._bg = RoundedRectangle(pos=popup.pos, size=popup.size, radius=[dp(12)])
    popup.bind(pos=lambda *a: setattr(popup._bg, "pos", popup.pos),
               size=lambda *a: setattr(popup._bg, "size", popup.size))
    close.bind(on_release=popup.dismiss)
    content.add_widget(close)
    popup.open()


# ── Navigation bar ───────────────────────────────────────────

class NavBar(BoxLayout):
    def __init__(self, current="", **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(48)
        self.spacing = dp(6)
        self.padding = [dp(4), 0]

        screens = [
            ("check", "CHECK", BLUE_SOFT),
            ("wallet", "SIGN", GREEN_BR),
            ("unlock", "WALLET", YELLOW),
        ]
        for name, label, color in screens:
            btn = Button(
                text=label,
                background_normal="",
                background_color=color if name == current else INPUT_BG,
                color=TEXT,
                bold=True,
                font_size=dp(13),
                size_hint_x=1,
            )
            btn.bind(on_release=lambda b, n=name: self._go(n))
            self.add_widget(btn)

    def _go(self, name):
        app = App.get_running_app()
        if name == "wallet" and not app.private_key:
            app.sm.current = "unlock"
        else:
            app.sm.current = name


# ── Screens ──────────────────────────────────────────────────

class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(16))
        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(90), spacing=dp(4))
        header.add_widget(TitleLabel(text="SOS 69069"))
        header.add_widget(SubLabel(text="Ethereum Mainnet", color=TEXT_MUTED))
        root.add_widget(header)

        card = Card()
        card.add_widget(SubLabel(text="No wallet found on this device.", color=TEXT_SEC))
        card.add_widget(Label(size_hint_y=None, height=dp(8)))
        create_btn = BrandButton(text="CREATE NEW WALLET", bg_color=GREEN)
        create_btn.bind(on_release=self.go_create)
        card.add_widget(create_btn)
        import_btn = BrandButton(text="IMPORT EXISTING KEY", bg_color=BLUE)
        import_btn.bind(on_release=self.go_import)
        card.add_widget(import_btn)
        root.add_widget(card)
        root.add_widget(Label())
        footer = SubLabel(text="Whatever you do. SOS records. Continue ...", color=TEXT_MUTED)
        footer.font_size = dp(12)
        root.add_widget(footer)
        self.add_widget(root)

    def go_create(self, *_):
        self.manager.current = "create"

    def go_import(self, *_):
        self.manager.current = "import"


class CreateWalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        root.add_widget(TitleLabel(text="Create New Wallet"))
        hint = SubLabel(text="A new private key will be generated on this device.\nSet a password to encrypt it locally.", color=TEXT_SEC)
        hint.height = dp(50)
        root.add_widget(hint)

        card = Card()
        self.password_input = BrandInput(hint_text="Set a password", password=True)
        card.add_widget(self.password_input)
        self.confirm_input = BrandInput(hint_text="Confirm password", password=True)
        card.add_widget(self.confirm_input)
        create_btn = BrandButton(text="GENERATE & SAVE", bg_color=GREEN)
        create_btn.bind(on_release=self.do_create)
        card.add_widget(create_btn)
        back_btn = BrandButton(text="BACK", bg_color=INPUT_BG)
        back_btn.bind(on_release=self.go_back)
        card.add_widget(back_btn)
        root.add_widget(card)
        root.add_widget(Label())
        self.add_widget(root)

    def go_back(self, *_):
        self.manager.current = "welcome"

    def do_create(self, *_):
        pw = self.password_input.text
        confirm = self.confirm_input.text
        if len(pw) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if pw != confirm:
            show_popup("Error", "Passwords do not match.")
            return
        privkey_hex = "0x" + os.urandom(32).hex()
        address = address_from_private_key(privkey_hex)
        app = App.get_running_app()
        ws.save_wallet(app.user_data_dir, privkey_hex, address, pw)
        show_popup("Wallet Created", f"Address:\n{address}\n\nBack up this device securely.")
        app.go_to_wallet_screen(address)


class ImportWalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        root.add_widget(TitleLabel(text="Import Wallet"))
        card = Card()
        self.privkey_input = BrandInput(hint_text="Private key (0x...)")
        card.add_widget(self.privkey_input)
        self.password_input = BrandInput(hint_text="Set a password", password=True)
        card.add_widget(self.password_input)
        self.confirm_input = BrandInput(hint_text="Confirm password", password=True)
        card.add_widget(self.confirm_input)
        import_btn = BrandButton(text="IMPORT & SAVE", bg_color=GREEN)
        import_btn.bind(on_release=self.do_import)
        card.add_widget(import_btn)
        back_btn = BrandButton(text="BACK", bg_color=INPUT_BG)
        back_btn.bind(on_release=self.go_back)
        card.add_widget(back_btn)
        root.add_widget(card)
        root.add_widget(Label())
        self.add_widget(root)

    def go_back(self, *_):
        self.manager.current = "welcome"

    def do_import(self, *_):
        raw = self.privkey_input.text.strip()
        pw = self.password_input.text
        confirm = self.confirm_input.text
        if len(pw) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if pw != confirm:
            show_popup("Error", "Passwords do not match.")
            return
        try:
            privkey_int = int(raw.replace("0x", ""), 16)
            if not (0 < privkey_int < 2**256):
                raise ValueError()
            privkey_hex = "0x" + raw.replace("0x", "").zfill(64)
            address = address_from_private_key(privkey_hex)
        except Exception:
            show_popup("Error", "Invalid private key format.")
            return
        app = App.get_running_app()
        ws.save_wallet(app.user_data_dir, privkey_hex, address, pw)
        show_popup("Wallet Imported", f"Address:\n{address}")
        app.go_to_wallet_screen(address)


class UnlockScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        root.add_widget(TitleLabel(text="Unlock Wallet"))
        self.address_label = SubLabel(text="", color=YELLOW)
        root.add_widget(self.address_label)
        card = Card()
        self.password_input = BrandInput(hint_text="Password", password=True)
        card.add_widget(self.password_input)
        unlock_btn = BrandButton(text="UNLOCK", bg_color=GREEN)
        unlock_btn.bind(on_release=self.do_unlock)
        card.add_widget(unlock_btn)
        root.add_widget(card)

        # always allow going to Check without unlocking
        check_btn = BrandButton(text="CHECK ANY ADDRESS", bg_color=BLUE)
        check_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "check"))
        root.add_widget(check_btn)

        root.add_widget(Label())
        self.add_widget(root)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        try:
            addr = ws.peek_address(app.user_data_dir)
            self.address_label.text = f"Wallet: {addr}"
        except Exception:
            self.address_label.text = ""

    def do_unlock(self, *_):
        pw = self.password_input.text
        app = App.get_running_app()
        try:
            privkey_hex = ws.load_wallet(app.user_data_dir, pw)
        except ws.WrongPasswordOrTampered:
            show_popup("Error", "Wrong password.")
            return
        except Exception as e:
            show_popup("Error", f"Could not load wallet: {e}")
            return
        address = address_from_private_key(privkey_hex)
        app.private_key = privkey_hex
        app.go_to_wallet_screen(address)


class CheckScreen(Screen):
    """Lookup Effective / Trust / Push for any address."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))

        root.add_widget(TitleLabel(text="SOS 69069"))
        root.add_widget(SubLabel(text="Check Presence", color=TEXT_MUTED))

        card = Card()
        self.addr_input = BrandInput(hint_text="0x address")
        card.add_widget(self.addr_input)

        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        check_btn = BrandButton(text="CHECK", bg_color=BLUE)
        check_btn.bind(on_release=self.do_check)
        row.add_widget(check_btn)
        mine_btn = BrandButton(text="MY ADDRESS", bg_color=INPUT_BG)
        mine_btn.bind(on_release=self.use_mine)
        row.add_widget(mine_btn)
        card.add_widget(row)
        root.add_widget(card)

        # Metrics card
        metrics = Card()
        self.effective_lbl = Label(
            text="Effective: —", color=BLUE_SOFT, bold=True,
            font_size=dp(28), size_hint_y=None, height=dp(40),
            halign="center",
        )
        self.effective_lbl.bind(size=lambda *a: setattr(self.effective_lbl, "text_size", self.effective_lbl.size))
        metrics.add_widget(self.effective_lbl)

        row2 = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(12))
        self.trust_lbl = Label(text="Trust: —", color=GREEN_BR, bold=True, font_size=dp(16), halign="center")
        self.trust_lbl.bind(size=lambda *a: setattr(self.trust_lbl, "text_size", self.trust_lbl.size))
        self.push_lbl = Label(text="Push: —", color=ORANGE, bold=True, font_size=dp(16),halign="center")
        self.push_lbl.bind(size=lambda *a: setattr(self.push_lbl, "text_size", self.push_lbl.size))
        row2.add_widget(self.trust_lbl)
        row2.add_widget(self.push_lbl)
        metrics.add_widget(row2)

        self.status_lbl = SubLabel(text="", color=TEXT_MUTED)
        metrics.add_widget(self.status_lbl)
        root.add_widget(metrics)

        root.add_widget(Label())  # spacer
        root.add_widget(NavBar(current="check"))
        self.add_widget(root)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        # pre-fill with unlocked address or last known
        if app.private_key:
            try:
                self.addr_input.text = address_from_private_key(app.private_key)
            except Exception:
                pass
        elif not self.addr_input.text:
            try:
                self.addr_input.text = ws.peek_address(app.user_data_dir)
            except Exception:
                self.addr_input.text = "0x1C10e6574ee696f54b21A611a21313E4714628ad"

    def use_mine(self, *_):
        app = App.get_running_app()
        if app.private_key:
            self.addr_input.text = address_from_private_key(app.private_key)
            self.do_check()
            return
        try:
            addr = ws.peek_address(app.user_data_dir)
            if addr:
                self.addr_input.text = addr
                self.do_check()
                return
        except Exception:
            pass
        show_popup("Info", "Unlock or create a wallet first.")

    def do_check(self, *_):
        addr = self.addr_input.text.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter a valid 0x address.")
            return

        self.status_lbl.text = "Loading…"
        self.effective_lbl.text = "Effective: …"
        self.trust_lbl.text = "Trust: …"
        self.push_lbl.text = "Push: …"

        def worker():
            try:
                stats = rpc.stats_of(addr)
                Clock.schedule_once(lambda dt: self._show(stats, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show(None, str(e)), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _show(self, stats, err):
        if err:
            self.status_lbl.text = err
            self.effective_lbl.text = "Effective: —"
            self.trust_lbl.text = "Trust: —"
            self.push_lbl.text = "Push: —"
            return
        self.effective_lbl.text = f"Effective: {stats['effective']}"
        self.trust_lbl.text = f"Trust: {stats['trust']}"
        self.push_lbl.text = f"Push: {stats['push']}"
        self.status_lbl.text = "Live on Ethereum Mainnet"


class WalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(10))
        root.add_widget(TitleLabel(text="SOS 69069"))
        self.contract_label = SubLabel(text=f"Contract: {CONTRACT_ADDRESS[:10]}...", color=TEXT_MUTED)
        root.add_widget(self.contract_label)
        self.my_address_label = SubLabel(text="", color=YELLOW)
        root.add_widget(self.my_address_label)

        card = Card()
        self.recipient_input = BrandInput(hint_text="Recipient address (0x...)")
        card.add_widget(self.recipient_input)
        self.payload_input = BrandInput(hint_text="Payload hash (0x... 32 bytes)")
        card.add_widget(self.payload_input)
        self.metadata_input = BrandInput(hint_text="Metadata (max 64 chars)")
        card.add_widget(self.metadata_input)
        sign_btn = BrandButton(text="SIGN PRESENCE", bg_color=GREEN)
        sign_btn.bind(on_release=self.do_sign)
        card.add_widget(sign_btn)
        lock_btn = BrandButton(text="LOCK WALLET", bg_color=INPUT_BG)
        lock_btn.bind(on_release=self.do_lock)
        card.add_widget(lock_btn)
        root.add_widget(card)

        self.result_label = Label(text="", color=GREEN_BR, font_size=dp(13),
                                  size_hint_y=None, height=dp(100),
                                  halign="left", valign="top")
        self.result_label.bind(size=lambda *a: setattr(self.result_label, "text_size", self.result_label.size))
        root.add_widget(self.result_label)

        root.add_widget(NavBar(current="wallet"))
        self.add_widget(root)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        if app.private_key:
            addr = address_from_private_key(app.private_key)
            self.my_address_label.text = f"Your address: {addr}"

    def do_sign(self, *_):
        app = App.get_running_app()
        if not app.private_key:
            show_popup("Error", "Wallet is locked.")
            return
        recipient = self.recipient_input.text.strip()
        payload = self.payload_input.text.strip()
        metadata = self.metadata_input.text.strip()
        if len(metadata) > 64:
            show_popup("Error", "Metadata must be 64 characters or fewer.")
            return
        try:
            result = sign_record(app.private_key, CHAIN_ID, recipient, payload, metadata)
            self.result_label.text = f"Signature:\n{result['signature']}"
        except Exception as e:
            show_popup("Error", f"Signing failed: {e}")

    def do_lock(self, *_):
        app = App.get_running_app()
        app.private_key = None
        self.result_label.text = ""
        self.manager.current = "unlock"


class SOSApp(App):
    private_key = None

    def build(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        sm = ScreenManager()
        sm.add_widget(WelcomeScreen(name="welcome"))
        sm.add_widget(CreateWalletScreen(name="create"))
        sm.add_widget(ImportWalletScreen(name="import"))
        sm.add_widget(UnlockScreen(name="unlock"))
        sm.add_widget(CheckScreen(name="check"))
        sm.add_widget(WalletScreen(name="wallet"))

        if ws.wallet_exists(self.user_data_dir):
            sm.current = "unlock"
        else:
            sm.current = "welcome"
        self.sm = sm
        return sm

    def go_to_wallet_screen(self, address):
        self.sm.current = "wallet"


if __name__ == "__main__":
    SOSApp().run()
