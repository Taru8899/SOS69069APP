"""SOS 69069 — Android entry point."""
import os
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager

from ui.screens_wallet import (
    LoadingScreen, WelcomeScreen, CreateWalletScreen,
    ImportWalletScreen, UnlockScreen, WalletScreen,
)
from ui.screens_truth import CheckScreen
from ui.screens_msg import MessagesScreen
from ui.screens_sign import SignScreen, BatchScreen, SignSubmitScreen
from ui.screens_pres import PresenceScreen
from ui.screens_lsf import LegacyScreen
from ui.screens_gas import GasScreen


class SOSApp(App):
    keys = None
    payer_slot = 1
    last_check_address = None
    reply_code = None
    reply_to = None
    last_batch_results = None

    @property
    def private_key(self):
        if not self.keys:
            return None
        return self.get_payer_key() or self.keys.get(1) or self.keys.get(2)

    @private_key.setter
    def private_key(self, value):
        if self.keys is None:
            self.keys = {1: None, 2: None}
        if value is None:
            self.keys = {1: None, 2: None}
            return
        self.keys[self.payer_slot] = value

    def get_payer_key(self):
        if not self.keys:
            return None
        return self.keys.get(self.payer_slot) or self.keys.get(1) or self.keys.get(2)

    def get_signer_key(self):
        if not self.keys:
            return None
        return self.keys.get(1) or self.keys.get(2) or self.get_payer_key()

    def cycle_payer_slot(self):
        if not self.keys:
            return
        other = 2 if self.payer_slot == 1 else 1
        if self.keys.get(other):
            self.payer_slot = other

    def logout(self):
        self.keys = {1: None, 2: None}
        self.payer_slot = 1
        if getattr(self, "sm", None) is not None:
            try:
                self.sm.current = "unlock"
            except Exception:
                pass

    def build(self):
        os.makedirs(self.user_data_dir, exist_ok=True)
        if self.keys is None:
            self.keys = {1: None, 2: None}
        sm = ScreenManager()
        self.sm = sm
        for name, cls in (
            ("loading", LoadingScreen),
            ("welcome", WelcomeScreen),
            ("create", CreateWalletScreen),
            ("import", ImportWalletScreen),
            ("unlock", UnlockScreen),
            ("check", CheckScreen),
            ("messages", MessagesScreen),
            ("sign", SignScreen),
            ("batch", BatchScreen),
            ("presence", PresenceScreen),
            ("legacy", LegacyScreen),
            ("gas", GasScreen),
            ("ss", SignSubmitScreen),
            ("wallet", WalletScreen),
        ):
            try:
                sm.add_widget(cls(name=name))
            except Exception as e:
                print("Screen init failed:", name, e)
        sm.current = "loading"
        return sm

    def go_to_wallet_screen(self, address):
        self.sm.current = "sign"


if __name__ == "__main__":
    SOSApp().run()
