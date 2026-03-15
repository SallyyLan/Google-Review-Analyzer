"""
Lightweight client for calling a Hugging Face chat model (e.g. Qwen, Mistral)
via the Inference API.

Reads HF_TOKEN from the environment (loaded in run_pipeline.py via python-dotenv).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from huggingface_hub import InferenceClient


# Mistral-7B-Instruct-v0.2 is no longer available via HF Inference API (router returns 404).
# Qwen 7B Instruct is supported and works well for JSON-style analysis.
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"


@dataclass
class LLMConfig:
    model_id: str = DEFAULT_MODEL_ID
    # Keep under HF router limit: inputs + max_new_tokens <= 32769.
    # 2048 is enough for themes + summary JSON; avoids 422 when prompt is large.
    max_new_tokens: int = 2048
    temperature: float = 0.1
    top_p: float = 0.9
    stop_sequences: Optional[list[str]] = None


_client: Optional[InferenceClient] = None
_config = LLMConfig()


def _get_client() -> InferenceClient:
    """
    Lazily construct a global InferenceClient.

    Requires HF_TOKEN to be set in the environment.
    """
    global _client
    if _client is not None:
        return _client

    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN is not set. Add your Hugging Face token to the .env file "
            "or environment before running the pipeline."
        )

    _client = InferenceClient(model=_config.model_id, token=token)
    return _client


def generate_text(prompt: str, max_new_tokens: Optional[int] = None) -> str:
    """
    Call the configured Hugging Face model with a single prompt and return raw text.

    The model is configured for low temperature and deterministic output so JSON
    responses are more stable.
    """
    client = _get_client()
    max_tokens = max_new_tokens or _config.max_new_tokens

    # Mistral-7B-Instruct and similar models only support the conversational (chat)
    # task, not text-generation. Use chat_completion only.
    completion = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a restaurant review analyst and must respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=_config.temperature,
        top_p=_config.top_p,
    )
    choice = getattr(completion, "choices", [{}])[0]
    message = getattr(choice, "message", choice.get("message", {}))  # type: ignore[assignment]
    content = getattr(message, "content", message.get("content", ""))  # type: ignore[assignment]
    text = str(content or "").strip()
    return text


__all__ = ["generate_text", "LLMConfig", "DEFAULT_MODEL_ID"]

