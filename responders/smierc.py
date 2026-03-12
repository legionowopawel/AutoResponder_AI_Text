import os
import csv
import base64
import random
from flask import current_app

# --- KONFIGURACJA ---
DEFAULT_SYSTEM_PROMPT = "Jesteś Pawłem, piszesz z zaświatów. Ton absurdalny, krótko."
ETAPY_CSV_PATH = os.path.join("prompts", "etapy.csv")
STYLE_CSV_PATH = os.path.join("prompts", "style.csv")

def _load_config_csv():
    """Wczytuje etapy i style z plików CSV, które masz w folderze prompts."""
    etapy_data = {}
    style_data = {}

    # Wczytywanie etapy.csv
    if os.path.exists(ETAPY_CSV_PATH):
        try:
            with open(ETAPY_CSV_PATH, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        e_id = int(row['etap'])
                        etapy_data[e_id] = row
                    except: continue
        except Exception as e:
            current_app.logger.error(f"[smierc] Błąd czytania etapy.csv: {e}")

    # Wczytywanie style.csv
    if os.path.exists(STYLE_CSV_PATH):
        try:
            with open(STYLE_CSV_PATH, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        e_id = int(row['etap'])
                        style_data[e_id] = row
                    except: continue
        except Exception as e:
            current_app.logger.error(f"[smierc] Błąd czytania style.csv: {e}")
    
    return etapy_data, style_data

def build_smierc_section(sender_email, data=None, **kwargs):
    """
    Główna funkcja budująca sekcję SMIERC.
    
    sender_email: (str) Adres email nadawcy (pierwszy argument z app.py)
    data: (dict) Słownik z polami: etap, data_smierci, historia (przekazany jako data=data)
    **kwargs: Przechwytuje pozostałe argumenty (np. body), zapobiegając błędowi TypeError
    """
    if data is None:
        data = {}

    # Pobieranie danych z przesłanego słownika
    etap = int(data.get('etap', 1))
    data_smierci_str = data.get('data_smierci', "nieznanego dnia")
    historia = data.get('historia', "")

    # 1. Ładowanie konfiguracji z Twoich plików CSV (etapy.csv i style.csv)
    etapy_dict, style_dict = _load_config_csv()

    # 2. Pobieranie danych dla konkretnego etapu
    row = etapy_dict.get(etap, {})
    s_row = style_dict.get(etap, {})

    if not row:
        # Tryb awaryjny (jeśli etapu nie ma w pliku CSV)
        opis = "Błądzenie w antymaterii"
        obraz_lista = ""
        video_lista = ""
        obrazki_ai = 1
        system_prompt_template = DEFAULT_SYSTEM_PROMPT
    else:
        opis = row.get('opis', "")
        obraz_lista = row.get('obraz', "")
        video_lista = row.get('video', "")
        
        # Solidne sprawdzanie liczby obrazków AI (rozwiązuje problem braku obrazka na etapie 30)
        val_ai = str(row.get('obrazki_ai', '0')).strip()
        try:
            # Sprawdzamy czy to liczba i czy jest większa od 0
            obrazki_ai = int(val_ai) if val_ai.isdigit() else 0
        except:
            obrazki_ai = 0
            
        system_prompt_template = row.get('system_prompt') or DEFAULT_SYSTEM_PROMPT

    # 3. Personalizacja system promptu (podstawienie daty śmierci)
    system_prompt = system_prompt_template.replace("{data_smierci_str}", data_smierci_str)
    
    # 4. Pobranie stylu wizualnego dla FLUX
    styl_flux_raw = s_row.get('styl', "")
    styl_flux = _load_style_content(styl_flux_raw)

    # 5. Generowanie odpowiedzi tekstowej (AI)
    # Upewnij się, że funkcja _get_ai_reply jest dostępna w Twoim kodzie
    wynik = _get_ai_reply(system_prompt, historia)

    # 6. Przygotowanie załączników (Obrazy statyczne z dysku)
    images_static = _load_images_base64(obraz_lista)
    
    # 7. Generowanie obrazów AI (FLUX)
    images_ai = []
    if obrazki_ai > 0:
        current_app.logger.info(f"[smierc] Generowanie {obrazki_ai} obrazów AI dla etapu {etap}")
        # Upewnij się, że funkcja _generate_n_flux_images jest dostępna w Twoim kodzie
        images_ai, _ = _generate_n_flux_images(obrazki_ai, wynik or opis, styl_flux, etap)

    # 8. Przygotowanie wideo
    videos = _load_videos_base64(video_lista)

    # Logowanie dla debugowania
    current_app.logger.info(f"[smierc] Etap {etap}: Wysyłam {len(images_static + images_ai)} obrazów i {len(videos)} wideo.")

    return {
        "reply_html": wynik,
        "nowy_etap": etap + 1,
        "images": images_static + images_ai,
        "videos": videos
    }
# --- KONIEC GŁÓWNEJ LOGIKI ---
# Upewnij się, że poniżej w pliku smierc.py masz swoje funkcje:
# _get_ai_reply, _generate_n_flux_images, _load_style_content, _load_images_base64 itd.