from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from sos_core import sign_record, CONTRACT_ADDRESS

CHAIN_ID = 1  # set to your target chain id


class SOSWallet(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=20, spacing=10, **kwargs)

        self.address_label = Label(text=f"Contract: {CONTRACT_ADDRESS}")
        self.add_widget(self.address_label)

        self.recipient_input = TextInput(hint_text="Recipient address (0x...)")
        self.add_widget(self.recipient_input)

        self.payload_input = TextInput(hint_text="Payload hash (0x... 32 bytes)")
        self.add_widget(self.payload_input)

        self.metadata_input = TextInput(hint_text="Metadata (max 64 chars)")
        self.add_widget(self.metadata_input)

        sign_btn = Button(text="SIGN PRESENCE", size_hint_y=None, height=60)
        sign_btn.bind(on_release=self.do_sign)
        self.add_widget(sign_btn)

        self.result_label = Label(text="")
        self.add_widget(self.result_label)

        self.private_key = None  # loaded from encrypted storage, never hardcoded

    def do_sign(self, *_):
        if not self.private_key:
            self.result_label.text = "No wallet loaded yet."
            return
        try:
            result = sign_record(
                self.private_key,
                CHAIN_ID,
                self.recipient_input.text.strip(),
                self.payload_input.text.strip(),
                self.metadata_input.text.strip(),
            )
            self.result_label.text = f"Signature:\n{result['signature']}"
        except Exception as e:
            self.result_label.text = f"Error: {e}"


class SOSApp(App):
    def build(self):
        return SOSWallet()


if __name__ == "__main__":
    SOSApp().run()
