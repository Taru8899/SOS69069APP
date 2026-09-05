from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
import os

from sos_core import sign_record, address_from_private_key, CONTRACT_ADDRESS
from pure_crypto import privkey_to_pubkey
import wallet_storage as ws

CHAIN_ID = 1  # set to your target chain id


def show_popup(title, message):
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(Label(text=message))
    close_btn = Button(text="OK", size_hint_y=None, height=50)
    popup = Popup(title=title, content=layout, size_hint=(0.85, 0.4))
    close_btn.bind(on_release=popup.dismiss)
    layout.add_widget(close_btn)
    popup.open()


class WelcomeScreen(Screen):
    """Shown when no wallet exists yet: choose create or import."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=30, spacing=20)

        layout.add_widget(Label(text="SOS 69069", font_size=28, size_hint_y=None, height=60))
        layout.add_widget(Label(text="No wallet found on this device.", size_hint_y=None, height=40))

        create_btn = Button(text="CREATE NEW WALLET", size_hint_y=None, height=60)
        create_btn.bind(on_release=self.go_create)
        layout.add_widget(create_btn)

        import_btn = Button(text="IMPORT EXISTING KEY", size_hint_y=None, height=60)
        import_btn.bind(on_release=self.go_import)
        layout.add_widget(import_btn)

        layout.add_widget(Label())  # spacer
        self.add_widget(layout)

    def go_create(self, *_):
        self.manager.current = "create"

    def go_import(self, *_):
        self.manager.current = "import"


class CreateWalletScreen(Screen):
    """Generates a new private key and asks the user to set a password."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=30, spacing=15)

        self.layout.add_widget(Label(text="Create New Wallet", font_size=22, size_hint_y=None, height=50))
        self.layout.add_widget(Label(
            text="A new private key will be generated on this device.\n"
                 "Set a password to encrypt it locally.",
            size_hint_y=None, height=80,
        ))

        self.password_input = TextInput(hint_text="Set a password", password=True,
                                         multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.password_input)

        self.confirm_input = TextInput(hint_text="Confirm password", password=True,
                                        multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.confirm_input)

        create_btn = Button(text="GENERATE & SAVE", size_hint_y=None, height=60)
        create_btn.bind(on_release=self.do_create)
        self.layout.add_widget(create_btn)

        back_btn = Button(text="BACK", size_hint_y=None, height=50)
        back_btn.bind(on_release=self.go_back)
        self.layout.add_widget(back_btn)

        self.layout.add_widget(Label())
        self.add_widget(self.layout)

    def go_back(self, *_):
        self.manager.current = "welcome"

    def do_create(self, *_):
        pw = self.password_input.text
        confirm = self.confirm_input.text

        if len(pw) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if pw != confirm:
            show_popup("Error", "Passwords do not match.")
            return

        privkey_hex = "0x" + os.urandom(32).hex()
        address = address_from_private_key(privkey_hex)

        app = App.get_running_app()
        ws.save_wallet(app.user_data_dir, privkey_hex, address, pw)

        show_popup("Wallet Created", f"Address:\n{address}\n\nBack up this device securely.")
        app.go_to_wallet_screen(address)


