#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from quote_engine import _extract_dimensions

# Use the actual OCR text from the user's output
test_text = """a ro) 'wal 4 + 4 A 4 > " " Ls ae FES &5 Q oP e (C) a wy rN : ~ : a, ~ —- - st 5 8 tb aS L an ie O 7 A mt a 18 26 Front view Scale: 1:1 Section view A-A Scale: 1:1 N 2 All practice drawings and video tutorials are available at WWW.CADDESIGNS.IN 0: 2° CAD DESIGNS DRAWING TITLE T— 1 oHECRED By PATE iz DRAWING NUMBER REV A4 EDST 1 X DESIGNED BY DATE pase PRE owe iiperorie ool ower D es eS A"""

print('Testing dimension extraction with actual OCR text...')
print(f'Text length: {len(test_text)}')
print(f'Text preview: {test_text[:200]}')
print()

result = _extract_dimensions(test_text)
print()
print('=== EXTRACTION RESULT ===')
print(f'Length: {result.get("length_in")}')
print(f'Width: {result.get("width_in")}')
print(f'Height: {result.get("height_in")}')

