from PIL import Image, ImageDraw

from local_lens.input_analysis import INPUT_SCREENSHOT, INPUT_UNKNOWN, classify_input


def test_flat_ui_like_image_classified_as_screenshot():
    img = Image.new("RGB", (400, 300), (240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 380, 60], fill=(60, 60, 60))
    draw.rectangle([20, 80, 200, 100], fill=(30, 30, 30))
    input_type, confidence = classify_input(img)
    assert input_type == INPUT_SCREENSHOT
    assert confidence > 0


def test_solid_color_image_does_not_crash():
    img = Image.new("RGB", (100, 100), "white")
    input_type, confidence = classify_input(img)
    assert isinstance(input_type, str)
    assert 0.0 <= confidence <= 1.0


def test_random_noise_image_has_high_uniqueness():
    import random

    random.seed(0)
    img = Image.new("RGB", (200, 200))
    img.putdata([(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
                 for _ in range(200 * 200)])
    input_type, confidence = classify_input(img)
    # Not asserting a specific label (that's testing an unstable heuristic
    # exactly), just that noisy/high-variety input isn't mistaken for a
    # flat, low-variety screenshot.
    assert input_type != INPUT_SCREENSHOT


def test_result_is_always_a_valid_pair():
    img = Image.new("RGB", (50, 50), "blue")
    input_type, confidence = classify_input(img)
    assert input_type in {"screenshot", "photo", "document_scan", "unknown"}
    assert isinstance(confidence, float)
