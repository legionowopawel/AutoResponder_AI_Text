"""
requiem_kalibracja.py  v5
Lokalne narzędzie do testowania promptów Requiem Autorespondera.
Umieść w katalogu: C:\\python\\...\\AutoResponder_AI_Text\\prompts\\

v5 zmiany:
  - API calls (DeepSeek, Groq, FLUX) importowane bezpośrednio z responders/smierc.py
  - testowanie kalibracji = testowanie prawdziwego kodu produkcyjnego
  - klucze API czytane ze zmiennych środowiskowych lokalnie
    (DEEPSEEK_API_KEY, GROQ_API_KEY, HF_TOKEN)
  - zmiana parametrów FLUX w smierc.py automatycznie działa też tutaj
"""

import os
import re
import sys
import shutil
import threading
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# ── Ścieżki ───────────────────────────────────────────────────────────────────
SCRIPT_DIR     = Path(__file__).parent
PROJECT_DIR    = SCRIPT_DIR.parent
BACKUP_DIR     = PROJECT_DIR / "backup"
RESPONDERS_DIR = PROJECT_DIR / "responders"
SMIERC_PY      = RESPONDERS_DIR / "smierc.py"

FILE_PAWEL_1_6     = SCRIPT_DIR / "requiem_PAWEL_system_1-6.txt"
FILE_PAWEL_7       = SCRIPT_DIR / "requiem_PAWEL_system_7.txt"
FILE_WYSLANNIK     = SCRIPT_DIR / "requiem_WYSLANNIK_system_8_.txt"
FILE_FLUX_GROQ_SYS = SCRIPT_DIR / "requiem_WYSLANNIK_flux_groq_system.txt"
FILE_IMAGE_STYLE   = SCRIPT_DIR / "requiem_WYSLANNIK_IMAGE_STYLE.txt"
FILE_POZAGROBOWE   = SCRIPT_DIR / "pozagrobowe.txt"

TODAY = datetime.date.today().strftime("%d.%m.%Y")

# ── Import funkcji z smierc.py ────────────────────────────────────────────────
# Dodajemy katalog projektu do sys.path żeby import działał lokalnie
# bez potrzeby instalowania pakietu Flask czy core/
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Lokalny mock flask.current_app — żeby smierc.py nie crashował bez Flaska
try:
    from flask import current_app as _flask_app
except Exception:
    pass

import types, logging as _logging

class _MockApp:
    """Podmienia current_app.logger gdy nie ma Flaska."""
    logger = _logging.getLogger("smierc_kalibracja")
    @staticmethod
    def __bool__(): return True

_mock_app = _MockApp()
_logging.basicConfig(level=_logging.INFO,
                     format="[%(levelname)s] %(name)s: %(message)s")

# Monkey-patch flask.current_app na nasz mock zanim załaduje się smierc.py
import unittest.mock as _mock
_flask_patch = _mock.patch("flask.current_app", _mock_app)
_flask_patch.start()

# Podmień też zmienne środowiskowe — smierc.py czyta API_KEY_GROQ i HF_TOKEN
# kalibracja używa GROQ_API_KEY i HF_TOKEN — ujednolicamy
def _sync_env():
    """Przepisuje lokalne klucze na nazwy używane przez smierc.py."""
    for src, dst in [("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
                     ("GROQ_API_KEY",     "API_KEY_GROQ"),
                     ("HF_TOKEN",         "HF_TOKEN")]:
        val = os.environ.get(src, "").strip()
        if val:
            os.environ[dst] = val

_sync_env()

# Lokalny mock core.ai_client — używa DEEPSEEK_API_KEY bezpośrednio
def _deepseek_local(system: str, user: str, model=None) -> str | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            max_tokens=800, temperature=0.85,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        _mock_app.logger.warning("DeepSeek lokalny błąd: %s", e)
        return None

# Wstrzykujemy mock core.ai_client zanim smierc.py go zaimportuje
_core_mock = types.ModuleType("core")
_ai_mock   = types.ModuleType("core.ai_client")
_ai_mock.call_deepseek = _deepseek_local
_ai_mock.MODEL_TYLER   = "deepseek-chat"
_core_mock.ai_client   = _ai_mock
sys.modules["core"]            = _core_mock
sys.modules["core.ai_client"]  = _ai_mock

# Teraz możemy bezpiecznie zaimportować smierc.py
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("smierc", SMIERC_PY)
    _smierc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_smierc)
    _SMIERC_OK = True
except Exception as _e:
    _SMIERC_OK = False
    _mock_app.logger.error("Nie udało się załadować smierc.py: %s", _e)


