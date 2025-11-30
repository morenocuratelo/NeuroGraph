"""
Prompt management utilities.

Loads system prompts from `prompts.json` and formats them with optional
keyword arguments for runtime interpolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Mapping


DEFAULT_PROMPTS_PATH = Path(__file__).with_name("prompts.json")


class PromptManager:
    def __init__(self, prompts_path: Path | str | None = None) -> None:
        self.prompts_path = Path(prompts_path) if prompts_path else DEFAULT_PROMPTS_PATH
        self._prompts = self._load_prompts()

    def _load_prompts(self) -> Dict[str, str]:
        if not self.prompts_path.exists():
            raise FileNotFoundError(f"Prompts file not found: {self.prompts_path}")

        with self.prompts_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, Mapping):
            raise ValueError("Prompts file must contain a JSON object")

        return {str(k): str(v) for k, v in raw.items()}

    def available(self) -> Iterable[str]:
        return self._prompts.keys()

    def get(self, name: str) -> str:
        try:
            return self._prompts[name]
        except KeyError as exc:
            raise KeyError(f"Prompt '{name}' not found") from exc

    def format(self, name: str, **kwargs) -> str:
        prompt = self.get(name)
        return prompt.format(**kwargs) if kwargs else prompt


__all__ = ["PromptManager", "DEFAULT_PROMPTS_PATH"]
