# OpenSquilla Releases

| Version | Tag | Date | Notes |
|---|---|---|---|
| 0.1.0-alpha.1 | v0.1.0-alpha.1 | 2026-05-06 | First public alpha |

## Alpha tag SOP

1. Verify `git status` is clean.
2. Update `CHANGELOG.md`: move entries from `[Unreleased]` to `[0.1.0-alpha.1] - <date>` section; reopen empty `[Unreleased]`.
3. `git tag -a v0.1.0-alpha.1 -m "First public alpha"`
4. `git push origin v0.1.0-alpha.1` (this triggers `.github/workflows/wheelhouse-release.yml`)
5. Wait for wheelhouse workflow → review the draft GitHub Release → publish.
6. For subsequent alphas: bump tag to `v0.1.0-alpha.2` etc.; `pyproject.toml` version stays `0.1.0`.

## Why pyproject stays 0.1.0

PEP 440 pre-release suffixes (`0.1.0a1`) cause `uv sync` and `pip install` to skip the package by default unless `--prerelease=allow` is passed. To keep the README install command (`uv sync --extra recommended`) working without flags, the project communicates alpha status via git tags and GitHub Release labels rather than the package version itself. The version will bump to `0.2.0` (or similar) when alpha exits.
