"""Tests for GitHub OAuth client-id resolution (env var, .env, build-baked)."""

import os

from ambilight import paths
from ambilight.config import AppConfig
from ambilight.integrations.github.service import (
    BUILTIN_CLIENT_ID,
    GithubIntegration,
    resolve_client_id,
)


ENV_KEY = "AMBILIGHT_GITHUB_CLIENT_ID"


class FakeController:
    def flash(self, *a, **k):
        pass


def test_env_var_takes_precedence(monkeypatch):
    monkeypatch.setenv(ENV_KEY, "Iv1.envvalue")
    assert resolve_client_id() == "Iv1.envvalue"


def test_falls_back_to_builtin_default(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_KEY, raising=False)
    # No env, no baked file → the shipped built-in default is used so the
    # integration works out of the box.
    monkeypatch.setattr(paths, "resource_path", lambda name: str(tmp_path / name))
    assert BUILTIN_CLIENT_ID
    assert resolve_client_id() == BUILTIN_CLIENT_ID


def test_dotenv_is_loaded_into_environ(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_KEY, raising=False)
    (tmp_path / ".env").write_text(
        '# comment\nexport AMBILIGHT_GITHUB_CLIENT_ID="Iv1.fromdotenv"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "resource_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path)
    paths.load_env_files()
    assert os.environ.get(ENV_KEY) == "Iv1.fromdotenv"
    assert resolve_client_id() == "Iv1.fromdotenv"


def test_dotenv_never_overrides_real_env(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_KEY, "Iv1.real")
    (tmp_path / ".env").write_text("AMBILIGHT_GITHUB_CLIENT_ID=Iv1.dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "resource_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(paths, "user_data_dir", lambda: tmp_path)
    paths.load_env_files()
    assert os.environ.get(ENV_KEY) == "Iv1.real"   # not overridden


def test_config_client_id_overrides_resolver(monkeypatch):
    monkeypatch.setenv(ENV_KEY, "Iv1.fromenv")
    cfg = AppConfig()
    cfg.github.client_id = "Iv1.fromconfig"
    gi = GithubIntegration(cfg, FakeController(), loop=None)
    assert gi._client_id == "Iv1.fromconfig"   # config wins over env/baked
