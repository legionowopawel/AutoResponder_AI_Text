"""
core/flux_client.py
════════════════════════════════════════════════════════════════════════════════
Wspólny klient generowania obrazów FLUX — używany przez zwykly.py, smierc.py
i zwykly_psychiatryczny_raport.py.

2026-11: PRZENIESIONY Z HUGGING FACE NA CLOUDFLARE WORKERS AI.
  Hugging Face przestało odnawiać kredyty. Teraz generujemy przez REST API:

    POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/
         @cf/black-forest-labs/flux-1-schnell
    Authorization: Bearer {CF_API_TOKEN}
    {"prompt": "...", "steps": 5}

  Odpowiedź: JSON, obraz w result.image jako base64 (JPEG).

RÓŻNICE WZGLĘDEM HF (obsłużone TUTAJ, respondery bez zmian):
  • seed NIE jest wysyłany — REST API odrzuca go błędem 400 (kod 5006,
    "Additional or unevaluated properties '/seed' not allowed"), mimo że
    przykład w dokumentacji go zawiera. Bez seeda model losuje sam, więc
    każdy obraz i tak jest inny. Parametr `seed` w sygnaturze jest ignorowany.
  • prompt max 2048 znaków → dłuższy jest przycinany (na granicy słowa)
  • steps max 8 → przycinane do 1..8
  • guidance_scale NIE istnieje → parametr `guidance` jest ignorowany
  • width/height NIE istnieją → obraz (1024×1024) jest kadrowany od środka do
    żądanych proporcji (np. 768×1024 dla zdjęcia pacjenta) przez Pillow
  • wynik jest konwertowany do PNG, żeby kontrakt "zwraca bajty PNG" został

ZGODNOŚĆ BŁĘDÓW (dlatego respondery nie wymagają zmian):
  Klasa FluxHTTPError ma te same pola co dawny HfHubHTTPError
  (.response.status_code / .text / .json()) i jest dostępna pod starą nazwą
  `HfHubHTTPError`. Kody Cloudflare są mapowane na semantykę, którą respondery
  już rozumieją:
    • 3036 "daily free allocation of 10,000 neurons"  → HTTP 402  (mark_dead + stop)
    • 3040 / inne 429 "capacity"                      → HTTP 429  (chwilowe, bez mark_dead)
    • 401 / 403                                       → HTTP 401/403 (mark_dead)
    • błąd sieci / timeout                            → response=None

UŻYCIE:
    from core.flux_client import generate_flux_bytes, HfHubHTTPError

    try:
        png_bytes = generate_flux_bytes(prompt, token, seed=123, steps=5)
    except HfHubHTTPError as e:
        status = e.response.status_code if e.response is not None else None
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import base64
import io
import json
import logging

import requests

from core.config import (
    CF_API_BASE,
    CF_MAX_PROMPT_CHARS,
    CF_MAX_STEPS,
    CF_MODEL_FLUX,
)
from core.hf_token_manager import unpack_cf_credential

logger = logging.getLogger(__name__)

__all__ = ["generate_flux_bytes", "FluxHTTPError", "HfHubHTTPError"]


# ─── Błędy (zgodne z dawnym HfHubHTTPError) ───────────────────────────────────


class _ErrorResponse:
    """Minimalny obiekt response: status_code, text, headers, json()."""

    def __init__(self, status_code, message: str, cf_code=None):
        self.status_code = status_code
        payload = {"error": message}
        if cf_code is not None:
            payload["cf_code"] = cf_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)
        self.headers: dict = {}
        self.request = None

    def json(self):
        return dict(self._payload)


class FluxHTTPError(Exception):
    """Błąd generowania obrazu. `.response` jak w requests/huggingface_hub."""

    def __init__(self, message: str, response=None):
        super().__init__(message)
        self.response = response


# Stara nazwa — respondery robią `from core.flux_client import HfHubHTTPError`.
HfHubHTTPError = FluxHTTPError


# ─── Pomocnicze ───────────────────────────────────────────────────────────────


def _parse_cf_error(resp: requests.Response) -> tuple[int | None, str]:
    """Wyciąga (kod, komunikat) z odpowiedzi błędu Cloudflare."""
    try:
        data = resp.json()
    except Exception:
        return None, (resp.text or "")[:200]
    errors = data.get("errors") if isinstance(data, dict) else None
    if errors and isinstance(errors, list) and isinstance(errors[0], dict):
        return errors[0].get("code"), str(errors[0].get("message", ""))[:300]
    return None, str(data)[:200]


def _raise_for_cf_status(resp: requests.Response) -> None:
    """Mapuje błąd Cloudflare na FluxHTTPError o semantyce znanej responderom."""
    status = resp.status_code
    code, msg = _parse_cf_error(resp)
    low = msg.lower()

    # Dzienny limit darmowych neuronów — trwały do północy UTC.
    # Mapujemy na 402: respondery robią mark_dead(name) i (smierc / psych)
    # przerywają dalsze próby. Tekst celowo zawiera "exhausted" i
    # "purchase pre-paid credits" — po tych frazach responderzy rozpoznają
    # globalne wyczerpanie.
    if code == 3036 or (status == 429 and "daily free allocation" in low):
        text = (
            "Cloudflare Workers AI: daily free allocation of 10,000 neurons "
            "exhausted (code 3036). Upgrade to Workers Paid or purchase "
            "pre-paid credits to continue."
        )
        raise FluxHTTPError(text, _ErrorResponse(402, text, 3036))

    # Chwilowy brak mocy (3040) i inne 429 — NIE używamy słów "exceeded"/"quota"
    # (oryginalny komunikat CF zawiera "exceeded"), bo _quota_permanently_exhausted
    # w responderach uznałby to za trwałe wyczerpanie i uśmiercił token.
    if status == 429:
        text = f"Cloudflare busy, retry later (code {code})"
        raise FluxHTTPError(text, _ErrorResponse(429, text, code))

    text = f"Cloudflare HTTP {status} (code {code}): {msg[:150]}"
    raise FluxHTTPError(text, _ErrorResponse(status, msg[:200] or text, code))


def _truncate_prompt(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if len(prompt) <= CF_MAX_PROMPT_CHARS:
        return prompt
    cut = prompt[:CF_MAX_PROMPT_CHARS]
    last_space = cut.rfind(" ")
    if last_space > CF_MAX_PROMPT_CHARS * 0.8:
        cut = cut[:last_space]
    logger.warning(
        "[FLUX] Prompt %d znaków > limit %d — przycięty",
        len(prompt),
        CF_MAX_PROMPT_CHARS,
    )
    return cut.rstrip()


def _to_png_bytes(raw: bytes, width: int | None, height: int | None) -> bytes:
    """JPEG z Cloudflare → PNG (kontrakt: zwracamy PNG). Opcjonalnie kadruje
    od środka do proporcji width:height (Cloudflare nie ma width/height)."""
    try:
        from PIL import Image
    except ImportError:
        logger.error("[FLUX] Pillow niedostępny — zwracam surowe bajty (JPEG)")
        return raw

    img = Image.open(io.BytesIO(raw))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if width and height:
        w, h = img.size
        target = width / height
        current = w / h
        if abs(current - target) > 0.01:
            if current > target:
                new_w = round(h * target)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            else:
                new_h = round(w / target)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
        if img.size != (width, height):
            img = img.resize((width, height), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── Główna funkcja ───────────────────────────────────────────────────────────


def generate_flux_bytes(
    prompt: str,
    token: str,
    seed: int | None = None,  # ignorowane — Cloudflare REST odrzuca seed (400/5006)
    steps: int = 5,
    guidance: float = 2.0,  # ignorowane — Cloudflare flux-1-schnell nie ma guidance
    width: int | None = None,
    height: int | None = None,
    timeout: int = 55,
    provider: str | None = None,  # ignorowane — zachowane dla zgodności sygnatury
) -> bytes:
    """
    Generuje obrazek FLUX przez Cloudflare Workers AI. Zwraca surowe bajty PNG.

    `token` to wartość z get_active_tokens(), czyli "ACCOUNT_ID:TOKEN".
    Błędy: FluxHTTPError (alias HfHubHTTPError) — patrz opis modułu.
    """
    account_id, api_token = unpack_cf_credential(token)
    if not account_id or not api_token:
        msg = "Cloudflare: brak Account ID lub tokenu (sprawdź CF_ACCOUNT_ID i CF_API_TOKEN)"
        raise FluxHTTPError(msg, _ErrorResponse(401, msg))

    payload: dict = {
        "prompt": _truncate_prompt(prompt),
        "steps": max(1, min(int(steps or 4), CF_MAX_STEPS)),
    }
    # `seed` celowo NIE trafia do payloadu (patrz opis modułu) — 400 / kod 5006.

    url = f"{CF_API_BASE}/accounts/{account_id}/ai/run/{CF_MODEL_FLUX}"
    logger.info(
        "[FLUX] Cloudflare %s steps=%s (konto %s…)",
        CF_MODEL_FLUX,
        payload["steps"],
        account_id[:6],
    )

    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(10, timeout),
        )
    except requests.exceptions.RequestException as exc:
        # Błąd sieci / timeout — brak odpowiedzi HTTP → response=None
        raise FluxHTTPError(f"Cloudflare: błąd połączenia: {str(exc)[:150]}", None) from exc

    if resp.status_code != 200:
        _raise_for_cf_status(resp)

    ctype = (resp.headers.get("content-type") or "").lower()
    if ctype.startswith("image/"):
        raw = resp.content
    else:
        try:
            data = resp.json()
        except Exception as exc:
            msg = "Cloudflare: odpowiedź nie jest JSON-em"
            raise FluxHTTPError(msg, _ErrorResponse(502, msg)) from exc
        if isinstance(data, dict) and data.get("success") is False:
            code, msg = _parse_cf_error(resp)
            text = f"Cloudflare: success=false (code {code}): {msg[:150]}"
            raise FluxHTTPError(text, _ErrorResponse(502, text, code))
        result = data.get("result") if isinstance(data, dict) else None
        b64 = result.get("image") if isinstance(result, dict) else None
        if not b64:
            msg = "Cloudflare: odpowiedź bez result.image"
            raise FluxHTTPError(msg, _ErrorResponse(502, msg))
        raw = base64.b64decode(b64)

    try:
        return _to_png_bytes(raw, width, height)
    except Exception as exc:
        msg = f"Cloudflare: nie udało się odczytać obrazu: {str(exc)[:120]}"
        raise FluxHTTPError(msg, _ErrorResponse(502, msg)) from exc
