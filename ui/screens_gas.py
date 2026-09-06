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

class GasScreen(Screen):
    """Gas cost panel: Push / Trust / Effective / Total (Etherscan)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="GAS"))
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
        b1 = BrandButton(text="CHECK", bg_color=ORANGE)
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

        root.add_widget(SectionLabel(text="Check presence", color=TEXT))
        presence_metrics = Card()
        self.presence_eff = Label(text="Effective: —", color=BLUE_SOFT, bold=True,
                                   font_size=dp(22), size_hint_y=None, height=dp(32), halign="center")
        self.presence_eff.bind(size=lambda *a: setattr(self.presence_eff, "text_size", self.presence_eff.size))
        presence_metrics.add_widget(self.presence_eff)
        prow2 = BoxLayout(size_hint_y=None, height=dp(28), spacing=dp(10))
        self.presence_trust = Label(text="Trust: —", color=GREEN_BR, bold=True, font_size=dp(15), halign="left")
        self.presence_trust.bind(size=lambda *a: setattr(self.presence_trust, "text_size", self.presence_trust.size))
        self.presence_push = Label(text="Push: —", color=ORANGE, bold=True, font_size=dp(15), halign="right")
        self.presence_push.bind(size=lambda *a: setattr(self.presence_push, "text_size", self.presence_push.size))
        prow2.add_widget(self.presence_trust)
        prow2.add_widget(self.presence_push)
        presence_metrics.add_widget(prow2)
        self.presence_status = LinkButton(text="", color=GREEN_BR, height=dp(24))
        presence_metrics.add_widget(self.presence_status)
        root.add_widget(presence_metrics)

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
            pres = None
            pres_err = None
            try:
                pres = rpc.stats_of(addr)
            except Exception as e:
                pres_err = str(e)
            try:
                data = rpc.gas_costs_for(addr)
                Clock.schedule_once(lambda dt: self._show_both(data, None, pres, pres_err), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show_both(None, str(e), pres, pres_err), 0)
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
        addr = self.addr_input.text.strip()
        link = etherscan_address(addr)
        self.lbl_eff.text = "Effective: " + self._fmt(
            data["effectiveEth"], data["effectiveUsd"], data["effectiveCount"], "txs")
        self.lbl_trust.text = "Trust: " + self._fmt(
            data["trustEth"], data["trustUsd"], data["trustCount"], "txs")
        self.lbl_push.text = "Push: " + self._fmt(
            data["pushEth"], data["pushUsd"], data["pushCount"], "txs")
        self.lbl_total.text = "Total: " + self._fmt(
            data["totalEth"], data["totalUsd"],
            data["pushCount"] + data["trustCount"], "txs")
        # clickable count links under metrics
        if hasattr(self, "gas_links"):
            self.gas_links.clear_widgets()
            for label, n in (
                ("Effective", data["effectiveCount"]),
                ("Trust", data["trustCount"]),
                ("Push", data["pushCount"]),
                ("Total", data["pushCount"] + data["trustCount"]),
            ):
                self.gas_links.add_widget(LinkButton(
                    text=f"{label}: {n} txs ↗",
                    url=link,
                    color=BLUE_SOFT,
                    font_size=dp(12),
                    height=dp(24),
                ))
        price = data.get("ethUsd")
        if price is not None:
            self.status.text = ""
            if hasattr(self, "price_link"):
                self.price_link.text = f"ETH price: {price:.0f} ↗"
                self.price_link.url = link
        else:
            if hasattr(self, "price_link"):
                self.price_link.text = "Done (no USD price)"
                self.price_link.url = None


    def do_presence_check(self, *_):
        addr = self.addr_input.text.strip()
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter a valid 0x address.")
            return
        self.presence_status.text = "Loading…"
        self.presence_eff.text = "Effective: …"
        self.presence_trust.text = "Trust: …"
        self.presence_push.text = "Push: …"

        def worker():
            try:
                s = rpc.stats_of(addr)
                Clock.schedule_once(lambda dt: self._show_presence(s, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show_presence(None, str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _show_presence(self, s, err):
        if err:
            self.presence_status.text = err
            self.presence_eff.text = "Effective: —"
            self.presence_trust.text = "Trust: —"
            self.presence_push.text = "Push: —"
            return
        self.presence_eff.text = f"Effective: {s['effective']}"
        self.presence_trust.text = f"Trust: {s['trust']}"
        self.presence_push.text = f"Push: {s['push']}"
        addr = self.addr_input.text.strip()
        self.presence_status.text = "Live on Ethereum Mainnet ↗"
        self.presence_status.url = etherscan_address(addr)
        App.get_running_app().last_check_address = addr

    def presence_use_mine(self, *_):
        self.use_mine()






    def _show_both(self, data, err, pres, pres_err):
        # presence always attempted
        if pres and not pres_err:
            self.presence_eff.text = f"Effective: {pres['effective']}"
            self.presence_trust.text = f"Trust: {pres['trust']}"
            self.presence_push.text = f"Push: {pres['push']}"
            addr = self.addr_input.text.strip()
            self.presence_status.text = "Live on Ethereum Mainnet ↗"
            if hasattr(self.presence_status, "url"):
                self.presence_status.url = etherscan_address(addr)
        elif pres_err:
            self.presence_status.text = pres_err
        if err:
            self.status.text = err
            # still keep presence if we got it
            return
        self._show(data, None)


