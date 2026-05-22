# -*- coding: utf-8 -*-
"""
crossword_strategies.py — Wielostrategiczny generator krzyżówek

Implementuje różne podejścia do umieszczania wyrazów:
1. CENTERED - Wyraz środek w środku, pionowo go przecinają
2. TOP_LEFT - Wyraz startowy w górnym lewym rogu
3. TOP_CENTER - Wyraz startowy na górze pośrodku
4. SPIRAL - Łączy wyrazy w spiralę od środka
5. RANDOM - Losowe pozycje startowe
6. DENSE - Maksymalizuje gęstość (backtracking agresywny)

Każda strategia próbuje umieścić wyrazy przestrzegając reguł Scrabble:
- Wyrazy muszą się przecinać
- Wszystkie przecięcia muszą tworzyć poprawne słowa
- Brak pustych pół w samym tekście (mogą być na brzegach)
"""

import random
from typing import List, Tuple, Optional, Dict, Set
from enum import Enum
from .word_source import WordSource
from .crossword_grid import CrosswordGrid, Direction


class StartingStrategy(Enum):
    """Strategia umieszczenia wyrazu startowego."""
    CENTERED = "centered"
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    MIDDLE_LEFT = "middle_left"
    RANDOM = "random"


class StrategyConfig:
    """Konfiguracja dla konkretnej strategii."""
    
    def __init__(
        self,
        name: str,
        starting_strategy: StartingStrategy,
        max_iterations: int = 100,
        backtrack_depth: int = 25,
        aggressive_fill: bool = False
    ):
        self.name = name
        self.starting_strategy = starting_strategy
        self.max_iterations = max_iterations
        self.backtrack_depth = backtrack_depth
        self.aggressive_fill = aggressive_fill  # Jeśli True, wymuszaj więcej wyrazów


class StrategyResult:
    """Wynik generowania jedną strategią."""
    
    def __init__(
        self,
        grid: CrosswordGrid,
        strategy_name: str,
        density: float,
        word_count: int,
        filled_cells: int,
        total_cells: int,
        letter_count: int
    ):
        self.grid = grid
        self.strategy_name = strategy_name
        self.density = density
        self.word_count = word_count
        self.filled_cells = filled_cells
        self.total_cells = total_cells
        self.letter_count = letter_count
        
        # Oblicz procent pustych miejsc
        self.empty_percent = round(100 * (total_cells - filled_cells) / total_cells, 1)
    
    def __repr__(self):
        return (
            f"Strategy: {self.strategy_name} | "
            f"Density: {self.density:.1%} | "
            f"Words: {self.word_count} | "
            f"Empty: {self.empty_percent}% | "
            f"Letters: {self.letter_count}"
        )


