"""Local Lens -- Streamlit UI.

This module owns the UI only: layout, session state, and Streamlit-specific
caching. All OCR/document-understanding logic lives in `local_lens/`, which
has no Streamlit dependency and can be reused by a future CLI/API/MCP
server or desktop shell.
"""

from __future__ import annotations

import io
import time

import streamlit as st
from PIL import Image, ImageDraw, ImageGrab
from streamlit_paste_button import paste_image_button as pbutton

from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE, PaddleOCREngine
from local_lens.export import to_json, to_markdown, to_txt
from local_lens.languages import DEFAULT_LANGUAGE, available_languages
from local_lens.models import DocumentResult
from local_lens.preprocessing.image import (
    PRESET_AUTO,
    PRESET_HIGH_CONTRAST,
    PRESET_NONE,
    apply_preset,
)
from local_lens.services.ocr_service import OCRService
from local_lens.utils.hashing import hash_image_bytes

# -----------------------------------------------------------------------------
# Engine registry
# -----------------------------------------------------------------------------
ENGINES = {
    "easyocr": ("EasyOCR", EasyOCREngine, True),
    "paddleocr": ("PaddleOCR", PaddleOCREngine, PADDLEOCR_AVAILABLE),
}

PREPROCESSING_LABELS = {
    PRESET_NONE: "None",
    PRESET_AUTO: "Auto",
    PRESET_HIGH_CONTRAST: "High contrast",
}

st.set_page_config(page_title="Local Lens", page_icon="🔍", layout="wide")


# -----------------------------------------------------------------------------
# Cached construction (model load happens once per config, not per rerun)
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _load_service(engine_key: str) -> OCRService:
    _, engine_cls, _ = ENGINES[engine_key]
    return OCRService(engine_cls())


@st.cache_data(show_spinner=False, ttl=3600)
def _run_ocr(
    image_bytes: bytes, engine_key: str, langs: tuple[str, ...], preprocessing: str
) -> DocumentResult:
    service = _load_service(engine_key)
    return service.process(image_bytes, list(langs), preprocessing)


def _render_overlay(image: Image.Image, result: DocumentResult) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for block in result.blocks:
        if block.bbox is None:
            continue
        box = [block.bbox.left, block.bbox.top, block.bbox.right, block.bbox.bottom]
        draw.rectangle(box, outline="#4ade80", width=2)
    return annotated


# -----------------------------------------------------------------------------
# Session state
# -----------------------------------------------------------------------------
_DEFAULTS = {
    "uploaded_bytes": None,
    "pasted_bytes": None,
    "clipboard_bytes": None,
    "last_clipboard_hash": None,
    "auto_detect": False,
}
for key, default in _DEFAULTS.items():
    st.session_state.setdefault(key, default)


# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🔍 Local Lens")
    st.caption("Private screenshot and document intelligence.")
    st.markdown("---")

    st.markdown("#### OCR Engine")
    engine_options = list(ENGINES.keys())
    engine_key = st.radio(
        "OCR Engine",
        options=engine_options,
        format_func=lambda k: ENGINES[k][0] + ("" if ENGINES[k][2] else " (not installed)"),
        index=0,
        label_visibility="collapsed",
    )
    if not ENGINES[engine_key][2]:
        st.warning(
            f"{ENGINES[engine_key][0]} is not installed. "
            "See README.md for setup, or pick a different engine."
        )

    st.markdown("#### Language")
    lang_options = available_languages()
    selected_langs = st.multiselect(
        "Language",
        options=[code for code, _ in lang_options],
        default=[DEFAULT_LANGUAGE],
        format_func=lambda code: dict(lang_options).get(code, code),
        label_visibility="collapsed",
    )
    if not selected_langs:
        selected_langs = [DEFAULT_LANGUAGE]

    st.markdown("#### Image preprocessing")
    preprocessing = st.radio(
        "Image preprocessing",
        options=list(PREPROCESSING_LABELS.keys()),
        format_func=lambda k: PREPROCESSING_LABELS[k],
        index=0,
        label_visibility="collapsed",
    )

    show_regions = st.toggle("Show detected regions", value=False)

    st.markdown("---")
    auto_detect = st.toggle(
        "🔄 Auto-watch clipboard",
        value=st.session_state.auto_detect,
        help="Copy an image or snip to clipboard and it will auto-appear here.",
    )
    st.session_state.auto_detect = auto_detect

    if auto_detect:
        st.info("Clipboard watcher is **ON**. Copy an image to trigger OCR.")
        try:
            clipboard_img = ImageGrab.grabclipboard()
            if isinstance(clipboard_img, Image.Image):
                buf = io.BytesIO()
                clipboard_img.convert("RGB").save(buf, format="PNG")
                clipboard_bytes = buf.getvalue()
                clip_hash = hash_image_bytes(clipboard_bytes)
                if clip_hash != st.session_state.last_clipboard_hash:
                    st.session_state.last_clipboard_hash = clip_hash
                    st.session_state.clipboard_bytes = clipboard_bytes
                    st.session_state.uploaded_bytes = None
                    st.session_state.pasted_bytes = None
                    st.toast("📋 New image detected from clipboard", icon="✅")
            # Non-image clipboard contents (text, files, empty) are silently
            # ignored rather than surfaced as an error -- that's expected,
            # not exceptional, when auto-watch is on.
        except Exception as exc:  # pragma: no cover - platform dependent
            st.warning(f"Clipboard access failed: {exc}")
    else:
        st.caption("Turn on clipboard watching to make it fully hands-free.")

