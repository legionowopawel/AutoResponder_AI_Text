import os
import base64
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# -----------------------------------
# 1. Normalizacja Gmaili
# -----------------------------------
def normalize_email(email: str) -> str:
    email = (email or "").lower().strip()

    # Jeśli Gmail zwraca format: "Imię Nazwisko <email>"
    if "<" in email and ">" in email:
        start = email.find("<") + 1
        end = email.find(">")
        email = email[start:end].strip()

    # Normalizacja Gmaila (kropki i aliasy)
    if email.endswith("@gmail.com"):
        local, domain = email.split("@")
        local = local.replace(".", "")
        local = local.split("+", 1)[0]
        return f"{local}@{domain}"

    return email


# -----------------------------------
# 2. Wczytywanie list emaili z ENV
# -----------------------------------
def load_allowed_emails(env_name: str):
    env = os.getenv(env_name, "")
    if not env:
        print(f"[WARN] Brak {env_name} w zmiennych środowiskowych")
        return set()

    emails = set()
    for e in env.split(","):
        clean = normalize_email(e.strip())
        if clean:
            emails.add(clean)

    print(f"[INFO] Wczytano emaile z {env_name}:", emails)
    return emails


ALLOWED_EMAILS = load_allowed_emails("ALLOWED_EMAILS")
ALLOWED_EMAILS_BIZ = load_allowed_emails("ALLOWED_EMAILS_BIZNES")
SLOWO_KLUCZ = (os.getenv("SLOWO_KLUCZ", "") or "").strip().lower()


# -----------------------------------
# 3. Limity długości
# -----------------------------------
MAX_PROMPT_CHARS = 2500
MAX_USER_CHARS = 1500
MAX_MODEL_INPUT_CHARS = 4000
MAX_MODEL_REPLY_CHARS = 1500


def load_prompt(filename: str = "prompt.txt"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            txt = f.read()
            if len(txt) > MAX_PROMPT_CHARS:
                txt = txt[:MAX_PROMPT_CHARS]
            print(f"[INFO] Wczytano {filename} (długość:", len(txt), ")")
            return txt
    except FileNotFoundError:
        print(f"[ERROR] Brak pliku {filename}")
        return "Brak pliku prompt.txt\n\n{{USER_TEXT}}"


def summarize_and_truncate(text: str, max_chars: int = MAX_USER_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text

    summary = text[:max_chars]
    return (
        "Streszczenie długiej wiadomości użytkownika (skrócone do bezpiecznej długości):\n\n"
        + summary
    )


def build_safe_prompt(user_text: str, base_prompt: str) -> str:
    safe_user_text = summarize_and_truncate(user_text, MAX_USER_CHARS)
    prompt = base_prompt.replace("{{USER_TEXT}}", safe_user_text)

    if len(prompt) > MAX_MODEL_INPUT_CHARS:
        prompt = prompt[:MAX_MODEL_INPUT_CHARS]

    return prompt


def truncate_reply(text: str, max_chars: int = MAX_MODEL_REPLY_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Odpowiedź skrócona do bezpiecznej długości]"


# -----------------------------------
# 4. Funkcje AI – GROQ (tekst)
# -----------------------------------
def call_groq(user_text: str):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza GROQ (YOUR_GROQ_API_KEY)")
        return None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak listy modeli GROQ (GROQ_MODELS)")
        return None, None

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    base_prompt = load_prompt("prompt.txt")
    prompt = build_safe_prompt(user_text, base_prompt)

    for model_id in models:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                },
                timeout=20,
            )

            if response.status_code != 200:
                print("[ERROR] GROQ error:", response.status_code, response.text)
                continue

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return truncate_reply(content), f"GROQ:{model_id}"

        except Exception as e:
            print("[EXCEPTION] GROQ:", e)
            continue

    print("[WARN] Żaden model GROQ nie zwrócił odpowiedzi")
    return None, None


