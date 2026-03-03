"""
responders/zwykly.py
Responder emocjonalny — Tyler Durden.
Wykrywa emocję, generuje odpowiedź tekstową, dołącza emotkę PNG i PDF.
"""
import os
from flask import current_app

from core.ai_client  import call_deepseek, extract_clean_text, sanitize_model_output, MODEL_TYLER
from core.files      import read_file_base64, load_prompt
from core.html_builder import build_html_reply

# Katalog z emotkami i PDF-ami emocji
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMOTKI_DIR = os.path.join(BASE_DIR, "emotki")
PDF_DIR    = os.path.join(BASE_DIR, "pdf_biznes")

EMOTIONS = [
    "twarz_lek",
    "twarz_nuda",
    "twarz_radosc",
    "twarz_smutek",
    "twarz_spokoj",
    "twarz_zaskoczenie",
    "twarz_zlosc",
]
FALLBACK_EMOT = "error"


def detect_emotion(body_text: str) -> str:
    """Pyta model o emocję i zwraca jedną z etykiet z listy EMOTIONS."""
    prompt = (
        "Na podstawie poniższego tekstu wybierz dokładnie jedną z następujących "
        f"etykiet emocji (bez dodatkowego tekstu): {', '.join(EMOTIONS)}; "
        f"jeśli żadna nie pasuje, odpowiedz: {FALLBACK_EMOT}.\n\n"
        f"Tekst:\n{body_text}\n\nOdpowiedź:"
    )
    res = call_deepseek("Detektor emocji (zwróć tylko jedną etykietę)", prompt, MODEL_TYLER)
    if not res:
        return FALLBACK_EMOT
    token = res.strip().lower()
    for e in EMOTIONS:
        if e in token:
            return e
    return FALLBACK_EMOT


def _get_emoticon_and_pdf(emotion_key: str):
    """Zwraca (png_b64, pdf_b64) dla danej emocji, z fallbackiem na error."""
    png_b64 = read_file_base64(os.path.join(EMOTKI_DIR, f"{emotion_key}.png"))
    pdf_b64 = read_file_base64(os.path.join(PDF_DIR,    f"{emotion_key}.pdf"))

    if not png_b64:
        png_b64 = read_file_base64(os.path.join(EMOTKI_DIR, f"{FALLBACK_EMOT}.png"))
    if not pdf_b64:
        pdf_b64 = read_file_base64(os.path.join(PDF_DIR,    f"{FALLBACK_EMOT}.pdf"))

    return png_b64, pdf_b64


def build_zwykly_section(body: str) -> dict:
    """
    Buduje sekcję 'zwykly' odpowiedzi:
    - wykrywa emocję
    - generuje odpowiedź przez model (prompt.txt)
    - dołącza emotkę i PDF
    """
    emotion = detect_emotion(body)

    prompt_template = load_prompt(
        "prompt.txt",
        fallback="Odpowiedz krótko i empatycznie na poniższy tekst: {{USER_TEXT}}"
    )
    prompt_for_model = prompt_template.replace("{{USER_TEXT}}", body[:3000])

    res_raw   = call_deepseek(prompt_for_model, "", MODEL_TYLER)
    res_clean = sanitize_model_output(res_raw) if res_raw else ""
    res_text  = extract_clean_text(res_clean)
    if not res_text:
        res_text = "Przepraszam, wystąpił problem z generowaniem odpowiedzi."

    png_b64, pdf_b64 = _get_emoticon_and_pdf(emotion)

    return {
        "reply_html": build_html_reply(res_text),
        "emoticon": {
            "base64":       png_b64,
            "content_type": "image/png",
            "filename":     f"{emotion}.png",
        },
        "pdf": {
            "base64":   pdf_b64,
            "filename": f"{emotion}.pdf",
        },
        "detected_emotion": emotion,
    }
