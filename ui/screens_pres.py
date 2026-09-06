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

class PresenceScreen(Screen):
    """Create and manage presence offers (O/A/D/X protocol)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
        root.add_widget(HeaderBar(title="PRES"))

        # Create offer card
        create = Card()
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

        root.add_widget(Label(size_hint_y=None, height=dp(8)))  # gap under filter row

        self.status = CopyableText(text="Tap a filter to load offers", color=TEXT_MUTED, height=dp(28))
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
        self.load_offers()

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
        txo = o.get("txHash") or ""
        st = o.get("status", "?")
        title = ("PUSH" if o.get("type") == "P" else "TRUST") + f"  #{o.get('id','')[:8]}"
        card.add_widget(LinkButton(
            text=f"{title}  [{st}] ↗",
            url=etherscan_tx(txo) if txo else None,
            color=GREEN_BR,
            font_size=dp(15),
            height=dp(30),
        ))
        card.add_widget(Label(
            text=f"Poster {short_addr(o.get('signer',''))}  qty={o.get('qty','1')}  ret={o.get('ret') or '—'}",
            color=TEXT_SEC, bold=True, font_size=dp(14), size_hint_y=None, height=dp(24),
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