# -----------------------------------
# 4b. Funkcje AI – GROQ (klienci biznesowi / notariusz)
# -----------------------------------
BIZ_PROMPT = """
Jesteś systemem automatycznej odpowiedzi dla kancelarii notarialnej.
Twoim zadaniem jest:

1. ZAWSZE potraktować wiadomość klienta jako pytanie, nawet jeśli:
   • jest bardzo krótka,
   • jest niejasna,
   • jest jednym słowem (np. „drzewo”),
   • jest tylko stwierdzeniem.

2. Odpowiedzieć w sposób:
   • uprzejmy,
   • profesjonalny,
   • informacyjny,
   • neutralny,
   • bez udzielania porad prawnych,
   • bez interpretacji przepisów,
   • bez formułowania opinii notarialnych.

3. Każdą odpowiedź zakończ obowiązkową klauzulą:
   „To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej.”

4. Na podstawie treści wiadomości dokonaj klasyfikacji tematu do jednej z poniższych kategorii PDF.
Zwróć wynik w FORMACIE JSON:
{
  "odpowiedz_tekstowa": "...",
  "kategoria_pdf": "NAZWA_PLIKU_PDF_DOKŁADNIE_JAK_NIŻEJ"
}

Jeśli nie potrafisz dopasować kategorii, ustaw:
"kategoria_pdf": "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

LISTA PLIKÓW PDF:

1. sprzedaz_nieruchomosci_mieszkanie_procedura_koszty_wymagane_dokumenty.pdf
2. zakup_nieruchomosci_mieszkanie_rynek_pierwotny_wytyczne_notarialne.pdf
3. zakup_nieruchomosci_rynek_wtorny_sprawdzenie_stanu_prawnego.pdf
4. darowizna_mieszkania_lub_domu_obowiazki_podatkowe_i_formalne.pdf
5. umowa_darowizny_nieruchomosci_wymagane_dokumenty_i_terminy.pdf
6. zniesienie_wspolwlasnosci_nieruchomosci_krok_po_kroku.pdf
7. podzial_majatku_wspolnego_nieruchomosci_wytyczne_notariusza.pdf
8. sluzebnosc_drogi_koniecznej_wyjasnienie_i_procedura.pdf
9. ustanowienie_hipoteki_na_nieruchomosci_wymogi_i_koszty.pdf
10. umowa_przedwstepna_sprzedazy_nieruchomosci_wzorzec_i_wytyczne.pdf
11. sporządzenie_testamentu_notarialnego_wytyczne_i_koszty.pdf
12. odwolanie_lub_zmiana_testamentu_notarialnego_procedura.pdf
13. stwierdzenie_nabycia_spadku_notarialnie_wymagane_dokumenty.pdf
14. dzial_spadku_umowny_krok_po_kroku_z_notariuszem.pdf
15. zachowek_wyjasnienie_praw_i_obowiazkow_spadkobiercow.pdf
16. odrzucenie_spadku_w_terminie_6_miesiecy_instrukcja.pdf
17. przyjecie_spadku_z_dobrodziejstwem_inwentarza_wytyczne.pdf
18. umowa_o_zrzeczenie_sie_dziedziczenia_zasady_i_skutki.pdf
19. spis_inwentarza_wyjasnienie_procedury_i_kosztow.pdf
20. testament_dla_osoby_niepelnosprawnej_wymogi_formalne.pdf
21. pelnomocnictwo_do_sprzedazy_nieruchomosci_wymogi_i_zabezpieczenia.pdf
22. pelnomocnictwo_do_zakupu_nieruchomosci_wytyczne_notarialne.pdf
23. pelnomocnictwo_ogolne_zakres_uprawnien_i_ryzyka.pdf
24. pelnomocnictwo_szczegolne_do_czynnosci_prawnych_wzor.pdf
25. oswiadczenie_o_podrozy_dziecka_za_granice_wymogi.pdf
26. oswiadczenie_o_podziale_majatku_wspolnego_po_rozwodzie.pdf
27. oswiadczenie_o_ustanowieniu_rozszerzonej_wspolnosci_majatkowej.pdf
28. oswiadczenie_o_ustanowieniu_rozlacznej_wspolnosci_majatkowej.pdf
29. oswiadczenie_o_przyjeciu_lub_odrzuceniu_spadku_wzor.pdf
30. oswiadczenie_o_stanie_rodzinnym_i_majatkowym_wymogi.pdf
31. zakladanie_spolki_z_o_o_wymagane_dokumenty_i_koszty.pdf
32. umowa_spolki_z_o_o_wyjasnienie_kluczowych_postanowien.pdf
33. przeksztalcenie_jdg_w_spolke_z_o_o_procedura_notarialna.pdf
34. sprzedaz_udzialow_w_spolce_z_o_o_wytyczne_i_ryzyka.pdf
35. prokura_ustanowienie_zakres_uprawnien_i_obowiazkow.pdf
36. umowa_spolki_cywilnej_wyjasnienie_i_wymogi_formalne.pdf
37. rejestracja_zmian_w_krs_przez_notariusza_instrukcja.pdf
38. likwidacja_spolki_z_o_o_krok_po_kroku_z_notariuszem.pdf
39. umowa_zbycia_przedsiebiorstwa_wymogi_i_konsekwencje.pdf
40. umowa_ustanowienia_zastawu_rejestrowego_wyjasnienie.pdf
41. intercyza_umowa_majatkowa_malzenska_wyjasnienie_i_koszty.pdf
42. umowa_rozszerzajaca_wspolnosc_majatkowa_wytyczne.pdf
43. umowa_ograniczajaca_wspolnosc_majatkowa_instrukcja.pdf
44. umowa_wylaczajaca_wspolnosc_majatkowa_skutki_prawne.pdf
45. podzial_majatku_po_rozwodzie_z_notariuszem_krok_po_kroku.pdf
46. ustanowienie_rozlacznej_wspolnosci_majatkowej_wzor.pdf
47. umowa_o_podzial_majatku_wspolnego_po_separacji.pdf
48. umowa_o_ustanowienie_sluzebnosci_mieszkania_wyjasnienie.pdf
49. umowa_o_ustanowienie_uzytkowania_wyjasnienie_i_koszty.pdf
50. kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf

Oto treść wiadomości od klienta:
{{USER_TEXT}}
"""


