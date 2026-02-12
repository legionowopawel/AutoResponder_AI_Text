import os
import json
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- KONFIGURACJA POBIERANA Z RENDER ---
MODEL_BIZ = os.getenv("MODEL_BIZ", "llama-3.3-70b-versatile")
MODEL_TYLER = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", 512))
GROQ_API_KEY = "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"

def get_emoticon_data(emotion_name):
    """Obsługuje Twoje pliki PNG."""
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
    file_name = emocje_map.get(emotion_name.lower(), "twarz_spokoj.png")
    path = os.path.join("emotki", file_name)
    
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            return {"filename": file_name, "content_type": "image/png", "base64": b64, "cid": "emotka_cid"}
    return None

def get_pdf_info(filename):
    """Pobiera PDF z folderu pdfy."""
    clean_name = filename.strip()
    path = os.path.join("pdfy", clean_name)
    if not os.path.exists(path):
        path = os.path.join("pdfy", "error.pdf")
        clean_name = "error.pdf"
    with open(path, "rb") as f:
        return {"filename": clean_name, "base64": base64.b64encode(f.read()).decode("utf-8")}

def call_groq(system_prompt, user_msg, model_name):
    """Wywołuje Groq w formacie JSON Chat Completion."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    # UWAGA: Aby JSON działał, słowo 'JSON' musi być w prompcie
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt + " ALWAYS return response in VALID JSON format."},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.6,
        "max_tokens": GROQ_MAX_TOKENS,
        "response_format": {"type": "json_object"}
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        res_json = r.json()
        
        if 'choices' not in res_json:
            app.logger.error(f"GROQ ERROR ({model_name}): {res_json}")
            return None
        
        content = res_json['choices'][0]['message']['content']
        return json.loads(content)
    except Exception as e:
        app.logger.error(f"EXCEPTION: {str(e)}")
        return None

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    user_msg = data.get("body", "")
    result = {}

    # 1. BIZNESOWY (70B)
    try:
        with open("prompt_biznesowy.txt", "r", encoding="utf-8") as f:
            biz_prompt = f.read()
        biz_res = call_groq(biz_prompt, user_msg, MODEL_BIZ)
        if biz_res:
            pdf_name = biz_res.get("plik_pdf", "error.pdf")
            result["biznes"] = {
                "reply_html": f"<div>{biz_res.get('odpowiedz', '')}<br><br><small>Kancelaria Notarialna | Model: {MODEL_BIZ}</small></div>",
                "pdf": get_pdf_info(pdf_name)
            }
    except Exception as e:
        app.logger.error(f"Biznes error: {e}")

    # 2. TYLER (8B - szybki i ma duże limity)
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            tyler_prompt = f.read()
        tyler_res = call_groq(tyler_prompt, user_msg, MODEL_TYLER)
        if tyler_res:
            emotion = tyler_res.get("emocja", "spokoj")
            emot_data = get_emoticon_data(emotion)
            reply_html = (
                f"<div>{tyler_res.get('tekst', '').replace(chr(10), '<br>')}"
                f"<br><br><img src='cid:emotka_cid' width='80'><br>"
                f"<small>Model: {MODEL_TYLER}</small></div>"
            )
            result["zwykly"] = {
                "reply_html": reply_html,
                "emoticon": emot_data,
                "pdf": get_pdf_info("error.pdf")
            }
    except Exception as e:
        app.logger.error(f"Tyler error: {e}")

    return jsonify(result), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)