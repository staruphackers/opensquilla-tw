from __future__ import annotations

from opensquilla.safety.secret_redaction import redact_secret_text, redact_secret_value


def test_redact_secret_text_masks_env_assignments_and_provider_keys() -> None:
    text = (
        "env.OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz "
        "DASHSCOPE_API_KEY:sk-123456789012345678901234 "
        "Authorization: Bearer secret-token"
    )

    redacted = redact_secret_text(text)

    assert "sk-or-v1-abcdefghijklmnopqrstuvwxyz" not in redacted
    assert "sk-123456789012345678901234" not in redacted
    assert "secret-token" not in redacted
    assert "env.OPENROUTER_API_KEY=[REDACTED]" in redacted
    assert "DASHSCOPE_API_KEY:[REDACTED]" in redacted
    assert "Authorization: Bearer [REDACTED]" in redacted


def test_redact_secret_text_does_not_mask_token_counters() -> None:
    assert redact_secret_text("total_tokens=123 cached_tokens:100") == (
        "total_tokens=123 cached_tokens:100"
    )


def test_redact_secret_value_masks_secret_keys_and_nested_strings() -> None:
    payload = {
        "api_key": "plain-secret",
        "messages": [
            {
                "content": "debug env.OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz"
            }
        ],
    }

    redacted = redact_secret_value(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert "sk-or-v1-abcdefghijklmnopqrstuvwxyz" not in str(redacted)
