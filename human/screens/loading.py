"""PQID load screen — SOS logo + version; safe on Android."""
from kivy.app import App
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.metrics import dp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.resources import resource_find
import os
import traceback

from human.app_meta import format_version
from human import texts as T


def _find_logo():
    """Locate SOS logo in package (works on desktop and Android)."""
    names = ("logo_smooth.png", "sos69069.png", "icon.png", "presplash.png")
    candidates = []
    # next to this file → repo root
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))
    for n in names:
        candidates.append(os.path.join(root, n))
        candidates.append(n)
        found = resource_find(n)
        if found:
            candidates.append(found)
    try:
        app = App.get_running_app()
        if app:
            for n in names:
                candidates.append(os.path.join(app.directory, n))
                candidates.append(os.path.join(app.user_data_dir, n))
    except Exception:
        pass
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


class HumanLoadingScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        try:
            Window.clearcolor = (0.04, 0.06, 0.1, 1)
        except Exception:
            pass
        root = BoxLayout(orientation="vertical", padding=dp(24), spacing=dp(12))
        # center column
        col = BoxLayout(orientation="vertical", size_hint=(1, 1), spacing=dp(12))
        col.add_widget(Label(size_hint_y=0.25))  # top spacer

        logo_path = None
        try:
            logo_path = _find_logo()
        except Exception:
            logo_path = None
        if logo_path:
            try:
                img = Image(
                    source=logo_path,
                    size_hint=(1, None),
                    height=dp(120),
                    allow_stretch=True,
                    keep_ratio=True,
                )
                col.add_widget(img)
            except Exception as e:
                print("logo load failed:", e)
                col.add_widget(Label(text="SOS", color=T.GREEN_BR, font_size=dp(32), bold=True, size_hint_y=None, height=dp(48)))
        else:
            col.add_widget(Label(text="SOS", color=T.GREEN_BR, font_size=dp(32), bold=True, size_hint_y=None, height=dp(48)))

        for text, fs, colr in (
            (T.LOADING_LINE1, T.FONT_SECTION, T.TEXT),
            (T.LOADING_LINE2, T.FONT_SECTION, T.TEXT),
            (format_version(), T.FONT_SMALL, T.TEXT_MUTED),
            (T.LOADING_LINE3, T.FONT_BODY, T.TEXT_SEC),
        ):
            lbl = Label(
                text=str(text),
                font_size=fs,
                color=colr,
                size_hint_y=None,
                height=dp(28),
                halign="center",
                valign="middle",
            )
            lbl.bind(size=lambda *a, l=lbl: setattr(l, "text_size", (l.width, None)))
            col.add_widget(lbl)

        col.add_widget(Label(size_hint_y=0.35))
        root.add_widget(col)
        self.add_widget(root)
        self._scheduled = False

    def on_enter(self, *a):
        if self._scheduled:
            return
        self._scheduled = True
        Clock.schedule_once(self._next, 5.0)

    def _next(self, dt):
        try:
            app = App.get_running_app()
            target = getattr(app, "pqid_after_load", None) or "human_home"
            if getattr(app, "sm", None) is not None:
                if target in [s.name for s in app.sm.screens]:
                    app.sm.current = target
                else:
                    app.sm.current = app.sm.screen_names[0]
        except Exception:
            traceback.print_exc()
