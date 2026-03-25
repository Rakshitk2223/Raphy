import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import httpx

from backend.config import settings


EXTRACTION_PROMPT = """You are a smart memory assistant. Analyze the conversation to determine what action to take with the user's memories.

EXISTING MEMORY DATA:
{memory_context}

CONVERSATION:
{conversation}

Your task is to understand the user's INTENT and extract the appropriate action.

RETURN a JSON object with this EXACT structure:
{{
    "action": "CREATE|UPDATE|DELETE|QUERY|NONE",
    "target": "preference|fact|reminder|skill|info|any",
    "item_key": "the key being modified (e.g., 'favorite_color', 'dinner')",
    "item_value": "the new value (for CREATE/UPDATE)",
    "old_value": "the previous value if changing/updating (for UPDATE)",
    "reminder_time": "time mentioned (for reminders only, e.g., '7:30 PM', 'tomorrow 3pm')",
    "clarification_needed": true|false,
    "clarification_question": "question to ask if similar but potentially different item exists",
    "response_message": "what you should tell the user after the action"
}}

ACTION DEFINITIONS:
- CREATE: Adding completely new info/reminder
- UPDATE: Changing existing info (acknowledge old value)
- DELETE: Removing info ("forget", "remove", "delete")
- QUERY: User asking what they have saved
- NONE: No memory action needed

GUIDELINES:
1. For UPDATE with different value: Set old_value and response_message like "I remember your favorite color was [old], I'll update it to [new]"
2. For CLARIFICATION needed: Set clarification_needed=true and provide a question like "You already have dinner at 7:30 PM. Is this the same dinner or a different one?"
3. For DELETE: Set item_key and response_message like "Okay, I've forgotten that about you"
4. For QUERY: Set response_message asking what user wants to know
5. For CREATE: Just add the new info normally
6. If no memory action: action = "NONE"

KEY DETECTION:
- Preferences: favorite_color, favorite_food, favorite_car, favorite_movie, etc.
- Facts: personal details, work info, education, hobbies
- Reminders: meetings, tasks, events with times

Examples:
- "My favorite color is now red" → action=UPDATE, target=preference, item_key=favorite_color, item_value=red, old_value=blue, response_message="I remember your favorite color was blue, I'll update it to red"
- "Remind me about dinner at 7:30" → action=CREATE, target=reminder, item_key=dinner, item_value=dinner at 7:30 PM, reminder_time=7:30 PM
- "Forget my age" → action=DELETE, target=info, item_key=age, response_message="Okay, I've removed that information"
- "What do you know about me?" → action=QUERY, target=any, response_message="I know..."

Now analyze the conversation and return ONLY valid JSON:"""


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

    def get_preference(self, key: str) -> Optional[str]:
        prefs = self._data.get("preferences", {})
        key_lower = key.lower().replace("favourite", "favorite")
        for k, v in prefs.items():
            if k.lower().replace("favourite", "favorite") == key_lower:
                return v
        return None

    def get_memory_context(self) -> str:
        parts = []

        prefs = self._data.get("preferences", {})
        if prefs:
            parts.append("PREFERENCES:")
            for k, v in prefs.items():
                parts.append(f"  - {k}: {v}")

        info = self._data.get("info", {})
        if info:
            parts.append("INFO:")
            for k, v in info.items():
                parts.append(f"  - {k}: {v}")

        facts = self._data.get("learned_facts", [])
        if facts:
            parts.append("FACTS:")
            for f in facts[-10:]:
                parts.append(f"  - {f.get('fact', '')} ({f.get('category', '')})")

        from backend.memory.profile import user_profile

        reminders = user_profile.get_notes("reminder")
        if reminders:
            parts.append("REMINDERS:")
            for r in reminders:
                parts.append(f"  - {r.get('content', '')}")

        if not parts:
            return "No existing memory found."

        return "\n".join(parts)

    def query_memory(self, query: str = "all") -> str:
        parts = []

        prefs = self._data.get("preferences", {})
        if prefs:
            parts.append("Preferences:")
            for k, v in prefs.items():
                parts.append(f"  - {k}: {v}")

        info = self._data.get("info", {})
        if info:
            parts.append("Personal Info:")
            for k, v in info.items():
                parts.append(f"  - {k}: {v}")

        facts = self._data.get("learned_facts", [])
        if facts:
            parts.append("Facts I know about you:")
            for f in facts:
                parts.append(f"  - {f.get('fact', '')}")

        from backend.memory.profile import user_profile

        reminders = user_profile.get_notes("reminder")
        if reminders:
            parts.append("Your Reminders:")
            for r in reminders:
                parts.append(f"  - {r.get('content', '')}")

        if not parts:
            return "I don't have any information about you yet. Tell me something about yourself!"

        return "\n".join(parts)

    def update_fact(self, old_fact: str, new_fact: str):
        facts = self._data.get("learned_facts", [])
        for f in facts:
            if old_fact.lower() in f.get("fact", "").lower():
                f["fact"] = new_fact
                f["updated_at"] = datetime.now().isoformat()
                self.save()
                return True
        return False

    def delete_fact(self, fact_text: str):
        facts = self._data.get("learned_facts", [])
        original_len = len(facts)
        self._data["learned_facts"] = [
            f for f in facts if fact_text.lower() not in f.get("fact", "").lower()
        ]
        if len(self._data["learned_facts"]) != original_len:
            self.save()
            return True
        return False

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

    def get_core_profile(self) -> dict:
        """Load the core profile - this is permanent and never changes"""
        core_path = self.brain_path.parent / "core_profile.json"
        if core_path.exists():
            try:
                return json.loads(core_path.read_text(encoding="utf-8"))
            except:
                pass
        return {}

    def get_core_summary(self) -> str:
        """Get core profile as a string for system prompt"""
        core = self.get_core_profile()
        if not core:
            return ""

        parts = []

        master = core.get("master", {})
        if master:
            name = master.get("name", "Unknown")
            nickname = master.get("nickname", "")
            gaming = master.get("gaming_name", "")

            core_info = f"Master's name: {name}"
            if nickname:
                core_info += f" (also goes by {nickname})"
            if gaming:
                core_info += f", Gaming name: {gaming}"
            parts.append(core_info)

        role = core.get("role", {})
        if role:
            parts.append(f"Your role: {role.get('title', 'AI Assistant')}")

        important = core.get("important", [])
        if important:
            parts.append(f"Always remember: {'; '.join(important[:3])}")

        return " | ".join(parts)

    def get_summary(self) -> str:
        parts = []

        # FIRST: Always include core profile (most important!)
        core_summary = self.get_core_summary()
        if core_summary:
            parts.append(f"CORE MEMORY: {core_summary}")

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

    memory_context = brain.get_memory_context()

    prompt = EXTRACTION_PROMPT.format(memory_context=memory_context, conversation=conversation)

    try:
        print(f"[BRAIN] Starting smart extraction for {len(messages)} messages")

        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/generate", json=payload)

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "").strip()

                print(f"[BRAIN] Raw LLM response: {response_text[:800]}")

                json_match = re.search(r"\{[\s\S]*\}", response_text)
                if json_match:
                    try:
                        extracted = json.loads(json_match.group())
                        print(f"[BRAIN] Smart extraction result: {extracted}")

                        action = extracted.get("action", "NONE")
                        target = extracted.get("target", "any")
                        item_key = extracted.get("item_key", "")
                        item_value = extracted.get("item_value", "")
                        old_value = extracted.get("old_value", "")
                        reminder_time = extracted.get("reminder_time", "")
                        clarification = extracted.get("clarification_needed", False)
                        clarify_question = extracted.get("clarification_question", "")
                        response_msg = extracted.get("response_message", "")

                        result_message = None

                        if action == "CREATE":
                            if target in ["preference", "info"]:
                                brain.add_preference(item_key, item_value)
                                result_message = (
                                    response_msg
                                    or f"Okay, I've noted that your {item_key} is {item_value}"
                                )
                            elif target == "fact":
                                brain.add_fact(item_value, "general")
                                result_message = (
                                    response_msg or f"Okay, I've remembered: {item_value}"
                                )
                            elif target == "reminder":
                                from backend.memory.profile import user_profile

                                reminder_text = item_value
                                if reminder_time:
                                    reminder_text = f"{item_value} at {reminder_time}"
                                user_profile.add_note(reminder_text, "reminder")
                                result_message = response_msg or f"Reminder set: {reminder_text}"

                            brain.save()
                            brain.sync_to_profile()
                            print(f"[BRAIN] CREATE: {item_key} = {item_value}")

                        elif action == "UPDATE":
                            if target in ["preference", "info"]:
                                old = brain.get_preference(item_key) or old_value or "that"
                                brain.add_preference(item_key, item_value)
                                result_message = (
                                    response_msg
                                    or f"I remember your {item_key} was {old}, I've updated it to {item_value}"
                                )
                            elif target == "fact":
                                brain.update_fact(item_key, item_value)
                                result_message = response_msg or f"Updated: {item_value}"

                            brain.save()
                            brain.sync_to_profile()
                            print(f"[BRAIN] UPDATE: {item_key} = {item_value} (was {old_value})")

                        elif action == "DELETE":
                            if target in ["preference", "info"]:
                                brain.delete_info(item_key)
                                brain.delete_preference(item_key)
                            elif target == "fact":
                                brain.delete_fact(item_key)
                            elif target == "reminder":
                                from backend.memory.profile import user_profile

                                user_profile.delete_note_by_content(item_key)

                            brain.save()
                            brain.sync_to_profile()
                            result_message = response_msg or f"Okay, I've removed that information"
                            print(f"[BRAIN] DELETE: {item_key}")

                        elif action == "QUERY":
                            result_message = response_msg or brain.query_memory(item_key)
                            print(f"[BRAIN] QUERY: {item_key}")

                        elif clarification:
                            result_message = clarify_question or "Could you clarify?"
                            print(f"[BRAIN] CLARIFICATION NEEDED: {clarify_question}")

                        if result_message:
                            return {"success": True, "message": result_message, "action": action}

                        return {"success": False, "action": "NONE"}

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
