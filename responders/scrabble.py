"""
responders/scrabble.py
Responder Scrabble — generuje krzyżówkę na podstawie słów z emaila,
przy użyciu silnika z katalogu KRZYZOWKA.
"""

import os
import io
import re
import base64
import csv
from flask import current_app

from core.html_builder import build_html_reply
from .KRZYZOWKA.crossword_new import CrosswordGeneratorNew
from .KRZYZOWKA.crossword_grid import CrosswordGrid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── Stałe wizualne (identyczne jak w grze Scrabble) ──────────────────────────
COLOR_BG = (10, 45, 10)
COLOR_BOARD = (34, 139, 34)
COLOR_GRID = (0, 100, 0)
COLOR_TILE = (245, 222, 179)
COLOR_TEXT = (40, 40, 40)

BOARD_DIM = 15

LETTERS_PTS = {
    "A": 1,
    "Ą": 5,
    "B": 3,
    "C": 2,
    "Ć": 6,
    "D": 2,
    "E": 1,
    "Ę": 5,
    "F": 5,
    "G": 3,
    "H": 3,
    "I": 1,
    "J": 3,
    "K": 2,
    "L": 2,
    "Ł": 3,
    "M": 2,
    "N": 1,
    "Ń": 7,
    "O": 1,
    "Ó": 5,
    "P": 2,
    "R": 1,
    "S": 1,
    "Ś": 5,
    "T": 2,
    "U": 3,
    "W": 1,
    "Y": 2,
    "Z": 1,
    "Ź": 9,
    "Ż": 5,
}

# Kandydaci na czcionkę (Linux Render + Windows lokalnie)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _load_premium_map() -> dict:
    """Wczytaj mapę premii z plansza.csv."""
    premium_map = {}
    path = os.path.join(DATA_DIR, "plansza.csv")
    if not os.path.exists(path):
        return premium_map
    try:
        with open(path, encoding="utf-8", newline="") as f:
            for r, row in enumerate(csv.reader(f)):
                if r >= BOARD_DIM:
                    break
                for c, val in enumerate(row[:BOARD_DIM]):
                    val = val.strip().upper()
                    if not val:
                        continue
                    try:
                        if val.endswith(("S", "W")):
                            premium_map[(r, c)] = ("S", int(val[:-1]), (200, 0, 0))
                        elif val.endswith("L"):
                            premium_map[(r, c)] = ("L", int(val[:-1]), (0, 0, 180))
                    except Exception:
                        pass
    except Exception as e:
        current_app.logger.warning("_load_premium_map error: %s", e)
    return premium_map


def _tile_value(ch: str) -> int:
    return LETTERS_PTS.get(ch.upper(), ord(ch) if ch else 0)


