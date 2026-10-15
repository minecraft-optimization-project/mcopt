Reduces the server tick cost of the Trinkets compat layer on 1.20.1. On a 365 mod pack (Prominence II) tclayer was 4 to 5% of total server tick time, almost all from `LivingEntityTrinketComponent#isEquipped` and `getInventory()` being called per entity per tick (Artifacts `isEquippedBy` and its `LivingEntity` tick mixin).

### Changes

1. `LivingEntityTrinketComponent#isEquipped` delegates to `WrappedTrinketComponent#isEquipped` (Accessories capability lookup), same as the 1.21 branches after ec2d2d48. The old body iterated `getInventory()`, which rebuilds the wrapped group/slot map on every call. The override is kept instead of removed: Things 0.3.3 has a `@ModifyVariable` at HEAD of this method, and a straight cherry-pick of ec2d2d48 makes that mixin fail and crashes the server. `getEquipped` and `forEach` are unchanged.
2. `ImmutableDelegatingMap#values()` and `#entrySet()` return lazy read-only views instead of collecting a new `toUnmodifiableSet()` per call. Same contents. Iteration order of the old sets was already unspecified.
3. `WrappingTrinketsUtils#filterGroupInfo` replaces `replaceAll("(trinket_group_).*-", "")` with an equivalent `indexOf`/`lastIndexOf` scan, so no regex is compiled per call (reached from `ItemStack#is(TagKey)` via `ItemStackMixin#redirectTags`). Checked against the regex on 2,000,000 generated inputs. `redirectTags` also iterates `getTags()` directly instead of via `toList()`.

### Benchmark

Full Prominence II 4.1.3 server, same seeded world per run, 1,500 mixed mobs in forceloaded chunks, 150 s spark sample per run, 4 runs per side, alternating.

| | beta.14 | this PR |
|---|---|---|
| tclayer, % of tick time | 3.12 to 4.51 (mean 3.77) | 0.62 to 0.80 (mean 0.67) |
| `LivingEntityTrinketComponent#isEquipped`, inclusive | 2.97 to 3.52 | 0.20 to 0.26 |
| tclayer + accessories + artifacts | mean 6.95 | mean 4.08 |

Part of the cost moves into the Accessories capability lookup, which is expected. The change in average tick time over the whole server was within run to run noise for this scenario.

Ran with the full pack (Things, Artifacts, Botania Trinkets integration loaded) with no mixin errors.
