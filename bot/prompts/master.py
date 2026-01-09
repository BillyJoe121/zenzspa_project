from pathlib import Path


def _load_master_prompt():
    prompt_path = Path(__file__).with_name("master_prompt.txt")
    return prompt_path.read_text(encoding="utf-8")


MASTER_SYSTEM_PROMPT = _load_master_prompt()

__all__ = ["MASTER_SYSTEM_PROMPT"]
