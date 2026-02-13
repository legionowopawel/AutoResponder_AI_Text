#!/usr/bin/env python3
# app.py - webhook backend dla Google Apps Script
import os
import base64
import requests
from flask import Flask, request, jsonify

import json

def sanitize_model_output(raw_text: str) -> str:
    """
    Jeśli model zwrócił JSON lub JSON + tekst, wyciągnij właściwy tekst.
    Zwraca czysty tekst odpowiedzi.
    """
    if not raw_text:
        return ""
    txt = raw_text.strip()
    # Jeśli cały tekst jest JSONem, spróbuj sparsować i wyciągnąć typowe pola
    if txt.startswith("{") or txt.startswith("["):
        try:
            obj = json.loads(txt)
            if isinstance(obj, dict):
                for key in ("odpowiedz_tekstowa", "reply", "answer", "text", "message", "reply_html"):
                    if key in obj:
                        return str(obj[key])
                # jeśli dict z jedną wartością, zwróć ją
                if len(obj) == 1:
                    return str(next(iter(obj.values())))
            if isinstance(obj, list):
                return "\n".join(str(x) for x in obj)
        except Exception:
            pass
    # Jeśli JSON jest na początku, a potem jest tekst, usuń wrapper JSON
    if txt.startswith("{") and "}" in txt:
        try:
            end = txt.index("}") + 1
            maybe_json = txt[:end]
            obj = json.loads(maybe_json)
            remainder = txt[end:].strip()
            if remainder:
                return remainder
        except Exception:
            pass
    return raw_text

app = Flask(__name__)

# Konfiguracja
GROQ_API_KEY = os.getenv("KLUCZ_GROQ")
MODEL_BIZ = os.getenv("MODEL_BIZ", "llama-3.3-70b-versatile")
MODEL_TYLER = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

EMOTKI_DIR = os.path.join(os.path.dirname(__file__), "emotki")
PDF_DIR = os.path.join(os.path.dirname(__file__), "pdf")

EMOTIONS = [
    "twarz_lek",
    "twarz_nuda",
    "twarz_radosc",
    "twarz_smutek",
    "twarz_spokoj",
    "twarz_zaskoczenie",
    "twarz_zlosc"
]
FALLBACK_EMOT = "error"

# Pomocniczne
def read_file_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None

def safe_emoticon_and_pdf_for(emotion_key):
    """Zwraca dict z base64 dla PNG i PDF; jeśli brak, używa error."""
    png_name = f"{emotion_key}.png"
    pdf_name = f"{emotion_key}.pdf"

    png_path = os.path.join(EMOTKI_DIR, png_name)
    pdf_path = os.path.join(PDF_DIR, pdf_name)

    png_b64 = read_file_base64(png_path)
    pdf_b64 = read_file_base64(pdf_path)

    if not png_b64 or not pdf_b64:
        # fallback
        png_b64 = read_file_base64(os.path.join(EMOTKI_DIR, f"{FALLBACK_EMOT}.png"))
        pdf_b64 = read_file_base64(os.path.join(PDF_DIR, f"{FALLBACK_EMOT}.pdf"))

    return png_b64, pdf_b64

