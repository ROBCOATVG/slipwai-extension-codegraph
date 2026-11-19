#!/usr/bin/env python3
"""Write `scripts/codegraph`, the command this extension's guidance names, and nothing else.

    python3 scripts/extensions/codegraph/wrapper.py

The keel copies a package's files into a project under `scripts/extensions/<key>/`, as bytes and with no mode, so
nothing an extension ships is executable where it lands and nothing lands at a path short enough to put in a brief.
1.0.0 named `scripts/codegraph` in `AGENTS.md` anyway: version 1 of the keel had shipped that file to every project,
the crossing to 2.1 removed it, and this package wrote nothing in its place — so a delegate that followed the page
ran a file that was not there. `./init --extension codegraph` calls `write()` now, and the gate
(`hooks/check.py`) fails where the file is missing and names this script, which is the repair that installs and
indexes nothing.

The wrapper is tracked, not ignored: it travels with the checkout, which is the point of it. Its source is
`bin/codegraph` beside this file, and what is written is that file's bytes, so a newer package rewrites an older
copy and a second run changes nothing. A file at that path that is not this wrapper — somebody's own script — is
left alone and said (docs/extensions.md, obligation 6).
"""
from __future__ import annotations

import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "bin/codegraph"
# `<scripts>/extensions/codegraph/wrapper.py`: the wrapper sits in the `scripts/` this extension was copied under.
TARGET = HERE.parents[1] / "codegraph"
# What every version of the wrapper has opened with, the keel's own version-1 copy included: how a file at that
# path is known to be the wrapper rather than something a person put there.
OURS = "`scripts/codegraph <verb> …`: the code index's CLI"
EXECUTABLE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH


def write() -> str | None:
    """Make `scripts/codegraph` this package's wrapper, executable. Why it could not, or None."""
    try:
        wanted = SOURCE.read_bytes()
        if TARGET.exists():
            held = TARGET.read_bytes()
            if OURS.encode("utf-8") not in held:
                return (f"{TARGET} is there and is not this extension's wrapper, so it was left alone. Move it "
                        f"away and run `python3 {Path(__file__).resolve()}` to have `scripts/codegraph` written")
            if held != wanted:
                TARGET.write_bytes(wanted)
        else:
            TARGET.write_bytes(wanted)
        if stat.S_IMODE(TARGET.stat().st_mode) != EXECUTABLE:
            TARGET.chmod(EXECUTABLE)
    except OSError as error:
        return (f"{TARGET} could not be written ({error}). Fix that and run "
                f"`python3 {Path(__file__).resolve()}`")
    return None


def main() -> int:
    problem = write()
    if problem:
        print(f"codegraph: {problem}", file=sys.stderr)
        return 1
    print(f"codegraph: {TARGET} runs the pinned CLI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
