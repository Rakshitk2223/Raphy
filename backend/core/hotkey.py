import asyncio
import threading
from typing import Callable, Optional
from pynput import keyboard


class HotkeyManager:
    def __init__(self):
        self.listener: Optional[keyboard.Listener] = None
        self.callbacks: dict[str, Callable] = {}
        self.pressed_keys: set = set()
        self._running = False

    def register(self, hotkey_name: str, callback: Callable):
        self.callbacks[hotkey_name] = callback

    def _on_press(self, key):
        try:
            if key == keyboard.Key.alt_l:
                self.pressed_keys.add("alt_l")
            elif key == keyboard.Key.enter:
                self.pressed_keys.add("enter")

                if "alt_l" in self.pressed_keys:
                    if "voice_toggle" in self.callbacks:
                        threading.Thread(
                            target=self.callbacks["voice_toggle"],
                            daemon=True,
                        ).start()
        except Exception as e:
            print(f"Hotkey error: {e}")

    def _on_release(self, key):
        try:
            if key == keyboard.Key.alt_l:
                self.pressed_keys.discard("alt_l")
            elif key == keyboard.Key.enter:
                self.pressed_keys.discard("enter")
        except Exception:
            pass

    def start(self):
        if self._running:
            return

        self._running = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()
        print("Hotkey listener started (Left Alt+Enter for voice)")

    def stop(self):
        self._running = False
        if self.listener:
            self.listener.stop()
            self.listener = None


hotkey_manager = HotkeyManager()
