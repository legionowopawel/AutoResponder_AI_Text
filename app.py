import os
import base64
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False

# -----------------------------------
# 1. Normalizacja Gmaili (wyciąganie adresu z "Imię Nazwisko <email>")
# -----------------------------------
def normalize_email(email: str) -> str:
    email = (email or "").lower().strip()

    # Jeśli format: "Imię Nazwisko <email@domena>"
    if "<" in email and ">" in email:
        start = email.find("<") + 1
        end = email.find(">")
        email = email[start:end].strip()

    # Normalizacja Gmaila (usuń kropki i aliasy)
    if email.endswith("@gmail.com"):
        try:
            local, domain = email.split("@", 1)
            local = local.replace(".", "")
            local = local.split("+", 1)[0]
            return f"{local}@{domain}"
        except Exception:
            return email

    return email


# -----------------------------------
# 2. Wczytywanie list emaili z ENV (dwie listy)
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
# 3. Limity długości i prompt loader
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
            print(f"[INFO] Wczytano {filename} (długość: {len(txt)})")
            return txt
    except FileNotFoundError:
        print(f"[ERROR] Brak pliku {filename}")
        return "Brak pliku prompt.txt\n\n{{USER_TEXT}}"


def summarize_and_truncate(text: str, max_chars: int = MAX_USER_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    summary = text[:max_chars]
    return "Streszczenie długiej wiadomości użytkownika (skrócone do bezpiecznej długości):\n\n" + summary


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
# 4. Funkcje AI – GROQ (tekst ogólny)
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
# 4b. Funkcje AI – GROQ (biznesowy prompt, oczekuje JSON)
# -----------------------------------
BIZ_PROMPT = """
Jesteś systemem automatycznej odpowiedzi dla kancelarii notarialnej.
Twoim zadaniem jest:

1. ZAWSZE potraktować wiadomość klienta jako pytanie, nawet jeśli:
   • jest bardzo krótka,
   • jest niejasna,
   • jest jednym słem (np. "drzewo"),
   • jest tylko stwierdzeniem.
Traktuj każde słowo, nawet pojedyncze, jako pełnoprawne pytanie lub temat.
Nigdy nie proś o doprecyzowanie.
Nigdy nie proś o przesłanie pytania.
Zawsze udziel odpowiedzi na podstawie tego, co otrzymałeś.

2. Odpowiedzieć w sposób:
   • uprzejmy,
   • profesjonalny,
   • informacyjny,
   • neutralny,
   • bez udzielania porad prawnych,
   • bez interpretacji przepisów,
   • bez formułowania opinii notarialnych.

3. Każdą odpowiedź zakończ obowiązkową klauzulą:
   "To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej."

4. Na podstawie treści wiadomości dokonaj klasyfikacji tematu do jednej z poniższych kategorii PDF.
Zwróć wynik w FORMACIE JSON (dokładnie taki obiekt JSON, bez dodatkowego tekstu):
{
  "odpowiedz_tekstowa": "tekst odpowiedzi dla klienta",
  "kategoria_pdf": "NAZWA_PLIKU_PDF_DOKŁADNIE_JAK_NIŻEJ"
}

Jeśli nie potrafisz dopasować kategorii, ustaw:
"kategoria_pdf": "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"

LISTA PLIKÓW PDF:
sprzedaz_nieruchomosci_mieszkanie_procedura_koszty_wymagane_dokumenty.pdf
zakup_nieruchomosci_mieszkanie_rynek_pierwotny_wytyczne_notarialne.pdf
zakup_nieruchomosci_rynek_wtorny_sprawdzenie_stanu_prawnego.pdf
darowizna_mieszkania_lub_domu_obowiazki_podatkowe_i_formalne.pdf
umowa_darowizny_nieruchomosci_wymagane_dokumenty_i_terminy.pdf
zniesienie_wspolwlasnosci_nieruchomosci_krok_po_kroku.pdf
podzial_majatku_wspolnego_nieruchomosci_wytyczne_notariusza.pdf
sluzebnosc_drogi_koniecznej_wyjasnienie_i_procedura.pdf
ustanowienie_hipoteki_na_nieruchomosci_wymogi_i_koszty.pdf
umowa_przedwstepna_sprzedazy_nieruchomosci_wzorzec_i_wytyczne.pdf
sporządzenie_testamentu_notarialnego_wytyczne_i_koszty.pdf
odwolanie_lub_zmiana_testamentu_notarialnego_procedura.pdf
stwierdzenie_nabycia_spadku_notarialnie_wymagane_dokumenty.pdf
dzial_spadku_umowny_krok_po_kroku_z_notariuszem.pdf
zachowek_wyjasnienie_praw_i_obowiazkow_spadkobiercow.pdf
odrzucenie_spadku_w_terminie_6_miesiecy_instrukcja.pdf
przyjecie_spadku_z_dobrodziejstwem_inwentarza_wytyczne.pdf
umowa_o_zrzeczenie_sie_dziedziczenia_zasady_i_skutki.pdf
spis_inwentarza_wyjasnienie_procedury_i_kosztow.pdf
testament_dla_osoby_niepelnosprawnej_wymogi_formalne.pdf
pelnomocnictwo_do_sprzedazy_nieruchomosci_wymogi_i_zabezpieczenia.pdf
pelnomocnictwo_do_zakupu_nieruchomosci_wytyczne_notarialne.pdf
pelnomocnictwo_ogolne_zakres_uprawnien_i_ryzyka.pdf
pelnomocnictwo_szczegolne_do_czynnosci_prawnych_wzor.pdf
oswiadczenie_o_podrozy_dziecka_za_granice_wymogi.pdf
oswiadczenie_o_podziale_majatku_wspolnego_po_rozwodzie.pdf
oswiadczenie_o_ustanowieniu_rozszerzonej_wspolnosci_majatkowej.pdf
oswiadczenie_o_ustanowieniu_rozlacznej_wspolnosci_majatkowej.pdf
oswiadczenie_o_przyjeciu_lub_odrzuceniu_spadku_wzor.pdf
oswiadczenie_o_stanie_rodzinnym_i_majatkowym_wymogi.pdf
zakladanie_spolki_z_o_o_wymagane_dokumenty_i_koszty.pdf
umowa_spolki_z_o_o_wyjasnienie_kluczowych_postanowien.pdf
przeksztalcenie_jdg_w_spolke_z_o_o_procedura_notarialna.pdf
sprzedaz_udzialow_w_spolce_z_o_o_wytyczne_i_ryzyka.pdf
prokura_ustanowienie_zakres_uprawnien_i_obowiazkow.pdf
umowa_spolki_cywilnej_wyjasnienie_i_wymogi_formalne.pdf
rejestracja_zmian_w_krs_przez_notariusza_instrukcja.pdf
likwidacja_spolki_z_o_o_krok_po_kroku_z_notariuszem.pdf
umowa_zbycia_przedsiebiorstwa_wymogi_i_konsekwencje.pdf
umowa_ustanowienia_zastawu_rejestrowego_wyjasnienie.pdf
intercyza_umowa_majatkowa_malzenska_wyjasnienie_i_koszty.pdf
umowa_rozszerzajaca_wspolnosc_majatkowa_wytyczne.pdf
umowa_ograniczajaca_wspolnosc_majatkowa_instrukcja.pdf
umowa_wylaczajaca_wspolnosc_majatkowa_skutki_prawne.pdf
podzial_majatku_po_rozwodzie_z_notariuszem_krok_po_kroku.pdf
ustanowienie_rozlacznej_wspolnosci_majatkowej_wzor.pdf
umowa_o_podzial_majatku_wspolnego_po_separacji.pdf
umowa_o_ustanowienie_sluzebnosci_mieszkania_wyjasnienie.pdf
umowa_o_ustanowienie_uzytkowania_wyjasnienie_i_koszty.pdf
kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf
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

            # Oczekujemy czystego JSON-a; spróbuj sparsować
            try:
                parsed = json.loads(content)
                answer = parsed.get("odpowiedz_tekstowa", "").strip()
                pdf_name = parsed.get("kategoria_pdf", "").strip()
            except Exception as e:
                print("[WARN] Nie udało się sparsować JSON z GROQ business:", e)
                # fallback: traktuj cały content jako odpowiedź i ustaw fallback pdf
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
# 7. PDF (zwykłe i biznesowe)
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

    # fallback do kontaktu w katalogu pdf_biznes
    fallback = os.path.join("pdf_biznes", "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf")
    b64_fallback = _read(fallback)
    if b64_fallback:
        return b64_fallback, "application/pdf"

    print("[ERROR] Nie udało się wczytać nawet fallback biznesowego PDF")
    return "", "application/pdf"


# -----------------------------------
# 8. Webhook - główna logika
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

    sender_raw = (data.get("from") or data.get("sender") or "").strip()
    sender = normalize_email(sender_raw)
    subject = data.get("subject", "") or ""
    body = data.get("body", "") or ""
    body_lower = body.lower()

    allowed_sender = sender in ALLOWED_EMAILS
    business_sender = sender in ALLOWED_EMAILS_BIZ
    has_keyword = bool(SLOWO_KLUCZ) and (SLOWO_KLUCZ in body_lower)

    print(f"[DEBUG] Nadawca: {sender_raw}, normalized={sender}, allowed={allowed_sender}, biz={business_sender}, keyword={has_keyword}")

    # Ignoruj odpowiedzi (RE:)
    if subject.lower().startswith("re:"):
        print("[INFO] Wykryto odpowiedź (RE:), ignoruję:", subject)
        return jsonify({"status": "ignored", "reason": "reply detected"}), 200

    if not body.strip():
        print("[INFO] Pusta treść wiadomości – ignoruję")
        return jsonify({"status": "ignored", "reason": "empty body"}), 200

    # Decyzja: kto ma otrzymać odpowiedź
    # Zasada: jeśli nadawca jest na ALLOWED_EMAILS -> zwykła odpowiedź
    #         jeśli nadawca jest na ALLOWED_EMAILS_BIZ -> odpowiedź biznesowa
    #         jeśli nadawca użył SLOWO_KLUCZ -> otrzymuje obie odpowiedzi (biznesową + zwykłą)
    #         jeśli nadawca jest na obu listach -> otrzymuje obie odpowiedzi
    send_zwykla = allowed_sender
    send_biznes = business_sender

    # Jeśli użyto słowa kluczowego, wymuszamy obie odpowiedzi
    if has_keyword:
        send_zwykla = True
        send_biznes = True

    # Jeśli nadawca nie jest na żadnej liście i nie użył słowa kluczowego -> ignoruj
    if not send_zwykla and not send_biznes:
        print("[INFO] Nadawca nie jest dozwolony lub nie użył słowa kluczowego:", sender)
        return jsonify({"status": "ignored", "reason": "sender not allowed"}), 200

    # Przygotujemy strukturę odpowiedzi, która może zawierać dwie części
    result = {
        "status": "ok",
        "zwykly": None,
        "biznes": None
    }

    # -------------------------
    # Generuj odpowiedź biznesową (jeśli dotyczy)
    # -------------------------
    if send_biznes:
        print("[INFO] Generuję odpowiedź biznesową dla:", sender)
        biz_text, biz_pdf_name, biz_text_source = call_groq_business(body)
        if not biz_text:
            print("[ERROR] Brak odpowiedzi z GROQ business")
            # fallback: prosty komunikat i fallback pdf
            biz_text = "Czekam na pytanie."
            biz_pdf_name = "kontakt_godziny_pracy_notariusza_podstawowe_informacje.pdf"
            biz_text_source = "GROQ_BIZ:fallback"

        # Emocja i emotka (opcjonalnie)
        emotion = detect_emotion_ai(body)
        emoticon_file = map_emotion_to_file(emotion)
        emoticon_b64, emoticon_content_type = load_emoticon_base64(emoticon_file)

        # Wczytaj PDF biznesowy z katalogu pdf_biznes
        pdf_b64, pdf_content_type = load_pdf_biznes_base64(biz_pdf_name)
        pdf_info = None
        if pdf_b64:
            pdf_info = {
                "filename": biz_pdf_name,
                "content_type": pdf_content_type,
                "base64": pdf_b64,
            }
            print(f"[PDF-BIZ] PDF załączony: {biz_pdf_name}")
        else:
            print(f"[PDF-BIZ] BŁĄD — nie udało się wczytać PDF: {biz_pdf_name}")

        # HTML odpowiedzi biznesowej (do wysłania przez Apps Script)
        safe_text_html = biz_text.replace("\n", "<br>")
        emoticon_cid = "emotka_biz"

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
model tekstu: {biz_text_source}<br>
</div>
"""

        final_reply_html = f"""
<div style="font-family: Arial, sans-serif; font-size: 14px; color: #000000;">
  <p><b>Treść odpowiedzi automatycznej (notarialna):</b></p>
  <p><i>{safe_text_html}</i></p>
  <p style="margin-top: 16px;">
    <img src="cid:{emoticon_cid}" alt="emotka" style="width:64px;height:64px;">
  </p>
  {footer_html}
</div>
"""

        result["biznes"] = {
            "reply_html": final_reply_html,
            "text": biz_text,
            "text_source": biz_text_source,
            "emotion": emotion,
            "emoticon": {
                "filename": emoticon_file,
                "content_type": emoticon_content_type,
                "base64": emoticon_b64,
                "cid": emoticon_cid,
            },
            "pdf": pdf_info,
        }

    # -------------------------
    # Generuj odpowiedź zwykłą (jeśli dotyczy)
    # -------------------------
    if send_zwykla:
        print("[INFO] Generuję odpowiedź zwykłą dla:", sender)
        zwykly_text, zwykly_text_source = call_groq(body)
        if not zwykly_text:
            print("[ERROR] Brak odpowiedzi z GROQ (zwykły)")
            zwykly_text = "Przepraszamy, wystąpił problem z wygenerowaniem odpowiedzi."
            zwykly_text_source = "GROQ:fallback"

        emotion = detect_emotion_ai(body)
        emoticon_file = map_emotion_to_file(emotion)
        emoticon_b64, emoticon_content_type = load_emoticon_base64(emoticon_file)

        # Logika dołączania PDF zwykłego: tylko jeśli nadawca jest na liście ALLOWED_EMAILS i użył 'pdf' w treści lub użyto słowa kluczowego
        pdf_info = None
        pdf_needed = False
        if allowed_sender:
            if "pdf" in body_lower:
                pdf_needed = True
            elif has_keyword:
                pdf_needed = True

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

        safe_text_html = zwykly_text.replace("\n", "<br>")
        emoticon_cid = "emotka_zwykly"

        footer_html = f"""
<hr>
<div style="font-size: 11px; color: #0b3d0b; font-family: Georgia, 'Times New Roman', serif; line-height: 1.4;">
────────────────────────────────────────────<br>
Ta wiadomość została wygenerowana automatycznie przez system Pawła.<br>
To odpowiedź automatyczna, nie stanowi porady prawnej ani opinii notarialnej.<br>
• Google Apps Script – obsługa skrzynki Gmail<br>
• Render.com – backend API<br>
• Groq – modele AI<br>
────────────────────────────────────────────<br>
model tekstu: {zwykly_text_source}<br>
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

        result["zwykly"] = {
            "reply_html": final_reply_html,
            "text": zwykly_text,
            "text_source": zwykly_text_source,
            "emotion": emotion,
            "emoticon": {
                "filename": emoticon_file,
                "content_type": emoticon_content_type,
                "base64": emoticon_b64,
                "cid": emoticon_cid,
            },
            "pdf": pdf_info,
        }

    return jsonify(result), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
