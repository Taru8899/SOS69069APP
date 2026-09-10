"""PQID load screen — lives in human/ for standalone reuse."""
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
import os

from human.app_meta import APP_NAME, format_version
from human import texts as T

class HumanLoadingScreen(Screen):
    """Same structure as main load screen; branded SOS 69069 PQID."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.clearcolor = (0.04, 0.06, 0.1, 1)
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        root.add_widget(BoxLayout(size_hint_y=0.2))
        col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(10))
        col.bind(minimum_height=col.setter("height"))
        # logo if present
        for name in ("logo_smooth.png", "sos69069.png", "icon.png"):
            p = os.path.join(os.path.dirname(__file__), "..", "..", name)
            p = os.path.abspath(p)
            if os.path.isfile(p):
                col.add_widget(Image(source=p, size_hint=(1, None), height=dp(96), allow_stretch=True, keep_ratio=True))
                break
        for text, fs, colr, h in (
            (T.LOADING_LINE1, T.FONT_SECTION, T.TEXT, dp(30)),
            (T.LOADING_LINE2, T.FONT_SECTION, T.TEXT, dp(28)),
            (format_version(), T.FONT_SMALL, T.TEXT_MUTED, dp(24)),
            (T.LOADING_LINE3, T.FONT_BODY, T.TEXT_SEC, dp(28)),
        ):
            lbl = Label(text=text, font_size=fs, color=colr, size_hint_y=None, height=h, halign="center")
            lbl.bind(size=lambda *a, l=lbl: setattr(l, "text_size", l.size))
            col.add_widget(lbl)
        wrap = BoxLayout(orientation="vertical")
        wrap.add_widget(Label())  # spacer
        wrap.add_widget(col)
        wrap.add_widget(Label())
        root.add_widget(wrap)
        self.add_widget(root)

    def on_enter(self, *a):
        Clock.schedule_once(self._next, 5.0)

    def _next(self, dt):
        app = App.get_running_app()
        # standalone: go human_home or unlock; embedded: same if started on this screen
        target = getattr(app, "pqid_after_load", None) or "human_home"
        try:
            app.sm.current = target
        except Exception as e:
            print("HumanLoadingScreen next:", e)
