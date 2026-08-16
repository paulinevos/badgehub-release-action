#!/usr/bin/env bash
# Builds a deterministic .mpk, per docs.micropythonos.com/apps/bundling-apps/:
# the first ZIP entry must be the top-level directory named after fullname,
# directories sorted before files, stored (-0) rather than deflated.
#
#     bundle.sh <app-directory> [output-directory]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIRECTORY="$(cd "${1:?usage: bundle.sh <app-directory> [output-directory]}" && pwd)"
OUTPUT_DIRECTORY="$(cd "${2:-$PWD}" && pwd)"

MANIFEST="${APP_DIRECTORY}/MANIFEST.JSON"
FULLNAME="$(python3 "${HERE}/manifest.py" "${MANIFEST}" --get fullname)"
VERSION="$(python3 "${HERE}/manifest.py" "${MANIFEST}" --get version)"

# The archive holds exactly one top-level directory, named after fullname, or
# MicroPythonOS rejects it on install — so bundle from the app directory's
# parent under that name rather than from whatever the checkout calls it.
PARENT="$(dirname "${APP_DIRECTORY}")"
if [ "$(basename "${APP_DIRECTORY}")" != "${FULLNAME}" ]; then
  echo "the app directory must be named ${FULLNAME}, not $(basename "${APP_DIRECTORY}")" >&2
  exit 1
fi

OUTPUT="${OUTPUT_DIRECTORY}/${FULLNAME}_${VERSION}.mpk"
rm -f "${OUTPUT}"

cd "${PARENT}"
find "${FULLNAME}" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${FULLNAME}" -exec touch -t 202501010000.00 {} \;
(find "${FULLNAME}" -type d; find "${FULLNAME}" -type f) \
  | sort \
  | TZ=CET zip -X -r -0 "${OUTPUT}" -@

echo "built ${OUTPUT}"
