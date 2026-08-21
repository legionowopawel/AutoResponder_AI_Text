"""
core/flux_client.py
════════════════════════════════════════════════════════════════════════════════
Wspólny klient generowania obrazów FLUX — używany przez zwykly.py, smierc.py
i zwykly_psychiatryczny_raport.py.

DLACZEGO TEN PLIK ISTNIEJE (2026-08):
  Endpoint "hf-inference" (bezpośredni hosting modeli przez Hugging Face)
  przestał obsługiwać FLUX.1-schnell (HTTP 410 "deprecated and no longer
  supported by provider hf-inference"). HF w 2026 kieruje generowanie obrazów
  przez zewnętrznych providerów (Together AI, fal, Replicate, ...) poprzez
  wspólny router — huggingface_hub.InferenceClient obsługuje to automatycznie,
  rozliczając się z darmowego limitu "Inference Providers credits" na tym
  samym tokenie HF_TOKEN*, którego już używasz.

  Surowe requesty POST na stary URL (".../hf-inference/models/...") nie
  zadziałają z nowym providerem — format zapytania/odpowiedzi jest inny,
  stąd ten wrapper zamiast samej zmiany stałej URL.

UŻYCIE:
    from core.flux_client import generate_flux_bytes, HfHubHTTPError

    try:
        png_bytes = generate_flux_bytes(prompt, token, seed=123, steps=5, guidance=2)
    except HfHubHTTPError as e:
        status = e.response.status_code if e.response is not None else None
        # 401/402/403 → mark_dead(name) tak jak wcześniej
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import io
import logging
import threading
import time

from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError  # re-eksport dla responderów

from core.config import (
    HF_MODEL_FLUX,
    HF_PROVIDER,
    HF_PROVIDER_CACHE_TTL,
    HF_PROVIDER_HEALTHCHECK_TIMEOUT,
    HF_PROVIDER_PRIORITY,
)

logger = logging.getLogger(__name__)

_ACTIVE_PROVIDER_CACHE: dict[str, tuple[str, float]] = {}
_ACTIVE_PROVIDER_LOCK = threading.Lock()


def _get_provider_candidates(explicit_provider: str | None = None) -> list[str]:
    """Zwraca kolejność providerów do testowania."""
    if explicit_provider and explicit_provider != "auto":
        ordered = [explicit_provider]
        for provider in HF_PROVIDER_PRIORITY:
            if provider not in ordered:
                ordered.append(provider)
        return ordered
    return list(HF_PROVIDER_PRIORITY)


def _summarize_error(exc: Exception) -> str:
    message = str(exc)
    if not message:
        return exc.__class__.__name__
    return message[:180].strip()


def get_working_provider(token: str, model_name: str = HF_MODEL_FLUX) -> str | None:
    """Sprawdza kolejno providery i zwraca pierwszego, który odpowiada poprawnie."""
    candidates = _get_provider_candidates(HF_PROVIDER)
    now = time.monotonic()

    with _ACTIVE_PROVIDER_LOCK:
        cached_provider, cached_at = _ACTIVE_PROVIDER_CACHE.get(token, (None, 0.0))
        if cached_provider and (now - cached_at) < HF_PROVIDER_CACHE_TTL:
            logger.info(
                "[FLUX] Używam cache providera dla tokenu %s: '%s' (TTL %.0fs)",
                token[:6],
                cached_provider,
                HF_PROVIDER_CACHE_TTL,
            )
            return cached_provider

    for provider in candidates:
        logger.info("[FLUX] Sprawdzam dostępność providera: '%s'...", provider)
        try:
            client = InferenceClient(
                provider=provider,
                api_key=token,
                timeout=HF_PROVIDER_HEALTHCHECK_TIMEOUT,
            )
            client.text_to_image(
                "ping",
                model=model_name,
                width=64,
                height=64,
                num_inference_steps=1,
                guidance_scale=1.0,
            )
            logger.info(
                "[FLUX] Provider '%s' odpowiada prawidłowo (200 OK). Wybrano ostatecznie: '%s'.",
                provider,
                provider,
            )
            with _ACTIVE_PROVIDER_LOCK:
                _ACTIVE_PROVIDER_CACHE[token] = (provider, time.monotonic())
            return provider
        except Exception as exc:
            logger.warning(
                "[FLUX] Provider '%s' zgłosił problem: %s. Próbuję następnego...",
                provider,
                _summarize_error(exc),
            )

    logger.error(
        "[FLUX] Żaden z listowanych providerów nie odpowiada dla modelu '%s'!",
        model_name,
    )
    return None


def generate_flux_bytes(
    prompt: str,
    token: str,
    seed: int | None = None,
    steps: int = 5,
    guidance: float = 2.0,
    width: int | None = None,
    height: int | None = None,
    timeout: int = 55,
    provider: str | None = None,
) -> bytes:
    """
    Generuje obrazek FLUX przez routowanego providera HF.
    Zwraca surowe bajty PNG (kompatybilne z dotychczasowym kodem
    kompresji JPG / base64 w responderach).

    Jeżeli provider nie został jawnie podany, wybieramy aktywnego providera
    przez dwuetapowy health check (PING -> RUN), aby nie marnować czasu na
    uszkodzone infrastrukturalnie endpointy typu Together z HTTP 503.
    """

    selected_provider = provider or get_working_provider(token, HF_MODEL_FLUX)
    if not selected_provider:
        raise HfHubHTTPError(
            "No working HF image provider available",
            response=None,
        )

    logger.info(
        "[FLUX] Rozpoczynam generowanie właściwego obrazka przy użyciu providera '%s' i tokenu %s...",
        selected_provider,
        token[:6],
    )

    last_error: Exception | None = None
    for candidate in _get_provider_candidates(selected_provider):
        try:
            client = InferenceClient(
                provider=candidate,
                api_key=token,
                timeout=timeout,
            )
            kwargs = {}
            if seed is not None:
                kwargs["seed"] = seed
            if steps:
                kwargs["num_inference_steps"] = steps
            if guidance is not None:
                kwargs["guidance_scale"] = guidance
            if width:
                kwargs["width"] = width
            if height:
                kwargs["height"] = height

            image = client.text_to_image(prompt, model=HF_MODEL_FLUX, **kwargs)

            with _ACTIVE_PROVIDER_LOCK:
                _ACTIVE_PROVIDER_CACHE[token] = (candidate, time.monotonic())

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as exc:
            last_error = exc
            logger.warning(
                "[FLUX] Provider '%s' podczas generowania zwrócił błąd: %s. Przełączam na następny...",
                candidate,
                _summarize_error(exc),
            )

    if last_error is not None:
        raise last_error
    raise HfHubHTTPError("No FLUX generation provider succeeded", response=None)
