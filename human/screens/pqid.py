from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from human.theme import PageScroll, HeaderBar, BrandButton, CopyableText, show_popup
from human.screens.nav import HumanNavBar
from human.app_meta import APP_NAME, format_version
from human import texts as T
from human import identity as ident
from human import record_store as rstore
from human import wallet_storage as hws

class HumanPqidScreen(Screen):
    """Section ID page — clear human data, version, logout human session."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="PQID"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=APP_NAME, color=T.TEXT, bold=True, font_size=T.FONT_TITLE, size_hint_y=None, height=dp(36), halign="center"))
        mid.add_widget(Label(text=format_version(), color=T.TEXT_MUTED, font_size=T.FONT_BODY, size_hint_y=None, height=dp(24), halign="center"))
        self.status = CopyableText(text="", color=T.TEXT_SEC, height=dp(100))
        mid.add_widget(self.status)
        clear_b = BrandButton(text=T.PQID_CLEAR, bg_color=T.DANGER)
        clear_b.bind(on_release=self.clear_human)
        mid.add_widget(clear_b)
        logout = BrandButton(text=T.PQID_LOGOUT, bg_color=T.INPUT_BG)
        logout.bind(on_release=self.logout_human)
        mid.add_widget(logout)
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_pqid"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        idn = ident.load_identity(app.user_data_dir)
        if idn:
            self.status.text = f"Fingerprint\n{idn.get('fingerprint')}\n\nHuman session: {'unlocked' if hws.is_unlocked() else 'locked / local file present'}"
        else:
            self.status.text = "No human identity on device."

    def clear_human(self, *_):
        app = App.get_running_app()
        removed = rstore.clear_human_data(app.user_data_dir)
        hws.logout_session()
        show_popup("Human data cleared", "Removed:\n" + ("\n".join(removed) if removed else "(already empty)"))
        self.on_pre_enter()

    def logout_human(self, *_):
        hws.logout_session()
        show_popup("Logged out", "Human session cleared in memory.\nIdentity file kept until CLEAR HUMAN DATA.")
        self.on_pre_enter()
