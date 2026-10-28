const assert = require("node:assert/strict");
const { test } = require("node:test");
const { loadEngine } = require("./engine-fixture.cjs");

function fixture(id = "ash_pup", level = 20) {
  const api = loadEngine();
  const state = api.Engine.createState(12345);
  const p = state.player;
  for (const skill of ["attack", "strength", "defence", "hitpoints"]) p.xp10[skill] = api.Rules.xpForLevel(99) * 10;
  p.hp = api.Player.maxHp(p);
  p.quests.beyond_crown = 100;
  p.quests.starless_forge = 20;
  api.Player.teleport(state, "starforge", 12, 24);
  api.Engine.tick(state);
  api.Player.teleport(state, "starforge", 12, 6);
  const foe = state.npcs.find(n => n.id === "astravor");
  api.Combat.startFight(state, foe);
  p.pets[id] = api.Rules.petXpFor(level);
  api.Engine.setPet(state, id);
  return { ...api, state, p, foe, id };
}

function petDps(Rules, d, level, c) {
  let chance = Rules.hitChance(Rules.petAttackRoll(d.att, level), Rules.npcDefenceRoll(c));
  if (d.perk === "keen") chance = Math.min(1, chance * 1.25);
  const average = (Rules.petMaxHit(d.maxHit, level, d.perk) + 1) / 2;
  const seconds = (d.perk === "quick" ? Rules.PET_QUICK : Rules.PET_SPEED) * Rules.TICK_MS / 1000;
  return chance * average * (d.perk === "flurry" ? 1.2 : 1) / seconds;
}

test("pet XP thresholds extend to 99 without altering any original level", () => {
  const { Rules: R } = loadEngine();
  assert.equal(R.PET_MAX_LVL, 99);
  assert.equal(R.PET_XP_MAX, 240100);
  for (let level = 1; level <= 99; level++) {
    const xp = 25 * (level - 1) ** 2;
    assert.equal(R.petXpFor(level), xp);
    assert.equal(R.petLevel(xp), level);
    if (level > 1) assert.equal(R.petLevel(xp - 1), level - 1);
  }
  assert.equal(R.petLevel(9025), 20);
  assert.equal(R.petLevel(10000), 21);
  assert.equal(R.petLevel(1e9), 99);
  assert.equal(R.petXpFor(100), 240100);
});

test("every pet retains exactly the same stats, perks, attack speeds and forms through level 20", () => {
  const f = fixture();
  for (const [id, d] of Object.entries(f.Data.pets)) {
    f.p.pets[id] = 0;
    for (let level = 1; level <= 20; level++) {
      f.p.pets[id] = f.Rules.petXpFor(level);
      const v = f.Engine.view.pet(f.state, id);
      const base = d.maxHit + Math.floor((level - 1) / 5);
      const max = d.perk === "scorch" ? base + Math.max(1, Math.floor(base / 4)) : base;
      assert.equal(v.att, d.att + 2 * (level - 1));
      assert.equal(v.maxHit, max);
      assert.equal(v.speed, d.perk === "quick" ? 4 : 6);
      assert.equal(v.perk, d.perk);
      assert.equal(v.stage, level >= 14 ? 2 : level >= 7 ? 1 : 0);
    }
  }
});

test("mature training improves accuracy every level and applies exact damage and milestone boundaries", () => {
  const { Rules: R, Data } = loadEngine();
  const expected = [[20, 58, 4], [21, 61, 4], [24, 70, 4], [25, 73, 5], [26, 76, 5],
    [27, 79, 6], [49, 145, 9], [50, 148, 10], [74, 220, 13], [75, 223, 14], [98, 292, 18], [99, 295, 19]];
  for (const [level, attack, max] of expected) {
    assert.equal(R.petAttack(20, level), attack);
    assert.equal(R.petMaxHit(1, level, "quick"), max);
    assert.equal(R.petMaxHit(1, level, "scorch"), max + Math.max(1, Math.floor(max / 4)));
  }
  for (const d of Object.values(Data.pets)) {
    for (let level = 21; level <= 99; level++) {
      assert.equal(R.petAttack(d.att, level) - R.petAttack(d.att, level - 1), 3);
      assert.ok(R.petMaxHit(d.maxHit, level, d.perk) >= R.petMaxHit(d.maxHit, level - 1, d.perk));
      assert.equal(R.petStage(level), 2);
    }
  }
  assert.equal(R.petMaxHit(6, 99, "keen"), 24);
});

test("real pet attacks earn damage XP past 20, report the new stats, and never award player combat XP", () => {
  const f = fixture("star_mote");
  f.p.pets.star_mote = f.Rules.petXpFor(21) - 1;
  const before = { ...f.p.xp10 };
  for (let i = 0; i < 100 && f.Rules.petLevel(f.p.pets.star_mote) === 20; i++) {
    f.state.tick++;
    f.Combat.petPhase(f.state);
  }
  assert.equal(f.Rules.petLevel(f.p.pets.star_mote), 21);
  assert.equal(f.p.pets.star_mote - (f.Rules.petXpFor(21) - 1), f.p.petLog.star_mote.dmg);
  assert.equal(f.p.petLog.star_mote.dmg, 620 - f.foe.hp);
  assert.deepEqual({ ...f.p.xp10 }, before);
  assert.ok(f.state.events.some(e => e.type === "msg" && /level 21.*Attack 101, max hit 9/.test(e.text)));
  assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
});

