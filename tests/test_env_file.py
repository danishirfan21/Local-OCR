"""Tests for the minimal .env loader: precedence (real env wins), parsing
edge cases, and that credential values are never surfaced through any
provider-status/error path -- only the boolean `configured` state. Every
test uses fake credential strings, never anything real, and creates its
own throwaway .env file under tmp_path (never touching the real project
.env)."""

from __future__ import annotations

import subprocess

from local_lens.deep_analysis.finalists import FINALISTS, credential_configured
from local_lens.env_file import load_env

# --- parsing + precedence --------------------------------------------------


def test_load_env_reads_missing_file_without_error(tmp_path):
    result = load_env(dotenv_path=tmp_path / "does-not-exist.env", env={})
    assert result == {}


def test_load_env_fills_in_values_from_file(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("LOCAL_LENS_BENCHMARK_GROQ_API_KEY=fake-groq-value\n", encoding="utf-8")

    result = load_env(dotenv_path=dotenv, env={})
    assert result["LOCAL_LENS_BENCHMARK_GROQ_API_KEY"] == "fake-groq-value"


def test_real_env_var_overrides_dotenv_value():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        dotenv = Path(d) / ".env"
        dotenv.write_text("LOCAL_LENS_BENCHMARK_GROQ_API_KEY=from-dotenv\n", encoding="utf-8")

        result = load_env(dotenv_path=dotenv, env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "from-real-env"})
        assert result["LOCAL_LENS_BENCHMARK_GROQ_API_KEY"] == "from-real-env"


def test_load_env_never_mutates_input_dict(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SOME_KEY=value\n", encoding="utf-8")

    original = {"OTHER_KEY": "x"}
    result = load_env(dotenv_path=dotenv, env=original)
    assert original == {"OTHER_KEY": "x"}  # unchanged
    assert result != original  # a new dict was returned


def test_load_env_ignores_comments_and_blank_lines(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# a comment\n\nLOCAL_LENS_BENCHMARK_GEMINI_API_KEY=fake-gemini-value\n   \n# trailing comment\n",
        encoding="utf-8",
    )
    result = load_env(dotenv_path=dotenv, env={})
    assert result["LOCAL_LENS_BENCHMARK_GEMINI_API_KEY"] == "fake-gemini-value"
    assert len(result) == 1


def test_load_env_strips_surrounding_quotes(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text('KEY_A="quoted-value"\nKEY_B=\'single-quoted\'\n', encoding="utf-8")
    result = load_env(dotenv_path=dotenv, env={})
    assert result["KEY_A"] == "quoted-value"
    assert result["KEY_B"] == "single-quoted"


def test_load_env_ignores_lines_without_equals(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("not a valid line\nVALID_KEY=value\n", encoding="utf-8")
    result = load_env(dotenv_path=dotenv, env={})
    assert result == {"VALID_KEY": "value"}


def test_absent_credential_remains_unconfigured(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SOME_UNRELATED_KEY=x\n", encoding="utf-8")
    result = load_env(dotenv_path=dotenv, env={})
    assert "LOCAL_LENS_BENCHMARK_GROQ_API_KEY" not in result


# --- integration with credential_configured() -----------------------------


def test_dotenv_credential_detected_via_credential_configured(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("LOCAL_LENS_BENCHMARK_GROQ_API_KEY=fake-value\n", encoding="utf-8")
    merged_env = load_env(dotenv_path=dotenv, env={})

    groq = next(fc for fc in FINALISTS if "Groq" in fc.label)
    assert credential_configured(groq, env=merged_env) is True


def test_real_env_overrides_dotenv_for_credential_configured(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("LOCAL_LENS_BENCHMARK_GROQ_API_KEY=changeme\n", encoding="utf-8")  # placeholder in file
    merged_env = load_env(dotenv_path=dotenv, env={"LOCAL_LENS_BENCHMARK_GROQ_API_KEY": "a-real-looking-value"})

    groq = next(fc for fc in FINALISTS if "Groq" in fc.label)
    assert credential_configured(groq, env=merged_env) is True
    assert merged_env["LOCAL_LENS_BENCHMARK_GROQ_API_KEY"] == "a-real-looking-value"


# --- secrets never surface through any status/error path -------------------


def test_provider_status_never_reveals_the_value(tmp_path, capsys):
    from local_lens.deep_analysis.runner import run_preflight

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "LOCAL_LENS_BENCHMARK_GROQ_API_KEY=totally-secret-fake-token-xyz\n"
        "LOCAL_LENS_BENCHMARK_GEMINI_API_KEY=another-secret-fake-token-abc\n",
        encoding="utf-8",
    )
    merged_env = load_env(dotenv_path=dotenv, env={})
    report = run_preflight(env=merged_env, round_name="free")

    # Serialize the whole report the way the CLI would print it and confirm
    # neither fake secret appears anywhere in that text.
    rendered = repr(report)
    assert "totally-secret-fake-token-xyz" not in rendered
    assert "another-secret-fake-token-abc" not in rendered
    for f in report.finalists:
        assert f.configured is True  # detected...
        # ...but nothing on the finalist carries the raw value
        assert "totally-secret-fake-token-xyz" not in repr(f)
        assert "another-secret-fake-token-abc" not in repr(f)


def test_load_env_error_paths_never_include_a_value(tmp_path):
    # A directory where a file is expected -- forces an OSError inside the
    # parser -- must not leak any path-adjacent content into an exception
    # message that could plausibly contain a fragment of a real .env.
    weird_path = tmp_path / "not_a_file_but_a_dir"
    weird_path.mkdir()
    result = load_env(dotenv_path=weird_path, env={})
    assert result == {}  # fails closed, no exception propagates


# --- .env stays out of git -------------------------------------------------


def _project_root():
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


def test_env_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=_project_root(), capture_output=True, text=True
    )
    assert result.returncode == 0, ".env must be gitignored -- git check-ignore should exit 0"


def test_env_example_has_no_real_looking_credential_values():
    content = (_project_root() / ".env.example").read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.endswith(("_API_KEY", "_TOKEN")):
            assert value.strip() == "", f".env.example must leave credential values empty, found: {line!r}"
