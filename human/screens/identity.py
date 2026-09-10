from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
import json
from human.theme import PageScroll, HeaderBar, BrandButton, CopyableText, show_popup
from human.screens.nav import HumanNavBar
from human import texts as T
from human import identity as ident

class HumanIdentityScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="IDENTITY"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=T.IDENTITY_TITLE, color=T.TEXT, bold=True, font_size=T.FONT_SECTION, size_hint_y=None, height=dp(32)))
        self.body = CopyableText(text="", color=T.TEXT_SEC, height=dp(160))
        mid.add_widget(self.body)
        self.qr_payload = CopyableText(text="", color=T.GREEN_BR, height=dp(100))
        mid.add_widget(self.qr_payload)
        create = BrandButton(text=T.IDENTITY_CREATE, bg_color=T.BLUE)
        create.bind(on_release=self.create_id)
        mid.add_widget(create)
        mid.add_widget(Label(text=T.IDENTITY_HINT, color=T.TEXT_MUTED, font_size=T.FONT_SMALL, size_hint_y=None, height=dp(40)))
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_identity"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self):
        app = App.get_running_app()
        idn = ident.load_identity(app.user_data_dir)
        if not idn:
            self.body.text = "No identity.\nTap CREATE IDENTITY."
            self.qr_payload.text = ""
            return
        self.body.text = (
            f"Fingerprint\n{idn.get('fingerprint')}\n\n"
            f"Public key\n{idn.get('public_key', '')[:40]}…\n\n"
            f"Algorithm: {idn.get('algorithm')}\nCreated: {idn.get('created')}"
        )
        self.qr_payload.text = json.dumps(ident.public_card(idn), indent=2)

    def create_id(self, *_):
        app = App.get_running_app()
        if ident.has_identity(app.user_data_dir):
            show_popup("Exists", T.IDENTITY_EXISTS)
            return
        try:
            idn = ident.generate_identity()
            ident.save_identity(app.user_data_dir, idn)
            show_popup("Created", f"Fingerprint\n{idn['fingerprint']}")
            self.refresh()
        except Exception as e:
            show_popup("Error", str(e))
