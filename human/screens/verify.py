from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
import json
from human.theme import PageScroll, HeaderBar, BrandButton, MultiInput, CopyableText, show_popup
from human.screens.nav import HumanNavBar
from human import texts as T
from human import attestation as att

class HumanVerifyScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="VERIFY"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=T.VERIFY_TITLE, color=T.TEXT, bold=True, font_size=T.FONT_SECTION, size_hint_y=None, height=dp(28)))
        mid.add_widget(Label(text=T.VERIFY_HINT, color=T.TEXT_MUTED, font_size=T.FONT_SMALL, size_hint_y=None, height=dp(48)))
        self.paste = MultiInput(height=dp(120), hint_text='{"type":"identity","pk":"...","fingerprint":"..."}')
        mid.add_widget(self.paste)
        self.info = CopyableText(text="", color=T.TEXT_SEC, height=dp(80))
        mid.add_widget(self.info)
        parse_b = BrandButton(text=T.VERIFY_PARSE, bg_color=T.INPUT_BG)
        parse_b.bind(on_release=self.parse)
        mid.add_widget(parse_b)
        acc = BrandButton(text=T.VERIFY_ACCEPT, bg_color=T.GREEN)
        acc.bind(on_release=self.accept)
        mid.add_widget(acc)
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_verify"))
        self.add_widget(root)
        self._parsed = None

    def parse(self, *_):
        try:
            data = json.loads(self.paste.text.strip())
            if "fingerprint" not in data and data.get("type") != "identity":
                raise ValueError("Need identity JSON with fingerprint")
            self._parsed = data
            self.info.text = f"Fingerprint\n{data.get('fingerprint', '—')}\npk: {(data.get('pk') or data.get('public_key') or '')[:36]}…"
        except Exception as e:
            self._parsed = None
            show_popup("Error", str(e))

    def accept(self, *_):
        if not self._parsed:
            self.parse()
            if not self._parsed:
                return
        app = App.get_running_app()
        att.save_acceptance(app.user_data_dir, self._parsed)
        show_popup("Accepted", "Stored local face-to-face acceptance.")
