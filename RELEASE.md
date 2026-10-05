# Release Process

## Astichi Configuration

`gearu.toml` releases the Python distribution from `main`, using immutable
`v<version>` tags and the `owebeeone/astichi` GitHub repository.

- Gearu updates `project.version` in `pyproject.toml` and refreshes `uv.lock`.
- The first candidate check synchronizes the public `astichi.__version__`
  mirror in `src/astichi/__init__.py`. Verification after committing only
  checks that mirror; it never repairs a tagged candidate.
- The Rust crate is private (`publish = false`) and only ships in the Python
  wheel. Its Cargo version and lockfile are not Python release-version mirrors
  and are intentionally not changed by Gearu.
- Candidate and exact-commit verification run the existing test harness across
  the full matrix declared in `pyproject.toml` (currently Python 3.12-3.15),
  strict MkDocs build, and distribution checks. Native and Python engine
  coverage is forced through both engines after a required native build; Rust
  must be installed. Python 3.15 is included
  in local release checks, but not yet in the release wheel matrix.
- Distribution checks build a wheel with native compilation required and an
  sdist, validate both with Twine, then install the wheel into a fresh virtual
  environment. The smoke check verifies the public/distribution versions,
  native extension loading, and a minimal executable Astichi composition with
  isolated Python imports. Temporary distributions are removed afterward.
- GitHub Release creation triggers `.github/workflows/publish.yml`, which
  builds the full Linux/macOS/Windows wheel matrix and publishes through PyPI
  trusted publishing. Gearu does not upload packages locally.

Prerequisites: Gearu 0.1.1 or later, Git, `uv`, Rust 1.85 or newer, and
`gh` authenticated for this repository when publishing a GitHub Release.
Run all commands from the repository root. Commit the configuration and docs
changes before asking Gearu to plan: even planning requires a clean tree.

The configuration contains no fixed next version. Start with
`gearu plan --bump patch`, review its proposed version, and use that explicit
version for any subsequently authorized release. Planning does not run the
checks; it reports the intended changes and commands. Gearu's plan lists the
manifest update, while the version mirror and lockfile are refreshed during
candidate preparation.

<!-- gearu:release:start -->
## Gearu Release Process

Gearu prepares and verifies the repository, creates an immutable tag, and can
create the GitHub Release that starts this repository's publication workflow.
It does not publish directly to package registries.

Full documentation: <https://owebeeone.github.io/gearu/>

### Install

Install the released tool with:

```sh
uv tool install gearu
```

Upgrade an existing installation with:

```sh
uv tool upgrade gearu
```

To test the unreleased `main` branch, install it directly from its repository:

```sh
uv tool install git+https://github.com/owebeeone/gearu.git
```

Verify the installation with `gearu --version`.

### Preconditions

- Read `gearu.toml` and this repository's release workflow.
- Choose an explicit release version or an explicit major, minor, or patch bump.
  Gearu does not infer release intent from commits.
- Use a clean checkout on the branch configured by `project.branch`.
- Synchronize configured release and source branches with their remote.
- Release required cross-repository dependencies first.
- Install and authenticate `gh` before requesting GitHub Release creation.

### Plan

Always inspect the read-only plan first:

```sh
gearu plan VERSION
```

Or ask Gearu to select the next version:

```sh
gearu plan --bump patch
gearu plan --bump minor
gearu plan --bump major
```

Gearu compares configured package versions with valid local and remote release
tags, then bumps the highest version. It reads remote tags directly and does not
fetch or create local tags while planning.

For a release candidate, use a numbered version such as `1.2.3-rc.1`.

Override a configured dependency tag only when the release intentionally uses a
different version:

```sh
gearu plan VERSION --dependency-tag DEPENDENCY=TAG
```

### Prepare the Local Release

After reviewing the plan:

```sh
gearu release VERSION
```

The release command can select the version itself:

```sh
gearu release --bump minor
```

This recalculates the next version at release time. To lock the version reviewed
in a prior bump plan, pass that plan's reported `VERSION` explicitly.

Gearu builds and tests in a temporary worktree. Only a successful candidate is
applied to the local release branch and tagged. This step does not change a
remote repository.

### Push and Create the GitHub Release

Push the exact release commit and tag atomically:

```sh
gearu release VERSION --push
```

Create the GitHub Release after that push:

```sh
gearu release VERSION --push --github-release
```

The final command starts workflows listening for `release.published`, including
package publication and documentation deployment where configured.

### Recovery

- If candidate checks fail, fix the problem and rerun; the normal checkout is
  left unchanged.
- If local preparation succeeds, rerun the same version with `--push`.
- If the push succeeds but GitHub Release creation fails, rerun with
  `--push --github-release`.
- If released contents must change, use a new patch or release-candidate version.
  Never move or replace the existing tag.
- If only a publication workflow fails, repair and rerun that workflow for the
  same GitHub Release.
<!-- gearu:release:end -->