# Wywołanie Groq (tekstowe)
def call_groq(system_prompt: str, user_msg: str, model_name: str, timeout=20):
    if not GROQ_API_KEY:
        app.logger.error("Brak KLUCZ_GROQ")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ],
        "temperature": 0.0
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            app.logger.warning(f"GROQ non-200 ({resp.status_code}): {resp.text}")
            return None
        data = resp.json()
        # Bez wymuszania JSON — oczekujemy zwykłego tekstu
        content = data["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        app.logger.exception("Błąd wywołania Groq")
        return None

# Prosty helper: poproś model o jednowyrazowe rozpoznanie emocji spośród listy
def detect_emotion_via_model(body_text: str):
    prompt = (
        "Na podstawie poniższego tekstu wybierz dokładnie jedną z następujących etykiet emocji "
        f"(bez dodatkowego tekstu): {', '.join(EMOTIONS)}; jeśli żadna nie pasuje, odpowiedz: {FALLBACK_EMOT}.\n\n"
        f"Tekst:\n{body_text}\n\nOdpowiedź:"
    )
    res = call_groq("Detektor emocji (zwróć tylko jedną etykietę)", prompt, MODEL_TYLER)
    if not res:
        return FALLBACK_EMOT
    # oczyszczanie
    token = res.strip().lower()
    for e in EMOTIONS:
        if e in token:
            return e
    return FALLBACK_EMOT

# Prosty helper: wykryj temat notarialny i wybierz pasujący pdf
def detect_notarial_topic_and_choose_pdf(body_text: str):
    # Model ma zwrócić krótką etykietę lub "UNKNOWN"
    prompt = (
        "Przeczytaj tekst klienta i rozpoznaj, który z poniższych tematów notarialnych jest najbardziej odpowiedni. "
        "Jeśli nie możesz jednoznacznie przypisać, odpowiedz: UNKNOWN.\n\n"
        "Tematy (przykładowe pliki PDF):\n"
        "- darowizna_mieszkania_lub_domu_obowiazki_podatkowe_i_formalne\n"
        "- dzial_spadku_umowny_krok_po_kroku_z_notariuszem\n"
        "- intercyza_umowa_majatkowa_malzenska_wyjasnienie_i_koszty\n"
        "- kontakt_godziny_pracy_notariusza_podstawowe_informacje\n"
        "- sprzedaz_nieruchomosci_mieszkanie_procedura_koszty_wymagane_dokumenty\n\n"
        f"Tekst:\n{body_text}\n\nOdpowiedź (jedna etykieta lub UNKNOWN):"
    )
    res = call_groq("Detektor tematu notarialnego (jedna etykieta lub UNKNOWN)", prompt, MODEL_BIZ)
    if not res:
        return "UNKNOWN"
    token = res.strip().lower()
    # mapowanie prostą heurystyką
    if "darowiz" in token:
        return "darowizna_mieszkania_lub_domu_obowiazki_podatkowe_i_formalne"
    if "spad" in token:
        return "dzial_spadku_umowny_krok_po_kroku_z_notariuszem"
    if "intercyz" in token or "intercyza" in token:
        return "intercyza_umowa_majatkowa_malzenska_wyjasnienie_i_koszty"
    if "kontakt" in token or "godzin" in token:
        return "kontakt_godziny_pracy_notariusza_podstawowe_informacje"
    if "sprzed" in token or "nieruchom" in token:
        return "sprzedaz_nieruchomosci_mieszkanie_procedura_koszty_wymagane_dokumenty"
    return "UNKNOWN"

# Formatowanie HTML zgodnie z wymaganiem (kursywa + zielona stopka)
def build_html_reply(body_text: str):
    # body_text powinien być już wygenerowany przez model (surowy)
    html = f"<p><i>{body_text}</i></p>\n"
    html += (
        "<p style=\"color:#0a8a0a; font-size:10px;\">"
        "Odpowiedź wygenerowana automatycznie przez system Script + Render.<br>"
        "Projekt dostępny na GitHub: https://github.com/legionowopawel/AutoResponder_AI_Text.git"
        "</p>"
    )
    return html

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    sender = data.get("from", "")
    subject = data.get("subject", "")
    body = data.get("body", "")

    if not body or not body.strip():
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    # --- EMOCJONALNA CZESC (Tyler / prompt.txt) ---
    # 1) wykryj emocję
    emotion = detect_emotion_via_model(body)

    # 2) wygeneruj treść odpowiedzi emocjonalnej (prompt.txt powinien być na serwerze)
    prompt_txt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    if os.path.exists(prompt_txt_path):
        with open(prompt_txt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    else:
        prompt_template = "Odpowiedz krótko i empatycznie na poniższy tekst: {{USER_TEXT}}"

    # wstaw treść użytkownika do promptu
    prompt_for_model = prompt_template.replace("{{USER_TEXT}}", body[:3000])

    res_tyler = call_groq(prompt_for_model, body, MODEL_TYLER)
    res_tyler = sanitize_model_output(res_tyler)
    if not res_tyler:
        res_tyler = "Przepraszam, wystąpił problem z generowaniem odpowiedzi."

    # załączniki dla emocji
    png_b64, pdf_b64 = safe_emoticon_and_pdf_for(emotion)

    emotional_section = {
        "reply_html": build_html_reply(res_tyler),
        "emoticon": {
            "base64": png_b64,
            "content_type": "image/png",
            "filename": f"{emotion}.png"
        },
        "pdf": {
            "base64": pdf_b64,
            "filename": f"{emotion}.pdf"
        },
        "detected_emotion": emotion
    }

    # --- BIZNESOWA CZESC (Notariusz / prompt_biznesowy.txt) ---
    prompt_biz_path = os.path.join(os.path.dirname(__file__), "prompt_biznesowy.txt")
    if os.path.exists(prompt_biz_path):
        with open(prompt_biz_path, "r", encoding="utf-8") as f:
            prompt_biz_template = f.read()
    else:
        prompt_biz_template = "Jesteś uprzejmym Notariuszem. Przygotuj profesjonalną odpowiedź: {{USER_TEXT}}"

    prompt_biz_for_model = prompt_biz_template.replace("{{USER_TEXT}}", body[:3000])
    res_biz = call_groq(prompt_biz_for_model, body, MODEL_BIZ)
    res_biz = sanitize_model_output(res_biz)
    if not res_biz:
        res_biz = "Przepraszam, wystąpił problem z generowaniem odpowiedzi biznesowej."

    # wykryj temat i wybierz pdf
    topic_pdf_key = detect_notarial_topic_and_choose_pdf(body)
    if topic_pdf_key == "UNKNOWN":
        # fallback: dołącz kontaktowy PDF
        pdf_key = "kontakt_godziny_pracy_notariusza_podstawowe_informacje"
        pdf_b64_biz = read_file_base64(os.path.join(PDF_DIR, f"{pdf_key}.pdf"))
        biz_section = {
            "reply_html": build_html_reply(res_biz + "\n\nRozpoznane zagadnienia: (zobacz załącznik)"),
            "pdf": {
                "base64": pdf_b64_biz,
                "filename": f"{pdf_key}.pdf"
            },
            "topic": "UNKNOWN",
            "notes": "Niejednoznaczny temat; proszę o kontakt w celu doprecyzowania."
        }
    else:
        pdf_b64_biz = read_file_base64(os.path.join(PDF_DIR, f"{topic_pdf_key}.pdf"))
        biz_section = {
            "reply_html": build_html_reply(res_biz),
            "pdf": {
                "base64": pdf_b64_biz,
                "filename": f"{topic_pdf_key}.pdf"
            },
            "topic": topic_pdf_key
        }

    response_data = {
        "biznes": biz_section,
        "zwykly": emotional_section
    }

    return jsonify(response_data), 200

if __name__ == "__main__":
    # diagnostyka tokena przy starcie
    if not GROQ_API_KEY:
        app.logger.warning("KLUCZ_GROQ nie ustawiony (KLUCZ_GROQ). Backend będzie działał, ale wywołania AI zwrócą None.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
