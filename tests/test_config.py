"""Per-provider model resolution — regression guard for the cross-provider bug
where every provider got the Groq default model id."""
import os

import config


def test_model_for_uses_provider_default(monkeypatch):
    monkeypatch.setitem(config.LLM, "model", None)  # no TA_LLM_MODEL override
    assert config.model_for("groq") == config.DEFAULT_MODELS["groq"]
    assert config.model_for("anthropic") == config.DEFAULT_MODELS["anthropic"]
    assert config.model_for("gemini") == config.DEFAULT_MODELS["gemini"]
    # The actual bug: anthropic must NOT inherit the Groq model id.
    assert config.model_for("anthropic") != config.DEFAULT_MODELS["groq"]


def test_model_for_respects_explicit_override(monkeypatch):
    monkeypatch.setitem(config.LLM, "model", "custom-model-x")
    assert config.model_for("anthropic") == "custom-model-x"
    assert config.model_for("groq") == "custom-model-x"


def test_dotenv_sets_missing_vars(tmp_path):
    env = tmp_path / ".env"
    env.write_text('FOO_KEY=abc123\n# a comment\nBAR_KEY="quoted val"\n\n')
    try:
        os.environ.pop("FOO_KEY", None)
        os.environ.pop("BAR_KEY", None)
        config._load_dotenv(str(env))
        assert os.environ["FOO_KEY"] == "abc123"
        assert os.environ["BAR_KEY"] == "quoted val"  # quotes stripped
    finally:
        os.environ.pop("FOO_KEY", None)
        os.environ.pop("BAR_KEY", None)


def test_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=fromfile\n")
    monkeypatch.setenv("FOO_KEY", "fromenv")  # real env wins
    config._load_dotenv(str(env))
    assert os.environ["FOO_KEY"] == "fromenv"


def test_dotenv_missing_file_is_noop():
    config._load_dotenv("/nonexistent/path/to/.env")  # must not raise
