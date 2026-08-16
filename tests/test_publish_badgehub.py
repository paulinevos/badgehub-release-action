"""Covers the BadgeHub response shape the publisher depends on.

Reading the file list from the wrong key made the cleanup step find nothing
and skip silently, leaving superseded .mpk files in the published revision.
"""

import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from publish_badgehub import BadgeHub  # noqa: E402


class DraftStub(BadgeHub):
    """A publisher whose only network call returns a canned draft."""

    def __init__(self, draft):
        super().__init__("a-slug", "a-token")
        self._draft = draft
        self.deleted = []

    def _get(self, path):
        return self._draft

    def _send(self, method, path, body, content_type, description):
        self.deleted.append(path)


def a_draft(*filenames):
    files = [{"name": name.rsplit(".", 1)[0], "ext": "." + name.rsplit(".", 1)[1]}
             for name in filenames]
    # DetailedProject nests files under `version`, which is the shape that
    # matters here — a flat {"files": ...} must not accidentally work.
    return {"slug": "a-slug", "version": {"revision": 10, "files": files}}


class DraftPackagesTest(unittest.TestCase):

    def test_reads_the_file_list_from_the_version_object(self):
        publisher = DraftStub(a_draft("app_0.1.0.mpk", "metadata.json"))
        self.assertEqual(publisher._draft_package_names(), ["app_0.1.0.mpk"])

    def test_ignores_everything_that_is_not_a_package(self):
        publisher = DraftStub(a_draft("metadata.json", "icon_64x64.png"))
        self.assertEqual(publisher._draft_package_names(), [])

    def test_survives_a_draft_with_no_version_yet(self):
        self.assertEqual(DraftStub({})._draft_package_names(), [])


class SupersededPackagesTest(unittest.TestCase):

    def test_deletes_older_packages_and_keeps_the_new_one(self):
        publisher = DraftStub(a_draft(
            "app_0.1.0.mpk", "app_0.2.0.mpk", "app_0.3.0.mpk", "metadata.json"))
        publisher._remove_superseded_packages("app_0.3.0.mpk")
        self.assertEqual(publisher.deleted,
                         ["draft/files/app_0.1.0.mpk", "draft/files/app_0.2.0.mpk"])

    def test_deletes_nothing_when_only_the_new_package_is_there(self):
        publisher = DraftStub(a_draft("app_0.3.0.mpk"))
        publisher._remove_superseded_packages("app_0.3.0.mpk")
        self.assertEqual(publisher.deleted, [])


if __name__ == "__main__":
    unittest.main()
