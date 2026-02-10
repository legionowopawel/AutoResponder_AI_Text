import os
import time
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# -----------------------------------
# 1. Normalizacja Gmaili
# -----------------------------------
def normalize_email(email: str) -> str:
    email = (email or "").lower().strip()
    if email.endswith("@gmail.com"):
        local, domain = email.split("@")
        local = local.replace(".", "")
        local = local.split("+", 1)[0]
        return f"{local}@{domain}"
    return email


# -----------------------------------
# 2. Wczytywanie listy emaili z ENV
# -----------------------------------
def load_allowed_emails():
    env = os.getenv("ALLOWED_EMAILS", "")
    if not env:
        print("[WARN] Brak ALLOWED_EMAILS w zmiennych środowiskowych")
        return set()

    emails = set()
    for e in env.split(","):
        clean = normalize_email(e.strip())
        if clean:
            emails.add(clean)

    print("[INFO] Wczytano emaile z ENV:", emails)
    return emails


ALLOWED_EMAILS = load_allowed_emails()


# -----------------------------------
# 3. Limity długości
# -----------------------------------
MAX_PROMPT_CHARS = 2500
MAX_USER_CHARS = 1500
MAX_MODEL_INPUT_CHARS = 4000
MAX_MODEL_REPLY_CHARS = 1500


def load_prompt():
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            txt = f.read()
            if len(txt) > MAX_PROMPT_CHARS:
                txt = txt[:MAX_PROMPT_CHARS]
            print("[INFO] Wczytano prompt.txt (długość:", len(txt), ")")
            return txt
    except FileNotFoundError:
        print("[ERROR] Brak pliku prompt.txt")
        return "Brak pliku prompt.txt\n\n{{USER_TEXT}}"


def load_image_prompt():
    try:
        with open("prompt_obrazek.txt", "r", encoding="utf-8") as f:
            txt = f.read()
            print("[INFO] Wczytano prompt_obrazek.txt (długość:", len(txt), ")")
            return txt
    except FileNotFoundError:
        print("[WARN] Brak pliku prompt_obrazek.txt – używam domyślnego promptu")
        return "Wygeneruj ilustrację pasującą do poniższej wiadomości użytkownika:\n\n{{USER_TEXT}}"


def summarize_and_truncate(text: str, max_chars: int = MAX_USER_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text

    summary = text[:max_chars]
    return (
        "Streszczenie długiej wiadomości użytkownika (skrócone do bezpiecznej długości):\n\n"
        + summary
    )


def build_safe_prompt(user_text: str) -> str:
    base_prompt = load_prompt()
    safe_user_text = summarize_and_truncate(user_text, MAX_USER_CHARS)
    prompt = base_prompt.replace("{{USER_TEXT}}", safe_user_text)

    if len(prompt) > MAX_MODEL_INPUT_CHARS:
        prompt = prompt[:MAX_MODEL_INPUT_CHARS]

    return prompt


def truncate_reply(text: str, max_chars: int = MAX_MODEL_REPLY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Odpowiedź skrócona do bezpiecznej długości]"


# -----------------------------------
# 4. Funkcje AI – GROQ (tekst)
# -----------------------------------
def call_groq(user_text):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza GROQ (YOUR_GROQ_API_KEY)")
        return None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak listy modeli GROQ (GROQ_MODELS)")
        return None, None

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    prompt = build_safe_prompt(user_text)

    for model_id in models:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                },
                timeout=20,
            )

            if response.status_code != 200:
                print("[ERROR] GROQ error:", response.status_code, response.text)
                continue

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return truncate_reply(content), f"GROQ:{model_id}"

        except Exception as e:
            print("[EXCEPTION] GROQ:", e)
            continue

    print("[WARN] Żaden model GROQ nie zwrócił odpowiedzi")
    return None, None


# -----------------------------------
# 5. Funkcje AI – Fal.ai (obrazek, darmowy)
# -----------------------------------

FAL_MODEL = "fal-ai/flux/dev"  # może być słabszy, ale darmowy endpoint proxy


def download_image_to_base64(url: str):
    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            print("[ERROR] Download image error:", resp.status_code, resp.text)
            return None
        image_bytes = resp.content
        return base64.b64encode(image_bytes).decode("ascii")
    except Exception as e:
        print("[EXCEPTION] Download image:", e)
        return None


