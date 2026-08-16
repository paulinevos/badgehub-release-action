#!/usr/bin/env python3
"""Reads and writes a MicroPythonOS MANIFEST.JSON.

The manifest is the only place an app's version and fullname live — the bundler
names the .mpk after both — so every other step asks this one script instead of
parsing JSON itself.

Writing edits the version field in place and leaves the rest of the file byte
for byte alone, keeping release diffs to a single line.

    python3 manifest.py path/to/MANIFEST.JSON --get fullname
    python3 manifest.py path/to/MANIFEST.JSON --set-version 1.0.0
"""

import argparse
import json
import re
import sys
from pathlib import Path

VERSION_FIELD = re.compile(r'("version"\s*:\s*")(\d+)\.(\d+)\.(\d+)(")')


class InvalidManifest(Exception):
    pass


class Version:

    def __init__(self, text):
        parts = text.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise InvalidManifest("'{}' is not a major.minor.patch version".format(text))
        self.text = ".".join(str(int(part)) for part in parts)

    def __str__(self):
        return self.text


class Manifest:

    def __init__(self, path):
        self.path = path
        self._text = self._read()
        self._fields = self._parse()

    def field(self, name):
        if name not in self._fields:
            raise InvalidManifest("{} has no '{}' field".format(self.path, name))
        return self._fields[name]

    def write_version(self, version):
        if not VERSION_FIELD.search(self._text):
            raise InvalidManifest(
                "no major.minor.patch version field in {}".format(self.path))
        replacement = r"\g<1>{}\g<5>".format(version)
        self.path.write_text(VERSION_FIELD.sub(replacement, self._text, count=1))

    def _read(self):
        if not self.path.is_file():
            raise InvalidManifest("no such manifest: {}".format(self.path))
        return self.path.read_text()

    def _parse(self):
        try:
            return json.loads(self._text)
        except ValueError as error:
            raise InvalidManifest("{} is not valid JSON: {}".format(self.path, error))


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--get", metavar="FIELD", help="print one manifest field")
    # Setting a version already in the manifest is a success on purpose: a
    # release whose tag matches the manifest must still build and publish.
    action.add_argument("--set-version", metavar="VERSION",
                        help="write an exact major.minor.patch version")
    return parser.parse_args(argv)


def main(argv):
    arguments = parse_arguments(argv)
    try:
        manifest = Manifest(arguments.manifest)
        if arguments.get:
            print(manifest.field(arguments.get))
            return 0
        version = Version(arguments.set_version)
        manifest.write_version(version)
        print(version)
        return 0
    except InvalidManifest as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
