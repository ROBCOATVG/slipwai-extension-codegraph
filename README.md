# CodeGraph

A slipwai extension: optional dev tooling a generated or adopted project can elect at `./init`.

Indexes the codebase into a local knowledge graph your coding agent can query over MCP, so it can trace callers, dependencies, and the blast radius of a change across files.

## Installing

```sh
slipwai extension install codegraph
```

Then, in a project:

```sh
./init --extension codegraph
```

`./init` offers it in the extension menu too, where it was installed when the project was generated.

## What is in here

| File | What it is |
| --- | --- |
| `extension.json` | The manifest: what the catalogue shows, which keel schema it speaks, and the points it hooks |
| `init.py` | The entry point `./init --extension codegraph` runs: installs and indexes, writes `scripts/codegraph`, the `AGENTS.md` block and each harness's MCP file |
| `bin/codegraph` | The source of `scripts/codegraph`, the wrapper the `AGENTS.md` block names: the pinned CLI through `npx` or an installed `codegraph` |
| `wrapper.py` | Writes that wrapper into the project, executable, and nothing else; the repair the gate names |
| `code_index.py` | The pin, the route to the CLI, the integrity check, `health` and `sync` |
| `hooks/project.py` | The `project` point (`make agents`, `slipwai migrate`): rewrites the `AGENTS.md` block and installs nothing |
| `hooks/sync.py` | The `after-stage` point: syncs the index after a rung, inside its 30s budget, and never fails one |
| `hooks/check.py` | The `check` point (`make check-extensions`): fails on an index that cannot be made sound and current, or a missing wrapper |
| `tests/` | What the package promises a project, run in a scratch one: `python -m unittest discover -s tests` |

## The six obligations

An extension's entry point meets all six, and `slipwai extension check` says so:

1. **Idempotent** — running it twice does what running it once did.
2. **Non-fatal** — a tool it cannot install is said, not fatal.
3. **Projects** — its `AGENTS.md` block is marker-fenced and replaced whole.
4. **Gated** — state that can go stale has a gate: `hooks/check.py`, on the `check` point.
5. **Recovers** — every failure path names the command that fixes it.
6. **Merges** — a hand-edited file is merged, never overwritten.
