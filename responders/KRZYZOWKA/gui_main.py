# -*- coding: utf-8 -*-
"""
gui_main.py — Główne GUI w PySide6 do generowania krzyżówek
"""

import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QMessageBox, QFileDialog, QTextEdit,
    QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from crossword_orchestrator import CrosswordOrchestrator


class GeneratorThread(QThread):
    """Wątek do generowania krzyżówek w tle."""
    
    finished = Signal(bool, str)  # success, message
    progress = Signal(str)        # progress message
    
    def __init__(self, orchestrator: CrosswordOrchestrator, width: int, height: int, 
                 source_file: str, word_file: str, num_variants: int, multi_strategy: bool = False):
        super().__init__()
        self.orchestrator = orchestrator
        self.width = width
        self.height = height
        self.source_file = source_file
        self.word_file = word_file
        self.num_variants = num_variants
        self.multi_strategy = multi_strategy
    
    def run(self):
        """Wykonaj generowanie."""
        try:
            self.progress.emit("Generowanie w toku...")
            success = self.orchestrator.generate_and_export(
                self.width,
                self.height,
                self.source_file,
                self.word_file if self.word_file else None,
                self.num_variants,
                multi_strategy=self.multi_strategy,
                progress_callback=self.progress.emit
            )
            
            if success:
                self.finished.emit(True, f"Krzyżówka wygenerowana! Wyniki w: {self.orchestrator.output_dir}")
            else:
                self.finished.emit(False, "Błąd podczas generowania")
                
        except Exception as e:
            self.finished.emit(False, f"Błąd: {str(e)}")


