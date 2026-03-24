import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import httpx

from backend.config import settings


EXTRACTION_PROMPT = """You are a user information extraction system. Analyze the conversation and extract information about the user.

IMPORTANT: Separate information into TWO categories:

1. PERSONAL INFO (permanent facts about the user):
   - name, height, age, location, bio
   - skills, job, company, role
   - preferences, favorites, hobbies
   - education, certifications
   - anything the user says about themselves

2. REMINDERS/SCHEDULES (actionable, time-sensitive):
   - meetings, appointments, calls
   - deadlines, dates to remember
   - tasks, todo items
   - anything the user wants to be reminded about
   - words like "remind me", "remember to", "don't forget", "at 3pm", "tomorrow", "next week"

Return a JSON object with this EXACT structure:
{{
    "personal": {{
        "info": {{"key": "value"}},
        "preferences": {{"key": "value"}},
        "skills": ["skill1"],
        "facts": [{{"fact": "fact", "category": "category"}}]
    }},
    "reminders": ["reminder text 1", "reminder text 2"]
}}

Categories for facts: personal, work, education, hobby, health, social, other

IMPORTANT:
- If user says "remind me..." or "remember to..." or mentions dates/times → add to reminders
- If user mentions personal facts about themselves → add to personal
- Only extract information explicitly stated, do not infer

Conversation:
{conversation}

JSON:"""


