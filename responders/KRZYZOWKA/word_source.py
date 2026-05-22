# -*- coding: utf-8 -*-
"""
word_source.py — Obsługa źródła słów do krzyżówek
Wczytuje słowa z pliku tekstowego (domyślnie dane.txt)
Format: WYRAZ definicja/podpowiedź
"""

from typing import List, Dict, Tuple, Optional
import os


class WordSource:
    """Zarządza źródłem słów do generowania krzyżówek."""
    
    def __init__(self, filepath: Optional[str] = None):
        """
        Inicjalizuje źródło słów.
        
        Args:
            filepath: Ścieżka do pliku z wyrazami. 
                     Jeśli None, użyj dane.txt w tym samym katalogu co skrypt.
        """
        if filepath is None:
            # Domyślna baza w katalogu projektu
            script_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(script_dir)
            filepath = os.path.join(parent_dir, "dane.txt")
        
        self.filepath = filepath
        self.words: Dict[str, str] = {}  # {word: definition}
        self.loaded = False
        
        # Spróbuj załadować — jeśli nie istnieje dane.txt, użyj baza.txt
        if not os.path.exists(filepath):
            alt_filepath = os.path.join(os.path.dirname(filepath), "baza.txt")
            if os.path.exists(alt_filepath):
                self.filepath = alt_filepath
        
        self.load()
    
    def load(self) -> bool:
        """Wczytaj słowa z pliku.
        
        Format pliku: każda linia to "WYRAZ definicja" (oddzielone spacją)
        
        Returns:
            True jeśli OK, False jeśli błąd
        """
        if not os.path.exists(self.filepath):
            print(f"[WordSource] BŁĄD: Plik nie istnieje: {self.filepath}")
            self.loaded = False
            return False
        
        try:
            self.words = {}
            with open(self.filepath, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split(None, 1)  # Podziel na pierwszy token (wyraz) i reszta
                    if len(parts) < 2:
                        print(f"[WordSource] Ostrzeżenie linia {line_num}: Brak definicji dla '{parts[0]}'")
                        if len(parts) == 1:
                            self.words[parts[0].upper()] = ""
                        continue
                    
                    word, definition = parts[0].upper(), parts[1]
                    
                    # Walidacja: tylko litery polskie
                    if not all(c.isalpha() or c in 'ĄĆĘŁŃÓŚŹŻ' for c in word):
                        print(f"[WordSource] Ostrzeżenie linia {line_num}: Wyraz 'r{word}' zawiera znaki niepolskie")
                        continue
                    
                    self.words[word] = definition
            
            self.loaded = True
            print(f"[WordSource] Załadowano {len(self.words)} słów z {self.filepath}")
            return True
            
        except Exception as e:
            print(f"[WordSource] BŁĄD ładowania: {e}")
            self.loaded = False
            return False
    
    def get_word(self, word: str) -> Optional[str]:
        """Pobierz definicję słowa (bez rozróżniania wielkości liter)."""
        return self.words.get(word.upper())
    
    def get_all_words(self) -> List[str]:
        """Zwróć listę wszystkich słów."""
        return list(self.words.keys())
    
    def get_words_by_length(self, length: int) -> List[str]:
        """Zwróć listę słów o danej długości."""
        return [w for w in self.words.keys() if len(w) == length]
    
    def is_valid(self, word: str) -> bool:
        """Sprawdź czy wyraz istnieje w bazie."""
        return word.upper() in self.words
    
    def get_stats(self) -> str:
        """Zwróć statystyki bazy słów."""
        if not self.loaded:
            return "Baza nie załadowana"
        
        by_length = {}
        for word in self.words.keys():
            l = len(word)
            by_length[l] = by_length.get(l, 0) + 1
        
        rows = [f"Plik: {self.filepath}"]
        rows.append(f"Razem słów: {len(self.words)}")
        rows.append("Rozkład długości:")
        for length in sorted(by_length.keys()):
            count = by_length[length]
            rows.append(f"  {length:2d} liter: {count:4d} słów")
        
        return "\n".join(rows)
