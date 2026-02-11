#!/usr/bin/env python3
# app.py — webhook generator treści (Render)
# Backend generuje treść i załączniki; decyzje kto jest obsługiwany są po stronie Apps Script.
# Zmiany: non-blocking 429 handling, mniejsze max_tokens, prosty cache odpowiedzi, bez time.sleep,
# bezpieczne ładowanie plików, fallback JSON, lepsze logowanie.

import os
import re
import json
import time
import base64
import hashlib
import requests
from typing import Tuple, Optional, Dict, Any
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# -------------------------
# Konfiguracja
# -------------------------
MAX_PROMPT_CHARS = 2500
MAX_USER_CHARS = 1500
MAX_MODEL_INPUT_CHARS = 4000
MAX_MODEL_REPLY_CHARS = 1500

# Conservative token settings to reduce TPD usage
GROQ_MAX_TOKENS_NORMAL = int(os.getenv("GROQ_MAX_TOKENS_NORMAL", "256"))
GROQ_MAX_TOKENS_BIZ = int(os.getenv("GROQ_MAX_TOKENS_BIZ", "300"))

# Simple in-memory cache for identical requests (process-local)
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # default 1 hour
_RESPONSE_CACHE: Dict[str, Dict[str, Any]] = {}  # key -> {"ts": epoch, "value": {...}}

# -------------------------
# Helpers
# -------------------------
def _now_ts() -> int:
    return int(time.time())

def _cache_get(key: str):
    entry = _RESPONSE_CACHE.get(key)
    if not entry:
        return None
    if entry["ts"] + CACHE_TTL < _now_ts():
        del _RESPONSE_CACHE[key]
        return None
    return entry["value"]

def _cache_set(key: str, value):
    _RESPONSE_CACHE[key] = {"ts": _now_ts(), "value": value}

def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def load_prompt(filename: str = "prompt.txt") -> str:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()[:MAX_PROMPT_CHARS]
    except Exception:
        return "{{USER_TEXT}}"

def summarize_and_truncate(text: str, max_chars: int = MAX_USER_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else text[:max_chars]

def build_safe_prompt(user_text: str, base_prompt: str) -> str:
    safe_user_text = summarize_and_truncate(user_text, MAX_USER_CHARS)
    prompt = base_prompt.replace("{{USER_TEXT}}", safe_user_text)
    return prompt[:MAX_MODEL_INPUT_CHARS]

def truncate_reply(text: str, max_chars: int = MAX_MODEL_REPLY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Odpowiedź skrócona]"

# -------------------------
# Retry-After parsing (non-blocking)
# -------------------------
def _parse_retry_after_seconds(resp: requests.Response) -> Optional[int]:
    ra = resp.headers.get("Retry-After")
    if ra:
        try:
            return int(float(ra))
        except Exception:
            pass
    # best-effort parse from message like "Please try again in 9m45.79s"
    try:
        body = resp.text or ""
        m = re.search(r"Please try again in (\d+\.?\d*)m", body)
        if m:
            minutes = float(m.group(1))
            return int(minutes * 60)
    except Exception:
        pass
    return None

# -------------------------
# GROQ calls (non-blocking, with cache)
# Each returns (text_or_none, source_or_none, meta_dict)
# meta contains rate_limited flag and optional retry_after seconds
# -------------------------
def call_groq(user_text: str) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    key = os.getenv("YOUR_GROQ_API_KEY")
    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not key or not models_env:
        app.logger.error("Brak konfiguracji GROQ")
        return None, None, {"rate_limited": False}

    cache_key = "groq_normal:" + _hash_text(user_text + models_env + str(GROQ_MAX_TOKENS_NORMAL))
    cached = _cache_get(cache_key)
    if cached:
        app.logger.debug("Cache hit for normal prompt")
        return cached["text"], cached["source"], {"rate_limited": False, "cached": True}

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    base_prompt = load_prompt("prompt.txt")
    prompt = build_safe_prompt(user_text, base_prompt)

    for model_id in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": GROQ_MAX_TOKENS_NORMAL,
                    "temperature": 0.0,
                },
                timeout=20,
            )
        except requests.exceptions.RequestException as e:
            app.logger.warning("call_groq request exception: %s", e)
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                text = truncate_reply(content)
                source = f"GROQ:{model_id}"
                _cache_set(cache_key, {"text": text, "source": source})
                return text, source, {"rate_limited": False}
            except Exception as e:
                app.logger.error("call_groq parse error: %s", e)
                continue

        if resp.status_code == 429:
            retry_after = _parse_retry_after_seconds(resp)
            app.logger.warning("GROQ 429 for %s. Retry-After: %s. Message: %s", model_id, retry_after, resp.text)
            return None, None, {"rate_limited": True, "retry_after": retry_after, "message": resp.text}

        app.logger.error("GROQ error %s: %s", resp.status_code, resp.text)
    return None, None, {"rate_limited": False}