class MultiStrategyGenerator:
    """
    Generator krzyżówek używający wielu strategii.
    
    Każda strategia generuje własną krzyżówkę,
    a następnie zostaje wybrana najlepsza.
    """
    
    def __init__(self, word_source: WordSource):
        self.word_source = word_source
        self.strategies = self._create_strategies()
    
    def _create_strategies(self) -> List[StrategyConfig]:
        """Utwórz listę strategii do próby."""
        return [
            StrategyConfig(
                "1. CENTERED (wyrazy od środka)",
                StartingStrategy.CENTERED,
                max_iterations=50,
                backtrack_depth=20,
                aggressive_fill=False
            ),
            StrategyConfig(
                "2. TOP_LEFT (z górnego lewego rogu)",
                StartingStrategy.TOP_LEFT,
                max_iterations=60,
                backtrack_depth=22,
                aggressive_fill=False
            ),
            StrategyConfig(
                "3. TOP_CENTER (top środek)",
                StartingStrategy.TOP_CENTER,
                max_iterations=60,
                backtrack_depth=22,
                aggressive_fill=False
            ),
            StrategyConfig(
                "4. MIDDLE_LEFT (środek lewa krawędź)",
                StartingStrategy.MIDDLE_LEFT,
                max_iterations=50,
                backtrack_depth=20,
                aggressive_fill=False
            ),
            StrategyConfig(
                "5. DENSE_MODE (maksymalna gęstość)",
                StartingStrategy.CENTERED,
                max_iterations=100,
                backtrack_depth=30,
                aggressive_fill=True
            ),
            StrategyConfig(
                "6. RANDOM (losowe umieszczenie)",
                StartingStrategy.RANDOM,
                max_iterations=70,
                backtrack_depth=25,
                aggressive_fill=False
            ),
        ]
    
    def generate_all_strategies(
        self,
        width: int,
        height: int,
        progress_callback=None,
        sort_by_density: bool = True
    ) -> List[StrategyResult]:
        """
        Wygeneruj krzyżówki używając wszystkich strategii.
        
        Args:
            width, height: Wymiary siatki
            progress_callback: Funkcja(strategy_name, current, total) do tracking postępu
            sort_by_density: Czy sortować po gęstości? False = zachowaj kolejność strategii
        
        Returns:
            Lista StrategyResult posortowana po gęstości (jeśli sort_by_density=True) 
            lub w oryginalnej kolejności strategii (jeśli False)
        """
        results = []
        total = len(self.strategies)
        
        for i, strategy_config in enumerate(self.strategies):
            if progress_callback:
                progress_callback(strategy_config.name, i + 1, total)
            
            generator = StrategyBasedGenerator(
                self.word_source,
                strategy_config
            )
            grid = generator.generate(width, height)
            
            # Oblicz metryki
            filled = grid.get_filled_count()
            total_cells = width * height
            density = grid.get_density()
            word_count = len(grid.placed_words)
            letter_count = sum(
                1 for r in grid.grid for cell in r
                if cell and cell not in ["", None]
            )
            
            result = StrategyResult(
                grid=grid,
                strategy_name=strategy_config.name,
                density=density,
                word_count=word_count,
                filled_cells=filled,
                total_cells=total_cells,
                letter_count=letter_count
            )
            results.append(result)
        
        # Sortuj po gęstości (malejąco) jeśli requested
        if sort_by_density:
            results.sort(key=lambda r: r.density, reverse=True)
        
        return results