class CrosswordGeneratorGUI(QMainWindow):
    """Główne okno aplikacji."""
    
    def __init__(self):
        super().__init__()
        self.orchestrator = CrosswordOrchestrator(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.generator_thread = None
        
        # Domyślny plik
        self.default_word_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "baza.txt"
        )
        
        self.init_ui()
    
    def init_ui(self):
        """Inicjalizuj interfejs użytkownika."""
        self.setWindowTitle("Generator Krzyżówek")
        self.setGeometry(100, 100, 700, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout()
        
        # Tytuł
        title = QLabel("Generator Krzyżówek")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # --- Sekcja: Wymiary siatki ---
        layout.addSpacing(15)
        
        layout.addWidget(QLabel("Wymiary siatki:"))
        
        size_layout = QHBoxLayout()
        
        size_layout.addWidget(QLabel("Szerokość:"))
        self.width_spin = QSpinBox()
        self.width_spin.setValue(15)
        self.width_spin.setMinimum(5)
        self.width_spin.setMaximum(30)
        size_layout.addWidget(self.width_spin)
        
        size_layout.addSpacing(20)
        
        size_layout.addWidget(QLabel("Wysokość:"))
        self.height_spin = QSpinBox()
        self.height_spin.setValue(15)
        self.height_spin.setMinimum(5)
        self.height_spin.setMaximum(30)
        size_layout.addWidget(self.height_spin)
        
        size_layout.addStretch()
        
        layout.addLayout(size_layout)
        
        # --- Sekcja: Plik słów ---
        layout.addSpacing(15)
        
        layout.addWidget(QLabel("Źródło słów:"))
        
        file_layout = QHBoxLayout()
        
        self.file_label = QLineEdit()
        self.file_label.setReadOnly(True)
        # Domyślnie ustaw baza.txt
        self.file_label.setText(self.default_word_file)
        file_layout.addWidget(self.file_label)
        
        self.browse_btn = QPushButton("Przeglądaj...")
        self.browse_btn.clicked.connect(self.on_browse_file)
        file_layout.addWidget(self.browse_btn)
        
        layout.addLayout(file_layout)
        
        # --- Sekcja: Liczba wariantów ---
        layout.addSpacing(15)
        
        variants_layout = QHBoxLayout()
        variants_layout.addWidget(QLabel("Liczba wariantów:"))
        self.variants_spin = QSpinBox()
        self.variants_spin.setValue(3)
        self.variants_spin.setMinimum(1)
        self.variants_spin.setMaximum(10)
        variants_layout.addWidget(self.variants_spin)
        variants_layout.addStretch()
        layout.addLayout(variants_layout)
        
        # --- Sekcja: Multi-strategy checkbox ---
        layout.addSpacing(10)
        
        from PySide6.QtWidgets import QCheckBox
        
        self.multi_strategy_check = QCheckBox("Używać 6 strategii umieszczania wyrazów")
        self.multi_strategy_check.setChecked(False)
        self.multi_strategy_check.setToolTip(
            "Jeśli zaznaczone, program generuje krzyżówki 6 różnymi metodami:\n"
            "1. CENTERED - wyrazy od środka\n"
            "2. TOP_LEFT - z górnego lewego rogu\n"
            "3. TOP_CENTER - od góry pośrodku\n"
            "4. MIDDLE_LEFT - ze środka lewej krawędzi\n"
            "5. DENSE_MODE - maksymalna gęstość\n"
            "6. RANDOM - losowe umieszczenie"
        )
        layout.addWidget(self.multi_strategy_check)
        
        # --- Sekcja: Przycisk START ---
        layout.addSpacing(20)
        
        self.generate_btn = QPushButton("Generuj Krzyżówkę")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.generate_btn.clicked.connect(self.on_generate)
        layout.addWidget(self.generate_btn)
        
        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # --- Output text ---
        layout.addSpacing(15)
        
        layout.addWidget(QLabel("Log:"))
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(150)
        layout.addWidget(self.output_text)
        
        layout.addStretch()
        
        central.setLayout(layout)
    
    def on_browse_file(self):
        """Otwórz dialog do wyboru pliku."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik ze słowami",
            os.path.expanduser("~"),
            "Text Files (*.txt);;All Files (*)"
        )
        
        if filepath:
            self.file_label.setText(filepath)
    
    def on_generate(self):
        """Wciśnięto przycisk Generuj."""
        width = self.width_spin.value()
        height = self.height_spin.value()
        
        # Pobierz pełną ścieżkę pliku
        word_file = self.file_label.text()
        source_file = os.path.basename(word_file)  # Nazwa do katalogu wyników
        
        num_variants = self.variants_spin.value()
        multi_strategy = self.multi_strategy_check.isChecked()
        
        # Validacja
        if width < 5 or height < 5:
            QMessageBox.warning(self, "Błąd", "Wymiary muszą być co najmniej 5×5")
            return
        
        if not os.path.exists(word_file):
            QMessageBox.warning(self, "Błąd", f"Plik nie istnieje: {word_file}")
            return
        
        # Wyłącz przycisk i pokaż progress
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.output_text.clear()
        self.output_text.append("Generator Krzyżówek — Uruchomiony")
        self.output_text.append("-" * 60)
        
        if multi_strategy:
            self.output_text.append("Tryb: 6 STRATEGII")
            self.output_text.append("")
            self.output_text.append("Będą generowane krzyżówki z:") 
            self.output_text.append("1. CENTERED — wyrazy od środka")
            self.output_text.append("2. TOP_LEFT — z górnego lewego rogu")
            self.output_text.append("3. TOP_CENTER — od góry pośrodku")
            self.output_text.append("4. MIDDLE_LEFT — ze środka lewej krawędzi")
            self.output_text.append("5. DENSE_MODE — maksymalna gęstość")
            self.output_text.append("6. RANDOM — losowe umieszczenie")
            self.output_text.append("")
            self.output_text.append("Postęp:")
        else:
            self.output_text.append("Tryb: STANDARDOWY")
        
        # Uruchom w wątku
        self.generator_thread = GeneratorThread(
            self.orchestrator,
            width, height, source_file, word_file, num_variants,
            multi_strategy=multi_strategy
        )
        self.generator_thread.progress.connect(self.on_progress)
        self.generator_thread.finished.connect(self.on_finished)
        self.generator_thread.start()
    
    def on_progress(self, message: str):
        """Aktualizuj log progressu."""
        self.output_text.append(message)
    
    def on_finished(self, success: bool, message: str):
        """Generowanie skończone."""
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        self.output_text.append("")
        self.output_text.append(message)
        
        if success:
            QMessageBox.information(self, "Sukces", message)
        else:
            QMessageBox.critical(self, "Błąd", message)


def main():
    app = QApplication(sys.argv)
    window = CrosswordGeneratorGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
