from __future__ import annotations

from pathlib import Path

from opensquilla.gateway.config import GatewayConfig


def test_gateway_config_loads_knowledge_http_section(tmp_path: Path) -> None:
    path = tmp_path / "opensquilla.toml"
    path.write_text(
        "\n".join(
            [
                "[knowledge]",
                'backend = "http"',
                'endpoint = "http://127.0.0.1:18765"',
                "timeout_seconds = 12.5",
                'api_key_env = "OPENSQUILLA_KNOWLEDGE_API_KEY"',
            ]
        ),
        encoding="utf-8",
    )

    config = GatewayConfig.load_from_toml(path)

    assert config.knowledge.enabled is True
    assert config.knowledge.backend == "http"
    assert config.knowledge.endpoint == "http://127.0.0.1:18765"
    assert config.knowledge.timeout_seconds == 12.5
    assert config.knowledge.api_key_env == "OPENSQUILLA_KNOWLEDGE_API_KEY"
