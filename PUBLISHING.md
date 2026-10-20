# Publishing to PyPI

Releases are built and uploaded by [`.github/workflows/publish.yml`](.github/workflows/publish.yml) using **PyPI Trusted Publishing**, so there is no API token to create, store or rotate. PyPI verifies a short-lived OIDC token minted by GitHub for this specific repository and workflow.

Releasing is [step 4](#4-release); steps 1 to 3 are one-off setup. For PyPI that setup is done: the `pypi` environment and trusted publisher were set up for 1.0.0 (2026-08-07), and 1.1.0 went out through them unchanged. Steps 1 and 2 only matter again if that setup is lost or moved. **TestPyPI is not set up**: the repository has no `testpypi` environment, so the dry run in step 3 fails until it is created.

## 1. Create the GitHub environments

Done for `pypi`; `testpypi` does not exist yet. In the repository, under **Settings → Environments**, create two environments:

| Name | Used for |
|---|---|
| `pypi` | real releases |
| `testpypi` | manual dry runs |

Adding yourself as a required reviewer on `pypi` gives you a confirmation step before anything becomes permanent, which is worth having — see the warning at the bottom.

## 2. Register the trusted publisher

Done for PyPI, where the project now exists, so a publisher is added under the project's own **Settings → Publishing** rather than as a pending publisher (that route was for the very first upload, which created the project). The values are:

| Field | Value |
|---|---|
| PyPI project name | `sharebyurl` |
| Owner | `watercrossing` |
| Repository name | `sharebyurl` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

Both fields must match exactly — the workflow filename including `.yml`, and the environment name. A mismatch fails at upload with `invalid-publisher`, after the build has already succeeded.

For TestPyPI, register it at <https://test.pypi.org/manage/account/publishing/> with the environment set to `testpypi` (not done, as far as is known).

## 3. Dry run against TestPyPI

Needs the `testpypi` environment and publisher from steps 1 and 2, which do not exist yet. Worth it before a release that changes the packaging itself; a code-only release can skip it.

**Actions → Publish → Run workflow**, target `testpypi`. This runs the full pipeline without creating a release. Then check the result installs:

```console
$ uv tool install --index-url https://test.pypi.org/simple/ \
    --index-strategy unsafe-best-match sharebyurl
```

`--index-strategy unsafe-best-match` is needed because `argcomplete` and `python-slugify` are not on TestPyPI and must come from the real index.

## 4. Release

```console
$ # bump __version__ in sharebyurl/__init__.py, commit and push, then:
$ git tag vX.Y.Z
$ git push origin vX.Y.Z
$ gh release create vX.Y.Z --title vX.Y.Z --notes "..."
```

Publishing the GitHub release is what triggers the upload; the tag alone does nothing. The workflow refuses to build if the tag does not match `__version__`, so a mistyped tag fails early rather than shipping a mislabelled artifact.

## Versioning

The version lives in exactly one place, `sharebyurl/__init__.py`; `pyproject.toml` reads it from there. Do not add a second copy.

## ⚠️ A published version is permanent

PyPI does not allow a filename or version to be reused, even after deleting it. A bad `1.0.0` cannot be replaced — it can only be yanked and followed by `1.0.1`. This is why the TestPyPI dry run is worth doing the first time, when the packaging itself is unproven.
