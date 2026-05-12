# ═══════════════════════════════════════════════════════════════════════════════
# EMOTKA FLUX — generowanie obrazka na podstawie treści emaila
# Wklej do zwykly.py w miejscu _generate_icon_flux()
# JSON config: prompts/zwykly_emotka_flux.json
# ═══════════════════════════════════════════════════════════════════════════════

EMOTKA_FLUX_JSON_PATH = os.path.join(PROMPTS_DIR, "zwykly_emotka_flux.json")


def _load_emotka_flux_config() -> dict:
    """
    Wczytuje konfigurację z zwykly_emotka_flux.json.
    Fallback: minimalny dict jeśli plik niedostępny.
    """
    try:
        with open(EMOTKA_FLUX_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        logger.info("[emotka-flux] Config wczytany OK")
        return data
    except FileNotFoundError:
        logger.warning("[emotka-flux] Brak zwykly_emotka_flux.json — używam fallbacku")
    except json.JSONDecodeError as e:
        logger.error("[emotka-flux] Błąd JSON w config: %s", e)
    return {}


def _emotka_wykryj_miejsca(body: str, mapowanie: dict) -> str:
    """
    Szuka nazw miejsc/instytucji w treści emaila.
    Zwraca opis wizualny miejsca lub pusty string.
    """
    body_lower = body.lower()
    for slowo, opis in mapowanie.items():
        if slowo.startswith("_"):
            continue
        if slowo.lower() in body_lower:
            logger.debug("[emotka-flux] Wykryto miejsce: '%s' → %s", slowo, opis[:60])
            return opis
    return mapowanie.get("_domyslny", "")


def _emotka_wykryj_tematy(body: str, mapowanie: dict) -> list[str]:
    """
    Szuka słów kluczowych z emaila i zbiera pasujące opisy wizualne.
    Zwraca listę max 3 opisów (żeby prompt nie był zbyt długi).
    """
    body_lower = body.lower()
    trafione = []
    for slowo, opis in mapowanie.items():
        if slowo.startswith("_"):
            continue
        if slowo.lower() in body_lower and opis not in trafione:
            trafione.append(opis)
        if len(trafione) >= 3:
            break
    if not trafione:
        trafione.append(mapowanie.get("_domyslny", "symbolic everyday objects"))
    return trafione


def _emotka_wykryj_emocje_nadawcy(body: str, cfg_emocja: dict) -> str:
    """
    Wykrywa emocję/ton nadawcy na podstawie charakterystycznych zwrotów.
    Zwraca opis nastroju do wplecenia w prompt wizualny.
    """
    body_lower = body.lower()
    wykrywanie = cfg_emocja.get("wykrywanie", {})
    przeklad = cfg_emocja.get("przeklad_na_nastroj", {})

    for typ_emocji, zwroty in wykrywanie.items():
        for zwrot in zwroty:
            if zwrot.lower() in body_lower:
                nastroj = przeklad.get(typ_emocji, "")
                logger.debug(
                    "[emotka-flux] Emocja nadawcy: '%s' → %s", typ_emocji, nastroj[:60]
                )
                return nastroj

    return przeklad.get("uprzejmy_formalny", "natural atmosphere")


def _emotka_buduj_prompt(
    body: str,
    emotion_key: str,
    cfg: dict,
) -> str:
    """
    Buduje prompt FLUX lokalnie bez calla AI.
    Łączy: opis miejsca + tematy z emaila + nastrój emocjonalny + styl wizualny + sufiks jakości.

    Zwraca gotowy string promptu (max długość z config).
    """
    budowanie = cfg.get("budowanie_promptu", {})
    ekstrakcja = cfg.get("ekstrakcja_kontekstu", {})

    # ── Nastrój z emocji wykrytej przez AI (z pola "emocja" w JSON odpowiedzi) ─
    mood_mapa = budowanie.get("mood_prefix_mapa", {})
    mood_prefix = mood_mapa.get(emotion_key, mood_mapa.get("_domyslny", "atmospheric light,"))

    # ── Miejsca z treści emaila ───────────────────────────────────────────────
    miejsca_mapa = ekstrakcja.get("miejsca", {}).get("mapowanie_na_opis", {})
    opis_miejsca = _emotka_wykryj_miejsca(body, miejsca_mapa)

    # ── Tematy/słowa kluczowe z emaila ───────────────────────────────────────
    tematy_mapa = ekstrakcja.get("tematy", {}).get("mapowanie", {})
    tematy_lista = _emotka_wykryj_tematy(body, tematy_mapa)
    tematy_str = ", ".join(tematy_lista)

    # ── Emocja nadawcy z tonu wiadomości ─────────────────────────────────────
    cfg_emocja = ekstrakcja.get("emocja_nadawcy", {})
    nastroj_nadawcy = _emotka_wykryj_emocje_nadawcy(body, cfg_emocja)

    # ── Styl wizualny — losowy wariant ────────────────────────────────────────
    style_warianty = budowanie.get("visual_style_warianty", [
        "35mm film photography, shallow depth of field, cinematic color grading"
    ])
    visual_style = random.choice(style_warianty)

    # ── Sufiks jakości — zakazy z zasady_generowania ──────────────────────────
    quality_suffix = budowanie.get(
        "quality_suffix",
        "photorealistic, no text, no writing, no people at computers, highly detailed"
    )

    # ── Złóż prompt według struktury z JSON ──────────────────────────────────
    # Struktura: SCENE + OBJECTS + MOOD + STYLE + QUALITY
    czesci = []

    if opis_miejsca:
        czesci.append(opis_miejsca)

    if tematy_str:
        czesci.append(tematy_str)

    if nastroj_nadawcy:
        czesci.append(nastroj_nadawcy)

    if mood_prefix:
        czesci.append(mood_prefix)

    czesci.append(visual_style)
    czesci.append(quality_suffix)

    prompt = ", ".join(filter(None, czesci))

    # Przytnij do max długości z config
    max_len = budowanie.get("max_dlugosc_promptu", 400)
    if len(prompt) > max_len:
        prompt = prompt[:max_len].rsplit(",", 1)[0]  # nie ucinaj w środku słowa
        logger.debug("[emotka-flux] Prompt przycięty do %d znaków", len(prompt))

    logger.info("[emotka-flux] Prompt zbudowany (%d znaków): %.150s…", len(prompt), prompt)
    return prompt


def _generate_emotka_from_email(
    body: str,
    emotion_key: str = "",
    sender_name: str = "",
    test_mode: bool = False,
) -> dict | None:
    """
    Generuje unikalny obrazek FLUX na podstawie treści emaila.
    Zastępuje statyczną emotkę PNG z katalogu emotki/.

    Każdy nadawca dostaje inny obraz — wyobrażenie miejsca, atmosfery
    lub konsekwencji opisanych w emailu. Bez tekstu, bez osób piszących.

    Parametry:
        body        — treść emaila (plain text)
        emotion_key — emocja wykryta przez AI ("radosc", "smutek" itp.)
        sender_name — imię nadawcy (do logów)
        test_mode   — True → zastępczy obrazek zamiast FLUX (oszczędność tokenów)

    Zwraca dict {base64, content_type, filename} lub None przy błędzie.
    """
    logger.info(
        "[emotka-flux] START — nadawca=%s | emocja=%s | test_mode=%s",
        sender_name or "(brak)",
        emotion_key or "(brak)",
        test_mode,
    )

    # ── test_mode → zastępczy obrazek bez FLUX ────────────────────────────────
    if test_mode:
        logger.info("[emotka-flux] test_mode=True — używam zastepczy.jpg")
        sub = _load_substitute_image()
        if sub:
            result = dict(sub)
            result["filename"] = "emotka_zastepczy.jpg"
            return result
        return None

    # ── Wczytaj config ────────────────────────────────────────────────────────
    cfg = _load_emotka_flux_config()

    # ── Fallback gdy brak config lub brak treści ──────────────────────────────
    if not cfg or not body or not body.strip():
        fallback_prompt = cfg.get("fallback", {}).get("prompt", "") if cfg else ""
        if not fallback_prompt:
            fallback_prompt = (
                "A contemplative urban Polish landscape, quiet street, "
                "late afternoon autumn light, 35mm film photography, "
                "photorealistic, no text, no people at computers, highly detailed"
            )
        logger.warning("[emotka-flux] Brak body lub config — używam fallback promptu")
        prompt = fallback_prompt
    else:
        # ── Zbuduj prompt z treści emaila ─────────────────────────────────────
        prompt = _emotka_buduj_prompt(body, emotion_key, cfg)

        # Ostateczny fallback jeśli prompt pusty
        if not prompt.strip():
            prompt = cfg.get("fallback", {}).get("prompt", "cinematic urban scene, photorealistic")

    # ── Parametry HF z config ─────────────────────────────────────────────────
    hf_params = cfg.get("parametry_hf", {})
    panel_index = cfg.get("panel_index", 96)

    steps    = hf_params.get("num_inference_steps", HF_STEPS)
    guidance = hf_params.get("guidance_scale", HF_GUIDANCE)
    width    = hf_params.get("width", 768)
    height   = hf_params.get("height", 768)

    # ── Tokeny HF ─────────────────────────────────────────────────────────────
    tokens = get_active_tokens()
    if not tokens:
        logger.error("[emotka-flux] Brak aktywnych tokenów HF — zwracam None")
        return None

    seed = random.randint(0, 2**32 - 1)
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": steps,
            "guidance_scale": guidance,
            "width": width,
            "height": height,
            "seed": seed,
        },
    }

    logger.info(
        "[emotka-flux] FLUX call — %d tokenów | panel=%d | seed=%d | prompt(150)=%.150s",
        len(tokens),
        panel_index,
        seed,
        prompt,
    )

    # ── Rotacja tokenów od panel_index ────────────────────────────────────────
    offset = (panel_index - 1) % len(tokens)
    tokens = tokens[offset:] + tokens[:offset]

    raw_img = None
    used_token = None

    for name, token in tokens:
        headers = {"Authorization": f"Bearer {token}", "Accept": "image/png"}
        try:
            resp = requests.post(
                HF_API_URL, headers=headers, json=payload, timeout=HF_TIMEOUT
            )
            remaining = resp.headers.get("X-Remaining-Requests")

            if resp.status_code == 200:
                raw_img = resp.content
                used_token = name
                logger.info(
                    "[emotka-flux] ✓ Token %s OK — %dB PNG | pozostało: %s",
                    name,
                    len(raw_img),
                    remaining or "?",
                )
                break
            elif resp.status_code == 402:
                mark_dead(name)
                logger.warning("[emotka-flux] 402 token=%s — wyczerpane kredyty", name)
            elif resp.status_code in (401, 403):
                mark_dead(name)
                logger.warning("[emotka-flux] HTTP %d token=%s — nieważny", resp.status_code, name)
            elif resp.status_code == 429:
                logger.warning("[emotka-flux] 429 token=%s — rate limit, próbuję następny", name)
            elif resp.status_code in (503, 529):
                logger.warning("[emotka-flux] %d token=%s — przeciążony, próbuję następny", resp.status_code, name)
            else:
                logger.warning(
                    "[emotka-flux] HTTP %d token=%s: %s",
                    resp.status_code, name, resp.text[:80],
                )
        except requests.exceptions.Timeout:
            logger.warning("[emotka-flux] Timeout token=%s (%ds)", name, HF_TIMEOUT)
        except requests.exceptions.ConnectionError as e:
            logger.warning("[emotka-flux] ConnectionError token=%s: %s", name, str(e)[:80])
        except Exception as e:
            logger.warning("[emotka-flux] Wyjątek token=%s: %s", name, str(e)[:80])

    if not raw_img:
        logger.error("[emotka-flux] Wszystkie tokeny zawiodły — zwracam None")
        return None

    # ── Konwertuj PNG → JPG i opcjonalnie zmniejsz ────────────────────────────
    param_img = cfg.get("parametry_obrazka", {})
    jpg_quality = param_img.get("jakosc_jpg", TYLER_JPG_QUALITY)
    zmniejsz    = param_img.get("zmniejsz_do_procent", 95) / 100.0

    try:
        from PIL import Image as PILImage

        pil = PILImage.open(io.BytesIO(raw_img)).convert("RGB")

        if zmniejsz < 1.0:
            w, h = pil.size
            pil = pil.resize(
                (int(w * zmniejsz), int(h * zmniejsz)),
                PILImage.LANCZOS,
            )

        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=jpg_quality, optimize=True)
        jpg_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"emotka_flux_{ts}_seed{seed}.jpg"
        size_kb = len(buf.getvalue()) // 1024

        logger.info(
            "[emotka-flux] KONIEC OK — %s | %dKB JPG | token=%s",
            filename, size_kb, used_token,
        )

        return {
            "base64": jpg_b64,
            "content_type": "image/jpeg",
            "filename": filename,
            "seed": seed,
            "token_name": used_token,
            "size_jpg": f"{size_kb}KB",
            "prompt_preview": prompt[:120],
        }

    except ImportError:
        logger.error("[emotka-flux] Pillow niedostępny — zwracam surowy PNG")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return {
            "base64": base64.b64encode(raw_img).decode("ascii"),
            "content_type": "image/png",
            "filename": f"emotka_flux_{ts}.png",
            "seed": seed,
        }
    except Exception as e:
        logger.warning("[emotka-flux] Błąd konwersji JPG: %s — zwracam PNG", e)
        return {
            "base64": base64.b64encode(raw_img).decode("ascii"),
            "content_type": "image/png",
            "filename": f"emotka_flux_{ts}.png",
            "seed": seed,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PODMIANA W build_zwykly_section — zamień stary blok emotki na nowy
# ═══════════════════════════════════════════════════════════════════════════════
#
# STARY KOD (usuń):
#   emoticon_b64 = _generate_icon_flux(emotion_key, sender_name)
#   emoticon = None
#   if emoticon_b64:
#       emoticon = {
#           "base64": emoticon_b64,
#           "content_type": "image/png",
#           "filename": f"emocja_{emotion_key or 'default'}.png",
#       }
#
# NOWY KOD (wstaw):
#   emoticon = _generate_emotka_from_email(
#       body=body,
#       emotion_key=emotion_key,
#       sender_name=sender_name,
#       test_mode=test_mode,
#   )
#
# ═══════════════════════════════════════════════════════════════════════════════
