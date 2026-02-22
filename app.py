#!/usr/bin/env python3
# app.py - webhook backend dla Google Apps Script
import os
import base64
import requests
import json
import re
from flask import Flask, request, jsonify

app = Flask(__name__)


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
                for key in ("odpowiedz_tekstowa", "reply", "answer", "text", "message", "reply_html", "content"):
                    if key in obj:
                        val = obj[key]
                        return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
                # jeśli dict z jedną wartością, zwróć ją
                if len(obj) == 1:
                    val = next(iter(obj.values()))
                    return val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
            if isinstance(obj, list):
                return "\n".join(str(x) for x in obj)
        except Exception:
            pass
    # Jeśli JSON jest na początku, a potem jest tekst, usuń wrapper JSON
    if txt.startswith("{") and "}" in txt:
        try:
            end = txt.index("}") + 1
            maybe_json = txt[:end]
            remainder = txt[end:].strip()
            try:
                json.loads(maybe_json)
                if remainder:
                    return remainder
            except Exception:
                # heurystyka: usuń leading JSON i zwróć resztę
                return txt[end:].strip()
        except Exception:
            pass
    return raw_text


def extract_clean_text(text: str) -> str:
    """
    Z odpowiedzi zawierającej JSON + inne treści wyciąga pole 'odpowiedz_tekstowa',
    jeśli jest dostępne. W przeciwnym razie zwraca przycięty tekst.
    """
    if not text:
        return ""
    txt = text.strip()
    match = re.search(r'\{.*\}', txt, re.DOTALL)
    if not match:
        return txt
    try:
        obj = json.loads(match.group(0))
        if isinstance(obj, dict) and "odpowiedz_tekstowa" in obj:
            val = obj["odpowiedz_tekstowa"]
            return val.strip() if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        return txt
    except Exception:
        return txt


# Konfiguracja
GROQ_API_KEY = os.getenv("API_KEY_DEEPSEEK")
MODEL_BIZ = os.getenv("MODEL_BIZ", "llama-3.3-70b-versatile")
MODEL_TYLER = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

EMOTKI_DIR = os.path.join(os.path.dirname(__file__), "emotki")
PDF_DIR = os.path.join(os.path.dirname(__file__), "pdf_biznes")

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
            data = f.read()
            if not data:
                app.logger.warning("Plik istnieje, ale jest pusty: %s", path)
                return None
            return base64.b64encode(data).decode("ascii")
    except Exception as e:
        app.logger.warning("read_file_base64 failed for %s: %s", path, e)
        return None


def safe_emoticon_and_pdf_for(emotion_key):
    """Zwraca tuple (png_b64, pdf_b64); jeśli brak, używa error fallback."""
    png_name = f"{emotion_key}.png"
    pdf_name = f"{emotion_key}.pdf"

    png_path = os.path.join(EMOTKI_DIR, png_name)
    pdf_path = os.path.join(PDF_DIR, pdf_name)

    png_b64 = read_file_base64(png_path)
    pdf_b64 = read_file_base64(pdf_path)

    if not png_b64:
        png_b64 = read_file_base64(os.path.join(EMOTKI_DIR, f"{FALLBACK_EMOT}.png"))
    if not pdf_b64:
        pdf_b64 = read_file_base64(os.path.join(PDF_DIR, f"{FALLBACK_EMOT}.pdf"))

    return png_b64, pdf_b64


# Wywołanie Groq (tekstowe)
def call_groq(system_prompt: str, user_msg: str, model_name: str, timeout=20):
    if not GROQ_API_KEY:
        app.logger.error("Brak  API_KEY_DEEPSEEK")
        return None

    url = "https://api.deepseek.com/chat/completions"
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
        "temperature": 0.0,
        "max_tokens": 300  # ograniczamy odpowiedź
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            app.logger.warning("GROQ non-200 (%s): %s", resp.status_code, resp.text[:500])
            return None
        try:
            data = resp.json()
        except Exception:
            # jeśli odpowiedź nie jest JSONem, zwróć surowy tekst
            return sanitize_model_output(resp.text)
        # standardowy format OpenAI-like
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            # fallback: spróbuj inne pola
            content = None
            if isinstance(data, dict):
                for key in ("content", "text", "message", "reply"):
                    if key in data and isinstance(data[key], str):
                        content = data[key]
                        break
            if not content:
                content = json.dumps(data, ensure_ascii=False)
        return sanitize_model_output(content)
    except Exception as e:
        app.logger.exception("Błąd wywołania Groq: %s", e)
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
    token = res.strip().lower()
    for e in EMOTIONS:
        if e in token:
            return e
    return FALLBACK_EMOT