class Brain:
    def __init__(self):
        self.brain_path = settings.memory_dir / "brain.json"
        self._data = None
        self.load()

    def load(self):
        if self.brain_path.exists():
            try:
                self._data = json.loads(self.brain_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._create_default()
        else:
            self._create_default()

        self._consolidate_from_profile()
        self.cleanup_duplicates()

    def reload(self):
        self.load()

    def _consolidate_from_profile(self):
        profile_path = self.brain_path.parent / "profile.json"
        if not profile_path.exists():
            return

        try:
            profile_data = json.loads(profile_path.read_text(encoding="utf-8"))

            if not profile_data:
                return

            merged = False

            prefs = profile_data.get("preferences", {})
            if prefs and isinstance(prefs, dict):
                for k, v in prefs.items():
                    if k not in self._data.get("preferences", {}):
                        if "preferences" not in self._data:
                            self._data["preferences"] = {}
                        self._data["preferences"][k] = v
                        merged = True

            about = profile_data.get("about")
            if about and not self._data.get("info", {}).get("about"):
                if "info" not in self._data:
                    self._data["info"] = {}
                self._data["info"]["about"] = about
                merged = True

            notes = profile_data.get("notes", [])
            if notes and not self._data.get("learned_facts"):
                for note in notes:
                    content = note.get("content", "")
                    category = note.get("category", "general")
                    if content and not any(
                        f.get("fact") == content for f in self._data.get("learned_facts", [])
                    ):
                        if "learned_facts" not in self._data:
                            self._data["learned_facts"] = []
                        self._data["learned_facts"].append(
                            {
                                "fact": content,
                                "category": category,
                                "learned_at": note.get("created_at", datetime.now().isoformat()),
                            }
                        )
                        merged = True

            if merged:
                self.deduplicate_preferences()
                self.save()
                print(f"[BRAIN] Consolidated data from profile.json")
        except Exception as e:
            print(f"[BRAIN] Failed to consolidate profile: {e}")

    def _create_default(self):
        self._data = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "info": {},
            "learned_facts": [],
            "preferences": {},
            "skills": [],
            "projects": [],
            "experience": [],
            "education": [],
            "goals": [],
            "personal": {},
        }
        self.save()

    def save(self):
        self.brain_path.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = datetime.now().isoformat()
        self.brain_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @property
    def data(self) -> dict:
        return self._data

    def update_info(self, key: str, value: str):
        if "info" not in self._data:
            self._data["info"] = {}
        self._data["info"][key] = value
        self.save()

    def add_fact(self, fact: str, category: str = "general"):
        if "learned_facts" not in self._data:
            self._data["learned_facts"] = []

        for existing in self._data["learned_facts"]:
            if existing.get("fact") == fact:
                return

        self._data["learned_facts"].append(
            {"fact": fact, "category": category, "learned_at": datetime.now().isoformat()}
        )
        self.save()

    def add_skill(self, skill: str):
        if "skills" not in self._data:
            self._data["skills"] = []

        skill_lower = skill.lower()
        for existing in self._data["skills"]:
            if existing.lower() == skill_lower:
                return

        self._data["skills"].append(skill)
        self.save()

    def add_preference(self, key: str, value: str):
        if "preferences" not in self._data:
            self._data["preferences"] = {}

        key_lower = key.lower().replace("favourite", "favorite")
        existing_key = None
        for k in self._data["preferences"]:
            if k.lower().replace("favourite", "favorite") == key_lower:
                existing_key = k
                break

        if existing_key:
            if self._data["preferences"][existing_key].lower() != value.lower():
                self._data["preferences"][existing_key] = value
                self.save()
        else:
            normalized_key = key.replace("favourite", "favorite")
            self._data["preferences"][normalized_key] = value
            self.save()

    def deduplicate_preferences(self):
        if "preferences" not in self._data:
            return

        normalized = {}
        for k, v in self._data["preferences"].items():
            key_lower = k.lower().replace("favourite", "favorite")
            if key_lower not in normalized:
                normalized[key_lower] = v
            elif normalized[key_lower].lower() != v.lower():
                normalized[key_lower] = v

        self._data["preferences"] = normalized
        self.save()

    def deduplicate_facts(self):
        if "learned_facts" not in self._data:
            return

        seen = set()
        unique_facts = []
        for fact in self._data["learned_facts"]:
            fact_text = fact.get("fact", "").lower()
            if fact_text and fact_text not in seen:
                seen.add(fact_text)
                unique_facts.append(fact)

        if len(unique_facts) != len(self._data["learned_facts"]):
            self._data["learned_facts"] = unique_facts
            self.save()

    def cleanup_duplicates(self):
        self.deduplicate_preferences()
        self.deduplicate_facts()

    def add_project(self, project: dict):
        if "projects" not in self._data:
            self._data["projects"] = []
        self._data["projects"].append(project)
        self.save()

    def add_experience(self, experience: dict):
        if "experience" not in self._data:
            self._data["experience"] = []
        self._data["experience"].append(experience)
        self.save()

    def add_education(self, education: dict):
        if "education" not in self._data:
            self._data["education"] = []
        self._data["education"].append(education)
        self.save()

    def add_goal(self, goal: str):
        if "goals" not in self._data:
            self._data["goals"] = []

        goal_lower = goal.lower()
        for existing in self._data["goals"]:
            if existing.lower() == goal_lower:
                return

        self._data["goals"].append(goal)
        self.save()

    def set_personal(self, key: str, value):
        if "personal" not in self._data:
            self._data["personal"] = {}
        self._data["personal"][key] = value
        self.save()

    def get_personal(self, key: str):
        return self._data.get("personal", {}).get(key)

    def get_all_preferences(self) -> dict:
        return self._data.get("preferences", {})

    def get_skills(self) -> list:
        return self._data.get("skills", [])

    def get_learned_facts(self) -> list:
        return self._data.get("learned_facts", [])

    def update_info(self, key: str, value: str):
        if "info" not in self._data:
            self._data["info"] = {}

        key_lower = key.lower()
        existing_key = None

        for k in self._data["info"]:
            if k.lower() == key_lower:
                existing_key = k
                break

        if existing_key:
            if self._data["info"][existing_key] != value:
                self._data["info"][existing_key] = value
                self.save()
        else:
            self._data["info"][key] = value
            self.save()

    def delete_info(self, key: str) -> bool:
        if "info" not in self._data:
            return False

        key_lower = key.lower()
        for k in list(self._data["info"].keys()):
            if k.lower() == key_lower:
                del self._data["info"][k]
                self.save()
                return True
        return False

    def delete_preference(self, key: str) -> bool:
        if "preferences" not in self._data:
            return False

        key_lower = key.lower()
        for k in list(self._data["preferences"].keys()):
            if k.lower() == key_lower:
                del self._data["preferences"][k]
                self.save()
                return True
        return False

    def delete_skill(self, skill: str) -> bool:
        if "skills" not in self._data:
            return False

        skill_lower = skill.lower()
        for s in list(self._data["skills"]):
            if s.lower() == skill_lower:
                self._data["skills"].remove(s)
                self.save()
                return True
        return False

    def clear_facts(self):
        self._data["learned_facts"] = []
        self.save()

    def get_summary(self) -> str:
        parts = []

        info = self._data.get("info", {})
        if info:
            info_parts = [f"{k}: {v}" for k, v in info.items()]
            parts.append(f"User info: {', '.join(info_parts)}")

        prefs = self._data.get("preferences", {})
        if prefs:
            prefs_parts = [f"{k}: {v}" for k, v in prefs.items()]
            parts.append(f"Preferences: {', '.join(prefs_parts)}")

        skills = self._data.get("skills", [])
        if skills:
            parts.append(f"Skills: {', '.join(skills)}")

        facts = self._data.get("learned_facts", [])
        if facts:
            recent = [f["fact"] for f in facts[-5:]]
            parts.append(f"Recent facts: {', '.join(recent)}")

        if not parts:
            return "No information learned yet."

        return " | ".join(parts)

    def export(self, path: Path):
        path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_data(self, path: Path):
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
                self.save()
                return True
            except:
                return False
        return False

    def sync_to_profile(self):
        profile_path = self.brain_path.parent / "profile.json"
        if not profile_path.exists():
            return

        try:
            profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
            merged = False

            prefs = self._data.get("preferences", {})
            if prefs and isinstance(prefs, dict):
                if "preferences" not in profile_data:
                    profile_data["preferences"] = {}
                for k, v in prefs.items():
                    if k not in profile_data["preferences"]:
                        profile_data["preferences"][k] = v
                        merged = True

            if merged:
                profile_path.write_text(
                    json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"[BRAIN] Synced brain data to profile.json")
        except Exception as e:
            print(f"[BRAIN] Failed to sync to profile: {e}")


