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
# 5. Webhook
# -----------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    # Prosta ochrona – sekret w nagłówku
    secret_header = request.headers.get("X-Webhook-Secret")
    expected_secret = os.getenv("WEBHOOK_SECRET", "")
    if not expected_secret or secret_header != expected_secret:
        print("[WARN] Nieprawidłowy lub brak X-Webhook-Secret")
        return jsonify({"error": "unauthorized"}), 401

    # Opcjonalna ochrona przed zbyt dużym payloadem
    if request.content_length and request.content_length > 20000:
        print("[WARN] Payload too large:", request.content_length)
        return jsonify({"error": "payload too large"}), 413

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
    has_text = bool(text)

    if not has_text:
        print("[ERROR] Brak odpowiedzi z GROQ – nic nie wysyłam")
        return jsonify({
            "status": "error",
            "reason": "no ai output",
        }), 200

    # Budujemy HTML odpowiedzi
    # Nagłówek pogrubiony, treść AI kursywą, stopka mała, ciemnozielona, Georgia
    footer_html = f"""
<hr>
<div style="font-size: 11px; color: #0b3d0b; font-family: Georgia, 'Times New Roman', serif; line-height: 1.4;">
────────────────────────────────────────────<br>
Ta wiadomość została wygenerowana automatycznie przez system: i<br>
program Pawła :<br>
<a href="https://github.com/legionowopawel/Autoresponder_Tresc_Obrazek_Zalacznik" style="color:#0b3d0b;">
https://github.com/legionowopawel/Autoresponder_Tresc_Obrazek_Zalacznik
</a><br>
• Google Apps Script – obsługa skrzynki Gmail<br>
• Render.com – backend API odpowiadający na wiadomości<br>
• Groq – modele AI generujące treść odpowiedzi<br>
<br>
Kod źródłowy projektu dostępny tutaj:<br>
<a href="https://github.com/legionowopawel/AutoIllustrator-Cloud2.git" style="color:#0b3d0b;">
https://github.com/legionowopawel/AutoIllustrator-Cloud2.git
</a><br>
────────────────────────────────────────────<br>
Program Pawła o nazwie: Autoresponder_Tresc_Obrazek_Zalacznik - Źródło<br>
modelu tekstu: {text_source}     oraz model grafiki uzyty do obrazka: None<br>
</div>
"""

    final_reply_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #000000;">
  <p><b>Treść mojej odpowiedzi:</b><br>
  <b>Na podstawie tego, co otrzymałem, przygotowałem odpowiedź:</b></p>

  # Zamiana nowych linii na <br>
  safe_text_html = text.replace("\n", "<br>")

  <p><i>{safe_text_html}</i></p>


  {footer_html}
</div>
"""

    return jsonify({
        "status": "ok",
        "has_text": True,
        "reply": final_reply_html,
        "text_source": text_source,
    }), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
