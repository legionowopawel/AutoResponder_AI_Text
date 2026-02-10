import os
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
# 4. Funkcje AI
# -----------------------------------
def call_groq(user_text):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza GROQ")
        return None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak listy modeli GROQ")
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
                print("[ERROR] GROQ error:", response.text)
                continue

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return truncate_reply(content), f"GROQ:{model_id}"

        except Exception as e:
            print("[EXCEPTION] GROQ:", e)
            continue

    return None, None


# -----------------------------------
# 5. Webhook
# -----------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    sender_raw = (data.get("from") or data.get("sender") or "").lower()
    sender = normalize_email(sender_raw)
    subject = data.get("subject", "") or ""
    body = data.get("body", "") or ""

    if sender not in ALLOWED_EMAILS:
        return jsonify({"status": "ignored", "reason": "sender not allowed"}), 200

    if subject.lower().startswith("re:"):
        return jsonify({"status": "ignored", "reason": "reply detected"}), 200

    if not body.strip():
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    text, source = call_groq(body)

    if not text:
        return jsonify({
            "status": "ok",
            "reply": "Dziękuję za wiadomość. Modele AI nie odpowiedziały w czasie.",
        }), 200

    final_reply = (
        "Treść mojej odpowiedzi:\n"
        "Na podstawie tego, co otrzymałem, przygotowałem odpowiedź:\n\n"
        f"{text}\n\n"
        "────────────────────────────────────────────\n"
        "Ta wiadomość została wygenerowana automatycznie przez system:\n"
        "• Google Apps Script – obsługa skrzynki Gmail\n"
        "• Render.com – backend API odpowiadający na wiadomości\n"
        "• Groq – modele AI generujące treść odpowiedzi\n\n"
        "Kod źródłowy projektu dostępny tutaj:\n"
        "https://github.com/legionowopawel/AutoIllustrator-Cloud2.git\n"
        "────────────────────────────────────────────\n"
        f"ProgramPawła o nazwie: Autoresponder_Tresc_Obrazek_Zalacznik - Źródło modelu: {source}\n"
    )

    return jsonify({"status": "ok", "reply": final_reply}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
