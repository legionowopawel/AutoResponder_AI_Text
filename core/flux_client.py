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

from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError  # re-eksport dla responderów

from core.config import HF_PROVIDER, HF_MODEL_FLUX


def generate_flux_bytes(
    prompt: str,
    token: str,
    seed: int | None = None,
    steps: int = 5,
    guidance: float = 2.0,
    width: int | None = None,
    height: int | None = None,
    timeout: int = 55,
) -> bytes:
    """
    Generuje obrazek FLUX przez routowanego providera HF.
    Zwraca surowe bajty PNG (kompatybilne z dotychczasowym kodem
    kompresji JPG / base64 w responderach).

    Rzuca HfHubHTTPError przy błędzie HTTP (401/402/403/429/5xx) —
    wywołujący łapie ten wyjątek dokładnie tak jak wcześniej sprawdzał
    resp.status_code.
    """
    client = InferenceClient(provider=HF_PROVIDER, api_key=token, timeout=timeout)

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

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