test("level 99 caps XP without stopping combat damage or records", () => {
  const f = fixture("ash_pup", 99);
  f.p.pets.ash_pup = f.Rules.PET_XP_MAX - 1;
  for (let i = 0; i < 100; i++) {
    f.state.tick++;
    f.Combat.petPhase(f.state);
  }
  assert.equal(f.p.pets.ash_pup, f.Rules.PET_XP_MAX);
  assert.ok(f.p.petLog.ash_pup.dmg > 1);
  assert.ok(f.foe.hp < 620);
  const v = f.Engine.view.pet(f.state, "ash_pup");
  assert.equal(v.lvl, 99);
  assert.equal(v.next, null);
  assert.equal(v.nextBenefit, null);
  assert.equal(v.milestones.every(m => m.reached), true);
  assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
});

test("legacy capped pets and new high-level pets retain XP, discovery records, ownership and summons on reload", () => {
  const f = fixture();
  f.p.pets.ash_pup = 9025;
  f.p.pets.star_mote = f.Rules.petXpFor(75) + 100;
  f.p.petLog.ash_pup = { dmg: 15000, kills: 12, best: 4, kc: 100, out: 1000 };
  f.Player.teleport(f.state, "starforge", 12, 24);
  f.Combat.breakOff(f.state);
  const saved = f.Engine.serialize(f.state);
  assert.equal(saved.v, 1);
  const restored = f.Engine.deserialize(saved);
  assert.equal(restored.player.pets.ash_pup, 9025);
  assert.equal(f.Rules.petLevel(restored.player.pets.ash_pup), 20);
  assert.equal(restored.player.pets.star_mote, f.Rules.petXpFor(75) + 100);
  assert.equal(restored.player.pet, "ash_pup");
  assert.deepEqual({ ...restored.player.petLog.ash_pup }, { ...f.p.petLog.ash_pup });
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
  saved.pt.star_mote = 1e9;
  assert.equal(f.Engine.deserialize(saved).player.pets.star_mote, f.Rules.PET_XP_MAX);
});

test("the Pet dex exposes the cap, next gain, milestone stats, and progress beyond the old cap", () => {
  const f = fixture("ash_pup");
  let v = f.Engine.view.pet(f.state, "ash_pup");
  assert.equal(v.maxLevel, 99);
  assert.equal(v.next, 10000);
  assert.equal(v.nextBenefit, "Level 21: Attack 61, max hit 4.");
  assert.deepEqual(Array.from(v.milestones, m => [m.lvl, m.reached, m.maxHit]),
    [[25, false, 5], [50, false, 10], [75, false, 14], [99, false, 19]]);
  f.p.pets.ash_pup = f.Rules.petXpFor(50);
  v = f.Engine.view.pet(f.state, "ash_pup");
  assert.equal(v.milestones.filter(m => m.reached).length, 2);
  assert.equal(v.nextBenefit, "Level 51: Attack 151, max hit 10.");
  assert.equal(f.Engine.view.pets(f.state).maxLevel, 99);
});

test("fully trained pets deliver substantial damage while remaining companions to a well-geared endgame player", () => {
  const f = fixture();
  Object.assign(f.p.eq, { weapon: "eventide", shield: null, head: "astral_helm", body: "astral_cuirass",
    legs: "astral_greaves", neck: "amber_charm", hands: "astral_gauntlets", cape: "heros_mantle",
    feet: "astral_boots", ring: "starbound_signet" });
  const b = f.Player.bonuses(f.p);
  for (const id of ["astravor", "hollow_king", "starbound_sentinel"]) {
    const c = f.Data.npcs[id].combat;
    const playerChance = f.Rules.hitChance(f.Rules.playerAttackRoll(99, f.p.style, b.att), f.Rules.npcDefenceRoll(c));
    const playerDps = playerChance * (f.Rules.playerMaxHit(99, f.p.style, b.str) + 1) / 2 / (b.speed * 0.6);
    for (const d of Object.values(f.Data.pets)) {
      const dps = petDps(f.Rules, d, 99, c);
      assert.ok(dps < playerDps * 0.85, `${d.name} must remain below 85% of player DPS against ${id}`);
      if (id === "astravor") {
        assert.ok(dps > petDps(f.Rules, d, 20, c) * 3, `${d.name} must gain at least triple its level-20 DPS`);
      }
    }
  }
});

test("actual sustained attacks match advertised level-99 stats for every perk", () => {
  const ids = Object.keys(loadEngine().Data.pets);
  for (const id of ids) {
    const f = fixture(id, 99);
    const n = 12000;
    for (let i = 0; i < n; i++) {
      f.state.tick++;
      f.foe.hp = 620;
      f.Combat.petPhase(f.state);
    }
    const actual = f.p.petLog[id].dmg / (n * 0.6);
    const expected = petDps(f.Rules, f.Data.pets[id], 99, f.Data.npcs.astravor.combat);
    assert.ok(Math.abs(actual - expected) < expected * 0.1, `${id}: actual ${actual}, expected ${expected}`);
    assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
  }
});
