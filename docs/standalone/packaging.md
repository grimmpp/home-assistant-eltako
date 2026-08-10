# The pip package of the standalone runtime

The [standalone runtime](readme.md) is published as a python package, so it can be used on a
laptop, a build server or a test bench without cloning this repository:

```bash
pip install eltako-enocean-tool
eet serve                          # or: eltako-enocean-tool serve
```

The Home Assistant integration is **not** installed this way - inside Home Assistant it is
installed by HACS, which copies `custom_components/eltako` into the config folder. The pip
package exists for the runtime which works without Home Assistant.

## The name

`eltako-enocean-tool` describes the program for somebody who does not use Home Assistant: a
tool for an ELTAKO/EnOcean installation. Inside this repository the same thing is called the
*standalone runtime*, because there the interesting part is that it runs without Home
Assistant - outside of it that says nothing.

"Tool" and not "manager" on purpose. The
[EnOcean Device Manager](https://github.com/grimmpp/enocean-device-manager) covers the same
ground with a desktop application and is maintained further; two names which cannot be
confused are worth more than a version relationship which has to be explained in every
issue. Nothing here claims to be its successor.

| | |
| --- | --- |
| distribution | `eltako-enocean-tool` (wheel: `eltako_enocean_tool-<version>-py3-none-any.whl`) |
| commands | `eet`, `eltako-enocean-tool` - the same entry point |
| import packages | `eltako_standalone`, `custom_components.eltako` |
| web ui / sidebar | **ELTAKO EnOcean Tool** (`PANEL_TITLE` in `const.py`) |

`eet` is the one to type. Three letters are cheap and taken elsewhere though - on linux
`/usr/bin/eet` belongs to the EFL data tool (debian package `libeet-bin`) - so the long name
is installed next to it and is what the documentation and the pipeline use where a collision
must not break anything.

The import package keeps its name: `eltako_standalone` says what the code is inside this
repository, it appears in `python -m eltako_standalone`, in the config folder and throughout
the documentation. A distribution name which differs from the import name is normal
(`pip install pillow` &rarr; `import PIL`).

## What is in the package

The standalone runtime *is* the integration: it imports `custom_components.eltako.*`
unchanged and only replaces the `homeassistant` package with a shim. So the wheel contains
two top level packages:

| in the wheel | what it is |
| --- | --- |
| `eltako_standalone/` | runtime, cli, web server, and `hass_shim/homeassistant` |
| `custom_components/eltako/` | the integration - the same code HACS installs |

Two details of that layout are deliberate ([`pyproject.toml`](../../pyproject.toml)):

* `custom_components` has **no `__init__.py`** and is therefore an implicit namespace
  package. An installed wheel merges with a `custom_components` folder which already exists
  somewhere else on `sys.path` instead of shadowing it.
* `eltako_standalone/hass_shim` has no `__init__.py` either, so the shim can only be reached
  through the `sys.path` insert of `runtime.install_shim()` - never as a top level
  `import homeassistant` which somebody did not ask for.

Everything the integration reads from disk at runtime (the web ui in `frontend/`,
`manifest.json`, `docs_index.json`, the translations, the Grafana dashboards) is package
data. A file which is not listed there is missing after `pip install` although it works in a
checkout, which is why `tests/test_metadata.py` and the smoke test of the pipeline check for
them explicitly.

Not in the package: the documentation, the dev container, the blueprints and the test suites.
`python -m eltako_standalone test` therefore reports its suites as unavailable when it runs
from an installed package - the tests live in the repository.

## Versions

One version for both, `2.2.0` is the integration **and** the package:

| where | why |
| --- | --- |
| `custom_components/eltako/manifest.json` | what Home Assistant and HACS read |
| `eltako_standalone/__init__.py` (`__version__`) | what the wheel is built from |

`pip install eltako-enocean-tool==2.2.0` has to give the integration of version 2.2.0, so both
are bumped together. `tests/test_metadata.py` fails if they drift apart, the pipeline checks
it again before it builds, and a release tag which does not belong to the version does not
get published.

## The pipeline

[`.github/workflows/build_package.yml`](../../.github/workflows/build_package.yml)

| job | when | what |
| --- | --- | --- |
| `build` | every push, pull request | version check, `python -m build`, `twine check --strict`, upload of `dist/` as a build artifact |
| `smoke-test` | after `build` | installs the built **wheel** in a clean environment on linux (3.12, 3.13, 3.14), windows and macos, then `eet --help`, the import of shim + integration, the presence of the web ui files, and a real boot: `eet --demo devices` with the bundled demo data |
| `publish` | a published GitHub release, or manually | upload to PyPI (or to TestPyPI for a dry run) |

The smoke test deliberately does **not** check out the repository: it has to work from the
wheel alone, exactly like on a machine which never saw this repository. It is also the reason
windows and macos are in the matrix - there the standalone runtime is the only way to reach a
USB gateway natively, so a package which is broken there is a broken feature.

### Releasing

1. Bump the version in `manifest.json` and in `eltako_standalone/__init__.py`, describe the
   release in `changes.md` (a test insists on the section).
2. Publish a **GitHub release** with the tag of this repository's usual shape,
   `v<version>-<what changed>`, e.g. `v2.2.0-standalone-package`. That is the same release
   HACS picks up.
3. The pipeline builds, smoke tests and uploads to PyPI.

A dry run before the first release: *Actions → Build python package → Run workflow →
publish to `testpypi`*, then

```bash
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ eltako-enocean-tool
```

(the extra index is needed because the dependencies are not on TestPyPI).

### Credentials

The publish job uses [trusted publishing](https://docs.pypi.org/trusted-publishers/): PyPI is
told once that `build_package.yml` of this repository may upload `eltako-enocean-tool`, and no
token is stored in GitHub at all. Alternatively set the repository secret `PYPI_API_TOKEN`
(or `TEST_PYPI_API_TOKEN`) - if it exists it is used instead.

Both paths run in a GitHub *environment* (`pypi` / `testpypi`), so a required reviewer can be
configured there if a release should not be able to leave the repository unnoticed.

## Building it locally

The same three commands the pipeline runs:

```bash
pip install build twine
python -m build                 # -> dist/eltako_enocean_tool-<version>-py3-none-any.whl
python -m twine check --strict dist/*
python -m zipfile -l dist/*.whl # what really ended up in it
```

And the way to try the result out without touching the current environment:

```bash
python -m venv /tmp/eltako && /tmp/eltako/bin/pip install dist/*.whl
/tmp/eltako/bin/eet --config /tmp/eltako-config --demo devices
```
