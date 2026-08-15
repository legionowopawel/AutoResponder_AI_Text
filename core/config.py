"""
core/config.py
Centralna konfiguracja dla responders/zwykly.py.
Inne respondery (biznes.py, smierc.py itd.) mają własne stałe w swoich plikach.

Aby zmienić ile znaków emaila trafia do AI — zmień MAX_DLUGOSC_EMAIL.
Najlszepszy byłby model Groq llama-3.3-70b-versatile: limit ~128 000 tokenów (~500 000 znaków) Tymczasowo daje gorszy model : llama-3.1-8b-instant.
"""

# ─────────────────────────────────────────────────────────────────────────────
# GŁÓWNA STAŁA — limit długości emaila przekazywanego do AI
# Zmień tutaj aby sterować dla całego zwykly.py naraz.
# ─────────────────────────────────────────────────────────────────────────────
MAX_DLUGOSC_EMAIL = 30000

# ─────────────────────────────────────────────────────────────────────────────
# DEEPSEEK API
# ─────────────────────────────────────────────────────────────────────────────
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ─────────────────────────────────────────────────────────────────────────────
# FLUX / HUGGING FACE INFERENCE PROVIDERS
# 2026-08: "hf-inference" (bezpośredni hosting HF) przestał obsługiwać
# FLUX.1-schnell (HTTP 410). Generowanie idzie teraz przez routowanego
# providera — patrz core/flux_client.py. Zmień HF_PROVIDER tutaj, jeśli
# Together kiedyś też wycofa darmowy dostęp (np. na "fal-ai" albo "nscale").
# ─────────────────────────────────────────────────────────────────────────────
HF_PROVIDER = "together"
HF_MODEL_FLUX = "black-forest-labs/FLUX.1-schnell"
HF_STEPS = 5
HF_GUIDANCE = 2
HF_TIMEOUT = 55
TYLER_JPG_QUALITY = 85  # Kompresja JPG paneli tryptyku (95% = minimalna strata)

# ─────────────────────────────────────────────────────────────────────────────
# MAPOWANIE EMOCJI → NAZWY PLIKÓW
# ─────────────────────────────────────────────────────────────────────────────
EMOCJA_MAP = {
    "radosc": "twarz_radosc",
    "smutek": "twarz_smutek",
    "zlosc": "twarz_zlosc",
    "lek": "twarz_lek",
    "nuda": "twarz_nuda",
    "spokoj": "twarz_spokoj",
}
FALLBACK_EMOT = "error"
