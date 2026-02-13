"""
config.py — konfiguracja projektu PC_super

Plik zbiera zmienne środowiskowe, ścieżki do plików i proste funkcje walidacyjne.
Ustaw zmienne środowiskowe w systemie (Windows / Render / Docker) zamiast edytować ten plik.
"""

import os
from typing import List

# ----------------------------
# 1. Bazowe ścieżki
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Katalogi z zasobami (emotki, pdf itp.)
EMOTKI_DIR = os.path.join(BASE_DIR, "emotki")
PDF_DIR = os.path.join(BASE_DIR, "pdf")

# Pliki pomocnicze
ALLOWED_EMAILS_FILE = os.path.join(BASE_DIR, "dozwolone_email.txt")
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")
PROMPT_BIZ_FILE = os.path.join(BASE_DIR, "prompt_biznesowy.txt")
LOG_FILE = os.path.join(BASE_DIR, "pc_super.log")

# ----------------------------
# 2. Mail / serwery
# ----------------------------
IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", os.getenv("SMTP_PORT_DEFAULT", "465")))

MAIL_USER = os.getenv("MAIL_USER", "")
MAIL_PASS = os.getenv("MAIL_PASS", "")

# ----------------------------
# 3. Klucze API i modele
# ----------------------------
# Groq (model tekstowy)
GROQ_API_KEY = os.getenv("KLUCZ_GROQ", "")  # używaj KLUCZ_GROQ w środowisku
MODEL_BIZ = os.getenv("MODEL_BIZ", "llama-3.3-70b-versatile")
MODEL_TYLER = os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile")

# HuggingFace (opcjonalnie, do generowania obrazów)
HF_IMAGE_API_KEY = os.getenv("YOUR_HF_IMAGE_API_KEY", "")
HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-2")

# ----------------------------
# 4. Interwały i ustawienia
# ----------------------------
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))

# ----------------------------
# 5. Listy i słowa kluczowe (opcjonalnie z env)
# ----------------------------
# Możesz ustawić BIZ_LIST i ALLOWED_LIST jako przecinkiem rozdzielone stringi w Script Properties
# lub w zmiennych środowiskowych (np. w Render). Jeśli nie, skrypt Google decyduje o listach.
def _split_env_list(name: str) -> List[str]:
    raw = os.getenv(name, "")
    if not raw:
        return []
    return [s.strip().lower() for s in raw.split(",") if s.strip()]

BIZ_LIST = _split_env_list("BIZ_LIST")          # np. "biz1@firma.pl,biz2@firma.pl"
ALLOWED_LIST = _split_env_list("ALLOWED_LIST")  # np. "friend1@gmail.com,friend2@gmail.com"
KEYWORDS = _split_env_list("KEYWORDS")          # np. "notariusz,umowa,spadek"

# ----------------------------
# 6. Pomocnicze funkcje walidacyjne
# ----------------------------
def is_env_configured() -> bool:
    """Szybka walidacja najważniejszych zmiennych środowiskowych."""
    ok = True
    missing = []
    if not MAIL_USER:
        missing.append("MAIL_USER")
        ok = False
    if not MAIL_PASS:
        missing.append("MAIL_PASS")
        ok = False
    if not GROQ_API_KEY:
        missing.append("KLUCZ_GROQ")
        ok = False
    return ok

def load_allowed_emails_from_file(path: str = ALLOWED_EMAILS_FILE) -> List[str]:
    """Wczytuje plik dozwolone_email.txt i zwraca listę adresów (lowercase)."""
    emails = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                e = line.strip().lower()
                if e:
                    emails.append(e)
    except FileNotFoundError:
        # plik może nie istnieć w środowisku — to nie jest krytyczny błąd
        pass
    except Exception:
        pass
    return emails

# ----------------------------
# 7. Bezpieczny podgląd (do logów/diagnostyki)
# ----------------------------
def masked_key_preview(key: str) -> str:
    if not key:
        return "<BRAK>"
    k = key.strip()
    if len(k) <= 8:
        return k[:2] + "..." + k[-2:]
    return k[:4] + "..." + k[-4:]

# ----------------------------
# 8. Domyślne wartości i fallbacky
# ----------------------------
# Jeśli katalogi nie istnieją, nie tworzymy ich automatycznie tutaj — to zadanie deploya.
# Funkcje wyższego poziomu powinny sprawdzać istnienie plików i używać fallbacków (error.png/pdf).

# ----------------------------
# 9. Re-export (ułatwienie importów)
# ----------------------------
__all__ = [
    "BASE_DIR", "EMOTKI_DIR", "PDF_DIR", "ALLOWED_EMAILS_FILE", "PROMPT_FILE", "PROMPT_BIZ_FILE",
    "IMAP_HOST", "SMTP_HOST", "SMTP_PORT", "MAIL_USER", "MAIL_PASS",
    "GROQ_API_KEY", "MODEL_BIZ", "MODEL_TYLER", "HF_IMAGE_API_KEY", "HF_IMAGE_MODEL",
    "CHECK_INTERVAL_SECONDS", "HTTP_TIMEOUT_SECONDS",
    "BIZ_LIST", "ALLOWED_LIST", "KEYWORDS",
    "is_env_configured", "load_allowed_emails_from_file", "masked_key_preview"
]
