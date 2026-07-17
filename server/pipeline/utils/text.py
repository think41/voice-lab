import re


def clean_model_text(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    return text.strip()


def normalize_for_speech(text: str) -> str:
    text = clean_model_text(text)
    return re.sub(r"\bthink\s*41\b", "Think forty one", text, flags=re.IGNORECASE)
