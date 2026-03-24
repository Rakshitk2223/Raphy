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
            "about": "",
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

    def set_about(self, about: str):
        self._profile["about"] = about
        self._extract_preferences(about)
        self.save()

    def get_about(self) -> str:
        return self._profile.get("about", "")

    def _extract_preferences(self, text: str):
        import re

        if "preferences" not in self._profile:
            self._profile["preferences"] = {}

        text_lower = text.lower()

        name_patterns = [
            r"(?:my name is|i am|i'm)\s+([a-zA-Z]+)",
            r"name[:\s]+([a-zA-Z]+)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).strip().capitalize()
                if len(name) > 1 and name.lower() not in ["i", "am", "my"]:
                    self._profile["name"] = name
                    break

        color_match = re.search(
            r"(?:fav(?:ourite|rite)?\s+(?:color|colour)\s*(?:is|=|:)?\s*|color\s*(?:is|=|:)?\s*)(\w+)",
            text_lower,
        )
        if color_match:
            color = color_match.group(1).strip().capitalize()
            if len(color) > 2:
                self._profile["preferences"]["favorite_color"] = color

        car_match = re.search(
            r"(?:fav(?:ourite|rite)?\s+car\s*(?:is|=|:)?\s*|car\s*(?:is|=|:)?\s*)([a-zA-Z0-9\s]+?)(?:\.|,|$)",
            text_lower,
        )
        if car_match:
            car = car_match.group(1).strip()
            if len(car) > 2:
                self._profile["preferences"]["favorite_car"] = car

        job_patterns = [
            r"(?:i work (?:as|at)|i'm a|i am a|job[:\s]+|profession[:\s]+)([a-zA-Z0-9\s]+?)(?:\.|,|$)",
            r"(?:developer|engineer|designer|manager|teacher|doctor|artist|writer)",
        ]
        for pattern in job_patterns:
            match = re.search(pattern, text_lower)
            if match:
                job = match.group(1).strip() if match.lastindex else match.group(0).strip()
                if len(job) > 2 and len(job) < 50:
                    self._profile["preferences"]["job"] = job
                    break

        skill_patterns = [
            r"(?:i know|i work with|i use|i'm good at|skills?[:\s]+)([a-zA-Z0-9\s,]+?)(?:\.|,|$)",
        ]
        for pattern in skill_patterns:
            match = re.search(pattern, text_lower)
            if match:
                skills = match.group(1).strip()
                if len(skills) > 2 and len(skills) < 100:
                    self._profile["preferences"]["skills"] = skills
                    break

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

    def delete_note_by_content(self, content_substring: str) -> bool:
        notes = self._profile.get("notes", [])
        original_len = len(notes)
        self._profile["notes"] = [
            n for n in notes if content_substring.lower() not in n.get("content", "").lower()
        ]
        if len(self._profile["notes"]) != original_len:
            self.save()
            return True
        return False

    def update_from_chat(self, user_message: str, assistant_response: str = ""):
        """Learn from conversation - detect preferences automatically"""
        import re
        from datetime import datetime

        message_lower = user_message.lower()

        remember_patterns = [
            r"remember (?:that )?(.+)",
            r"note (?:that )?(.+)",
            r"keep in mind (?:that )?(.+)",
            r"dont forget (?:that )?(.+)",
            r"remember,? (.+)",
        ]

        for pattern in remember_patterns:
            match = re.search(pattern, message_lower)
            if match:
                remember_content = match.group(1).strip()
                if len(remember_content) > 3 and len(remember_content) < 200:
                    self.add_note(remember_content, "remember")
                    print(f"[MEMORY] Remembered: {remember_content}")
                    return

        color_patterns = [
            r"(?:fav(?:ourite|rite)?\s+(?:color|colour)\s+(?:is\s+)?|color\s+(?:is\s+)?)([a-zA-Z]+)",
            r"i like\s+(?:the\s+)?color\s+([a-zA-Z]+)",
            r"my favorite\s+color\s+(?:is\s+)?([a-zA-Z]+)",
        ]
        for pattern in color_patterns:
            match = re.search(pattern, message_lower)
            if match:
                color = match.group(1).strip()
                if len(color) > 2 and color not in ["and", "the", "this", "that", "like", "love"]:
                    self.set_preference("favorite_color", color.capitalize())

        car_patterns = [
            r"(?:fav(?:ourite|rite)?\s+car\s+(?:is\s+)?|car\s+(?:is\s+)?)(.+?)(?:\.|$|\?|!|,)",
            r"i like\s+(?:the\s+)?car\s+([a-zA-Z0-9\s]+?)(?:\.|,|$)",
            r"my favorite\s+car\s+(?:is\s+)?([a-zA-Z0-9\s]+?)(?:\.|,|$)",
        ]
        for pattern in car_patterns:
            match = re.search(pattern, message_lower)
            if match:
                car = match.group(1).strip()
                if len(car) > 2 and car not in ["and", "the", "this", "that", "like", "love"]:
                    self.set_preference("favorite_car", car)

        food_patterns = [
            r"(?:fav(?:ourite|rite)?\s+food\s+(?:is\s+)?)(.+?)(?:\.|$|\?|!|,)",
            r"i (?:love|like)\s+(?:to eat\s+)?(.+?)(?:\.|,|$)",
        ]
        for pattern in food_patterns:
            match = re.search(pattern, message_lower)
            if match:
                food = match.group(1).strip()
                if len(food) > 2 and len(food) < 50:
                    self.set_preference("favorite_food", food)

        hobby_patterns = [
            r"i (?:love|like|enjoy)\s+(?:playing|watching|doing)\s+(.+?)(?:\.|,|$)",
            r"my hobby\s+(?:is\s+)?(.+?)(?:\.|,|$)",
            r"in my free time i (.+?)(?:\.|,|$)",
        ]
        for pattern in hobby_patterns:
            match = re.search(pattern, message_lower)
            if match:
                hobby = match.group(1).strip()
                if len(hobby) > 2 and len(hobby) < 50:
                    self.set_preference("hobby", hobby)

        self.save()

    def add_chat_summary(self, summary: str):
        """Add a summary of past conversation"""
        if "chat_summaries" not in self._profile:
            self._profile["chat_summaries"] = []

        from datetime import datetime

        self._profile["chat_summaries"].append(
            {"summary": summary, "timestamp": datetime.now().isoformat()}
        )

        if len(self._profile["chat_summaries"]) > 10:
            self._profile["chat_summaries"] = self._profile["chat_summaries"][-10:]

        self.save()

    def get_chat_summaries(self) -> list:
        return self._profile.get("chat_summaries", [])

    def get_context_summary(self) -> str:
        """Get a summary of what the assistant knows about the user"""
        parts = []

        about = self.get_about()
        if about:
            parts.append(f"About the user: {about}")

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
