#!/usr/bin/env python3
# app.py — webhook generator treści (Render)
# Uwaga: nie umieszczaj sekretów w tym pliku. Wszystkie klucze i listy emaili
# powinny być w zmiennych środowiskowych po stronie Apps Script.

import os
import re
import json
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# -------------------------
# Konfiguracja i pomocnicze
# -------------------------
MAX_PROMPT_CHARS = 2500
MAX_USER_CHARS = 1500
MAX_MODEL_INPUT_CHARS = 4000
MAX_MODEL_REPLY_CHARS = 1500

def normalize_email(email: str) -> str:
    email = (email or "").lower().strip()
    if "<" in email and ">" in email:
        start = email.find("<") + 1
        end = email.find(">")
        email = email[start:end].strip()
    if email.endswith("@gmail.com"):
        try:
            local, domain = email.split("@", 1)
            local = local.replace(".", "")
            local = local.split("+", 1)[0]
            return f"{local}@{domain}"
        except Exception:
            return email
    return email

def load_prompt(filename: str = "prompt.txt"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            txt = f.read()
            return txt[:MAX_PROMPT_CHARS]
    except FileNotFoundError:
        print(f"[ERROR] Brak pliku {filename}")
        return "{{USER_TEXT}}"

def summarize_and_truncate(text: str, max_chars: int = MAX_USER_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]

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
# Wywołania modelu (GROQ)
# -------------------------
def call_groq(user_text: str):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza YOUR_GROQ_API_KEY")
        return None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak GROQ_MODELS")
        return None, None

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    base_prompt = load_prompt("prompt.txt")
    prompt = build_safe_prompt(user_text, base_prompt)

    for model_id in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": [{"role": "user", "content": prompt}], "max_tokens": 512, "temperature": 0.0},
                timeout=20,
            )
            if resp.status_code != 200:
                print("[ERROR] GROQ:", resp.status_code, resp.text)
                continue
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return truncate_reply(content), f"GROQ:{model_id}"
        except Exception as e:
            print("[EXCEPTION] call_groq:", e)
            continue
    return None, None

# -------------------------
# Biznes prompt i parsowanie
# -------------------------
BIZ_PROMPT = ""
try:
    with open("prompt_biznesowy.txt", "r", encoding="utf-8") as f:
        BIZ_PROMPT = f.read()
except Exception:
    BIZ_PROMPT = (
        "WAŻNE: ODPOWIEDŹ MUSI BYĆ WYŁĄCZNIE W FORMACIE JSON. ZWRÓĆ OBIEKT JSON:\n"
        '{"odpowiedz_tekstowa":"...","kategoria_pdf":"NAZWA_PLIKU.pdf"}\n\n{{USER_TEXT}}'
    )

def call_groq_business(user_text: str):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza YOUR_GROQ_API_KEY dla biznesu")
        return None, None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak GROQ_MODELS dla biznesu")
        return None, None, None

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    prompt = build_safe_prompt(user_text, BIZ_PROMPT)

    for model_id in models:
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": [{"role": "user", "content": prompt}], "max_tokens": 700, "temperature": 0.0},
                timeout=25,
            )
            if resp.status_code != 200:
                print("[ERROR] GROQ business:", resp.status_code, resp.text)
                continue

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"
            answer = ""

            try:
                parsed = json.loads(content)
                answer = parsed.get("odpowiedz_tekstowa", "").strip()
                pdf_name = parsed.get("kategoria_pdf", "").strip() or pdf_name
            except Exception:
                m = re.search(r'(\{.*\})', content, re.DOTALL)
                if m:
                    try:
                        parsed = json.loads(m.group(1))
                        answer = parsed.get("odpowiedz_tekstowa", "").strip()
                        pdf_name = parsed.get("kategoria_pdf", "").strip() or pdf_name
                    except Exception:
                        pass

            if not answer:
                answer = content.strip() or "Czekam na pytanie."

            if not pdf_name:
                pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

            return truncate_reply(answer), pdf_name, f"GROQ_BIZ:{model_id}"

        except Exception as e:
            print("[EXCEPTION] call_groq_business:", e)
            continue

    return None, None, None