def call_groq_business(user_text: str):
    key = os.getenv("YOUR_GROQ_API_KEY")
    if not key:
        print("[ERROR] Brak klucza GROQ (YOUR_GROQ_API_KEY) dla biznesu")
        return None, None, None

    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not models_env:
        print("[ERROR] Brak listy modeli GROQ (GROQ_MODELS) dla biznesu")
        return None, None, None

    models = [m.strip() for m in models_env.split(",") if m.strip()]
    base_prompt = BIZ_PROMPT
    prompt = build_safe_prompt(user_text, base_prompt)

    for model_id in models:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 700,
                },
                timeout=25,
            )

            if response.status_code != 200:
                print("[ERROR] GROQ business error:", response.status_code, response.text)
                continue

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Oczekujemy JSON-a, ale na wszelki wypadek spróbujemy parsować ostrożnie
            import json
            try:
                parsed = json.loads(content)
                answer = parsed.get("odpowiedz_tekstowa", "").strip()
                pdf_name = parsed.get("kategoria_pdf", "").strip()
            except Exception as e:
                print("[WARN] Nie udało się sparsować JSON z GROQ business:", e)
                answer = content.strip()
                pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

            if not pdf_name:
                pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

            return truncate_reply(answer), pdf_name, f"GROQ_BIZ:{model_id}"

        except Exception as e:
            print("[EXCEPTION] GROQ business:", e)
            continue

    print("[WARN] Żaden model GROQ business nie zwrócił odpowiedzi")
    return None, None, None


