# Fix tracker

Status: `found` → `fix written` → `measured` → `PR open` → `merged` / `released (ours)`.
Cost is the share of server tick time on the profiled server (Prominence II 4.1.3, 7–8 players), unless noted.

| Mod | Version (pack) | Hot spot | Cost | Fix | Status | Links |
|---|---|---|---|---|---|---|
| Accessories (tclayer) | 1.0.0-beta.48+1.20.1 / tclayer 3.8.1-beta.14 | `LivingEntityTrinketComponent.isEquipped` rebuilds the whole wrapped slot map per call; `ImmutableDelegatingMap` snapshots sets per call; regex per call in `filterGroupInfo` | 4.1% + ~0.7% | isEquipped → capability (override kept: Things mixins into it — plain backport of 1.21 `ec2d2d48` crashes); lazy map views; regex → scan. Bench: tclayer 3.12% → 0.80% | measured | branch `perf/1.20.1-tclayer-isequipped`; PR draft `prs/tclayer-isequipped-backport.md` |
| Create: Testosterone | 2.0.3 (pack) / 2.0.4 (upstream) | `fluidEffectHandler.onWorldTick`: world fluid lookup for every living entity, every tick | 5.1% (2.0.3) | **Already fixed upstream in 2.0.4.** Bench: 6.41% (2.0.3) → 1.59% (2.0.4) → 1.43% (2.0.4 + our extra patch, within noise). Action: packs should update to 2.0.4. Our patch not submitted. | upstream fixed | branch `perf/fluid-effect-handler` (parked) |
| Mine Cells | 2.0.0 | Fall-reset `getResetToPos` waits on still-loading checkpoint chunks on the server thread (`isChunkLoaded` is ticket-level only) | 4.27 s freeze | Query only fully loaded chunks (`getWorldChunk`), background-load nearest checkpoint, hold & retry. Bench: worst tick 3,098–4,027 ms → 28 ms | measured | branch `perf/fall-reset-no-sync-chunk-load`; `mcopt-patches` (assets ARR → no fork builds); PR draft `prs/minecells-fall-reset.md` |
| BCLib | 3.0.14 | `ItemPredicate` `isShears` inject on every `inventory_changed` advancement check | 4.8% | Precompute the predicate flag; via `mcopt-patches` if upstream won't take 1.20.1 | found | upstream #239 (closed, fixed in 26.x only) |
| Aquamirae | 7.1.14 | `Level.getRainGradient` inject per ticking chunk | 2.6% | Needs measuring first; no public 1.20.1 source → `mcopt-patches` or issue | found | |
| Artifacts | 9.5.17 | `isEquippedBy` polled per tick (cost lands in tclayer) | (in tclayer) | Re-measure after tclayer fix | found | |
| Simply Swords | 1.70.2 | `HivemindSwarmManager.hasActive` every world tick | 1.4% | Track active swarms | found | |
| Pehkui | 3.8.3 | per-entity scale tick | 2.3% | Low priority | found | |
| Kibe | 1.10.1-BETA | `cannotDespawn` → `hasStatusEffect` per spawn attempt | 0.9% | Reorder checks | found | |
| Derelict | 2.1.0 | `BlockEntityType.supports` mixin | 0.65–2.6% | Investigate | found | |
