const assert = require("node:assert/strict");
const { test } = require("node:test");
const { loadEngine } = require("./engine-fixture.cjs");

const tiers = { bronze: 1, iron: 10, steel: 20, cobalt: 30, verdite: 40, emberite: 55, starsteel: 70 };
const offsets = { axe: 0, dagger: 1, sword: 2, pickaxe: 3, helm: 4, mace: 5,
  shield: 6, greatsword: 7, greaves: 8, breastplate: 10 };
const astral = { smelt_astral_alloy: 80, smith_astral_gauntlets: 80, smith_astral_boots: 81,
  smith_astral_helm: 82, smith_nightfall: 83, smith_astral_greaves: 83,
  smith_eventide: 84, smith_astral_cuirass: 85 };
const levels = { ...astral };
for (const [metal, base] of Object.entries(tiers)) {
  levels["smelt_" + metal] = base;
  for (const [kind, offset] of Object.entries(offsets)) levels["smith_" + metal + "_" + kind] = base + offset;
}

function fixture(rid, level, bankFeed) {
  const api = loadEngine();
  const state = api.Engine.createState(12345);
  const p = state.player;
  p.map = "overworld";
  p.x = p.px = p.mx = 44;
  p.y = p.py = p.my = 45;
  p.inv.fill(null);
  p.xp10.smithing = api.Rules.xpForLevel(level) * 10;
  p.quests.beyond_crown = 100;
  const r = api.Data.recipes[rid];
  if (bankFeed) p.bank = r.in.map(([id, qty]) => ({ id, qty }));
  else for (const [id, qty] of r.in) api.Player.add(p, id, qty);
  for (const tool of r.tools) api.Player.add(p, tool, 1);
  api.Sim.setObj(state, p.map, 45, 45, r.at[0], 100000);
  assert.equal(api.Script.openMake(state, r.at[0], api.Util.refObj(45, 45)), true);
  assert.equal(api.Engine.setMakeBankFeed(state, bankFeed), true);
  return { ...api, state, p, r };
}

test("all metal and astral recipes have the exact rebalanced unlock levels", () => {
  const { Data } = loadEngine();
  for (const [rid, level] of Object.entries(levels)) assert.equal(Data.recipes[rid].lvl, level, rid);
  assert.equal(Data.recipes.smelt_gold.lvl, 40);
  assert.equal(Data.recipes.smith_emberward.lvl, 35);
});

test("every changed recipe rejects one level below and produces at its threshold in pack and bank modes", () => {
  for (const bankFeed of [false, true]) {
    for (const [rid, level] of Object.entries(levels)) {
      const f = fixture(rid, Math.max(1, level - 1), bankFeed);
      if (level > 1) {
        const before = JSON.stringify([f.p.inv, f.p.bank, f.p.xp10]);
        const row = f.Engine.view.make(f.state).rows.find(row => row.rid === rid);
        assert.equal(row.lvl, level, rid);
        assert.equal(row.ok, false, rid);
        assert.equal(f.Engine.make(f.state, rid, 1), false, rid);
        assert.equal(JSON.stringify([f.p.inv, f.p.bank, f.p.xp10]), before, rid);
      }
      f.p.xp10.smithing = f.Rules.xpForLevel(level) * 10;
      assert.equal(f.Engine.view.make(f.state).rows.find(row => row.rid === rid).ok, true, rid);
      // Isolate unlocks from iron's unchanged random smelting failure.
      if (rid === "smelt_iron") f.Rules.makeChance = () => 1;
      const beforeXp = f.p.xp10.smithing;
      assert.equal(f.Engine.make(f.state, rid, 1), true, rid);
      for (let i = 0; i < 8; i++) f.Engine.tick(f.state);
      for (const [id, qty] of f.r.out) {
        assert.equal(bankFeed ? f.Player.bankCount(f.p, id) : f.Player.count(f.p, id), qty, rid);
      }
      for (const [id] of f.r.in) {
        assert.equal(bankFeed ? f.Player.bankCount(f.p, id) : f.Player.count(f.p, id), 0, rid);
      }
      assert.equal(f.p.xp10.smithing - beforeXp, f.r.xp * 10, rid);
      assert.deepEqual(Array.from(f.Engine.check(f.state)), [], rid);
    }
  }
});

test("guides and level-up unlocks use the new recipe thresholds", () => {
  const f = fixture("smith_starsteel_breastplate", 80, false);
  const rows = f.Engine.view.guide(f.state, "smithing").rows;
  for (const [rid, level] of Object.entries(levels)) {
    const icon = f.Data.recipes[rid].out[0][0];
    const row = rows.find(row => row.icon === icon);
    assert.equal(row.lvl, level, rid);
    assert.equal(row.ok, level <= 80, rid);
    assert.ok(f.Engine.view.unlocks("smithing", level).includes(row.name), rid);
  }
  assert.ok(f.Engine.view.goal(f.state, "smithing").names.includes("Astral boots"));
});

test("Fallen Star quest requirements and Vesna's offer agree at Smithing 70 and Mining 80", () => {
  const f = fixture("smelt_starsteel", 69, false);
  f.p.quests.beyond_crown = 0;
  f.p.quests.embers_beneath = 100;
  f.p.xp10.mining = f.Rules.xpForLevel(80) * 10;
  const quest = f.Data.quests.fallen_star;
  const offer = f.Data.dialogues.vesna.nodes.root.branch.find(branch => branch.go === "offer");
  const eligible = conditions => conditions.every(condition => f.Script.test(f.state, condition));
  assert.equal(eligible(quest.reqs), false);
  assert.equal(eligible(offer.if), false);
  f.p.xp10.smithing = f.Rules.xpForLevel(70) * 10;
  assert.equal(eligible(quest.reqs), true);
  assert.equal(eligible(offer.if), true);
  assert.ok(quest.reqText.includes("Smithing 70"));
  assert.match(quest.journal[20], /Smithing 70/);
  assert.match(quest.rewards.lines[0], /70 to 80/);
  f.p.xp10.mining = f.Rules.xpForLevel(79) * 10;
  assert.equal(eligible(quest.reqs), false);
  assert.equal(eligible(offer.if), false);
});

test("astral alloy keeps its quest gate at the new level 80 threshold", () => {
  const f = fixture("smelt_astral_alloy", 80, false);
  f.p.quests.beyond_crown = 0;
  assert.equal(f.Engine.make(f.state, "smelt_astral_alloy", 1), false);
  f.p.quests.beyond_crown = 100;
  assert.equal(f.Engine.make(f.state, "smelt_astral_alloy", 1), true);
});

test("a saved level-80 smith can craft the starsteel breastplate without resetting XP", () => {
  const f = fixture("smith_starsteel_breastplate", 80, false);
  const xp = f.p.xp10.smithing;
  const saved = f.Engine.serialize(f.state);
  assert.equal(saved.v, 1);
  const restored = f.Engine.deserialize(saved);
  assert.equal(restored.player.xp10.smithing, xp);
  f.Script.openMake(restored, "anvil", f.Util.refObj(45, 45));
  assert.equal(f.Engine.make(restored, "smith_starsteel_breastplate", 1), true);
  for (let i = 0; i < 8; i++) f.Engine.tick(restored);
  assert.equal(f.Player.count(restored.player, "starsteel_breastplate"), 1);
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
});
