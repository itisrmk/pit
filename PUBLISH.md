# Publishing PIT to PyPI

This document contains instructions for publishing the `prompt-pit` package to PyPI.

## Package Information

- **PyPI Package Name:** `prompt-pit`
- **CLI Command:** `pit` (unchanged)
- **Import Name:** `pit` (unchanged)

## Prerequisites

Ensure you have the required tools installed:

```bash
pip install build twine
```

## Build Steps

### 1. Clean Previous Builds

```bash
cd /Users/rahulkashyap/.openclaw/workspace/pit
rm -rf dist/ build/ *.egg-info
```

### 2. Build the Package

```bash
python -m build
```

This will create:
- `dist/prompt-pit-<version>.tar.gz` (source distribution)
- `dist/prompt_pit-<version>-py3-none-any.whl` (wheel)

### 3. Verify the Build

```bash
twine check dist/*
```

## Test Publishing (TestPyPI)

Before publishing to the main PyPI, test on TestPyPI:

```bash
twine upload --repository testpypi dist/*
```

Then test the installation:

```bash
# Create a fresh virtual environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ prompt-pit

# Verify CLI works
pit --version
pit --help
```

## Publish to PyPI

Once testing is complete:

```bash
twine upload dist/*
```

You will be prompted for your PyPI credentials (or use API tokens).

## Post-Publish Verification

After publishing, verify the package is available:

```bash
# Install from PyPI
pip install prompt-pit

# Test the CLI
pit --version
pit --help
pit init
```

## Version Updates

When releasing a new version:

1. Update the version in `pyproject.toml`:
   ```toml
   [project]
   version = "0.2.0"  # Update this
   ```

2. Update the version badge in `README.md` if applicable

3. Create a git tag:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. Build and publish following the steps above

## Troubleshooting

### Package name already exists
If `prompt-pit` is taken, consider alternatives like:
- `prompt-pit-cli`
- `pit-prompt-vc`
- `pit-version-control`

### Import errors after installation
Ensure the package structure is correct:
- The `pit/` directory should be at the root
- `pit/__init__.py` should exist
- `pit/cli/main.py` should contain the `app` entry point

### CLI command not found
The `[project.scripts]` section in `pyproject.toml` defines the CLI entry point:
```toml
[project.scripts]
pit = "pit.cli.main:app"
```

After installation, `pit` should be available in your PATH.

## Resources

- [PyPI](https://pypi.org/)
- [TestPyPI](https://test.pypi.org/)
- [Python Packaging User Guide](https://packaging.python.org/)
- [Twine Documentation](https://twine.readthedocs.io/)
