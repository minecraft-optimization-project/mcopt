# Performance patterns and traps

Recurring causes of server lag found while profiling mods, and how to fix them. Add to this as we find more.

## Chunk access on the server thread

- **`World#isChunkLoaded` does not mean "loaded".** On the server it is true once the chunk holder's ticket
  level reaches FULL, even while the chunk is still loading or generating. `World#getTopY` uses it as its
  guard, and any following `getChunk`/`getBlockState` then **blocks the server thread** until the load finishes.
  Use `ServerChunkManager#getWorldChunk(x, z)`, which returns only chunks that are already fully loaded (or null).
- **`getChunk(x, z, FULL, false)` still waits** on the main thread if a load is already in flight.
- **`getTopY` on an unloaded chunk returns the bottom of the world**, so code that validates positions with it
  silently rejects every unloaded candidate.
- To use a far-away chunk without blocking, add a short-lived ticket (`ChunkTicketType.create(..., expiryTicks)`)
  and retry on a later tick.
- Example: Mine Cells fall protection (`prs/minecells-fall-reset.md`).

## Per-tick work over every entity

- `level.getAllEntities()` in a world tick handler is O(all loaded entities) every tick, including entities in
  chunks that do not tick. Skip non-ticking positions **before** doing any world lookups. Better still, hook the
  entity's own tick so only ticking entities are visited.
- Prefer state the entity already caches (`getFeetBlockState()`, fluid heights) over world queries.
- Example: Create: Testosterone 2.0.3 → 2.0.4 (fixed upstream).

## Allocation and hidden work in hot paths

- `String#replaceAll`/`split(regex)` compile a regex on every call. Use a `static final Pattern`, or plain `indexOf`.
- `stream().toList()` just to iterate allocates a list; iterate the stream or the source directly.
- Compatibility layers that build "views" (maps of wrappers) per call are expensive when polled per tick. Check
  whether a direct API call exists.
- Example: Accessories tclayer (`prs/tclayer-isequipped-backport.md`).

## Before writing a fix

- **Check the newest upstream release and branches first.** Testosterone and tclayer had both already fixed
  their hot spots upstream. Packs were just shipping an old version, or the fix was never backported.
