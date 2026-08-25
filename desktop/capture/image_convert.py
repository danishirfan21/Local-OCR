"""QPixmap/QImage -> PNG bytes.

PNG (lossless) rather than JPEG -- OCR shouldn't see compression
artifacts. Deliberately produces the same `bytes` shape
OCRService.process() already accepts (MainWindow.open_image() reads a
file straight into bytes) rather than adding a second PIL/numpy-specific
OCR entry point -- one bytes-based interface for both Open Image and
Capture.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QPixmap


def qimage_to_png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def qpixmap_to_png_bytes(pixmap: QPixmap) -> bytes:
    return qimage_to_png_bytes(pixmap.toImage())
