from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from human.theme import PageScroll, HeaderBar, BrandButton, CopyableText
from kivy.app import App as _App
from human.screens.nav import HumanNavBar
from human import texts as T
from human import identity as ident

class HumanHomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="HOME"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=T.HOME_TITLE, color=T.TEXT, bold=True, font_size=T.FONT_TITLE, size_hint_y=None, height=dp(36), halign="center"))
        self.status = CopyableText(text="", color=T.TEXT_SEC, height=dp(72))
        mid.add_widget(self.status)
        for text, screen, color in (
            (T.BTN_MY_IDENTITY, "human_identity", T.BLUE),
            (T.BTN_MY_RECORDS, "human_records", T.GREEN),
            (T.BTN_VERIFY, "human_verify", T.YELLOW),
            (T.BTN_ATTEST, "human_attest", T.ORANGE),
            (T.BTN_CHAIN, "human_chain", T.BLUE_SOFT),
        ):
            b = BrandButton(text=text, bg_color=color)
            b.bind(on_release=lambda btn, s=screen: setattr(self.manager, "current", s))
            mid.add_widget(b)
        note = Label(text=T.HOME_SUB, color=T.TEXT_MUTED, font_size=T.FONT_SMALL, size_hint_y=None, height=dp(48), halign="center")
        note.bind(size=lambda *a: setattr(note, "text_size", note.size))
        mid.add_widget(note)
        back = BrandButton(text="BACK TO MAIN ID", bg_color=T.INPUT_BG)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "wallet"))
        mid.add_widget(back)
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_home"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        idn = ident.load_identity(app.user_data_dir)
        if not idn:
            self.status.text = "No human identity yet.\nOpen IDENTITY to create one."
        else:
            self.status.text = f"Fingerprint\n{idn.get('fingerprint', '—')}\nalg: {idn.get('algorithm', '')}"
