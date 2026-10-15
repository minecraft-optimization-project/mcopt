# Mine Cells: Fall protection never waits for chunks on the server thread

**Target:** `mim1q/MineCells` branch `minecells-2.0.0+1.20.1`
**Branch:** `minecraft-optimization-project/MineCells:perf/fall-reset-no-sync-chunk-load`
**Status:** draft, not opened

---

Hi! We profiled a live Prominence II server (Mine Cells 2.0.0) and found the Ramparts fall protection causing multi-second freezes. This PR fixes that.

### The problem

When an entity falls below Y 180 in the Ramparts, `EntityFallResetMixin#minecells$getResetToPos` picks the nearest checkpoint by calling `World#getTopY` and `World#getBlockState` for every checkpoint in the 1024-block cell, and there are dozens of them.

`World#getTopY` guards with `World#isChunkLoaded`. That returns true as soon as a chunk's *ticket level* reaches FULL, even if the chunk is still loading. The following `getChunk` then blocks the server thread until the load finishes. For checkpoints whose chunks really are unloaded, `getTopY` returns the bottom of the world, so they always fail the solid-floor check.

As a result:

- **Freezes:** a 4.27 s server freeze on a live server (spark: `minecells$getResetToPos` → `Stream.min` → `World.getBlockState` → `ServerChunkManager.getChunkBlocking`). We reproduce 3–4 s per trigger in a test world.
- **Wrong destination:** unloaded checkpoints never qualify, so players usually end up at the dimension entrance instead of the nearest checkpoint.

### The fix

- Only query chunks that are already fully loaded, via `ServerChunkManager#getWorldChunk`, which never blocks.
- If the nearest valid checkpoint isn't loaded, load its chunk in the background with a short-lived ticket. Hold the entity in place, and check again on the next fall-protection tick (every 2 ticks). Loading usually takes a few ticks.
- After 10 s of waiting, fall back to the existing synchronous lookup, so an entity can never get stuck.
- The new logic lives in `util/FallResetTargets`. The mixin change is the hold/retry branch.

### Results

Test server running the full Prominence II pack. A cow is launched at Y 170 in the Ramparts, and the chunks are generated but not loaded. Worst server tick during the reset:

| Fall position | Before | After |
|---|---|---|
| 40, 480 | 3,098–4,027 ms (sent to entrance) | 28 ms (nearest checkpoint) |
| 300, 700 | 395 ms (entrance) | 26 ms (entrance) |
| −200, 600 | <100 ms (entrance) | 28 ms (entrance) |

### Notes

- The branch head (`317eac31`) doesn't build for us. With Java 21, Loom's interface injection isn't applied (`getModel(Identifier)`, `allowNbtUpdateAnimation`). With Java 17, gimm1q's classes can't be read. We compile-checked these two files against the released 2.0.0 jar, and tested the identical logic at runtime on 2.0.0 through a mixin patch.
- `minecells-2.0.0+1.21.1` still has the same `getResetToPos`, so the same change applies there.
