import unicodedata

from local_lens.text_normalization import normalize_urdu_text


def test_strips_bidi_control_characters():
    text = "‏سلام‎ دنیا‬"
    result = normalize_urdu_text(text)
    for cp in (0x200E, 0x200F, 0x202C):
        assert chr(cp) not in result


def test_applies_nfc_normalization():
    decomposed = unicodedata.normalize("NFD", "café")
    assert decomposed != unicodedata.normalize("NFC", decomposed)  # sanity check
    result = normalize_urdu_text(decomposed)
    assert result == unicodedata.normalize("NFC", decomposed)


def test_leaves_plain_text_unchanged():
    assert normalize_urdu_text("Hello World") == "Hello World"


def test_leaves_arabic_indic_digits_unchanged():
    # These are legitimate content, not noise -- must not be touched.
    text = "١٢٣"
    assert normalize_urdu_text(text) == text


def test_empty_string():
    assert normalize_urdu_text("") == ""
