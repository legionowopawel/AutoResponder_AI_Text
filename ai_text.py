#!/usr/bin/env python3
"""
ai_text.py

Bezpieczne wywołanie modelu tekstowego (Groq) z retry, timeout, ograniczeniami długości
i sanitizacją odpowiedzi (usuwanie ewentualnych wrapperów JSON).
"""

import os
import time
import json
import requests
from typing import Optional

# Konfiguracja i limity
GROQ_API_KEY = os.getenv("KLUCZ_GROQ", "") or os.getenv("GROQ_API_KEY", "")
MAX_USER_CHARS = 2000
MAX_PROMPT_CHARS = 3000
MAX_MODEL_INPUT_CHARS = 5000
MAX_MODEL_REPLY_CHARS = 2000
RETRIES = 2
TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))

DEFAULT_MODEL = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

# Ścieżka do pliku prompt (jeśli chcesz używać z pliku)
PROMPT_FILE = os.getenv("PROMPT_FILE", os.path.join(os.path.dirname(__file__), "prompt.txt"))


def load_prompt() -> str:
    try:
        if os.path.exists(PROMPT_FILE):
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                txt = f.read()
            return txt[:MAX_PROMPT_CHARS]
    except Exception:
        pass
    return ""


def build_prompt(user_text: str) -> str:
    user_text = (user_text or "").strip()
    if len(user_text) > MAX_USER_CHARS:
        user_text = user_text[:MAX_USER_CHARS]
    base = load_prompt()
    if "{{USER_TEXT}}" in base:
        prompt = base.replace("{{USER_TEXT}}", user_text)
    else:
        prompt = f"{base}\n\n{user_text}" if base else user_text
    return prompt[:MAX_MODEL_INPUT_CHARS]


def truncate_reply(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_MODEL_REPLY_CHARS:
        return text
    return text[:MAX_MODEL_REPLY_CHARS]


def sanitize_model_output(raw_text: Optional[str]) -> str:
    """
    Usuwa ewentualne JSON-wrapppery lub leading JSON z odpowiedzi modelu.
    Zwraca czysty tekst, który powinien być użyty jako odpowiedź.
    """
    if not raw_text:
        return ""
    txt = raw_text.strip()

    # Jeśli cały tekst jest JSONem, spróbuj sparsować i wyciągnąć typowe pola
    if txt.startswith("{") or txt.startswith("["):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                for key in ("odpowiedz_tekstowa", "reply", "answer", "text", "message", "reply_html", "content"):
                    if key in obj:
                        val = obj[key]
                        if isinstance(val, str):
                            return val.strip()
                        else:
                            return json.dumps(val, ensure_ascii=False)
                # jeśli dict z jedną wartością, zwróć ją
                if len(obj) == 1:
                    val = next(iter(obj.values()))
                    if isinstance(val, str):
                        return val.strip()
                    else:
                        return json.dumps(val, ensure_ascii=False)
            if isinstance(obj, list):
                # złącz elementy listy w tekst
                return "\n".join(str(x) for x in obj)
        except Exception:
            # nie JSON lub parsowanie nieudane -> przejdź dalej
            pass

    # Jeśli JSON jest na początku, a potem jest tekst, usuń wrapper JSON
    if txt.startswith("{") and "}" in txt:
        try:
            end = txt.index("}") + 1
            maybe_json = txt[:end]
            remainder = txt[end:].strip()
            # spróbuj sparsować maybe_json
            try:
                obj = json.loads(maybe_json)
                if remainder:
                    return remainder
                # jeśli nie ma remainder, spróbuj wyciągnąć wartość z obj
                if isinstance(obj, dict):
                    for key in ("odpowiedz_tekstowa", "reply", "answer", "text", "message", "reply_html", "content"):
                        if key in obj:
                            val = obj[key]
                            if isinstance(val, str):
                                return val.strip()
                            else:
                                return json.dumps(val, ensure_ascii=False)
            except Exception:
                # jeśli nie parsuje, zwróć surowy tekst bez leading JSON (heurystyka)
                try:
                    # usuń wszystko do pierwszego zamykającego nawiasu klamrowego
                    return txt[end:].strip()
                except Exception:
                    pass
        except Exception:
            pass

    # Jeśli nic nie pasuje, zwróć oryginalny tekst
    return raw_text


def generate_text_reply(user_text: str, model: Optional[str] = None, retries: int = RETRIES, timeout: int = TIMEOUT) -> str:
    """
    Wywołanie Groq z retry i fallbackem.
    Zwraca tekst lub komunikat o błędzie.
    """
    if not GROQ_API_KEY:
        return "Brak klucza API (GROQ)."

    model_name = model or DEFAULT_MODEL
    prompt = build_prompt(user_text)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,
        "temperature": 0.7
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    # jeśli nie JSON, traktujemy jako surowy tekst
                    raw = resp.text
                    cleaned = sanitize_model_output(raw)
                    return truncate_reply(cleaned)

                # Bezpieczeństwo: spróbuj wyciągnąć content z odpowiedzi
                content = ""
                try:
                    # standardowy format OpenAI-like
                    content = data["choices"][0]["message"]["content"]
                except Exception:
                    # inne formaty: spróbuj kilka pól
                    if isinstance(data, dict):
                        for key in ("content", "text", "message", "reply"):
                            if key in data and isinstance(data[key], str):
                                content = data[key]
                                break
                    # fallback: zamień cały obiekt na string
                    if not content:
                        content = json.dumps(data, ensure_ascii=False)

                # sanitize i truncate
                content = sanitize_model_output(content)
                return truncate_reply(content)
            else:
                last_err = f"GROQ status {resp.status_code}: {resp.text[:1000]}"
                # logowanie do stdout (backend powinien logować)
                print(last_err)
        except requests.RequestException as e:
            last_err = f"Błąd połączenia Groq: {e}"
            print(last_err)
        # prosty backoff
        time.sleep(1 + attempt)

    # jeśli nie udało się nic uzyskać
    if last_err:
        print("generate_text_reply failed:", last_err)
    return "Przepraszam, wystąpił problem z generowaniem odpowiedzi (API niedostępne)."
