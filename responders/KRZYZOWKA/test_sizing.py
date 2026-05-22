#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
test_sizing.py — Test generator with different grid sizes
"""

from crossword_orchestrator import CrosswordOrchestrator
import os

def test_size(width, height):
    """Test crossword generation with given size."""
    print(f"\n{'='*60}")
    print(f"Testing {width}x{height} grid...")
    print(f"{'='*60}")
    
    orchestrator = CrosswordOrchestrator(
        os.path.dirname(os.path.abspath(__file__))
    )
    
    # Test standard mode
    print(f"\n[Standard Mode]")
    success = orchestrator.generate_and_export(
        width=width,
        height=height,
        source_filename=f"test_{width}x{height}_std",
        word_file=os.path.join(os.path.dirname(__file__), "baza.txt"),
        num_variants=1,
        multi_strategy=False
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
    
    # Test multi-strategy mode
    print(f"\n[Multi-Strategy Mode (6 strategies)]")
    success = orchestrator.generate_and_export(
        width=width,
        height=height,
        source_filename=f"test_{width}x{height}_multi",
        word_file=os.path.join(os.path.dirname(__file__), "baza.txt"),
        num_variants=2,
        multi_strategy=True
    )
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")

# Test various sizes
sizes_to_test = [
    (5, 5),    # Small
    (7, 7),    # Medium-small
    (10, 10),  # Medium
    (15, 15),  # Default (should work)
    (20, 15),  # Larger rectangular
    (12, 18),  # Another rectangular
]

if __name__ == "__main__":
    print("Testing Crossword Generator with different sizes...")
    
    for width, height in sizes_to_test:
        try:
            test_size(width, height)
        except Exception as e:
            print(f"ERROR for {width}x{height}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("Testing complete!")
    print(f"{'='*60}")
