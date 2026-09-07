# SPDX-License-Identifier: Apache-2.0
"""Konektor keluar ke penyedia LLM (Lampiran konektor).

Dua protokol cukup untuk sepuluh penyedia:
- anthropic         : Claude (Messages API)
- openai_compatible : ChatGPT/OpenAI, Perplexity, DeepSeek, Kimi (Moonshot), Grok (xAI),
                      GLM (Zhipu), Nemotron (NVIDIA NIM), Gemini (lapisan kompatibilitas resmi Google
                      di /v1beta/openai/, per ai.google.dev/gemini-api/docs/openai, dicek Sep 2026),
                      dan endpoint privat (vLLM/Ollama/LM Studio) — semuanya memakai /chat/completions.

PRESET di bawah berasal dari informasi umum per pertengahan 2026 dan
DAPAT BERUBAH. Base URL dan nama model selalu bisa ditimpa di konfigurasi.json.
Kunci API hanya dibaca dari environment variable — tidak pernah dari berkas.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

PRESET: dict[str, dict] = {
    "claude": {"jenis": "anthropic", "base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-5", "env": "ANTHROPIC_API_KEY"},
    "openai": {"jenis": "openai_compatible", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "env": "OPENAI_API_KEY"},
    "perplexity": {"jenis": "openai_compatible", "base_url": "https://api.perplexity.ai", "model": "sonar", "env": "PERPLEXITY_API_KEY"},
    "deepseek": {"jenis": "openai_compatible", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "env": "DEEPSEEK_API_KEY"},
    "kimi": {"jenis": "openai_compatible", "base_url": "https://api.moonshot.ai/v1", "model": "kimi-k2-0711-preview", "env": "MOONSHOT_API_KEY"},
    "grok": {"jenis": "openai_compatible", "base_url": "https://api.x.ai/v1", "model": "grok-4", "env": "XAI_API_KEY"},
    "glm": {"jenis": "openai_compatible", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.5", "env": "ZHIPU_API_KEY"},
    "nemotron": {"jenis": "openai_compatible", "base_url": "https://integrate.api.nvidia.com/v1", "model": "nvidia/llama-3.1-nemotron-70b-instruct", "env": "NVIDIA_API_KEY"},
    "gemini": {"jenis": "openai_compatible", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash", "env": "GEMINI_API_KEY"},
    "lokal": {"jenis": "openai_compatible", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b", "env": "LOKAL_API_KEY"},
}


class PenyediaGagal(RuntimeError):
    pass


def _post_json(url: str, badan: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(url, data=json.dumps(badan).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        isi = e.read().decode(errors="replace")[:500]
        raise PenyediaGagal(f"HTTP {e.code} dari {url}: {isi}") from e
    except urllib.error.URLError as e:
        raise PenyediaGagal(f"tidak bisa menghubungi {url}: {e.reason}") from e


class PenyediaOpenAICompat:
    def __init__(self, id_: str, base_url: str, api_key: str, model: str, timeout: int = 90, headers: dict | None = None):
        self.id = id_
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.headers = headers or {}

    def tanya(self, sistem: str, pesan: str, maks_token: int = 1024, suhu: float = 0.2) -> str:
        badan = {
            "model": self.model, "max_tokens": maks_token, "temperature": suhu,
            "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": pesan}],
        }
        h = {**self.headers}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        data = _post_json(f"{self.base_url}/chat/completions", badan, h, self.timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise PenyediaGagal(f"format jawaban tak dikenal dari {self.id}: {str(data)[:300]}") from e


class PenyediaAnthropic:
    def __init__(self, id_: str, base_url: str, api_key: str, model: str, timeout: int = 90, versi: str = "2023-06-01"):
        self.id = id_
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.versi = versi

    def tanya(self, sistem: str, pesan: str, maks_token: int = 1024, suhu: float = 0.2) -> str:
        badan = {"model": self.model, "max_tokens": maks_token, "temperature": suhu, "system": sistem,
                 "messages": [{"role": "user", "content": pesan}]}
        h = {"x-api-key": self.api_key, "anthropic-version": self.versi}
        data = _post_json(f"{self.base_url}/v1/messages", badan, h, self.timeout)
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except Exception as e:
            raise PenyediaGagal(f"format jawaban tak dikenal dari {self.id}: {str(data)[:300]}") from e


def bangun_penyedia(konfig: dict | None) -> dict:
    """Bangun registry {id: Penyedia} dari konfigurasi['penyedia'].

    Contoh konfigurasi:
      "penyedia": {
        "claude":   {"aktif": true},
        "deepseek": {"aktif": true, "model": "deepseek-chat"},
        "lokal":    {"aktif": true, "base_url": "http://vllm:8000/v1", "model": "qwen3-8b"}
      }
    Penyedia tanpa kunci di environment dilewati (bukan galat) — kecuali 'lokal'
    yang boleh tanpa kunci.
    """
    hasil: dict = {}
    for pid, k in (konfig or {}).items():
        if not k.get("aktif", False):
            continue
        preset = dict(PRESET.get(pid, {}))
        gabung = {**preset, **{a: b for a, b in k.items() if a != "aktif"}}
        jenis = gabung.get("jenis", "openai_compatible")
        api_key = os.environ.get(gabung.get("env", f"{pid.upper()}_API_KEY"), "")
        if not api_key and pid != "lokal" and not gabung.get("tanpa_kunci"):
            continue
        if jenis == "anthropic":
            hasil[pid] = PenyediaAnthropic(pid, gabung["base_url"], api_key, gabung["model"], gabung.get("timeout", 90))
        else:
            hasil[pid] = PenyediaOpenAICompat(pid, gabung["base_url"], api_key, gabung["model"], gabung.get("timeout", 90), gabung.get("headers"))
    return hasil


def daftar_preset() -> list[dict]:
    return [{"id": k, **{a: b for a, b in v.items() if a != "env"}, "env": v["env"]} for k, v in PRESET.items()]
