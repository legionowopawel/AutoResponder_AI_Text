"""
core/hf_token_manager.py
════════════════════════════════════════════════════════════════════════════════
Centralny menedżer tokenów CLOUDFLARE Workers AI — współdzielony przez WSZYSTKIE
respondery (zwykly, smierc, dociekliwy, …).

NAZWA PLIKU I API ZOSTAJĄ "hf_*" CELOWO (hf_tokens, get_active_tokens,
mark_dead, is_dead) — dzięki temu respondery i app.py nie wymagają zmian.
Wcześniej trzymał tokeny Hugging Face; od 2026-11 trzyma tokeny Cloudflare.

ZMIENNE ŚRODOWISKOWE (Render → Environment):
  CF_ACCOUNT_ID    Account ID Cloudflare (32 znaki hex) — wspólny dla tokenów
  CF_API_TOKEN     token API z uprawnieniami Workers AI (Read + Edit)
  CF_API_TOKEN1…   kolejne tokeny (do CF_API_TOKEN99)
  CF_ACCOUNT_ID1…  OPCJONALNIE: Account ID dla tokenu o tym samym numerze,
                   gdy należy do innego konta Cloudflare niż CF_ACCOUNT_ID

  Uwaga: limit darmowy (10 000 neuronów/dzień) jest per KONTO, nie per token.

WARTOŚĆ TOKENU zwracana przez get_active_tokens() to "ACCOUNT_ID:TOKEN"
(pack_cf_credential / unpack_cf_credential) — dzięki temu generate_flux_bytes()
dostaje komplet danych w jednym stringu, a sygnatury responderów się nie zmieniają.

ZASADY:
  1. Stan tokenów (aktywne / martwe) jest JEDEN dla całego procesu serwera.
  2. Walidacja tokenu przez lekki GET .../tokens/verify (nie zużywa neuronów).
  3. Warm-up jednorazowy przy pierwszym użyciu (lazy).
  4. Tokeny oznaczane jako martwe przez mark_dead(name) podczas sesji.
  5. Reset ręczny przez /admin/hf-reset.

KLUCZOWE OPTYMALIZACJE:
  - Gdy ALL_DEAD_CACHE=True → get_active_tokens() zwraca [] natychmiast,
    zero requestów HTTP. Kasuje cache po RECHECK_AFTER sekundach.
  - warmup() uruchamia się MAX RAZ co MIN_WARMUP_INTERVAL sekund
    — chroni przed pętlą restart→warmup→OOM.
  - Liczba równoległych wątków warm-upu ograniczona do MAX_WARMUP_THREADS.

UŻYCIE:
    from core.hf_token_manager import hf_tokens, mark_dead, get_active_tokens

    tokens = get_active_tokens()          # [(name, "ACCOUNT_ID:TOKEN"), ...]
    mark_dead("CF_API_TOKEN")             # po błędzie 401/402/403
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
    TimeoutError as FuturesTimeout,
)
from typing import Optional

import requests as _requests

logger = logging.getLogger(__name__)

# ─── Stałe konfiguracyjne ──────────────────────────────────────────────────────

_CF_API = "https://api.cloudflare.com/client/v4"
# Weryfikacja tokenu (nie zużywa neuronów):
#   - tokeny użytkownika: GET /user/tokens/verify
#   - tokeny konta (Account API Tokens): GET /accounts/{id}/tokens/verify
# Próbujemy oba — token jest MARTWY dopiero gdy OBA zwrócą 401/403.
_CHECK_TIMEOUT = 6  # timeout pojedynczego sprawdzenia tokenu (s)
_TOKEN_RANGE = 100  # skanuj CF_API_TOKEN, CF_API_TOKEN1 … CF_API_TOKEN99
_MAX_WARMUP_THREADS = 8  # max równoległych wątków podczas warm-upu

# Po tym czasie od warm-upu z wynikiem ALL_DEAD — spróbuj ponownie
# 0 = nigdy nie próbuj ponownie (tokeny 401 są trwale martwe)
_RECHECK_AFTER = 300  # po 5 min sprawdź ponownie (też po odnowieniu dziennego limitu)

# Minimalny odstęp między kolejnymi warm-upami (ochrona przed pętlą OOM-restart)
_MIN_WARMUP_INTERVAL = 120  # sekund


# ─── Poświadczenia: "ACCOUNT_ID:TOKEN" ────────────────────────────────────────


def pack_cf_credential(account_id: str, token: str) -> str:
    """Skleja Account ID i token w jeden string (token CF nie zawiera ':')."""
    return f"{account_id}:{token}"


def unpack_cf_credential(value: str) -> tuple[str, str]:
    """Rozdziela "ACCOUNT_ID:TOKEN". Zwraca ("", "") przy złym formacie."""
    if value and ":" in value:
        account_id, token = value.split(":", 1)
        return account_id.strip(), token.strip()
    return "", (value or "").strip()


# ─── Stan tokenu ──────────────────────────────────────────────────────────────


class _TokenState:
    __slots__ = ("name", "value", "alive", "dead_reason", "dead_at", "remaining")

    def __init__(self, name: str, value: str):
        self.name: str = name
        self.value: str = value
        self.alive: bool = True
        self.dead_reason: str = ""
        self.dead_at: float = 0.0
        self.remaining: Optional[int] = None


# ─── Menedżer ─────────────────────────────────────────────────────────────────


class HFTokenManager:
    """
    Singleton — jeden obiekt na cały proces Flask. Thread-safe (RLock).
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._tokens: dict[str, _TokenState] = {}
        self._warmed_up: bool = False
        self._warmup_lock: threading.Lock = threading.Lock()
        self._warmup_running: bool = False
        self._last_warmup_at: float = 0.0  # monotonic timestamp ostatniego warm-upu
        self._all_dead_since: float = 0.0  # kiedy ostatnio stwierdzono ALL DEAD

    # ── Wczytywanie tokenów ze środowiska ─────────────────────────────────────

    def _load_from_env(self) -> list[_TokenState]:
        default_account = os.getenv("CF_ACCOUNT_ID", "").strip()
        names = ["CF_API_TOKEN"] + [f"CF_API_TOKEN{i}" for i in range(1, _TOKEN_RANGE)]
        states = []
        for name in names:
            val = os.getenv(name, "").strip()
            if not val:
                continue
            suffix = name[len("CF_API_TOKEN"):]  # "" albo "1", "2", …
            account_id = os.getenv(f"CF_ACCOUNT_ID{suffix}", "").strip() or default_account
            if not account_id:
                logger.error(
                    "[hf-manager] Token %s pominięty — brak CF_ACCOUNT_ID%s w zmiennych środowiskowych",
                    name,
                    suffix,
                )
                continue
            states.append(_TokenState(name, pack_cf_credential(account_id, val)))
        return states

    # ── Lekka weryfikacja jednego tokenu ──────────────────────────────────────

    @staticmethod
    def _check_token_alive(name: str, value: str) -> tuple[bool, str]:
        """
        Sprawdza token przez GET .../tokens/verify (nie zużywa neuronów).

        Token jest uznawany za MARTWY wyłącznie gdy:
          - verify zwróci status inny niż "active" (expired/disabled), albo
          - OBA endpointy (user i account) zwrócą 401/403.
        Timeout, 429 i błędy 5xx = zakładamy aktywny (fail-safe).
        """
        account_id, token = unpack_cf_credential(value)
        headers = {"Authorization": f"Bearer {token}"}

        urls = [f"{_CF_API}/user/tokens/verify"]
        if account_id:
            urls.append(f"{_CF_API}/accounts/{account_id}/tokens/verify")

        last_auth_status = None
        for url in urls:
            try:
                resp = _requests.get(url, headers=headers, timeout=_CHECK_TIMEOUT)
            except _requests.exceptions.Timeout:
                logger.warning("[hf-manager] Token %s: timeout verify — zakładam aktywny", name)
                return True, ""
            except Exception as e:
                logger.warning(
                    "[hf-manager] Token %s: błąd verify (%s) — zakładam aktywny", name, e
                )
                return True, ""

            status = resp.status_code
            if status == 200:
                try:
                    cf_status = ((resp.json() or {}).get("result") or {}).get("status")
                except Exception:
                    cf_status = None
                resp.close()
                if cf_status and cf_status != "active":
                    reason = f"Token Cloudflare ma status '{cf_status}'"
                    logger.warning("[hf-manager] Token %s MARTWY: %s", name, reason)
                    return False, reason
                return True, ""

            resp.close()
            if status in (401, 403):
                last_auth_status = status
                continue  # spróbuj drugiego endpointu (user ↔ account)

            # 429 / 5xx / inne — nie uśmiercaj
            logger.debug(
                "[hf-manager] Token %s: HTTP %s na verify — zakładam aktywny", name, status
            )
            return True, ""

        reason = f"Nieważny token (HTTP {last_auth_status} na user i account verify)"
        logger.warning("[hf-manager] Token %s MARTWY: %s", name, reason)
        return False, reason

    # ── Warm-up ───────────────────────────────────────────────────────────────

    def warmup(self, force: bool = False) -> None:
        """
        Sprawdza wszystkie tokeny JEDEN raz.
        - Blokuje warmup_lock żeby nie uruchamiać wielokrotnie równolegle.
        - Respektuje _MIN_WARMUP_INTERVAL — chroni przed pętlą OOM-restart.
        - Ogranicza równoległość do _MAX_WARMUP_THREADS.
        """
        with self._warmup_lock:
            if self._warmed_up and not force:
                return

            now = time.monotonic()
            if not force and (now - self._last_warmup_at) < _MIN_WARMUP_INTERVAL:
                # Za wcześnie na kolejny warm-up — zwróć co mamy
                logger.info(
                    "[hf-manager] Warm-up pominięty — był %.0fs temu (min %ds)",
                    now - self._last_warmup_at,
                    _MIN_WARMUP_INTERVAL,
                )
                self._warmed_up = True  # traktuj jako "done" żeby nie loopować
                return

            self._last_warmup_at = now

            states = self._load_from_env()
            if not states:
                logger.error(
                    "[hf-manager] Brak tokenów Cloudflare (CF_API_TOKEN* + CF_ACCOUNT_ID) w zmiennych środowiskowych!"
                )
                with self._lock:
                    self._tokens = {}
                    self._warmed_up = True
                return

            logger.info("[hf-manager] Warm-up: sprawdzam %d tokenów Cloudflare…", len(states))

            # Równoległe sprawdzanie z ograniczoną pulą wątków
            results: dict[str, tuple[bool, str]] = {}
            with ThreadPoolExecutor(max_workers=_MAX_WARMUP_THREADS) as pool:
                future_to_name = {
                    pool.submit(self._check_token_alive, s.name, s.value): s.name
                    for s in states
                }
                try:
                    for future in as_completed(
                        future_to_name, timeout=_CHECK_TIMEOUT + 4
                    ):
                        name = future_to_name[future]
                        try:
                            results[name] = future.result()
                        except Exception as e:
                            logger.warning(
                                "[hf-manager] Błąd sprawdzenia %s: %s", name, e
                            )
                            results[name] = (True, "")  # fail-safe: zakładaj aktywny
                except FuturesTimeout:
                    logger.warning(
                        "[hf-manager] Warm-up timeout — część tokenów nieznana"
                    )
                    for name in future_to_name.values():
                        if name not in results:
                            results[name] = (True, "")  # fail-safe

            with self._lock:
                self._tokens = {}
                for s in states:
                    alive, reason = results.get(s.name, (True, ""))
                    s.alive = alive
                    s.dead_reason = reason
                    s.dead_at = 0.0 if alive else time.monotonic()
                    self._tokens[s.name] = s

                active = sum(1 for s in self._tokens.values() if s.alive)
                dead = len(self._tokens) - active

                if active == 0 and self._tokens:
                    self._all_dead_since = time.monotonic()
                    logger.warning(
                        "[hf-manager] WSZYSTKIE %d TOKENY MARTWE — "
                        "FLUX wyłączony do ręcznego resetu lub upływu %ds",
                        dead,
                        _RECHECK_AFTER or 999999,
                    )
                else:
                    self._all_dead_since = 0.0

            logger.info(
                "[hf-manager] Warm-up: %d aktywnych / %d martwych / %d łącznie",
                active,
                dead,
                len(self._tokens),
            )
            self._warmed_up = True

    # ── Publiczne API ──────────────────────────────────────────────────────────

    def get_active_tokens(self) -> list[tuple[str, str]]:
        """
        Zwraca listę aktywnych tokenów: [(name, value), …]

        FAST-PATH: gdy wszystkie tokeny są martwe → zwraca [] BEZ warm-upu
        i BEZ żadnych requestów HTTP. Sprawdza tylko czy minął _RECHECK_AFTER.
        """
        # Fast-path: wszystkie martwe i _RECHECK_AFTER=0 → od razu []
        if self._warmed_up and self._all_dead_since > 0:
            if _RECHECK_AFTER == 0:
                return []
            if (time.monotonic() - self._all_dead_since) < _RECHECK_AFTER:
                return []
            # Czas minął — zresetuj i sprawdź ponownie
            logger.info(
                "[hf-manager] Ponowne sprawdzenie tokenów po %ds", _RECHECK_AFTER
            )
            with self._lock:
                self._warmed_up = False
                self._all_dead_since = 0.0

        if not self._warmed_up:
            self.warmup()

        with self._lock:
            return [(s.name, s.value) for s in self._tokens.values() if s.alive]

    def mark_dead(self, name: str, reason: str = "402/401/403") -> None:
        """
        Oznacza token jako martwy. Wywoływane przez respondery po błędzie.
        Gdy po oznaczeniu wszystkie są martwe — ustawia _all_dead_since.
        """
        with self._lock:
            s = self._tokens.get(name)
            if s is None:
                logger.debug("[hf-manager] mark_dead(%s) — token nieznany", name)
                return
            if not s.alive:
                return  # już martwy, nic do roboty

            s.alive = False
            s.dead_reason = reason
            s.dead_at = time.monotonic()

            active = sum(1 for x in self._tokens.values() if x.alive)
            logger.warning(
                "[hf-manager] Token %s → MARTWY (%s). Aktywnych: %d",
                name,
                reason,
                active,
            )

            if active == 0:
                self._all_dead_since = time.monotonic()
                logger.warning(
                    "[hf-manager] WSZYSTKIE TOKENY MARTWE — "
                    "kolejne wywołania get_active_tokens() zwrócą [] natychmiast"
                )

    def mark_remaining(self, name: str, remaining: int) -> None:
        with self._lock:
            s = self._tokens.get(name)
            if s:
                s.remaining = remaining

    def is_dead(self, name: str) -> bool:
        with self._lock:
            s = self._tokens.get(name)
            return s is not None and not s.alive

    def all_dead(self) -> bool:
        """True gdy wszystkie znane tokeny są martwe (lub brak tokenów)."""
        if not self._warmed_up:
            return False
        with self._lock:
            if not self._tokens:
                return True
            return self._all_dead_since > 0

    def status_report(self) -> list[dict]:
        """Pełny raport stanu — do /admin/hf-reset."""
        if not self._warmed_up:
            # Nie blokuj endpointu status jeśli warm-up nie był wykonany
            return [{"info": "warm-up nie wykonany — brak danych"}]
        with self._lock:
            now = time.monotonic()
            return [
                {
                    "name": s.name,
                    "alive": s.alive,
                    "reason": s.dead_reason or "OK",
                    "remaining": s.remaining,
                    "dead_ago": (
                        f"{int(now - s.dead_at)}s temu"
                        if not s.alive and s.dead_at
                        else None
                    ),
                }
                for s in self._tokens.values()
            ]

    def reset(self) -> None:
        """
        Resetuje stan — wymusza ponowny warm-up przy następnym użyciu.
        Używać przy ręcznej zmianie tokenów w Render env.
        """
        with self._warmup_lock:
            with self._lock:
                self._warmed_up = False
                self._all_dead_since = 0.0
                self._last_warmup_at = 0.0  # zezwól na natychmiastowy warm-up
                self._tokens = {}
        logger.info("[hf-manager] Reset — warm-up przy następnym get_active_tokens()")

    def force_reset(self) -> None:
        """
        Reset TWARDY — ignoruje _MIN_WARMUP_INTERVAL.
        Tylko do użytku przez /admin/hf-reset gdy tokeny faktycznie zmieniono.
        """
        with self._warmup_lock:
            with self._lock:
                self._warmed_up = False
                self._all_dead_since = 0.0
                self._last_warmup_at = 0.0  # zezwól na natychmiastowy warm-up
                self._tokens = {}
        logger.info(
            "[hf-manager] Force-reset — warm-up przy następnym użyciu (bez cooldown)"
        )


# ── Singleton ──────────────────────────────────────────────────────────────────
hf_tokens = HFTokenManager()
cf_tokens = hf_tokens  # alias — nowa, poprawna nazwa


# ── Skróty (dla wygody migracji) ──────────────────────────────────────────────


def get_active_tokens() -> list[tuple[str, str]]:
    """Zwraca aktywne tokeny [(name, value), …]"""
    return hf_tokens.get_active_tokens()


def mark_dead(name: str, reason: str = "błąd 402/401/403") -> None:
    """Oznacza token jako martwy."""
    hf_tokens.mark_dead(name, reason)


def mark_remaining(name: str, remaining: int) -> None:
    """Aktualizuje licznik pozostałych requestów."""
    hf_tokens.mark_remaining(name, remaining)


def is_dead(name: str) -> bool:
    """Sprawdza czy token jest martwy."""
    return hf_tokens.is_dead(name)
