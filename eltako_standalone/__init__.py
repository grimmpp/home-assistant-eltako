"""Standalone runtime for the Eltako integration - runs without Home Assistant.

See eltako_standalone/README.md.
"""

# Version of the pip package (see pyproject.toml). The wheel ships the integration itself,
# so this follows the version of custom_components/eltako/manifest.json - both are checked
# against each other in tests/test_metadata.py.
__version__ = "2.2.0rc1"
