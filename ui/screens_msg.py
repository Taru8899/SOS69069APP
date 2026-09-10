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
import local_store
import tx as txmod

from ui.theme import (
    PageScroll,
    CHAIN_ID, MAX_META, TEXT, TEXT_SEC, TEXT_MUTED, INPUT_BG, CARD_BG,
    GREEN, GREEN_BR, BLUE, BLUE_SOFT, YELLOW, ORANGE, DANGER,
    Card, BrandButton, BrandInput, MultiInput, SubLabel, SectionLabel,
    HeaderBar, PayerBar, NavBar, CopyableText, LinkButton,
    show_popup, confirm_gas_then, open_url, etherscan_address, etherscan_tx,
    short_addr, fmt_time, utf8_len, extract_conv_code, get_app_version,
    get_build_fingerprint, _logo_image, _logo_path,
)

class MessagesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(6))
        root.add_widget(HeaderBar(title="MSG"))

        # Address FIXED outside scroll so paste/focus works on Android
        self.addr_input = BrandInput(hint_text="0x address to load messages")
        root.add_widget(self.addr_input)

        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=[0, dp(4), 0, dp(8)])
        mid.bind(minimum_height=mid.setter("height"))

        cols = BoxLayout(size_hint_y=None, height=dp(100), spacing=dp(8))
        left = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.5)
        mine = BrandButton(text="MINE", bg_color=INPUT_BG)
        mine.bind(on_release=self.use_mine)
        load = BrandButton(text="LOAD", bg_color=GREEN)
        load.bind(on_release=self.load_messages)
        left.add_widget(mine)
        left.add_widget(load)
        right = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_x=0.5)
        self.tab_trust = BrandButton(text="TRUST", bg_color=BLUE)
        self.tab_push = BrandButton(text="PUSH", bg_color=INPUT_BG)
        self.tab_trust.bind(on_release=lambda *_: self.switch_tab("trust"))
        self.tab_push.bind(on_release=lambda *_: self.switch_tab("push"))
        right.add_widget(self.tab_trust)
        right.add_widget(self.tab_push)
        cols.add_widget(left)
        cols.add_widget(right)
        mid.add_widget(cols)

        self.status = CopyableText(text="Enter address and tap LOAD", color=TEXT_MUTED, height=dp(28))
        mid.add_widget(self.status)

        self.list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=[0, dp(4)])
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        mid.add_widget(self.list_box)

        scroll.add_widget(mid)
        root.add_widget(scroll)
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
        # Do not overwrite a pasted/edited address
        if (self.addr_input.text or "").strip():
            return
        app = App.get_running_app()
        if getattr(app, "last_check_address", None):
            self.addr_input.text = app.last_check_address
        elif app.private_key:
            try:
                self.addr_input.text = address_from_private_key(app.private_key)
            except Exception:
                pass

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
            data_dir = getattr(App.get_running_app(), "user_data_dir", None) or "."
            try:
                fresh = rpc.fetch_messages(addr, direction=self.direction, max_results=80)
                merged = local_store.msg_merge_save(
                    data_dir, fresh, address=addr, direction=self.direction, source="network+merge"
                )
                events = local_store.msg_filter(merged, addr, self.direction)
                Clock.schedule_once(lambda dt: self._render(events, None), 0)
            except Exception as e:
                cached, _ = local_store.msg_load(data_dir)
                events = local_store.msg_filter(cached, addr, self.direction)
                if events:
                    Clock.schedule_once(lambda dt: self._render(events, None), 0)
                else:
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
        self.status.text = f"{len(events)} message(s)"
        for ev in events:
            meta = (ev.get("metadata") or "").strip()
            when = fmt_time(ev.get("timestamp") or 0)
            card = Card()
            card.add_widget(CopyableText(text=meta, color=TEXT, font_size=dp(15), height=dp(48)))
            txh = ev.get("txHash") or ""
            if txh:
                card.add_widget(LinkButton(
                    text=f"tx {txh[:18]}… · blk {ev.get('blockNumber','')} · {when} ↗",
                    url=etherscan_tx(txh),
                    color=GREEN_BR,
                    font_size=dp(12),
                    height=dp(26),
                ))
            from_a = ev.get("signer") or ""
            to_a = ev.get("intendedTo") or ""
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
            row.add_widget(CopyableText(
                text=f"{short_addr(from_a)} → {short_addr(to_a)}",
                color=YELLOW, font_size=dp(12), height=dp(32),
            ))
            code = extract_conv_code(meta) or (
                txh[2:10].lower() if isinstance(txh, str) and txh.startswith("0x") and len(txh) >= 10 else ""
            )
            if code:
                rb = Button(
                    text=f"REPLY · {code}",
                    background_normal="",
                    background_color=BLUE,
                    color=TEXT,
                    bold=True,
                    font_size=dp(10),
                    size_hint_x=None,
                    width=dp(96),
                    size_hint_y=None,
                    height=dp(28),
                )
                rb.bind(on_release=lambda b, c=code, a=from_a: self._reply(c, a))
                row.add_widget(rb)
            card.add_widget(row)
            self.list_box.add_widget(card)


    def _reply(self, code, party):
        app = App.get_running_app()
        app.reply_code = code
        app.reply_to = party
        if not app.private_key:
            show_popup("Info", "Unlock wallet first to reply.")
            self.manager.current = "unlock"
            return
        self.manager.current = "sign"


