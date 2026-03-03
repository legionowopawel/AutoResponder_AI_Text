"""
responders/nawiazanie.py
Responder NAWIĄZANIE — analizuje historię konwersacji z nadawcą.

Przepływ:
  1. Apps Script wysyła poprzednią wiadomość (previous_body, previous_subject)
     razem z webhookiem — jeśli była w Google Sheets
  2. Jeśli previous_body istnieje → wysyłamy do DeepSeek:
     obecna wiadomość + poprzednia + instrukcja z prompt_nawiazanie.txt
  3. DeepSeek wywołany ASYNCHRONICZNIE z timeout 25s — jeśli nie zdąży,
     webhook odpowiada normalnie bez sekcji nawiązania (brak blokowania)
  4. Render zwraca sekcję 'nawiazanie' → Apps Script wysyła osobny email

Wymagane pola w webhooku (z Apps Script):
  sender           — adres email nadawcy
  sender_name      — imię i nazwisko z nagłówka From (np. "Jan Kowalski")
  previous_body    — treść ostatniej wiadomości od tego nadawcy (lub null)
  previous_subject — temat ostatniej wiadomości (lub null)
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from flask import current_app

from core.ai_client import call_groq as call_deepseek, MODEL_TYLER

# ── Stałe ─────────────────────────────────────────────────────────────────────
# Maksymalny czas oczekiwania na DeepSeek — nie blokujemy webhooka dłużej niż to
DEEPSEEK_TIMEOUT_SEC = 25

# ── Ścieżki ───────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
PROMPT_FILE = os.path.join(PROMPTS_DIR, "prompt_nawiazanie.txt")


# ── Wczytaj plik promptu ──────────────────────────────────────────────────────
def _load_prompt(fallback: str) -> str:
    try:
        with open(PROMPT_FILE, encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                return content
    except Exception as e:
        current_app.logger.warning("Nie można wczytać %s: %s", PROMPT_FILE, e)
    return fallback


# ── Buduj instrukcję dla DeepSeek ────────────────────────────────────────────
def _build_instruction(
    current_body: str,
    previous_body: str,
    previous_subject: str,
    sender: str,
    sender_name: str,
) -> str:
    template = _load_prompt(
        fallback=(
            "Porównaj dwie wiadomości od tej samej osoby.\n\n"
            "NADAWCA: [SENDER_NAME] <[SENDER_EMAIL]>\n\n"
            "POPRZEDNIA WIADOMOŚĆ (temat: [PREVIOUS_SUBJECT]):\n[PREVIOUS_BODY]\n\n"
            "OBECNA WIADOMOŚĆ:\n[CURRENT_BODY]\n\n"
            "Nawiąż do poprzedniej wiadomości, zwróć się po imieniu, "
            "opisz potrzeby tej osoby nawet te niewypowiedziane wprost."
        )
    )

    instruction = template.replace("[SENDER_NAME]",         sender_name or "")
    instruction = instruction.replace("[SENDER_EMAIL]",     sender or "")
    instruction = instruction.replace("[PREVIOUS_SUBJECT]", previous_subject or "brak tematu")
    instruction = instruction.replace("[PREVIOUS_BODY]",    previous_body[:1500])
    instruction = instruction.replace("[CURRENT_BODY]",     current_body[:1500])
    return instruction


# ── Wywołanie DeepSeek w osobnym wątku ───────────────────────────────────────
def _call_deepseek_async(instruction: str, app) -> str | None:
    """
    Wywołuje DeepSeek w osobnym wątku z app context.
    Zwraca wynik lub None przy błędzie.
    """
    with app.app_context():
        return call_deepseek(instruction, "", MODEL_TYLER)


# ── Główna funkcja responderu ─────────────────────────────────────────────────
def build_nawiazanie_section(
    body: str,
    previous_body: str | None,
    previous_subject: str | None,
    sender: str = "",
    sender_name: str = "",
) -> dict:
    """
    Buduje sekcję 'nawiazanie'.

    Jeśli brak previous_body — zwraca has_history=False i pusty reply_html.
    Jeśli jest historia — wywołuje DeepSeek asynchronicznie z timeout 25s.
    Jeśli DeepSeek nie odpowie w czasie — zwraca has_history=False zamiast
    blokować cały webhook przez 3 minuty.
    """

    # Brak historii — cicho, nic nie robimy
    if not previous_body or not previous_body.strip():
        current_app.logger.info(
            "Nawiązanie: brak historii dla %s <%s> — pomijam",
            sender_name or "(brak imienia)", sender
        )
        return {
            "has_history": False,
            "reply_html":  "",
            "analysis":    "",
        }

    current_app.logger.info(
        "Nawiązanie: znaleziono historię dla %s <%s> | poprzedni temat: %s",
        sender_name or "(brak imienia)", sender, previous_subject
    )

    # Buduj instrukcję
    instruction = _build_instruction(
        body, previous_body, previous_subject or "",
        sender, sender_name
    )

    # Wywołaj DeepSeek asynchronicznie z timeout
    from flask import current_app as flask_app
    app = flask_app._get_current_object()

    result = None
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_deepseek_async, instruction, app)
            result = future.result(timeout=DEEPSEEK_TIMEOUT_SEC)

    except FutureTimeoutError:
        current_app.logger.warning(
            "Nawiązanie: DeepSeek timeout (%ds) dla %s — pomijam sekcję",
            DEEPSEEK_TIMEOUT_SEC, sender
        )
        return {
            "has_history": False,
            "reply_html":  "",
            "analysis":    "",
        }
    except Exception as e:
        current_app.logger.warning(
            "Nawiązanie: błąd DeepSeek dla %s: %s — pomijam sekcję",
            sender, str(e)[:80]
        )
        return {
            "has_history": False,
            "reply_html":  "",
            "analysis":    "",
        }

    if not result or not result.strip():
        current_app.logger.warning(
            "Nawiązanie: DeepSeek nie zwrócił analizy dla %s", sender
        )
        return {
            "has_history": True,
            "reply_html":  "<p>Nie udało się wygenerować analizy nawiązania.</p>",
            "analysis":    "",
        }

    # Wyczyść wynik
    analysis = re.sub(r'\n{3,}', '\n\n', result.strip())
    analysis_html = analysis.replace("\n", "<br>")

    current_app.logger.info(
        "Nawiązanie: analiza gotowa dla %s <%s> (%.150s...)",
        sender_name or "(brak)", sender, analysis
    )

    reply_html = (
        "<p><strong>Nawiązanie do poprzedniej rozmowy:</strong></p>"
        f"<p>{analysis_html}</p>"
    )

    return {
        "has_history": True,
        "reply_html":  reply_html,
        "analysis":    analysis,
    }