# ── Funkcje API — delegowane do smierc.py ────────────────────────────────────
def call_deepseek(system: str, user: str) -> str | None:
    return _deepseek_local(system, user)

def call_groq(system: str, user: str, max_tokens: int = 300) -> str | None:
    if not _SMIERC_OK:
        return None
    return _smierc._call_groq(system, user)

def call_llm_email(system: str, user: str) -> tuple[str | None, str]:
    r = call_deepseek(system, user)
    if r:
        return r, "DeepSeek"
    r = call_groq(system, user, max_tokens=800)
    if r:
        return r, "Groq (fallback)"
    return None, "brak"

def call_llm_flux(system: str, user: str) -> tuple[str | None, str]:
    if _SMIERC_OK:
        return _smierc._generate_flux_prompt(user)
    return None, "smierc.py niedostępny"

def generate_flux_image(prompt: str):
    """Deleguje do _generate_flux_image() z smierc.py — używa tych samych
    stałych HF_API_URL / HF_STEPS / HF_GUIDANCE co produkcja."""
    if not _SMIERC_OK:
        return None, "smierc.py niedostępny"
    result = _smierc._generate_flux_image(prompt)
    if result:
        import base64
        return base64.b64decode(result["base64"]), None
    return None, "FLUX nie zwrócił obrazka"


def _smierc_info() -> str:
    """Zwraca info o parametrach FLUX z smierc.py — do wyświetlenia w UI."""
    if not _SMIERC_OK:
        return "smierc.py: BŁĄD ŁADOWANIA"
    url   = getattr(_smierc, "HF_API_URL",  "?")
    steps = getattr(_smierc, "HF_STEPS",    "?")
    guid  = getattr(_smierc, "HF_GUIDANCE", "?")
    model = url.split("/")[-1] if "/" in url else url
    return f"smierc.py ✓  →  {model}  steps={steps}  guidance={guid}"


# ── Paleta ────────────────────────────────────────────────────────────────────
BG      = "#0d0d0d"
BG2     = "#161616"
BG3     = "#1e1e1e"
ACCENT  = "#c8a96e"
ACCENT2 = "#8b5e3c"
FG      = "#e8e0d0"
FG2     = "#a09080"
FG3     = "#6a5a4a"
BTN_BG  = "#2a1f14"
SUCCESS = "#4a7c59"
ERR     = "#7c3a3a"
GREEN   = "#2d6b3a"
GREEN_H = "#3d8f4e"
BORDER  = "#3a2e22"

FONT_MONO  = ("Consolas", 10)
FONT_BTN   = ("Georgia", 9)
FONT_TITLE = ("Georgia", 12, "bold")
FONT_FILE  = ("Consolas", 8)
FONT_LBL   = ("Georgia", 9, "italic")


# ── Helpers ───────────────────────────────────────────────────────────────────
def load_txt(path: Path, fallback="") -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return fallback

def load_etapy() -> dict:
    etapy = {}
    try:
        for line in FILE_POZAGROBOWE.read_text(encoding="utf-8").splitlines():
            m = re.match(r'^(\d+)\.\s+(.+)$', line.strip())
            if m:
                etapy[int(m.group(1))] = m.group(2).strip()
    except Exception:
        pass
    return etapy

def ts_now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")

def elapsed(start: datetime.datetime) -> str:
    s = (datetime.datetime.now() - start).total_seconds()
    return f"{s:.1f}s"


