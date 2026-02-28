"""
config.py — konfiguracja projektu PC_super

Zmienne środowiskowe ustaw w panelu Render (Environment).
Listy emaili i słów kluczowych są zarządzane w Google Apps Script Properties.
"""

import os
from typing import List

# ----------------------------
# 1. Bazowe ścieżki
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Katalogi z zasobami
EMOTKI_DIR = os.path.join(BASE_DIR, "emotki")
PDF_DIR    = os.path.join(BASE_DIR, "pdf")

# Pliki promptów
PROMPT_FILE     = os.path.join(BASE_DIR, "prompt.txt")
PROMPT_BIZ_FILE = os.path.join(BASE_DIR, "prompt_biznesowy.txt")
LOG_FILE        = os.path.join(BASE_DIR, "pc_super.log")

# ----------------------------
# 2. Klucze API i modele
# ----------------------------
GROQ_API_KEY = os.getenv("KLUCZ_GROQ", "")
MODEL_BIZ    = os.getenv("MODEL_BIZ",   "llama-3.3-70b-versatile")
MODEL_TYLER  = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

# ----------------------------
# 3. Ustawienia HTTP
# ----------------------------
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))

# ----------------------------
# 4. Walidacja środowiska
# ----------------------------
def is_env_configured() -> bool:
    """Sprawdza czy wymagane zmienne środowiskowe są ustawione."""
    missing = []
    if not GROQ_API_KEY:
        missing.append("KLUCZ_GROQ")
    if missing:
        print(f"[WARN] Brakujące zmienne środowiskowe: {', '.join(missing)}")
        return False
    return True

# ----------------------------
# 5. Diagnostyka
# ----------------------------
def masked_key_preview(key: str) -> str:
    """Zwraca zamaskowany podgląd klucza API (do logów)."""
    if not key:
        return "<BRAK>"
    k = key.strip()
    if len(k) <= 8:
        return k[:2] + "..." + k[-2:]
    return k[:4] + "..." + k[-4:]

# ----------------------------
# 6. Re-export
# ----------------------------
__all__ = [
    "BASE_DIR", "EMOTKI_DIR", "PDF_DIR",
    "PROMPT_FILE", "PROMPT_BIZ_FILE", "LOG_FILE",
    "GROQ_API_KEY", "MODEL_BIZ", "MODEL_TYLER",
    "HTTP_TIMEOUT_SECONDS",
    "is_env_configured", "masked_key_preview",
]