# -----------------------------------------------------------------------------
# Hero
# -----------------------------------------------------------------------------
st.markdown("<h1 style='text-align:center;'>🔍 Local Lens</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center; color:#6b7280;'>Capture → Understand → Act. "
    "Private, local screenshot and document intelligence.</p>",
    unsafe_allow_html=True,
)
st.markdown("")

# -----------------------------------------------------------------------------
# Input
# -----------------------------------------------------------------------------
tab_upload, tab_paste = st.tabs(["📁 Upload", "📋 Paste"])

with tab_upload:
    uploaded_file = st.file_uploader(
        "Upload an image", type=["jpg", "jpeg", "png", "webp", "bmp", "tiff"]
    )
    if uploaded_file is not None:
        st.session_state.uploaded_bytes = uploaded_file.getvalue()
        st.session_state.pasted_bytes = None
        st.session_state.clipboard_bytes = None

with tab_paste:
    paste_result = pbutton(label="📋 Paste image (Ctrl+V)", key="local_lens_paste")
    if paste_result.image_data is not None:
        buf = io.BytesIO()
        paste_result.image_data.convert("RGB").save(buf, format="PNG")
        st.session_state.pasted_bytes = buf.getvalue()
        st.session_state.uploaded_bytes = None
        st.session_state.clipboard_bytes = None

image_bytes = (
    st.session_state.uploaded_bytes
    or st.session_state.pasted_bytes
    or st.session_state.clipboard_bytes
)

# -----------------------------------------------------------------------------
# Processing + results
# -----------------------------------------------------------------------------
if image_bytes is not None:
    if not ENGINES[engine_key][2]:
        st.error(f"{ENGINES[engine_key][0]} is not installed -- pick another engine.")
    else:
        try:
            with st.spinner("🔍 Reading text from image..."):
                result = _run_ocr(image_bytes, engine_key, tuple(selected_langs), preprocessing)
        except Exception as exc:
            st.error(f"OCR failed: {exc}")
            result = None

        if result is not None:
            st.markdown("---")

            content_type = result.metadata.get("content_type", "unknown")
            avg_conf = result.average_confidence

            m1, m2, m3 = st.columns(3)
            m1.metric("Words/lines detected", result.metadata.get("block_count", 0))
            m2.metric("Average confidence", f"{avg_conf * 100:.1f}%" if avg_conf else "N/A")
            m3.metric("Detected content", content_type.capitalize())

            img_col, text_col = st.columns([1, 1])

            with img_col:
                st.markdown("#### 🖼 Image")
                display_image = apply_preset(Image.open(io.BytesIO(image_bytes)), preprocessing)
                if show_regions:
                    display_image = _render_overlay(display_image, result)
                st.image(display_image, use_container_width=True)

            with text_col:
                st.markdown("#### 📝 Extracted text")
                if result.text.strip():
                    st.text_area(
                        "Extracted content",
                        result.text,
                        height=320,
                        label_visibility="collapsed",
                    )

                    # Contextual export actions based on detected content type.
                    st.markdown("##### Export")
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        label = "📥 Download Code" if content_type == "code" else "📥 Download TXT"
                        st.download_button(
                            label,
                            data=to_txt(result),
                            file_name="extracted_text.txt",
                            mime="text/plain",
                        )
                    with d2:
                        if content_type != "code":
                            st.download_button(
                                "📥 Download Markdown",
                                data=to_markdown(result),
                                file_name="extracted_text.md",
                                mime="text/markdown",
                            )
                    with d3:
                        # JSON is always offered regardless of content type --
                        # it's the structured backbone future Local Lens
                        # features (tables, formulas, schema extraction) build on.
                        st.download_button(
                                "📥 Download JSON",
                                data=to_json(result),
                                file_name="extracted_text.json",
                                mime="application/json",
                            )
                else:
                    st.info(
                        "No text detected.\n\n"
                        "Try:\n- A different preprocessing option\n"
                        "- A clearer screenshot\n- Zooming into the area with text"
                    )
else:
    st.info("Upload, paste, or copy a screenshot to get started.")

# -----------------------------------------------------------------------------
# Clipboard polling loop (Streamlit has no push-based clipboard API, so this
# reruns the script periodically while auto-watch is enabled)
# -----------------------------------------------------------------------------
if st.session_state.auto_detect:
    time.sleep(1)
    st.rerun()
