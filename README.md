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
| `code_index.py` | The pin, the route to the CLI, the integrity check, `health`, `sync`, and the rule the guard holds |
| `guards/ask_the_index.py` | The `before-search` guard: a search of the source for a symbol is refused until the session has asked the index. Offered by the keel, on only where a person agreed |
| `hooks/project.py` | The `project` point (`make agents`, `slipwai migrate`): rewrites the `AGENTS.md` block, writes `scripts/codegraph` where it is missing, and installs nothing |
| `hooks/sync.py` | The `after-stage` point: syncs the index after a rung, inside its 30s budget, and never fails one |
| `hooks/check.py` | The `check` point (`make check-extensions`): fails on an index that cannot be made sound and current, or a missing wrapper |
| `tests/` | What the package promises a project, run in a scratch one: `python -m unittest discover -s tests` |

## The guard

`extension.json` declares one guard, at the keel's `before-search` point. **Electing the extension does not turn
it on**: a guard refuses things a person asked for, so the keel asks, and `python3 scripts/extensions/guards.py
--elect codegraph` is the answer (`--remove codegraph` takes it back). A project that had this extension before it
had a guard is told once, at `slipwai migrate` and at every `make agents`, and nothing changes until somebody says yes.

Where it is on, a search of the **source** for a **symbol** — a Grep, or `grep`, `rg`, `ag`, `ack` or `git grep`
through the shell, whose pattern is only names the index defines or names shaped like one — is refused, with
`scripts/codegraph callers|impact|explore <symbol>` to ask instead, until that session (or that delegate inside
it) has asked the index once: one of its MCP tools, which the guard declares it `sees`, or a query verb through
the shell. Who has asked is kept in `.codegraph/asked.json`, which Git ignores.

It never refuses a search confined to documents (`specs/`, `docs/`, `*.md` and the like, by path or by filter), a
Glob or a file-name search, a pattern that is words or a regular expression, or a search outside the repository.
It allows, and says why on stderr, wherever it cannot tell or the index could not have answered: no index, one that
cannot be read, one last written more than 14 days ago, no route to the CLI on this machine, or an event that does
not name the tool, the session or the directory. It runs no command and opens no connection, and anything that
goes wrong inside it allows the search.

**It needs a keel that hands a guard the search** (slipwai with #121: the search event on stdin, `sees`, and
`SLIPWAI_GUARDS_HELD`). The manifest has no field to say so — `core` is the schema range, and that did not move —
so on an older keel this version installs and behaves as 1.0.1 did: the guard is handed only the query, cannot
judge, and allows every search, and the `AGENTS.md` block says no guard holds. Only Claude Code has a moment
before a search that the keel can refuse at; the block says which harness holds the rule in the project it is in.

## The six obligations

An extension's entry point meets all six, and `slipwai extension check` says so:

1. **Idempotent** — running it twice does what running it once did.
2. **Non-fatal** — a tool it cannot install is said, not fatal.
3. **Projects** — its `AGENTS.md` block is marker-fenced and replaced whole.
4. **Gated** — state that can go stale has a gate: `hooks/check.py`, on the `check` point.
5. **Recovers** — every failure path names the command that fixes it.
6. **Merges** — a hand-edited file is merged, never overwritten.
