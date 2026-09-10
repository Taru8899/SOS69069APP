from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
import os, json
from human.theme import PageScroll, HeaderBar, CopyableText
from human.screens.nav import HumanNavBar
from human import texts as T

class HumanAttestScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="ATTEST"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=T.ATTEST_TITLE, color=T.TEXT, bold=True, font_size=T.FONT_SECTION, size_hint_y=None, height=dp(28)))
        mid.add_widget(Label(text=T.ATTEST_HINT, color=T.TEXT_MUTED, font_size=T.FONT_SMALL, size_hint_y=None, height=dp(40)))
        self.body = CopyableText(text="", color=T.TEXT_SEC, height=dp(200))
        mid.add_widget(self.body)
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_attest"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        path = os.path.join(app.user_data_dir, "human_attestations")
        lines = []
        if os.path.isdir(path):
            for fn in sorted(os.listdir(path), reverse=True)[:20]:
                try:
                    with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                        d = json.load(f)
                    sub = d.get("subject") or {}
                    lines.append(f"{fn}\n  fp={sub.get('fingerprint', '—')}")
                except Exception:
                    pass
        self.body.text = "\n\n".join(lines) if lines else "No attestations yet.\nUse VERIFY to accept someone face-to-face."
