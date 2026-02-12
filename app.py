import os
import re
import json
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Konfiguracja - Zmieniamy na mniejszy model dla Tyler'a, żeby oszczędzać limity!
# Model 70b zostawiamy dla biznesu, 8b dla zabawy (jest 10x szybszy i ma wyższe limity).
MODEL_BIZ = "llama-3.3-70b-versatile"
MODEL_TYLER = "llama-3.1-8b-instant" 
GROQ_MAX_TOKENS = 1024

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

def call_groq(system_prompt, user_msg, model_name):
    """Wywołuje Groq z lepszą obsługą błędów."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt + " Answer in JSON format."},
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
            # TO WYPISZE BŁĄD W LOGACH RENDERA
            app.logger.error(f"GROQ ERROR ({model_name}): {json.dumps(res_json)}")
            return None, model_name

        content = res_json['choices'][0]['message']['content']
        return json.loads(content), model_name
    except Exception as e:
        app.logger.error(f"EXCEPTION ({model_name}): {str(e)}")
        return None, model_name

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    user_msg = data.get("body", "")
    result = {}

    # --- 1. BIZNESOWY ---
    try:
        with open("prompt_biznesowy.txt", "r", encoding="utf-8") as f:
            biz_prompt = f.read()
        biz_res, _ = call_groq(biz_prompt, user_msg, MODEL_BIZ)
        if biz_res:
            pdf_name = biz_res.get("plik_pdf", "error.pdf")
            result["biznes"] = {
                "reply_html": f"<div>{biz_res.get('odpowiedz', '')}<br><br><small>Kancelaria Notarialna</small></div>",
                "pdf": get_pdf_info(pdf_name)
            }
    except: pass

    # --- 2. ZWYKŁY (Tyler) ---
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            tyler_prompt = f.read()
        tyler_res, tyler_src = call_groq(tyler_prompt, user_msg, MODEL_TYLER)
        if tyler_res:
            emot_data = get_emoticon_data(tyler_res.get("emocja", "spokoj"))
            reply_html = f"<div>{tyler_res.get('tekst', '').replace(chr(10), '<br>')}<br><br><img src='cid:emotka_cid' width='80'><br><small>Model: {tyler_src}</small></div>"
            result["zwykly"] = {
                "reply_html": reply_html,
                "emoticon": emot_data,
                "pdf": get_pdf_info("error.pdf")
            }
    except: pass

    return jsonify(result), 200

def get_pdf_info(filename):
    path = os.path.join("pdfy", filename.strip())
    if not os.path.exists(path): path = os.path.join("pdfy", "error.pdf")
    with open(path, "rb") as f:
        return {"filename": os.path.basename(path), "base64": base64.b64encode(f.read()).decode("utf-8")}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)