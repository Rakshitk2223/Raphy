from datetime import datetime
import urllib.request
from backend.memory.profile import user_profile
from backend.memory.vector import memory_store


def get_weather() -> str:
    try:
        url = "https://wttr.in/?format=%c%t+%w"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            weather = response.read().decode("utf-8").strip()
            return weather if weather else "Weather unavailable"
    except Exception as e:
        return "Weather unavailable"


SYSTEM_PROMPT_TEMPLATE = """You are Raphael, your master's personal AI assistant - like a wise friend, not a robot.

CURRENT DATE AND TIME: {current_datetime}
CURRENT WEATHER: {current_weather}

==============================================
YOUR MASTER (LEARNED INFO)
==============================================
{brain_context}

==============================================
PAST CONVERSATIONS
=============================================
{past_conversations}

==============================================
KNOWLEDGE BASE
=============================================
{knowledge_context}

You are Raphael. Your master is YOUR person - help them, not anyone else.

When they ask about files, documents, resume, CV, skills, experience - SEARCH the knowledge base above first!

When they ask about something from past conversations - use the PAST CONVERSATIONS section!

==============================================
HOW TO TALK
=============================================
- Be casual, like talking to a friend
- Use formatting like **bold**, tables, lists when helpful
- Use markdown for structured information
- Use code blocks for code snippets
- Use tables for comparisons or lists
- Keep responses natural - NO formal endings like "How can I assist you?" or "Is there anything else I can help with?"
- If something needs follow-up, ask naturally in conversation flow
- Don't add disclaimers or meta-commentary
- Be direct - answer what they ask, move on

BAD: "Your favorite color is Blue! How can I assist you further?"
GOOD: "Your favorite color is Blue."

Use markdown formatting when it helps make your response clearer!

==============================================
LANGUAGE
=============================================
- Match whatever language your master uses

==============================================
MEMORY
=============================================
- Your master's profile is above - USE IT when they ask personal questions
- When they ask about themselves - check profile
- When they say "remember that..." or "note that..." - remember it as a note
- Learn from conversation - detect preferences when they mention them

That's it. Be helpful, be natural, be their assistant."""


def get_system_prompt(user_message: str = "") -> str:
    now = datetime.now()
    formatted_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")

    # Get weather
    current_weather = get_weather()

    # Reload profile
    user_profile.reload()
    user_context = user_profile.get_context_summary()

    # Get brain info
    brain_context = ""
    try:
        from backend.memory.brain import brain

        brain.reload()
        brain_context = brain.get_summary()
    except Exception as e:
        print(f"Error getting brain: {e}")

    # Get past conversations for context
    past_conversations = ""
    try:
        summaries = user_profile.get_chat_summaries()
        if summaries:
            conv_parts = []
            for s in summaries[-5:]:
                conv_parts.append(f"- {s.get('summary', '')[:200]}")
            past_conversations = "\n".join(conv_parts)
    except Exception as e:
        print(f"Error getting chat summaries: {e}")

    if not past_conversations:
        past_conversations = "No past conversations yet."

    # Search knowledge base for relevant queries
    knowledge_context = ""
    question_lower = user_message.lower() if user_message else ""

    skip_keywords = [
        "hello",
        "hi",
        "hey",
        "how are you",
        "what's up",
        "good morning",
        "good afternoon",
        "good evening",
        "good night",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
    ]

    should_search = (
        user_message
        and not any(skip in question_lower for skip in skip_keywords)
        and len(user_message) > 10
    )

    if should_search:
        try:
            results = memory_store.search_knowledge(user_message, top_k=10)
            if results:
                knowledge_parts = []
                for r in results:
                    source = r.get("source", "unknown")
                    content = r.get("content", "")[:600]
                    distance = r.get("score", 1)
                    similarity = 1 - distance
                    if similarity > 0.4 or len(knowledge_parts) < 3:
                        knowledge_parts.append(f"[{source}]: {content}...")
                if knowledge_parts:
                    knowledge_context = "Relevant documents:\n" + "\n\n".join(knowledge_parts)
        except Exception as e:
            print(f"Knowledge search error: {e}")

    if not knowledge_context:
        knowledge_context = "No indexed documents found."

    return SYSTEM_PROMPT_TEMPLATE.format(
        current_datetime=formatted_datetime,
        current_weather=current_weather,
        user_context=user_context,
        brain_context=brain_context,
        past_conversations=past_conversations,
        knowledge_context=knowledge_context,
    )