# -----------------------------------
# 5. AI – rozpoznawanie emocji
# -----------------------------------
def detect_emotion_ai(user_text: str) -> str | None:
    key = os.getenv("YOUR_GROQ_API_KEY")
    models_env = os.getenv("GROQ_MODELS", "").strip()
    if not key or not models_env:
        print("[ERROR] Brak konfiguracji GROQ do rozpoznawania emocji")
        return None

    model_id = models_env.split(",")[0].strip()

    prompt = (
        "Na podstawie poniższego tekstu określ jedną dominującą emocję z listy:\n"
        "radość, smutek, złość, strach, neutralne, zaskoczenie, nuda, spokój.\n\n"
        "Zwróć tylko jedno słowo z tej listy, bez dodatkowego komentarza.\n\n"
        f"Tekst:\n{user_text}"
    )

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16,
            },
            timeout=15,
        )

        if response.status_code != 200:
            print("[ERROR] GROQ emotion error:", response.status_code, response.text)
            return None

        data = response.json()
        content = data["choices"][0]["message"]["content"].strip().lower()
        emotion = content.split()[0]
        print("[INFO] Wykryta emocja AI:", emotion)
        return emotion

    except Exception as e:
        print("[EXCEPTION] GROQ emotion:", e)
        return None


# -----------------------------------
# 6. Emotki
# -----------------------------------
def map_emotion_to_file(emotion: str | None) -> str:
    if not emotion:
        return "error.png"

    emotion = emotion.strip().lower()

    if emotion in ["radość", "radosc", "pozytywne", "szczęście", "szczescie"]:
        return "twarz_radosc.png"
    if emotion in ["smutek", "przygnębienie", "przygnebienie"]:
        return "twarz_smutek.png"
    if emotion in ["złość", "zlosc", "gniew"]:
        return "twarz_zlosc.png"
    if emotion in ["strach", "lęk", "lek"]:
        return "twarz_lek.png"
    if emotion in ["zaskoczenie", "zdziwienie"]:
        return "twarz_zaskoczenie.png"
    if emotion in ["nuda"]:
        return "twarz_nuda.png"
    if emotion in ["spokój", "spokoj", "neutralne", "neutralny"]:
        return "twarz_spokoj.png"

    return "twarz_spokoj.png"


def load_emoticon_base64(filename: str) -> tuple[str, str]:
    base_path = os.path.join("emotki", filename)

    def _read(path: str) -> str | None:
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[ERROR] Nie udało się wczytać emotki {path}: {e}")
            return None

    b64 = _read(base_path)
    if b64:
        return b64, "image/png"

    error_path = os.path.join("emotki", "error.png")
    b64_err = _read(error_path)
    if b64_err:
        return b64_err, "image/png"

    print("[ERROR] Nie udało się wczytać nawet error.png")
    return "", "image/png"


# -----------------------------------
# 7. PDF
# -----------------------------------
def map_emotion_to_pdf_file(emotion: str | None) -> str:
    png_name = map_emotion_to_file(emotion)
    pdf_name = png_name.rsplit(".", 1)[0] + ".pdf"
    return pdf_name


def load_pdf_base64(filename: str) -> tuple[str, str]:
    base_path = os.path.join("pdf", filename)

    def _read(path: str) -> str | None:
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[ERROR] Nie udało się wczytać PDF {path}: {e}")
            return None

    b64 = _read(base_path)
    if b64:
        return b64, "application/pdf"

    error_path = os.path.join("pdf", "error.pdf")
    b64_err = _read(error_path)
    if b64_err:
        return b64_err, "application/pdf"

    print("[ERROR] Nie udało się wczytać nawet error.pdf")
    return "", "application/pdf"


def load_pdf_biznes_base64(filename: str) -> tuple[str, str]:
    base_path = os.path.join("pdf_biznes", filename)

    def _read(path: str) -> str | None:
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[ERROR] Nie udało się wczytać PDF biznesowego {path}: {e}")
            return None

    b64 = _read(base_path)
    if b64:
        return b64, "application/pdf"

    # fallback
    fallback = os.path.join("pdf_biznes", "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf")
    b64_fallback = _read(fallback)
    if b64_fallback:
        return b64_fallback, "application/pdf"

    print("[ERROR] Nie udało się wczytać nawet fallback biznesowego PDF")
    return "", "application/pdf"

