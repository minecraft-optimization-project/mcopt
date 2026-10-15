# Accessories (tclayer, 1.20.1): Make Trinkets isEquipped and inventory views cheap

**Target:** `wisp-forest/accessories` branch `1.20.1-Backport`
**Branch:** `minecraft-optimization-project/accessories:perf/1.20.1-tclayer-isequipped` (3 commits on `59869f4f`, beta.48)
**Status:** draft, not opened

---

Hi! Profiling a 365-mod 1.20.1 server (Prominence II) showed the Trinkets compat layer at **~4–5% of total server tick time**. The cost comes from Trinkets API calls that Artifacts makes for every living entity every tick:

- `LivingEntityTrinketComponent#isEquipped`, via Artifacts `isEquippedBy`
- `getInventory().values()`, via the Artifacts `LivingEntity` tick mixin

### Changes

1. **`isEquipped` delegates to the Accessories capability** (`WrappedTrinketComponent#isEquipped`), as the 1.21 branches already do (`ec2d2d48`).
   - The old body iterated `getInventory()`, which rebuilds the whole wrapped group/slot map and hashes it into new sets on every call.
   - The override is **kept, not removed**. We first tried a straight cherry-pick of `ec2d2d48`, and it crashes with **Things** 0.3.3: Things `@ModifyVariable`s the predicate at HEAD of `LivingEntityTrinketComponent#isEquipped` and `@ModifyArg`s inside `getEquipped`. Keeping the method keeps those mixins working. `getEquipped`/`forEach` are unchanged; the Trinkets `forEach` contract also visits empty slots.
2. **`ImmutableDelegatingMap#values()`/`entrySet()` return lazy read-only views** instead of collecting a fresh `toUnmodifiableSet()` snapshot per call. The contents are the same. The old sets' iteration order was unspecified (randomized per JVM run).
3. **`WrappingTrinketsUtils#filterGroupInfo`** no longer compiles a regex per call. It's reached from `ItemStack#is(TagKey)` via `ItemStackMixin#redirectTags`. The equivalent `indexOf`/`lastIndexOf` scan was fuzz-tested against the regex on 2,000,000 generated slot names. `redirectTags` also iterates `getTags()` directly instead of collecting it into a list.

### Results

Full Prominence II pack on a test server, identical seeded world, 1,500 mixed mobs, 150 s spark profile per side:

| | beta.14 (released) | This PR |
|---|---|---|
| tclayer share of server tick time | 3.12% | **0.80%** |
| `LivingEntityTrinketComponent#isEquipped` (inclusive) | 2.97% | **0.20%** |
| tclayer + accessories + artifacts combined | 5.81% | **4.35%** |

Tested in game on the same pack: no mixin failures, and the server runs normally with Things, Artifacts and Botania's Trinkets integration loaded.
