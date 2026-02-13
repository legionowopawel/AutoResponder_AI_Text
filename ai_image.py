import os
import requests
import time
from config import HF_IMAGE_API_KEY

IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-2")
DEFAULT_OUT = "pc_super_image.png"
RETRIES = 2
TIMEOUT = 30

def build_image_prompt_from_text(answer_text: str) -> str:
    base = "Minimalistyczny schemat blokowy ilustrujący główne idee odpowiedzi: "
    core = (answer_text or "")[:400].replace("\n", " ")
    return base + core + ", clean diagram, white background, vector style"

def generate_image(answer_text: str, out_path: str = DEFAULT_OUT) -> str:
    """
    Wysyła zapytanie do HuggingFace Inference API i zapisuje obraz.
    Zwraca ścieżkę do pliku lub None w przypadku błędu.
    Ma retry i fallback.
    """
    if not HF_IMAGE_API_KEY:
        # brak klucza — nie próbujemy
        return None

    prompt = build_image_prompt_from_text(answer_text)
    url = f"https://api-inference.huggingface.co/models/{IMAGE_MODEL}"
    headers = {"Authorization": f"Bearer {HF_IMAGE_API_KEY}"}
    payload = {"inputs": prompt}

    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            if resp.status_code == 200:
                # zapisujemy surową zawartość (może być obraz)
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                return out_path
            else:
                # log i retry
                print(f"HuggingFace status {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as e:
            print("Błąd połączenia HF:", e)
        time.sleep(1 + attempt)
    return None
