"""HOME | IDENTITY | VERIFY | RECORDS | ATTEST | CHAIN | PQID"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from human import texts as T

_ITEMS = [
    ("human_home", "HOME", T.BLUE_SOFT),
    ("human_identity", "IDENTITY", T.GREEN_BR),
    ("human_verify", "VERIFY", T.YELLOW),
    ("human_records", "RECORDS", T.ORANGE),
    ("human_attest", "ATTEST", get_color_from_hex("#a78bfa")),
    ("human_chain", "CHAIN", get_color_from_hex("#c084fc")),
    ("human_pqid", "PQID", T.BLUE),
]

class HumanNavBar(BoxLayout):
    def __init__(self, current="", **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(46)
        self.spacing = dp(2)
        self.padding = [dp(1), 0]
        for name, label, color in _ITEMS:
            btn = Button(
                text=label, background_normal="",
                background_color=color if name == current else T.INPUT_BG,
                color=T.TEXT, bold=True, font_size=T.FONT_NAV, size_hint_x=1,
            )
            btn.bind(on_release=lambda b, n=name: self._go(n))
            self.add_widget(btn)

    def _go(self, name):
        App.get_running_app().sm.current = name
