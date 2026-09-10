"""PQID UI chrome — self-contained (works embedded and standalone)."""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.metrics import dp
from kivy.utils import get_color_from_hex

TEXT = get_color_from_hex("#f1f5f9")
TEXT_SEC = get_color_from_hex("#cbd5e1")
TEXT_MUTED = get_color_from_hex("#94a3b8")
GREEN = get_color_from_hex("#22c55e")
GREEN_BR = get_color_from_hex("#4ade80")
BLUE = get_color_from_hex("#3b82f6")
BLUE_SOFT = get_color_from_hex("#38bdf8")
YELLOW = get_color_from_hex("#eab308")
ORANGE = get_color_from_hex("#f97316")
DANGER = get_color_from_hex("#ef4444")
INPUT_BG = get_color_from_hex("#1e293b")
CARD_BG = get_color_from_hex("#0f172a")


def PageScroll(**kwargs):
    kwargs.setdefault("do_scroll_x", False)
    kwargs.setdefault("bar_width", 0)
    kwargs.setdefault("bar_color", (0, 0, 0, 0))
    kwargs.setdefault("bar_inactive_color", (0, 0, 0, 0))
    return ScrollView(**kwargs)


class HeaderBar(BoxLayout):
    LEFT = 10

    def __init__(self, title="", **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(8), **kwargs)
        self.add_widget(Label(text=str(title), color=TEXT, bold=True, font_size=dp(16), halign="left"))


class BrandButton(Button):
    def __init__(self, bg_color=None, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(44)
        self.background_normal = ""
        self.background_color = bg_color or BLUE
        self.color = TEXT
        self.bold = True
        self.font_size = dp(14)


class BrandInput(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("multiline", False)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(46)
        self.background_normal = ""
        self.background_active = ""
        self.background_color = INPUT_BG
        self.foreground_color = TEXT
        self.padding = [dp(12), dp(12)]
        self.font_size = dp(14)


class MultiInput(TextInput):
    def __init__(self, **kwargs):
        h = kwargs.pop("height", dp(80))
        kwargs.setdefault("multiline", True)
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = h
        self.background_normal = ""
        self.background_active = ""
        self.background_color = INPUT_BG
        self.foreground_color = TEXT
        self.padding = [dp(12), dp(12)]


class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(4), padding=dp(8), **kwargs)
        self.bind(minimum_height=self.setter("height"))


class CopyableText(TextInput):
    def __init__(self, **kwargs):
        kwargs.setdefault("readonly", True)
        kwargs.setdefault("multiline", True)
        h = kwargs.pop("height", dp(40))
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = h
        self.background_normal = ""
        self.background_active = ""
        self.background_color = (0, 0, 0, 0)
        self.foreground_color = kwargs.get("color", TEXT)
        self.padding = [0, 0]


class LinkButton(Button):
    def __init__(self, text="", url="", **kwargs):
        super().__init__(text=text, **kwargs)
        self.url = url
        self.size_hint_y = None
        self.height = dp(36)
        self.background_normal = ""
        self.background_color = (0, 0, 0, 0)
        self.color = GREEN_BR
        self.bold = True


def show_popup(title, message):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(text=str(title), color=TEXT, bold=True, size_hint_y=None, height=dp(28)))
    body = Label(text=str(message), color=TEXT_SEC, size_hint_y=None)
    body.bind(texture_size=lambda *a: setattr(body, "height", max(dp(40), body.texture_size[1])))
    body.text_size = (dp(260), None)
    content.add_widget(body)
    pop = Popup(title="", content=content, size_hint=(0.85, None), height=dp(220),
                separator_height=0, background_color=CARD_BG)
    close = BrandButton(text="OK", bg_color=BLUE)
    close.bind(on_release=pop.dismiss)
    content.add_widget(close)
    pop.open()