def _try_font(size: int):
    """Zwraca czcionkę TrueType lub domyślną Pillow."""
    from PIL import ImageFont

    for fp in FONT_CANDIDATES:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def render_scrabble_image(text: str) -> bytes:
    """
    Renderuje tekst jako PNG na planszy Scrabble.
    Każdy znak = jeden kafelek. Zwraca PNG jako bytes.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        current_app.logger.error("Pillow nie jest zainstalowane!")
        return b""

    tile_sz = 36
    gap = 2
    cell = tile_sz + gap
    margin = 14

    # Zawijanie tekstu do wierszy planszy
    chars = list(text)
    rows_chars = []
    while chars:
        rows_chars.append(chars[:BOARD_DIM])
        chars = chars[BOARD_DIM:]
    rows_chars = rows_chars[:BOARD_DIM]
    while len(rows_chars) < BOARD_DIM:
        rows_chars.append([])

    premium_map = _load_premium_map()

    img_w = 2 * margin + BOARD_DIM * cell
    img_h = 2 * margin + BOARD_DIM * cell
    img = Image.new("RGB", (img_w, img_h), COLOR_BG)
    draw = ImageDraw.Draw(img)

    font_letter = _try_font(int(tile_sz * 0.52))
    font_pts = _try_font(int(tile_sz * 0.24))
    font_prem = _try_font(int(tile_sz * 0.26))

    for r in range(BOARD_DIM):
        for c in range(BOARD_DIM):
            x = margin + c * cell
            y = margin + r * cell
            prem = premium_map.get((r, c))

            # Tło pola
            bg_col = prem[2] if prem else COLOR_BOARD
            draw.rectangle([x, y, x + tile_sz - 1, y + tile_sz - 1], fill=bg_col)
            draw.rectangle(
                [x, y, x + tile_sz - 1, y + tile_sz - 1], outline=COLOR_GRID, width=1
            )

            row_chars = rows_chars[r]
            ch = row_chars[c] if c < len(row_chars) else None

            if ch is not None and ch != " ":
                # Kafelek z literą
                draw.rectangle(
                    [x + 1, y + 1, x + tile_sz - 2, y + tile_sz - 2], fill=COLOR_TILE
                )
                draw.rectangle(
                    [x + 1, y + 1, x + tile_sz - 2, y + tile_sz - 2],
                    outline=(0, 0, 0),
                    width=1,
                )
                # Litera
                try:
                    bbox = font_letter.getbbox(ch)
                    lw = bbox[2] - bbox[0]
                    lx = x + (tile_sz - lw) // 2 - bbox[0]
                    ly = y + tile_sz // 10
                except Exception:
                    lx, ly = x + tile_sz // 4, y + tile_sz // 10
                draw.text((lx, ly), ch, font=font_letter, fill=COLOR_TEXT)

                # Wartość w prawym dolnym rogu
                val_str = str(_tile_value(ch))
                try:
                    vbbox = font_pts.getbbox(val_str)
                    vw = vbbox[2] - vbbox[0]
                    vh = vbbox[3] - vbbox[1]
                except Exception:
                    vw, vh = 8, 8
                draw.text(
                    (x + tile_sz - vw - 3, y + tile_sz - vh - 3),
                    val_str,
                    font=font_pts,
                    fill=COLOR_TEXT,
                )

            elif prem and ch is None:
                # Etykieta premii na pustym polu
                label = f"{prem[1]}{prem[0]}"
                try:
                    pbbox = font_prem.getbbox(label)
                    pw = pbbox[2] - pbbox[0]
                    ph = pbbox[3] - pbbox[1]
                except Exception:
                    pw, ph = tile_sz // 2, tile_sz // 2
                draw.text(
                    (x + (tile_sz - pw) // 2, y + (tile_sz - ph) // 2),
                    label,
                    font=font_prem,
                    fill=(255, 255, 255),
                )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _extract_email_words(body: str) -> list[str]:
    """Wyciągnij unikalne słowa z emaila, min. długość 3 znaki."""
    if not body:
        return []

    pattern = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{3,}")
    words = {match.group(0).upper() for match in pattern.finditer(body)}
    return sorted(words)


class EmailWordSource:
    """Źródło słów z treści emaila dla silnika krzyżówki."""

    def __init__(self, words: list[str]):
        self.words = {word: f"Słowo z wiadomości ({len(word)} liter)" for word in words}

    def get_word(self, word: str) -> str | None:
        return self.words.get(word.upper())

    def get_words_by_length(self, length: int) -> list[str]:
        return [word for word in self.words.keys() if len(word) == length]


def _generate_crossword_grid(
    words: list[str], width: int, height: int
) -> CrosswordGrid | None:
    if not words:
        return None

    source = EmailWordSource(words)
    generator = CrosswordGeneratorNew(source)
    try:
        return generator.generate(width, height, time_limit=4.0)
    except Exception as e:
        try:
            current_app.logger.warning("_generate_crossword_grid error: %s", e)
        except RuntimeError:
            print(f"_generate_crossword_grid error: {e}")
        return None


def _build_crossword_html(grid: CrosswordGrid) -> str:
    h_clues, v_clues = grid.get_clues_list()

    rows = [
        "<!DOCTYPE html>",
        '<html lang="pl">',
        "<head>",
        '    <meta charset="UTF-8">',
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "    <title>Krzyżówka</title>",
        "    <style>",
        "        body { margin: 0; padding: 20px; font-family: Arial, sans-serif; background-color: #f5f5f5; color: #333; }",
        "        .container { max-width: 1100px; margin: 0 auto; background-color: white; padding: 24px; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,0.08); }",
        "        h1 { text-align: center; margin-bottom: 24px; }",
        "        .content { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }",
        "        .grid { display: inline-block; border: 3px solid #000; background: #fff; }",
        "        .grid-row { display: flex; }",
        "        .cell { width: 36px; height: 36px; border: 1px solid #555; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 16px; position: relative; background: #f8eadf; }",
        "        .cell.black { background: #111; border-color: #222; }",
        "        .cell-clue { position: absolute; top: 2px; left: 2px; font-size: 10px; color: #c00; font-weight: 700; }",
        "        .clues { display: grid; gap: 20px; }",
        "        .clues h2 { margin-bottom: 12px; font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 6px; }",
        "        .clue { margin-bottom: 8px; line-height: 1.4; font-size: 14px; }",
        "        .clue-num { font-weight: 700; color: #c00; margin-right: 6px; }",
        "        @media (max-width: 900px) { .content { grid-template-columns: 1fr; } }",
        "    </style>",
        "</head>",
        "<body>",
        '    <div class="container">',
        "        <h1>Krzyżówka 15×15</h1>",
        '        <div class="content">',
        '            <div class="grid">',
    ]

    for row in range(grid.height):
        rows.append('                <div class="grid-row">')
        for col in range(grid.width):
            cell = grid.grid[row][col]
            clue_num = grid.get_clue_number(row, col)
            if cell is None:
                rows.append('                    <div class="cell black"></div>')
            else:
                clue = (
                    f'<span class="cell-clue">{clue_num}</span>'
                    if clue_num is not None
                    else ""
                )
                letter = cell if cell != "" else ""
                rows.append(
                    f'                    <div class="cell">{clue}{letter}</div>'
                )
        rows.append("                </div>")

    rows.extend(
        [
            "            </div>",
            '            <div class="clues">',
            "                <div>",
            "                    <h2>Poziomo</h2>",
        ]
    )

    for num, clue, _word in h_clues:
        rows.append(
            f'                    <div class="clue"><span class="clue-num">{num}.</span> {clue}</div>'
        )

    rows.extend(
        [
            "                </div>",
            "                <div>",
            "                    <h2>Pionowo</h2>",
        ]
    )

    for num, clue, _word in v_clues:
        rows.append(
            f'                    <div class="clue"><span class="clue-num">{num}.</span> {clue}</div>'
        )

    rows.extend(
        [
            "                </div>",
            "            </div>",
            "        </div>",
            "    </div>",
            "</body>",
            "</html>",
        ]
    )

    return "\n".join(rows)


def _render_crossword_grid_image(grid: CrosswordGrid) -> bytes:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        current_app.logger.error("Pillow nie jest zainstalowane!")
        return b""

    tile_sz = 36
    gap = 2
    cell = tile_sz + gap
    margin = 14

    img_w = 2 * margin + BOARD_DIM * cell
    img_h = 2 * margin + BOARD_DIM * cell
    img = Image.new("RGB", (img_w, img_h), COLOR_BG)
    draw = ImageDraw.Draw(img)

    font_letter = _try_font(int(tile_sz * 0.52))
    font_pts = _try_font(int(tile_sz * 0.24))

    for r in range(BOARD_DIM):
        for c in range(BOARD_DIM):
            x = margin + c * cell
            y = margin + r * cell
            cell_value = grid.grid[r][c]

            if cell_value is None:
                draw.rectangle(
                    [x, y, x + tile_sz - 1, y + tile_sz - 1], fill=(10, 10, 10)
                )
                draw.rectangle(
                    [x, y, x + tile_sz - 1, y + tile_sz - 1],
                    outline=COLOR_GRID,
                    width=1,
                )
                continue

            draw.rectangle([x, y, x + tile_sz - 1, y + tile_sz - 1], fill=COLOR_BOARD)
            draw.rectangle(
                [x, y, x + tile_sz - 1, y + tile_sz - 1], outline=COLOR_GRID, width=1
            )
            if cell_value != "":
                draw.rectangle(
                    [x + 1, y + 1, x + tile_sz - 2, y + tile_sz - 2], fill=COLOR_TILE
                )
                draw.rectangle(
                    [x + 1, y + 1, x + tile_sz - 2, y + tile_sz - 2],
                    outline=(0, 0, 0),
                    width=1,
                )

                try:
                    bbox = font_letter.getbbox(cell_value)
                    lw = bbox[2] - bbox[0]
                    lx = x + (tile_sz - lw) // 2 - bbox[0]
                    ly = y + tile_sz // 10
                except Exception:
                    lx, ly = x + tile_sz // 4, y + tile_sz // 10
                draw.text((lx, ly), cell_value, font=font_letter, fill=COLOR_TEXT)

                val_str = str(_tile_value(cell_value))
                try:
                    vbbox = font_pts.getbbox(val_str)
                    vw = vbbox[2] - vbbox[0]
                    vh = vbbox[3] - vbbox[1]
                except Exception:
                    vw, vh = 8, 8
                draw.text(
                    (x + tile_sz - vw - 3, y + tile_sz - vh - 3),
                    val_str,
                    font=font_pts,
                    fill=COLOR_TEXT,
                )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_scrabble_section(body: str) -> dict:
    """
    Buduje sekcję 'scrabble' odpowiedzi:
    - generuje krzyżówkę z wyrazów emaila
    - zwraca HTML do emaila oraz załącznik HTML z krzyżówką
    """
    words = _extract_email_words(body)
    if not words:
        reply_html = build_html_reply(
            "Nie znaleziono w treści emaila wystarczającej liczby wyrazów "
            "(min. 3 znaki). Krzyżówka nie została wygenerowana."
        )
        return {"reply_html": reply_html}

    grid = _generate_crossword_grid(words, BOARD_DIM, BOARD_DIM)
    if not grid:
        reply_html = build_html_reply(
            "Nie udało się wygenerować krzyżówki z przekazanych słów."
        )
        return {"reply_html": reply_html}

    png_bytes = _render_crossword_grid_image(grid)
    png_b64 = base64.b64encode(png_bytes).decode("ascii") if png_bytes else None
    image_dict = None
    if png_b64:
        image_dict = {
            "base64": png_b64,
            "content_type": "image/png",
            "filename": "scrabble_krzyzowka.png",
        }

    summary_text = (
        f"Krzyżówka 15×15 wygenerowana z {len(words)} unikalnych wyrazów "
        f"z Twojego emaila. W załączniku znajduje się plik PNG z gotową krzyżówką."
    )
    if png_b64:
        summary_text += (
            "<br><br>Podgląd krzyżówki: "
            f'<img src="data:image/png;base64,{png_b64}" '
            'alt="Krzyżówka" style="max-width:100%;height:auto;border:1px solid #ccc;border-radius:8px;"/>'
        )

    reply_html = build_html_reply(summary_text)

    result = {"reply_html": reply_html}
    if image_dict:
        result["image"] = image_dict
        result["images"] = [image_dict]

    return result
