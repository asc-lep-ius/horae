import pytest
from pydantic import SecretStr, ValidationError

from horae.config import Settings


class TestSettingsDefaults:
    def test_defaults_with_required_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "testuser")
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "secret123")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.radicale_url == "http://localhost:5232"
        assert settings.radicale_username == "testuser"
        assert settings.default_calendar == "personal"
        assert settings.default_duration_minutes == 60
        assert settings.ollama_url == "http://localhost:11434"
        assert settings.ollama_model == "llama3.2"

    def test_custom_values_override_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "admin")
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "pw")
        monkeypatch.setenv("HORAE_RADICALE_URL", "https://cal.example.com")
        monkeypatch.setenv("HORAE_DEFAULT_CALENDAR", "work")
        monkeypatch.setenv("HORAE_DEFAULT_DURATION_MINUTES", "30")
        monkeypatch.setenv("HORAE_OLLAMA_URL", "http://gpu-server:11434")
        monkeypatch.setenv("HORAE_OLLAMA_MODEL", "mistral")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.radicale_url == "https://cal.example.com"
        assert settings.radicale_username == "admin"
        assert settings.default_calendar == "work"
        assert settings.default_duration_minutes == 30
        assert settings.ollama_url == "http://gpu-server:11434"
        assert settings.ollama_model == "mistral"


class TestSettingsRequired:
    def test_missing_username_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "secret")
        monkeypatch.delenv("HORAE_RADICALE_USERNAME", raising=False)

        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_missing_password_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "user")
        monkeypatch.delenv("HORAE_RADICALE_PASSWORD", raising=False)

        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]


class TestSettingsSecretStr:
    def test_password_is_secret_str(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "user")
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "super-secret")

        settings = Settings()  # type: ignore[call-arg]

        assert isinstance(settings.radicale_password, SecretStr)
        assert settings.radicale_password.get_secret_value() == "super-secret"

    def test_password_not_leaked_in_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "user")
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "super-secret")

        settings = Settings()  # type: ignore[call-arg]

        assert "super-secret" not in repr(settings)
        assert "super-secret" not in str(settings)


class TestSettingsEnvPrefix:
    def test_ignores_unprefixed_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RADICALE_USERNAME", "wrong")
        monkeypatch.setenv("HORAE_RADICALE_USERNAME", "correct")
        monkeypatch.setenv("HORAE_RADICALE_PASSWORD", "pw")

        settings = Settings()  # type: ignore[call-arg]

        assert settings.radicale_username == "correct"
