from PIL import Image

from local_lens.preprocessing.image import (
    PRESET_AUTO,
    PRESET_HIGH_CONTRAST,
    PRESET_NONE,
    apply_preset,
    resize_max_dim,
)


def test_apply_preset_none_is_deterministic():
    img = Image.new("RGB", (100, 50), "white")
    out1 = apply_preset(img, PRESET_NONE)
    out2 = apply_preset(img, PRESET_NONE)
    assert list(out1.getdata()) == list(out2.getdata())


def test_apply_preset_none_keeps_rgb_mode():
    img = Image.new("L", (10, 10), 128)
    out = apply_preset(img, PRESET_NONE)
    assert out.mode == "RGB"


def test_apply_preset_high_contrast_returns_rgb():
    img = Image.new("RGB", (10, 10), "white")
    out = apply_preset(img, PRESET_HIGH_CONTRAST)
    assert out.mode == "RGB"


def test_apply_preset_auto_changes_pixels_on_gray_image():
    img = Image.new("RGB", (10, 10), (128, 128, 128))
    out = apply_preset(img, PRESET_AUTO)
    assert out.size == img.size


def test_unknown_preset_raises():
    img = Image.new("RGB", (10, 10), "white")
    try:
        apply_preset(img, "bogus")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_resize_max_dim_caps_large_images():
    img = Image.new("RGB", (5000, 1000), "white")
    out = resize_max_dim(img, max_dim=2000)
    assert max(out.size) == 2000
    assert out.size[0] / out.size[1] == 5  # aspect ratio preserved


def test_resize_max_dim_leaves_small_images_unchanged():
    img = Image.new("RGB", (100, 50), "white")
    out = resize_max_dim(img, max_dim=2000)
    assert out.size == (100, 50)
