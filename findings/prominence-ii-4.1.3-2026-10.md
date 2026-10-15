# Prominence II server: performance findings for follow-up PRs

Findings from profiling a live
**Prominence II: Hasturian Era 4.1.3** server (Minecraft **1.20.1**, **Fabric Loader 0.19.3**, Fabric API 0.92.12,
Java **21** Temurin 21.0.12.1, 365 mods). The goal is to **reproduce, write and test fixes** that can be opened
as upstream PRs (or issues, where no source is public).

Collected 2026-10-14. Every number below can be re-derived from the raw profiles in `profiles/` with the scripts in `tools/`.

## Ground rules

- **Never test on a live server.** Use a separate copy of the pack (see `tools/bench`).
- Build fixes against the **exact branch/version** listed for each mod. The pack pins old 1.20.1 versions, and several upstreams have since moved on.
- Measure before and after with spark under comparable load. See [How to verify a fix](#how-to-verify-a-fix).
- "Confidence" marks what was confirmed by reading source or disassembling the installed jar versus what was inferred from the profile alone.

## Folder contents

| Path | What |
|---|---|
| `profiles/jwolv23adY_5players.sparkprofile` | Raw spark sampler data, 10 min, 5 players. Viewer: https://spark.lucko.me/jwolv23adY |
| `profiles/P2ZK5zK77O_7-8players.sparkprofile` | Raw spark sampler data, 10 min, 7–8 players, **contains a 4.27 s freeze**. Viewer: https://spark.lucko.me/P2ZK5zK77O |
| `reports/*.by-mod.txt` | Tick time per mod (with pass-through wrappers removed), per entity type, and hot frames inside each top mod |
| `reports/*.windows-and-spike.txt` | Per-minute stats (players, entities, chunks, TPS, MSPT median/max) plus frames over-represented in the worst minute |
| `reports/P2ZK5zK77O_7-8players.callers.txt` | Caller chains and callees for each candidate hot spot |
| `tools/` | Python 3 (stdlib only) spark protobuf decoder and analyzers. See below |
| `mappings/yarn-1.20.1+build.10.tiny` | Yarn mappings used to turn `class_XXXX`/`method_XXXX` into readable names |
| `server/mods.tsv` | All 367 mod entries: id, version, jar filename, source URL, authors (from each jar's `fabric.mod.json`) |
| `server/` (other files) | Current JVM args, server.properties (secrets stripped), ServerCore config, Immersive Optimization config, Fabric dependency override |

Raw profiles can also be re-downloaded: `curl -o x.sparkprofile https://spark-usercontent.lucko.me/<id>` (content type `application/x-spark-sampler`, protobuf).

## Tools

```sh
M=mappings/yarn-1.20.1+build.10.tiny
python3 -I tools/report.py  profiles/<file> $M [top_n_mods]        # per-mod / per-entity breakdown, Yarn names
python3 -I tools/windows.py profiles/<file> $M [window_index]      # per-minute stats + spike-window frame diff
python3 -I tools/callers.py profiles/<file> $M "<substring>" ...   # caller chains + callees for matching frames
```

Notes:
- Only the `Server thread` is analyzed. Percentages are of **busy tick time**, meaning time inside `MinecraftServer.tickServer`, not wall time. The server idles between ticks.
- `report.py` treats `neruina` (an exception-catching wrapper around every entity tick), `fabric-*` event plumbing, `architectury`, `mixinextras` and `cardinal-components*` as pass-through, so their time is credited to the mod that actually does the work. Neruina's own handler is literally named `notTheCauseOfTickLag`.
- Mixin handlers are attributed by parsing names like `handler$abc000$<modid>$<method>`.
- `windows.py` uses spark's per-minute `time_window_statistics`. Its "chunks" figure is spark's own count and may include chunk holders, not only fully loaded chunks.

## Load context

| Profile | Players | Busy | Avg tick | Spikes >150 ms (tick monitor) |
|---|---|---|---|---|
| jwolv23adY | 5 | 31% of wall | 15.7 ms | 2 (185 ms, 254 ms) |
| P2ZK5zK77O | 7–8 | 45% of wall | 22.5 ms | 9, including **4271 ms at 22:37:38** and 1175 ms at 22:37:33 (local time, UTC−7) |

Profile 2 per-minute stats: 2,600–3,300 entities and 26,000–29,000 chunks (spark count). Server tuning in place
during both profiles: G1 with Aikar flags, 12 GB heap, view distance 8 / simulation distance 6, ServerCore dynamic mode, Immersive Optimization
entity culling, Lithium, FerriteCore and ModernFix. See `server/`.

## Findings, ranked by payoff and ease

Percentages are from profile 2 (7–8 players) unless noted.

### 1. Accessories trinkets layer ("tclayer") + Artifacts: ~4–5.6% of tick time

- **Profile:** `LivingEntityTrinketComponent.isEquipped` [tclayer] = 4.10%, of which 4.05% is called from Artifacts
  `FabricPlatformHelper.isEquippedBy` <- `PlatformHelper.isEquippedBy`. Inside it, 3.35% is `ImmutableDelegatingMap.entrySet`.
  The tclayer `ItemStack.<mixin redirectTags>` adds ~0.7% and shows `java.util.regex.Pattern` frames.
- **Source (confidence: read on branch, not mapped to exact jar build):**
  - Artifacts [`FabricPlatformHelper.java#L43`](https://github.com/ochotonida/artifacts/blob/1.20.1/fabric/src/main/java/artifacts/fabric/platform/FabricPlatformHelper.java#L43):
    `TrinketsApi.getTrinketComponent(entity).map(c -> c.isEquipped(predicate)).orElse(false)`, with no caching.
    It is polled per tick or per movement for any LivingEntity by Aqua Dashers (`isRunningWithAquaDashers`), Flippers (swim speed),
    Snowshoes (`getModifiedFriction`, `PowderSnowBlockMixin`), Rooted Boots, Obsidian Skull, Onion Ring, Pickaxe Heater, and Kitty Slippers (creeper `AvoidEntityGoal`).
  - tclayer, in [wisp-forest/accessories `1.20.1-Backport`, folder `tclayer/`](https://github.com/wisp-forest/accessories/tree/1.20.1-Backport/tclayer/src/main/java):
    - `WrappedTrinketComponent.getInventory()` builds a new `ImmutableDelegatingMap.trinketComponentView(...)` on every call.
    - `ImmutableDelegatingMap.entrySet()` streams the backing map, maps every key and value (new group maps and wrapper inventories), and collects into `Collectors.toUnmodifiableSet()`. The whole slot tree is allocated and hashed per call.
    - The key mapper `accessoriesToTrinkets_Slot` -> `filterGroupInfo` calls `trinketType.replaceAll("(trinket_group_).*-", "")`, which compiles a regex on every call.
    - `ItemStackMixin.redirectTags` (HEAD of `ItemStack.is(TagKey)`) runs this path for any `accessories:`/`trinkets:` tag and builds `getTags().toList()` each time.
- **Fix ideas:**
  - tclayer:
    - Make `filterGroupInfo` use a `static final Pattern`, or better, `startsWith("trinket_group_")` plus `indexOf('-')`.
    - Make `entrySet()` a lazy `AbstractSet` view.
    - Cache the wrapped view per component and invalidate it on slot or container change, or implement `isEquipped` directly against Accessories containers.
    - Iterate `getTags()` without `toList()`.
  - Artifacts: cache equipped state per entity per tick, or use Accessories' native API when present.
- **Upstream:** no issue or PR found for this hot spot. Related: Accessories [#269](https://github.com/wisp-forest/accessories/issues/269) (TPS, different cause),
  [PR #399](https://github.com/wisp-forest/accessories/pull/399) (perf, 1.21.9 only), Artifacts [#382](https://github.com/ochotonida/artifacts/issues/382) (closed),
  [PR #323](https://github.com/ochotonida/artifacts/pull/323) (closed). The 1.21.x tclayer code was not checked.
- **Installed:** `accessories-fabric-1.0.0-beta.48+1.20.1.jar`, `accessories_tclayer-3.8.1-beta.14+1.20.1.jar`, and the Artifacts version is in `server/mods.tsv`.

### 2. Create: Testosterone: ~5% of tick time

- **Profile:** `fluidEffectHandler.onWorldTick` = 5.08%, via the Fabric `END_WORLD_TICK` event, then `applyPotionEffect` 4.84%.
  Hottest frames inside it: `PalettedContainer.get`, `WorldChunk.getFluidState`, `ChunkHolder.getFutureByStatus`. The cost is constant, whether or not anyone uses the fluids.
- **Source (confidence: read on branch):** [`fluidEffectHandler.java` @ `2.0.0-fabric`](https://github.com/mifort-github/createTestosterone/blob/2.0.0-fabric/src/main/java/net/mifort/testosterone/events/fluidEffectHandler.java).
  Every tick: `for (Entity entity : level.getAllEntities()) if (entity instanceof LivingEntity living) applyPotionEffect(living);`.
  Each call does `isPositionEntityTicking(...)` and then `level.getFluidState(entity.blockPosition())`.
- **Fix ideas:**
  - Run every 10 ticks (`if (level.getGameTime() % 10 != 0) return;`). The applied effects last 20 ticks, so they won't lapse.
  - Skip entities not touching the mod's fluids, using vanilla's cached per-entity fluid heights (`getFluidHeight(<fluid tag>)`) instead of a world lookup.
  - Probably about a 10-line PR.
- **Upstream:** the NeoForge `master` branch already rewrote this as a per-entity tick using `isInFluidType`. There is no Fabric 1.20.1 backport. No perf issue or PR found.
- **Installed:** `testosterone-2.0.3.jar` (plus `testosterone-tweaks-1.0.0.jar`, a separate tweak mod).

### 3. Mine Cells: caused the 4.27 s freeze, plus ~1.5% steady

- **Profile:** in the freeze minute (window 1 of profile 2) these frames run about 1.8 s over their per-minute average:
  `Entity.<mixin minecells:injectTick>` -> `Entity.minecells$getResetToPos` -> Stream `.min()` -> `World.getBlockState` ->
  `ServerChunkManager.getChunkBlocking` -> `ThreadExecutor.waitForTasks`. That is a **synchronous chunk load or generation on the main thread**. It runs from `PlayerEntity.tick`.
  See `reports/P2ZK5zK77O_7-8players.windows-and-spike.txt`.
- **Source (confidence: read on branch):** [`mixin/entity/EntityFallResetMixin.java` @ `minecells-2.0.0+1.20.1`](https://github.com/mim1q/MineCells/blob/minecells-2.0.0%2B1.20.1/src/main/java/com/github/mim1q/minecells/mixin/entity/EntityFallResetMixin.java).
  - `injectTick` (L92-153) runs every 2nd tick. It only does anything in the **Ramparts** dimension, for entities ≥4 blocks from `dimensionTpPos` (hostiles are killed instead).
  - Players below Y 180 call `getResetToPos()` (L169-193). It takes the grid special points for the 1024-block cell, maps CHECKPOINTs to `getTopY(...)`, filters with `getBlockState(it.down())`, and returns `.min(...)`.
  - Those points can be up to ~1024 blocks away, in unloaded or ungenerated chunks, which forces a sync load. If the teleport doesn't get the player above Y 180, it repeats every 2 ticks.
- **Fix ideas:**
  - Skip candidates whose chunk isn't loaded (`world.isChunkLoaded(...)` / `getChunk(x, z, FULL, false)`) before `getTopY`/`getBlockState`.
  - Cache the result per player or per 1024-cell.
  - Add a retry cooldown (for example 40 ticks).
  - Fall back to the dimension entrance.
- **Upstream:** branch `1.20.x` replaced this with `getTeleportPosition(...)`, with a comment saying the scan was "disabled due to some bugs". It wasn't verified whether that version still loads chunks. Branch `minecells-2.0.0+1.21.1` still calls `getResetToPos` (L162). No issue or PR found. Related: [#128](https://github.com/mim1q/MineCells/issues/128) (all dimensions stay loaded), [#119](https://github.com/mim1q/MineCells/issues/119).
- **Open question, unexplained:** `LeapingZombieEntity.<init>` -> `MineCellsEntity.<init>` costs ~1.5%, from `SpawnHelper.createMob` during natural spawning,
  with native `sched_yield`/libc frames, which points to lock contention. The Mine Cells constructors are trivial ([`MineCellsEntity.java#L59`](https://github.com/mim1q/MineCells/blob/minecells-2.0.0%2B1.20.1/src/main/java/com/github/mim1q/minecells/entity/MineCellsEntity.java#L59)),
  so the cause is likely vanilla `HostileEntity` setup or **another mod's mixin on `Entity`/`MobEntity.<init>`**.
  Needs a profile with full stacks under `<init>` (spark `--not-combined`, or async-profiler with `-e lock`) to identify.

### 4. BCLib: ~4.8% of tick time

- **Profile:** `ItemPredicate.<mixin bclib:isShears>` = 4.82%. 4.61% of it comes from `ItemPredicate.test` <- `InventoryChangedCriterion$Conditions.matches`
  <- `AbstractCriterion.trigger` (the `inventory_changed` advancement trigger, which fires on every inventory change and is checked against every advancement in the pack).
  Under the handler, 3.61% is `SingletonImmutableSet.contains`.
- **Source (confidence: high, the installed `bclib-3.0.14.jar` was disassembled and matches the branch):**
  [`ItemPredicateBuilderMixin.java` @ `1.20`](https://github.com/quiqueck/BCLib/blob/1.20/src/main/java/org/betterx/bclib/mixin/common/shears/ItemPredicateBuilderMixin.java).
  ```java
  @Inject(method = "matches", at = @At("HEAD"), cancellable = true)
  void bclib_isShears(ItemStack itemStack, CallbackInfoReturnable<Boolean> info) {
      if (this.items != null && this.items.size() == 1 && this.items.contains(Items.SHEARS)) {
          if (itemStack.is(CommonItemTags.SHEARS)) info.setReturnValue(true);
      }
  }
  ```
  Each call is cheap. The cost is call volume, plus a `CallbackInfoReturnable` allocation per call.
- **Fix ideas:**
  - Precompute `bclib$isShearsPred` once in `@Inject(method="<init>", at=@At("RETURN"))`, so the hot path becomes `if (bclib$isShearsPred && itemStack.is(SHEARS))`.
  - Optionally switch to MixinExtras `@ModifyReturnValue`, only checking the tag when the vanilla result is false, to drop the per-call CIR allocation.
- **Upstream:** [#239](https://github.com/quiqueck/BCLib/issues/239) "Server Freeze/lag during itempredicate.test > …bclib$isShears" was closed as a duplicate on 2026-10-10. The maintainers say the check was reworked in the 26.x releases, and there's no 1.20.1 backport. [#233](https://github.com/quiqueck/BCLib/issues/233) is related. **The maintainers may not accept a 1.20.1 PR.** A standalone fix mod or pack-side mixin is an alternative.

### 5. Aquamirae: ~2.6% of tick time

- **Profile:** `World.<mixin aquamirae:modifyRainLevel>` = 2.62% self time. 2.53% comes from `World.getRainGradient` <- `World.isRaining` <- `ServerWorld.tickChunk` (once per ticking chunk per tick).
- **Source (confidence: high, disassembled from the installed `aquamirae-fabric-1.20.1-7.1.14.jar`, class `dev.obscuria.aquamirae.mixin.MixinLevel`):**
  the handler is a cancellable inject on `getRainGradient(float)`. It does `this.getDimensionEntry().matchesKey(AquamiraeRegion.THE_MAELSTROM_TYPE)` and returns early unless it's the Maelstrom.
  In the Maelstrom it computes a time-of-day rain curve (`aquamirae$rainLevelByWindow`).
  The cost per call is the CIR allocation plus a holder lookup and key compare, multiplied by thousands of calls per tick.
- **Fix ideas:** cache "is the Maelstrom" in a `@Unique` boolean per Level (the dimension type never changes), and use `@ModifyReturnValue` so no callback object is allocated.
- **Upstream:** **no public 1.20.1 source.** The repo [ObscuriaLithium/aquamirae](https://github.com/ObscuriaLithium/aquamirae) only has `1.21.1`, `legacy/*` (the only Fabric one is `legacy/6.0.0-fabric-1.20.1`) and tags v7.2.4–v7.2.7. The 1.21.1 `MixinLevel` no longer has this handler.
  This is an **issue for the author**, not a PR (or a separate fix mod).

### Smaller items (each under ~2.3%)

| Mod | Profile cost | Where | Notes / idea |
|---|---|---|---|
| Pehkui 3.8.3 | 2.3% (`<mixin pehkui:tick>`), 1.6% in `Entity.pehkui_getScaleData` | every entity tick, tracker tick | Mature mod. Mostly the inherent cost of scale data per entity. Low priority. Repo: https://github.com/Virtuoel/Pehkui |
| Simply Swords 1.70.2 | 1.4% `HivemindSwarmManager.hasActive` via `ServerWorld.<mixin simplyswords:tickFieldManagers>` | every world tick | Looks like it iterates all entities to find active swarms. Track active swarms in a set instead. Repo: https://github.com/Sweenus/SimplySwords-1.19 |
| Kibe 1.10.1-BETA | 0.94% `MobEntity.<mixin kibe:cannotDespawn>` -> `LivingEntity.hasStatusEffect` | `SpawnHelper.setupSpawn` (every spawn attempt) | Reorder or cheapen the check. Repo: https://github.com/lucaargolo/kibe |
| Simply Skills -> Pufferfish's Skills | 0.61% `SkillImpl.getState` | `ServerPlayerEntity.<mixin simplyskills:tick>` -> `HelperMethods.isUnlocked` | Cache unlocked state per player and update it on skill change. Simply Skills source not looked up |
| Derelict 2.1.0 | 0.65% (profile 2), 2.6% (profile 1) `BlockEntityType.<mixin derelict:supports>` | every block-entity validity check | Not investigated. Repo: https://github.com/mim1q/derelict |

### Context, not mod bugs

- Entity ticking is about 47% of busy time. Profile 2 by type: ServerPlayerEntity 17.6% plus PlayerEntity 8.8% (8 players, which is heavy because of accessory, scale and skill mods on players), vanilla `MobEntity` 4.5%, villagers 2.8%, zombies 2.8%, skeletons 2.3%. Natural spawning is about 12% (profile 1).
- Lithium shows ~6.5% but that is its own optimized implementations doing vanilla work, not overhead.

## How to verify a fix

1. **Test server:** copy the server folder, or install the Prominence II 4.1.3 server pack. `server/mods.tsv` lists every jar.
   Use the same Java 21 and JVM args (`server/user_jvm_args.txt`, plus `-Xms12288M -Xmx12288M` on the command line).
2. **Reproduce the workload:** most hot spots scale with loaded entities and players. Options:
   - Bots: a headless client such as Mineflayer can't join a modded Fabric server without the mods, so the reliable path is a real client, or a load test with `/summon` entities and forceloaded chunks.
   - Mine Cells: put a player in the Ramparts dimension below Y 180, with the checkpoint chunks unloaded, to trigger the sync chunk load.
   - BCLib: trigger frequent inventory changes (picking up and dropping items) with all pack advancements loaded.
   - Testosterone: has a constant cost proportional to loaded living entities, so it's easy to measure with many summoned mobs.
3. **Measure:** run `spark profiler start --timeout 300` before and after on the same scenario, then run `tools/report.py` on both and compare the mod's share and its hot frames. For micro-level validation, JMH or a simple timing harness around the patched method also works.
4. **Correctness:** keep behavior identical. For Testosterone, check the effects still apply. For Artifacts and tclayer, check equipped-item effects still activate and deactivate immediately on equip or unequip.

## Related server issue (not a PR target yet)

On 2026-10-14 at 21:48 a normal `stop` hung in `MinecraftServer.stopServer`'s "wait until no chunk work" loop, before the final save.
A heap histogram showed **7,956 `WorldChunk` / 8,116 `ChunkHolder` instances with only 4 `ChunkTicketManager` tickets**, and the counts didn't change over 30 s, so the server had to be killed.
The cause is unidentified. A possible link is the Mine Cells issue [#128](https://github.com/mim1q/MineCells/issues/128) ("all dimensions stay loaded"), or chunks pinned by some mod.
The idle baseline right after a clean boot is 9 `WorldChunk` / 625 `ChunkHolder`. If an investigation reproduces the hang, capture `jstack` plus `jcmd <pid> GC.class_histogram`, and if possible a heap dump, to find what holds the chunks.
