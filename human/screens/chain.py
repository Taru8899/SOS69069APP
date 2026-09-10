from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.metrics import dp
from human.theme import PageScroll, HeaderBar, CopyableText
from human.screens.nav import HumanNavBar
from human import texts as T
from human import chain_submit as cs

class HumanChainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation="vertical", padding=[dp(10), dp(8), dp(12), dp(8)], spacing=dp(6))
        root.add_widget(HeaderBar(title="CHAIN"))
        scroll = PageScroll()
        mid = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8), padding=[0, 4, 0, 8])
        mid.bind(minimum_height=mid.setter("height"))
        mid.add_widget(Label(text=T.CHAIN_TITLE, color=T.TEXT, bold=True, font_size=T.FONT_SECTION, size_hint_y=None, height=dp(28)))
        mid.add_widget(Label(text=T.CHAIN_HINT, color=T.TEXT_MUTED, font_size=T.FONT_SMALL, size_hint_y=None, height=dp(48)))
        self.body = CopyableText(text="", color=T.TEXT_SEC, height=dp(160))
        mid.add_widget(self.body)
        scroll.add_widget(mid)
        root.add_widget(scroll)
        root.add_widget(HumanNavBar(current="human_chain"))
        self.add_widget(root)

    def on_pre_enter(self, *a):
        addr = cs.try_get_main_payer_address()
        self.body.text = cs.describe_submit_bridge() + "\n\n" + (
            f"Main gas payer: {addr}" if addr else "Main gas payer: (not unlocked)"
        )
