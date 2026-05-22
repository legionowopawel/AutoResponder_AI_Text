# -*- coding: utf-8 -*-
"""
crossword_new.py — PRAWIDŁOWY generator krzyżówek

Algorytm (wg genxword):
1. Siatka wypełniona pustymi cellami ('' = białe)
2. Umieść pierwszy wyraz losowo
3. Dla każdego wyrazu szukaj na PRZECIĘCIACH z już umieszczonymi
4. Zbiór let_coords mapuje każdą literę na jej pozycje
5. Scoring przewiduje czy wyraz może być umieszczony
6. Czarne pola = obszary między wyrazami (naturalnie powstaną)
7. Wiele prób, wybierz najlepszą z największą ilością wyrazów
"""

import random
import time
from typing import List, Optional, Tuple
from collections import defaultdict
from .word_source import WordSource
from .crossword_grid import CrosswordGrid


class CrosswordGeneratorNew:
    """
    Prawidłowy generator krzyżówek oparty na genxword.
    """
    
    def __init__(self, word_source: WordSource):
        self.word_source = word_source
        self.empty = ''  # Marker pola pustego
        self.let_coords = defaultdict(list)  # {letter: [(row, col, vertical), ...]}
        self.grid = None
        self.height = 0
        self.width = 0
    
    def generate(self, width: int, height: int, time_limit: float = 3.0) -> CrosswordGrid:
        """
        Wygeneruj krzyżówkę w ciągu time_limit sekund.
        Zwraca najlepszą z największą ilością wyrazów.
        """
        self.width = width
        self.height = height
        
        best_wordlist = []
        best_grid = None
        
        start_time = time.time()
        
        while (time.time() - start_time) < time_limit:
            self._prep_grid()  # Czyszczenie dla nowej próby
            
            wordlist = self._prepare_wordlist()
            if not wordlist:
                continue
            
            # Umieść pierwszy wyraz losowo
            if wordlist:
                self._place_first_word(wordlist[0])
            
            # Umieszczaj kolejne wyrazy
            for word in wordlist[1:]:
                self._add_word(word)
            
            # Jeśli lepsze rozwiązanie, zapamiętaj
            if len(self.current_wordlist) > len(best_wordlist):
                best_wordlist = list(self.current_wordlist)
                best_grid = [row[:] for row in self.grid]
        
        # Zwróć krzyżówkę
        result = CrosswordGrid(width, height)
        if best_grid:
            # Zamień puste pola ("") na czarne (None)
            for r in range(height):
                for c in range(width):
                    if best_grid[r][c] == self.empty:
                        best_grid[r][c] = None
            result.grid = best_grid
            
            # Wyodrębnij wyrazy z siatki
            self._extract_words_from_grid(result)
        
        return result
    
    def _prep_grid(self):
        """Przygotuj grę do nowej próby."""
        self.grid = [[self.empty] * self.width for _ in range(self.height)]
        self.current_wordlist = []
        self.let_coords.clear()
    
    def _prepare_wordlist(self) -> List[str]:
        """Pobierz słowa, posortuj od najdłuższych."""
        all_words = []
        
        max_length = max(self.width, self.height)
        # Zbierz wszystkie dostępne słowa dopasowane do wymiarów planszy
        for length in range(2, max_length + 1):
            words = self.word_source.get_words_by_length(length)
            all_words.extend(words)
        
        if not all_words:
            return []
        
        # Posortuj od najdłuższych, wymieszaj
        all_words.sort(key=len, reverse=True)
        random.shuffle(all_words)
        return all_words[:60]  # Max 60 słów
    
    def _place_first_word(self, word: str):
        """Umieść pierwszy wyraz losowo."""
        # Jeśli wyraz nie mieści się w żaden sposób, wybierz inny
        if len(word) > self.height and len(word) > self.width:
            return
        
        vertical = random.choice([True, False])
        
        if vertical:
            # Sprawdzenie czy wyraz mieści się pionowo
            if len(word) <= self.height:
                row = random.randint(0, max(0, self.height - len(word)))
            else:
                return  # Nie mieści się pionowo
            col = random.randint(0, max(0, self.width - 1))
        else:
            # Sprawdzenie czy wyraz mieści się poziomo
            row = random.randint(0, max(0, self.height - 1))
            if len(word) <= self.width:
                col = random.randint(0, max(0, self.width - len(word)))
            else:
                return  # Nie mieści się poziomo
        
        self._set_word(word, row, col, vertical)
    
    def _add_word(self, word: str) -> bool:
        """Dodaj wyraz do siatki."""
        # Szukaj możliwych lokacji
        placement = self._get_coords(word)
        
        if placement:
            row, col, vertical = placement
            self._set_word(word, row, col, vertical)
            return True
        
        return False
    
    def _get_coords(self, word: str) -> Optional[Tuple[int, int, bool]]:
        """
        Szukaj możliwych pozycji dla wyrazu.
        
        Dla każdej litery w wyrazie szukaj gdzie jest na siatce,
        potem sprawdzaj czy można tam umieścić wyraz.
        """
        best_placement = None
        best_score = 0
        
        # Dla każdej litery w wyrazie
        for word_idx, word_letter in enumerate(word):
            # Szukaj tej litery na siatce
            if word_letter in self.let_coords:
                for grid_row, grid_col, grid_vertical in self.let_coords[word_letter]:
                    # Spróbuj POZIOMO
                    placement_h = self._check_placement(
                        word, grid_row, grid_col - word_idx, False
                    )
                    if placement_h:
                        score = placement_h[3]
                        if score > best_score:
                            best_score = score
                            best_placement = (placement_h[0], placement_h[1], False)
                    
                    # Spróbuj PIONOWO
                    placement_v = self._check_placement(
                        word, grid_row - word_idx, grid_col, True
                    )
                    if placement_v:
                        score = placement_v[3]
                        if score > best_score:
                            best_score = score
                            best_placement = (placement_v[0], placement_v[1], True)
        
        return best_placement
    
    def _check_placement(
        self,
        word: str,
        start_row: int,
        start_col: int,
        vertical: bool
    ) -> Optional[Tuple[int, int, bool, int]]:
        """
        Sprawdź czy można umieścić wyraz na danej pozycji.
        Zwróć (row, col, vertical, score) lub None.
        """
        if vertical:
            score = self._check_vertical(word, start_row, start_col)
        else:
            score = self._check_horizontal(word, start_row, start_col)
        
        if score > 0:
            return (start_row, start_col, vertical, score)
        
        return None
    
    def _check_horizontal(self, word: str, row: int, col: int) -> int:
        """
        Sprawdź możliwość umieszczenia POZIOMO.
        
        Reguły:
        - Nie poza granice
        - Lewa i prawa strona muszą być puste lub nie istnieć
        - Każda komórka: albo pusta (bez sąsiadów w/d), albo ta sama litera
        
        Zwróć score (liczba przecięć) lub 0.
        """
        # Granice
        if col < 0 or col + len(word) > self.width:
            return 0
        
        # Lewa strona
        if col > 0 and self.grid[row][col - 1] != self.empty:
            return 0
        
        # Prawa strona
        if col + len(word) < self.width and self.grid[row][col + len(word)] != self.empty:
            return 0
        
        score = 0
        
        for i, letter in enumerate(word):
            c = col + i
            cell = self.grid[row][c]
            
            if cell == self.empty:
                # Komórka pusta: nie może mieć sąsiadów w górę/dół
                if row > 0 and self.grid[row - 1][c] != self.empty:
                    return 0
                if row < self.height - 1 and self.grid[row + 1][c] != self.empty:
                    return 0
            elif cell == letter:
                # Przecięcie - zawsze OK
                score += 1
            else:
                # Konflikt
                return 0
        
        return max(1, score)
    
    def _check_vertical(self, word: str, row: int, col: int) -> int:
        """
        Sprawdź możliwość umieszczenia PIONOWO.
        """
        # Granice
        if row < 0 or row + len(word) > self.height:
            return 0
        
        # Góra
        if row > 0 and self.grid[row - 1][col] != self.empty:
            return 0
        
        # Dół
        if row + len(word) < self.height and self.grid[row + len(word)][col] != self.empty:
            return 0
        
        score = 0
        
        for i, letter in enumerate(word):
            r = row + i
            cell = self.grid[r][col]
            
            if cell == self.empty:
                # Komórka pusta: nie może mieć sąsiadów w lewo/prawo
                if col > 0 and self.grid[r][col - 1] != self.empty:
                    return 0
                if col < self.width - 1 and self.grid[r][col + 1] != self.empty:
                    return 0
            elif cell == letter:
                # Przecięcie - OK
                score += 1
            else:
                # Konflikt
                return 0
        
        return max(1, score)
    
    def _set_word(self, word: str, row: int, col: int, vertical: bool):
        """
        Umieść wyraz na siatce.
        Zaktualizuj let_coords.
        """
        self.current_wordlist.append(word)
        
        if vertical:
            for i, letter in enumerate(word):
                r = row + i
                self.grid[r][col] = letter
                if (r, col, vertical) not in self.let_coords[letter]:
                    self.let_coords[letter].append((r, col, vertical))
        else:
            for i, letter in enumerate(word):
                c = col + i
                self.grid[row][c] = letter
                if (row, c, vertical) not in self.let_coords[letter]:
                    self.let_coords[letter].append((row, c, vertical))
    
    def _extract_words_from_grid(self, grid: CrosswordGrid) -> None:
        """
        Wyodrębnij wyrazy z siatki (poziome i pionowe).
        Populuj placed_words i clue_numbers w grid.
        Pobierz definicje z word_source.
        """
        from .crossword_grid import Direction
        
        clue_num = 1
        placed_words = []
        clue_numbers = {}
        
        # Przeszukaj siatkę aby znaleźć ALL wyrazy
        for row in range(grid.height):
            for col in range(grid.width):
                cell = grid.grid[row][col]
                
                # Pomiń czarne pola
                if cell is None or cell == self.empty:
                    continue
                
                # Czy to początek wyrazu POZIOMEGO?
                if (col == 0 or grid.grid[row][col - 1] is None) and \
                   (col < grid.width - 1 and grid.grid[row][col + 1] is not None):
                    # Zbierz wyraz poziomo
                    horiz_word = ""
                    start_col = col
                    c = col
                    while c < grid.width and grid.grid[row][c] is not None:
                        horiz_word += grid.grid[row][c]
                        c += 1
                    
                    # Zapisz
                    if len(horiz_word) > 1:
                        # Pobierz definicję z word_source
                        definition = self.word_source.get_word(horiz_word)
                        if definition is None:
                            definition = f"({len(horiz_word)} liter)"
                        
                        clue_numbers[(row, col)] = clue_num
                        placed_words.append((horiz_word, row, col, Direction.HORIZONTAL, definition))
                        clue_num += 1
                
                # Czy to początek wyrazu PIONOWEGO?
                if (row == 0 or grid.grid[row - 1][col] is None) and \
                   (row < grid.height - 1 and grid.grid[row + 1][col] is not None):
                    # Zbierz wyraz pionowo
                    vert_word = ""
                    start_row = row
                    r = row
                    while r < grid.height and grid.grid[r][col] is not None:
                        vert_word += grid.grid[r][col]
                        r += 1
                    
                    # Zapisz
                    if len(vert_word) > 1:
                        # Pobierz definicję z word_source
                        definition = self.word_source.get_word(vert_word)
                        if definition is None:
                            definition = f"({len(vert_word)} liter)"
                        
                        clue_numbers[(row, col)] = clue_num
                        placed_words.append((vert_word, row, col, Direction.VERTICAL, definition))
                        clue_num += 1
        
        # Populuj grid
        grid.placed_words = placed_words
        grid.clue_numbers = clue_numbers
