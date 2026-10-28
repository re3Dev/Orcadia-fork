const assert = require("node:assert/strict");
const { test } = require("node:test");
const { loadEngine } = require("./engine-fixture.cjs");

function fixture(skill, level) {
  const api = loadEngine();
  const state = api.Engine.createState(12345);
  const p = state.player;
  p.map = "overworld";
  p.x = p.px = p.mx = 44;
  p.y = p.py = p.my = 45;
  p.inv.fill(null);
  p.xp10[skill] = api.Rules.xpForLevel(level) * 10;
  return { ...api, state, p };
}

function tick(f, n) {
  for (let i = 0; i < n; i++) f.Engine.tick(f.state);
}

function production(level, rid = "smelt_bronze") {
  const f = fixture("smithing", level);
  const r = f.Data.recipes[rid];
  f.p.xp10[r.skill] = f.Rules.xpForLevel(level) * 10;
  r.xp = 0;
  r.xp2 = null;
  r.if = null;
  r.full = 1;
  f.p.bank = r.in.map(([id, n]) => ({ id, qty: n * 1000 }));
  r.tools.forEach(tool => {
    const id = Object.keys(f.Data.items).find(id => f.Data.items[id].tool?.cat === tool);
    assert.ok(id);
    f.Player.add(f.p, id, 1);
  });
  const station = r.at[0];
  if (station) f.Sim.setObj(f.state, f.p.map, 45, 45, station, 100000);
  f.p.iface = { t: "make", at: station ? f.Util.refObj(45, 45) : null, rids: [rid] };
  assert.equal(f.Engine.setMakeBankFeed(f.state, true), true);
  assert.equal(f.Engine.make(f.state, rid, -1), true);
  return { ...f, r };
}

function gathering(skill, level) {
  const f = fixture(skill, level);
  const oid = { woodcutting: "tree", mining: "copper_rock", fishing: "spot_net" }[skill];
  const op = f.Data.objects[oid].ops[0];
  op.yields = [op.yields[0]];
  f.Sim.setObj(f.state, f.p.map, 45, 45, oid, 100000);
  const tool = Object.keys(f.Data.items).find(id => {
    const t = f.Data.items[id].tool;
    return t && t.cat === op.tool && (!t.lvl || t.lvl <= level);
  });
  f.Player.add(f.p, tool, 1);
  let rolls = 0;
  f.Rules.gatherChance = () => { rolls++; return 0; };
  assert.equal(f.Engine.act(f.state, f.Util.refObj(45, 45), op.id), true);
  tick(f, 1);
  assert.equal(f.p.act.k, "gather");
  return { ...f, op, rolls: () => rolls };
}

test("every level improves all seven work skills, including between recipe unlocks", () => {
  const { Rules } = loadEngine();
  assert.equal(Rules.WORK_SKILLS.length, 7);
  for (const skill of Rules.WORK_SKILLS) {
    assert.equal(Rules.workRate(skill, 1), 1);
    for (let level = 2; level <= 99; level++) {
      const previous = Rules.workRate(skill, level - 1);
      const current = Rules.workRate(skill, level);
      const milestone = [25, 50, 75, 99].includes(level);
      assert.ok(Math.abs(current - previous - (milestone ? 0.055 : 0.005)) < 1e-12);
      assert.ok(Rules.workTicks(skill, level, 4) < Rules.workTicks(skill, level - 1, 4));
    }
  }
});

test("milestones award additive permanent bonuses at the exact thresholds", () => {
  const { Rules } = loadEngine();
  for (const [level, bonus] of [[1, 0], [24, 11.5], [25, 17], [49, 29], [50, 34.5],
    [74, 46.5], [75, 52], [98, 63.5], [99, 69]]) {
    assert.equal(Rules.workBonus(level), bonus);
    assert.equal(Rules.workRate("smithing", level), 1 + bonus / 100);
  }
  assert.equal(Rules.workRate("smithing", 100), 1.69);
});

test("combat timing and instant services are not accelerated", () => {
  const { Rules } = loadEngine();
  for (const skill of ["attack", "strength", "defence", "hitpoints"]) {
    assert.equal(Rules.workRate(skill, 99), 1);
    assert.equal(Rules.workTicks(skill, 99, 4), 4);
  }
  assert.equal(Rules.workTicks("crafting", 99, 0), 0);
  assert.equal(Rules.workTicks("smithing", 99, 1), 1);
});

test("actual sustained output matches the rate, including level 2's fractional improvement", () => {
  for (const [level, expected] of [[1, 200], [2, 201], [24, 223], [25, 234], [49, 258],
    [50, 269], [74, 293], [75, 304], [98, 327], [99, 338]]) {
    const f = production(level);
    tick(f, 800);
    assert.equal(f.Player.bankCount(f.p, "bronze_bar"), expected, "level " + level);
    assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
  }
});

test("smithing, cooking and made-anywhere crafting share the adjusted timing", () => {
  for (const rid of ["smelt_bronze", "cook_raw_shrimp", "craft_leather_gloves"]) {
    const f = production(99, rid);
    tick(f, 600);
    const count = Math.floor(600 * 1.69 / f.r.ticks + 1e-7);
    assert.equal(f.Player.bankCount(f.p, f.r.out[0][0]), count, rid);
  }
});

