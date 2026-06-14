"""Per-provider model resolution — regression guard for the cross-provider bug
where every provider got the Groq default model id."""
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
