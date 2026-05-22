# -*- coding: utf-8 -*-
"""
html_exporter.py — Export krzyżówki do HTML5
Interaktywny format z CSS
"""

from typing import Optional
from .crossword_grid import CrosswordGrid


class HTMLExporter:
    """Eksportuje krzyżówkę do HTML5."""
    
    @staticmethod
    def export(grid: CrosswordGrid, filepath: str) -> bool:
        """
        Eksportuj krzyżówkę do HTML.
        
        Args:
            grid: Siatka krzyżówki
            filepath: Ścieżka do pliku wyjściowego
        
        Returns:
            True jeśli OK, False jeśli błąd
        """
        try:
            html_parts = []
            
            # Header
            html_parts.append("""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Krzyżówka</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            padding: 20px;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #222;
        }
        
        .content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 40px;
            margin-bottom: 40px;
        }
        
        .grid-section {
            display: flex;
            justify-content: center;
        }
        
        .grid {
            display: inline-block;
            border: 3px solid #000;
            background: white;
        }
        
        .grid-row {
            display: flex;
        }
        
        .cell {
            width: 40px;
            height: 40px;
            border: 2px solid #000;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 18px;
            position: relative;
            background-color: white;
        }
        
        .cell.black {
            background-color: #000;
            border: 1px solid #666;
        }
        
        .cell.empty {
            background-color: #f9f6f0;
        }
        
        .cell-clue {
            position: absolute;
            top: 2px;
            left: 3px;
            font-size: 9px;
            font-weight: bold;
            color: #c00;
            line-height: 1;
        }
        
        .clues-section {
            flex: 1;
        }
        
        .clues-section h2 {
            font-size: 16px;
            margin-bottom: 15px;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }
        
        .clue {
            margin-bottom: 8px;
            line-height: 1.4;
            font-size: 13px;
        }
        
        .clue-num {
            font-weight: bold;
            color: #c00;
            margin-right: 5px;
        }
        
        @media (max-width: 1000px) {
            .content {
                grid-template-columns: 1fr;
            }
        }
        
        footer {
            text-align: center;
            margin-top: 30px;
            font-size: 12px;
            color: #888;
            border-top: 1px solid #ddd;
            padding-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Krzyżówka</h1>
        
        <div class="content">
            <div class="grid-section">
                <div class="grid">
""")
            
            # Rysuj siatkę
            for r in range(grid.height):
                html_parts.append('                    <div class="grid-row">')
                for c in range(grid.width):
                    cell = grid.grid[r][c]
                    clue_num = grid.get_clue_number(r, c)
                    
                    if cell is None:
                        html_parts.append('                        <div class="cell black"></div>')
                    else:
                        cell_class = "cell"
                        if cell == "":
                            cell_class += " empty"
                        
                        letter = cell if cell != "" else ""
                        clue_marker = ""
                        
                        if clue_num is not None:
                            clue_marker = f'<span class="cell-clue">{clue_num}</span>'
                        
                        html_parts.append(f'                        <div class="{cell_class}">{clue_marker}{letter}</div>')
                
                html_parts.append('                    </div>')
            
            html_parts.append("""                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
""")
            
            # Pytania poziome
            html_parts.append('                <div class="clues-section">')
            html_parts.append('                    <h2>Poziomo</h2>')
            
            h_clues, v_clues = grid.get_clues_list()
            
            for num, clue, word in h_clues:
                html_parts.append(f'                    <div class="clue"><span class="clue-num">{num}.</span> {clue}</div>')
            
            html_parts.append('                </div>')
            
            # Pytania pionowe
            html_parts.append('                <div class="clues-section">')
            html_parts.append('                    <h2>Pionowo</h2>')
            
            for num, clue, word in v_clues:
                html_parts.append(f'                    <div class="clue"><span class="clue-num">{num}.</span> {clue}</div>')
            
            html_parts.append('                </div>')
            
            html_parts.append("""            </div>
        </div>
        
        <footer>
            Krzyżówka wygenerowana automatycznie
        </footer>
    </div>
</body>
</html>
""")
            
            # Zapisz
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(html_parts))
            
            print(f"[HTMLExporter] Zapisano: {filepath}")
            return True
            
        except Exception as e:
            print(f"[HTMLExporter] BŁĄD: {e}")
            return False
