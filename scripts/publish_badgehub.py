#!/usr/bin/env python3
"""Publishes a built .mpk to BadgeHub as a new version.

Three calls, all authenticated with a project API token in the
`badgehub-api-token` header (BadgeHub's `apiTokenAuth`, the one meant for
automation):

    POST  /api/v3/projects/{slug}/draft/files/{filename}   upload the .mpk
    PATCH /api/v3/projects/{slug}/draft/metadata           set the version
    PATCH /api/v3/projects/{slug}/publish                  publish the draft

The token is created once from the project page (or `POST /projects/{slug}/token`
with a logged-in session) and stored as a repository secret. Creating the
project itself needs a real login and cannot be done with a project token.

    BADGEHUB_API_TOKEN=... python3 publish_badgehub.py \\
        --mpk com.example.app_0.2.0.mpk --slug com.example.app --version 0.2.0
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://badgehub.eu/api/v3"
TOKEN_HEADER = "badgehub-api-token"
BOUNDARY = "----badgehub-release-boundary"
# badgehub.eu sits behind Cloudflare, which answers the default
# "Python-urllib/x.y" agent with 403 and error code 1010 before the request
# ever reaches the API. Any ordinary agent string is accepted.
USER_AGENT = "badgehub-release-action/1 (+https://github.com/paulinevos/badgehub-release-action)"


class PublishFailed(Exception):
    pass


class BadgeHub:

    def __init__(self, slug, token, dry_run=False):
        self._slug = slug
        self._token = token
        self._dry_run = dry_run

    def publish(self, mpk, metadata):
        self._upload(mpk)
        self._remove_superseded_packages(mpk.name)
        self._set_metadata(metadata)
        self._release()
        return "https://badgehub.eu/page/project/{}".format(self._slug)

    def _remove_superseded_packages(self, keep):
        """Drop older .mpk files from the draft.

        The appstore's file picker falls back to the *first* .mpk in the
        revision whenever it cannot match one by version, so a leftover build
        is not merely untidy — it is what users would install.
        """
        superseded = [name for name in self._draft_package_names() if name != keep]
        if not superseded:
            print("no superseded packages in the draft")
            return
        for name in superseded:
            self._send("DELETE", "draft/files/{}".format(name), b"",
                       "application/json", "removing superseded {}".format(name))

    def _draft_package_names(self):
        # A DetailedProject nests the file list under `version`, not at the
        # top level; reading the wrong key made this silently find nothing.
        draft = self._get("draft") or {}
        files = (draft.get("version") or {}).get("files") or []
        return [file.get("name", "") + file.get("ext", "")
                for file in files if file.get("ext") == ".mpk"]

    def _upload(self, mpk):
        body = self._multipart(mpk)
        self._send("POST", "draft/files/{}".format(mpk.name), body,
                   "multipart/form-data; boundary={}".format(BOUNDARY),
                   "uploading {} ({} bytes)".format(mpk.name, mpk.stat().st_size))

    def _set_metadata(self, metadata):
        """Overwrite the draft metadata, keeping BadgeHub-only fields.

        This endpoint replaces metadata.json wholesale rather than merging,
        so sending only the version wipes the name and description off the
        project page. Fields BadgeHub owns and the manifest knows nothing
        about — badges, development_status, categories — are read back and
        preserved.
        """
        existing = (self._get("draft") or {}).get("version", {}).get("app_metadata") or {}
        merged = dict(existing)
        merged.update(metadata)
        body = json.dumps(merged).encode()
        self._send("PATCH", "draft/metadata", body, "application/json",
                   "setting metadata: {}".format(", ".join(sorted(metadata))))

    def _release(self):
        self._send("PATCH", "publish", b"", "application/json",
                   "publishing the draft")

    def _get(self, path):
        url = "{}/projects/{}/{}".format(BASE_URL, self._slug, path)
        if self._dry_run:
            print("would list the draft: GET {}".format(url))
            return {}
        request = urllib.request.Request(url, method="GET")
        request.add_header(TOKEN_HEADER, self._token)
        request.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, ValueError) as error:
            raise PublishFailed("GET {} -> {}".format(url, error))

    def _send(self, method, path, body, content_type, description):
        url = "{}/projects/{}/{}".format(BASE_URL, self._slug, path)
        print("{}: {} {}".format(description, method, url))
        if self._dry_run:
            print("  (dry run, not sent)")
            return
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header(TOKEN_HEADER, self._token)
        request.add_header("Content-Type", content_type)
        request.add_header("User-Agent", USER_AGENT)
        try:
            with urllib.request.urlopen(request) as response:
                print("  {} {}".format(response.status, response.reason))
        except urllib.error.HTTPError as error:
            raise PublishFailed("{} {} -> {} {}: {}".format(
                method, url, error.code, error.reason,
                error.read().decode(errors="replace")[:400]))
        except urllib.error.URLError as error:
            raise PublishFailed("{} {} -> {}".format(method, url, error.reason))

    @staticmethod
    def _multipart(mpk):
        head = (
            '--{boundary}\r\n'
            'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n'
        ).format(boundary=BOUNDARY, name=mpk.name).encode()
        tail = "\r\n--{}--\r\n".format(BOUNDARY).encode()
        return head + mpk.read_bytes() + tail


def metadata_in(mpk):
    """The BadgeHub metadata a manifest describes.

    Read from the MANIFEST.JSON inside the package being published, so the
    project page can never describe something other than the shipped build.
    """
    with zipfile.ZipFile(mpk) as archive:
        names = [name for name in archive.namelist() if name.endswith("MANIFEST.JSON")]
        if not names:
            raise SystemExit("{} contains no MANIFEST.JSON".format(mpk))
        manifest = json.loads(archive.read(names[0]))
    fields = {
        "name": "name",
        "description": "short_description",
        "long_description": "long_description",
        "author": "publisher",
        "version": "version",
    }
    missing = sorted(key for key in fields.values() if key not in manifest)
    if missing:
        raise SystemExit("the manifest in {} has no {}".format(mpk, ", ".join(missing)))
    metadata = {name: manifest[key] for name, key in fields.items()}
    metadata["project_type"] = "app"
    return metadata


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mpk", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--slug", required=True,
                        help="the BadgeHub project slug, usually the fullname")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the calls without sending them")
    return parser.parse_args(argv)


def main(argv):
    arguments = parse_arguments(argv)
    if not arguments.mpk.is_file():
        raise SystemExit("no such file: {}".format(arguments.mpk))

    token = os.environ.get("BADGEHUB_API_TOKEN", "")
    if not token and not arguments.dry_run:
        raise SystemExit("BADGEHUB_API_TOKEN is not set")

    metadata = metadata_in(arguments.mpk)
    if metadata["version"] != arguments.version:
        raise SystemExit(
            "the package says version {} but the release says {}".format(
                metadata["version"], arguments.version))

    try:
        page = BadgeHub(arguments.slug, token, arguments.dry_run).publish(
            arguments.mpk, metadata)
    except PublishFailed as error:
        raise SystemExit("BadgeHub rejected the release: {}".format(error))
    print("\npublished {} {}\n{}".format(arguments.slug, arguments.version, page))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