brain = Brain()


async def extract_and_learn(messages: list[dict]):
    print(f"[BRAIN] extract_and_learn called with {len(messages) if messages else 0} messages")

    if not messages or len(messages) < 2:
        print("[BRAIN] Not enough messages for extraction")
        return

    recent_messages = []
    for msg in messages[-6:]:
        if msg.get("role") in ["user", "assistant"]:
            recent_messages.append(msg)

    if not recent_messages:
        print("[BRAIN] No user/assistant messages found")
        return

    print(f"[BRAIN] Processing {len(recent_messages)} recent messages")

    conversation = "\n".join(
        [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in recent_messages]
    )

    try:
        print(f"[BRAIN] Starting extraction for {len(messages)} messages")

        payload = {
            "model": settings.ollama_model,
            "prompt": EXTRACTION_PROMPT.format(conversation=conversation),
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "").strip()

                print(f"[BRAIN] Raw LLM response: {response_text[:500]}")

                json_match = re.search(r"\{[\s\S]*\}", response_text)
                if json_match:
                    try:
                        extracted = json.loads(json_match.group())
                        print(f"[BRAIN] Extracted data: {extracted}")

                        learned_something = False

                        personal = extracted.get("personal", {})
                        if "info" in personal:
                            for key, value in personal["info"].items():
                                brain.update_info(key, value)
                                learned_something = True

                        if "preferences" in personal:
                            for key, value in personal["preferences"].items():
                                brain.add_preference(key, value)
                                learned_something = True

                        if "skills" in personal:
                            for skill in personal["skills"]:
                                brain.add_skill(skill)
                                learned_something = True

                        if "facts" in personal:
                            for fact in personal["facts"]:
                                brain.add_fact(fact.get("fact", ""), fact.get("category", "other"))
                                learned_something = True

                        reminders = extracted.get("reminders", [])
                        if reminders:
                            for reminder in reminders:
                                if reminder:
                                    from backend.memory.profile import user_profile

                                    user_profile.add_note(reminder, "reminder")
                                    learned_something = True

                        if learned_something:
                            print(
                                f"[BRAIN] Learned: personal={len(personal.get('facts', []))} facts, reminders={len(reminders)}"
                            )
                            brain.sync_to_profile()
                        else:
                            print("[BRAIN] No new information to learn")
                        return learned_something
                    except json.JSONDecodeError as e:
                        print(f"[BRAIN] Failed to parse extraction JSON: {e}")
                else:
                    print(f"[BRAIN] No JSON found in response")
            else:
                print(f"[BRAIN] LLM returned status {response.status_code}")
    except Exception as e:
        print(f"[BRAIN] Extraction failed: {e}")
        import traceback

        traceback.print_exc()
