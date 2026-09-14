"""One-pass bounded local visual evaluator for the v4 assembler."""
from __future__ import annotations
import re
from typing import Any

FIELDS = ("people", "objects", "anatomy", "action", "environment")


class LocalContractVisualProvider:
    def __init__(self, model_path: str, max_new_tokens: int = 14):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_path, local_files_only=True, dtype=torch.float32)
        self.model.eval()
        self.max_new_tokens = max_new_tokens

    def analyze(self, image: Any) -> dict[str, str]:
        question = (
            "Evaluate five directly visible facts in this order: people/body parts; handheld "
            "object/tool; exposed body region; physical contact/holding/manipulation; broad "
            "indoor/outdoor environment. Reply with exactly five words, each YES, NO, or "
            "UNCERTAIN. Never name identity, diagnosis, treatment, procedure, or sensitive trait."
        )
        messages = [{"role": "user", "content": [{"type": "image"},
                    {"type": "text", "text": question}]}]
        prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = self.processor(text=prompt, images=[image], return_tensors="pt")
        with self.torch.no_grad():
            generated = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                                            do_sample=False)
        completion = generated[:, inputs["input_ids"].shape[1]:]
        raw = self.processor.batch_decode(completion, skip_special_tokens=True)[0]
        tokens = re.findall(r"\b(YES|NO|UNCERTAIN)\b", raw.upper())
        states = {"YES": "OBSERVED", "NO": "FALSE", "UNCERTAIN": "UNKNOWN"}
        result = {name: states.get(tokens[i], "UNKNOWN") if i < len(tokens) else "UNKNOWN"
                  for i, name in enumerate(FIELDS)}
        result.update({"closeup": "UNKNOWN", "centered": "UNKNOWN",
                       "direct_to_camera": "UNKNOWN", "_raw": raw[:300]})
        return result