# ── Backup + raport ───────────────────────────────────────────────────────────
def save_all(state: dict) -> Path:
    """
    Zapisuje cały stan sesji do backup/Wyniki_HH_MM_SS/.
    state: słownik z wszystkimi zebranymi danymi sesji.
    """
    ts      = datetime.datetime.now().strftime("%H_%M_%S")
    run_dir = BACKUP_DIR / f"Wyniki_{ts}"
    prom_dir = run_dir / "prompts"
    prom_dir.mkdir(parents=True, exist_ok=True)

    # Obrazek
    if state.get("img_bytes"):
        (run_dir / "niebo_wyslannik.png").write_bytes(state["img_bytes"])

    # tekst_zrodlowy.txt
    if state.get("body"):
        (run_dir / "tekst_zrodlowy.txt").write_text(state["body"], encoding="utf-8")

    # _.txt (debug FLUX)
    debug = (
        f"=== REQUIEM RESPONDER — DEBUG FLUX ===\n"
        f"Wygenerowano: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Email provider: {state.get('email_prov','')}\n"
        f"FLUX prompt provider: {state.get('flux_prov','')}\n\n"
        f"--- Odpowiedź Wysłannika (źródło promptu FLUX) ---\n"
        f"{state.get('wyslannik','')}\n\n"
        f"--- Proponowany tekst wysłany do FLUX.1-schnell ---\n"
        f"{state.get('flux','')}\n\n"
        f"--- Parametry FLUX ---\n"
        f"Model: {getattr(_smierc, 'HF_API_URL', '?').split('/')[-1] if _SMIERC_OK else '?'}\n"
        f"num_inference_steps: {getattr(_smierc, 'HF_STEPS', '?') if _SMIERC_OK else '?'}\n"
        f"guidance_scale: {getattr(_smierc, 'HF_GUIDANCE', '?') if _SMIERC_OK else '?'}\n"
        f"smierc.py: {'załadowany ✓' if _SMIERC_OK else 'BŁĄD ŁADOWANIA'}\n"
    )
    (run_dir / "_.txt").write_text(debug, encoding="utf-8")

    # raport.txt — pełne logi sesji
    log = state.get("log", [])
    raport = _build_raport(state, log)
    (run_dir / "raport.txt").write_text(raport, encoding="utf-8")

    # prompts/ — tylko requiem_*.txt + smierc.py (bez zmiany rozszerzenia)
    for f in SCRIPT_DIR.glob("requiem_*.txt"):
        shutil.copy2(f, prom_dir / f.name)
    if SMIERC_PY.exists():
        shutil.copy2(SMIERC_PY, prom_dir / "smierc.py")

    return run_dir


def _build_raport(state: dict, log: list) -> str:
    sep = "=" * 60
    lines = [
        sep,
        "REQUIEM KALIBRACJA — RAPORT SESJI",
        f"Data: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        sep,
        "",
        "=== TEKST ŹRÓDŁOWY (wiadomość nadawcy) ===",
        state.get("body", "(brak)"),
        "",
        sep,
        "=== LOGI ZDARZEŃ (chronologicznie) ===",
        "",
    ]
    for entry in log:
        lines.append(entry)
    lines += [
        "",
        sep,
        "=== WYNIKI GENEROWANIA ===",
        "",
    ]

    for etap_key, etap_label in [
        ("pawel_1_6",  "ETAP 1-6 — Paweł z zaświatów"),
        ("pawel_7",    "ETAP 7   — Reinkarnacja"),
        ("wyslannik",  "ETAP 8+  — Wysłannik"),
    ]:
        if state.get(etap_key):
            lines += [
                f"--- {etap_label} ---",
                f"Provider: {state.get(etap_key+'_prov', '?')}",
                f"Czas generowania: {state.get(etap_key+'_czas', '?')}",
                "",
                state[etap_key],
                "",
            ]

    if state.get("flux"):
        lines += [
            sep,
            "=== PROMPT FLUX ===",
            f"Provider: {state.get('flux_prov','?')}",
            f"Czas generowania: {state.get('flux_czas','?')}",
            "",
            state["flux"],
            "",
        ]

    if state.get("img_bytes"):
        lines += [
            sep,
            "=== OBRAZEK FLUX ===",
            f"Czas generowania: {state.get('img_czas','?')}",
            f"Rozmiar: {len(state['img_bytes']):,} B",
            "Plik: niebo_wyslannik.png",
            "",
        ]
    elif state.get("img_err"):
        lines += [
            sep,
            "=== OBRAZEK FLUX — BŁĄD ===",
            state["img_err"],
            "",
        ]

    lines += [
        sep,
        "=== UŻYTE PLIKI PROMPTÓW ===",
        "",
    ]
    for f in SCRIPT_DIR.glob("requiem_*.txt"):
        lines.append(f"  {f.name}")
        try:
            lines.append(f.read_text(encoding="utf-8").strip())
        except Exception:
            lines.append("(błąd odczytu)")
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)