test("firemaking uses the same work rate without changing fire duration or XP per log", () => {
  const f = fixture("firemaking", 99);
  const r = f.Data.recipes.burn_logs;
  f.Player.add(f.p, "logs", 20);
  f.Sim.setObj(f.state, f.p.map, 45, 45, "fire", 1000);
  f.p.iface = { t: "make", at: f.Util.refObj(45, 45), rids: ["burn_logs"] };
  const before = f.p.xp10.firemaking;
  assert.equal(f.Engine.make(f.state, "burn_logs", 5), true);
  tick(f, 18);
  assert.equal(f.Player.count(f.p, "logs"), 15);
  assert.equal(f.p.act, null);
  assert.equal(f.p.xp10.firemaking - before, 5 * r.xp * 10);
  assert.equal(f.Engine.objectAt(f.state, f.p.map, 45, 45).until, 1000);
});

test("all gathering skills gain the advertised roll frequency", () => {
  for (const skill of ["woodcutting", "mining", "fishing"]) {
    for (const level of [1, 2, 25, 99]) {
      const f = gathering(skill, level);
      tick(f, 800);
      const expected = Math.floor(800 * (1 + f.Rules.workBonus(level) / 100) / f.op.ticks + 1e-7);
      assert.equal(f.rolls(), expected, skill + " level " + level);
      assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
    }
  }
});

test("gathering resumes after node depletion using level-adjusted cycles", () => {
  const f = gathering("woodcutting", 99);
  f.p.afk.cont = false;
  const start = f.state.tick;
  f.Sim.setObj(f.state, f.p.map, 45, 45, "stump", start + 5);
  f.p.act.wait = true;
  tick(f, 4);
  assert.equal(f.rolls(), 0);
  f.Sim.setObj(f.state, f.p.map, 45, 45, "tree", start + 1000);
  tick(f, 4);
  assert.equal(f.rolls(), 1);
});

test("station approach waits a full adjusted cycle instead of banking time while walking", () => {
  const f = production(99);
  f.p.x = f.p.px = f.p.mx = 42;
  f.p.path = [];
  tick(f, 1);
  assert.equal(f.Player.bankCount(f.p, "bronze_bar"), 0);
  assert.ok(f.p.act.next >= f.state.tick + 4 / 1.69);
});

test("bank-fed jobs still stop on reload and existing saves need no migration", () => {
  const f = production(99);
  tick(f, 8);
  const save = f.Engine.serialize(f.state);
  const banked = f.Player.bankCount(f.p, "bronze_bar");
  assert.equal(save.v, 1);
  assert.equal(save.act, null);
  const restored = f.Engine.deserialize(save);
  assert.equal(f.Player.bankCount(restored.player, "bronze_bar"), banked);
  assert.match(f.Engine.view.guide(restored, "smithing").benefit, /\+69%/);
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
});

test("background catch-up and ordinary ticking produce identical output", () => {
  const normal = production(50);
  const background = production(50);
  tick(normal, 800);
  background.Engine.catchUp(background.state, 800);
  assert.equal(background.Player.bankCount(background.p, "bronze_bar"), normal.Player.bankCount(normal.p, "bronze_bar"));
});

test("guides, level-up unlocks and next goals expose every bonus and milestone", () => {
  const f = fixture("smithing", 24);
  const guide = f.Engine.view.guide(f.state, "smithing");
  assert.match(guide.benefit, /\+11.5%/);
  assert.match(guide.nextBenefit, /Level 25: Work rate \+17%/);
  const milestones = guide.rows.filter(r => /proficiency/.test(r.name));
  assert.deepEqual(Array.from(milestones, r => r.lvl), [25, 50, 75, 99]);
  assert.equal(milestones.every(r => !r.ok), true);
  const goal = f.Engine.view.goal(f.state, "smithing");
  assert.equal(goal.at, 25);
  assert.equal(goal.perk, true);
  assert.ok(goal.names.includes("Apprentice proficiency"));
  assert.ok(goal.names.includes("Work rate +17%"));
  f.p.xp10.smithing = f.Rules.xpForLevel(25) * 10;
  assert.equal(f.Engine.view.guide(f.state, "smithing").rows.find(r => r.lvl === 25 && /proficiency/.test(r.name)).ok, true);
  assert.equal(f.Engine.view.goal(f.state, "smithing").at, 26);
  assert.ok(f.Engine.view.unlocks("smithing", 26).includes("Work rate +17.5%"));
  f.p.xp10.smithing = f.Rules.xpForLevel(99) * 10;
  assert.equal(f.Engine.view.goal(f.state, "smithing"), null);
});

test("all skill guides have current benefits, including combat and vitality", () => {
  const f = fixture("smithing", 1);
  for (const skill of f.Rules.SKILLS) {
    const guide = f.Engine.view.guide(f.state, skill);
    assert.ok(guide.benefit.length > 0, skill);
    assert.ok(guide.detail.length > 0, skill);
  }
  assert.match(f.Engine.view.guide(f.state, "hitpoints").benefit, /Maximum health: 10/);
  assert.match(f.Engine.view.guide(f.state, "strength").benefit, /rounded/);
});

test("production menus display the actual adjusted cycle time", () => {
  const f = production(99);
  f.p.iface = { t: "make", at: f.Util.refObj(45, 45), rids: ["smelt_bronze"], bankFeed: true };
  const row = f.Engine.view.make(f.state).rows[0];
  assert.ok(Math.abs(row.seconds - 2.4 / 1.69) < 1e-12);
});
