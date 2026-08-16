#!/usr/bin/env python3
"""Covers the pieces the workflow cannot: manifest editing and bundling."""

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


class BundleTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.app = ExampleApp(self.root)
        self.output = Path(self.root) / "dist"
        self.output.mkdir()

    def bundle(self, app_directory=None):
        return run(["bash", str(SCRIPTS / "bundle.sh"),
                    str(app_directory or self.app.directory), str(self.output)])

    def test_names_the_package_after_fullname_and_version(self):
        self.bundle()
        self.assertTrue((self.output / "{}_0.1.0.mpk".format(FULLNAME)).is_file())

    def test_holds_one_top_level_directory_named_after_fullname(self):
        self.bundle()
        with zipfile.ZipFile(self.output / "{}_0.1.0.mpk".format(FULLNAME)) as archive:
            tops = {name.split("/")[0] for name in archive.namelist()}
        self.assertEqual({FULLNAME}, tops)

    def test_stores_entries_rather_than_deflating_them(self):
        self.bundle()
        with zipfile.ZipFile(self.output / "{}_0.1.0.mpk".format(FULLNAME)) as archive:
            methods = {info.compress_type for info in archive.infolist()}
        self.assertEqual({zipfile.ZIP_STORED}, methods)

    def test_is_reproducible(self):
        self.bundle()
        first = (self.output / "{}_0.1.0.mpk".format(FULLNAME)).read_bytes()
        self.bundle()
        second = (self.output / "{}_0.1.0.mpk".format(FULLNAME)).read_bytes()
        self.assertEqual(first, second)

    def test_refuses_a_directory_not_named_after_fullname(self):
        renamed = Path(self.root) / "app"
        shutil.copytree(self.app.directory, renamed)
        self.assertNotEqual(0, self.bundle(renamed).returncode)


class PublishTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        self.app = ExampleApp(self.root)
        run(["bash", str(SCRIPTS / "bundle.sh"),
             str(self.app.directory), str(self.root)])
        self.mpk = Path(self.root) / "{}_0.1.0.mpk".format(FULLNAME)

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
