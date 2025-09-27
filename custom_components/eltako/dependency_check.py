"""Dependency management for Eltako integration."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

# Global flag to track dependency installation attempts
_DEPENDENCY_CHECK_DONE = False
_DEPENDENCIES_AVAILABLE = False


async def ensure_dependencies_installed(hass) -> bool:
    """Ensure Eltako dependencies are installed and available."""
    global _DEPENDENCY_CHECK_DONE, _DEPENDENCIES_AVAILABLE

    if _DEPENDENCY_CHECK_DONE:
        return _DEPENDENCIES_AVAILABLE

    _DEPENDENCY_CHECK_DONE = True

    # Try to import required dependencies
    try:
        import eltako14bus
        import enocean
        import strenum
        import esp2_gateway_adapter
        _DEPENDENCIES_AVAILABLE = True
        _LOGGER.info("All Eltako dependencies are available")
        return True
    except ImportError as e:
        _LOGGER.warning("Eltako dependencies not available, attempting installation: %s", e)

    # Get config directory path
    config_dir = Path(hass.config.config_dir)
    deps_dir = config_dir / "deps"

    # Read requirements from manifest
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        requirements = manifest.get("requirements", [])
    except Exception as e:
        _LOGGER.error("Failed to read manifest.json: %s", e)
        return False

    if not requirements:
        _LOGGER.warning("No requirements found in manifest.json")
        return False

    # Ensure deps directory exists
    deps_dir.mkdir(exist_ok=True)

    # Try multiple installation methods
    installation_success = False

    # Method 1: Try uv first (Home Assistant 2024.10+)
    if await _try_uv_install(requirements, deps_dir):
        installation_success = True
    # Method 2: Fall back to pip if uv fails
    elif await _try_pip_install(requirements, deps_dir):
        installation_success = True
    # Method 3: Try system pip as last resort
    elif await _try_system_pip_install(requirements):
        installation_success = True

    if installation_success:
        # Add deps directory to Python path
        if str(deps_dir) not in sys.path:
            sys.path.insert(0, str(deps_dir))

        # Try importing again
        try:
            import eltako14bus
            import enocean
            import strenum
            import esp2_gateway_adapter
            _DEPENDENCIES_AVAILABLE = True
            _LOGGER.info("Dependencies successfully installed and imported")
            return True
        except ImportError as e:
            _LOGGER.error("Dependencies installed but import still fails: %s", e)

    _LOGGER.error("Failed to install dependencies. Manual installation may be required.")
    return False


async def _try_uv_install(requirements: list[str], deps_dir: Path) -> bool:
    """Try installing with uv (Home Assistant 2024.10+)."""
    try:
        cmd = [
            "uv", "pip", "install", "--quiet", "--upgrade",
            "--target", str(deps_dir)
        ] + requirements

        # Set UV_CACHE_DIR to avoid permission issues
        env = os.environ.copy()
        env["UV_CACHE_DIR"] = str(deps_dir / ".uv-cache")

        _LOGGER.debug("Running uv install: %s", " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            _LOGGER.info("Successfully installed dependencies with uv")
            return True
        else:
            _LOGGER.warning("uv installation failed: %s", stderr.decode())
            return False

    except Exception as e:
        _LOGGER.warning("uv not available or failed: %s", e)
        return False


async def _try_pip_install(requirements: list[str], deps_dir: Path) -> bool:
    """Try installing with pip."""
    try:
        cmd = [
            sys.executable, "-m", "pip", "install", "--quiet", "--upgrade",
            "--target", str(deps_dir)
        ] + requirements

        _LOGGER.debug("Running pip install: %s", " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            _LOGGER.info("Successfully installed dependencies with pip")
            return True
        else:
            _LOGGER.warning("pip installation failed: %s", stderr.decode())
            return False

    except Exception as e:
        _LOGGER.warning("pip installation failed: %s", e)
        return False


async def _try_system_pip_install(requirements: list[str]) -> bool:
    """Try installing with system pip as last resort."""
    try:
        cmd = ["pip", "install", "--quiet", "--user"] + requirements

        _LOGGER.debug("Running system pip install: %s", " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            _LOGGER.info("Successfully installed dependencies with system pip")
            return True
        else:
            _LOGGER.warning("System pip installation failed: %s", stderr.decode())
            return False

    except Exception as e:
        _LOGGER.warning("System pip installation failed: %s", e)
        return False