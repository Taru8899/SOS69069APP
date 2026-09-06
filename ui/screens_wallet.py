from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from kivy.clock import Clock
import os
import re
import threading

from sos_core import sign_record, address_from_private_key, CONTRACT_ADDRESS
import wallet_storage as ws
import rpc
import tx as txmod

from ui.theme import (
    CHAIN_ID, MAX_META, TEXT, TEXT_SEC, TEXT_MUTED, INPUT_BG, CARD_BG,
    GREEN, GREEN_BR, BLUE, BLUE_SOFT, YELLOW, ORANGE, DANGER,
    Card, BrandButton, BrandInput, MultiInput, SubLabel, SectionLabel,
    HeaderBar, PayerBar, NavBar, CopyableText, LinkButton,
    show_popup, confirm_gas_then, open_url, etherscan_address, etherscan_tx,
    short_addr, fmt_time, utf8_len, extract_conv_code, get_app_version,
    get_build_fingerprint, _logo_image, _logo_path,
)

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
        logo_row.add_widget(_logo_image(128))
        logo_row.add_widget(Label())
        block.add_widget(logo_row)

        for text, sz, col, h in (
            ("Loading ...", dp(18), TEXT, dp(30)),
            ("SOS 69069", dp(16), TEXT, dp(28)),
            ("v" + get_app_version(), dp(13), TEXT_MUTED, dp(24)),
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
        try:
            app = App.get_running_app()
            has_wallet = False
            try:
                has_wallet = bool(ws.wallet_exists(app.user_data_dir))
            except Exception:
                has_wallet = False
            target = "unlock" if has_wallet else "welcome"
            if target in self.manager.screen_names:
                self.manager.current = target
            elif "welcome" in self.manager.screen_names:
                self.manager.current = "welcome"
        except Exception as e:
            print("LoadingScreen._go_next error:", e)


class WelcomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(12))
        root.add_widget(Label(size_hint_y=0.15))  # top spacer

        # Centered logo block
        center = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(12))
        center.bind(minimum_height=center.setter("height"))
        logo_row = BoxLayout(size_hint_y=None, height=dp(120))
        logo_row.add_widget(Label())  # left flex
        logo_row.add_widget(_logo_image(120))
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
        chk = BrandButton(text="TRUTH", bg_color=INPUT_BG)
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



class WalletScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(10))
        root.add_widget(HeaderBar(title="ID"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        self.info = CopyableText(text="", color=TEXT_SEC, font_size=dp(13), height=dp(120))
        root.add_widget(self.info)
        card = Card()
        unlock = BrandButton(text="MANAGE / UNLOCK SLOTS", bg_color=BLUE)
        unlock.bind(on_release=lambda *_: setattr(self.manager, "current", "unlock"))
        card.add_widget(unlock)
        logout = BrandButton(text="LOGOUT ALL", bg_color=DANGER)
        logout.bind(on_release=lambda *_: App.get_running_app().logout())
        card.add_widget(logout)
        root.add_widget(card)

        center_block = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        center_block.bind(minimum_height=center_block.setter("height"))
        sos = Label(
            text="SOS 69069",
            color=TEXT,
            bold=True,
            font_size=dp(22),
            halign="center",
            size_hint_y=None,
            height=dp(36),
        )
        sos.bind(size=lambda *a: setattr(sos, "text_size", sos.size))
        center_block.add_widget(sos)
        ver = Label(
            text="v" + get_app_version(),
            color=TEXT_MUTED,
            bold=True,
            font_size=dp(14),
            halign="center",
            size_hint_y=None,
            height=dp(24),
        )
        ver.bind(size=lambda *a: setattr(ver, "text_size", ver.size))
        center_block.add_widget(ver)
        fp = get_build_fingerprint()
        fp_short = (fp[:12] + "…" + fp[-8:]) if len(fp) >= 24 else fp
        fp_lbl = CopyableText(
            text="build " + fp_short,
            color=TEXT_MUTED,
            font_size=dp(12),
            height=dp(28),
        )
        center_block.add_widget(fp_lbl)

        links = [
            ("sos69069.com", "https://sos69069.com"),
            ("Token on Etherscan", "https://etherscan.io/token/0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"),
            ("SOS 69069 on GitHub", "https://github.com/Taru8899/69069"),
            ("README.md", "https://github.com/Taru8899/69069/blob/main/README.md"),
            ("MIT license", "https://github.com/Taru8899/69069/blob/main/LICENSE"),
        ]
        for label, url in links:
            center_block.add_widget(LinkButton(
                text=label + " ↗", url=url, color=GREEN_BR, height=dp(28), halign="center",
            ))

        motto = Label(
            text="Originates from verified Activity and Signatures.\nWhatever you do. SOS records.\nWhatever you do. Continue ...",
            color=TEXT,
            bold=True,
            font_size=dp(14),
            halign="center",
            valign="top",
            size_hint_y=None,
            height=dp(72),
        )
        motto.bind(size=lambda *a: setattr(motto, "text_size", motto.size))
        center_block.add_widget(motto)
        root.add_widget(center_block)

        root.add_widget(Label())
        root.add_widget(NavBar(current="wallet"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if hasattr(self, "payer_bar"):
            self.payer_bar.refresh()
        lines = []
        for s in (1, 2):
            try:
                addr = ws.peek_address(app.user_data_dir, s)
            except Exception:
                addr = None
            st = "unlocked" if app.keys and app.keys.get(s) else ("saved" if addr else "empty")
            payer = " <- gas payer" if getattr(app, "payer_slot", 1) == s and app.keys and app.keys.get(s) else ""
            lines.append(f"Slot {s}: {st}{payer}")
            if addr:
                lines.append(f"  {addr}")
        self.info.text = "\n".join(lines)


