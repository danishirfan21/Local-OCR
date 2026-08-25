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

from local_lens.backends import deep_backend_status, fast_backend_statuses, table_backend_status
from local_lens.deep_analysis.base import DeepAnalysisError
from local_lens.deep_analysis.config import build_deep_provider
from local_lens.engines.easyocr_engine import EasyOCREngine
from local_lens.engines.paddleocr_engine import PADDLEOCR_AVAILABLE, PaddleOCREngine
from local_lens.export import export_table_csv, export_table_markdown, to_json, to_markdown, to_txt
from local_lens.languages import DEFAULT_LANGUAGE, available_languages
from local_lens.models import DocumentResult
from local_lens.preprocessing.image import (
    PRESET_AUTO,
    PRESET_HIGH_CONTRAST,
    PRESET_NONE,
    apply_preset,
)
from local_lens.routing.engine_router import choose_engine
from local_lens.services.ocr_service import OCRService
from local_lens.tables.paddle_table_extractor import (
    TABLE_EXTRACTION_AVAILABLE,
    PaddleTableExtractor,
)
from local_lens.utils.hashing import hash_image_bytes

# -----------------------------------------------------------------------------
# Engine registry
# -----------------------------------------------------------------------------
ENGINES = {
    "easyocr": ("EasyOCR", EasyOCREngine, True),
    "paddleocr": ("PaddleOCR", PaddleOCREngine, PADDLEOCR_AVAILABLE),
}
AVAILABLE_ENGINE_KEYS = [k for k, (_, _, available) in ENGINES.items() if available]

PREPROCESSING_LABELS = {
    PRESET_NONE: "None",
    PRESET_AUTO: "Auto",
    PRESET_HIGH_CONTRAST: "High contrast",
}

st.set_page_config(page_title="Local Lens", page_icon="🔍", layout="wide")

