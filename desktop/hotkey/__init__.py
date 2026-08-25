"""Global hotkey subsystem: pure shortcut parsing (shortcut.py, cross-
platform, no ctypes) kept separate from the Windows-only native adapter
(win32_adapter.py, only imported when sys.platform == "win32") and the
platform-abstracted manager (manager.py) that ties them together. See
item 25/26 of the V6.2 task: keep Windows-specific code isolated and unit-
test the pure parsing/lifecycle logic without depending on a real
Windows message loop.
"""