class StrategyBasedGenerator:
    """
    Generator używający konkretnej strategii umieszczania wyrazów.
    """
    
    def __init__(self, word_source: WordSource, config: StrategyConfig):
        self.word_source = word_source
        self.config = config
        self.best_grid = None
        self.best_density = 0.0
    
    def generate(self, width: int, height: int) -> CrosswordGrid:
        """Wygeneruj krzyżówkę używając konfigurowanej strategii."""
        self.best_grid = None
        self.best_density = 0.0
        
        for attempt in range(self.config.max_iterations):
            grid = CrosswordGrid(width, height)
            
            # Umieść wyraz startowy
            if not self._place_seed(grid):
                continue
            
            # Backtracking
            self._backtrack(grid, depth=0)
            
            # Zaznacz puste pola na czarno (nie w tekście)
            self._mark_empty_cells_black(grid)
            
            # Porównaj z najlepszą dotychczasową
            density = grid.get_density()
            if density > self.best_density:
                self.best_density = density
                self.best_grid = grid
        
        return self.best_grid or CrosswordGrid(width, height)
    
    def _place_seed(self, grid: CrosswordGrid) -> bool:
        """Umieść wyraz startowy zgodnie ze strategią."""
        strategy = self.config.starting_strategy
        
        # Dostosuj długość słowa do rozmiaru siatki
        max_grid_dim = min(grid.width, grid.height)
        # Minimalnie musimy mieć słowa co najmniej 2-literowe, maksymalnie tyle ile siatka pozwala
        min_seed_len = max(2, min(5, max_grid_dim - 1))  # Co najmniej 2, co najwyżej 5 lub mniej
        max_seed_len = max_grid_dim
        
        seed = self._get_seed_word(
            min_len=min_seed_len,
            max_len=max_seed_len
        )
        
        if not seed:
            return False
        
        row, col = self._get_seed_position(grid, len(seed), strategy)
        if row is None:
            return False
        
        clue = self.word_source.get_word(seed) or "?"
        return grid.place_word(seed, row, col, Direction.HORIZONTAL, clue)
    
    def _get_seed_position(
        self,
        grid: CrosswordGrid,
        word_len: int,
        strategy: StartingStrategy
    ) -> Tuple[Optional[int], Optional[int]]:
        """Oblicz pozycję wyrazu startowego."""
        h, w = grid.height, grid.width
        
        # Sprawdzenie czy słowo się w ogóle zmieści
        if word_len > w and word_len > h:
            return None, None
        
        if strategy == StartingStrategy.CENTERED:
            row = h // 2
            col = max(0, (w - word_len) // 2)
        elif strategy == StartingStrategy.TOP_LEFT:
            row = 0
            col = 0
        elif strategy == StartingStrategy.TOP_CENTER:
            row = 0
            col = max(0, (w - word_len) // 2)
        elif strategy == StartingStrategy.MIDDLE_LEFT:
            row = h // 2
            col = 0
        elif strategy == StartingStrategy.RANDOM:
            # Upewnij się że dostępny zakres jest prawidłowy
            max_row = max(0, h - 1)
            row = random.randint(0, max_row if max_row > 0 else 0)
            
            # Kolumna: upewnij się że słowo się zmieści
            if word_len <= w:
                max_col = w - word_len
                col = random.randint(0, max_col if max_col > 0 else 0)
            else:
                return None, None
        else:
            return None, None
        
        # Ostateczna walidacja
        if col < 0 or col + word_len > w or row < 0 or row >= h:
            return None, None
        
        return row, col
    
    def _get_seed_word(self, min_len: int, max_len: int) -> Optional[str]:
        """Pobierz losowe słowo o określonej długości."""
        candidates = []
        for length in range(min_len, max_len + 1):
            candidates.extend(self.word_source.get_words_by_length(length))
        
        return random.choice(candidates) if candidates else None
    
    def _backtrack(self, grid: CrosswordGrid, depth: int) -> int:
        """
        Rekurencyjny backtracking z umieszczaniem wyrazów.
        
        Returns:
            Liczba umieszczonych wyrazów
        """
        if depth >= self.config.backtrack_depth:
            return 0
        
        # Pobierz puste komórki
        empty_cells = grid.get_empty_cells()
        if not empty_cells:
            return 0
        
        # Sortuj: najpierw te blisko istniejących liter
        empty_cells.sort(
            key=lambda pos: self._proximity_score(grid, pos),
            reverse=True
        )
        
        # Jeśli nieagresywny mode, nie próbuj wypełniać wszystkich pól
        if not self.config.aggressive_fill:
            # Zmniejsz limit aby zostawić puste pola
            check_limit = 3  # Zamiast 10
        else:
            check_limit = 10
        
        # Spróbuj umieścić słowa
        placed_count = 0
        
        for row, col in empty_cells[:check_limit]:
            # Próbuj poziomo
            h_words = self._find_matching_words(grid, row, col, Direction.HORIZONTAL)
            for word in h_words[:2]:  # Zmniejsz z 3 do 2 kandydatów
                definition = self.word_source.get_word(word) or f"({len(word)} liter)"
                if grid.place_word(word, row, col, Direction.HORIZONTAL, definition):
                    new_placed = self._backtrack(grid, depth + 1)
                    placed_count += 1 + new_placed
                    break  # Spróbuj następną pozycję po umieszczeniu
            
            # Próbuj pionowo (jeśli poziomo nie zadziałało)
            v_words = self._find_matching_words(grid, row, col, Direction.VERTICAL)
            for word in v_words[:2]:
                definition = self.word_source.get_word(word) or f"({len(word)} liter)"
                if grid.place_word(word, row, col, Direction.VERTICAL, definition):
                    new_placed = self._backtrack(grid, depth + 1)
                    placed_count += 1 + new_placed
                    break
        
        return placed_count
    
    def _proximity_score(self, grid: CrosswordGrid, pos: Tuple[int, int]) -> float:
        """Punktacja bliskości (ile liter w pobliżu)."""
        row, col = pos
        score = 0
        
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < grid.height and 0 <= nc < grid.width:
                    cell = grid.grid[nr][nc]
                    if cell and cell not in ["", None]:
                        score += 1
        
        return score
    
    def _find_matching_words(
        self,
        grid: CrosswordGrid,
        row: int,
        col: int,
        direction: Direction
    ) -> List[str]:
        """Znajdź słowa mogące być umieszczone w danej pozycji."""
        candidates = []
        max_len = (
            grid.width - col if direction == Direction.HORIZONTAL
            else grid.height - row
        )
        
        for word_len in range(2, min(15, max_len + 1)):
            for word in self.word_source.get_words_by_length(word_len):
                if grid.can_place_word(word, row, col, direction):
                    intersections = self._count_intersections(
                        grid, word, row, col, direction
                    )
                    # Preferuj słowa z przecięciami
                    score = intersections * 10 + max(0, word_len - 4)
                    candidates.append((word, score))
        
        # Sortuj po wynikach
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [w for w, _ in candidates]
    
    def _count_intersections(
        self,
        grid: CrosswordGrid,
        word: str,
        row: int,
        col: int,
        direction: Direction
    ) -> int:
        """Ile liter słowa się przecina z istniejącymi."""
        count = 0
        
        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                c = col + i
                if c < grid.width:
                    cell = grid.grid[row][c]
                    if cell and cell not in ["", None] and cell == letter:
                        count += 1
        else:
            for i, letter in enumerate(word):
                r = row + i
                if r < grid.height:
                    cell = grid.grid[r][col]
                    if cell and cell not in ["", None] and cell == letter:
                        count += 1
        
        return count
    
    def _mark_empty_cells_black(self, grid: CrosswordGrid) -> None:
        """
        Zaznacz puste pola na czarno (None).
        
        Strategia:
        1. Każde "puste" pole ("") które nie może być osiągnięte przez wyraz
           zostaje zaznaczone jako niedostępne (None)
        2. Sprawdź czy pole ma potencjał być częścią przyszłego wyrazu
        """
        # Iteracyjnie sprawdzaj każde puste pole
        changed = True
        iterations = 0
        max_iterations = 5
        
        while changed and iterations < max_iterations:
            changed = False
            iterations += 1
            
            for r in range(grid.height):
                for c in range(grid.width):
                    cell = grid.grid[r][c]
                    
                    # Jeśli to puste pole
                    if cell == "":
                        # Sprawdź czy może być częścią wyrazu
                        can_be_used = self._can_be_part_of_word(grid, r, c)
                        
                        if not can_be_used:
                            # Zaznacz je na czarno
                            grid.grid[r][c] = None
                            changed = True
    
    def _can_be_part_of_word(self, grid: CrosswordGrid, row: int, col: int) -> bool:
        """
        Sprawdź czy puste pole może być częścią wyrazu.
        
        Pole może być częścią wyrazu jeśli:
        1. Jest w linii (poziomo/pionowo) z litera)
        2. Ma sąsiadów z literami w odpowiednim kierunku
        """
        # Sprawdź poziomo: czy są litery z lewej ORAZ z prawej (lub sąsiednie)
        h_connected_left = False
        h_connected_right = False
        
        for c in range(col - 1, -1, -1):
            if grid.grid[row][c] is None:
                break  # Czarne pole blokuje
            if grid.grid[row][c] and grid.grid[row][c] != "":
                h_connected_left = True
                break
        
        for c in range(col + 1, grid.width):
            if grid.grid[row][c] is None:
                break
            if grid.grid[row][c] and grid.grid[row][c] != "":
                h_connected_right = True
                break
        
        # Sprawdź pionowo
        v_connected_top = False
        v_connected_bottom = False
        
        for r in range(row - 1, -1, -1):
            if grid.grid[r][col] is None:
                break
            if grid.grid[r][col] and grid.grid[r][col] != "":
                v_connected_top = True
                break
        
        for r in range(row + 1, grid.height):
            if grid.grid[r][col] is None:
                break
            if grid.grid[r][col] and grid.grid[r][col] != "":
                v_connected_bottom = True
                break
        
        # Może być używane jeśli jest w linii z literami (w którykolwiek kierunek)
        h_can_be_used = h_connected_left or h_connected_right
        v_can_be_used = v_connected_top or v_connected_bottom
        
        # Jeśli jest w jakimkolwiek kierunku — może być użyte
        return h_can_be_used or v_can_be_used
