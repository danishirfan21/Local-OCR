from local_lens.scripts import SCRIPT_ARABIC, SCRIPT_LATIN, detect_scripts, infer_languages


def test_pure_latin_text():
    assert detect_scripts("Hello World") == [SCRIPT_LATIN]


def test_pure_arabic_script_text():
    assert detect_scripts("سلام دنیا") == [SCRIPT_ARABIC]


def test_mixed_script_text_preserves_first_seen_order():
    assert detect_scripts("Order نمبر 12345 confirmed") == [SCRIPT_LATIN, SCRIPT_ARABIC]


def test_digits_and_punctuation_only_has_no_script():
    assert detect_scripts("12345 !@#$%") == []


def test_empty_string_has_no_script():
    assert detect_scripts("") == []


def test_infer_languages_requires_both_script_and_selection():
    # Arabic script detected, but user only selected English -- no claim made.
    assert infer_languages([SCRIPT_ARABIC], ["en"]) == []


def test_infer_languages_matches_when_both_present():
    assert infer_languages([SCRIPT_LATIN, SCRIPT_ARABIC], ["en", "ur"]) == ["en", "ur"]


def test_infer_languages_empty_scripts_returns_empty():
    assert infer_languages([], ["en", "ur"]) == []
