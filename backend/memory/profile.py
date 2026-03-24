import json
from pathlib import Path
from typing import Optional

from backend.config import settings


class UserProfile:
    def __init__(self):
        self.profile_path = settings.memory_dir / "profile.json"
        self._profile = None
        self.load()

    def load(self):
        if self.profile_path.exists():
            try:
                self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._create_default()
        else:
            self._create_default()

    def reload(self):
        """Force reload from disk - call this before generating prompt"""
        self.load()

    def _create_default(self):
        self._profile = {
            "name": None,
            "created_at": "2026-03-24T00:00:00Z",
            "preferences": {},
            "goals": [],
            "notes": [],
            "learned_patterns": {},
            "chat_summaries": [],
        }
        self.save()

    def save(self):
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(
            json.dumps(self._profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @property
    def data(self) -> dict:
        return self._profile

    def set_name(self, name: str):
        self._profile["name"] = name
        self.save()

    def get_name(self) -> Optional[str]:
        return self._profile.get("name")

    def set_preference(self, key: str, value: str):
        if "preferences" not in self._profile:
            self._profile["preferences"] = {}
        self._profile["preferences"][key] = value
        self.save()

    def get_preference(self, key: str) -> Optional[str]:
        return self._profile.get("preferences", {}).get(key)

    def get_all_preferences(self) -> dict:
        return self._profile.get("preferences", {})

    def add_note(self, content: str, category: str = "general"):
        if "notes" not in self._profile:
            self._profile["notes"] = []
        self._profile["notes"].append(
            {"content": content, "category": category, "created_at": "2026-03-24T00:00:00Z"}
        )
        self.save()

    def get_notes(self, category: Optional[str] = None) -> list:
        notes = self._profile.get("notes", [])
        if category:
            return [n for n in notes if n.get("category") == category]
        return notes

    def delete_note(self, index: int) -> bool:
        notes = self._profile.get("notes", [])
        if 0 <= index < len(notes):
            notes.pop(index)
            self._profile["notes"] = notes
            self.save()
            return True
        return False

    def update_from_chat(self, user_message: str, assistant_response: str):
        """Learn from conversation - detect preferences automatically"""
        import re

        message_lower = user_message.lower()

        # Pattern 1: "is Blue" after "color" or "colour"
        color_match = re.search(
            r"(?:fav(?:ourite|rite)?\s+(?:color|colour)\s+(?:is\s+)?|color\s+(?:is\s+)?)([a-zA-Z]+)",
            message_lower,
        )
        if color_match:
            color = color_match.group(1).strip()
            if len(color) > 2 and color not in ["and", "the", "this", "that"]:
                self.set_preference("favorite_color", color.capitalize())

        # Pattern 2: "is Porsche 911 GT3 RS" - capture full car name
        car_match = re.search(
            r"(?:fav(?:ourite|rite)?\s+car\s+(?:is\s+)?|car\s+(?:is\s+)?)(.+?)(?:\.|$|\?|!|,)",
            message_lower,
        )
        if car_match:
            car = car_match.group(1).strip()
            if len(car) > 2 and car not in ["and", "the", "this", "that"]:
                self.set_preference("favorite_car", car)

        # Also check for "its [car name]" pattern
        if "its" in message_lower and "car" in message_lower:
            its_match = re.search(r"its\s+(.+?)(?:\.|$|\?|!|,)", message_lower)
            if its_match:
                car = its_match.group(1).strip()
                if len(car) > 2:
                    self.set_preference("favorite_car", car)

        self.save()

    def get_context_summary(self) -> str:
        """Get a summary of what the assistant knows about the user"""
        parts = []

        name = self.get_name()
        if name:
            parts.append(f"User's name: {name}")

        prefs = self.get_all_preferences()
        if prefs:
            prefs_str = ", ".join([f"{k}: {v}" for k, v in prefs.items()])
            parts.append(f"Preferences: {prefs_str}")

        notes = self.get_notes()
        if notes:
            parts.append(f"Notes ({len(notes)}): {len(notes)} items stored")

        if not parts:
            return "I don't know much about the user yet. Ask them questions to learn!"

        return " | ".join(parts)

    def clear(self):
        self._create_default()


user_profile = UserProfile()
