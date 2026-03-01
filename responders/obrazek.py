"""
responders/obrazek.py
Responder OBRAZEK — generuje 4-ujęciowy komiks AI z treści maila.

Używa Hugging Face Inference API z modelem FLUX.1-schnell.
Tokeny HF ustawiasz w Render jako zmienne środowiskowe:
  HF_TOKEN, HF_TOKEN1, HF_TOKEN2, HF_TOKEN3, HF_TOKEN4
Program próbuje tokenów po kolei — jeśli jeden nie działa, bierze następny.
Styl obrazka pochodzi z pliku: prompts/prompt_obrazek.txt

Parametry generowania:
  - num_inference_steps: 30
  - guidance_scale:      3.5
"""

import os
import re
import base64
import requests
from flask import current_app

from core.ai_client import call_groq as call_deepseek, MODEL_TYLER

# ── Stałe ─────────────────────────────────────────────────────────────────────
HF_API_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "black-forest-labs/FLUX.1-schnell"
)
HF_STEPS    = 30
HF_GUIDANCE = 3.5
TIMEOUT_SEC = 60
MAX_PROMPT  = 500

BASE_DIR          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_STYLE_FILE = os.path.join(BASE_DIR, "prompts", "prompt_obrazek.txt")


# ── Wczytaj styl z pliku ──────────────────────────────────────────────────────
def _load_style() -> str:
    try:
        with open(PROMPT_STYLE_FILE, encoding="utf-8") as f:
            style = f.read().strip()
            if style:
                return style
    except Exception as e:
        current_app.logger.warning("Nie można wczytać prompt_obrazek.txt: %s", e)

    # Fallback
    return (
        "4-panel comic strip, black and white, thick ink lines, "
        "oversized heads, exaggerated expressions, minimal background, "
        "no text outside speech bubbles, cinematic storytelling left to right."
    )


# ── Skróć treść maila do promptu obrazkowego ─────────────────────────────────
def _build_image_prompt(body: str, style: str) -> str:
    """
    Używa Groq żeby wyciągnąć z maila TYLKO wizualny opis sceny po angielsku.
    Kluczowe: żadnego polskiego tekstu, żadnych instrukcji — tylko opis obrazu.
    """
    groq_instruction = (
        "Read the email below and extract the main visual scene it describes. "
        "Write a SHORT English image prompt (max 25 words) describing ONLY "
        "what should be VISIBLE in the picture: characters, setting, action, mood. "
        "Do NOT include any Polish words, instructions, questions, or explanations. "
        "Output only the visual scene description, nothing else.\n\n"
        "Email:\n" + body[:600]
    )

    try:
        res = call_deepseek(groq_instruction, "", MODEL_TYLER)
        if res and res.strip():
            # Usuń cudzysłowy, polskie znaki mogące się wkraść, nowe linie
            prompt = re.sub(r'["\'\n]', ' ', res.strip())
            prompt = prompt[:MAX_PROMPT]
            current_app.logger.info("Groq scene prompt: %s", prompt)
        else:
            raise ValueError("Pusta odpowiedź Groq")
    except Exception as e:
        current_app.logger.warning("Groq prompt generation failed: %s", e)
        # Fallback: pierwsze zdanie maila przetłumaczone na angielski przez drugi call
        first = re.split(r'[.!?\n]', body.strip())[0].strip()
        prompt = first[:150] if first else "two elderly people sitting by fireplace drinking tea"

    # Złącz opis sceny ze stylem komiksowym
    full_prompt = f"{prompt}. {style.strip()}"

    return full_prompt


# ── Zbierz dostępne tokeny z Render ──────────────────────────────────────────
def _get_hf_tokens() -> list:
    names  = ["HF_TOKEN", "HF_TOKEN1", "HF_TOKEN2", "HF_TOKEN3", "HF_TOKEN4"]
    tokens = []
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            tokens.append((name, val))
    return tokens


