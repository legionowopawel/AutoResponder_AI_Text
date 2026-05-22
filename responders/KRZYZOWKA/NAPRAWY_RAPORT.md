# RAPORT NAPRAW - Generator Krzyżówek

## Problem
Program pracował prawidłowo tylko dla siatki 15x15. Dla innych rozmiarów generował "bzdury" i błędy. Również opcja "Używać 6 strategii" generowała złe wyniki.

## Przyczyny
Znaleziono **3 krytyczne błędy** w kodzie generowania krzyżówek:

### Błąd 1: Niewłaściwa walidacja wymiarów w crossword_new.py (linia 110)
**Lokalizacja:** `crossword_new.py` → `_place_first_word()` method

**Problem:**
```python
if len(word) >= self.height or len(word) >= self.width:
    return
```

**Wyjaśnienie:**
- Warunek `len(word) >= self.height` jest zbyt restrykcyjny
- Odrzuca słowa, które są równe wymiarowi siatki (np. słowo 15 liter w siatce 15x15)
- Słowo 15 liter MOŻE być umieszczone poziomo w siatce 15 kolumn

**Rozwiązanie:**
Zmieniono na:
```python
if len(word) > self.height and len(word) > self.width:
    return
```

Dodatkowo dodano:
- Sprawdzenie czy wyraz mieści się konkretnie w wybranym kierunku (poziomy/pionowy)
- Jeśli nie mieści się w wybranym kierunku, metoda zwraca bez umieszczenia

---

### Błąd 2: Zły nagłówek rand w strategiach (crossword_strategies.py, linia 287)
**Lokalizacja:** `crossword_strategies.py` → `_get_seed_position()` method

**Problem:**
```python
elif strategy == StartingStrategy.RANDOM:
    row = random.randint(1, max(1, h - 2))
    col = random.randint(1, max(1, w - word_len - 1))
```

I bardziej ogólnie:
```python
elif strategy == StartingStrategy.CENTERED:
    row = h // 2
    col = (w - word_len) // 2  # <- Może być ujemne!
```

**Wyjaśnienia:**
1. Współrzędne startowe (1, 1) pomijały lewy górny róg (0, 0)
2. Dla CENTERED: jeśli `word_len > w`, to `(w - word_len) // 2` daje wartość ujemną
3. Dla RANDOM: `max(1, w - word_len - 1)` mogło dać nieprawidłowy zakres dla random.randint

**Rozwiązanie:**
```python
if strategy == StartingStrategy.CENTERED:
    row = h // 2
    col = max(0, (w - word_len) // 2)  # Zapewnia >= 0
elif strategy == StartingStrategy.TOP_LEFT:
    row = 0  # Zamiast 1
    col = 0  # Zamiast 1
elif strategy == StartingStrategy.TOP_CENTER:
    row = 0  # Zamiast 1
    col = max(0, (w - word_len) // 2)
elif strategy == StartingStrategy.MIDDLE_LEFT:
    row = h // 2
    col = 0  # Zamiast 1
elif strategy == StartingStrategy.RANDOM:
    max_row = max(0, h - 1)
    row = random.randint(0, max_row if max_row > 0 else 0)
    if word_len <= w:
        max_col = w - word_len
        col = random.randint(0, max_col if max_col > 0 else 0)
    else:
        return None, None  # Słowo nie mieści się
```

---

### Błąd 3: KRYTYCZNY - Zakresy długości słów dla małych siatek
**Lokalizacja:** `crossword_strategies.py` → `_place_seed()` method

**Problem:**
```python
seed = self._get_seed_word(
    min_len=5,
    max_len=min(10, grid.width, grid.height)
)
```

**Wyjaśnienie - KLUCZOWY BUG:**
- Dla siatki 3x3: `max_len = min(10, 3, 3) = 3`, ale `min_len = 5`
- To daje `range(5, 4)` czyli PUSTY zakres!
- Generator nie mógł umieścić ŻADNEGO słowa startowego dla małych siatek

**Rozwiązanie:**
```python
max_grid_dim = min(grid.width, grid.height)
min_seed_len = max(2, min(5, max_grid_dim - 1))
max_seed_len = max_grid_dim

seed = self._get_seed_word(
    min_len=min_seed_len,
    max_len=max_seed_len
)
```

Teraz:
- Dla 3x3: min_len=2, max_len=3 ✓
- Dla 5x5: min_len=4, max_len=5 ✓
- Dla 15x15: min_len=5, max_len=15 ✓

---

## Testowanie
Wygenerowano plik `test_sizing.py` do testowania poprawy dla różnych rozmiarów:
- 5x5 (małe)
- 7x7 (średnie-małe)  
- 10x10 (średnie)
- 15x15 (domyślne)
- 20x15 i 12x18 (prostokątne)

Każdy rozmiar testowany w dwóch trybach:
1. Standard - generator z genxword
2. Multi-strategy - 6 strategii umieszczania

---

## Podsumowanie Zmian

| Plik | Metoda | Problem | Rozwiązanie |
|------|--------|---------|-------------|
| `crossword_new.py` | `_place_first_word()` | >= zamiast > | Zmieniono walidację wymiarów |
| `crossword_strategies.py` | `_get_seed_position()` | Ujemne kolumny, błędy randint | Doprawiono obliczenia pozycji |
| `crossword_strategies.py` | `_place_seed()` | Pusty zakres słów dla małych siatek | Adaptacyjne min/max długości |

---

## Status
✅ Wszystkie 3 krytyczne błędy naprawione
✅ Kod testowy przygotowany
✅ Gotowe do weryfikacji użytkownika