# -----------------------------------
# 8. Webhook
# -----------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    secret_header = request.headers.get("X-Webhook-Secret")
    expected_secret = os.getenv("WEBHOOK_SECRET", "")
    if not expected_secret or secret_header != expected_secret:
        print("[WARN] Nieprawidłowy lub brak X-Webhook-Secret")
        return jsonify({"error": "unauthorized"}), 401

    if request.content_length and request.content_length > 20000:
        print("[WARN] Payload too large:", request.content_length)
        return jsonify({"error": "payload too large"}), 413

    data = request.json or {}

    sender_raw = (data.get("from") or data.get("sender") or "").lower()
    sender = normalize_email(sender_raw)
    subject = data.get("subject", "") or ""
    body = data.get("body", "") or ""
    body_lower = body.lower()

    allowed_sender = sender in ALLOWED_EMAILS
    business_sender = sender in ALLOWED_EMAILS_BIZ
    has_keyword = bool(SLOWO_KLUCZ) and (SLOWO_KLUCZ in body_lower)

    print(f"[DEBUG] Nadawca: {sender}, allowed={allowed_sender}, biz={business_sender}, keyword={has_keyword}")

    # Brak na obu listach i brak słowa kluczowego -> ignorujemy
    if not allowed_sender and not business_sender and not has_keyword:
        print("[INFO] Nadawca nie jest dozwolony LUB nie użył słowa kluczowego:", sender)
        return jsonify({"status": "ignored", "reason": "sender not allowed"}), 200

    if subject.lower().startswith("re:"):
        print("[INFO] Wykryto odpowiedź (RE:), ignoruję:", subject)
        return jsonify({"status": "ignored", "reason": "reply detected"}), 200

    if not body.strip():
        print("[INFO] Pusta treść wiadomości – ignoruję")
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    # -----------------------------------
    # ŚCIEŻKA 1: KLIENCI BIZNESOWI (NOTARIUSZ)
    # -----------------------------------
    if business_sender:
        print("[INFO] Obsługa klienta biznesowego (notariusz):", sender)
        text, pdf_name, text_source = call_groq_business(body)
        if not text:
            print("[ERROR] Brak odpowiedzi z GROQ business – nic nie wysyłam")
            return jsonify({
                "status": "error",
                "reason": "no ai output business",
            }), 200

        # Emotka nadal może być na podstawie emocji (opcjonalnie)
        emotion = detect_emotion_ai(body)
        emoticon_file = map_emotion_to_file(emotion)
        emoticon_b64, emoticon_content_type = load_emoticon_base64(emoticon_file)

        # PDF zawsze potrzebny dla biznesu
        pdf_info = None
        if not pdf_name:
            pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

        pdf_b64, pdf_content_type = load_pdf_base64(pdf_name)
        if pdf_b64:
            pdf_info = {
                "filename": pdf_name,
                "content_type": pdf_content_type,
                "base64": pdf_b64,
            }
            print(f"[PDF-BIZ] PDF załączony: {pdf_name}")
        else:
            print(f"[PDF-BIZ] BŁĄD — nie udało się wczytać PDF: {pdf_name}")

        safe_text_html = text.replace("\n", "<br>")
        emoticon_cid = "emotka1"

        footer_html = f"""
<hr>
<div style="font-size: 11px; color: #0b3d0b; font-family: Georgia, 'Times New Roman', serif; line-height: 1.4;">
────────────────────────────────────────────<br>
Ta wiadomość została wygenerowana automatycznie przez system kancelarii notarialnej.<br>
To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej.<br>
• Google Apps Script – obsługa skrzynki Gmail<br>
• Render.com – backend API<br>
• Groq – modele AI<br>
────────────────────────────────────────────<br>
model tekstu: {text_source}<br>
</div>
"""

        final_reply_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #000000;">
  <p><b>Treść odpowiedzi automatycznej:</b></p>
  <p><i>{safe_text_html}</i></p>
  <p style="margin-top: 16px;">
    <img src="cid:{emoticon_cid}" alt="emotka" style="width:64px;height:64px;">
  </p>
  {footer_html}
