#!/usr/bin/env python3
"""The `before-search` guard: a search of the source for a symbol waits until this session has asked the index.

The keel runs this before a search, in a harness that can hold a guard, once a person has agreed to it
(`python3 scripts/extensions/guards.py --elect codegraph`); nothing in this package agrees for anybody. It is
also run, with what it exits with discarded, when one of the index's own MCP tools is used — the manifest
declares that this guard `sees` them — which is how it knows a session has asked.

The rule, and every place it allows because it cannot tell, is `code_index.guard()`. This file is the part that
must not be able to fail: **whatever goes wrong in there, the search goes ahead.** A guard that raised would be
reported by the keel and the call would go on anyway; this says why in the guard's own words first, and exits 0
so that nothing reads a crash as an opinion.

Exit 2 refuses, and only `code_index.guard()` returning it does. Standard library only.
"""
from __future__ import annotations

import sys
from pathlib import Path

REFUSE = 2


def main() -> int:
    try:
        sys.dont_write_bytecode = True  # no `__pycache__/` in the project for a tool call
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import code_index
        answer = code_index.guard()
    except Exception as error:  # noqa: BLE001 — fail open: a guard that cannot decide refuses nothing
        print(f"code-index: allowed — the guard could not decide ({type(error).__name__}: {error})",
              file=sys.stderr)
        return 0
    return REFUSE if answer == REFUSE else 0


if __name__ == "__main__":
    raise SystemExit(main())
