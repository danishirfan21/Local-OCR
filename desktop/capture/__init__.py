"""Screenshot region-selection capture (V6.3).

geometry.py is pure coordinate math (no Qt widgets, no Windows API) --
unit-tested directly. screen_capture.py and overlay.py are Qt-only, no
external dependency (QScreen.grabWindow proved sufficient -- see
docs/V6_3_CAPTURE.md for why `mss` wasn't needed). controller.py wires
capture into the app's existing OCR worker.
"""
