from pathlib import Path


def _load_default_prompt():
    prompt_path = Path(__file__).with_name("default_prompt.txt")
    return prompt_path.read_text(encoding="utf-8")


DEFAULT_SYSTEM_PROMPT = _load_default_prompt()

__all__ = ["DEFAULT_SYSTEM_PROMPT"]
