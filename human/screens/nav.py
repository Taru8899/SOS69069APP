"""Human section bottom nav: HOME | IDENTITY | VERIFY | RECORDS | ATTEST | CHAIN | PQID | BACK"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.metrics import dp
from kivy.utils import get_color_from_hex
from human import texts as T

# screen name per nav label
_ITEMS = [
    ("human_home", "HOME", T.BLUE_SOFT),
    ("human_identity", "IDENTITY", T.GREEN_BR),
    ("human_verify", "VERIFY", T.YELLOW),
    ("human_records", "RECORDS", T.ORANGE),
    ("human_attest", "ATTEST", get_color_from_hex("#a78bfa")),
    ("human_chain", "CHAIN", get_color_from_hex("#c084fc")),
    ("human_pqid", "PQID", T.BLUE),
    ("__back__", "BACK", T.TEXT_MUTED),
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
        app = App.get_running_app()
        if name == "__back__":
            # Embedded: main wallet/unlock. Standalone: PQID home.
            names = [s.name for s in app.sm.screens]
            if "wallet" in names or "unlock" in names:
                if getattr(app, "private_key", None):
                    app.sm.current = "wallet"
                else:
                    app.sm.current = "unlock" if "unlock" in names else "human_home"
            else:
                app.sm.current = "human_home"
            return
        app.sm.current = name
