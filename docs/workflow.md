# Workflow and conventions

## Forks

Every mod we patch is forked into this org with its original name.

| Branch | Purpose |
|---|---|
| upstream branches | Untouched mirrors of upstream, kept in sync. |
| `perf/<topic>` | One fix per branch, based on the **upstream branch the PR targets**. This is what the upstream PR is opened from. No CI or version changes. |
| `mcopt/<mc-version>` | Our release branch: the upstream release commit packs actually ship, plus every `perf/*` fix for that version, plus `.github/workflows/mcopt-release.yml`. |

Release tags on our forks are `<upstream-version>+mcopt.<n>`, for example `2.0.4+mcopt.1`.
The jar keeps the original mod id, so it is a drop-in replacement.

## Writing a fix

- Build against the exact upstream commit for the version the pack ships. Find it by searching the
  version string in `gradle.properties` history if releases are not tagged.
- Keep the diff minimal and in the project's style. No refactors, formatting changes or version bumps.
- If upstream already fixed it on a newer branch, **cherry-pick** (`git cherry-pick -x`) instead of rewriting.
- Prove equivalence for any non-trivial rewrite (for example, fuzz the old and new implementations against each other).

## Measuring

The bench harness runs a dedicated test server on a copy of the pack (never a live server):

```sh
tools/bench/bench.py template                       # once per pack: generate the seeded, empty bench area
tools/bench/ab.sh <pack-jar> <label> --orig fixed.jar -- --mobs 1500 --seconds 150
python3 -I tools/spark/report.py results/<label>-A.sparkprofile <yarn.tiny>
```

Every variant starts from the same template world with the same seeded mob population. Profiles are saved
locally (`--save-to-file`) and never uploaded. Don't run builds on the bench cores while a benchmark is running.

## PR text

Each PR includes:

- What the hot spot is, with the profile evidence: the frame, and its share of tick time on a real server.
- The change and why it is behavior-preserving, or exactly which edge case differs.
- Before/after from the bench harness, including entity counts and run length.
- Test notes (what was checked in game).
