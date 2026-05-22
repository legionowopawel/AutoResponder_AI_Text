# -*- coding: utf-8 -*-
"""
image_renderer.py — Renderowanie krzyżówki do PNG
Grafika oparta na estetyce gry Scrabble
"""

from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
from .crossword_grid import CrosswordGrid, Direction


# Kolory ze Scrabble
COLOR_TILE = (245, 222, 179)      # Beżowy
COLOR_BORDER = (0, 0, 0)           # Czarny
COLOR_TEXT = (40, 40, 40)          # Szary-czarny
COLOR_CLUE_NUM = (200, 0, 0)       # Czerwony dla numeru pytania
COLOR_EMPTY = (220, 220, 220)      # Jasno szary dla pustych komórek


class CrosswordImageRenderer:
    """Renderer krzyżówki do pliku PNG."""
    
    def __init__(self, cell_size: int = 40, font_size: int = 24):
        """
        Args:
            cell_size: Rozmiar jednej komórki w pikselach
            font_size: Rozmiar czcionki
        """
        self.cell_size = cell_size
        self.font_size = font_size
        self.margin = 40
        
        # Spróbuj załadować czcionkę
        self.font_main = self._load_font(font_size)
        self.font_clue = self._load_font(max(8, font_size // 2))
    
    def _load_font(self, size: int) -> ImageFont.FreeTypeFont:
        """Załaduj czcionkę TrueType."""
        # Nazwy czcionek do spróbowania (Windows)
        candidates = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\calibri.ttf",
            "C:\\Windows\\Fonts\\times.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        
        for font_path in candidates:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
        
        # Fallback: domyślna czcionka PIL
        return ImageFont.load_default()
    
    def render(self, grid: CrosswordGrid, filled: bool = True) -> Image.Image:
        """
        Renderuj siatkę krzyżówki do obrazu PIL.
        
        Args:
            grid: Siatka krzyżówki
            filled: True = uzupełniona (z literami), False = pusta (do wypełniania)
        
        Returns:
            Obiekt Image
        """
        width_px = grid.width * self.cell_size + 2 * self.margin
        height_px = grid.height * self.cell_size + 2 * self.margin
        
        # Stwórz obraz
        img = Image.new('RGB', (width_px, height_px), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Rysuj siatkę
        for r in range(grid.height):
            for c in range(grid.width):
                x0 = self.margin + c * self.cell_size
                y0 = self.margin + r * self.cell_size
                x1 = x0 + self.cell_size
                y1 = y0 + self.cell_size
                
                cell = grid.grid[r][c]
                
                # Kolor tła komórki
                if cell is None:
                    # Czarna komórka (niedostępna)
                    fill_color = (0, 0, 0)
                else:
                    # Biała = pusta, beżowa = do wypełnienia, lub zawiera literę
                    fill_color = COLOR_TILE if cell == "" else COLOR_TILE
                
                # Rysuj prostokąt
                draw.rectangle([x0, y0, x1, y1], fill=fill_color, outline=COLOR_BORDER, width=2)
                
                # Jeśli to wersja uzupełniona (filled) i jest litera, rysuj ją WYCENTROWANĄ
                if filled and cell and cell != "":
                    # Wycentruj literę idealne w środku komórki
                    cell_center_x = x0 + self.cell_size / 2
                    cell_center_y = y0 + self.cell_size / 2
                    draw.text(
                        (cell_center_x, cell_center_y),
                        cell,
                        fill=COLOR_TEXT,
                        font=self.font_main,
                        anchor="mm"  # mm = middle, middle
                    )
                
                # Jeśli ta komórka ma numer pytania, rysuj go w lewym górnym rogu
                clue_num = grid.get_clue_number(r, c)
                if clue_num is not None and cell is not None:
                    num_text = str(clue_num)
                    draw.text(
                        (x0 + 4, y0 + 2),
                        num_text,
                        fill=COLOR_CLUE_NUM,
                        font=self.font_clue
                    )
        
        return img
    
    def render_with_clues(self, grid: CrosswordGrid, filled: bool = True) -> Image.Image:
        """
        Renderuj krzyżówkę wraz z pytaniami poniżej.
        
        Args:
            grid: Siatka krzyżówki
            filled: True = uzupełniona, False = pusta
        
        Returns:
            Obraz zawierający siatkę krzyżówki i pytania
        """
        # Renderuj siatkę
        grid_img = self.render(grid, filled=filled)
        
        # Pobierz pytania
        h_clues, v_clues = grid.get_clues_list()
        
        # Oblicz wysokość sekcji pytań
        clues_height = max(len(h_clues), len(v_clues)) * 30 + 100
        
        # Stwórz większy obraz
        total_height = grid_img.height + clues_height
        final_img = Image.new('RGB', (grid_img.width, total_height), color=(255, 255, 255))
        
        # Wklej siatkę
        final_img.paste(grid_img, (0, 0))
        
        # Rysuj pytania
        draw = ImageDraw.Draw(final_img)
        
        y = grid_img.height + 20
        
        # Pytania poziome
        draw.text(
            (20, y),
            "POZIOMO:",
            fill=COLOR_TEXT,
            font=self.font_main
        )
        y += 40
        
        for num, clue, word in h_clues[:20]:  # Maksymalnie 20 pytań
            text = f"{num}. {clue}"
            draw.text(
                (40, y),
                text,
                fill=COLOR_TEXT,
                font=self.font_clue
            )
            y += 25
        
        # Pytania pionowe
        y += 20
        draw.text(
            (grid_img.width // 2 + 20, grid_img.height + 40 + max(len(h_clues), 2) * 25),
            "PIONOWO:",
            fill=COLOR_TEXT,
            font=self.font_main
        )
        
        y = grid_img.height + 40 + max(len(h_clues), 2) * 25 + 40
        
        for num, clue, word in v_clues[:20]:
            text = f"{num}. {clue}"
            draw.text(
                (grid_img.width // 2 + 40, y),
                text,
                fill=COLOR_TEXT,
                font=self.font_clue
            )
            y += 25
        
        return final_img
