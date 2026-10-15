Fixes multi-second server freezes from the Ramparts fall protection. Seen as a 4.27 s freeze on a live server; spark showed `minecells$getResetToPos` -> `Stream.min` -> `World.getBlockState` -> `ServerChunkManager.getChunkBlocking`.

### Cause

`getResetToPos` calls `World#getTopY` and `World#getBlockState` for every checkpoint in the 1024 block cell. `getTopY` guards with `World#isChunkLoaded`, but on the server that only checks that the chunk holder's ticket level is FULL, not that the chunk has finished loading. The following `getChunk` then blocks the server thread until the load completes.

Side effect: for checkpoints whose chunks really are unloaded, `getTopY` returns the world bottom, so they always fail the solid floor check and the entity is usually sent to the dimension entrance instead of the nearest checkpoint.

### Change

- New `util/FallResetTargets`: only queries chunks that are fully loaded (`ServerChunkManager#getWorldChunk`, non-blocking) and reads height and block state from that chunk.
- If the nearest checkpoint is not loaded, it adds a short-lived ticket (100 ticks, radius 1) to load it off-thread and returns null.
- `injectTick`: on null, holds the entity at its current position (teleport, zero velocity, reset fall distance) and returns. The handler already runs every 2 ticks while below the reset height, so it retries automatically.
- After 200 ticks of waiting it falls back to the old synchronous lookup (`minecells$getResetToPosBlocking`, unchanged).

### Test

Full Prominence II 4.1.3 server. Ramparts generated, then server restarted so chunks are on disk but not loaded. A cow is summoned at Y 170 with horizontal motion so fall protection triggers. Worst tick measured with the spark tick monitor.

| Position | Before | After |
|---|---|---|
| 40, 480 (5 runs before, 4 after) | 2,732 to 4,027 ms, sent to entrance | no tick over 100 ms (max 28 ms), sent to nearest checkpoint |
| 300, 700 | 395 ms, entrance | 26 ms, entrance |
| -200, 600 | under 100 ms, entrance | 28 ms, entrance |

### Notes

- The branch head (317eac31) does not build for me as is: with Java 21 Loom interface injection is not applied (`getModel(Identifier)`, `allowNbtUpdateAnimation`), with Java 17 gimm1q classes cannot be read. I compile checked these two files against the released 2.0.0 jar and tested the same logic at runtime on 2.0.0 through a mixin.
- `minecells-2.0.0+1.21.1` has the same `getResetToPos` and should need the same change.
