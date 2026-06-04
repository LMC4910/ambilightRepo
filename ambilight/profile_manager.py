"""
Profile Management Module
=========================
Manages saving, loading, listing, and applying configuration profiles.
Profiles are stored as JSON files in the `profiles` subdirectory.
"""

import json
import logging
import os
import dataclasses
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import AppConfig, ConfigManager
from . import paths

logger = logging.getLogger(__name__)


def _default_profiles_dir() -> Path:
    """Where profiles live by default.

    Installed (frozen) build: ``~/.ambilight/profiles`` (writable) — the install
    dir is read-only and the built-in profiles ship inside the bundle. Dev: the
    repo-relative ``profiles`` dir (existing behaviour, used by tests too).
    """
    if paths.is_frozen():
        return paths.user_data_dir() / "profiles"
    return Path("profiles")


class ProfileManager:
    """Manages Ambilight configuration profiles."""

    def __init__(self, profiles_dir: str | Path | None = None):
        if profiles_dir is None:
            profiles_dir = _default_profiles_dir()
        self.profiles_dir = Path(profiles_dir)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.active_profile: Optional[str] = None  # last successfully applied profile
        self._seed_builtins()

    def _seed_builtins(self) -> None:
        """Copy bundled built-in profiles into the (writable) profiles dir on
        first run, without overwriting any the user has since edited."""
        try:
            bundled = Path(paths.resource_path("profiles"))
            if not bundled.is_dir() or bundled.resolve() == self.profiles_dir.resolve():
                return
            import shutil
            for src in bundled.glob("*.json"):
                dest = self.profiles_dir / src.name
                if not dest.exists():
                    shutil.copyfile(src, dest)
        except Exception as exc:
            logger.warning("Could not seed built-in profiles: %s", exc)

    def list_profiles(self) -> List[str]:
        """Return a list of available profile names."""
        profiles = []
        for file in self.profiles_dir.glob("*.json"):
            profiles.append(file.stem)
        return sorted(profiles)

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the dictionary representation of a profile, or None if not found."""
        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read profile '{name}': {e}")
            return None

    def save_profile(self, name: str, config: Optional[AppConfig] = None) -> bool:
        """
        Save the given AppConfig as a named profile. 
        If config is None, saves the current global configuration.
        """
        if not name or ".." in name or "/" in name or "\\" in name:
            logger.error(f"Invalid profile name: {name}")
            return False

        if config is None:
            config = ConfigManager.get()

        path = self.profiles_dir / f"{name}.json"
        try:
            data = dataclasses.asdict(config)
            # auto_profile rules are a meta-setting, not a lighting profile — keep
            # them out so applying a profile never changes the switching rules.
            data.pop("auto_profile", None)
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved profile '{name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to save profile '{name}': {e}")
            return False

    def write_profile(self, name: str, data: Dict[str, Any]) -> bool:
        """
        Write an imported profile dict to disk under *name*.

        The data is round-tripped through :func:`_dict_to_dataclass` so an
        imported file is validated/normalised against ``AppConfig`` (unknown
        keys dropped) before being saved.
        """
        if not name or ".." in name or "/" in name or "\\" in name:
            logger.error(f"Invalid profile name: {name}")
            return False
        try:
            from .config import _dict_to_dataclass
            cfg = _dict_to_dataclass(AppConfig, data)
            if not isinstance(cfg, AppConfig):
                logger.error(f"Imported profile '{name}' is not a valid config.")
                return False
            return self.save_profile(name, cfg)
        except Exception as e:
            logger.error(f"Failed to import profile '{name}': {e}")
            return False

    def delete_profile(self, name: str) -> bool:
        """Delete a named profile."""
        path = self.profiles_dir / f"{name}.json"
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted profile '{name}'")
                return True
            except Exception as e:
                logger.error(f"Failed to delete profile '{name}': {e}")
                return False
        return False

    def apply_profile(self, name: str) -> bool:
        """Load a profile and apply it to the current configuration."""
        data = self.get_profile(name)
        if data is None:
            return False

        try:
            # Never let a profile overwrite the auto-switch rules (FR-PROF-07).
            data.pop("auto_profile", None)
            ConfigManager.update(data)
            self.active_profile = name
            logger.info(f"Applied profile '{name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to apply profile '{name}': {e}")
            return False

# Global singleton
profile_manager = ProfileManager()