# -------------------------
# Emocje i pliki
# -------------------------
def detect_emotion_ai(user_text: str) -> str | None:
    key = os.getenv("YOUR_GROQ_API_KEY")
    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not key or not models_env:
        return None
    model_id = models_env.split(",")[0].strip()
    prompt = (
        "Określ jedną dominującą emocję z listy: radość, smutek, złość, strach, neutralne, zaskoczenie, nuda, spokój.\n\n"
        f"Tekst:\n{user_text}"
    )
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": [{"role": "user", "content": prompt}], "max_tokens": 16, "temperature": 0.0},
            timeout=12,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip().lower()
        return content.split()[0]
    except Exception:
        return None

def map_emotion_to_file(emotion: str | None) -> str:
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

def load_emoticon_base64(filename: str) -> tuple[str, str]:
    path = os.path.join("emotki", filename)
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "image/png"
    except Exception as e:
        print(f"[ERROR] Nie udało się wczytać emotki {path}: {e}")
        try:
            with open(os.path.join("emotki", "error.png"), "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), "image/png"
        except Exception:
            return "", "image/png"

def map_emotion_to_pdf_file(emotion: str | None) -> str:
    png_name = map_emotion_to_file(emotion)
    return png_name.rsplit(".", 1)[0] + ".pdf"

def load_pdf_base64(filename: str) -> tuple[str, str]:
    path = os.path.join("pdf", filename)
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
    except Exception as e:
        print(f"[ERROR] Nie udało się wczytać PDF {path}: {e}")
        try:
            with open(os.path.join("pdf", "error.pdf"), "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
        except Exception:
            return "", "application/pdf"

def load_pdf_biznes_base64(filename: str) -> tuple[str, str]:
    path = os.path.join("pdf_biznes", filename)
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
    except Exception as e:
        print(f"[ERROR] Nie udało się wczytać PDF biznesowego {path}: {e}")
        try:
            with open(os.path.join("pdf_biznes", "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"), "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), "application/pdf"
        except Exception:
            return "", "application/pdf"

# -------------------------
# Webhook — główna logika (BEZ WHITELIST)
# -------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    secret_header = request.headers.get("X-Webhook-Secret")
    expected_secret = os.getenv("WEBHOOK_SECRET", "")
    if expected_secret and secret_header != expected_secret:
        print("[WARN] Nieprawidłowy X-Webhook-Secret")
        return jsonify({"error": "unauthorized"}), 401

    data = request.json or {}
    sender_raw = (data.get("from") or data.get("sender") or "").strip()
    sender = normalize_email(sender_raw)
    subject = (data.get("subject") or "").strip()
    body = (data.get("body") or "").strip()
    body_lower = body.lower()

    print(f"[DEBUG] Nadawca raw: {sender_raw} normalized: {sender}")

    # ignoruj odpowiedzi
    if subject.lower().startswith("re:"):
        print("[INFO] Ignoruję odpowiedź (RE:)", subject)
        return jsonify({"status": "ignored", "reason": "reply detected"}), 200

    if not body:
        print("[INFO] Pusta treść wiadomości – ignoruję")
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    result = {"status": "ok", "zwykly": None, "biznes": None}

    # generuj odpowiedź biznesową (zawsze jeśli body istnieje)
    print("[INFO] Generuję odpowiedź biznesową dla:", sender)
    biz_text, biz_pdf_name, biz_source = call_groq_business(body)
    if not biz_text:
        biz_text = "Czekam na pytanie."
        biz_pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"
        biz_source = "GROQ_BIZ:fallback"

    emotion = detect_emotion_ai(body)
    emoticon_file = map_emotion_to_file(emotion)
    emot_b64, emot_ct = load_emoticon_base64(emoticon_file)
    pdf_b64, pdf_ct = load_pdf_biznes_base64(biz_pdf_name)
    pdf_info = None
    if pdf_b64:
        pdf_info = {"filename": biz_pdf_name, "content_type": pdf_ct, "base64": pdf_b64}
        print("[PDF-BIZ] Dołączono:", biz_pdf_name)
    else:
        print("[PDF-BIZ] Brak PDF biznesowego:", biz_pdf_name)

    safe_html = biz_text.replace("\n", "<br>")
    footer_html = (
        "<hr>"
        "<div style='font-size:11px;color:#0b3d0b;font-family:Georgia,Times New Roman,serif;line-height:1.4;'>"
        "────────────────────────────────────────────<br>"
        "Ta wiadomość została wygenerowana automatycznie przez system kancelarii notarialnej.<br>"
        "To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej.<br>"
        "────────────────────────────────────────────<br>"
        f"model tekstu: {biz_source}<br>"
        "</div>"
    )

    reply_html = f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#000'>{safe_html}<br><img src='cid:emotka_biz' style='width:64px;height:64px;'><br>{footer_html}</div>"

    result["biznes"] = {
        "reply_html": reply_html,
        "text": biz_text,
        "text_source": biz_source,
        "emotion": emotion,
        "emoticon": {"filename": emoticon_file, "content_type": emot_ct, "base64": emot_b64, "cid": "emotka_biz"},
        "pdf": pdf_info,
    }

    # generuj odpowiedź zwykłą (zawsze jeśli body istnieje)
    print("[INFO] Generuję odpowiedź zwykłą dla:", sender)
    zwykly_text, zwykly_source = call_groq(body)
    if not zwykly_text:
        zwykly_text = "Przepraszamy, wystąpił problem z wygenerowaniem odpowiedzi."
        zwykly_source = "GROQ:fallback"

    emotion = detect_emotion_ai(body)
    emoticon_file = map_emotion_to_file(emotion)
    emot_b64, emot_ct = load_emoticon_base64(emoticon_file)

    pdf_info = None
    # backend może zawsze dołączać pdf zwykły (skrypt zdecyduje czy wysłać)
    pdf_file = map_emotion_to_pdf_file(emotion)
    pdf_b64, pdf_ct = load_pdf_base64(pdf_file)
    if pdf_b64:
        pdf_info = {"filename": pdf_file, "content_type": pdf_ct, "base64": pdf_b64}
        print("[PDF] Dołączono:", pdf_file)
    else:
        print("[PDF] Brak PDF zwykłego:", pdf_file)

    safe_html = zwykly_text.replace("\n", "<br>")
    footer_html = (
        "<hr>"
        "<div style='font-size:11px;color:#0b3d0b;font-family:Georgia,Times New Roman,serif;line-height:1.4;'>"
        "────────────────────────────────────────────<br>"
        "Ta wiadomość została wygenerowana automatycznie przez system Pawła.<br>"
        "To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej.<br>"
        "────────────────────────────────────────────<br>"
        f"model tekstu: {zwykly_source}<br>"
        "</div>"
    )

    reply_html = f"<div style='font-family:Arial,sans-serif;font-size:14px;color:#000'>{safe_html}<br><img src='cid:emotka_zwykly' style='width:64px;height:64px;'><br>{footer_html}</div>"

    result["zwykly"] = {
        "reply_html": reply_html,
        "text": zwykly_text,
        "text_source": zwykly_source,
        "emotion": emotion,
        "emoticon": {"filename": emoticon_file, "content_type": emot_ct, "base64": emot_b64, "cid": "emotka_zwykly"},
        "pdf": pdf_info,
    }

    return jsonify(result), 200

# -------------------------
# Uruchomienie
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    host = "0.0.0.0"
    print(f"[INFO] Uruchamiam aplikację na {host}:{port}")
    app.run(host=host, port=port)
