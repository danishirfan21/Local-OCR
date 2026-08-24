from local_lens.utils.hashing import hash_image_bytes


def test_same_bytes_same_hash():
    data = b"abc123" * 100
    assert hash_image_bytes(data) == hash_image_bytes(data)


def test_different_bytes_different_hash():
    assert hash_image_bytes(b"abc") != hash_image_bytes(b"xyz")


def test_hash_is_stable_hex_string():
    digest = hash_image_bytes(b"hello world")
    assert isinstance(digest, str)
    assert len(digest) == 32
    int(digest, 16)  # must be valid hex


def test_long_input_only_hashes_prefix_consistently():
    # Two inputs that differ only after the hash prefix window should hash
    # the same -- this documents the intentional prefix-only behavior.
    common_prefix = b"x" * 200_000
    a = common_prefix + b"AAAA"
    b = common_prefix + b"BBBB"
    assert hash_image_bytes(a) == hash_image_bytes(b)
