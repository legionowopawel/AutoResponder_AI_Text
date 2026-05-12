"""
core/wykrywaczplci.py

Detekcja tożsamości nadawcy emaila: imię, nazwisko, płeć.

ARCHITEKTURA:
  1. Reguły (zero tokenów) — wyciągnij kandydatów z FROM, podpisu, treści, emaila lokalnego
  2. DeepSeek #1 — ekstrakcja i ranking kandydatów
  3. DeepSeek #2 — weryfikacja, wybór, płeć
  4. Zapis raportu TXT na Google Drive (folder DRIVE_FOLDER_ID)
  5. Zwraca dict gotowy do nadpisania sender_name i gender w pipeline app.py

WYWOŁANIE z app.py (po odebraniu emaila, przed uruchomieniem pipeline):
    from core.wykrywaczplci import detect_sender_identity
    identity = detect_sender_identity(
        sender_email=sender,
        sender_name=sender_name,
        body=body,
    )
    sender_name = identity["sender_name"]   # nadpisz
    gender     = identity["gender"]          # nowa zmienna: "M", "K", "N"
"""

import os
import re
import json
import logging
import time
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

# ── Ścieżki ───────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_JSON = os.path.join(_BASE_DIR, "prompts", "wykrywaczplci.json")

# ── DeepSeek ──────────────────────────────────────────────────────────────────
_DEEPSEEK_KEY = os.getenv("API_KEY_DEEPSEEK", "").strip()
_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ── Drive folder (env var) ────────────────────────────────────────────────────
_DRIVE_FOLDER_PLEC = os.getenv("DRIVE_FOLDER_ID", "").strip()

# ── Próg pewności poniżej którego nie nadpisujemy sender_name ─────────────────
_PEWNOSC_PROG = 30


# ═══════════════════════════════════════════════════════════════════════════════
# POMOCNIKI
# ═══════════════════════════════════════════════════════════════════════════════


