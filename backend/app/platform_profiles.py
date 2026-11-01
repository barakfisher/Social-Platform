"""How a post fits each platform, as the server tells the writer, reviewer and topic ideas.

Like the tone and call-to-action presets, the server owns these instructions; the client
sends only the platform ID. They are general to every brand: what one brand does on each
channel comes from its own Knowledge Base and Brand DNA, which take precedence.
"""

from typing import Literal

Platform = Literal["linkedin", "facebook"]

# What the writer (and the source check, for platform_fit) is told about the platform.
POST_STYLES: dict[str, str] = {
    "linkedin": (
        "LinkedIn, read by professionals, managers and decision makers. Favour authority, "
        "a professional insight, differentiation and practical value. The first two lines "
        "stand on their own as a sharp claim or question, because readers see only them "
        "before expanding the post. Short paragraphs of one to three sentences with a blank "
        "line between them; one main idea; short bullet lines (•) when they help. "
        "Professional and specific, often a first-person insight. End with a professional "
        "question or the call to action. Few emojis or none; at most three relevant hashtags "
        "on the last line, or none."
    ),
    "facebook": (
        "Facebook, read by a broad community and personal network. Favour personal "
        "connection, trust, meaning, and comments and shares. Open with a story, a moment or "
        "a personal question. Conversational and flowing, with short paragraphs. Warm and "
        "personal, speaking to the reader directly. End with a question that invites readers "
        "to share their own experience in the comments, or the call to action. Emojis in "
        "moderation; no hashtags."
    ),
}

# The roles a post may play, in the order this platform prefers them for topic ideas.
IDEA_ROLES: dict[str, list[str]] = {
    "linkedin": [
        "differentiation (challenging a common belief)",
        "professional authority",
        "practical value",
        "reaching managers and senior leaders",
        "call to sign up",
    ],
    "facebook": [
        "personal connection",
        "trust and meaning",
        "curiosity and reaching a new audience",
        "practical value",
        "call to sign up",
    ],
}