st.markdown(
    """
    <style>
    .ll-rtl textarea { direction: rtl; text-align: right; }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Cached construction (model load happens once per config, not per rerun)
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _load_table_extractor():
    return PaddleTableExtractor() if TABLE_EXTRACTION_AVAILABLE else None


@st.cache_resource(show_spinner=False)
def _load_service(engine_key: str) -> OCRService:
    _, engine_cls, _ = ENGINES[engine_key]
    return OCRService(engine_cls(), table_extractor=_load_table_extractor())


@st.cache_resource(show_spinner=False)
def _load_deep_service() -> OCRService | None:
    provider = build_deep_provider()
    if provider is None:
        return None
    return OCRService(provider)


@st.cache_data(show_spinner=False, ttl=3600)
def _run_ocr(
    image_bytes: bytes, engine_key: str, langs: tuple[str, ...], preprocessing: str
) -> DocumentResult:
    service = _load_service(engine_key)
    return service.process(image_bytes, list(langs), preprocessing)


def _resolve_engine(engine_choice: str, image_bytes: bytes):
    """Return (engine_key, routing_reason | None) for the chosen sidebar option."""
    if engine_choice != "auto":
        return engine_choice, None
    image = Image.open(io.BytesIO(image_bytes))
    decision = choose_engine(image, AVAILABLE_ENGINE_KEYS)
    reason = f"{ENGINES[decision.engine][0]} -- {decision.reason} (input type: {decision.input_type}, confidence {decision.input_type_confidence:.2f})"
    return decision.engine, reason


def _render_overlay(image: Image.Image, result: DocumentResult) -> Image.Image:
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    for block in result.blocks:
        if block.bbox is None:
            continue
        box = [block.bbox.left, block.bbox.top, block.bbox.right, block.bbox.bottom]
        draw.rectangle(box, outline="#4ade80", width=2)
    for table in result.tables:
        if table.bbox is None:
            continue
        box = [table.bbox.left, table.bbox.top, table.bbox.right, table.bbox.bottom]
        draw.rectangle(box, outline="#3b82f6", width=3)
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

    st.markdown("#### Processing Mode")
    deep_status = deep_backend_status()
    mode_options = ["fast", "deep"]

    def _mode_label(k: str) -> str:
        if k == "fast":
            return "Fast -- runs entirely on this device"
        return "Deep Analyze -- uses your configured remote provider" + (
            "" if deep_status.available else " (not configured)"
        )

    processing_mode = st.radio(
        "Processing Mode",
        options=mode_options,
        format_func=_mode_label,
        index=0,
        label_visibility="collapsed",
    )
    if processing_mode == "deep":
        if deep_status.available:
            st.info(
                f"☁ Deep Analyze will send the selected image to **{deep_status.reason}**. "
                "Nothing is sent until you upload/paste an image with this mode selected."
            )
        else:
            st.warning(
                "Deep Analyze is not configured. Set `LOCAL_LENS_DEEP_BASE_URL` "
                "(bring your own endpoint/key) to enable it -- see README.md. "
                "Falling back to Fast mode."
            )

    with st.expander("Model availability"):
        for status in fast_backend_statuses():
            mark = "✓" if status.available else "○"
            st.caption(f"{mark} {status.name} -- {'available' if status.available else status.reason}")
        t_status = table_backend_status()
        mark = "✓" if t_status.available else "○"
        st.caption(f"{mark} table extraction -- {'available' if t_status.available else t_status.reason}")
        mark = "✓" if deep_status.available else "○"
        st.caption(f"{mark} Deep Analyze (remote) -- {'configured: ' + deep_status.reason if deep_status.available else deep_status.reason}")

    st.markdown("#### OCR Engine")
    st.caption("Applies to Fast mode only.")
    engine_choice_options = ["auto"] + list(ENGINES.keys())

    def _engine_label(k: str) -> str:
        if k == "auto":
            return "Auto (recommended)"
        name, _, available = ENGINES[k]
        return name + ("" if available else " (not installed)")

    engine_choice = st.radio(
        "OCR Engine",
        options=engine_choice_options,
        format_func=_engine_label,
        index=0,
        label_visibility="collapsed",
    )
    if engine_choice != "auto" and not ENGINES[engine_choice][2]:
        st.warning(
            f"{ENGINES[engine_choice][0]} is not installed. "
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
    result = None
    mode_used = "fast"
    engine_label_display = None
    routing_reason = None

    if processing_mode == "deep" and deep_status.available:
        deep_service = _load_deep_service()
        try:
            with st.spinner(f"☁ Sending image to {deep_status.reason}..."):
                result = deep_service.process(image_bytes, selected_langs, PRESET_NONE)
            mode_used = "deep"
            engine_label_display = deep_service.engine.name
        except DeepAnalysisError as exc:
            st.warning(f"Deep analysis failed: {exc}. Falling back to Fast OCR.")
        except Exception as exc:  # provider bugs must not crash the whole app
            st.warning(f"Deep analysis failed: {exc}. Falling back to Fast OCR.")

    if result is None:
        engine_key, routing_reason = _resolve_engine(engine_choice, image_bytes)

        if not ENGINES.get(engine_key, (None, None, False))[2]:
            st.error(f"{engine_key} is not installed -- pick another engine.")
        else:
            try:
                with st.spinner(f"🔍 Reading text from image ({ENGINES[engine_key][0]})..."):
                    result = _run_ocr(image_bytes, engine_key, tuple(selected_langs), preprocessing)
                engine_label_display = ENGINES[engine_key][0]
            except Exception as exc:
                st.error(f"OCR failed: {exc}")
                result = None

    if result is not None:
        st.markdown("---")

        content_type = result.metadata.get("content_type", "unknown")
        avg_conf = result.average_confidence
        is_urdu_primary = "ur" in result.detected_languages

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Words/lines detected", result.metadata.get("block_count", 0))
        m2.metric("Average confidence", f"{avg_conf * 100:.1f}%" if avg_conf else "N/A")
        label = "Table" if content_type == "table" else content_type.capitalize()
        if is_urdu_primary:
            label += " (Urdu)"
        m3.metric("Detected content", label)
        m4.metric("Total time", f"{result.metadata.get('total_ms', 0):.0f} ms")

        mode_label = "Deep Analyze (remote)" if mode_used == "deep" else "Fast (local)"
        st.caption(f"Detected: {label} · Engine: {engine_label_display} · Mode: {mode_label}")

        with st.expander("⚙️ Advanced details"):
            st.write(f"**Engine used:** {engine_label_display}")
            st.write(f"**Mode:** {mode_label}")
            if mode_used == "deep":
                st.write(f"**Provider:** {result.metadata.get('provider', 'unknown')} @ {result.metadata.get('base_url', 'unknown')}")
            if routing_reason:
                st.write(f"**Auto routing:** {routing_reason}")
            elif mode_used == "fast":
                st.write("**Auto routing:** not used (manual engine selection)")
            st.write(f"**Detected scripts:** {result.detected_scripts or 'none'}")
            st.write(f"**Detected languages:** {result.detected_languages or 'unresolved'}")
            st.write("**Stage timings (ms):**")
            st.json(result.metadata.get("timings", {}))

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
                text_area_class = "ll-rtl" if is_urdu_primary else ""
                if text_area_class:
                    st.markdown(f'<div class="{text_area_class}">', unsafe_allow_html=True)
                st.text_area(
                    "Extracted content",
                    result.text,
                    height=320,
                    label_visibility="collapsed",
                )
                if text_area_class:
                    st.markdown("</div>", unsafe_allow_html=True)

                # Contextual export actions based on detected content type.
                st.markdown("##### Export")
                if content_type == "code":
                    d1, d2 = st.columns(2)
                    with d1:
                        st.download_button(
                            "📥 Download Code (TXT)", data=to_txt(result),
                            file_name="extracted_code.txt", mime="text/plain",
                        )
                    with d2:
                        st.download_button(
                            "📥 Download JSON", data=to_json(result),
                            file_name="extracted_code.json", mime="application/json",
                        )
                elif content_type == "table" and result.tables:
                    table = result.tables[0]
                    st.dataframe(table.rows, use_container_width=True)
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        st.download_button(
                            "📥 Export CSV", data=export_table_csv(table),
                            file_name="table.csv", mime="text/csv",
                        )
                    with d2:
                        st.download_button(
                            "📥 Export Markdown", data=export_table_markdown(table),
                            file_name="table.md", mime="text/markdown",
                        )
                    with d3:
                        st.download_button(
                            "📥 Export JSON", data=to_json(result),
                            file_name="table.json", mime="application/json",
                        )
                else:
                    status = result.metadata.get("table_extraction_status")
                    if content_type == "table" and status and status != "ok":
                        st.caption(f"Table detected but extraction {status.replace('_', ' ')} -- showing plain text instead.")
                    d1, d2, d3 = st.columns(3)
                    with d1:
                        st.download_button(
                            "📥 Download TXT", data=to_txt(result),
                            file_name="extracted_text.txt", mime="text/plain",
                        )
                    with d2:
                        st.download_button(
                            "📥 Download Markdown", data=to_markdown(result),
                            file_name="extracted_text.md", mime="text/markdown",
                        )
                    with d3:
                        st.download_button(
                            "📥 Download JSON", data=to_json(result),
                            file_name="extracted_text.json", mime="application/json",
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
