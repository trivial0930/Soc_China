"""Qwen multimodal clients for the inspection layers (chosen provider: 通义千问).

  * L3 cloud : Alibaba Cloud Bailian (DashScope) OpenAI-compatible API, model
               ``qwen3-vl-plus`` -> drop into ``report.CloudReportBackend``.
  * L2 local : a local Qwen3-VL served by Ollama (also OpenAI-compatible) ->
               drop into ``cognition.LocalVLMBackend``.

Both expose ``complete(prompt, images) -> str`` so they satisfy the existing
``cognition.VLMClient`` / ``report.CloudClient`` protocols with no backend change.

The OpenAI-style multimodal message assembly and base64 image encoding are pure
and unit-tested. The HTTP call is an injected ``transport`` (a fake in tests); the
real transport lazily builds the ``openai`` SDK client on-board and needs an API
key (cloud) or a running Ollama (local).
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Callable, List, Optional

# Alibaba Cloud Bailian / DashScope OpenAI-compatible endpoint.
DASHSCOPE_OPENAI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
OLLAMA_OPENAI_BASE = "http://localhost:11434/v1"

# (messages, model) -> assistant reply text
Transport = Callable[[List[dict], str], str]


def encode_image(path: str) -> str:
    """Read an image file into an OpenAI ``image_url`` data URI."""
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    with open(path, "rb") as handle:
        b64 = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def build_messages(prompt: str, image_uris: List[str]) -> List[dict]:
    """Assemble OpenAI-style multimodal messages (text + image_url parts)."""
    content: List[dict] = [{"type": "text", "text": prompt}]
    for uri in image_uris:
        content.append({"type": "image_url", "image_url": {"url": uri}})
    return [{"role": "user", "content": content}]


class OpenAICompatVLMClient:
    """An OpenAI-compatible vision-language client (DashScope or Ollama)."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        transport: Optional[Transport] = None,
        encode: Callable[[str], str] = encode_image,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self._transport = transport
        self._encode = encode

    def complete(self, prompt: str, images: List[str]) -> str:
        uris = [self._encode(path) for path in images]
        messages = build_messages(prompt, uris)
        if self._transport is not None:
            return self._transport(messages, self.model)
        return self._default_transport(messages)

    def _default_transport(self, messages: List[dict]) -> str:  # pragma: no cover - needs SDK + key
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or ""


def qwen_cloud_client(
    api_key: str, model: str = "qwen3-vl-plus", transport: Optional[Transport] = None, **kwargs
) -> OpenAICompatVLMClient:
    """L3 cloud client: Qwen3-VL-Plus on Alibaba Cloud Bailian."""
    return OpenAICompatVLMClient(
        model=model, base_url=DASHSCOPE_OPENAI_BASE, api_key=api_key, transport=transport, **kwargs
    )


def ollama_vlm_client(
    model: str = "qwen3-vl:8b",
    base_url: str = OLLAMA_OPENAI_BASE,
    transport: Optional[Transport] = None,
    **kwargs,
) -> OpenAICompatVLMClient:
    """L2 local client: a local Qwen3-VL served by Ollama."""
    return OpenAICompatVLMClient(
        model=model, base_url=base_url, api_key="ollama", transport=transport, **kwargs
    )
