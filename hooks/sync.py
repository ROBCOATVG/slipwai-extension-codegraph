#!/usr/bin/env python3
"""The `after-stage` point: a rung of the ladder finished, having edited what it edited; bring the index up to it.

CodeGraph keeps its database current from a watcher, and the watcher is what is off in the places a captain's
session runs — a sandbox, a headless session whose daemon has idled out. So the next rung would ask an index
that has not read what the last one wrote, and get *nothing calls that* about code that is ten minutes old.
Version 1 reached this moment through one harness's own hook row; `after-stage` is the keel's point for it, on
every harness.

`extension.json` has declared this script since 1.0.0 and the package did not ship it until 1.0.1: the toolkit
reported `hooks/sync.py is not in this project` after every rung and nothing synced.

The manifest gives this 30 seconds and the toolkit ends a hook that overruns, so the sync is given less than
that and ended here, where it can be said. Never fails a rung: it exits 0 whatever happened and prints what it
could not do — the gate (`hooks/check.py`) is what fails on an index that stayed behind.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import code_index  # noqa: E402

# Inside the 30s the manifest declares, with room for this interpreter and `npx` to start.
SECONDS = 25


def outcome() -> str:
    """What the sync did, in one line; empty where there is no index here to sync."""
    if not code_index.DATABASE.is_file():
        return ""
    done, said = code_index.cli("sync", ".", seconds=SECONDS)
    if done:
        return "codegraph: synced the index after the rung"
    return (f"codegraph: did not sync the index after the rung ({said or 'the CLI said nothing'}); "
            "`scripts/codegraph sync` brings it up to the tree")


def main() -> int:
    try:
        said = outcome()
    except Exception as error:  # noqa: BLE001 — a hook reports; it never fails the rung
        said = (f"codegraph: did not sync the index after the rung ({type(error).__name__}: {error}); "
                "`scripts/codegraph sync` brings it up to the tree")
    if said:
        print(said)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
