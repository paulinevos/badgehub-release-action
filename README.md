# BadgeHub release action

Releases a [MicroPythonOS](https://micropythonos.com) app: writes the version
you give it into `MANIFEST.JSON`, builds a deterministic `.mpk`, checks the
archive layout, and publishes the result to [BadgeHub](https://badgehub.eu).

Everything is driven by the app's own manifest — the package is named after
`fullname` and `version`, and the BadgeHub project page is filled from the
manifest *inside the built package*, so the listing can never describe a
different build than the one shipped.

## Usage

```yaml
name: release

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - uses: paulinevos/badgehub-release-action@v1
        id: release
        with:
          version: ${{ github.event.release.tag_name }}
          app-directory: com.example.app
          badgehub-token: ${{ secrets.BADGEHUB_API_TOKEN }}

      - env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release upload "${{ github.event.release.tag_name }}" \
            "${{ steps.release.outputs.mpk }}" --clobber
```

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `version` | yes | | The version to release, as `major.minor.patch`. A leading `v` is stripped, so a tag name can be passed straight through. |
| `app-directory` | yes | | The directory holding `MANIFEST.JSON`. Must be named after the manifest's `fullname`. |
| `output-directory` | no | `.` | Where to write the `.mpk`. |
| `badgehub-token` | no | `''` | A BadgeHub project API token. Publishing is skipped with a warning when empty, so forks still build. |
| `badgehub-slug` | no | the manifest's `fullname` | The BadgeHub project slug. |
| `dry-run` | no | `false` | Print the BadgeHub calls without sending them. |

## Outputs

| Output | Description |
| --- | --- |
| `version` | The released version, without any leading `v`. |
| `fullname` | The manifest's `fullname`. |
| `mpk` | The path to the built `.mpk`. |

## What it does not do

Deliberately left to the calling workflow, because every repository wants them
differently:

- running the app's own tests and validation before releasing;
- committing the raised `MANIFEST.JSON` back to the default branch;
- attaching the `.mpk` to the GitHub release.

## The BadgeHub token

Create a project API token once from the BadgeHub project page (or
`POST /api/v3/projects/{slug}/token` with a logged-in session) and store it as a
repository secret. Creating the project itself needs a real login and cannot be
done with a project token.

The token authenticates three calls:

```
POST  /api/v3/projects/{slug}/draft/files/{filename}   upload the .mpk
PATCH /api/v3/projects/{slug}/draft/metadata           set the metadata
PATCH /api/v3/projects/{slug}/publish                  publish the draft
```

Older `.mpk` files are deleted from the draft before publishing: the appstore's
file picker falls back to the *first* `.mpk` in a revision when it cannot match
one by version, so a leftover build is what users would install.

## Requirements

The runner needs `python3` (3.8+, standard library only), `zip`, and `unzip` —
all present on `ubuntu-latest`.

## Development

```
python3 -m unittest discover -s tests
```