def _load_prompt_json() -> dict:
    try:
        with open(_PROMPT_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("[wykrywaczplci] Błąd ładowania wykrywaczplci.json: %s", e)
        return {}


def _deepseek_call(system: str, user: str, max_tokens: int = 800) -> str | None:
    if not _DEEPSEEK_KEY:
        logger.warning("[wykrywaczplci] Brak API_KEY_DEEPSEEK")
        return None
    try:
        resp = requests.post(
            _DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {_DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            },
            timeout=45,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        logger.error("[wykrywaczplci] DeepSeek HTTP %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("[wykrywaczplci] DeepSeek error: %s", e)
    return None


def _parse_json_safe(raw: str | None) -> dict:
    """Wyciąga pierwszy obiekt JSON z odpowiedzi."""
    if not raw:
        return {}
    # Znajdź { ... }
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        return json.loads(raw[start:end])
    except Exception as e:
        logger.warning("[wykrywaczplci] JSON parse error: %s | raw: %.200s", e, raw)
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# KROK 0 — REGUŁY (zero tokenów)
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_from_header(sender_email: str, sender_name: str) -> str:
    """Wyciąga część tekstową z pola FROM (nie adres email)."""
    # sender_name już jest wyciągnięty przez GAS — używamy go bezpośrednio
    name = (sender_name or "").strip()
    # Usuń potencjalny email jeśli GAS dał cały string "Jan K. <jan@x.com>"
    name = re.sub(r"<[^>]+>", "", name).strip()
    return name if len(name) > 1 else "__BRAK__"


def _extract_email_local(sender_email: str) -> str:
    """Odczytuje imię z lokalnej części adresu email (jan.kowalski → Jan Kowalski)."""
    try:
        local = sender_email.split("@")[0]
        # Podziel po . lub _ lub -
        parts = re.split(r"[._\-]", local)
        parts = [p.capitalize() for p in parts if len(p) > 1]
        if parts:
            return " ".join(parts)
    except Exception:
        pass
    return "__BRAK__"


def _extract_signature(body: str) -> str:
    """
    Szuka podpisu w ostatnich 8 liniach emaila.
    Wzorce: "pozdrawiam X", "- X", "Z poważaniem X", samotna linia z imieniem.
    """
    if not body:
        return "__BRAK__"
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    last_lines = lines[-8:] if len(lines) >= 8 else lines

    PATTERNS = [
        r"(?:pozdrawiam[,\s]+|pozdr[.,\s]+|regards[,\s]+|best regards[,\s]+|z poważaniem[,\s]+|serdecznie[,\s]+|do zobaczenia[,\s]+)([A-ZŁŚŻŹĆŃÓĄ][a-złśżźćńóąA-ZŁŚŻŹĆŃÓĄ\s\-]{1,40})",
        r"^[\-–—]+\s+([A-ZŁŚŻŹĆŃÓĄ][a-złśżźćńóąA-ZŁŚŻŹĆŃÓĄ\s\-]{1,40})\s*$",
        r"^([A-ZŁŚŻŹĆŃÓĄ][a-złśżźćńóąA-ZŁŚŻŹĆŃÓĄ\s\-]{1,40})\s*$",
    ]

    for line in reversed(last_lines):
        for pattern in PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                # Odrzuć zbyt długie (>3 słowa) lub zbyt krótkie
                words = candidate.split()
                if 1 <= len(words) <= 3:
                    return candidate
    return "__BRAK__"


def _extract_self_intro(body: str) -> str:
    """
    Szuka autoprzedstawienia w pierwszych 5 liniach.
    Wzorce: "tu Jan", "jestem Grzegorz", "mówi X", "pisze X".
    """
    if not body:
        return "__BRAK__"
    lines = [l.strip() for l in body.strip().splitlines() if l.strip()]
    first_lines = lines[:5]

    PATTERNS = [
        r"(?:tu\s+|jestem\s+|mówi\s+|pisze\s+|nazywam się\s+)([A-ZŁŚŻŹĆŃÓĄ][a-złśżźćńóąA-ZŁŚŻŹĆŃÓĄ\s\-]{1,40})",
        r"(?:here is|this is|it's|it is)\s+([A-Z][a-zA-Z\s\-]{1,40})",
    ]

    for line in first_lines:
        for pattern in PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                words = candidate.split()
                if 1 <= len(words) <= 3:
                    return candidate
    return "__BRAK__"


# ═══════════════════════════════════════════════════════════════════════════════
# KROK 1 — DEEPSEEK EKSTRAKCJA
# ═══════════════════════════════════════════════════════════════════════════════


def _deepseek_ekstrakcja(
    prompt_cfg: dict,
    sender_email: str,
    sender_name: str,
    body: str,
    rule_candidates: dict,
) -> dict:
    cfg = prompt_cfg.get("deepseek_1_ekstrakcja", {})
    system = cfg.get("system", "")

    body_preview = (body or "")[:600]
    last_lines = "\n".join(
        [l for l in (body or "").strip().splitlines() if l.strip()][-8:]
    )
    first_lines = "\n".join(
        [l for l in (body or "").strip().splitlines() if l.strip()][:5]
    )

    user = (
        f"FROM (nagłówek): {sender_name or '__BRAK__'}\n"
        f"EMAIL: {sender_email}\n"
        f"PIERWSZE 5 LINII TREŚCI:\n{first_lines}\n\n"
        f"OSTATNIE 8 LINII TREŚCI:\n{last_lines}\n\n"
        f"KANDYDACI ZNALEZIENI PRZEZ REGUŁY:\n"
        f"  podpis_koniec: {rule_candidates.get('podpis_koniec', '__BRAK__')}\n"
        f"  autoprzedstawienie: {rule_candidates.get('autoprzedstawienie', '__BRAK__')}\n"
        f"  pole_from: {rule_candidates.get('pole_from', '__BRAK__')}\n"
        f"  email_lokalny: {rule_candidates.get('email_lokalny', '__BRAK__')}\n\n"
        f"Odpowiedź (zacznij od {{):"
    )

    raw = _deepseek_call(system, user, max_tokens=600)
    return _parse_json_safe(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# KROK 2 — DEEPSEEK WERYFIKACJA
# ═══════════════════════════════════════════════════════════════════════════════


def _deepseek_weryfikacja(
    prompt_cfg: dict,
    ekstrakcja_result: dict,
    sender_email: str,
    body: str,
    rule_candidates: dict,
) -> dict:
    cfg = prompt_cfg.get("deepseek_2_weryfikacja", {})
    system = cfg.get("system", "")

    kandydaci = ekstrakcja_result.get("kandydaci", {})
    rekomendacja = ekstrakcja_result.get("rekomendacja_wstepna", "__BRAK__")

    user = (
        f"EMAIL NADAWCY: {sender_email}\n\n"
        f"WYNIKI EKSTRAKCJI (DeepSeek 1):\n"
        f"  podpis_koniec: {kandydaci.get('podpis_koniec', rule_candidates.get('podpis_koniec', '__BRAK__'))}\n"
        f"  autoprzedstawienie_tresc: {kandydaci.get('autoprzedstawienie_tresc', rule_candidates.get('autoprzedstawienie', '__BRAK__'))}\n"
        f"  pole_from: {kandydaci.get('pole_from', rule_candidates.get('pole_from', '__BRAK__'))}\n"
        f"  email_lokalny: {kandydaci.get('email_lokalny', rule_candidates.get('email_lokalny', '__BRAK__'))}\n"
        f"  rekomendacja_wstepna: {rekomendacja}\n\n"
        f"FRAGMENTY DOWODOWE:\n"
        f"  cytat_podpisu: {ekstrakcja_result.get('fragmenty_dowodowe', {}).get('cytat_podpisu', '__BRAK__')}\n"
        f"  cytat_autoprzedstawienia: {ekstrakcja_result.get('fragmenty_dowodowe', {}).get('cytat_autoprzedstawienia', '__BRAK__')}\n\n"
        f"Odpowiedź (zacznij od {{):"
    )

    raw = _deepseek_call(system, user, max_tokens=500)
    return _parse_json_safe(raw)


# ═══════════════════════════════════════════════════════════════════════════════
# KROK 3 — ZAPIS RAPORTU TXT NA DRIVE
# ═══════════════════════════════════════════════════════════════════════════════


def _build_report_txt(
    sender_email: str,
    sender_name_original: str,
    body: str,
    rule_candidates: dict,
    ekstrakcja: dict,
    weryfikacja: dict,
    sender_name_final: str,
    gender: str,
) -> str:
    wynik = weryfikacja.get("wynik", {})
    odrzucone = weryfikacja.get("odrzucone", {})
    kandydaci = ekstrakcja.get("kandydaci", {})
    fragmenty = ekstrakcja.get("fragmenty_dowodowe", {})

    ts = datetime.now(tz=timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S")
    body_preview = (body or "")[:300].replace("\n", " ")

    lines = [
        "=== WYKRYWACZ PŁCI — RAPORT ===",
        f"Data i czas: {ts}",
        f"Nadawca email: {sender_email}",
        "",
        "--- DANE WEJŚCIOWE ---",
        f"FROM (nagłówek sender_name): {sender_name_original}",
        f"Body (pierwsze 300 znaków): {body_preview}",
        "",
        "--- KANDYDACI (reguły) ---",
        f"podpis_koniec (reguły):        {rule_candidates.get('podpis_koniec', '__BRAK__')}",
        f"autoprzedstawienie (reguły):   {rule_candidates.get('autoprzedstawienie', '__BRAK__')}",
        f"pole_from (reguły):            {rule_candidates.get('pole_from', '__BRAK__')}",
        f"email_lokalny (reguły):        {rule_candidates.get('email_lokalny', '__BRAK__')}",
        "",
        "--- EKSTRAKCJA (DeepSeek 1) ---",
        f"podpis_koniec:             {kandydaci.get('podpis_koniec', '__BRAK__')}",
        f"autoprzedstawienie_tresc:  {kandydaci.get('autoprzedstawienie_tresc', '__BRAK__')}",
        f"pole_from:                 {kandydaci.get('pole_from', '__BRAK__')}",
        f"email_lokalny:             {kandydaci.get('email_lokalny', '__BRAK__')}",
        f"rekomendacja_wstepna:      {ekstrakcja.get('rekomendacja_wstepna', '__BRAK__')}",
        f"cytat_podpisu:             {fragmenty.get('cytat_podpisu', '__BRAK__')}",
        f"cytat_autoprzedstawienia:  {fragmenty.get('cytat_autoprzedstawienia', '__BRAK__')}",
        "",
        "--- WERYFIKACJA (DeepSeek 2) ---",
        f"Imię:            {wynik.get('imie', '__BRAK__')}",
        f"Nazwisko:        {wynik.get('nazwisko', '__BRAK__')}",
        f"Pełne:           {wynik.get('imie_nazwisko_pelne', '__BRAK__')}",
        f"Płeć:            {wynik.get('plec', 'N')}",
        f"Pewność:         {wynik.get('pewnosc', 0)}/100",
        f"Źródło:          {wynik.get('zrodlo', '__BRAK__')}",
        f"Uzasadnienie:    {wynik.get('uzasadnienie', '__BRAK__')}",
        f"Odrzucone:       {odrzucone.get('powod', '__BRAK__')}",
        "",
        "--- WYNIK KOŃCOWY ---",
        f"sender_name (nadpisany): {sender_name_final}",
        f"gender:                  {gender}",
    ]
    return "\n".join(lines)


def _save_report_to_drive(
    report_txt: str,
    imie: str,
    plec: str,
) -> str:
    """Zapisuje raport TXT na Drive. Zwraca URL lub pusty string."""
    if not _DRIVE_FOLDER_PLEC:
        logger.warning("[wykrywaczplci] Brak DRIVE_FOLDER_ID — nie zapisuję raportu")
        return ""
    try:
        try:
            from drive_utils import upload_file_to_drive
        except ImportError:
            logger.warning("[wykrywaczplci] Brak drive_utils — nie zapisuję raportu")
            return ""

        now = datetime.now(tz=timezone(timedelta(hours=2)))
        ts_str = now.strftime("%y_%m_%d_%H_%M")
        imie_clean = re.sub(r"[^a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]", "", (imie or "brak")).lower()
        filename = f"{imie_clean}_{plec.upper()}_{ts_str}.txt"

        import base64
        content_b64 = base64.b64encode(report_txt.encode("utf-8")).decode("ascii")

        result = upload_file_to_drive(
            file_data=content_b64,
            filename=filename,
            mime_type="text/plain",
            folder_id=_DRIVE_FOLDER_PLEC,
        )
        if result:
            url = result.get("url", "")
            logger.info("[wykrywaczplci] Raport zapisany: %s → %s", filename, url)
            return url
    except Exception as e:
        logger.error("[wykrywaczplci] Błąd zapisu raportu na Drive: %s", e)
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# GŁÓWNA FUNKCJA PUBLICZNA
# ═══════════════════════════════════════════════════════════════════════════════


def detect_sender_identity(
    sender_email: str,
    sender_name: str,
    body: str,
) -> dict:
    """
    Wykrywa tożsamość nadawcy emaila.

    Parametry:
        sender_email  — adres email (np. jan.kowalski@gmail.com)
        sender_name   — wartość z pola FROM nagłówka (np. "Jan K." lub "jan k.")
        body          — treść emaila jako plain text

    Zwraca dict:
        {
            "sender_name": str,          # imię/nazwisko do użycia przez respondery
            "gender": str,               # "M", "K", "N"
            "imie": str,                 # samo imię
            "nazwisko": str,             # samo nazwisko lub "__BRAK__"
            "pewnosc": int,              # 0-100
            "zrodlo": str,               # skąd pochodzi wybór
            "drive_url": str,            # URL raportu na Drive (lub "")
            "fallback_used": bool,       # True jeśli użyto wartości domyślnych
        }
    """
    logger.info("[wykrywaczplci] START — sender=%s | sender_name=%s", sender_email, sender_name)

    prompt_cfg = _load_prompt_json()
    pewnosc_prog = prompt_cfg.get("fallback", {}).get("pewnosc_prog", _PEWNOSC_PROG)

    # ── Krok 0: Reguły ────────────────────────────────────────────────────────
    rule_candidates = {
        "podpis_koniec": _extract_signature(body),
        "autoprzedstawienie": _extract_self_intro(body),
        "pole_from": _extract_from_header(sender_email, sender_name),
        "email_lokalny": _extract_email_local(sender_email),
    }
    logger.info("[wykrywaczplci] Kandydaci z reguł: %s", rule_candidates)

    # ── Krok 1: DeepSeek ekstrakcja ───────────────────────────────────────────
    ekstrakcja = _deepseek_ekstrakcja(
        prompt_cfg, sender_email, sender_name, body, rule_candidates
    )
    logger.info("[wykrywaczplci] Ekstrakcja DS1: %s", str(ekstrakcja)[:300])

    # ── Krok 2: DeepSeek weryfikacja ──────────────────────────────────────────
    weryfikacja = _deepseek_weryfikacja(
        prompt_cfg, ekstrakcja, sender_email, body, rule_candidates
    )
    logger.info("[wykrywaczplci] Weryfikacja DS2: %s", str(weryfikacja)[:300])

    # ── Wyciągnij wynik ───────────────────────────────────────────────────────
    wynik = weryfikacja.get("wynik", {})
    imie = wynik.get("imie", "__BRAK__") or "__BRAK__"
    nazwisko = wynik.get("nazwisko", "__BRAK__") or "__BRAK__"
    imie_nazwisko_pelne = wynik.get("imie_nazwisko_pelne", "") or ""
    plec = wynik.get("plec", "N") or "N"
    if plec not in ("M", "K", "N"):
        plec = "N"
    pewnosc = int(wynik.get("pewnosc", 0) or 0)
    zrodlo = wynik.get("zrodlo", "brak") or "brak"

    # ── Fallback jeśli pewność za niska lub brak imienia ──────────────────────
    fallback_used = False
    if pewnosc < pewnosc_prog or imie == "__BRAK__" or not imie_nazwisko_pelne:
        fallback_name = sender_name or sender_email.split("@")[0]
        sender_name_final = fallback_name
        gender_final = "N"
        fallback_used = True
        logger.warning(
            "[wykrywaczplci] Fallback — pewność=%d < %d lub brak imienia",
            pewnosc, pewnosc_prog,
        )
    else:
        sender_name_final = imie_nazwisko_pelne
        gender_final = plec

    logger.info(
        "[wykrywaczplci] WYNIK: sender_name=%s | gender=%s | pewnosc=%d | fallback=%s",
        sender_name_final, gender_final, pewnosc, fallback_used,
    )

    # ── Krok 3: Raport TXT na Drive ───────────────────────────────────────────
    report_txt = _build_report_txt(
        sender_email=sender_email,
        sender_name_original=sender_name,
        body=body,
        rule_candidates=rule_candidates,
        ekstrakcja=ekstrakcja,
        weryfikacja=weryfikacja,
        sender_name_final=sender_name_final,
        gender=gender_final,
    )

    drive_url = _save_report_to_drive(
        report_txt=report_txt,
        imie=imie if imie != "__BRAK__" else "brak",
        plec=gender_final,
    )

    return {
        "sender_name": sender_name_final,
        "gender": gender_final,
        "imie": imie,
        "nazwisko": nazwisko,
        "pewnosc": pewnosc,
        "zrodlo": zrodlo,
        "drive_url": drive_url,
        "fallback_used": fallback_used,
    }
