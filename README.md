# Orcadia fork

The self-contained OrcaSlicer plugin is
[`cloud_plugin-fdb0-3b0d-ec7f-95be18c.py`](./cloud_plugin-fdb0-3b0d-ec7f-95be18c.py).
It includes the Python host wrapper and embedded JavaScript game.

## Meaningful skill levels

Woodcutting, Mining, Fishing, Smithing, Cooking, Firemaking and Crafting gain:

- **+0.5% work rate per level above 1.**
- **+5% permanent work rate at each proficiency milestone:** Apprentice at 25,
  Journeyman at 50, Expert at 75, and Master at 99.

All bonuses are automatic, specific to the skill, and additive:

| Level | Per-level bonus | Proficiency bonus | Total work-rate bonus |
|---|---:|---:|---:|
| 1 | 0% | 0% | 0% |
| 25 | 12% | 5% | 17% |
| 50 | 24.5% | 10% | 34.5% |
| 75 | 37% | 15% | 52% |
| 99 | 49% | 20% | 69% |

Cycle duration is `base ticks / (1 + total bonus / 100)`. For example, a
four-tick recipe at 99 averages about 2.37 ticks, or 1.42 seconds, instead of
2.4 seconds. **+69% work rate does not mean 69% less time.**

Fractional deadlines retain small improvements across cycles instead of rounding
each action to a whole-tick duration. Completion still occurs on game ticks,
with at most one timed action per tick. Existing instant services remain instant.

Gathering gets more rolls, not guaranteed success: existing level-based success
odds, tools, seasons and perks still apply. Walking, node respawns, courier/drop
delays, materials per action, XP per item, cooking/iron failure odds, fire
duration, combat, and pet mechanics are unchanged.

Open a skill guide to see its current benefit, next-level benefit and proficiency
milestones alongside existing recipe/gear unlocks and perks. Skill tooltips,
level-up unlock messages and next-goal chips also show the benefits. Production
recipe tooltips show average cycle time when the recipe is available.

Old characters receive bonuses from their existing levels automatically. The
save version and XP thresholds are unchanged; no reset or migration is needed.
Existing action restoration behavior remains unchanged on reload.

## Bank-fed production

Put ingredients in your bank, carry required tools, open a production station,
enable **Bank-fed: On**, choose **All** (or a finite quantity), and select a
recipe. Anywhere-made recipes use the same toggle on their crafting sheet.

Materials come directly from storage, and normal products, failure products,
perk duplicates and saved ingredients go back there. Jobs stop explicitly when
materials run out or storage cannot fit all possible outputs. Inventory-based
production remains the default. Fire lighting/refuelling are not bank-fed.

Bank-fed jobs run only while the game is open, including background catch-up.
Completed goods and XP persist, but jobs do not resume or produce offline after
closing. Existing inventory jobs retain their normal offline behavior.

## Testing

No npm dependencies are required. With Node.js installed, run:

```powershell
node --test .\tests\bank-production.test.cjs .\tests\skill-progression.test.cjs
```

Tests execute the actual embedded engine and cover progression thresholds,
sustained output, gathering, production, UI view data, save compatibility and
bank-production regressions. The full embedded JavaScript is also syntax-checked.

## Trying the plugin

Close all OrcaSlicer windows, back up your installed plugin and your save, then
replace the installed Python script with this fork's script of the same name.
**Keep backups outside the installed plugin folder:** OrcaSlicer rejects plugin
packages containing multiple Python scripts.

This checkout does not update the installed copy automatically. Subscribed
plugin updates may overwrite local modifications. Do not use Restore defaults
to reload the script; it resets your character.
