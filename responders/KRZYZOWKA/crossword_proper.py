# -*- coding: utf-8 -*-
"""
crossword_proper.py — PRAWIDŁOWY generator krzyżówek

ALGORYTM (oparty na genxword):
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
from typing import List, Optional, Tuple, Dict
from collections import defaultdict
from .word_source import WordSource
from .crossword_grid import CrosswordGrid, Direction


class ProperCrosswordGenerator:
    """
    Generator krzyżówek ze ZDROWYM ROZSĄDKIEM.
    
    Siatka zaczyna się CAŁKOWICIE CZARNA (None).
    Wyrazy są umieszczane z przerwami czarnymi polami.
    """
    
    def __init__(self, word_source: WordSource):
        self.word_source = word_source
    
    def generate(self, width: int, height: int, max_attempts: int = 50) -> CrosswordGrid:
        """
        Wygeneruj PRAWIDŁOWĄ krzyżówkę.
        
        Procedura:
        1. Siatka całkowicie czarna (None)
        2. Wybierz wyraz startowy (poziomo, ze środka)
        3. Umieść go ze znakami czarnymi po bokach
        4. Dla każdej litery: spróbuj umieścić wyraz pionowo
        5. Powtórz aż do nasycenia
        """
        best_grid = None
        best_word_count = 0
        
        for attempt in range(max_attempts):
            grid = self._create_empty_grid(width, height)
            placed_words = []
            
            # Krok 1: Umieść wyraz startowy poziomo (ze środka)
            seed = self._get_seed_word(min_len=4, max_len=min(width-4, 10))
            if not seed:
                continue
            
            seed_row = height // 2
            seed_col = max(1, (width - len(seed)) // 2)
            
            # Czy się zmieści?
            if seed_col + len(seed) + 1 > width:
                continue
            
            # Umieść wyraz ze spacjami
            for i, letter in enumerate(seed):
                grid.grid[seed_row][seed_col + i] = letter
            
            # Umieść czarne pola Z LEWEJ (jeśli jest miejsce)
            if seed_col > 0:
                grid.grid[seed_row][seed_col - 1] = None
            
            # Umieść czarne pola Z PRAWEJ
            if seed_col + len(seed) < width:
                grid.grid[seed_row][seed_col + len(seed)] = None
            
            placed_words.append(seed)
            
            # Krok 2: Recursive backtrack
            self._backtrack_place_words(grid, placed_words, max_depth=10)
            
            word_count = len(placed_words)
            if word_count > best_word_count:
                best_word_count = word_count
                best_grid = grid
        
        return best_grid or self._create_empty_grid(width, height)
    
    def _create_empty_grid(self, width: int, height: int) -> CrosswordGrid:
        """Stwórz siatkę całkowicie BIAŁĄ ("" = puste pola)."""
        grid = CrosswordGrid(width, height)
        for r in range(height):
            for c in range(width):
                grid.grid[r][c] = ""  # BIAŁE POLA = PUSTE, CZARNE BĘDĄ DODANE PÓŹNIEJ
        return grid
    
    def _get_seed_word(self, min_len: int, max_len: int) -> Optional[str]:
        """Pobierz losowe słowo."""
        candidates = []
        for length in range(min_len, max_len + 1):
            candidates.extend(self.word_source.get_words_by_length(length))
        return random.choice(candidates) if candidates else None
    def _backtrack_place_words(
        self,
        grid: CrosswordGrid,
        placed_words: List[str],
        max_depth: int = 10,
        depth: int = 0
    ) -> None:
        """
        Rekurencyjnie umieszczaj wyrazy PIONOWO i POZIOMO.
        """
        if depth >= max_depth:
            return
        
        letter_positions = self._find_all_letters(grid)
        
        if not letter_positions:
            return
        
        added_any = False
        attempts = 0
        
        # Alternuj: parzyste depth = PIONOWO, nieparzyste = POZIOMO
        if depth % 2 == 0:
            # PIONOWO
            for (row, col), letter in letter_positions:
                if attempts >= 2:
                    break
                if self._try_place_word_vertical(grid, row, col, letter, placed_words):
                    added_any = True
                    attempts += 1
        else:
            # POZIOMO
            for (row, col), letter in letter_positions:
                if attempts >= 2:
                    break
                if self._try_place_word_horizontal(grid, row, col, letter, placed_words):
                    added_any = True
                    attempts += 1
        
        if added_any:
            self._backtrack_place_words(grid, placed_words, max_depth, depth + 1)
    
    def _find_all_letters(self, grid: CrosswordGrid) -> List[Tuple[Tuple[int, int], str]]:
        """Znajdź wszystkie pozycje liter w siatce."""
        letters = []
        for r in range(grid.height):
            for c in range(grid.width):
                cell = grid.grid[r][c]
                if cell and cell != "" and cell not in [None]:
                    letters.append(((r, c), cell))
        return letters
    
    def _try_place_word_vertical(
        self,
        grid: CrosswordGrid,
        target_row: int,
        col: int,
        seed_letter: str,
        placed_words: List[str]
    ) -> bool:
        """
        Spróbuj umieścić wyraz pionowo na danej literze.
        
        Returns: True jeśli się udało
        """
        # Szukaj wyrazów zawierających seed_letter
        for word_len in range(2, min(grid.height - 2, 8)):
            words = self.word_source.get_words_by_length(word_len)
            random.shuffle(words)
            
            for word in words[:10]:  # Spróbuj max 10 wyrazów
                if word in placed_words:
                    continue
                
                # Szukaj seed_letter w wyrazie
                for pos_in_word, w_letter in enumerate(word):
                    if w_letter != seed_letter:
                        continue
                    
                    # Wylicz gdzie zacząć wyraz
                    start_row = target_row - pos_in_word
                    
                    # Czy się zmieści?
                    if start_row < 1 or start_row + len(word) >= grid.height - 1:
                        continue
                    
                    # Czy można umieścić? (bez czarnych pól w środku)
                    if not self._can_place_vertical_at(grid, word, start_row, col):
                        continue
                    
                    # UMIEŚĆ WYRAZ
                    for i, letter in enumerate(word):
                        grid.grid[start_row + i][col] = letter
                    
                    # Czarne pola POWYŻEJ i PONIŻEJ
                    if start_row > 0:
                        grid.grid[start_row - 1][col] = None
                    if start_row + len(word) < grid.height:
                        grid.grid[start_row + len(word)][col] = None
                    
                    # Czarne pola Z BOKÓW (opcjonalnie, na razie nie dodaję)
                    
                    placed_words.append(word)
                    return True
        
        return False
    
    def _can_place_vertical_at(
        self,
        grid: CrosswordGrid,
        word: str,
        start_row: int,
        col: int
    ) -> bool:
        """Sprawdź czy kunnen umieścić wyraz pionowo."""
        for i, letter in enumerate(word):
            r = start_row + i
            c = col
            
            if r < 0 or r >= grid.height or c < 0 or c >= grid.width:
                return False
            
            cell = grid.grid[r][c]
            
            # Jeśli czarne pole, nie można
            if cell is None:
                return False
            
            # Jeśli już litera, musi być ta sama
            if cell and cell != "" and cell != letter:
                return False
        
        return True
    
    def _try_place_word_horizontal(
        self,
        grid: CrosswordGrid,
        target_row: int,
        target_col: int,
        seed_letter: str,
        placed_words: List[str]
    ) -> bool:
        """
        Spróbuj umieścić wyraz poziomo na danej literze.
        
        Returns: True jeśli się udało
        """
        for word_len in range(2, min(grid.width - 2, 8)):
            words = self.word_source.get_words_by_length(word_len)
            random.shuffle(words)
            
            for word in words[:10]:
                if word in placed_words:
                    continue
                
                # Szukaj seed_letter w wyrazie
                for pos_in_word, w_letter in enumerate(word):
                    if w_letter != seed_letter:
                        continue
                    
                    # Wylicz gdzie zacząć wyraz
                    start_col = target_col - pos_in_word
                    
                    # Czy się zmieści?
                    if start_col < 1 or start_col + len(word) >= grid.width - 1:
                        continue
                    
                    # Czy można umieścić?
                    if not self._can_place_horizontal_at(grid, word, target_row, start_col):
                        continue
                    
                    # UMIEŚĆ WYRAZ
                    for i, letter in enumerate(word):
                        grid.grid[target_row][start_col + i] = letter
                    
                    # Czarne pola Z LEWEJ i Z PRAWEJ
                    if start_col > 0:
                        grid.grid[target_row][start_col - 1] = None
                    if start_col + len(word) < grid.width:
                        grid.grid[target_row][start_col + len(word)] = None
                    
                    placed_words.append(word)
                    return True
        
        return False
    
    def _can_place_horizontal_at(
        self,
        grid: CrosswordGrid,
        word: str,
        row: int,
        start_col: int
    ) -> bool:
        """Sprawdź czy kunnen umieścić wyraz poziomo."""
        for i, letter in enumerate(word):
            r = row
            c = start_col + i
            
            if r < 0 or r >= grid.height or c < 0 or c >= grid.width:
                return False
            
            cell = grid.grid[r][c]
            
            # Jeśli czarne pole, nie można
            if cell is None:
                return False
            
            # Jeśli już litera, musi być ta sama
            if cell and cell != "" and cell != letter:
                return False
        
        return True

