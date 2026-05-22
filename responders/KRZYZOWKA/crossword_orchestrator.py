# -*- coding: utf-8 -*-
"""
crossword_orchestrator.py — Orkiestracja generowania i eksportu krzyżówek
Zarządza procesem od input do output katalogów WYNIKI_*

Obsługuje:
- Multi-strategy generation (6 podejść do umieszczania wyrazów)
- Automatyczne zaznaczanie pustych pól na czarno
- Nazewnictwo katalogów z procentem pustych i ilością użytych liter
"""

import os
import datetime
from typing import Optional, List, Callable
from pathlib import Path
from .word_source import WordSource
from .crossword_grid import CrosswordGrid
from .crossword_generator import CrosswordGenerator
from .crossword_new import CrosswordGeneratorNew
from .crossword_strategies import MultiStrategyGenerator, StrategyResult
from .image_renderer import CrosswordImageRenderer
from .excel_exporter import ExcelExporter
from .html_exporter import HTMLExporter


class CrosswordOrchestrator:
    """Zarządza całym procesem generowania i eksportu krzyżówek."""
    
    def __init__(self, base_dir: str = "."):
        """
        Args:
            base_dir: Katalog bazowy projektu
        """
        self.base_dir = base_dir
        self.word_source: Optional[WordSource] = None
        self.output_dir: Optional[str] = None
    
    def setup_word_source(self, word_file: Optional[str] = None) -> bool:
        """
        Załaduj źródło słów.
        
        Args:
            word_file: Ścieżka do pliku z wyrazami, lub None dla domyślnego
        
        Returns:
            True jeśli OK
        """
        try:
            if word_file is None:
                # Spróbuj dane.txt w katalogu projektu
                parent_dir = os.path.dirname(os.path.abspath(__file__))
                parent_dir = os.path.dirname(parent_dir)  # Wyjdź z Krzyzowka
                word_file = os.path.join(parent_dir, "dane.txt")
            
            self.word_source = WordSource(word_file)
            
            if not self.word_source.loaded:
                return False
            
            print(f"[Orchestrator] Źródło słów: OK ({len(self.word_source.get_all_words())} słów)")
            return True
            
        except Exception as e:
            print(f"[Orchestrator] BŁĄD ładowania źródła: {e}")
            return False
    
    def create_output_directory(self, source_filename: str) -> bool:
        """
        Utwórz katalog wyjściowy w formacie WYNIKI_data_godzina_nazwa.
        
        Args:
            source_filename: Nazwa pliku źródłowego (bez rozszerzenia)
        
        Returns:
            True jeśli OK
        """
        try:
            now = datetime.datetime.now()
            date_time = now.strftime("%Y%m%d_%H%M%S")
            
            # Wyczyść nazwę
            clean_name = Path(source_filename).stem  # Bez rozszerzenia
            
            output_name = f"WYNIKI_{date_time}_{clean_name}"
            self.output_dir = os.path.join(self.base_dir, output_name)
            
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"[Orchestrator] Katalog wyjściowy: {self.output_dir}")
            return True
            
        except Exception as e:
            print(f"[Orchestrator] BŁĄD tworzenia katalogu: {e}")
            return False
    
    def generate_and_export(
        self,
        width: int,
        height: int,
        source_filename: str = "dane.txt",
        word_file: Optional[str] = None,
        num_variants: int = 3,
        multi_strategy: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """
        Wygeneruj krzyżówkę(i) i wyeksportuj do wszystkich formatów.
        
        Args:
            width: Szerokość siatki
            height: Wysokość siatki
            source_filename: Nazwa pliku źródłowego (do nazwy katalogu)
            word_file: Ścieżka do pliku słów, lub None dla domyślnego
            num_variants: Liczba wariantów do wygenerowania
            multi_strategy: Czy używać multi-strategy generation (6 strategii)?
            progress_callback: Funkcja(message: str) do tracking postępu
        
        Returns:
            True jeśli OK
        """
        # Krok 1: Załaduj słowa
        if not self.setup_word_source(word_file):
            print("[Orchestrator] BŁĄD: Nie mogę załadować słów")
            return False
        
        # Krok 2: Utwórz katalog wyjściowy
        if not self.create_output_directory(source_filename):
            print("[Orchestrator] BŁĄD: Nie mogę utworzyć katalogu wyjściowego")
            return False
        
        # Krok 3: Wygeneruj warianty
        if multi_strategy:
            return self._generate_multi_strategy(
                width, height, num_variants, progress_callback
            )
        else:
            return self._generate_single_strategy(
                width, height, num_variants, progress_callback
            )
    
    def _generate_single_strategy(
        self,
        width: int,
        height: int,
        num_variants: int,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Nowy generator - prawidłowa krzyżówka z genxword-like algorytmem."""
        msg = f"[Orchestrator] Generuję {num_variants} wariantów krzyżówki ({width}x{height})..."
        print(msg)
        if progress_callback:
            progress_callback(msg)
        
        # Nowy, prawidłowy generator
        generator = CrosswordGeneratorNew(self.word_source)
        
        variants = []
        for i in range(num_variants):
            msg = f"  Wariant {i+1}/{num_variants}..."
            print(msg)
            if progress_callback:
                progress_callback(msg)
            
            grid = generator.generate(width, height, time_limit=3.0)
            variants.append(grid)
        
        print(f"[Orchestrator] Wygenerowano warianty")
        
        # Eksportuj każdy wariant
        for i, grid in enumerate(variants, 1):
            self._export_variant(grid, i, width, height)
        
        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True
    
    def _generate_multi_strategy(
        self,
        width: int,
        height: int,
        num_variants: int,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Nowe podejście - lata multi-strategy (6 strategii)."""
        msg = f"[Orchestrator] Generuję krzyżówki z {num_variants} strategiami ({width}x{height})..."
        print(msg)
        if progress_callback:
            progress_callback(msg)
        
        # Utwórz generator multi-strategy
        multi_gen = MultiStrategyGenerator(self.word_source)
        
        # Funkcja progress do generator
        def strategy_progress(strategy_name: str, current: int, total: int):
            msg = f"  [{current}/{total}] Generuję: {strategy_name}..."
            print(msg)
            if progress_callback:
                progress_callback(msg)
        
        # Wygeneruj wszystkie strategie - NIE sortuj aby zobaczyć różne podejścia
        results = multi_gen.generate_all_strategies(
            width, height, progress_callback=strategy_progress, sort_by_density=False
        )
        
        # Wyświetl statystyki
        print(f"[Orchestrator] Wyniki generowania:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result}")
        
        # ZMIANA: Zamiast brać top num_variants po gęstości,
        # weź pierwsze num_variants strategii w oryginalnej kolejności
        # To pokazuje różne podejścia
        selected_results = results[:num_variants]
        
        # Jeśli mamy mniej wyników niż variants, uzupełnij
        if len(selected_results) < num_variants:
            selected_results = results
        
        # Eksportuj wybrane warianty
        for i, result in enumerate(selected_results, 1):
            self._export_variant_multi_strategy(
                result.grid,
                i,
                result.strategy_name,
                result.empty_percent,
                result.letter_count,
                width,
                height
            )
        
        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True
    
    def _export_variant_multi_strategy(
        self,
        grid: CrosswordGrid,
        variant_num: int,
        strategy_name: str,
        empty_percent: float,
        letter_count: int,
        width: int,
        height: int
    ) -> None:
        """
        Eksportuj wariant z multi-strategy.
        
        Nazwa katalogu zawiera: _xx_ (procent pustych), _yyy_ (ilość liter)
        """
        # Zaokrąglij procent do całkowitej liczby
        empty_percent_int = int(round(empty_percent))
        
        # Formatuj nazwy z metadanes
        empty_marker = f"_{empty_percent_int:02d}_"
        letter_marker = f"_{letter_count:03d}"
        
        # Prefiks pliku
        variant_prefix = f"{variant_num:03d}"
        
        # Print strategii
        print(f"  Wariant {variant_num}: {strategy_name} | "
              f"Puste: {empty_percent:.1f}% | Litery: {letter_count}")
        
        # PNG uzupełniona
        renderer = CrosswordImageRenderer(cell_size=40)
        img_filled = renderer.render(grid, filled=True)
        png_filled_name = f"{variant_prefix}{empty_marker}{letter_marker}_completed.png"
        png_filled_path = os.path.join(self.output_dir, png_filled_name)
        img_filled.save(png_filled_path, "PNG")
        
        # PNG pusta
        img_blank = renderer.render(grid, filled=False)
        png_blank_name = f"{variant_prefix}{empty_marker}{letter_marker}_blank.png"
        png_blank_path = os.path.join(self.output_dir, png_blank_name)
        img_blank.save(png_blank_path, "PNG")
        
        # TXT
        txt_name = f"{variant_prefix}{empty_marker}{letter_marker}.txt"
        txt_path = os.path.join(self.output_dir, txt_name)
        self._save_clues_txt(grid, txt_path)
        
        # XLSX (tylko dla wariantu 1)
        if variant_num == 1:
            xlsx_name = f"krizowka{empty_marker}{letter_marker}.xlsx"
            xlsx_path = os.path.join(self.output_dir, xlsx_name)
            exporter = ExcelExporter()
            exporter.export(grid, xlsx_path)
            
            # HTML (tylko dla wariantu 1)
            html_name = f"krizowka{empty_marker}{letter_marker}.html"
            html_path = os.path.join(self.output_dir, html_name)
            HTMLExporter.export(grid, html_path)
    
    def _export_variant(self, grid: CrosswordGrid, variant_num: int, width: int, height: int) -> None:
        """Eksportuj jeden wariant do wszystkich formatów (stare nazewnictwo)."""
        
        variant_prefix = f"{variant_num:03d}"
        
        # PNG krzyżówki - wersja uzupełniona (z literami)
        print(f"  Exportuję wariant {variant_num}: PNG (uzupełniona)...")
        renderer = CrosswordImageRenderer(cell_size=40)
        img_filled = renderer.render(grid, filled=True)
        png_filled_path = os.path.join(self.output_dir, f"{variant_prefix}_completed.png")
        img_filled.save(png_filled_path, "PNG")
        print(f"    {png_filled_path}")
        
        # PNG krzyżówki - wersja pusta (do wypełniania)
        print(f"  Exportuję wariant {variant_num}: PNG (pusta)...")
        img_blank = renderer.render(grid, filled=False)
        png_blank_path = os.path.join(self.output_dir, f"{variant_prefix}_blank.png")
        img_blank.save(png_blank_path, "PNG")
        print(f"    {png_blank_path}")
        
        # TXT z pytaniami
        print(f"  Exportuję wariant {variant_num}: TXT...")
        txt_path = os.path.join(self.output_dir, f"{variant_prefix}.txt")
        self._save_clues_txt(grid, txt_path)
        print(f"    {txt_path}")
        
        # XLSX (tylko dla pierwszego wariantu)
        if variant_num == 1:
            print(f"  Exportuję wariant {variant_num}: XLSX...")
            xlsx_path = os.path.join(self.output_dir, "krizowka.xlsx")
            exporter = ExcelExporter()
            exporter.export(grid, xlsx_path)
            print(f"    {xlsx_path}")
            
            # HTML (tylko dla pierwszego wariantu)
            print(f"  Exportuję wariant {variant_num}: HTML...")
            html_path = os.path.join(self.output_dir, "krizowka.html")
            HTMLExporter.export(grid, html_path)
            print(f"    {html_path}")
    
    def _save_clues_txt(self, grid: CrosswordGrid, filepath: str) -> None:
        """Zapisz pytania do pliku TXT (bez duplikatów)."""
        try:
            h_clues, v_clues = grid.get_clues_list()
            
            # Deduplikuj pytania (jeśli tego samego numeru pojawia się wiele razy)
            h_clues_unique = {}
            for num, clue, word in h_clues:
                if num not in h_clues_unique:
                    h_clues_unique[num] = (clue, word)
            
            v_clues_unique = {}
            for num, clue, word in v_clues:
                if num not in v_clues_unique:
                    v_clues_unique[num] = (clue, word)
            
            lines = []
            lines.append("KRZYŻÓWKA - PYTANIA")
            lines.append("=" * 60)
            lines.append("")
            lines.append("POZIOMO:")
            lines.append("-" * 60)
            
            for num in sorted(h_clues_unique.keys()):
                clue, word = h_clues_unique[num]
                lines.append(f"{num:2d}. {clue} ({len(word)} liter)")
            
            lines.append("")
            lines.append("PIONOWO:")
            lines.append("-" * 60)
            
            for num in sorted(v_clues_unique.keys()):
                clue, word = v_clues_unique[num]
                lines.append(f"{num:2d}. {clue} ({len(word)} liter)")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
        except Exception as e:
            print(f"[Orchestrator] BŁĄD zapisu TXT: {e}")
