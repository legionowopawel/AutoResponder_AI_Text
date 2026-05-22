# Generator Krzyżówek — Dokumentacja

## Przegląd projektu

**Krzyzowka** to podprogram dedykowany do generowania klasycznych krzyżówek na bazie istniejącego silnika Scrabble. Program wykorzystuje zaawansowany algorytm backtrackingu do maksymalizacji zagęszczenia haseł w siatce.

---

## Struktura katalogów

```
Krzyzowka/
├── baza.txt                          # Baza słów (format: WYRAZ definicja)
├── main.py                           # Entry point (GUI + CLI)
├── gui_main.py                       # Interfejs graficzny PySide6
├── crossword_orchestrator.py         # Orkiestracja procesu
├── crossword_generator.py            # Generator z algorytmem backtrackingu
├── crossword_grid.py                 # Struktura danych siatki
├── word_source.py                    # Obsługa bazy słów
├── image_renderer.py                 # Renderowanie PNG
├── excel_exporter.py                 # Export do Excel (.xlsx)
├── html_exporter.py                  # Export do HTML5
├── requirements_krzyzowka.txt        # Zależności Python
├── README.md                         # Ten plik
├── WYNIKI_*/                         # Katalogi wyników (auto-generowane)
└── __pycache__/                      # Cache Python
```

---

## Instalacja zależności

```bash
# Zainstaluj wymagane pakiety
pip install -r requirements_krzyzowka.txt

# Wymagane pakiety:
# - PySide6 (GUI)
# - openpyxl (Excel export)
# - Pillow (PNG rendering)
```

---

## Użycie

### 1. **Tryb Graficzny (GUI)**

Uruchomić interfejs graficzny:

```bash
python main.py
```

Lub:

```bash
python gui_main.py
```

**Funkcjonalności:**
- Ustawienie wymiarów siatki (domyślnie 15×15)
- Wybór pliku ze słowami (domyślnie `dane.txt` w katalogu projektu)
- Ustawienie liczby wariantów (1-10, domyślnie 3)
- Wizualizacja postępu generowania

### 2. **Tryb Wiersza Poleceń (CLI)**

Generowanie bez GUI:

```bash
# Domyślnie: dane.txt, 3 warianty
python main.py --cli 15 15

# Z niestandardowym plikiem słów
python main.py --cli 12 12 /path/to/words.txt
```

**Parametry:**
- `width` (liczba): Szerokość siatki (5-30)
- `height` (liczba): Wysokość siatki (5-30)
- `word_file` (opcjonalny): Ścieżka do pliku słów

---

## Format pliku z wyrazami

Plik powinien zawierać jedno słowo na linię w formacie:

```
WYRAZ DEFINICJA_LUB_PODPOWIEDŹ
```

**Przykład (baza.txt):**

```
PRACA Zarobkowe zajęcie, cel uczestników CIS
ZAWÓD Wyuczona profesja, np. kucharz lub ogrodnik
ETAT Stałe zatrudnienie w pełnym wymiarze godzin
NAUKA Zdobywanie nowej wiedzy i umiejętności
```

**Reguły:**
- Wyraz musi zawierać tylko litery (obsługiwane: polskie znaki diakrytyczne)
- Definicja rozdzielona spacją od wyrazu
- Puste linie i komentarze (`#`) są ignorowane
- Wspierana jest długość wyrazów od 2 do 15 znaków

---

## Struktura katalogów wyników

Po wygenerowaniu krzyżówki zostaje utworzony katalog:

```
WYNIKI_20260522_114339_baza/
├── krizowka.xlsx              # Arkusz Excel z siatką + pytaniami
├── krizowka.html              # Interaktywna strona HTML
├── 001_completed.png          # Wariant 1: Grafika UZUPEŁNIONA (z literami)
├── 001_blank.png              # Wariant 1: Grafika PUSTA (do wypełniania)
├── 001.txt                    # Wariant 1: Lista pytań
├── 002_completed.png          # Wariant 2: Grafika UZUPEŁNIONA
├── 002_blank.png              # Wariant 2: Grafika PUSTA
├── 002.txt                    # Wariant 2: Lista pytań
├── 003_completed.png          # Wariant 3: Grafika UZUPEŁNIONA
├── 003_blank.png              # Wariant 3: Grafika PUSTA
└── 003.txt                    # Wariant 3: Lista pytań
```

**Opis plików:**

| Plik | Format | Zawartość |
|------|--------|-----------|
| `krizowka.xlsx` | Excel | Siatka krzyżówki + pytania (idealnie sformatowane komórki) |
| `krizowka.html` | HTML5 | Krzyżówka interaktywna + pytania (do wydruku/przeglądu) |
| `NNN_completed.png` | PNG | Grafika krzyżówki UZUPEŁNIONA — wszystkie litery widoczne (1 wariant) — **dla wszystkich 3 wariantów** |
| `NNN_blank.png` | PNG | Grafika krzyżówki PUSTA — bez liter, do wypełniania ołówkiem (1 wariant) — **dla wszystkich 3 wariantów** |
| `NNN.txt` | TXT | Tekst pytań do wariantu NNN |

---

## Algorytm generowania

### Strategia

Program dąży do **maksymalnego zagęszczenia haseł** w siatce przy użyciu:

