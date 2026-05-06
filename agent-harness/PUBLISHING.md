# Publishing cli-anything-sumologic to PyPI

This document describes the exact steps to publish a new release to PyPI.

## Prerequisites

- Python 3.10+
- A PyPI account at https://pypi.org
- A PyPI API token (see "Setting up a PyPI API token" below)

## Setting Up a PyPI API Token

1. Log in to https://pypi.org
2. Go to Account Settings → API tokens → Add API token
3. Give it a name (e.g. `cli-anything-sumologic-publish`) and set scope to
   "Entire account" (or restrict to this project once it has been uploaded once)
4. Copy the token — it starts with `pypi-` and is shown only once
5. Store it in `~/.pypirc`:

```ini
[distutils]
index-servers = pypi

[pypi]
username = __token__
password = pypi-<your-token-here>
```

Or export it as an environment variable before running twine:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-<your-token-here>
```

## One-Time Setup: Install Build Tools

```bash
pip install build twine
```

## Building the Distribution

From the `agent-harness/` directory:

```bash
# Remove any stale artifacts
rm -rf dist/ build/

# Build sdist (tar.gz) and wheel (.whl)
python -m build
```

This produces:
- `dist/cli_anything_sumologic-1.0.0.tar.gz`   — source distribution
- `dist/cli_anything_sumologic-1.0.0-py3-none-any.whl` — universal wheel

## Verifying the Build (Optional but Recommended)

```bash
# Check the distributions for common packaging problems
twine check dist/*
```

All checks should pass with no errors before uploading.

## Test Upload to TestPyPI (Recommended for First Release)

```bash
twine upload --repository testpypi dist/*
```

Verify it installs correctly from TestPyPI:

```bash
pip install --index-url https://test.pypi.org/simple/ cli-anything-sumologic
cli-anything-sumologic --help
```

## Upload to PyPI (Production)

```bash
twine upload dist/*
```

After upload, the package is available at:
https://pypi.org/project/cli-anything-sumologic/

Users can then install it with:

```bash
pip install cli-anything-sumologic
```

## Bumping the Version for a New Release

1. Update `version` in `pyproject.toml`
2. Re-run the build steps above
3. Upload the new dist files with `twine upload dist/*`

The version string follows [PEP 440](https://peps.python.org/pep-0440/).
Use `1.0.1` for patches, `1.1.0` for minor features, `2.0.0` for breaking changes.

## Namespace Package Note

`cli_anything/` intentionally has **no `__init__.py`** — it is a PEP 420
implicit namespace package so that multiple `cli-anything-*` packages can
co-exist under the same `cli_anything` namespace when installed side-by-side.
Do not add an `__init__.py` to `cli_anything/`.
