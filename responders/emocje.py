"""
responders/emocje.py
Empatyczny pocieszyciel — 8 metod pocieszenia.

Strategia: 8 osobnych zapytan do AI (jedno na metode).
Kazde zapytanie uzywa user_template z emocje.json z wypelnionymi placeholderami.
"""

import re
import os
import json
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
PROMPT_JSON = os.path.join(PROMPTS_DIR, "emocje.json")

ALL_METODY_KEYS = [
    "walidacja_emocji",
    "obecnosc",
    "normalizacja",
    "odzwierciedlenie",
    "przestrzen_na_cisze",
    "docenienie_odwagi",
    "bez_srebrnych_podszewek",
    "cieplo_przez_konkret",
]


# ── Ladowanie promptu ─────────────────────────────────────────────────────────


def _load_prompt() -> dict:
    try:
        with open(PROMPT_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[emocje] Brak emocje.json: %s — uzywam fallbacku", e)
        return _fallback_prompt_data()


def _fallback_prompt_data() -> dict:
    return {
        "system": (
            "Jestes empatycznym towarzyszem. Generujesz WYLACZNIE czysty JSON. "
            "Pierwszy znak to '{', ostatni '}'. Zero tekstu poza nawiasami."
        ),
        "user_template": (
            "Mail: {{MAIL}}\nImie: {{SENDER_NAME}}\n"
            "Metoda: {{METODA_NAZWA}} ({{METODA_KEY}})\n"
            "Opis: {{METODA_OPIS}}\n\n"
            "Zwroc obiekt JSON:\n"
            "{\"metoda\": \"{{METODA_KEY}}\", \"pocieszenie\": \"<p>Jestem tu z Toba.</p>\", "
            "\"nastroj\": \"neutralna\", \"intensywnosc\": 5}"
        ),
        "metody_pocieszenia": [],
        "fallback_pocieszenie": (
            "<p>Dostalem Twoja wiadomosc i jestem tutaj.</p>"
            "<p>To co czujesz ma sens. Jestem z Toba.</p>"
        ),
    }


# ── Budowanie prompta dla jednej metody ───────────────────────────────────────


def _buduj_user_msg(
    template: str,
    mail_text: str,
    sender_name: str,
    metoda: dict,
) -> str:
    msg = template
    msg = msg.replace("{{MAIL}}", mail_text[:3000])
    msg = msg.replace("{{SENDER_NAME}}", sender_name or "nieznany")
    msg = msg.replace("{{METODA_KEY}}", metoda.get("key", ""))
    msg = msg.replace("{{METODA_NAZWA}}", metoda.get("nazwa", ""))
    msg = msg.replace("{{METODA_OPIS}}", metoda.get("opis", ""))
    msg = msg.replace("{{METODA_PRZYKLAD}}", metoda.get("przyklad", ""))
    return msg


# ── Bezposrednie wywolanie DeepSeek ──────────────────────────────────────────


def _call_ai_raw(system_msg: str, user_msg: str) -> str | None:
    """
    Wywoluje DeepSeek bezposrednio przez requests.
    Pomija call_deepseek i sanitize_model_output z ai_client.py
    ktore niszcza JSON przed parsowaniem i crashuja poza kontekstem Flask.
    """
    import time
    import requests as _requests

    api_key = os.getenv("API_KEY_DEEPSEEK", "").strip()
    model_name = os.getenv("MODEL_TYLER", "deepseek-chat")

    if not api_key:
        logger.error("[emocje] Brak API_KEY_DEEPSEEK w srodowisku!")
        return None

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 550,
    }

    resp = None
    try:
        resp = _requests.post(url, headers=headers, json=payload, timeout=(10, 30))

        if resp.status_code == 429:
            logger.warning("[emocje] Rate limit (429) — czekam 5s i powtarzam")
            resp.close()
            time.sleep(5)
            resp = _requests.post(url, headers=headers, json=payload, timeout=(10, 30))

        if resp.status_code != 200:
            logger.error(
                "[emocje] API non-200: status=%s body=%.300s",
                resp.status_code,
                resp.text,
            )
            return None

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("[emocje] API OK — content len=%d", len(content))
        return content

    except _requests.exceptions.Timeout:
        logger.error("[emocje] API timeout po 30s")
        return None
    except _requests.exceptions.ConnectionError as e:
        logger.error("[emocje] API connection error: %s", e)
        return None
    except (KeyError, IndexError) as e:
        logger.error("[emocje] Nieoczekiwana struktura odpowiedzi API: %s", e)
        return None
    except Exception as e:
        logger.exception("[emocje] Nieoczekiwany blad API: %s", e)
        return None
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass


# ── Parsowanie odpowiedzi JSON z AI ──────────────────────────────────────────