class ImportWalletScreen(Screen):
    """Imports an existing raw private key and encrypts it with a new password."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=30, spacing=15)

        self.layout.add_widget(Label(text="Import Wallet", font_size=22, size_hint_y=None, height=50))

        self.privkey_input = TextInput(hint_text="Private key (0x...)", multiline=False,
                                        size_hint_y=None, height=50)
        self.layout.add_widget(self.privkey_input)

        self.password_input = TextInput(hint_text="Set a password", password=True,
                                         multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.password_input)

        self.confirm_input = TextInput(hint_text="Confirm password", password=True,
                                        multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.confirm_input)

        import_btn = Button(text="IMPORT & SAVE", size_hint_y=None, height=60)
        import_btn.bind(on_release=self.do_import)
        self.layout.add_widget(import_btn)

        back_btn = Button(text="BACK", size_hint_y=None, height=50)
        back_btn.bind(on_release=self.go_back)
        self.layout.add_widget(back_btn)

        self.layout.add_widget(Label())
        self.add_widget(self.layout)

    def go_back(self, *_):
        self.manager.current = "welcome"

    def do_import(self, *_):
        raw = self.privkey_input.text.strip()
        pw = self.password_input.text
        confirm = self.confirm_input.text

        if len(pw) < 8:
            show_popup("Error", "Password must be at least 8 characters.")
            return
        if pw != confirm:
            show_popup("Error", "Passwords do not match.")
            return

        try:
            privkey_int = int(raw.replace("0x", ""), 16)
            if not (0 < privkey_int < 2**256):
                raise ValueError()
            privkey_hex = "0x" + raw.replace("0x", "").zfill(64)
            address = address_from_private_key(privkey_hex)
        except Exception:
            show_popup("Error", "Invalid private key format.")
            return

        app = App.get_running_app()
        ws.save_wallet(app.user_data_dir, privkey_hex, address, pw)

        show_popup("Wallet Imported", f"Address:\n{address}")
        app.go_to_wallet_screen(address)


class UnlockScreen(Screen):
    """Shown when a wallet already exists: ask for the password."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=30, spacing=15)

        self.layout.add_widget(Label(text="Unlock Wallet", font_size=22, size_hint_y=None, height=50))
        self.address_label = Label(text="", size_hint_y=None, height=40)
        self.layout.add_widget(self.address_label)

        self.password_input = TextInput(hint_text="Password", password=True,
                                         multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.password_input)

        unlock_btn = Button(text="UNLOCK", size_hint_y=None, height=60)
        unlock_btn.bind(on_release=self.do_unlock)
        self.layout.add_widget(unlock_btn)

        self.layout.add_widget(Label())
        self.add_widget(self.layout)

    def on_pre_enter(self):
        app = App.get_running_app()
        try:
            addr = ws.peek_address(app.user_data_dir)
            self.address_label.text = f"Wallet: {addr}"
        except Exception:
            self.address_label.text = ""

    def do_unlock(self, *_):
        pw = self.password_input.text
        app = App.get_running_app()
        try:
            privkey_hex = ws.load_wallet(app.user_data_dir, pw)
        except ws.WrongPasswordOrTampered:
            show_popup("Error", "Wrong password.")
            return
        except Exception as e:
            show_popup("Error", f"Could not load wallet: {e}")
            return

        address = address_from_private_key(privkey_hex)
        app.private_key = privkey_hex
        app.go_to_wallet_screen(address)


class WalletScreen(Screen):
    """Main signing screen, only reachable after unlock/create/import."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation="vertical", padding=20, spacing=10)

        self.address_label = Label(text=f"Contract: {CONTRACT_ADDRESS}",
                                    size_hint_y=None, height=40)
        self.layout.add_widget(self.address_label)

        self.my_address_label = Label(text="", size_hint_y=None, height=40)
        self.layout.add_widget(self.my_address_label)

        self.recipient_input = TextInput(hint_text="Recipient address (0x...)",
                                          multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.recipient_input)

        self.payload_input = TextInput(hint_text="Payload hash (0x... 32 bytes)",
                                        multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.payload_input)

        self.metadata_input = TextInput(hint_text="Metadata (max 64 chars)",
                                         multiline=False, size_hint_y=None, height=50)
        self.layout.add_widget(self.metadata_input)

        sign_btn = Button(text="SIGN PRESENCE", size_hint_y=None, height=60)
        sign_btn.bind(on_release=self.do_sign)
        self.layout.add_widget(sign_btn)

        lock_btn = Button(text="LOCK WALLET", size_hint_y=None, height=50)
        lock_btn.bind(on_release=self.do_lock)
        self.layout.add_widget(lock_btn)

        self.result_label = Label(text="", size_hint_y=None, height=150)
        self.layout.add_widget(self.result_label)

        self.add_widget(self.layout)

    def on_pre_enter(self):
        app = App.get_running_app()
        if app.private_key:
            addr = address_from_private_key(app.private_key)
            self.my_address_label.text = f"Your address: {addr}"

    def do_sign(self, *_):
        app = App.get_running_app()
        if not app.private_key:
            show_popup("Error", "Wallet is locked.")
            return

        recipient = self.recipient_input.text.strip()
        payload = self.payload_input.text.strip()
        metadata = self.metadata_input.text.strip()

        if len(metadata) > 64:
            show_popup("Error", "Metadata must be 64 characters or fewer.")
            return

        try:
            result = sign_record(app.private_key, CHAIN_ID, recipient, payload, metadata)
            self.result_label.text = f"Signature:\n{result['signature']}"
        except Exception as e:
            show_popup("Error", f"Signing failed: {e}")

    def do_lock(self, *_):
        app = App.get_running_app()
        app.private_key = None
        self.result_label.text = ""
        self.manager.current = "unlock"


class SOSApp(App):
    private_key = None

    def build(self):
        os.makedirs(self.user_data_dir, exist_ok=True)

        sm = ScreenManager()
        sm.add_widget(WelcomeScreen(name="welcome"))
        sm.add_widget(CreateWalletScreen(name="create"))
        sm.add_widget(ImportWalletScreen(name="import"))
        sm.add_widget(UnlockScreen(name="unlock"))
        sm.add_widget(WalletScreen(name="wallet"))

        if ws.wallet_exists(self.user_data_dir):
            sm.current = "unlock"
        else:
            sm.current = "welcome"

        self.sm = sm
        return sm

    def go_to_wallet_screen(self, address):
        self.sm.current = "wallet"


if __name__ == "__main__":
    SOSApp().run()
