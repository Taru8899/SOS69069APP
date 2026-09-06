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

class CheckScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(HeaderBar.LEFT), dp(8), dp(12), dp(8)], spacing=dp(8))
        root.add_widget(HeaderBar(title="TRUTH"))

        trends_card = Card()
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
            btn.bind(on_release=(lambda ww: lambda *_: self.select_window(ww))(w))
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

        self.trends_status = CopyableText(text="Select a time window and tap LOAD TRENDS", color=TEXT_MUTED, height=dp(28))
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
        self.load_trends()


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
        self.load_trends()


    def load_trends(self, *_):
        window = getattr(self, "_trend_window", None) or "24h"
        year = getattr(self, "_trend_year", None)
        self._trend_window = window
        self.trends_status.text = f"Loading trends ({window})…"
        self.trends_box.clear_widgets()

        def worker():
            try:
                events = rpc.fetch_all_metadata_events()
                trends = rpc.compute_word_trends(events, window, year=year)
                Clock.schedule_once(lambda dt: self._show_trends(trends, events, None), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._show_trends([], [], str(e)), 0)
        threading.Thread(target=worker, daemon=True).start()

    def _show_trends(self, trends, events, err):
        self.trends_box.clear_widgets()
        total_events = len(events) if events else 0
        if err:
            self.trends_status.text = err
            return
        if not trends:
            self.trends_status.text = f"No words found in this window ({total_events} total messages scanned)."
            return
        self._trend_events = events
        self.trends_status.text = f"Top words ({total_events} total messages scanned)"
        for rank, (word, count) in enumerate(trends[:20], start=1):
            row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8), padding=[0, 0, 0, 0])
            btn = Button(
                text=f"{rank}.  {word}   ({count})",
                background_normal="",
                background_color=(0, 0, 0, 0),
                color=TEXT,
                bold=True,
                font_size=dp(19),
                halign="left",
                size_hint_y=None,
                height=dp(40),
            )
            btn.bind(size=lambda *a, b=btn: setattr(b, "text_size", (b.width, None)))
            btn.bind(on_release=lambda b, w=word: self._open_trend_messages(w))
            row.add_widget(btn)
            self.trends_box.add_widget(row)


    def _open_trend_messages(self, word):
        self.trends_status.text = f'Messages for "{word}"…'
        self.trends_box.clear_widgets()
        back = BrandButton(text="← BACK TO TRENDS", bg_color=INPUT_BG)
        back.bind(on_release=lambda *_: self.load_trends())
        self.trends_box.add_widget(back)
        events = getattr(self, "_trend_events", []) or []
        shown = 0
        for ev in events:
            meta = (ev.get("metadata") or "")
            if word.lower() not in meta.lower():
                continue
            card = Card()
            title = Label(
                text=meta[:200],
                color=TEXT,
                bold=True,
                font_size=dp(17),
                halign="left",
                valign="top",
                size_hint_y=None,
                height=dp(52),
            )
            title.bind(size=lambda *a, w=title: setattr(w, "text_size", (w.width, None)))
            card.add_widget(title)
            signer = ev.get("signer") or ""
            addr_l = Label(
                text=short_addr(signer),
                color=TEXT_SEC,
                bold=True,
                font_size=dp(14),
                halign="center",
                size_hint_y=None,
                height=dp(26),
            )
            addr_l.bind(size=lambda *a, w=addr_l: setattr(w, "text_size", w.size))
            card.add_widget(addr_l)
            txh = ev.get("txHash") or ""
            if txh:
                card.add_widget(LinkButton(
                    text=f"tx {txh[:18]}… ↗",
                    url=etherscan_tx(txh),
                    color=GREEN_BR,
                    font_size=dp(13),
                    height=dp(26),
                    halign="center",
                ))
            self.trends_box.add_widget(card)
            shown += 1
            if shown >= 20:
                break
        self.trends_status.text = (
            f'No messages found for "{word}"' if shown == 0
            else f'{shown} message(s) for "{word}"'
        )



