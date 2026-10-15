# Minecraft Optimization Project

Measured, upstream-first performance fixes for popular Minecraft mods.

Large modpacks often lose a big share of their tick budget not to the game itself, but to small
inefficiencies in individual mods: a regex compiled on every call, a full world lookup for every
entity on every tick, a synchronous chunk load hidden in a stream. Each one is cheap to fix and
easy to miss, and they add up across hundreds of mods.

This project finds those hot spots with real server profiles, fixes them, **measures** the fix
under a reproducible load, and sends it upstream. While a fix waits for review (or for mods
that are no longer maintained), we publish builds ourselves so packs can use them today.

## How it works

1. **Profile** a real server with [spark](https://spark.lucko.me) under player load.
2. **Attribute** tick time to mods with the analyzers in [`tools/spark`](tools/spark).
3. **Fix** on a fork, against the exact version packs ship, in a minimal, reviewable commit.
4. **Measure** with [`tools/bench`](tools/bench): the same seeded world, the same mob population and
   the same profiling window, with only the one jar swapped. Before/after numbers go in the PR.
5. **Upstream** the fix as a PR to the original repository.
6. **Publish** an `+mcopt` build from our fork's release branch until upstream ships it.

Mods whose license does not allow redistributing modified builds get their fixes through
[`mcopt-patches`](https://github.com/minecraft-optimization-project/mcopt-patches), a companion mod
that patches the original jar at runtime instead.

## Fix tracker

See [TRACKER.md](TRACKER.md).

## Repository layout

| Path | What |
|---|---|
| `tools/spark/` | Spark profile decoder, per-mod attribution, caller chains, per-minute spike analysis |
| `tools/bench/` | Reproducible A/B benchmark harness for a dedicated test server |
| `findings/` | Profiling write-ups per modpack |
| `docs/` | Contributor workflow, conventions for forks, branches and releases |
| `templates/fork-ci/` | GitHub Actions workflow added to fork release branches |

## Principles

- **Measure, don't guess.** Every fix ships with before/after numbers from a controlled run.
- **Same behavior.** Performance fixes must not change gameplay. Any edge case that differs is called out in the PR.
- **Upstream first.** Our builds are a stopgap, not a fork of the ecosystem.
- **Respect licenses.** We only redistribute modified builds where the license allows it.