# ── GUI ───────────────────────────────────────────────────────────────────────
class RequiemApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("✦ REQUIEM KALIBRACJA v5 ✦")
        self.root.configure(bg=BG)
        self.root.geometry("880x1080")
        self.root.minsize(700, 600)

        self.etap_var = tk.IntVar(value=1)
        self.etapy    = load_etapy()
        self.max_etap = max(self.etapy.keys()) if self.etapy else 7

        # Stan sesji — wszystko co trafi do raportu
        self._s = self._empty_state()

        self._build_ui()

    def _empty_state(self) -> dict:
        return {
            "body":         "",
            "pawel_1_6":    "", "pawel_1_6_prov": "", "pawel_1_6_czas": "",
            "pawel_7":      "", "pawel_7_prov":   "", "pawel_7_czas":   "",
            "wyslannik":    "", "wyslannik_prov":  "", "wyslannik_czas": "",
            "email_prov":   "",
            "flux":         "", "flux_prov":       "", "flux_czas":      "",
            "img_bytes":    None, "img_czas": "", "img_err": "",
            "log":          [],
        }

    def _log(self, msg: str):
        entry = f"[{ts_now()}] {msg}"
        self._s["log"].append(entry)

    # ── Buduj UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=BG3, troughcolor=BG, arrowcolor=ACCENT,
                        bordercolor=BORDER, lightcolor=BG3, darkcolor=BG3)

        outer  = tk.Frame(self.root, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                               style="Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.mf = tk.Frame(canvas, bg=BG)
        cw = canvas.create_window((0, 0), window=self.mf, anchor="nw")
        self.mf.bind("<Configure>",
                     lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(cw, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        f = self.mf

        # ── Nagłówek ──────────────────────────────────────────────────────────
        tk.Label(f, text="✦  REQUIEM  KALIBRACJA  v5  ✦",
                 font=("Georgia", 16, "bold"), fg=ACCENT, bg=BG).pack(pady=(18, 2))
        tk.Label(f, text="DeepSeek → email Wysłannika  |  Groq → prompt FLUX  |  fallback wzajemny",
                 font=("Georgia", 9, "italic"), fg=FG2, bg=BG).pack(pady=(0, 2))
        # Info o smierc.py i parametrach FLUX
        smierc_color = SUCCESS if _SMIERC_OK else ERR
        tk.Label(f, text=f"  ⚙  {_smierc_info()}",
                 font=FONT_FILE, fg=smierc_color, bg=BG).pack(pady=(0, 4))
        self.api_status = tk.Label(f, text="", font=FONT_FILE, fg=FG3, bg=BG)
        self.api_status.pack(pady=(0, 6))
        self._check_api_keys()
        self._sep(f)

        # ── Ustawienia ────────────────────────────────────────────────────────
        cfg = tk.Frame(f, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        cfg.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(cfg, text="ETAP PAWŁA (1–6)", font=FONT_FILE,
                 fg=FG3, bg=BG2).grid(row=0, column=0, sticky="w", padx=12, pady=(10,10))
        tk.Spinbox(cfg, from_=1, to=self.max_etap, textvariable=self.etap_var,
                   width=4, font=FONT_MONO, bg=BG3, fg=ACCENT,
                   buttonbackground=BTN_BG, insertbackground=ACCENT,
                   highlightthickness=0, bd=0
                   ).grid(row=0, column=1, padx=10, pady=(10,10), sticky="w")
        tk.Label(cfg, text=f"data śmierci: {TODAY}", font=FONT_FILE,
                 fg=FG3, bg=BG2).grid(row=0, column=2, padx=10, pady=(10,10), sticky="w")
        self._sep(f)

        # ── ① Wiadomość ───────────────────────────────────────────────────────
        self._title(f, "①  WIADOMOŚĆ NADAWCY")
        self.body_text = self._textbox(f, h=6, ro=False)
        self.body_text.insert("1.0", "Wpisz tutaj przykładową wiadomość od nadawcy...")
        self.body_text.bind("<FocusIn>", self._clear_ph)
        self._sep(f)

        # ── ② Paweł 1-6 ───────────────────────────────────────────────────────
        self._title(f, "②  ETAP 1–6 — Paweł z zaświatów")
        self._badge(f, FILE_PAWEL_1_6.name)
        self.res_pawel = self._textbox(f, h=5)
        self.pawel_meta = tk.Label(f, text="", font=FONT_FILE, fg=FG3, bg=BG)
        self.pawel_meta.pack(anchor="w", padx=20)
        self._btn(f, f"▶  Generuj z pliku: {FILE_PAWEL_1_6.name}", self._gen_pawel_1_6)
        self._sep(f)

        # ── ③ Paweł 7 ─────────────────────────────────────────────────────────
        self._title(f, "③  ETAP 7 — Reinkarnacja / pożegnanie")
        self._badge(f, FILE_PAWEL_7.name)
        self.res_pawel7 = self._textbox(f, h=5)
        self.pawel7_meta = tk.Label(f, text="", font=FONT_FILE, fg=FG3, bg=BG)
        self.pawel7_meta.pack(anchor="w", padx=20)
        self._btn(f, f"▶  Generuj z pliku: {FILE_PAWEL_7.name}", self._gen_pawel_7)
        self._sep(f)

        # ── ④ Wysłannik ───────────────────────────────────────────────────────
        self._title(f, "④  ETAP 8+ — Wysłannik z wyższych sfer")
        self._badge(f, FILE_WYSLANNIK.name)
        tk.Label(f, text="  Provider: DeepSeek → email  (fallback: Groq)",
                 font=FONT_FILE, fg=FG3, bg=BG).pack(anchor="w", padx=20)
        self.res_wyslannik = self._textbox(f, h=6)
        self.wyslannik_meta = tk.Label(f, text="", font=FONT_FILE, fg=FG3, bg=BG)
        self.wyslannik_meta.pack(anchor="w", padx=20, pady=(0, 4))
        self._btn(f, f"▶  Generuj z pliku: {FILE_WYSLANNIK.name}", self._gen_wyslannik)
        self._sep(f)

        # ── ⑤ Prompt FLUX ─────────────────────────────────────────────────────
        _flux_model = getattr(_smierc, "HF_API_URL", "").split("/")[-1] if _SMIERC_OK else "FLUX.1-schnell"
        self._title(f, f"⑤  PROPONOWANY TEKST DO {_flux_model.upper()}")
        self._badge(f, FILE_FLUX_GROQ_SYS.name)
        tk.Label(f, text="  Provider: Groq → prompt FLUX  (fallback: DeepSeek)",
                 font=FONT_FILE, fg=FG3, bg=BG).pack(anchor="w", padx=20)
        self.flux_text = self._textbox(f, h=4)
        self.flux_status = tk.Label(f, text="", font=FONT_LBL, fg=FG2, bg=BG)
        self.flux_status.pack(anchor="w", padx=20, pady=2)
        self._btn(f, "▶  Generuj tekst proponowany do FLUX.1-schnell",
                  self._gen_flux_tekst)
        self._sep(f)

        # ── ⑥ Obrazek ────────────────────────────────────────────────────────
        self._title(f, "⑥  GENERUJ OBRAZEK  →  AUTO-ZAPIS")
        tk.Label(f,
            text="  Po wygenerowaniu obrazka — automatyczny zapis do backup/Wyniki_HH_MM_SS/",
            font=FONT_FILE, fg=FG2, bg=BG).pack(anchor="w", padx=20, pady=(0, 4))
        self.img_status = tk.Label(f,
            text="Najpierw wygeneruj tekst proponowany (krok ⑤)",
            font=FONT_LBL, fg=FG3, bg=BG)
        self.img_status.pack(anchor="w", padx=20, pady=4)
        _flux_btn_label = f"🟢  Generuj obrazek  ({_flux_model})  →  auto-zapis"
        self.btn_obrazek = self._btn(f, _flux_btn_label,
            self._gen_obrazek, green=True, state=tk.DISABLED)
        self._sep(f)

        # ── ⑦ Ręczny zapis ────────────────────────────────────────────────────
        self._title(f, "⑦  ZAPISZ RĘCZNIE W DOWOLNYM MOMENCIE")
        tk.Label(f,
            text="  Zapisuje wszystko co zostało wygenerowane do tej pory.\n"
                 "  Zawartość: niebo_wyslannik.png  •  _.txt  •  tekst_zrodlowy.txt"
                 "  •  raport.txt  •  prompts/",
            font=FONT_FILE, fg=FG2, bg=BG, justify=tk.LEFT
        ).pack(anchor="w", padx=20, pady=(0, 4))
        self.backup_status = tk.Label(f, text="", font=FONT_LBL, fg=FG2, bg=BG)
        self.backup_status.pack(anchor="w", padx=20, pady=2)
        self.btn_backup = self._btn(f,
            "💾  Zapisz teraz  +  wyczyść ekran",
            self._save_manual)

        tk.Frame(f, bg=BG, height=40).pack()

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _check_api_keys(self):
        ds = "✓ DeepSeek" if os.environ.get("DEEPSEEK_API_KEY") else "✗ DeepSeek"
        gr = "✓ Groq"     if os.environ.get("GROQ_API_KEY")     else "✗ Groq"
        hf = "✓ HF_TOKEN" if os.environ.get("HF_TOKEN")         else "✗ HF_TOKEN"
        ok = all(os.environ.get(k) for k in ["DEEPSEEK_API_KEY", "GROQ_API_KEY", "HF_TOKEN"])
        self.api_status.configure(text=f"{ds}   {gr}   {hf}",
                                  fg=SUCCESS if ok else ERR)

    def _sep(self, p):
        tk.Frame(p, bg=BORDER, height=1).pack(fill=tk.X, padx=20, pady=8)

    def _title(self, p, text):
        tk.Label(p, text=text, font=FONT_TITLE,
                 fg=ACCENT, bg=BG).pack(anchor="w", padx=20, pady=(4, 2))

    def _badge(self, p, name):
        tk.Label(p, text=f"  📄 {name}", font=FONT_FILE,
                 fg=FG3, bg=BG).pack(anchor="w", padx=20, pady=(0, 2))

    def _textbox(self, parent, h=4, ro=True) -> tk.Text:
        frame = tk.Frame(parent, highlightbackground=BORDER,
                         highlightthickness=1, bg=BORDER)
        frame.pack(fill=tk.X, padx=20, pady=4)
        txt = tk.Text(frame, height=h, wrap=tk.WORD, font=FONT_MONO,
                      bg=BG3, fg=FG, insertbackground=ACCENT,
                      selectbackground=ACCENT2, selectforeground=FG,
                      relief=tk.FLAT, bd=0, padx=10, pady=8,
                      state=tk.DISABLED if ro else tk.NORMAL)
        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview,
                           style="Vertical.TScrollbar")
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        def _resize(e=None):
            lines = int(txt.index("end-1c").split(".")[0])
            txt.configure(height=max(h, min(lines + 1, 32)))
        txt.bind("<Configure>", _resize)
        return txt

    def _btn(self, parent, label, cmd, green=False, state=tk.NORMAL):
        bg = GREEN if green else BTN_BG
        fg = "#ffffff" if green else ACCENT
        hv = GREEN_H if green else ACCENT2
        b = tk.Button(parent, text=label, command=cmd,
                      font=FONT_BTN, fg=fg, bg=bg,
                      activebackground=hv,
                      activeforeground="#ffffff" if green else BG,
                      relief=tk.FLAT, bd=0, pady=9, padx=16,
                      cursor="hand2", state=state)
        b.pack(fill=tk.X, padx=20, pady=(4, 8))
        b.bind("<Enter>", lambda e: b.configure(bg=hv))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        return b

    def _clear_ph(self, e):
        if self.body_text.get("1.0", tk.END).strip() == \
                "Wpisz tutaj przykładową wiadomość od nadawcy...":
            self.body_text.delete("1.0", tk.END)

    def _set(self, w: tk.Text, text: str):
        w.configure(state=tk.NORMAL)
        w.delete("1.0", tk.END)
        w.insert("1.0", text)
        lines = text.count("\n") + 1
        w.configure(height=max(4, min(lines + 2, 32)), state=tk.DISABLED)

    def _loading(self, w: tk.Text, label: str = ""):
        self._set(w, f"⏳ generuję... {label}")

    def _get_body(self) -> str:
        b = self.body_text.get("1.0", tk.END).strip()
        return "" if b == "Wpisz tutaj przykładową wiadomość od nadawcy..." else b

    def _get_wyslannik(self) -> str:
        return self.res_wyslannik.get("1.0", tk.END).strip()

    # ── Generatory ────────────────────────────────────────────────────────────
    def _gen_pawel_1_6(self):
        body = self._get_body()
        if not body:
            messagebox.showwarning("Brak wiadomości", "Wpisz wiadomość nadawcy.")
            return
        self._s["body"] = body
        self._loading(self.res_pawel)
        self.pawel_meta.configure(text="", fg=FG3)
        etap_tresc = self.etapy.get(self.etap_var.get(), "Podróż trwa")
        t0 = datetime.datetime.now()
        self._log(f"START Paweł 1-6 | etap: {etap_tresc}")

        def _run():
            tmpl = load_txt(FILE_PAWEL_1_6,
                "Jesteś Pawłem — zmarłym mężczyzną piszącym z zaświatów. "
                "Piszesz po polsku. Odpowiedź max 5 zdań. "
                "Podpisz się: — Autoresponder Pawła-zza-światów. "
                "Wspomnij że umarłeś na suchoty dnia {data_smierci_str}.")
            system = tmpl.replace("{data_smierci_str}", TODAY)
            result, prov = call_llm_email(system,
                f"Etap w zaświatach: {etap_tresc}\nWiadomość: {body}")
            czas = elapsed(t0)
            self._s.update({"pawel_1_6": result or "", "pawel_1_6_prov": prov,
                             "pawel_1_6_czas": czas})
            self._log(f"KONIEC Paweł 1-6 | provider: {prov} | czas: {czas}")
            self.root.after(0, lambda: (
                self._set(self.res_pawel, result or "[Błąd API]"),
                self.pawel_meta.configure(
                    text=f"  ↳ {prov}  |  {czas}", fg=FG3)
            ))
        threading.Thread(target=_run, daemon=True).start()

    def _gen_pawel_7(self):
        body = self._get_body()
        if not body:
            messagebox.showwarning("Brak wiadomości", "Wpisz wiadomość nadawcy.")
            return
        self._s["body"] = body
        self._loading(self.res_pawel7)
        self.pawel7_meta.configure(text="", fg=FG3)
        etap_tresc = self.etapy.get(self.max_etap, "Reinkarnacja nadchodzi nieuchronnie")
        t0 = datetime.datetime.now()
        self._log(f"START Paweł 7 | etap: {etap_tresc}")

        def _run():
            tmpl = load_txt(FILE_PAWEL_7,
                "Jesteś Pawłem — zmarłym mężczyzną piszącym z zaświatów. "
                "Ton: spokojny, wzruszający. Odpowiedź max 5 zdań. "
                "Umarłem na suchoty dnia {data_smierci_str}. "
                "Poinformuj że nadchodzi reinkarnacja. Pożegnaj się ciepło.")
            system = tmpl.replace("{data_smierci_str}", TODAY)
            result, prov = call_llm_email(system,
                f"Etap: {etap_tresc}\nWiadomość: {body}")
            czas = elapsed(t0)
            self._s.update({"pawel_7": result or "", "pawel_7_prov": prov,
                             "pawel_7_czas": czas})
            self._log(f"KONIEC Paweł 7 | provider: {prov} | czas: {czas}")
            self.root.after(0, lambda: (
                self._set(self.res_pawel7, result or "[Błąd API]"),
                self.pawel7_meta.configure(
                    text=f"  ↳ {prov}  |  {czas}", fg=FG3)
            ))
        threading.Thread(target=_run, daemon=True).start()

    def _gen_wyslannik(self):
        body = self._get_body()
        if not body:
            messagebox.showwarning("Brak wiadomości", "Wpisz wiadomość nadawcy.")
            return
        self._s["body"] = body
        self._loading(self.res_wyslannik)
        self.wyslannik_meta.configure(text="", fg=FG3)
        t0 = datetime.datetime.now()
        self._log("START Wysłannik")

        def _run():
            system = load_txt(FILE_WYSLANNIK,
                "Jesteś wysłannikiem z wyższych sfer duchowych. "
                "Przebijasz każdą rzecz wymienioną przez nadawcę — TYLKO przymiotnikami, "
                "nigdy liczbami. Ton: dostojny, poetycki, lekko absurdalny. Max 4 zdania. "
                "Podpisz się: — Wysłannik z wyższych sfer")
            result, prov = call_llm_email(system, f"Osoba pyta: {body}")
            czas = elapsed(t0)
            self._s.update({"wyslannik": result or "", "wyslannik_prov": prov,
                             "wyslannik_czas": czas, "email_prov": prov})
            self._log(f"KONIEC Wysłannik | provider: {prov} | czas: {czas}")
            self.root.after(0, lambda: (
                self._set(self.res_wyslannik, result or "[Błąd API]"),
                self.wyslannik_meta.configure(
                    text=f"  ↳ {prov}  |  {czas}", fg=FG3)
            ))
        threading.Thread(target=_run, daemon=True).start()

    def _gen_flux_tekst(self):
        wyslannik = self._get_wyslannik()
        if not wyslannik or wyslannik.startswith("⏳") or wyslannik == "[Błąd API]":
            messagebox.showwarning("Brak tekstu Wysłannika",
                "Najpierw wygeneruj odpowiedź Wysłannika (krok ④).")
            return
        self.flux_status.configure(text="⏳ Groq generuje kreatywny prompt FLUX...", fg=FG2)
        self._set(self.flux_text, "...")
        self.btn_obrazek.configure(state=tk.DISABLED)
        t0 = datetime.datetime.now()
        self._log("START generowanie promptu FLUX")

        def _run():
            system = load_txt(FILE_FLUX_GROQ_SYS,
                "You are a creative prompt engineer for FLUX image generator. "
                "Based on the Polish heavenly messenger text, write a surreal, "
                "otherworldly image prompt in English (max 80 words). "
                "Invent bizarre celestial creatures inspired by the content. "
                "NOT photorealistic. End with: divine surreal digital art, "
                "otherworldly paradise, vivid colors, epic scale. Return ONLY the prompt.")
            user = f"Generate a FLUX image prompt based on this heavenly messenger text:\n\n{wyslannik}"
            result, prov = call_llm_flux(system, user)
            if not result:
                result = load_txt(FILE_IMAGE_STYLE,
                    "surreal heavenly paradise, divine golden light, "
                    "celestial beings, otherworldly atmosphere, vivid colors, digital art")
                prov = "statyczny fallback"
            czas = elapsed(t0)
            self._s.update({"flux": result, "flux_prov": prov, "flux_czas": czas})
            self._log(f"KONIEC prompt FLUX | provider: {prov} | czas: {czas}")
            self.root.after(0, lambda: (
                self._set(self.flux_text, result),
                self.flux_status.configure(
                    text=f"✓ Gotowy — {prov}  |  {czas}", fg=SUCCESS),
                self.btn_obrazek.configure(state=tk.NORMAL)
            ))
        threading.Thread(target=_run, daemon=True).start()

    def _gen_obrazek(self):
        if not self._s.get("flux"):
            messagebox.showwarning("Brak promptu",
                "Najpierw wygeneruj tekst proponowany (krok ⑤).")
            return
        _flux_model_name = getattr(_smierc, "HF_API_URL", "").split("/")[-1] if _SMIERC_OK else "FLUX"
        _flux_steps      = getattr(_smierc, "HF_STEPS", 5) if _SMIERC_OK else 5
        self.img_status.configure(
            text=f"⏳ Generuję obrazek {_flux_model_name} (steps={_flux_steps}, ~20-30s)...", fg=FG2)
        self.btn_obrazek.configure(state=tk.DISABLED)
        t0 = datetime.datetime.now()
        self._log("START generowanie obrazka FLUX")

        def _run():
            img_bytes, err = generate_flux_image(self._s["flux"])
            czas = elapsed(t0)
            self._s["img_bytes"] = img_bytes
            self._s["img_czas"]  = czas
            self._s["img_err"]   = err or ""

            if img_bytes:
                self._log(f"KONIEC obrazek OK | rozmiar: {len(img_bytes):,} B | czas: {czas}")
                # Auto-zapis
                try:
                    run_dir = save_all(self._s)
                    self._log(f"AUTO-ZAPIS → {run_dir.name}")
                    self.root.after(0, lambda: self.img_status.configure(
                        text=f"✓ Obrazek OK ({len(img_bytes):,} B)  |  {czas}"
                             f"  →  auto-zapisano: {run_dir.name}",
                        fg=SUCCESS))
                except Exception as e:
                    self._log(f"BŁĄD auto-zapisu: {e}")
                    self.root.after(0, lambda: self.img_status.configure(
                        text=f"✓ Obrazek OK | BŁĄD zapisu: {e}", fg=ERR))
            else:
                self._log(f"BŁĄD obrazek: {err} | czas: {czas}")
                self.root.after(0, lambda: (
                    self.img_status.configure(text=f"✗ Błąd FLUX: {err}", fg=ERR),
                    self.btn_obrazek.configure(state=tk.NORMAL)
                ))
        threading.Thread(target=_run, daemon=True).start()

    def _save_manual(self):
        """Ręczny zapis w dowolnym momencie — zapisuje co jest, czyści ekran."""
        body = self._get_body()
        if body:
            self._s["body"] = body
        if not any([self._s.get("pawel_1_6"), self._s.get("wyslannik"),
                    self._s.get("flux"), self._s.get("img_bytes")]):
            messagebox.showwarning("Brak danych",
                "Nie ma nic do zapisania. Wygeneruj najpierw jakiś wynik.")
            return
        self._log("RĘCZNY ZAPIS")
        try:
            run_dir = save_all(self._s)
            self.backup_status.configure(
                text=f"✓ Zapisano: {run_dir.name}", fg=SUCCESS)
            messagebox.showinfo("✓ Zapisano",
                f"Katalog:\n{run_dir}\n\n"
                f"  niebo_wyslannik.png\n"
                f"  _.txt\n"
                f"  tekst_zrodlowy.txt\n"
                f"  raport.txt\n"
                f"  prompts/ (requiem_*.txt + smierc.py)")
            self._clear_all()
        except Exception as e:
            messagebox.showerror("Błąd zapisu", str(e))

    def _clear_all(self):
        for w in [self.res_pawel, self.res_pawel7, self.res_wyslannik, self.flux_text]:
            self._set(w, "")
        for lbl in [self.pawel_meta, self.pawel7_meta, self.wyslannik_meta]:
            lbl.configure(text="", fg=FG3)
        self.flux_status.configure(text="", fg=FG2)
        self.img_status.configure(
            text="Najpierw wygeneruj tekst proponowany (krok ⑤)", fg=FG3)
        self.backup_status.configure(text="", fg=FG2)
        self.btn_obrazek.configure(state=tk.DISABLED)
        self._s = self._empty_state()


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = RequiemApp(root)
    root.mainloop()
