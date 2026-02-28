"""
core/ai_client.py
Wywołania modelu AI (DeepSeek/Groq), sanitizacja odpowiedzi.
"""
import os
import json
import requests
from flask import current_app

GROQ_API_KEY = os.getenv("API_KEY_DEEPSEEK")
MODEL_BIZ    = os.getenv("MODEL_BIZ",   "deepseek-chat")
MODEL_TYLER  = os.getenv("MODEL_TYLER", "deepseek-chat")


def sanitize_model_output(raw_text: str) -> str:
    """Usuwa JSON-wrappery, zwraca czysty tekst odpowiedzi modelu."""
    if not raw_text:
        return ""
    txt = raw_text.strip()

    if txt.startswith("{") or txt.startswith("["):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                for key in ("odpowiedz_tekstowa", "reply", "answer",
                            "text", "message", "reply_html", "content"):
                    if key in obj:
                        val = obj[key]
                        return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
                if len(obj) == 1:
                    val = next(iter(obj.values()))
                    return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
            if isinstance(obj, list):
                return "\n".join(str(x) for x in obj)
        except Exception:
            pass

    if txt.startswith("{") and "}" in txt:
        try:
            end = txt.index("}") + 1
            maybe_json = txt[:end]
            remainder  = txt[end:].strip()
            try:
                json.loads(maybe_json)
                if remainder:
                    return remainder
            except Exception:
                return txt[end:].strip()
        except Exception:
            pass

    return raw_text


def extract_clean_text(text: str) -> str:
    """Wyciąga pole 'odpowiedz_tekstowa' z JSON-a jeśli istnieje."""
    import re
    if not text:
        return ""
    txt   = text.strip()
    match = re.search(r'\{.*\}', txt, re.DOTALL)
    if not match:
        return txt
    try:
        obj = json.loads(match.group(0))
        if isinstance(obj, dict) and "odpowiedz_tekstowa" in obj:
            val = obj["odpowiedz_tekstowa"]
            return val.strip() if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        return txt
    except Exception:
        return txt


def call_groq(system_prompt: str, user_msg: str, model_name: str, timeout: int = 20):
    """
    Wywołanie modelu przez API DeepSeek/Groq.
    Zwraca czysty tekst lub None przy błędzie.
    """
    if not GROQ_API_KEY:
        current_app.logger.error("Brak API_KEY_DEEPSEEK")
        return None

    url     = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens":  3000,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            current_app.logger.warning("API non-200 (%s): %s", resp.status_code, resp.text[:500])
            return None
        try:
            data = resp.json()
        except Exception:
            return sanitize_model_output(resp.text)

        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = None
            if isinstance(data, dict):
                for key in ("content", "text", "message", "reply"):
                    if key in data and isinstance(data[key], str):
                        content = data[key]
                        break
            if not content:
                content = json.dumps(data, ensure_ascii=False)

        return sanitize_model_output(content)

    except Exception as e:
        current_app.logger.exception("Błąd wywołania API: %s", e)
        return None