</div>
"""

        response_json = {
            "status": "ok",
            "has_text": True,
            "reply": final_reply_html,
            "text_source": text_source,
            "emotion": emotion,
            "emoticon": {
                "filename": emoticon_file,
                "content_type": emoticon_content_type,
                "base64": emoticon_b64,
                "cid": emoticon_cid,
            },
        }

        if pdf_info:
            response_json["pdf"] = pdf_info

        return jsonify(response_json), 200

    # -----------------------------------
    # ŚCIEŻKA 2: ZWYKLI NADAWCY (Twoja dotychczasowa logika)
    # -----------------------------------
    text, text_source = call_groq(body)
    has_text = bool(text)

    if not has_text:
        print("[ERROR] Brak odpowiedzi z GROQ – nic nie wysyłam")
        return jsonify({
            "status": "error",
            "reason": "no ai output",
        }), 200

    emotion = detect_emotion_ai(body)
    emoticon_file = map_emotion_to_file(emotion)
    emoticon_b64, emoticon_content_type = load_emoticon_base64(emoticon_file)

    # NOWA LOGIKA PDF + LOGI (jak ustaliliśmy)
    pdf_needed = False

    if allowed_sender:
        if "pdf" in body_lower:
            print(f"[PDF] Załączam PDF — nadawca {sender} jest na liście i użył słowa 'pdf'")
            pdf_needed = True
        elif has_keyword:
            print(f"[PDF] Załączam PDF — nadawca {sender} jest na liście i użył słowa kluczowego")
            pdf_needed = True
        else:
            print(f"[PDF] NIE załączam PDF — nadawca {sender} jest na liście, ale nie użył 'pdf' ani słowa kluczowego")
    else:
        if has_keyword:
            print(f"[PDF] Załączam PDF — nadawca {sender} NIE jest na liście, ale użył słowa kluczowego")
            pdf_needed = True
        else:
            print(f"[PDF] NIE załączam PDF — nadawca {sender} NIE jest na liście i nie użył słowa kluczowego")

    pdf_info = None
    if pdf_needed:
        pdf_file = map_emotion_to_pdf_file(emotion)
        pdf_b64, pdf_content_type = load_pdf_base64(pdf_file)
        if pdf_b64:
            pdf_info = {
                "filename": pdf_file,
                "content_type": pdf_content_type,
                "base64": pdf_b64,
            }
            print(f"[PDF] PDF załączony: {pdf_file}")
        else:
            print(f"[PDF] BŁĄD — nie udało się wczytać PDF: {pdf_file}")

    safe_text_html = text.replace("\n", "<br>")
    emoticon_cid = "emotka1"

    footer_html = f"""
<hr>
<div style="font-size: 11px; color: #0b3d0b; font-family: Georgia, 'Times New Roman', serif; line-height: 1.4;">
────────────────────────────────────────────<br>
Ta wiadomość została wygenerowana automatycznie przez system Pawła.<br>
• Google Apps Script – obsługa skrzynki Gmail<br>
• Render.com – backend API<br>
• Groq – modele AI<br>
• https://github.com/legionowopawel/AutoResponder_AI_Text.git<br>

────────────────────────────────────────────<br>
model tekstu: {text_source}<br>
</div>
"""

    final_reply_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #000000;">
  <p><b>Treść mojej odpowiedzi:</b><br>
  <b>Na podstawie tego, co otrzymałem, przygotowałem odpowiedź:</b></p>

  <p><i>{safe_text_html}</i></p>

  <p style="margin-top: 16px;">
    <img src="cid:{emoticon_cid}" alt="emotka" style="width:64px;height:64px;">
  </p>

  {footer_html}
</div>
"""

    response_json = {
        "status": "ok",
        "has_text": True,
        "reply": final_reply_html,
        "text_source": text_source,
        "emotion": emotion,
        "emoticon": {
            "filename": emoticon_file,
            "content_type": emoticon_content_type,
            "base64": emoticon_b64,
            "cid": emoticon_cid,
        },
    }

    if pdf_info:
        response_json["pdf"] = pdf_info

    return jsonify(response_json), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
