import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ============================
# 1. KONFIGURACJA
# ============================

GROQ_API_KEY = os.getenv("KLUCZ_GROQ")
MODEL_BIZ = os.getenv("MODEL_BIZ", "llama-3.3-70b-versatile")
MODEL_TYLER = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

# ============================
# 2. DIAGNOSTYKA TOKENA GROQ
# ============================

def debug_token():
    key = GROQ_API_KEY

    print("=== DIAGNOSTYKA KLUCZA GROQ ===")

    if key is None:
        print("🔴 KLUCZ_GROQ = BRAK (Render NIE widzi zmiennej środowiskowej!)")
        print("=== KONIEC DIAGNOSTYKI ===")
        return

    if key == "":
        print("🔴 KLUCZ_GROQ = PUSTY STRING (zmienna ustawiona, ale bez wartości!)")
        print("=== KONIEC DIAGNOSTYKI ===")
        return

    print("🟢 KLUCZ_GROQ = ZNALEZIONY")

    # Sprawdzenie spacji
    if key != key.strip():
        print("🟠 UWAGA: Token ma spacje na początku lub końcu!")
    else:
        print("🟢 Brak spacji na początku/końcu")

    # Długość
    print(f"ℹ️ Długość tokena: {len(key)} znaków")

    # Bezpieczny podgląd
    start = key[:4]
    end = key[-4:] if len(key) >= 8 else ""
    print(f"🔍 Podgląd tokena: {start}...{end}")

    # Podgląd nagłówka Authorization
    print(f"🔎 Authorization header: Bearer {start}...{end}")

    print("=== KONIEC DIAGNOSTYKI ===")


# ============================
# 3. NORMALIZACJA MAILI
# ============================

def normalize_email(email: str) -> str:
    """Usuwa kropki i aliasy z Gmaila."""
    email = (email or "").lower().strip()
    if email.endswith("@gmail.com"):
        local, domain = email.split("@")
        local = local.replace(".", "").split("+", 1)[0]
        return f"{local}@{domain}"
    return email

# ============================
# 4. FUNKCJA DO WYWOŁANIA GROQ
# ============================

def call_groq(system_prompt: str, user_msg: str, model_name: str):
    """Wywołuje API Groq i wymusza odpowiedź w JSON."""
    if not GROQ_API_KEY:
        print("[ERROR] Brak zmiennej środowiskowej KLUCZ_GROQ lub jest pusta!")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": system_prompt + " Odpowiadaj zawsze w formacie JSON."
            },
            {"role": "user", "content": user_msg}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.7
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)

        if resp.status_code != 200:
            print(f"[GROQ ERROR ({model_name})]: {resp.text}")
            return None

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    except Exception as e:
        print(f"[EXCEPTION GROQ]: {str(e)}")
        return None

# ============================
# 5. POMOCNICZE FUNKCJE
# ============================

def get_base64_image():
    """Zwraca przykładową emotkę w Base64."""
    return (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

def generate_pdf_dummy():
    """Symulacja generowania PDF w Base64."""
    return "JVBERi0xLjQKJ...[SKRÓCONE]..."

# ============================
# 6. GŁÓWNY WEBHOOK
# ============================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    sender_raw = data.get("from", "")
    sender = normalize_email(sender_raw)
    subject = data.get("subject", "")
    body = data.get("body", "")

    # --- ZABEZPIECZENIA ---
    if not body.strip():
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    if subject.lower().startswith("re:"):
        return jsonify({"status": "ignored", "reason": "loop prevention"}), 200

    # --- PROMPTY ---
    prompt_biznes = "Jesteś uprzejmym Notariuszem. Przygotuj profesjonalną odpowiedź."
    prompt_tyler = "Jesteś Tylerem Durdenem z Fight Clubu. Bądź cyniczny i krótki."

    # --- WYWOŁANIA AI ---
    res_biz = call_groq(prompt_biznes, body, MODEL_BIZ)
    res_tyl = call_groq(prompt_tyler, body, MODEL_TYLER)

    # --- BUDOWANIE ODPOWIEDZI ---
    response_data = {
        "biznes": None,
        "zwykly": None
    }

    if res_biz:
        response_data["biznes"] = {
            "reply_html": f"<p>{res_biz}</p><img src='cid:emotka_cid'>",
            "emoticon": {
                "base64": get_base64_image(),
                "content_type": "image/png",
                "filename": "smile.png"
            },
            "pdf": {
                "base64": generate_pdf_dummy(),
                "filename": "Oferta_Notariusz.pdf"
            }
        }

    if res_tyl:
        response_data["zwykly"] = {
            "reply_html": f"<p><b>Tyler mówi:</b> {res_tyl}</p>"
        }

    return jsonify(response_data), 200

# ============================
# 7. START SERWERA
# ============================

if __name__ == "__main__":
    # Diagnostyka przy starcie
    debug_token()

    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
