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

class SignScreen(Screen):
    """Single sign with optional reply code."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(6), dp(10), dp(6)], spacing=dp(6))
        root.add_widget(HeaderBar(title="SIGN"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        self.my_lbl = SubLabel(text="", color=YELLOW)
        self.my_lbl.halign = "left"
        root.add_widget(self.my_lbl)

        card = Card()
        self.recipient = BrandInput(hint_text="Recipient address (0x...)")
        card.add_widget(self.recipient)
        self.payload = BrandInput(hint_text="Payload hash (editable)")
        self.payload.text = "0x" + os.urandom(32).hex()
        card.add_widget(self.payload)
        self.code = BrandInput(hint_text="Conversation code (8 hex, optional)")
        card.add_widget(self.code)
        self.metadata = BrandInput(hint_text="Metadata / message (max 64 chars)")
        card.add_widget(self.metadata)
        self.counter = Label(text="0/64 characters", color=TEXT, bold=True, font_size=dp(14), size_hint_y=None, height=dp(24), halign="left")
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
        root.add_widget(Label())  # flex spacer — keeps header/content pinned to top
        self.tx_link = LinkButton(text="", color=GREEN_BR, height=dp(28))
        root.add_widget(self.tx_link)
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
        if hasattr(self, "tx_link"):
            self.tx_link.text = f"tx {txh[:22]}… ↗"
            self.tx_link.url = etherscan_tx(txh)
        show_popup("Sent", f"Transaction submitted.\n{txh[:22]}…")


class BatchScreen(Screen):
    """Paste many addresses + messages, sign all."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(6), dp(10), dp(6)], spacing=dp(4))
        root.add_widget(HeaderBar(title="BT"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)
        root.add_widget(SubLabel(text="One address and one message per line", color=TEXT_MUTED))

        card = Card()
        card.add_widget(SubLabel(text="Addresses", color=TEXT_SEC))
        self.addrs = MultiInput(height=dp(55), hint_text="0xabc...\n0xdef...")
        card.add_widget(self.addrs)
        card.add_widget(Label(text="Messages (max 64 chars each)", color=TEXT, bold=True, font_size=dp(14), size_hint_y=None, height=dp(24), halign="left"))
        self.msgs = MultiInput(height=dp(55), hint_text="hello\nworld")
        card.add_widget(self.msgs)
        self.info = SubLabel(text="0 pairs", color=TEXT_MUTED)
        card.add_widget(self.info)
        self.addrs.bind(text=self._count)
        self.msgs.bind(text=self._count)

        load = BrandButton(text="LOAD & PREVIEW", bg_color=BLUE)
        load.bind(on_release=self.load_pairs)
        card.add_widget(load)
        root.add_widget(card)

        prev_scroll = ScrollView(size_hint_y=None, height=dp(90))
        self.preview = Label(text="", color=TEXT_SEC, font_size=dp(12),
                             size_hint_y=None, halign="left", valign="top")
        self.preview.bind(texture_size=lambda *a: setattr(self.preview, "height", max(dp(90), self.preview.texture_size[1])))
        self.preview.bind(width=lambda *a: setattr(self.preview, "text_size", (self.preview.width, None)))
        prev_scroll.add_widget(self.preview)
        root.add_widget(prev_scroll)

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

        res_scroll = ScrollView(size_hint_y=None, height=dp(80))
        self.result = Label(text="", color=GREEN_BR, font_size=dp(11),
                            size_hint_y=None, halign="left", valign="top")
        self.result.bind(texture_size=lambda *a: setattr(self.result, "height", max(dp(80), self.result.texture_size[1])))
        self.result.bind(width=lambda *a: setattr(self.result, "text_size", (self.result.width, None)))
        res_scroll.add_widget(self.result)
        root.add_widget(res_scroll)
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



class SignSubmitScreen(Screen):

    """
    Split flow: sign offline, submit with gas wallet.
    Address field: up to 200 lines (use 1 or 2).
    Metadata field: up to 200 lines (use 1 or 2) — must match address count.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(6), dp(10), dp(6)], spacing=dp(4))
        root.add_widget(HeaderBar(title="S&S"))
        self.payer_bar = PayerBar()
        root.add_widget(self.payer_bar)

        tabs = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.tab1_btn = Button(text="1. SIGN", background_normal="", background_color=BLUE,
                                color=TEXT, bold=True, font_size=dp(13))
        self.tab2_btn = Button(text="2. SUBMIT", background_normal="", background_color=INPUT_BG,
                                color=TEXT, bold=True, font_size=dp(13))
        self.tab1_btn.bind(on_release=lambda *_: self.switch_tab(1))
        self.tab2_btn.bind(on_release=lambda *_: self.switch_tab(2))
        tabs.add_widget(self.tab1_btn)
        tabs.add_widget(self.tab2_btn)
        root.add_widget(tabs)

        self.body = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(1, 1))
        root.add_widget(self.body)

        # ---- Tab 1: Sign ----
        self.tab1_content = BoxLayout(orientation="vertical", spacing=dp(6),
                                       size_hint_y=None)
        self.tab1_content.bind(minimum_height=self.tab1_content.setter("height"))

        sign_card = Card()
        sign_card.add_widget(SectionLabel(text="Address", color=YELLOW))
        self.ss_addr = BrandInput(hint_text="0x…")
        sign_card.add_widget(self.ss_addr)
        sign_card.add_widget(SectionLabel(text="Messages (one per line, max 200)", color=YELLOW))
        self.ss_metas = MultiInput(height=dp(120), hint_text="message one\nmessage two\n...")
        sign_card.add_widget(self.ss_metas)
        sbtn = BrandButton(text="SIGN PAYLOAD(S)", bg_color=BLUE)
        sbtn.bind(on_release=self.do_ss_sign)
        sign_card.add_widget(sbtn)
        self.tab1_content.add_widget(sign_card)

        self.payload_box = CopyableText(
            text="Signed payload JSON will appear here — long-press to select & copy",
            color=GREEN_BR,
            font_size=dp(11),
            height=dp(90),
        )
        self.tab1_content.add_widget(self.payload_box)

        # ---- Tab 2: Submit ----
        self.tab2_content = BoxLayout(orientation="vertical", spacing=dp(6),
                                       size_hint_y=None)
        self.tab2_content.bind(minimum_height=self.tab2_content.setter("height"))

        sub_card = Card()
        sub_card.add_widget(SectionLabel(text="Step 2 — Paste payload(s) & submit", color=ORANGE))
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
        self.tab2_content.add_widget(sub_card)

        root.add_widget(NavBar(current="ss"))
        self.add_widget(root)
        self._payloads = []
        self.switch_tab(1)

    def switch_tab(self, tab):
        self._current_tab = tab
        self.body.clear_widgets()
        if tab == 1:
            self.tab1_btn.background_color = BLUE
            self.tab2_btn.background_color = INPUT_BG
            self.body.add_widget(self.tab1_content)
        else:
            self.tab2_btn.background_color = ORANGE
            self.tab1_btn.background_color = INPUT_BG
            self.body.add_widget(self.tab2_content)

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
            addr = self.ss_addr.text.strip()
            metas = self._parse_lines(self.ss_metas.text, max_lines=200)
        except ValueError as e:
            show_popup("Error", str(e))
            return
        if not (addr.startswith("0x") and len(addr) == 42):
            show_popup("Error", "Enter one valid 0x address.")
            return
        if not metas:
            show_popup("Error", "Enter at least one message line.")
            return
        if len(metas) > 200:
            show_popup("Error", "Max 200 message lines.")
            return
        for m in metas:
            if utf8_len(m) > 64:
                show_popup("Error", "Each message max 64 characters.")
                return
        addrs = [addr] * len(metas)

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
        text = "\n".join(hashes)
        self.ss_status.text = text
        show_popup("Submitted", f"{len(hashes)} tx(s) on-chain:\n" + "\n".join(h[:28] + "…" for h in hashes))



