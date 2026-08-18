"""Fetch and compile the official ITC-2007 CB-CTT validator.

    python evaluation/itc2007/build.py          # fetch + compile
    python evaluation/itc2007/build.py --check  # verify what is already here

The validator is **not** vendored into this repository. It is third-party
source by Schaerf and Di Gaspero published without an explicit licence, so
it is fetched on demand and its sha256 recorded here instead. That also
means the binary E4b validates against has provenance: a URL, a hash, and
a compiler, rather than being a file someone pasted in.

Everything lands in `evaluation/itc2007/vendor/`, which is git-ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

#: Official source. The competition site serves this over valid TLS; the
#: instances themselves sit behind a login, which is why E4b needs them
#: supplied separately (see INSTANCES.md).
VALIDATOR_URL = ("https://www.eeecs.qub.ac.uk/itc2007/curriculmcourse/"
                 "validator.cc")

#: sha256 of validator.cc v1.1 as fetched 2026-08-18. A change here means
#: the competition site changed the validator, which would invalidate any
#: comparison to published results and must be investigated, not accepted.
VALIDATOR_SHA256 = \
    "994234100519ace008926c55e08ede9c638dbb5fb054b7b2cda02de468cd345a"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(force: bool = False) -> Path:
    VENDOR.mkdir(parents=True, exist_ok=True)
    src = VENDOR / "validator.cc"
    if force or not src.exists():
        with urllib.request.urlopen(VALIDATOR_URL, timeout=60) as r:
            src.write_bytes(r.read())
    got = _sha256(src)
    if got != VALIDATOR_SHA256:
        raise SystemExit(
            "validator.cc sha256 mismatch%s  expected %s%s  got      %s%s"
            "The competition site's validator changed. Stop and check it "
            "before comparing anything to published results."
            % (chr(10), VALIDATOR_SHA256, chr(10), got, chr(10)))
    return src


def _compiler() -> list[str]:
    for name in ("g++", "clang++", "c++"):
        found = shutil.which(name)
        if found:
            return [found]
    zig = shutil.which("zig")
    if zig:
        return [zig, "c++"]
    raise SystemExit(
        "no C++ compiler found (looked for g++, clang++, c++, zig).%s"
        "The official validator is a single .cc file; any C++ compiler "
        "will do. On this machine MinGW works once binutils is present: "
        "mingw-get install binutils" % chr(10))


def compile_validator(src: Path) -> Path:
    exe = VENDOR / ("validator.exe" if sys.platform == "win32"
                    else "validator")
    cmd = _compiler() + ["-O2", "-o", str(exe), str(src)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not exe.exists():
        raise SystemExit("compile failed:%s%s%s"
                         % (chr(10), proc.stdout, proc.stderr))
    return exe


def validator_path(build_if_missing: bool = True) -> Path:
    """Path to a compiled validator, building it if it is not there yet."""
    exe = VENDOR / ("validator.exe" if sys.platform == "win32"
                    else "validator")
    if exe.exists():
        return exe
    if not build_if_missing:
        raise SystemExit("no validator built; run "
                         "python evaluation/itc2007/build.py")
    return compile_validator(fetch())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify the vendored source hash, do not compile")
    ap.add_argument("--force", action="store_true", help="re-download")
    args = ap.parse_args()

    src = fetch(force=args.force)
    print("validator.cc  %s  sha256 %s" % (VALIDATOR_URL, _sha256(src)[:16]))
    if args.check:
        print("hash matches the recorded value.")
        return 0
    exe = compile_validator(src)
    print("built %s" % exe.relative_to(HERE.parent.parent))
    print("next: python evaluation/itc2007/crosscheck.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