def call_fal_image(user_text):
    """
    Generuje obrazek przez Fal.ai.
    Zwraca (image_base64, image_url, image_source) albo (None, None, None).
    """
    api_key = os.getenv("FAL_API_KEY")
    if not api_key:
        print("[WARN] Brak FAL_API_KEY – obrazek nie będzie generowany")
        return None, None, None

    prompt_template = load_image_prompt()
    safe_user_text = summarize_and_truncate(user_text, 800)
    final_prompt = prompt_template.replace("{{USER_TEXT}}", safe_user_text)

    url = f"https://fal.run/{FAL_MODEL}"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": {
            "prompt": final_prompt,
            # Fal zwykle sam dobiera rozmiar, ale możemy zasugerować:
            "image_size": "square_hd",
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            print("[ERROR] Fal.ai error:", resp.status_code, resp.text)
            return None, None, None

        data = resp.json()
        # typowy format: {"images": [{"url": "..."}]}
        images = data.get("images") or data.get("output") or []
        image_url = None

        if isinstance(images, list) and len(images) > 0:
            first = images[0]
            if isinstance(first, dict):
                image_url = first.get("url") or first.get("image_url")
            elif isinstance(first, str):
                image_url = first
        elif isinstance(images, dict):
            image_url = images.get("url") or images.get("image_url")

        if not image_url:
            print("[ERROR] Fal.ai – brak URL obrazka w odpowiedzi:", data)
            return None, None, None

        image_b64 = download_image_to_base64(image_url)
        if not image_b64:
            print("[ERROR] Fal.ai – nie udało się pobrać obrazka")
            return None, None, None

        print("[INFO] Udało się wygenerować obrazek przez Fal.ai")
        return image_b64, image_url, f"FAL:{FAL_MODEL}"

    except Exception as e:
        print("[EXCEPTION] Fal.ai:", e)
        return None, None, None


# -----------------------------------
# 6. Webhook
# -----------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    sender_raw = (data.get("from") or data.get("sender") or "").lower()
    sender = normalize_email(sender_raw)
    subject = data.get("subject", "") or ""
    body = data.get("body", "") or ""

    if sender not in ALLOWED_EMAILS:
        print("[INFO] Nadawca nie jest na liście dozwolonych:", sender)
        return jsonify({"status": "ignored", "reason": "sender not allowed"}), 200

    if subject.lower().startswith("re:"):
        print("[INFO] Wykryto odpowiedź (RE:), ignoruję:", subject)
        return jsonify({"status": "ignored", "reason": "reply detected"}), 200

    if not body.strip():
        print("[INFO] Pusta treść wiadomości – ignoruję")
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    # --- Tekst z GROQ ---
    text, text_source = call_groq(body)

    # --- Obrazek z Fal.ai ---
    image_b64, image_url, image_source = call_fal_image(body)

    has_text = bool(text)
    has_image = bool(image_b64)

    if not has_text and not has_image:
        print("[ERROR] Brak odpowiedzi z GROQ i brak obrazka z Fal.ai – nic nie wysyłam")
        return jsonify({
            "status": "error",
            "reason": "no ai output",
        }), 200

    final_reply = None
    if has_text:
        final_reply = (
            "Treść mojej odpowiedzi:\n"
            "Na podstawie tego, co otrzymałem, przygotowałem odpowiedź:\n\n"
            f"{text}\n\n"
        )

        if has_image and image_url:
            final_reply += (
                "Link do wygenerowanego obrazka:\n"
                f"{image_url}\n\n"
            )

        final_reply += (
            "────────────────────────────────────────────\n"
            "Ta wiadomość została wygenerowana automatycznie przez system: i\n"
            "program Pawła :\n"
            "https://github.com/legionowopawel/Autoresponder_Tresc_Obrazek_Zalacznik\n"
            "• Google Apps Script – obsługa skrzynki Gmail\n"
            "• Render.com – backend API odpowiadający na wiadomości\n"
            "• Groq – modele AI generujące treść odpowiedzi\n\n"
            "Kod źródłowy projektu dostępny tutaj:\n"
            "https://github.com/legionowopawel/AutoIllustrator-Cloud2.git\n"
            "────────────────────────────────────────────\n"
            f"Program Pawła o nazwie: Autoresponder_Tresc_Obrazek_Zalacznik - Źródło\n"
            f"modelu tekstu: {text_source}     oraz model grafiki uzyty do obrazka: {image_source}\n"
        )

    return jsonify({
        "status": "ok",
        "has_text": has_text,
        "has_image": has_image,
        "reply": final_reply,
        "image_base64": image_b64,
        "image_url": image_url,
        "image_mime": "image/png" if has_image else None,
        "text_source": text_source,
        "image_source": image_source,
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
