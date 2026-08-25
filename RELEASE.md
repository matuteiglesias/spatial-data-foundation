# Release procedure

Releases are human-triggered and published to PyPI through GitHub Actions Trusted Publishing. The repository must not store a PyPI username, password, API token, tile-provider credential, or other release secret.

## Versioning contract

`spatial-data-foundation` follows semantic versioning. Public compatibility includes the documented Python API, governed spatial-relation semantics, emitted materialization/provenance contracts, and optional presentation entry points.

- patch releases may repair implementation defects, tests, packaging, provider metadata, or documentation without changing accepted spatial meaning;
- minor releases may add backward-compatible capabilities, providers, optional extras, result fields, or helpers while preserving existing public behavior;
- major releases are required for incompatible public API or spatial-semantic changes.

Dataset/source schema versions and domain methodology versions remain separate from the package version.

## One-time PyPI and GitHub setup

Before the first publication:

1. confirm that the PyPI project name `spatial-data-foundation` is still available;
2. configure a PyPI pending Trusted Publisher for this repository, or add a Trusted Publisher under the existing project's **Publishing** settings if the project already exists;
3. create a GitHub repository environment named `pypi`.

Use these exact Trusted Publisher values:

- owner: `matuteiglesias`
- repository: `spatial-data-foundation`
- workflow: `release.yml`
- environment: `pypi`

Protection rules or required reviewers on the `pypi` environment are recommended so publication remains an explicit human-controlled action.

## Release steps

1. Confirm the intended version in `pyproject.toml` and verify that the change obeys the compatibility rules above.
2. Merge release-ready changes to `main` only after CI is green, including the dedicated clean-wheel distribution job.
3. Confirm the PyPI Trusted Publisher and GitHub `pypi` environment are configured.
4. Create a GitHub Release from the exact intended `main` commit using tag `vX.Y.Z`, where `X.Y.Z` exactly matches the package version.
5. Publish the GitHub Release. This triggers `.github/workflows/release.yml`.
6. The release workflow builds the wheel and sdist, verifies the release tag/version match, installs the exact built wheel in fresh core and presentation environments, uploads those exact artifacts between jobs, and publishes them to PyPI using OIDC.
7. After the workflow succeeds, verify both installation surfaces from clean environments.

The workflow intentionally has no manual dispatch and does not publish on ordinary branch, push, or pull-request events.

## Downstream installation

Core analytical/spatial use:

```bash
python -m pip install spatial-data-foundation
```

Optional contextual mapping:

```bash
python -m pip install "spatial-data-foundation[presentation]"
```

For downstream repositories that need the current compatibility line, prefer a released version range rather than a sibling checkout or Git URL:

```bash
python -m pip install "spatial-data-foundation>=0.1,<0.2"
```