def _parsuj_json_odpowiedz(raw: str) -> dict | None:
    if not raw:
        return None

    clean = raw.strip()

    # Usun markdown fences
    clean = re.sub(r"```json\s*", "", clean)
    clean = re.sub(r"```\s*", "", clean)
    clean = clean.strip()

    # Naprawa niezamknietych nawiasow
    open_count = clean.count("{")
    close_count = clean.count("}")
    if open_count > close_count:
        clean += "}" * (open_count - close_count)

    # Szukaj pierwszego poprawnego obiektu JSON z polem pocieszenie
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", clean):
        try:
            obj, _ = decoder.raw_decode(clean[match.start():])
            if isinstance(obj, dict) and "pocieszenie" in obj:
                return obj
        except json.JSONDecodeError:
            continue

    # Ostatnia szansa — caly string jako JSON
    try:
        obj = json.loads(clean)
        if isinstance(obj, dict) and "pocieszenie" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    logger.warning("[emocje] Nie mozna sparsowac JSON: %.300s", clean)
    return None


# ── Jedno zapytanie = jedna metoda ───────────────────────────────────────────


def _generuj_jedna_metoda(
    mail_text: str,
    sender_name: str,
    metoda: dict,
    prompt_data: dict,
) -> dict | None:
    """Wywoluje AI dla jednej metody. Zwraca dict lub None."""
    system_msg = prompt_data.get("system", "Odpowiadaj WYLACZNIE w JSON.")
    template = prompt_data.get("user_template", "")
    user_msg = _buduj_user_msg(template, mail_text, sender_name, metoda)

    key = metoda.get("key", "?")

    try:
        raw = _call_ai_raw(system_msg, user_msg)
    except Exception as e:
        logger.error("[emocje] Wyjątek przy wywolaniu AI dla %s: %s", key, e)
        return None

    if not raw:
        logger.error("[emocje] Brak odpowiedzi AI dla metody: %s", key)
        return None

    logger.info("[emocje] RAW dla %s (pierwsze 200 zn): %.200s", key, raw)

    result = _parsuj_json_odpowiedz(raw)
    if result:
        result["metoda"] = key
        result.setdefault("nastroj", "neutralna")
        result.setdefault("intensywnosc", 5)
        logger.info(
            "[emocje] OK metoda=%s nastroj=%s",
            key,
            result.get("nastroj"),
        )
    else:
        logger.warning("[emocje] Parsowanie nieudane dla %s — raw: %.300s", key, raw)

    return result


# ── Pomocnicy HTML ────────────────────────────────────────────────────────────


def _wyciagnij_imie(sender_name: str, sender_email: str = "") -> str:
    name = (sender_name or "").strip()
    if not name or "@" in name:
        if sender_email:
            local = sender_email.split("@")[0]
            local = re.sub(r"[._+\-]", " ", local).strip()
            local = re.split(r"\s+", local)[0]
            local = re.sub(r"\d+", "", local).strip()
            if local:
                return local.capitalize()
        return ""
    return name


def _nastroj_do_koloru(nastroj: str) -> dict:
    palety = {
        "smutek":        {"bg": "#eeedfe", "border": "#afa9ec", "ink": "#534ab7"},
        "bol":           {"bg": "#eeedfe", "border": "#afa9ec", "ink": "#534ab7"},
        "lek":           {"bg": "#faeeda", "border": "#fac775", "ink": "#854f0b"},
        "frustracja":    {"bg": "#fcebeb", "border": "#f09595", "ink": "#a32d2d"},
        "zlosc":         {"bg": "#fcebeb", "border": "#f09595", "ink": "#a32d2d"},
        "samotnosc":     {"bg": "#fbeaf0", "border": "#f0a8c4", "ink": "#993556"},
        "neutralna":     {"bg": "#d4f0e8", "border": "#7ecab8", "ink": "#1d8a6e"},
    }
    return palety.get(nastroj, palety["neutralna"])


def _metoda_do_tagu(key: str) -> str:
    mapy = {
        "walidacja_emocji":        "metoda 01 · walidacja emocji",
        "obecnosc":                "metoda 02 · obecnosc",
        "normalizacja":            "metoda 03 · normalizacja",
        "odzwierciedlenie":        "metoda 04 · odzwierciedlenie",
        "przestrzen_na_cisze":     "metoda 05 · przestrzen na cisze",
        "docenienie_odwagi":       "metoda 06 · docenienie odwagi",
        "bez_srebrnych_podszewek": "metoda 07 · bez srebrnych podszewek",
        "cieplo_przez_konkret":    "metoda 08 · cieplo przez konkret",
    }
    return mapy.get(key, f"metoda · {key.replace('_', ' ')}")


def _buduj_html_blok(
    pocieszenie_html: str,
    sender_name: str,
    metoda_key: str,
    nastroj: str,
    gender: str = "N",
) -> str:
    kolory = _nastroj_do_koloru(nastroj)
    tag = _metoda_do_tagu(metoda_key)
    if sender_name:
        if gender == "K":
            zwrot = f"Droga {sender_name}"
        elif gender == "M":
            zwrot = f"Drogi {sender_name}"
        else:
            zwrot = f"Drogi/a {sender_name}"
        powitanie = f"<p>{zwrot},</p>"
    else:
        powitanie = ""

    return (
        f'<div style="border-left:3px solid {kolory["border"]};padding:10px 14px;'
        f'margin-bottom:18px;background:{kolory["bg"]};border-radius:0 10px 10px 0;">'
        f'<p style="font-family:monospace;font-size:10px;color:{kolory["ink"]};'
        f'margin:0 0 8px 0;letter-spacing:0.04em;">{tag}</p>'
        f'<div style="font-family:monospace;font-size:13px;color:#2a1f14;line-height:1.75;">'
        f"{powitanie}{pocieszenie_html}"
        f"</div></div>"
    )


