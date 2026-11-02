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
# FLUX / CLOUDFLARE WORKERS AI
# 2026-11: Hugging Face przestało odnawiać darmowe kredyty → generowanie obrazów
# przeniesione na Cloudflare Workers AI (REST API). Patrz core/flux_client.py.
#
# Zmienne środowiskowe na Render (patrz core/hf_token_manager.py):
#   CF_ACCOUNT_ID   — Account ID z Cloudflare (32 znaki hex, ten z adresu dashboardu)
#   CF_API_TOKEN    — token "Workers AI" (Read + Edit); kolejne: CF_API_TOKEN1, CF_API_TOKEN2…
#   (opcjonalnie CF_ACCOUNT_ID1… — gdy token nr 1 należy do INNEGO konta Cloudflare)
#
# Darmowy limit: 10 000 neuronów DZIENNIE na konto (odnawiany codziennie).
# Kilka tokenów z TEGO SAMEGO konta NIE zwiększa limitu — dopiero osobne konta.
# ─────────────────────────────────────────────────────────────────────────────
CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_MODEL_FLUX = "@cf/black-forest-labs/flux-1-schnell"
CF_MAX_PROMPT_CHARS = 2048  # twardy limit modelu — dłuższy prompt jest przycinany
CF_MAX_STEPS = 8  # twardy limit modelu flux-1-schnell

# Nazwy poniżej (HF_*) zostają dla zgodności z responderami (zwykly, smierc,
# zwykly_psychiatryczny_raport importują je z core.config).
HF_STEPS = 5
HF_GUIDANCE = 2  # Cloudflare flux-1-schnell NIE obsługuje guidance — ignorowane
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
