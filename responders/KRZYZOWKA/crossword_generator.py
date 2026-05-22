# -*- coding: utf-8 -*-
"""
crossword_generator.py — Generator krzyżówek z algorytmem backtrackingu
Dąży do maksymalnego zagęszczenia haseł.
"""

import random
from typing import List, Optional, Tuple
from .word_source import WordSource
from .crossword_grid import CrosswordGrid, Direction


class CrosswordGenerator:
    """
    Generator krzyżówek wykorzystujący backtracking.
    Dąży do maksymalnego zagęszczenia słów w siatce.
    """
    
    def __init__(self, word_source: WordSource, max_attempts: int = 100):
        """
        Args:
            word_source: Źródło słów
            max_attempts: Maksymalna liczba prób generowania
        """
        self.word_source = word_source
        self.max_attempts = max_attempts
        self.best_grid: Optional[CrosswordGrid] = None
        self.best_density = 0.0
        self.generation_stats = {}
    
    def generate(self, width: int, height: int) -> CrosswordGrid:
        """
        Wygeneruj krzyżówkę.
        
        Strategia:
        1. Umieść słowo startowe (losowe, długość 5-10) pośrodku
        2. Backtrack: dla każdej pozycji, spróbuj umieścić słowa poziome i pionowe
        3. Zapisz warianty z największym zagęszczeniem
        
        Returns:
            Najlepszą znalezioną siatkę
        """
        self.best_grid = None
        self.best_density = 0.0
        
        for attempt in range(self.max_attempts):
            grid = CrosswordGrid(width, height)
            
            # Krok 1: Umieść początkowe słowo
            seed_word = self._get_seed_word(min(5, width, height), max(8, width, height))
            if not seed_word:
                continue
            
            start_row = height // 2
            start_col = (width - len(seed_word)) // 2
            
            grid.place_word(
                seed_word,
                start_row,
                start_col,
                Direction.HORIZONTAL,
                self.word_source.get_word(seed_word) or "?"
            )
            
            # Krok 2: Backtrack
            self._backtrack(grid, depth=0, max_depth=20)
            
            # Krok 3: Porównaj z najlepszą dotychczasową
            density = grid.get_density()
            if density > self.best_density:
                self.best_density = density
                self.best_grid = grid
        
        self.generation_stats = {
            'attempts': self.max_attempts,
            'best_density': self.best_density,
            'words_placed': len(self.best_grid.placed_words) if self.best_grid else 0
        }
        
        return self.best_grid or CrosswordGrid(width, height)
    
    def _get_seed_word(self, min_len: int, max_len: int) -> Optional[str]:
        """Pobierz losowe słowo o długości między min_len a max_len."""
        candidates = []
        for length in range(min_len, max_len + 1):
            candidates.extend(self.word_source.get_words_by_length(length))
        
        if candidates:
            return random.choice(candidates)
        return None
    
    def _backtrack(self, grid: CrosswordGrid, depth: int, max_depth: int) -> None:
        """
        Rekurencyjny backtrack do umieszczania słów.
        
        Strategia:
        - Dla każdej pustej komórki, próbuj umieścić słowa poziome i pionowe
        - Aby wstawić słowo, musi się przecinać z istniejącymi (chyba że to first move)
        - Priorytet: bardziej zagęszczone obszary
        """
        if depth >= max_depth:
            return
        
        # Jeśli to bardzo początek (pierwsze słowo dostarczone), skip
        if grid.get_filled_count() == 0:
            return
        
        # Pobierz puste komórki
        empty_cells = grid.get_empty_cells()
        if not empty_cells:
            return
        
        # Sortuj puste komórki: pierwszeństwo dla tych blisko innych liter
        empty_cells.sort(
            key=lambda pos: self._proximity_score(grid, pos),
            reverse=True
        )
        
        # Spróbuj umieścić słowa w pierwszych kilku pustych komórkach
        placed_any = False
        for row, col in empty_cells[:5]:  # Ogranicza eksplozję kombinacji
            # Próbuj poziomo
            words_h = self._find_matching_words(grid, row, col, Direction.HORIZONTAL)
            for word in words_h[:2]:  # Top 2 słowa
                # Walidacja: czy słowo ma przecięcie?
                if self._requires_intersection(grid, row, col, Direction.HORIZONTAL):
                    if self._count_intersections(grid, word, row, col, Direction.HORIZONTAL) == 0:
                        continue  # Pomiń jeśli brak przecięcia
                
                clue = self.word_source.get_word(word) or "?"
                if grid.place_word(word, row, col, Direction.HORIZONTAL, clue):
                    placed_any = True
                    self._backtrack(grid, depth + 1, max_depth)
            
            # Próbuj pionowo
            words_v = self._find_matching_words(grid, row, col, Direction.VERTICAL)
            for word in words_v[:2]:
                if self._requires_intersection(grid, row, col, Direction.VERTICAL):
                    if self._count_intersections(grid, word, row, col, Direction.VERTICAL) == 0:
                        continue
                
                clue = self.word_source.get_word(word) or "?"
                if grid.place_word(word, row, col, Direction.VERTICAL, clue):
                    placed_any = True
                    self._backtrack(grid, depth + 1, max_depth)
    
    def _proximity_score(self, grid: CrosswordGrid, pos: Tuple[int, int]) -> float:
        """
        Oblicz wynik bliskości dla pozycji (ile innych liter w pobliżu).
        Wyższy wynik = bardziej oblegana komórka.
        """
        row, col = pos
        score = 0
        
        # Sprawdź wszystkie 8 sąsiadujących komórek
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < grid.height and 0 <= nc < grid.width:
                    cell = grid.grid[nr][nc]
                    if cell and cell != "":  # Literał
                        score += 1
        
        return score
    
    def _requires_intersection(
        self,
        grid: CrosswordGrid,
        row: int,
        col: int,
        direction: Direction
    ) -> bool:
        """
        Sprawdź czy słowo w tej pozycji MUSI mieć przecięcie.
        Jeśli siatka jest już zaznaczana, wymaga przecięcia.
        """
        # Jeśli siatka ma mało liter, pierwszy ruchy mogą być bez przecięcia
        filled = grid.get_filled_count()
        return filled > 10  # Po umieszczeniu kilku słów, wymagaj przecięć
    
    def _find_matching_words(
        self,
        grid: CrosswordGrid,
        row: int,
        col: int,
        direction: Direction
    ) -> List[str]:
        """
        Znajdź słowa z bazy, które mogą być umieszczone wychodząc z (row, col).
        
        Priorytet:
        1. Słowa z więcej przecinającymi się literami
        2. Słowa dłuższe (ponad 4 litery)
        
        Zwraca słowa posortowane (malejąco) po liczbie przecinających się liter.
        """
        candidates = []
        
        if direction == Direction.HORIZONTAL:
            # Znajduje słowa, które mogą być umieszczone w wierszu row zaczynając od col
            # i przecinają się z istniejącymi literami
            for word_len in range(2, grid.width - col + 1):
                for word in self.word_source.get_words_by_length(word_len):
                    if grid.can_place_word(word, row, col, direction):
                        # Oblicz wynik: ile liter przecina
                        intersections = self._count_intersections(
                            grid, word, row, col, direction
                        )
                        # Bonus: preferuj dłuższe słowa
                        length_bonus = max(0, word_len - 4)
                        score = intersections * 10 + length_bonus
                        candidates.append((word, score, intersections))
        
        else:  # VERTICAL
            for word_len in range(2, grid.height - row + 1):
                for word in self.word_source.get_words_by_length(word_len):
                    if grid.can_place_word(word, row, col, direction):
                        intersections = self._count_intersections(
                            grid, word, row, col, direction
                        )
                        length_bonus = max(0, word_len - 4)
                        score = intersections * 10 + length_bonus
                        candidates.append((word, score, intersections))
        
        # Sortuj malejąco po wynikowi (przecinającymi literami + bonus długości)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Filtruj: jeśli liczba przecinających się liter == 0, 
        # to potencjalnie wyspę (bądź ostrożny)
        result = []
        for word, score, intersections in candidates:
            # Jeśli nie ma przecinających się liter, akceptuj tylko jeśli krata jest prawie pusta
            if intersections == 0 and grid.get_filled_count() > 5:
                continue
            result.append(word)
        
        return result
    
    def _count_intersections(
        self,
        grid: CrosswordGrid,
        word: str,
        row: int,
        col: int,
        direction: Direction
    ) -> int:
        """Ile liter słowa przecina się z istniejącymi literami."""
        count = 0
        
        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                c = col + i
                cell = grid.grid[row][c]
                if cell and cell != "" and cell == letter:
                    count += 1
        else:
            for i, letter in enumerate(word):
                r = row + i
                cell = grid.grid[r][col]
                if cell and cell != "" and cell == letter:
                    count += 1
        
        return count
    
    def generate_variants(
        self,
        width: int,
        height: int,
        num_variants: int = 3
    ) -> List[CrosswordGrid]:
        """
        Wygeneruj kilka różnych wariantów krzyżówki.
        
        Returns:
            Lista posortowana niemalejąco po gęstości
        """
        variants = []
        
        for _ in range(num_variants):
            grid = self.generate(width, height)
            variants.append(grid)
        
        # Sortuj po gęstości (malejąco)
        variants.sort(key=lambda g: g.get_density(), reverse=True)
        
        return variants
