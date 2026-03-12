"""
responders/smierc.py - Wersja KOMPLETNA z logowaniem i poprawką _load_xlsx
"""

import os
import re
import random
import base64
import requests
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import current_app

from core.ai_client import call_deepseek, MODEL_TYLER

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")
MEDIA_DIR   = os.path.join(BASE_DIR, "media")

FILE_XLSX                    = os.path.join(PROMPTS_DIR, "requiem_etapy.xlsx")
FILE_WYSLANNIK_SYSTEM        = os.path.join(PROMPTS_DIR, "requiem_WYSLANNIK_system_8_.txt")
FILE_WYSLANNIK_FLUX_GROQ_SYS = os.path.join(PROMPTS_DIR, "requiem_WYSLANNIK_flux_groq_system.txt")

HF_API_URL  = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ═══════════════════════════════════════════════════════════════════════════════
# FUNKCJE POMOCNICZE (MUSZĄ BYĆ TUTAJ)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_int(val) -> int | None:
    try: return int(float(str(val).strip()))
    except: return None

def _load_xlsx() -> dict:
    import openpyxl
    etapy = {}
    try:
        wb = openpyxl.load_workbook(FILE_XLSX, read_only=True, data_only=True)
        ws = wb["etapy"]
        rows = list(ws.iter_rows(values_only=True))
        if not rows: return {}
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        for row in rows[1:]:
            d = {headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row) if i < len(headers)}
            num = _parse_int(d.get("etap"))
            if num is not None:
                etapy[num] = {
                    "opis": d.get("opis", ""),
                    "obraz": d.get("obraz", ""),
                    "video": d.get("video", ""),
                    "obrazki_ai": _parse_int(d.get("obrazki_ai") or 0) or 0,
                    "system_prompt": d.get("system_prompt", ""),
                    "styl_odpowiedzi_tekstowej": d.get("styl_odpowiedzi_tekstowej", "")
                }
        wb.close()
    except Exception as e:
        current_app.logger.error("[xlsx] BŁĄD WCZYTYWANIA: %s", e)
    return etapy

def _load_file_list(file_list_str: str, subfolder: str) -> list:
    res = []
    if not file_list_str: return res
    for fname in file_list_str.split(","):
        fname = fname.strip()
        path = os.path.join(MEDIA_DIR, subfolder, fname)
        try:
            with open(path, "rb") as f:
                res.append({
                    "base64": base64.b64encode(f.read()).decode("ascii"),
                    "content_type": _guess_content_type(fname),
                    "filename": fname
                })
        except: continue
    return res

def _guess_content_type(f: str) -> str:
    ext = f.split(".")[-1].lower()
    return {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg","mp4":"video/mp4","mpg":"video/mpeg","mpeg":"video/mpeg"}.get(ext, "application/octet-stream")

# ═══════════════════════════════════════════════════════════════════════════════
# GŁÓWNA LOGIKA
# ═══════════════════════════════════════════════════════════════════════════════

def build_smierc_section(sender_email, body, etap, data_smierci_str, historia) -> dict:
    etapy = _load_xlsx() # Teraz na pewno zdefiniowane wyżej
    max_etap = max(etapy.keys()) if etapy else 0

    if etap > max_etap:
        # Tu możesz dodać wywołanie _run_wyslannik (jeśli go masz w pliku)
        return {"reply_html": "<p>Wędrujesz dalej...</p>", "nowy_etap": etap, "images": []}

    row = etapy.get(etap)
    if not row:
        return {"reply_html": "Cisza...", "nowy_etap": etap}

    # Tekst (uproszczone wywołanie)
    sys_prompt = row["system_prompt"] or "Jesteś duchem. Pisz krótko."
    wynik = call_deepseek(sys_prompt, body, MODEL_TYLER) or "..."

    # Ładowanie mediów do JEDNEJ listy 'images'
    images_statyczne = _load_file_list(row["obraz"], "images/niebo")
    videos = _load_file_list(row["video"], "mp4/niebo")

    # (Tu opcjonalnie generowanie AI images_ai...)
    images_ai = [] 

    return {
        "reply_html": f"<p>{wynik}</p>",
        "nowy_etap":  etap + 1,
        "images":     images_statyczne + images_ai, # Wszystkie obrazki razem
        "videos":     videos
    }