def _buduj_html_email(
    metody_results: list[dict],
    sender_name: str,
    nastroj_dominujacy: str,
    gender: str = "N",
) -> str:
    kolory = _nastroj_do_koloru(nastroj_dominujacy)
    imie = sender_name or "Nadawca"

    bloki = []
    for r in metody_results:
        blok = _buduj_html_blok(
            r.get("pocieszenie", "<p>Jestem tutaj.</p>"),
            sender_name,
            r.get("metoda", "obecnosc"),
            r.get("nastroj", nastroj_dominujacy),
            gender=gender,
        )
        bloki.append(blok)

    bloki_html = "\n".join(bloki)

    return (
        f'<div style="font-family:monospace;color:#2a1f14;max-width:560px;margin:0 auto;padding:16px 14px;">'
        f'<p style="font-size:10px;color:{kolory["ink"]};margin:0 0 16px 0;opacity:0.7;letter-spacing:0.05em;">'
        f"pocieszenie dla {imie} · {len(metody_results)} metod</p>"
        f"{bloki_html}"
        f'<div style="margin-top:16px;padding-top:10px;border-top:1px solid #d3cfc8;'
        f'font-size:10px;color:#8a7a6a;text-align:center;">'
        f"<em>nastroj: {nastroj_dominujacy}</em></div></div>"
    )


# ── Glowna funkcja responderu ─────────────────────────────────────────────────


def build_emocje_section(
    body: str,
    sender_name: str = "",
    sender_email: str = "",
    attachments: list = None,
    test_mode: bool = False,
    gender: str = "N",
    imie: str = "__BRAK__",
    nazwisko: str = "__BRAK__",
) -> dict:
    """
    Generuje odpowiedzi WSZYSTKIMI 8 metodami pocieszenia.
    Strategia: 8 osobnych zapytan AI — jedno po drugim.

    Zwraca dict z:
      reply_html  — HTML z blokami 8 metod
      images      — []
      docs        — []
    """
    prompt_data = _load_prompt()
    mail_text = (body or "").strip()

    fallback_pocieszenie = prompt_data.get(
        "fallback_pocieszenie",
        "<p>Dostalem Twoja wiadomosc i jestem tutaj.</p>",
    )

    if not mail_text:
        logger.warning("[emocje] Pusty body — zwracam fallback")
        return {"reply_html": fallback_pocieszenie, "images": [], "docs": []}

    imie = _wyciagnij_imie(sender_name, sender_email)

    # Mapa key -> definicja metody z JSON
    metody_def_map = {
        m.get("key", m.get("nazwa", "").lower().replace(" ", "_")): m
        for m in prompt_data.get("metody_pocieszenia", [])
        if isinstance(m, dict)
    }

    logger.info(
        "[emocje] START — imie=%s | mail len=%d | metod=%d",
        imie or "(brak)",
        len(mail_text),
        len(ALL_METODY_KEYS),
    )

    # ── 8 osobnych zapytan sekwencyjnie ──────────────────────────────────────
    metody_results = []
    for key in ALL_METODY_KEYS:
        metoda_def = metody_def_map.get(
            key, {"key": key, "nazwa": key, "opis": "", "przyklad": ""}
        )
        logger.info("[emocje] Generuje metode: %s", key)

        try:
            result = _generuj_jedna_metoda(mail_text, imie, metoda_def, prompt_data)
        except Exception as e:
            logger.error("[emocje] Wyjątek dla metody %s: %s", key, e)
            result = None

        if result and isinstance(result, dict):
            result["metoda"] = key
            metody_results.append(result)
            logger.info("[emocje] Metoda %s — OK", key)
        else:
            logger.warning("[emocje] Fallback dla metody: %s", key)
            metody_results.append(
                {
                    "metoda": key,
                    "pocieszenie": fallback_pocieszenie,
                    "nastroj": "neutralna",
                    "intensywnosc": 5,
                }
            )

    # Dominujacy nastoj — z pierwszego wyniku ktory nie jest fallbackiem
    nastroj_dominujacy = "neutralna"
    for r in metody_results:
        n = r.get("nastroj", "neutralna")
        if n and n != "neutralna":
            nastroj_dominujacy = n
            break

    reply_html = _buduj_html_email(metody_results, imie, nastroj_dominujacy, gender=gender)

    ai_count = sum(
        1 for r in metody_results
        if r.get("pocieszenie") != fallback_pocieszenie
    )

    logger.info(
        "[emocje] KONIEC — metod=%d | AI=%d | fallback=%d | nastroj=%s | imie=%s",
        len(metody_results),
        ai_count,
        len(metody_results) - ai_count,
        nastroj_dominujacy,
        imie or "(brak)",
    )

    return {
        "reply_html": reply_html,
        "images": [],
        "docs": [],
    }
