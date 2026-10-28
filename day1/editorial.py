"""Copy limits retain all fifteen players and never alter numerical evidence."""
import re


def compact_review_segments(segments, max_words=500):
    def count():
        return sum(len(re.findall(r"\b[\w'-]+\b", s["text"])) for s in segments)
    if count() <= max_words:
        return segments
    # Keep complete sentences, every player, captain and closing message.
    for s in segments:
        if s.get("player_id"):
            sentences = re.split(r"(?<=[.!?])\s+", s["text"])
            s["text"] = " ".join(sentences[:2])
    if count() > max_words:
        for s in segments:
            if s.get("player_id"):
                s["text"] = re.split(r"(?<=[.!?])\s+", s["text"])[0]
    if count() > max_words:
        optional = {"quietest_review", "hero_review"}
        segments[:] = [s for s in segments if s["id"] not in optional]
    if count() > max_words:
        raise RuntimeError("Review cannot fit its copy limit without losing a player or essential context")
    return segments
