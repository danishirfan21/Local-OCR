from PIL import Image, ImageDraw

from local_lens.routing.engine_router import choose_engine


def _screenshot_like_image():
    img = Image.new("RGB", (400, 300), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 60], fill=(60, 60, 60))
    return img


def test_routes_screenshot_to_easyocr_when_both_available():
    decision = choose_engine(_screenshot_like_image(), ["easyocr", "paddleocr"])
    assert decision.engine == "easyocr"
    assert decision.reason
    assert decision.input_type


def test_falls_back_and_explains_when_preferred_engine_unavailable():
    img = Image.new("RGB", (200, 200))
    import random

    random.seed(0)
    img.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                 for _ in range(200 * 200)])
    decision = choose_engine(img, ["easyocr"])
    assert decision.engine == "easyocr"
    assert "isn't installed" in decision.reason or decision.engine == "easyocr"


def test_raises_when_no_engines_available():
    try:
        choose_engine(_screenshot_like_image(), [])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_decision_always_has_a_reason_string():
    decision = choose_engine(_screenshot_like_image(), ["easyocr", "paddleocr"])
    assert isinstance(decision.reason, str)
    assert len(decision.reason) > 0