# ── Wywołaj HF API i pobierz PNG ─────────────────────────────────────────────
def _generate_image_hf(full_prompt: str) -> bytes:
    """
    Wysyła prompt do HF FLUX.1-schnell.
    Próbuje tokenów po kolei, przechodzi dalej przy każdym błędzie.
    """
    tokens = _get_hf_tokens()
    if not tokens:
        current_app.logger.error("Brak HF_TOKEN w zmiennych środowiskowych!")
        return b""

    payload = {
        "inputs": full_prompt,
        "parameters": {
            "num_inference_steps": HF_STEPS,
            "guidance_scale":      HF_GUIDANCE,
        },
    }

    current_app.logger.info(
        "HF FLUX — tokeny: %s | prompt: %.150s",
        [n for n, _ in tokens], full_prompt,
    )

    for name, token in tokens:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept":        "image/png",
        }
        current_app.logger.info("HF FLUX — próbuję token: %s", name)
        try:
            resp = requests.post(
                HF_API_URL, headers=headers, json=payload, timeout=TIMEOUT_SEC
            )

            if resp.status_code == 200:
                current_app.logger.info(
                    "HF FLUX sukces — token=%s | PNG %d B", name, len(resp.content)
                )
                return resp.content

            elif resp.status_code in (401, 403):
                current_app.logger.warning(
                    "HF FLUX token %s nieważny (%s) — próbuję następny",
                    name, resp.status_code
                )
            elif resp.status_code in (503, 529):
                current_app.logger.warning(
                    "HF FLUX token %s przeciążony (%s) — próbuję następny",
                    name, resp.status_code
                )
            else:
                current_app.logger.error(
                    "HF FLUX token %s błąd %s: %s — próbuję następny",
                    name, resp.status_code, resp.text[:200]
                )

        except requests.exceptions.Timeout:
            current_app.logger.warning(
                "HF FLUX token %s timeout po %d sek — próbuję następny",
                name, TIMEOUT_SEC
            )
        except Exception as e:
            current_app.logger.error(
                "HF FLUX token %s nieoczekiwany błąd: %s — próbuję następny",
                name, e
            )

    current_app.logger.error("HF FLUX — wszystkie tokeny (%d) zawiodły!", len(tokens))
    return b""


# ── Główna funkcja responderu ─────────────────────────────────────────────────
def build_obrazek_section(body: str) -> dict:
    """
    Buduje sekcję 'obrazek':
      1. Wczytuje styl komiksowy z prompts/prompt_obrazek.txt
      2. Groq wyciąga z maila wizualny opis sceny po angielsku
      3. Generuje 4-ujęciowy komiks PNG przez HF FLUX.1-schnell
      4. Zwraca base64 PNG + HTML dla nadawcy
    """
    if not body or not body.strip():
        return {
            "reply_html": "<p>Brak treści do wygenerowania obrazka.</p>",
            "image": {
                "base64":       None,
                "content_type": "image/png",
                "filename":     "komiks_ai.png",
            },
            "prompt_used": "",
        }

    style       = _load_style()
    full_prompt = _build_image_prompt(body, style)
    current_app.logger.info("Pełny prompt: %.250s", full_prompt)

    png_bytes = _generate_image_hf(full_prompt)
    png_b64   = base64.b64encode(png_bytes).decode("ascii") if png_bytes else None

    if png_b64:
        reply_html = (
            "<p>Na podstawie Twojej treści utworzyłem prompt i wygenerowałem obrazek:</p>"
            f"<p><em>{full_prompt}</em></p>"
        )
    else:
        reply_html = (
            "<p>Na podstawie Twojej treści utworzyłem prompt:</p>"
            f"<p><em>{full_prompt}</em></p>"
            "<p>Jednak wystąpił błąd po stronie serwisu AI podczas generowania obrazka. "
            "Spróbuj ponownie za chwilę.</p>"
        )

    current_app.logger.info(
        "Obrazek AI: sukces=%s | rozmiar=%d B", bool(png_b64), len(png_bytes)
    )

    return {
        "reply_html": reply_html,
        "image": {
            "base64":       png_b64,
            "content_type": "image/png",
            "filename":     "komiks_ai.png",
        },
        "prompt_used": full_prompt,
    }
