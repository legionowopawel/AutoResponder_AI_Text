import time
import os
import traceback
from config import CHECK_INTERVAL_SECONDS
from mail_utils import (
    fetch_unseen_allowed,
    extract_body,
    send_reply_with_image,
    send_error_email
)
from ai_text import generate_text_reply
from ai_image import generate_image

LOG_FILE = "pc_super.log"
LAST_TEXT = "last_text.txt"
LAST_IMAGE = "last_image.png"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[INFO] {ts} — {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")

def log_error(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[ERROR] {ts} — {msg}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")

def save_last_text(text):
    try:
        with open(LAST_TEXT, "w", encoding="utf-8") as f:
            f.write(text or "")
    except Exception as e:
        log_error(f"Nie można zapisać last_text: {e}")

def save_last_image(image_path):
    try:
        if image_path and os.path.exists(image_path):
            os.replace(image_path, LAST_IMAGE)
    except Exception as e:
        log_error(f"Nie można zapisać last_image.png: {e}")

def process_single_message(msg):
    try:
        from_addr = msg["From"]
        real_from = msg.get("Reply-To") or from_addr
        real_from = real_from.split("<")[-1].split(">")[0].strip()
        subject = msg.get("Subject", "")
        body = extract_body(msg)

        if not body or not body.strip():
            log(f"Pomijam wiadomość od {real_from} — pusty body")
            return

        # Generowanie odpowiedzi tekstowej (Tyler / zwykly)
        answer = generate_text_reply(body)
        save_last_text(answer)

        # Generowanie obrazu (opcjonalne)
        image_path = None
        try:
            image_path = generate_image(answer)
            if image_path:
                save_last_image(image_path)
        except Exception as e:
            log_error(f"Błąd generowania obrazu: {e}")

        # Finalna treść maila (HTML) - prosty fallback do tekstu
        final_text = (
            "<html><body>"
            f"<p><i>{answer}</i></p>"
            "<p style='color:#0a8a0a; font-size:10px;'>"
            "Odpowiedź wygenerowana automatycznie przez system Script + Render.<br>"
            "Projekt dostępny na GitHub: https://github.com/legionowopawel/AutoResponder_AI_Text.git"
            "</p>"
            "</body></html>"
        )

        # Wysyłamy (jeśli image_path jest None, send_reply_with_image poradzi sobie)
        send_reply_with_image(real_from, subject, final_text, image_path)
        log(f"Wysłano odpowiedź do {real_from}")
    except Exception as e:
        log_error(f"Wyjątek w process_single_message: {e}\n{traceback.format_exc()}")
        # Wyślij powiadomienie o błędzie (nie blokujemy)
        try:
            send_error_email(str(e))
        except Exception as mail_err:
            log_error(f"Nie można wysłać maila z błędem: {mail_err}")

def process_loop():
    """Główna pętla PC_super – działa w usłudze Windows"""
    log("Start pętli process_loop")
    while True:
        try:
            messages = fetch_unseen_allowed()
            if not messages:
                time.sleep(CHECK_INTERVAL_SECONDS)
                continue

            for msg in messages:
                try:
                    process_single_message(msg)
                except Exception as e:
                    log_error(f"Błąd przetwarzania pojedynczej wiadomości: {e}")
                    continue

        except Exception as e:
            log_error(f"Globalny wyjątek w pętli: {e}\n{traceback.format_exc()}")
            try:
                send_error_email(str(e))
            except Exception as mail_err:
                log_error(f"Nie można wysłać maila z błędem: {mail_err}")
            time.sleep(CHECK_INTERVAL_SECONDS)
