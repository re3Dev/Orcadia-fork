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

## The Starless Forge: post-Hollow King expansion

Start with **Astronomer Vesna in Saltmere (126,48)** after completing
**The Hollow King**. Existing saves work without a reset.

1. **Beyond the Crown:** defeat five hollow knights, then bring Vesna three
   starsteel bars and one cut diamond in your pack. Rewards: Starward,
   15,000 Smithing XP, 10,000 Defence XP, three quest points, astral alloy
   smelting, and access to the **Starless stair in Duskhollow (145,134)**.
2. Speak to Vesna again for **The Starless Forge**. Defeat six starbound
   sentinels in the dungeon, pass the northern seal, defeat Astravor, and bring
   its core back to Vesna. Rewards: 20,000 coins, 30,000 XP each in Attack,
   Strength, Defence and Hitpoints, five quest points, and the Starbound signet.
   Recommended combat level: **100**, with strong food and Starward.

Astravor remains available after the quest. It has **620 HP**, a **22 maximum
melee hit**, and a marked **3x3 blast for 20-34 damage after three ticks**.
Step entirely outside the marked area to dodge. Equipping **Starward**
(Defence 60, +55 defence) halves blast damage; merely carrying it does not.
At 180 HP it attacks faster and blasts more frequently. Retreat through the
seal to reset the fight. Its respawn is 250 ticks (150 game seconds), and it
waits until the arena is empty before respawning.

**The boss arena is dangerous, not an unattended/offline farm.** Emergency
AFK rescue is disabled there and catch-up freezes. Reloading during a live
fight returns you to the dungeon's entry chamber; graves are also placed
there. The exit ladder is always usable. Sentinels use normal combat/AFK
rules outside the arena.

### Equipment and smithing

Nightfall and Eventide require **Attack 70**. Astral armour and the signet
require **Defence 70**.

| Item | Attack / strength / defence | Smithing level | Astral alloy cost |
|---|---:|---:|---:|
| Astral gauntlets | 6 / 6 / 14 | 90 | 1 |
| Astral boots | 0 / 0 / 20 | 91 | 1 |
| Astral helm | 0 / 0 / 46 | 92 | 2 |
| Nightfall, one-handed, speed 4 | 70 / 74 / 0 | 94 | 4 |
| Astral greaves | 0 / 0 / 90 | 96 | 3 |
| Eventide, two-handed, speed 7 | 76 / 250 / 0 | 98 | 5 |
| Astral cuirass | 0 / 0 / 140 | 99 | 5 |
| Starbound signet, quest reward | 8 / 8 / 12 | - | - |

At **Smithing 90**, smelt one astral alloy from **two starsteel bars,
three stardust and four coal** at a furnace, after Beyond the Crown.
Forge equipment at an anvil with a carried hammer. All eight production
recipes support bank-fed crafting and skill work-rate bonuses.
Stardust is guaranteed from sentinels (1-2) and Astravor (2-4).

Vesna replaces a lost Starward for the original three bars and cut diamond,
and replaces a lost signet for free after its quest. Replacements are
unavailable while you already own the item, including in storage or a grave.
The Hero's mantle continues to require the **original quests** only;
the expansion does not revoke an existing character's earned cape.
Original NPC spawn IDs and saved respawn timers are unchanged.

### Astravor's drops

Every kill gives **4,000-8,000 coins**, **2-4 stardust**, and one main-table
roll:

| Main drop | Quantity | Weight / 128 |
|---|---:|---:|
| Astral alloy | 1-2 | 30 |
| Starsteel bars | 2-4 | 24 |
| Stormray | 4-6 | 24 |
| Uncut sunstones | 1-2 | 16 |
| Astral greaves | 1 | 12 |
| Astral cuirass | 1 | 10 |
| Astral helm | 1 | 6 |
| Astral gauntlets | 1 | 6 |

Additional, independent rolls: **Nightfall 1/50**, **Eventide 1/80**,
and the **Star mote pet 1/200** while unowned. Star mote has base attack 60,
base max hit 6 and Keen (+25% accuracy), growing into an Astral wisp and
then a Void lantern. The quest core is guaranteed while needed, including
if lost before turn-in; already owning a core prevents another drop.

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
node --test .\tests\bank-production.test.cjs .\tests\skill-progression.test.cjs .\tests\starless-forge.test.cjs
```

Tests execute the actual embedded engine and cover progression thresholds,
sustained output, gathering, production, UI view data, save compatibility and
bank-production regressions. Expansion tests cover quest turn-ins and recovery,
map connectivity and locks, boss telegraphs/dodging/wards/reset/respawn, a first
kill using existing gear, drops, crafting, equipment requirements and legacy saves.
The full embedded JavaScript is also syntax-checked.

## Trying the plugin

Close all OrcaSlicer windows, back up your installed plugin and your save, then
replace the installed Python script with this fork's script of the same name.
**Keep backups outside the installed plugin folder:** OrcaSlicer rejects plugin
packages containing multiple Python scripts.

This checkout does not update the installed copy automatically. Subscribed
plugin updates may overwrite local modifications. Do not use Restore defaults
to reload the script; it resets your character.
