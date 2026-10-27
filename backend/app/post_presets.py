"""Tone and call-to-action presets offered in Create Post, with their writer instructions.

The client sends a preset ID; the server owns what each preset asks the writer to do. "other"
carries the user's own bounded text instead, which stays untrusted data like the topic.
"""

from typing import Literal

TONES = {
    "brand_voice": "Use the brand voice from the brand profile.",
    "professional": "Professional and authoritative.",
    "educational": "Explanatory and educational; make the idea easy to understand.",
    "friendly": "Friendly and conversational.",
    "storytelling": "Open with a short story or concrete example, without inventing facts.",
    "inspirational": "Inspirational and encouraging.",
    "humorous": "Light and humorous. Jokes and metaphors must not state new facts.",
    "concise": "Direct and concise.",
}

CTAS = {
    "none": "No call to action.",
    "comment": "Invite readers to share their experience or opinion in the comments.",
    "save": "Invite readers to save the post for later.",
    "tag": "Invite readers to tag someone this is relevant to.",
    "follow": "Invite readers to follow for more content on this topic.",
    "message": "Invite readers to send a private message.",
    "read_more": "Invite readers to read more at the link in the offer details.",
    "signup": "Invite readers to sign up for the offer in the offer details.",
    "contact": "Invite readers to get in touch.",
}

OTHER = "other"
# Static copies for request validation; tests keep them equal to the dictionaries.
ToneId = Literal[
    "brand_voice",
    "professional",
    "educational",
    "friendly",
    "storytelling",
    "inspirational",
    "humorous",
    "concise",
    "other",
]
CtaId = Literal[
    "none", "comment", "save", "tag", "follow", "message", "read_more", "signup", "contact", "other"
]
