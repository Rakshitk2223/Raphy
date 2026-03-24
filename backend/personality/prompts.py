from datetime import datetime
from backend.memory.profile import user_profile
from backend.memory.vector import memory_store

SYSTEM_PROMPT_TEMPLATE = """You are Raphael, your master's personal AI assistant - like a wise friend, not a robot.

CURRENT DATE AND TIME: {current_datetime}

==============================================
YOUR MASTER
==============================================
{user_context}

==============================================
KNOWLEDGE BASE
==============================================
{knowledge_context}

You are Raphael. Your master is YOUR person - help them, not anyone else.

When they ask about files, documents, resume, CV, skills, experience - SEARCH the knowledge base above first!

==============================================
HOW TO TALK
==============================================
- Be casual, like talking to a friend
- Keep responses natural - NO formal endings like "How can I assist you?" or "Is there anything else I can help with?"
- If something needs follow-up, ask naturally in conversation flow
- Don't add disclaimers or meta-commentary
- Be direct - answer what they ask, move on

BAD: "Your favorite color is Blue! How can I assist you further?"
GOOD: "Your favorite color is Blue."

==============================================
LANGUAGE
==============================================
- Match whatever language your master uses

==============================================
MEMORY
==============================================
- Your master's profile is above - USE IT when they ask personal questions
- When they ask about themselves - check profile

That's it. Be helpful, be natural, be their assistant."""


def get_system_prompt(user_message: str = "") -> str:
    now = datetime.now()
    formatted_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p")

    # Reload profile
    user_profile.reload()
    user_context = user_profile.get_context_summary()

    # Search knowledge base if question is about files/documents
    knowledge_context = ""
    question_lower = user_message.lower() if user_message else ""
    file_keywords = [
        "resume",
        "cv",
        "skills",
        "experience",
        "education",
        "document",
        "file",
        "about me",
        "what do you know",
    ]

    if any(keyword in question_lower for keyword in file_keywords):
        try:
            results = memory_store.search_knowledge(user_message, top_k=3)
            if results:
                knowledge_parts = []
                for r in results:
                    source = r.get("source", "unknown")
                    content = r.get("content", "")[:300]
                    knowledge_parts.append(f"[{source}]: {content}...")
                knowledge_context = "Relevant documents:\n" + "\n\n".join(knowledge_parts)
        except Exception as e:
            print(f"Knowledge search error: {e}")

    if not knowledge_context:
        knowledge_context = "No indexed documents found."

    return SYSTEM_PROMPT_TEMPLATE.format(
        current_datetime=formatted_datetime,
        user_context=user_context,
        knowledge_context=knowledge_context,
    )