def call_groq_business(user_text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Dict[str, Any]]:
    key = os.getenv("YOUR_GROQ_API_KEY")
    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not key or not models_env:
        app.logger.error("Brak konfiguracji GROQ dla biznesu")
        return None, None, None, {"rate_limited": False}

    cache_key = "groq_biz:" + _hash_text(user_text + models_env + str(GROQ_MAX_TOKENS_BIZ))
    cached = _cache_get(cache_key)
    if cached:
        app.logger.debug("Cache hit for business prompt")
        return cached["text"], cached["pdf_name"], cached["source"], {"rate_limited": False, "cached": True}

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    prompt = build_safe_prompt(user_text, os.getenv("BIZ_PROMPT_TEXT", load_prompt("prompt_biznesowy.txt")))

    for model_id in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": GROQ_MAX_TOKENS_BIZ,
                    "temperature": 0.0,
                },
                timeout=25,
            )
        except requests.exceptions.RequestException as e:
            app.logger.warning("call_groq_business request exception: %s", e)
            continue

        if resp.status_code == 200:
            try:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"
                answer = ""
                try:
                    parsed = json.loads(content)
                    answer = parsed.get("odpowiedz_tekstowa", "").strip()
                    pdf_name = parsed.get("kategoria_pdf", "").strip() or pdf_name
                except Exception:
                    m = re.search(r"(\{.*\})", content, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(1))
                            answer = parsed.get("odpowiedz_tekstowa", "").strip()
                            pdf_name = parsed.get("kategoria_pdf", "").strip() or pdf_name
                        except Exception:
                            pass
                if not answer:
                    answer = content.strip() or "Czekam na pytanie."
                text = truncate_reply(answer)
                source = f"GROQ_BIZ:{model_id}"
                _cache_set(cache_key, {"text": text, "pdf_name": pdf_name, "source": source})
                return text, pdf_name, source, {"rate_limited": False}
            except Exception as e:
                app.logger.error("call_groq_business parse error: %s", e)
                continue

        if resp.status_code == 429:
            retry_after = _parse_retry_after_seconds(resp)
            app.logger.warning("GROQ business 429 for %s. Retry-After: %s. Message: %s", model_id, retry_after, resp.text)
            return None, None, None, {"rate_limited": True, "retry_after": retry_after, "message": resp.text}

        app.logger.error("GROQ business error %s: %s", resp.status_code, resp.text)
    return None, None, None, {"rate_limited": False}

# -------------------------
# Emotki / PDF loaders (safe)
# -------------------------
def map_emotion_to_file(emotion: Optional[str]) -> str:
    if not emotion:
        return "error.png"
    e = emotion.strip().lower()
    if e in ["radość", "radosc", "szczescie", "pozytywne"]:
        return "twarz_radosc.png"
    if e in ["smutek"]:
        return "twarz_smutek.png"
    if e in ["złość", "zlosc", "gniew"]:
        return "twarz_zlosc.png"
    if e in ["strach", "lek", "lęk"]:
        return "twarz_lek.png"
    if e in ["zaskoczenie", "zdziwienie"]:
        return "twarz_zaskoczenie.png"
    if e in ["nuda"]:
        return "twarz_nuda.png"
    return "twarz_spokoj.png"

def load_emoticon_base64(filename: str) -> Tuple[str, str]:
    path = os.path.join("emotki", filename)
    fallback = os.path.join("emotki", "error.png")
    if not os.path.isfile(path):
        if os.path.isfile(fallback):
            path = fallback
        else:
            app.logger.warning("Emoticon not found: %s", filename)
            return "", "image/png"
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "image/png"
    except Exception as e:
        app.logger.error("Nie udało się wczytać emotki %s: %s", path, e)
        return "", "image/png"

def map_emotion_to_pdf_file(emotion: Optional[str]) -> str:
    png_name = map_emotion_to_file(emotion)
    return png_name.rsplit(".", 1)[0] + ".pdf"

def load_pdf_base64(filename: str) -> Tuple[str, str]:
    path = os.path.join("pdf", filename)
    if not os.path.isfile(path):
        app.logger.warning("PDF not found: %s", path)
        return "", "application/pdf"
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
    except Exception as e:
        app.logger.error("Nie udało się wczytać PDF %s: %s", path, e)
        return "", "application/pdf"

def load_pdf_biznes_base64(filename: str) -> Tuple[str, str]:
    path = os.path.join("pdf_biznes", filename)
    fallback = os.path.join("pdf_biznes", "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf")
    if not os.path.isfile(path):
        if os.path.isfile(fallback):
            path = fallback
        else:
            app.logger.warning("PDF biznesowy not found: %s", filename)
            return "", "application/pdf"
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
    except Exception as e:
        app.logger.error("Nie udało się wczytać PDF biznesowego %s: %s", path, e)
        return "", "application/pdf"

