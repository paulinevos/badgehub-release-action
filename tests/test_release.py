#!/usr/bin/env python3
"""Covers the pieces the workflow cannot: manifest editing and publishing."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
FULLNAME = "com.example.app"
MANIFEST_TEXT = json.dumps({
    "name": "Example",
    "publisher": "Example",
    "short_description": "An example",
    "long_description": "An example app",
    "fullname": FULLNAME,
    "version": "0.1.0",
    "category": "utility",
})


class ExampleApp:
    """A throwaway checkout of an app, laid out the way the action expects."""

    def __init__(self, root):
        self.directory = Path(root) / FULLNAME
        self.directory.mkdir()
        self.manifest = self.directory / "MANIFEST.JSON"
        self.manifest.write_text(MANIFEST_TEXT)
        (self.directory / "app.py").write_text("print('hello')\n")

    def read_manifest(self):
        return json.loads(self.manifest.read_text())


def run(command):
    return subprocess.run(command, capture_output=True, text=True)


def stub_mpk(directory):
    """Something for the publisher to upload.

    Bundling itself lives in badgehub-scaffolder now, and is tested there; a
    publish test only needs a file of the right name and shape.
    """
    path = directory / "{}_0.1.0.mpk".format(FULLNAME)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("{}/MANIFEST.JSON".format(FULLNAME), MANIFEST_TEXT)
        archive.writestr("{}/app.py".format(FULLNAME), "print('hello')\n")
    return path


class ManifestTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.app = ExampleApp(self.root)

    def manifest_command(self, *arguments):
        return run([sys.executable, str(SCRIPTS / "manifest.py"),
                    str(self.app.manifest), *arguments])

    def test_reads_a_field(self):
        result = self.manifest_command("--get", "fullname")
        self.assertEqual(FULLNAME, result.stdout.strip())

    def test_writes_the_version(self):
        self.manifest_command("--set-version", "1.2.3")
        self.assertEqual("1.2.3", self.app.read_manifest()["version"])

    def test_writing_the_current_version_is_not_a_failure(self):
        result = self.manifest_command("--set-version", "0.1.0")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_touches_nothing_but_the_version(self):
        self.manifest_command("--set-version", "9.9.9")
        expected = MANIFEST_TEXT.replace('"0.1.0"', '"9.9.9"')
        self.assertEqual(expected, self.app.manifest.read_text())

    def test_rejects_a_version_that_is_not_major_minor_patch(self):
        result = self.manifest_command("--set-version", "1.2")
        self.assertNotEqual(0, result.returncode)

    def test_rejects_an_unknown_field(self):
        result = self.manifest_command("--get", "publisher_name")
        self.assertNotEqual(0, result.returncode)


class PublishTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.app = ExampleApp(self.root)
        self.mpk = stub_mpk(Path(self.root))

    def publish(self, version):
        return run([sys.executable, str(SCRIPTS / "publish_badgehub.py"),
                    "--mpk", str(self.mpk), "--slug", FULLNAME,
                    "--version", version, "--dry-run"])

    def test_sends_the_calls_a_release_needs(self):
        result = self.publish("0.1.0")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("draft/files/{}_0.1.0.mpk".format(FULLNAME), result.stdout)
        self.assertIn("draft/metadata", result.stdout)
        self.assertIn("publish", result.stdout)

    def test_refuses_a_version_the_package_does_not_carry(self):
        result = self.publish("0.2.0")
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
