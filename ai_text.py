import os
import requests
import time
from config import GROQ_API_KEY, PROMPT_FILE

MAX_USER_CHARS = 2000
MAX_PROMPT_CHARS = 3000
MAX_MODEL_INPUT_CHARS = 5000
MAX_MODEL_REPLY_CHARS = 2000
RETRIES = 2
TIMEOUT = 20

def load_prompt():
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            txt = f.read()
        return txt[:MAX_PROMPT_CHARS]
    except Exception as e:
        print("Nie można wczytać PROMPT_FILE:", e)
        return ""

def build_prompt(user_text: str) -> str:
    user_text = (user_text or "").strip()
    if len(user_text) > MAX_USER_CHARS:
        user_text = user_text[:MAX_USER_CHARS]
    base = load_prompt()
    prompt = base.replace("{{USER_TEXT}}", user_text)
    return prompt[:MAX_MODEL_INPUT_CHARS]

def truncate_reply(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_MODEL_REPLY_CHARS:
        return text
    return text[:MAX_MODEL_REPLY_CHARS]

def generate_text_reply(user_text: str) -> str:
    """
    Wywołanie Groq z retry i fallbackem.
    Zwraca tekst lub komunikat o błędzie.
    """
    if not GROQ_API_KEY:
        return "Brak klucza API (GROQ)."

    prompt = build_prompt(user_text)
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": os.getenv("MODEL_TYLER", "llama-3.3-70b-versatile"),
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,
        "temperature": 0.7
    }

    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return truncate_reply(content)
            else:
                print(f"GROQ status {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            print("Błąd połączenia Groq:", e)
        time.sleep(1 + attempt)
    return "Przepraszam, wystąpił problem z generowaniem odpowiedzi (API niedostępne)."
