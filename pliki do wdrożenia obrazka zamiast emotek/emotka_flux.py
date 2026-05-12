"""
responders/emotka_flux.py
═══════════════════════════════════════════════════════════════════════════════
Generuje unikalny obrazek FLUX na podstawie treści emaila.
Zastępuje statyczną emotkę PNG.

UŻYCIE w zwykly.py:
    from responders.emotka_flux import generate_emotka

    emoticon = generate_emotka(body)
    # zwraca dict {base64, content_type, filename} lub None

Moduł jest w pełni samodzielny — wystarczy przekazać treść emaila.
Resztą zajmuje się sam: wczytuje config JSON, buduje prompt,
wywołuje FLUX, konwertuje PNG → JPG i zwraca gotowy dict.

Config: prompts/zwykly_emotka_flux.json
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import random
import re
from datetime import datetime

import requests

from core.config import (
    HF_API_URL,
    HF_GUIDANCE,
    HF_STEPS,
    HF_TIMEOUT,
    TYLER_JPG_QUALITY,
)
from core.hf_token_manager import get_active_tokens, mark_dead

logger = logging.getLogger(__name__)

# ── Ścieżki ───────────────────────────────────────────────────────────────────

_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_BASE_DIR, "prompts", "zwykly_emotka_flux.json")
_SUBSTITUTE  = os.path.join(_BASE_DIR, "images", "zastepczy.jpg")


# ═══════════════════════════════════════════════════════════════════════════════
# WCZYTYWANIE CONFIGU
# ═══════════════════════════════════════════════════════════════════════════════

def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("[emotka-flux] Brak %s — używam fallbacku", _CONFIG_PATH)
    except json.JSONDecodeError as e:
        logger.error("[emotka-flux] Błąd JSON w config: %s", e)
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# BUDOWANIE PROMPTU
# ═══════════════════════════════════════════════════════════════════════════════

def _wykryj_miejsca(body_lower: str, mapowanie: dict) -> str:
    for slowo, opis in mapowanie.items():
        if slowo.startswith("_"):
            continue
        if slowo.lower() in body_lower:
            logger.debug("[emotka-flux] Miejsce: '%s'", slowo)
            return opis
    return mapowanie.get("_domyslny", "")


def _wykryj_tematy(body_lower: str, mapowanie: dict, max_tematow: int = 3) -> list[str]:
    trafione = []
    for slowo, opis in mapowanie.items():
        if slowo.startswith("_"):
            continue
        if slowo.lower() in body_lower and opis not in trafione:
            trafione.append(opis)
        if len(trafione) >= max_tematow:
            break
    return trafione or [mapowanie.get("_domyslny", "symbolic everyday objects")]


def _wykryj_ton_nadawcy(body_lower: str, cfg_emocja: dict) -> str:
    wykrywanie = cfg_emocja.get("wykrywanie", {})
    przeklad   = cfg_emocja.get("przeklad_na_nastroj", {})
    for typ, zwroty in wykrywanie.items():
        for zwrot in zwroty:
            if zwrot.lower() in body_lower:
                return przeklad.get(typ, "")
    return przeklad.get("uprzejmy_formalny", "natural atmosphere")


def _buduj_prompt(body: str, cfg: dict) -> str:
    """
    Składa prompt FLUX lokalnie bez calla AI.
    Struktura: miejsce + tematy + ton nadawcy + styl wizualny + jakość.
    """
    body_lower  = body.lower()
    budowanie   = cfg.get("budowanie_promptu", {})
    ekstrakcja  = cfg.get("ekstrakcja_kontekstu", {})

    # Miejsce
    miejsca_mapa = ekstrakcja.get("miejsca", {}).get("mapowanie_na_opis", {})
    opis_miejsca = _wykryj_miejsca(body_lower, miejsca_mapa)

    # Tematy
    tematy_mapa = ekstrakcja.get("tematy", {}).get("mapowanie", {})
    tematy      = _wykryj_tematy(body_lower, tematy_mapa)
    tematy_str  = ", ".join(tematy)

    # Ton nadawcy
    cfg_emocja    = ekstrakcja.get("emocja_nadawcy", {})
    ton_nadawcy   = _wykryj_ton_nadawcy(body_lower, cfg_emocja)

    # Styl wizualny — losowy wariant
    style_warianty = budowanie.get("visual_style_warianty", [
        "35mm film photography, shallow depth of field, cinematic color grading"
    ])
    visual_style = random.choice(style_warianty)

    # Sufiks jakości
    quality_suffix = budowanie.get(
        "quality_suffix",
        "photorealistic, no text, no writing, no people at computers, highly detailed"
    )

    # Złóż prompt
    czesci = [p for p in [
        opis_miejsca,
        tematy_str,
        ton_nadawcy,
        visual_style,
        quality_suffix,
    ] if p]

    prompt  = ", ".join(czesci)
    max_len = budowanie.get("max_dlugosc_promptu", 400)

    if len(prompt) > max_len:
        prompt = prompt[:max_len].rsplit(",", 1)[0]

    logger.info("[emotka-flux] Prompt (%d znaków): %.150s…", len(prompt), prompt)
    return prompt


# ═══════════════════════════════════════════════════════════════════════════════
# FLUX — generowanie obrazka
# ═══════════════════════════════════════════════════════════════════════════════

def _load_substitute() -> dict | None:
    if not os.path.exists(_SUBSTITUTE):
        return None
    try:
        with open(_SUBSTITUTE, "rb") as f:
            return {
                "base64":       base64.b64encode(f.read()).decode("ascii"),
                "content_type": "image/jpeg",
                "filename":     "emotka_zastepczy.jpg",
            }
    except Exception as e:
        logger.warning("[emotka-flux] Błąd odczytu zastepczy.jpg: %s", e)
        return None


def _call_flux(prompt: str, cfg: dict) -> bytes | None:
    """
    Wywołuje HF Inference API z rotacją tokenów.
    Zwraca surowe bajty PNG lub None.
    """
    hf_params = cfg.get("parametry_hf", {})
    panel_idx = cfg.get("panel_index", 96)

    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": hf_params.get("num_inference_steps", HF_STEPS),
            "guidance_scale":      hf_params.get("guidance_scale",      HF_GUIDANCE),
            "width":               hf_params.get("width",  768),
            "height":              hf_params.get("height", 768),
            "seed":                random.randint(0, 2**32 - 1),
        },
    }

    tokens = get_active_tokens()
    if not tokens:
        logger.error("[emotka-flux] Brak aktywnych tokenów HF")
        return None

    # Rotacja od panel_index — nie koliduje z trptykiem (1-7)
    offset = (panel_idx - 1) % len(tokens)
    tokens = tokens[offset:] + tokens[:offset]

    for name, token in tokens:
        headers = {"Authorization": f"Bearer {token}", "Accept": "image/png"}
        try:
            resp = requests.post(
                HF_API_URL, headers=headers, json=payload, timeout=HF_TIMEOUT
            )
            remaining = resp.headers.get("X-Remaining-Requests", "?")

            if resp.status_code == 200:
                logger.info(
                    "[emotka-flux] ✓ Token %s OK — %dB | pozostało: %s",
                    name, len(resp.content), remaining,
                )
                return resp.content

            elif resp.status_code in (401, 402, 403):
                mark_dead(name)
                logger.warning(
                    "[emotka-flux] HTTP %d token=%s → czarna lista",
                    resp.status_code, name,
                )
            elif resp.status_code == 429:
                logger.warning("[emotka-flux] 429 token=%s → następny", name)
            elif resp.status_code in (503, 529):
                logger.warning("[emotka-flux] %d token=%s → przeciążony", resp.status_code, name)
            else:
                logger.warning(
                    "[emotka-flux] HTTP %d token=%s: %.80s",
                    resp.status_code, name, resp.text,
                )

        except requests.exceptions.Timeout:
            logger.warning("[emotka-flux] Timeout token=%s", name)
        except Exception as e:
            logger.warning("[emotka-flux] Wyjątek token=%s: %s", name, str(e)[:80])

    logger.error("[emotka-flux] Wszystkie tokeny zawiodły")
    return None


def _png_to_jpg(raw_png: bytes, cfg: dict, seed: int) -> dict:
    """Konwertuje PNG → JPG, opcjonalnie zmniejsza. Zwraca dict gotowy do wysyłki."""
    param   = cfg.get("parametry_obrazka", {})
    quality = param.get("jakosc_jpg", TYLER_JPG_QUALITY)
    scale   = param.get("zmniejsz_do_procent", 95) / 100.0
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        from PIL import Image as PILImage

        pil = PILImage.open(io.BytesIO(raw_png)).convert("RGB")

        if scale < 1.0:
            w, h = pil.size
            pil  = pil.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)

        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=quality, optimize=True)
        size_kb = len(buf.getvalue()) // 1024

        logger.info("[emotka-flux] JPG OK — %dKB (jakość=%d%%)", size_kb, quality)

        return {
            "base64":       base64.b64encode(buf.getvalue()).decode("ascii"),
            "content_type": "image/jpeg",
            "filename":     f"emotka_flux_{ts}_seed{seed}.jpg",
            "size_jpg":     f"{size_kb}KB",
        }

    except ImportError:
        logger.error("[emotka-flux] Pillow niedostępny — zwracam PNG")
    except Exception as e:
        logger.warning("[emotka-flux] Błąd konwersji: %s — zwracam PNG", e)

    return {
        "base64":       base64.b64encode(raw_png).decode("ascii"),
        "content_type": "image/png",
        "filename":     f"emotka_flux_{ts}.png",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLICZNE API
# ═══════════════════════════════════════════════════════════════════════════════

def generate_emotka(
    body: str,
    test_mode: bool = False,
) -> dict | None:
    """
    Generuje unikalny obrazek FLUX na podstawie treści emaila.

    Parametry:
        body      — treść emaila (plain text) — jedyne co potrzeba
        test_mode — True → zastępczy JPG zamiast FLUX (oszczędność tokenów HF)

    Zwraca:
        dict {base64, content_type, filename, ...} lub None przy błędzie
    """
    logger.info("[emotka-flux] START — body len=%d | test_mode=%s", len(body or ""), test_mode)

    if test_mode:
        result = _load_substitute()
        if result:
            logger.info("[emotka-flux] test_mode → zastepczy.jpg")
            return result
        return None

    cfg = _load_config()

    # Prompt
    if body and body.strip():
        prompt = _buduj_prompt(body, cfg)
    else:
        prompt = cfg.get("fallback", {}).get("prompt", "")

    if not prompt:
        prompt = (
            "A contemplative urban Polish landscape, quiet street, "
            "late afternoon autumn light, 35mm film photography, "
            "photorealistic, no text, no people at computers, highly detailed"
        )
        logger.warning("[emotka-flux] Pusty prompt — używam globalnego fallbacku")

    # FLUX
    seed    = random.randint(0, 2**32 - 1)
    raw_png = _call_flux(prompt, cfg)

    if not raw_png:
        # Fallback do zastępczego obrazka
        logger.warning("[emotka-flux] FLUX zawiódł — używam zastepczy.jpg")
        return _load_substitute()

    result = _png_to_jpg(raw_png, cfg, seed)
    result["prompt_preview"] = prompt[:120]

    logger.info("[emotka-flux] KONIEC OK — %s", result["filename"])
    return result
