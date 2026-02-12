import os
import re
import json
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- KONFIGURACJA ---
# Zwiększone limity tokenów, aby wiersze i odpowiedzi biznesowe były kompletne
GROQ_MAX_TOKENS = 1024 

def get_emoticon_data(emotion_name):
    """Mapuje emocję na Twoje konkretne pliki PNG z katalogu emotki/."""
    emocje_map = {
        "radosc": "twarz_radosc.png",
        "smutek": "twarz_smutek.png",
        "zlosc": "twarz_zlosc.png",
        "lek": "twarz_lek.png",
        "nuda": "twarz_nuda.png",
        "spokoj": "twarz_spokoj.png",
        "zaskoczenie": "twarz_zaskoczenie.png",
        "error": "error.png"
    }
    
    # Jeśli AI poda emocję spoza listy, używamy 'spokoj' jako domyślnej
    file_name = emocje_map.get(emotion_name.lower(), "twarz_spokoj.png")
    path = os.path.join("emotki", file_name)
    
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            return {
                "filename": file_name, 
                "content_type": "image/png", 
                "base64": b64, 
                "cid": "emotka_cid" # Stały identyfikator dla HTML
            }
    return None

def get_pdf_info(filename):
    """Pobiera plik PDF z folderu pdfy i zamienia na base64."""
    # Oczyszczanie nazwy (na wypadek gdyby AI dodało spacje lub numery)
    clean_name = filename.strip().lower()
    path = os.path.join("pdfy", clean_name)
    
    # Jeśli plik nie istnieje, wyślij error.pdf
    if not os.path.exists(path):
        app.logger.warning(f"Nie znaleziono pliku: {path}. Wysyłam error.pdf")
        path = os.path.join("pdfy", "error.pdf")
        clean_name = "error.pdf"
        
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"filename": clean_name, "base64": b64}
    except Exception as e:
        app.logger.error(f"Błąd odczytu PDF: {e}")
        return None

def call_groq(system_prompt, user_msg):
    """Wywołuje Groq AI w trybie JSON."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.6,
        "max_tokens": GROQ_MAX_TOKENS,
        "response_format": {"type": "json_object"} # Wymuszenie formatu JSON
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        content = r.json()['choices'][0]['message']['content']
        return json.loads(content), "GROQ_LLAMA_3.3_70B"
    except Exception as e:
        app.logger.error(f"Błąd Groq/JSON: {e}")
        return None, None

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    user_msg = data.get("body", "")
    result = {}

    # --- 1. ODPOWIEDŹ BIZNESOWA (Notariusz) ---
    try:
        with open("prompt_biznesowy.txt", "r", encoding="utf-8") as f:
            biz_prompt = f.read()
        
        biz_res, biz_src = call_groq(biz_prompt, user_msg)
        if biz_res:
            pdf_name = biz_res.get("plik_pdf", "error.pdf")
            result["biznes"] = {
                "reply_html": f"<div>{biz_res.get('odpowiedz', '')}<br><br><small>Kancelaria Notarialna | Model: {biz_src}</small></div>",
                "pdf": get_pdf_info(pdf_name)
            }
    except Exception as e:
        app.logger.error(f"Błąd w sekcji biznesowej: {e}")

    # --- 2. ODPOWIEDŹ ZWYKŁA (Tyler Durden) ---
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            tyler_prompt = f.read()
            
        tyler_res, tyler_src = call_groq(tyler_prompt, user_msg)
        if tyler_res:
            emotion = tyler_res.get("emocja", "spokoj")
            emot_data = get_emoticon_data(emotion)
            
            # Budowanie HTML z obrazkiem inline
            reply_html = (
                f"<div>{tyler_res.get('tekst', '').replace(chr(10), '<br>')}"
                f"<br><br><img src='cid:emotka_cid' width='80'><br>"
                f"<small>Model: {tyler_src}</small></div>"
            )
            
            result["zwykly"] = {
                "reply_html": reply_html,
                "emoticon": emot_data,
                "pdf": get_pdf_info("error.pdf") # Zgodnie z Twoim życzeniem
            }
    except Exception as e:
        app.logger.error(f"Błąd w sekcji Tyler: {e}")

    return jsonify(result), 200

if __name__ == '__main__':
    # Render używa portu 10000
    app.run(host='0.0.0.0', port=10000)