# Prosty helper: wykryj temat notarialny i wybierz pasujący pdf
def detect_notarial_topic_and_choose_pdf(body_text: str):
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
    body_text = body_text.replace("\n", "<br>")
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
    emotion = detect_emotion_via_model(body)

    prompt_txt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    if os.path.exists(prompt_txt_path):
        with open(prompt_txt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    else:
        prompt_template = "Odpowiedz krótko i empatycznie na poniższy tekst: {{USER_TEXT}}"

    prompt_for_model = prompt_template.replace("{{USER_TEXT}}", body[:3000])

    res_tyler_raw = call_groq(prompt_for_model, body, MODEL_TYLER)
    res_tyler_clean = sanitize_model_output(res_tyler_raw) if res_tyler_raw else ""
    res_tyler = extract_clean_text(res_tyler_clean)
    if not res_tyler:
        res_tyler = "Przepraszam, wystąpił problem z generowaniem odpowiedzi."

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

    res_biz_raw = call_groq(prompt_biz_for_model, body, MODEL_BIZ)
    res_biz_clean = sanitize_model_output(res_biz_raw) if res_biz_raw else ""
    res_biz = extract_clean_text(res_biz_clean)
    if not res_biz:
        res_biz = "Przepraszam, wystąpił problem z generowaniem odpowiedzi biznesowej."

    # wykryj temat i wybierz pdf (z logowaniem i fallbackem)
    topic_pdf_key = detect_notarial_topic_and_choose_pdf(body)
    pdf_path = os.path.join(PDF_DIR, f"{topic_pdf_key}.pdf")
    pdf_b64_biz = read_file_base64(pdf_path)
    app.logger.info("BUSINESS PDF try: %s ; base64 present? %s", pdf_path, bool(pdf_b64_biz))

    chosen_filename = f"{topic_pdf_key}.pdf"
    if not pdf_b64_biz:
        fallback_key = "kontakt_godziny_pracy_notariusza_podstawowe_informacje"
        fallback_path = os.path.join(PDF_DIR, f"{fallback_key}.pdf")
        app.logger.warning("Brak PDF dla %s, próbuję fallback: %s", topic_pdf_key, fallback_path)
        pdf_b64_biz = read_file_base64(fallback_path)
        app.logger.info("Fallback PDF present? %s", bool(pdf_b64_biz))
        chosen_filename = f"{fallback_key}.pdf" if pdf_b64_biz else chosen_filename

    biz_section = {
        "reply_html": build_html_reply(
            res_biz + ("\n\nRozpoznane zagadnienia: (zobacz załącznik)" if topic_pdf_key == "UNKNOWN" else "")
        ),
        "pdf": {
            "base64": pdf_b64_biz,
            "filename": chosen_filename
        },
        "topic": topic_pdf_key if pdf_b64_biz else "UNKNOWN"
    }
    if not pdf_b64_biz:
        biz_section["notes"] = "Brak pliku PDF na serwerze; proszę o kontakt."

    response_data = {
        "biznes": biz_section,
        "zwykly": emotional_section
    }

    app.logger.info(
        "Response data prepared: biznes.pdf present? %s, zwykly.pdf present? %s",
        bool(response_data["biznes"].get("pdf", {}).get("base64")),
        bool(response_data["zwykly"].get("pdf", {}).get("base64"))
    )

    return jsonify(response_data), 200


if __name__ == "__main__":
    if not GROQ_API_KEY:
        app.logger.warning(" API_KEY_DEEPSEEK nie ustawiony ( API_KEY_DEEPSEEK). Backend będzie działał, ale wywołania AI zwrócą None.")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
