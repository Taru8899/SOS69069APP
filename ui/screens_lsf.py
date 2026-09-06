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

class LegacyScreen(Screen):
    """Legacy claim: CHECK old address, START / FINISH claim."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(HeaderBar(title="LSF"))
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
        self.lbl_new = LinkButton(text="Connected: —", color=GREEN_BR, height=dp(28))
        self.lbl_new_eff = SubLabel(text="Connected effective: —", color=TEXT)
        self.lbl_old = LinkButton(text="Old: —", color=GREEN_BR, height=dp(28))
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
        self.status = CopyableText(text="", color=TEXT_MUTED, height=dp(36))
        actions.add_widget(self.status)
        root.add_widget(actions)

        root.add_widget(Label())
        root.add_widget(NavBar(current="legacy"))
        self.add_widget(root)
        self._snapshot = None

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        if app.private_key:
            addr = address_from_private_key(app.private_key)
            self.lbl_new.text = "Connected: " + short_addr(addr) + " ↗"
            self.lbl_new.url = etherscan_address(addr)
        else:
            self.lbl_new.text = "Connected: (unlock wallet)"
            self.lbl_new.url = None

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
        self.lbl_old.text = "Old: " + short_addr(snap["old"]) + " ↗"
        self.lbl_old.url = etherscan_address(snap["old"])
        self.lbl_old_eff.text = f"Old effective now: {snap['old_eff']}"
        self.lbl_old_after.text = f"Old effective after +1: {snap['old_eff'] + 1}"
        if snap["new"]:
            self.lbl_new.text = "Connected: " + short_addr(snap["new"]) + " ↗"
            self.lbl_new.url = etherscan_address(snap["new"])
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





