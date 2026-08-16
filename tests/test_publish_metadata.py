"""Covers the metadata sent to BadgeHub.

PATCH draft/metadata overwrites metadata.json rather than merging, so sending
a partial document strips the project page. These pin both halves: what the
manifest contributes, and that BadgeHub's own fields survive.
"""

import io
import json
import unittest
import zipfile

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from publish_badgehub import BadgeHub, metadata_in  # noqa: E402

A_MANIFEST = {
    "name": "Example App",
    "publisher": "Example",
    "short_description": "An example",
    "long_description": "A longer description.",
    "fullname": "com.example.app",
    "version": "1.2.3",
    "category": "utility",
}


def an_mpk(tmp_path, manifest=None):
    path = tmp_path / "app_1.2.3.mpk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("com.example.app/MANIFEST.JSON",
                         json.dumps(manifest if manifest is not None else A_MANIFEST))
    return path


class MetadataFromManifestTest(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def test_describes_the_build_being_published(self):
        self.assertEqual(metadata_in(an_mpk(self.tmp)), {
            "name": "Example App",
            "description": "An example",
            "long_description": "A longer description.",
            "author": "Example",
            "version": "1.2.3",
            "project_type": "app",
        })

    def test_refuses_a_package_with_no_manifest(self):
        path = self.tmp / "empty.mpk"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("readme.txt", "nothing here")
        with self.assertRaises(SystemExit):
            metadata_in(path)


class MergeStub(BadgeHub):

    def __init__(self, existing):
        super().__init__("a-slug", "a-token")
        self._existing = existing
        self.sent = None

    def _get(self, path):
        return {"version": {"app_metadata": self._existing}}

    def _send(self, method, path, body, content_type, description):
        self.sent = json.loads(body)


class MetadataMergeTest(unittest.TestCase):

    def test_keeps_fields_badgehub_owns_and_the_manifest_does_not_know(self):
        publisher = MergeStub({
            "badges": ["fri3d_2026"],
            "development_status": "stable",
            "categories": ["Game"],
            "version": "0.0.1",
            "name": "Old name",
        })
        publisher._set_metadata({"name": "Example App", "version": "1.2.3"})
        self.assertEqual(publisher.sent, {
            "badges": ["fri3d_2026"],
            "development_status": "stable",
            "categories": ["Game"],
            "version": "1.2.3",
            "name": "Example App",
        })

    def test_works_when_the_draft_has_no_metadata_yet(self):
        publisher = MergeStub(None)
        publisher._set_metadata({"name": "Example App"})
        self.assertEqual(publisher.sent, {"name": "Example App"})


if __name__ == "__main__":
    unittest.main()
