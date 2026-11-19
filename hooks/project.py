#!/usr/bin/env python3
"""The `project` point: rewrite this extension's `AGENTS.md` block from `GUIDANCE`, and write the command it names.

`make agents`, `slipwai migrate` and `./init --integration` fire this point, and the drift check in
`make check-extensions` tells a person to run the first two when the block no longer matches. Undeclared, the
point defaults to the entry point — and this extension's `init.py` installs CodeGraph and indexes the repository,
so until 1.0.1 a re-projection either reinstalled the tool or, where the CLI was missing, stopped before the block
and left it drifted.

It writes `scripts/codegraph` too, where that is missing or an older copy (`wrapper.write`). 1.0.0 wrote no
wrapper, so a project that elected it has none, and the gate refuses a project without one: a project that takes
1.0.1 through a migration would go red on the very check it had just been given, until somebody ran a command.
The wrapper is this package's own bytes copied into place and made executable — nothing is installed, indexed or
fetched — and a file somebody else put at that path is left alone and said.

A re-projection is still not an election: the MCP files stay `./init --extension codegraph`'s to write.

Never fails: a hook exits 0 and says what it could not do.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE.parent))  # the toolkit's `scripts/extensions/`, for `guidance`
sys.path.insert(0, str(PACKAGE))


def wrapper() -> None:
    """`scripts/codegraph`, written where it is missing or stale; what stopped it is said and never raised."""
    try:
        import wrapper as made
        before = made.TARGET.read_bytes() if made.TARGET.is_file() else None
        problem = made.write()
        if problem:
            print(f"codegraph: {problem}")
        elif before != made.TARGET.read_bytes():
            print("codegraph: wrote scripts/codegraph, the command its AGENTS.md block names; it is a tracked "
                  "file: commit it")
    except Exception as error:  # noqa: BLE001 — a hook reports; it never fails what fired it
        print(f"codegraph: could not write scripts/codegraph ({type(error).__name__}: {error}); "
              f"`python3 {PACKAGE / 'wrapper.py'}` writes it too")


def main() -> int:
    wrapper()
    try:
        from guidance import AGENTS, canonical_block, installed_block, replace_block
        from init import GUIDANCE
        if not AGENTS.is_file():
            print("codegraph: no AGENTS.md here, so there is no block to rewrite; `make agents` after one exists")
            return 0
        if installed_block("codegraph") == canonical_block("codegraph", GUIDANCE):
            return 0
        replace_block("codegraph", GUIDANCE)
        print("codegraph: rewrote its AGENTS.md block")
    except Exception as error:  # noqa: BLE001 — a hook reports; it never fails what fired it
        print(f"codegraph: could not rewrite its AGENTS.md block ({type(error).__name__}: {error}); "
              "`./init --extension codegraph` writes it too")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