# -------------------------
# Webhook — główna logika
# -------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        secret_header = request.headers.get("X-Webhook-Secret")
        expected_secret = os.getenv("WEBHOOK_SECRET", "")
        if expected_secret and secret_header != expected_secret:
            app.logger.warning("Nieprawidłowy X-Webhook-Secret")
            return jsonify({"error": "unauthorized"}), 401

        data = request.json or {}
        sender_raw = (data.get("from") or data.get("sender") or "").strip()
        subject = (data.get("subject") or "").strip()
        body = (data.get("body") or "").strip()

        app.logger.debug("Received webhook from: %s subject: %s body_len: %d", sender_raw, subject, len(body))

        if subject.lower().startswith("re:"):
            app.logger.info("Ignoruję odpowiedź (RE:): %s", subject)
            return jsonify({"status": "ignored", "reason": "reply detected"}), 200

        if not body:
            app.logger.info("Pusta treść wiadomości – ignoruję")
            return jsonify({"status": "ignored", "reason": "empty body"}), 200

        result = {"status": "ok", "zwykly": None, "biznes": None}

        # BUSINESS response (try model, fallback if rate-limited)
        app.logger.info("Generuję odpowiedź biznesową")
        biz_text, biz_pdf_name, biz_source, biz_meta = call_groq_business(body)
        if biz_meta.get("rate_limited"):
            app.logger.info("Biznes: rate limited detected, returning fallback biznes")
            biz_text = "Czekam na pytanie. (model chwilowo niedostępny)"
            biz_pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"
            biz_source = "GROQ_BIZ:rate_limited"

        # EMOTION detection: optional and lightweight — do not call heavy model if rate-limited
        emotion = None
        # We avoid calling model for emotion detection to save tokens; keep None or implement lightweight heuristics if needed.

        emoticon_file = map_emotion_to_file(emotion)
        emot_b64, emot_ct = load_emoticon_base64(emoticon_file)
        pdf_b64, pdf_ct = load_pdf_biznes_base64(biz_pdf_name)
        pdf_info = {"filename": biz_pdf_name, "content_type": pdf_ct, "base64": pdf_b64} if pdf_b64 else None

        safe_html = biz_text.replace("\n", "<br>")
        footer_html = "<hr><div style='font-size:11px;color:#0b3d0b;'>model tekstu: {}</div>".format(biz_source)
        reply_html = f"<div>{safe_html}<br><img src='cid:emotka_biz' style='width:64px;height:64px;'><br>{footer_html}</div>"

        result["biznes"] = {
            "reply_html": reply_html,
            "text": biz_text,
            "text_source": biz_source,
            "emotion": emotion,
            "emoticon": {"filename": emoticon_file, "content_type": emot_ct, "base64": emot_b64, "cid": "emotka_biz"},
            "pdf": pdf_info,
        }

        # NORMAL response
        app.logger.info("Generuję odpowiedź zwykłą")
        zwykly_text, zwykly_source, zwyk_meta = call_groq(body)
        if zwyk_meta.get("rate_limited"):
            app.logger.info("Zwykly: rate limited detected, returning fallback zwykly")
            zwykly_text = "Przepraszamy, model chwilowo niedostępny. Proszę spróbować później."
            zwykly_source = "GROQ:rate_limited"

        emoticon_file = map_emotion_to_file(None)
        emot_b64, emot_ct = load_emoticon_base64(emoticon_file)
        pdf_file = map_emotion_to_pdf_file(None)
        pdf_b64, pdf_ct = load_pdf_base64(pdf_file)
        pdf_info = {"filename": pdf_file, "content_type": pdf_ct, "base64": pdf_b64} if pdf_b64 else None

        safe_html = (zwykly_text or "").replace("\n", "<br>")
        footer_html = "<hr><div style='font-size:11px;color:#0b3d0b;'>model tekstu: {}</div>".format(zwykly_source or "fallback")
        reply_html = f"<div>{safe_html}<br><img src='cid:emotka_zwykly' style='width:64px;height:64px;'><br>{footer_html}</div>"

        result["zwykly"] = {
            "reply_html": reply_html,
            "text": zwykly_text,
            "text_source": zwykly_source,
            "emotion": None,
            "emoticon": {"filename": emoticon_file, "content_type": emot_ct, "base64": emot_b64, "cid": "emotka_zwykly"},
            "pdf": pdf_info,
        }

        return jsonify(result), 200

    except Exception as e:
        app.logger.exception("Unhandled exception in webhook: %s", e)
        fallback = {
            "status": "ok",
            "zwykly": {
                "reply_html": "<div>Przepraszamy, wystąpił błąd serwera. Proszę spróbować później.</div>",
                "text": "Przepraszamy, wystąpił błąd serwera.",
                "text_source": "fallback",
                "emotion": None,
                "emoticon": None,
                "pdf": None,
            },
            "biznes": None,
        }
        return jsonify(fallback), 200

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    host = "0.0.0.0"
    app.logger.info("Uruchamiam aplikację na %s:%d", host, port)
    app.run(host=host, port=port)