1. **Słowo startowe (seed):** Losowe słowo (5-8 liter) umieszczane w centrum
2. **Backtracking:** Rekurencyjna eksploracja możliwych położeń słów
3. **Priorytetyzacja:**
   - Preferuj słowa z więcej przecinającymi się literami
   - Preferuj słowa dłuższe (5+ liter)
   - Filtruję słowa bez przecinań (aby uniknąć wysepek)
4. **Wybór najlepszego:** Z wielu prób wybierana siatka o najwyższej gęstości

### Parametry

- **max_attempts:** Liczba prób (domyślnie 50)
- **max_depth:** Maks. głębokość backtrackingu (domyślnie 20)
- **Próbkowanie słów:** Dla każdej pozycji testowane są top 3 słowa

### Wydajność

- Rozmiar 10×10: ~5-10 sekund
- Rozmiar 12×12: ~15-20 sekund
- Rozmiar 15×15: ~30-50 sekund (3 warianty = 1-2 min)

**Wynik:** 
- 6 plików PNG na 3 warianty (2 wersje na wariant: completed + blank)
- 1 plik Excel (krizowka.xlsx)
- 1 plik HTML (krizowka.html)
- 3 pliki TXT (pytania)

---

## Formatowanie Excel

Komórki siatki krzyżówki są sformatowane zgodnie ze specyfikacją:

- **Forma:** Idealne kwadraty (rozmiar dostosowany)
- **Ramka:** Gruba czarna linia dla komórek z literami
- **Tło:** Białe dla wszystkich komórek
- **Pytania:** Lista pod siatką, podzielona na poziome i pionowe

---

## Eksport HTML

Strona HTML zawiera:

- **Layout responsywny:** Grid CSS do wyświetlania siatki
- **Interaktywny:** Siatka do zaznaczania odp. (CSS klasy `cell`, `cell.black`)
- **Pytania:** Dwie kolumny (poziomo, pionowo)
- **Styl:** Gotowy do druku (Print-friendly)

---

## Logika numeracji pytań

- Każde słowo otrzymuje **unikalny numer pytania**
- Numer przypisywany jest **pierwszej komórce** słowa
- Jeśli słowa przecinają się, dzielą ten sam numer (dla tego kierunku)
- Numeracja jest **sekwencyjna** od lewej do prawej, góry do dołu

---

## Przykład użycia CLI

```bash
# Wygeneruj 15x15 krzyżówkę (3 warianty)
python main.py --cli 15 15

# Katalog wyników: WYNIKI_20260522_114339_baza/
```

**Wyjście:**

```
[WordSource] Załadowano 100 słów z baza.txt
[Orchestrator] Źródło słów: OK (100 słów)
[Orchestrator] Katalog wyjściowy: ...WYNIKI_20260522_114339_baza
[Orchestrator] Generuję 3 wariantów krzyżówki (15x15)...
[Orchestrator] Wygenerowano warianty:
  1. Gęstość: 78.5%, Słów: 45
  2. Gęstość: 75.3%, Słów: 42
  3. Gęstość: 72.1%, Słów: 40
  Exportuję wariant 1: PNG...
  Exportuję wariant 1: TXT...
  Exportuję wariant 1: XLSX...
  Exportuję wariant 1: HTML...
  [... warianty 2 i 3 ...]
✓ Krzyżówka wygenerowana pomyślnie!
Wyniki w: ...WYNIKI_20260522_114339_baza
```

---

## Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'PySide6'`

**Rozwiązanie:**

```bash
pip install PySide6
```

### Problem: `UnicodeEncodeError` na Windowsie

**Rozwiązanie:** Program automatycznie obsługuje kodowanie UTF-8. Jeśli problem trwa, uruchom:

```bash
$env:PYTHONIOENCODING = 'utf-8'
python main.py --cli 15 15
```

### Problem: Krzyżówka ma zbyt niską gęstość

**Rozwiązanie:** 
- Zwiększ `max_attempts` w `crossword_generator.py`
- Rozszerz bazę słów (więcej słów = więcej możliwości przecinań)
- Spróbuj mniejszych rozmiarów siatki (10×10 zamiast 15×15)

### Problem: Generator zbyt wolny (15×15)

**Rozwiązanie:**
- Zmniejsz `max_attempts` (np. z 50 na 20)
- Zmniejsz `max_depth` w backtrackingu (np. z 20 na 10)
- Użyj mniejszego rozmiaru siatki

---

## Integracja ze Scrabble

Program **nie zmienia** istniejącego silnika Scrabble. Zamiast tego:

- **Reużywa ideę:** Logika dopasowywania słów (backtracking)
- **Niezależny:** Całkowicie oddzielny katalog i moduły (`Krzyzowka/`)
- **Kompatybilna baza:** Format `baza.txt` jest kompatybilny z wejściami scrabble

---

## Rozszerzenia (Future)

Możliwe ulepszenia:

- [ ] Symetryczna krzyżówka (rotacja 180°)
- [ ] Ukryte słowa (niebieskie litery = niezależne hint)
- [ ] Export do PDF
- [ ] Silnik anagramów (znajdowanie lepszych dopasowań)
- [ ] Wielojęzyczność (angielskie krzyżówki itp.)

---

## Licencja

Projekt jest częścią silnika Scrabble. Patrz główny katalog projektów.

---

## Autor i kontakt

Wygenerowano automatycznie dla projektu **Scrabble ze słownikiem 4.0**.

For issues, see the main project documentation.
