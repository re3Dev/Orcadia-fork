const assert = require("node:assert/strict");
const { test } = require("node:test");
const { loadEngine } = require("./engine-fixture.cjs");

function fixture() {
  const api = loadEngine();
  const state = api.Engine.createState(12345);
  const p = state.player;
  p.inv.fill(null);
  for (const skill of ["attack", "strength", "defence", "hitpoints", "smithing"]) {
    p.xp10[skill] = api.Rules.xpForLevel(99) * 10;
  }
  p.hp = api.Player.maxHp(p);
  return { ...api, state, p };
}

function at(f, map, x, y) {
  f.Combat.breakOff(f.state);
  f.Player.teleport(f.state, map, x, y);
}

function ticks(f, count = 1) {
  for (let i = 0; i < count; i++) f.Engine.tick(f.state);
}

function talk(f) {
  assert.equal(f.Script.startDialogue(f.state, "vesna", 18), true);
}

function accept(f) {
  f.Engine.dialogueContinue(f.state);
  assert.equal(f.Engine.dialogueChoose(f.state, 0), true);
}

function bossFixture() {
  const f = fixture();
  f.p.quests.beyond_crown = 100;
  f.p.quests.starless_forge = 20;
  at(f, "starforge", 12, 24);
  ticks(f);
  f.boss = f.state.npcs.find(n => n.id === "astravor");
  assert.equal(f.boss.on, true);
  return f;
}

function interact(f, x, y, op) {
  assert.equal(f.Engine.act(f.state, f.Util.refObj(x, y), op), true);
  ticks(f);
}

function valid(f) {
  assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
}

test("the quest chain is offered only after the Hollow King and respects existing Vesna dialogue", () => {
  const f = fixture();
  talk(f);
  assert.notEqual(f.p.iface.n, "sf_offer");
  f.p.quests.fallen_star = 100;
  talk(f);
  assert.equal(f.p.iface.n, "after");
  f.p.quests.hollow_king = 100;
  talk(f);
  assert.equal(f.p.iface.n, "sf_offer");
  accept(f);
  assert.equal(f.Script.stage(f.state, "beyond_crown"), 10);
  assert.equal(f.Script.stage(f.state, "starless_forge"), 0);
});

test("five new knight kills, carried materials, ward reward, and second quest acceptance work end to end", () => {
  const f = fixture();
  f.p.quests.hollow_king = 100;
  f.p.kc.hollow_knight = 100;
  talk(f);
  accept(f);
  f.Script.onKill(f.state, "starbound_sentinel");
  assert.equal(f.p.qc.beyond_crown, undefined);
  for (let i = 0; i < 4; i++) f.Script.onKill(f.state, "hollow_knight");
  assert.equal(f.p.quests.beyond_crown, 10);
  assert.ok(f.Script.journal(f.state, "beyond_crown").some(row => row.text.includes("4/5")));
  f.Script.onKill(f.state, "hollow_knight");
  assert.equal(f.p.quests.beyond_crown, 20);
  f.p.bank = [{ id: "starsteel_bar", qty: 3 }, { id: "diamond", qty: 1 }];
  talk(f);
  assert.equal(f.p.iface.n, "sf_materials");
  f.Player.add(f.p, "starsteel_bar", 3);
  talk(f);
  assert.equal(f.p.iface.n, "sf_materials");
  f.Player.add(f.p, "diamond", 1);
  talk(f);
  assert.equal(f.p.quests.beyond_crown, 100);
  assert.equal(f.Player.count(f.p, "starsteel_bar"), 0);
  assert.equal(f.Player.count(f.p, "diamond"), 0);
  assert.equal(f.Player.count(f.p, "starward"), 1);
  assert.equal(f.Player.bankCount(f.p, "diamond"), 1);
  talk(f);
  assert.equal(f.p.iface.n, "sf_boss_offer");
  accept(f);
  assert.equal(f.p.quests.starless_forge, 10);
  valid(f);
});

test("the second quest counts six sentinels, requires a carried core, and rewards completion exactly once", () => {
  const f = bossFixture();
  f.Script.setStage(f.state, "starless_forge", 10);
  for (let i = 0; i < 5; i++) f.Script.onKill(f.state, "starbound_sentinel");
  assert.equal(f.p.quests.starless_forge, 10);
  f.Script.onKill(f.state, "starbound_sentinel");
  assert.equal(f.p.quests.starless_forge, 20);
  f.p.bank = [{ id: "starless_core", qty: 1 }];
  f.Script.checkTriggers(f.state);
  assert.equal(f.p.quests.starless_forge, 20);
  f.Player.add(f.p, "starless_core", 1);
  f.Script.checkTriggers(f.state);
  assert.equal(f.p.quests.starless_forge, 30);
  f.Player.remove(f.p, "starless_core", 1);
  talk(f);
  assert.equal(f.p.iface.n, "sf_core");
  f.Player.add(f.p, "starless_core", 1);
  talk(f);
  assert.equal(f.p.quests.starless_forge, 100);
  assert.equal(f.Player.count(f.p, "starbound_signet"), 1);
  assert.equal(f.Player.count(f.p, "coins"), 20000);
  assert.equal(f.Player.count(f.p, "starless_core"), 0);
  talk(f);
  assert.equal(f.p.iface.n, "sf_after");
  assert.equal(f.Player.count(f.p, "starbound_signet"), 1);
  assert.equal(f.Player.count(f.p, "coins"), 20000);
  valid(f);
});

test("lost wards cost the original materials and cannot be duplicated while owned or banked", () => {
  const f = fixture();
  f.p.quests.beyond_crown = 100;
  f.p.quests.starless_forge = 20;
  function replace() {
    talk(f);
    f.Engine.dialogueContinue(f.state);
    f.Engine.dialogueChoose(f.state, 0);
  }
  replace();
  assert.equal(f.p.iface.n, "sf_replace_need");
  assert.equal(f.Player.count(f.p, "starward"), 0);
  f.Player.add(f.p, "starsteel_bar", 3);
  f.Player.add(f.p, "diamond", 1);
  replace();
  assert.equal(f.Player.count(f.p, "starward"), 1);
  assert.equal(f.Player.count(f.p, "starsteel_bar"), 0);
  assert.equal(f.Player.count(f.p, "diamond"), 0);
  talk(f);
  f.Engine.dialogueContinue(f.state);
  assert.equal(f.Script.view(f.state).opts.length, 1);
  f.Player.remove(f.p, "starward", 1);
  f.p.bank = [{ id: "starward", qty: 1 }];
  talk(f);
  f.Engine.dialogueContinue(f.state);
  assert.equal(f.Script.view(f.state).opts.length, 1);
});

test("the quest signet can be reclaimed only after completion and only while unowned", () => {
  const f = fixture();
  f.p.quests.beyond_crown = 100;
  f.p.quests.starless_forge = 20;
  f.Player.add(f.p, "starward", 1);
  talk(f);
  f.Engine.dialogueContinue(f.state);
  assert.deepEqual(Array.from(f.Script.view(f.state).opts), ["Goodbye."]);
  f.p.quests.starless_forge = 100;
  talk(f);
  f.Engine.dialogueContinue(f.state);
  assert.equal(f.Engine.dialogueChoose(f.state, 0), true);
  assert.equal(f.Player.count(f.p, "starbound_signet"), 1);
  talk(f);
  f.Engine.dialogueContinue(f.state);
  assert.deepEqual(Array.from(f.Script.view(f.state).opts), ["Goodbye."]);
});

test("the stair is quest-locked, its destination is safe, and the exit always works", () => {
  const f = fixture();
  at(f, "overworld", 145, 135);
  assert.equal(f.Engine.act(f.state, f.Util.refObj(145, 134), "enter"), false);
  assert.equal(f.p.map, "overworld");
  f.p.quests.beyond_crown = 100;
  interact(f, 145, 134, "enter");
  assert.equal(f.p.map, "starforge");
  assert.equal(f.p.x, 12);
  assert.equal(f.p.y, 25);
  assert.equal(f.p.foe, 0);
  assert.equal(f.Sim.inFreeze(f.state), false);
  interact(f, 12, 26, "climb");
  assert.equal(f.p.map, "overworld");
  assert.equal(f.p.y, 135);
  valid(f);
});

test("the boss seal requires six sentinels, warns before entry, and permits retreat", () => {
  const f = fixture();
  at(f, "starforge", 12, 12);
  f.p.quests.starless_forge = 10;
  assert.equal(f.Engine.act(f.state, f.Util.refObj(12, 11), "enter"), false);
  assert.equal(f.World.findPath(f.state, "starforge", 12, 12, { x: 12, y: 10, mode: "tile" }, 30), null);
  f.p.quests.starless_forge = 20;
  interact(f, 12, 11, "enter");
  assert.equal(f.p.iface.d, "starforge_warning");
  assert.match(f.Script.view(f.state).text, /no emergency AFK rescue/);
  accept(f);
  assert.equal(f.p.y, 10);
  assert.equal(f.Sim.inFreeze(f.state), true);
  interact(f, 12, 11, "enter");
  assert.equal(f.p.y, 12);
  assert.equal(f.Sim.inFreeze(f.state), false);
});

test("new maps are rectangular, connected, and use valid walkable spawn and teleport tiles", () => {
  const f = fixture();
  const map = f.Data.maps.starforge;
  assert.ok(map.rows.every(row => row.length === 24));
  for (const spawn of map.spawns) {
    assert.ok(f.Data.npcs[spawn.n]);
    assert.equal(f.World.blocked(f.state, "starforge", spawn.x, spawn.y), false);
  }
  for (const place of map.place) assert.ok(f.Data.objects[place.o]);
  for (const [mapId, x, y] of [["starforge", 12, 25], ["starforge", 12, 24], ["starforge", 12, 12],
    ["starforge", 12, 10], ["overworld", 145, 135]]) {
    assert.equal(f.World.blocked(f.state, mapId, x, y), false);
  }
  for (const [sx, sy, x, y] of [[12, 25, 4, 14], [12, 25, 20, 17], [12, 25, 12, 12], [12, 10, 12, 5]]) {
    assert.ok(f.World.findPath(f.state, "starforge", sx, sy, { x, y, mode: "tile" }, 40));
  }
  assert.ok(f.World.findPath(f.state, "overworld", 132, 122, { x: 145, y: 135, mode: "tile" }, 50));
  assert.equal(f.World.regionAt("starforge", 12, 5).id, "starforge_heart");
  assert.equal(f.World.regionAt("starforge", 12, 24).id, "starforge");
});

test("Astravor is quest-gated, telegraphs a blast, and supports full dodges and exact ward halving", () => {
  const before = fixture();
  ticks(before);
  assert.equal(before.state.npcs.find(n => n.id === "astravor").on, false);
  function blast(ward, dodge) {
    const f = bossFixture();
    at(f, "starforge", 12, 9);
    ticks(f);
    f.boss.atkTimer = 100;
    ticks(f, f.boss.spec.next - f.state.tick);
    assert.equal(f.boss.spec.land, f.state.tick + 3);
    assert.equal(f.boss.spec.cx, 12);
    assert.equal(f.boss.spec.cy, 9);
    assert.ok(f.state.events.some(e => e.type === "breath" && e.uid === f.boss.uid));
    f.p.eq.shield = ward;
    if (dodge) f.p.x = 15;
    f.boss.x = f.boss.px = 12;
    f.boss.y = f.boss.py = 5;
    f.boss.atkTimer = 100;
    const hp = f.p.hp;
    f.state.tick = f.boss.spec.land;
    f.Combat.npcPhase(f.state);
    return hp - f.p.hp;
  }
  const damage = blast(null, false);
  assert.ok(damage >= 20 && damage <= 34);
  assert.equal(blast("starward", false), Math.floor(damage / 2));
  assert.equal(blast("emberward", false), damage);
  assert.equal(blast("starward", true), 0);
});

test("Astravor enrages, resets after retreat, does not respawn on top of players, and remains repeatable", () => {
  const f = bossFixture();
  at(f, "starforge", 12, 9);
  f.boss.hp = 180;
  ticks(f);
  assert.equal(f.boss.spec.enraged, true);
  at(f, "starforge", 12, 24);
  ticks(f, 12);
  assert.equal(f.boss.hp, 620);
  assert.equal(f.boss.spec.enraged, false);
  at(f, "starforge", 12, 9);
  f.Combat.killNpc(f.state, f.boss);
  const until = f.boss.deadUntil;
  assert.equal(until, f.state.tick + 250);
  f.state.tick = until;
  ticks(f);
  assert.equal(f.boss.hp, 0);
  at(f, "starforge", 12, 24);
  f.p.quests.starless_forge = 100;
  ticks(f);
  assert.equal(f.boss.hp, 620);
  assert.equal(f.boss.on, true);
});

test("a prepared level-90 character can earn the first kill with pre-expansion gear and the rewarded ward", () => {
  const f = bossFixture();
  for (const skill of ["attack", "strength", "defence", "hitpoints"]) f.p.xp10[skill] = f.Rules.xpForLevel(90) * 10;
  f.p.hp = f.Player.maxHp(f.p);
  Object.assign(f.p.eq, { weapon: "starsteel_sword", head: "starsteel_helm", body: "starsteel_breastplate",
    legs: "starsteel_greaves", shield: "starward", neck: "amber_charm" });
  f.Player.add(f.p, "stormray", 28);
  f.p.afk.eat = 70;
  at(f, "starforge", 12, 6);
  f.Combat.startFight(f.state, f.boss);
  let markedUntil = 0;
  for (let i = 0; i < 2000 && f.boss.hp > 0 && f.p.map === "starforge"; i++) {
    if (f.boss.spec.land > f.state.tick && f.boss.spec.land !== markedUntil) {
      markedUntil = f.boss.spec.land;
      const tiles = [[f.p.x + 2, f.p.y], [f.p.x - 2, f.p.y], [f.p.x, f.p.y + 2], [f.p.x, f.p.y - 2]];
      const safe = tiles.filter(([x, y]) => f.World.regionAt("starforge", x, y)?.id === "starforge_heart" &&
        !f.World.blocked(f.state, "starforge", x, y))
        .sort((a, b) => f.Util.dist(a[0], a[1], 12, 5) - f.Util.dist(b[0], b[1], 12, 5))[0];
      if (safe) f.Engine.walkTo(f.state, safe[0], safe[1]);
    }
    if (!f.boss.spec.land && f.p.act?.k !== "fight") f.Combat.startFight(f.state, f.boss);
    ticks(f);
  }
  assert.equal(f.p.kc.astravor, 1);
  assert.ok(f.p.hp > 0);
  assert.ok(f.Player.count(f.p, "stormray") > 0);
  assert.equal(f.Player.count(f.p, "starless_core"), 1);
  assert.equal(f.p.quests.starless_forge, 30);
  valid(f);
});

test("boss arena freezes catch-up, disables emergency rescue, and relocates reloads and graves safely", () => {
  const f = bossFixture();
  at(f, "starforge", 12, 9);
  const tick = f.state.tick;
  assert.equal(f.Engine.catchUp(f.state, 100).frozen, true);
  assert.equal(f.state.tick, tick);
  ticks(f);
  f.p.hp = 1;
  f.p.resume = { k: "fight" };
  assert.equal(f.Combat.emergency(f.state), false);
  f.p.resume = null;
  const saved = f.Engine.serialize(f.state);
  assert.deepEqual(Array.from(saved.pos), ["starforge", 12, 24]);
  assert.equal(saved.act, null);
  const restored = f.Engine.deserialize(saved);
  assert.equal(restored.player.y, 24);
  f.Player.add(f.p, "astral_alloy", 3);
  f.Combat.playerDeath(f.state);
  assert.equal(f.state.grave.map, "starforge");
  assert.equal(f.state.grave.y, 24);
  assert.equal(f.World.blocked(f.state, "starforge", f.state.grave.x, f.state.grave.y), false);
});

test("loot tables have exact weights, known IDs, guaranteed dust, and recoverable non-duplicating quest cores", () => {
  const f = fixture();
  for (const id of ["starbound_sentinel", "astravor"]) {
    const table = f.Data.drops[id];
    assert.equal(table.main.reduce((sum, row) => sum + row[0], 0), 128);
    for (const row of table.main) assert.ok(row[1] === null || f.Data.items[row[1]]);
    for (const row of table.always) assert.ok(f.Data.items[row[0]]);
  }
  for (const stage of [0, 10, 20, 30, 100]) {
    f.p.quests.starless_forge = stage;
    for (let i = 0; i < 20; i++) {
      const drops = f.Combat.dropFor(f.state, "astravor");
      assert.equal(drops.some(s => s.id === "starless_core"), stage === 20 || stage === 30);
      assert.ok(drops.some(s => s.id === "stardust" && s.qty >= 2 && s.qty <= 4));
      assert.ok(drops.some(s => s.id === "coins" && s.qty >= 4000 && s.qty <= 8000));
    }
  }
  f.p.quests.starless_forge = 30;
  f.p.bank = [{ id: "starless_core", qty: 1 }];
  assert.equal(f.Combat.dropFor(f.state, "astravor").some(s => s.id === "starless_core"), false);
  assert.deepEqual(Array.from(f.Data.drops.astravor.unique, row => Array.from(row)), [["nightfall", 50], ["eventide", 80]]);
  assert.equal(f.Data.pets.star_mote.rate, 200);
  assert.equal(f.Data.pets.star_mote.from, "astravor");
});

test("every astral recipe consumes the specified banked materials and stores its product", () => {
  const ids = Object.keys(loadEngine().Data.recipes).filter(id => id.includes("astral") || ["smith_nightfall", "smith_eventide"].includes(id));
  assert.equal(ids.length, 8);
  for (const id of ids) {
    const f = fixture();
    const recipe = f.Data.recipes[id];
    f.p.quests.beyond_crown = 100;
    f.p.bank = recipe.in.map(([id, qty]) => ({ id, qty }));
    f.Player.add(f.p, "hammer", 1);
    at(f, "overworld", 44, 45);
    f.Sim.setObj(f.state, "overworld", 45, 45, recipe.at[0], 100000);
    assert.equal(f.Script.openMake(f.state, recipe.at[0], f.Util.refObj(45, 45)), true);
    assert.ok(f.p.iface.rids.includes(id));
    assert.equal(f.Engine.setMakeBankFeed(f.state, true), true);
    assert.equal(f.Engine.make(f.state, id, 1), true, id);
    ticks(f, 10);
    for (const [id] of recipe.in) assert.equal(f.Player.bankCount(f.p, id), 0);
    for (const [id, qty] of recipe.out) assert.equal(f.Player.bankCount(f.p, id), qty);
    valid(f);
  }
});

test("astral smelting needs its quest and level; new equipment enforces level 70 and two-handed clashes", () => {
  const f = fixture();
  at(f, "overworld", 44, 45);
  f.Sim.setObj(f.state, "overworld", 45, 45, "furnace", 100000);
  for (const [id, qty] of f.Data.recipes.smelt_astral_alloy.in) f.Player.add(f.p, id, qty);
  f.Script.openMake(f.state, "furnace", f.Util.refObj(45, 45));
  assert.equal(f.Engine.make(f.state, "smelt_astral_alloy", 1), false);
  f.p.quests.beyond_crown = 100;
  f.p.xp10.smithing = f.Rules.xpForLevel(89) * 10;
  assert.equal(f.Engine.make(f.state, "smelt_astral_alloy", 1), false);
  f.p.inv.fill(null);
  f.Player.add(f.p, "nightfall", 1);
  f.p.xp10.attack = f.Rules.xpForLevel(69) * 10;
  assert.equal(f.Player.equip(f.state, 0), false);
  f.p.xp10.attack = f.Rules.xpForLevel(70) * 10;
  assert.equal(f.Player.equip(f.state, 0), true);
  f.Player.add(f.p, "starward", 1);
  assert.equal(f.Player.equip(f.state, 0), true);
  f.Player.add(f.p, "eventide", 1);
  assert.equal(f.Player.equip(f.state, 0), true);
  assert.equal(f.p.eq.shield, null);
  f.Player.add(f.p, "astral_cuirass", 1);
  f.p.xp10.defence = f.Rules.xpForLevel(69) * 10;
  assert.equal(f.Player.equip(f.state, f.p.inv.findIndex(s => s && s.id === "astral_cuirass")), false);
  f.p.xp10.defence = f.Rules.xpForLevel(70) * 10;
  assert.equal(f.Player.equip(f.state, f.p.inv.findIndex(s => s && s.id === "astral_cuirass")), true);
  valid(f);
});

test("new items, quests, pets and boss kill counts persist without changing the save version", () => {
  const f = bossFixture();
  f.Player.add(f.p, "nightfall", 1);
  f.p.bank = [{ id: "astral_alloy", qty: 50 }, { id: "stardust", qty: 123 }];
  f.p.quests.starless_forge = 30;
  f.p.pets.star_mote = 500;
  f.p.pet = "star_mote";
  f.p.kc.astravor = 42;
  const saved = f.Engine.serialize(f.state);
  assert.equal(saved.v, 1);
  const restored = f.Engine.deserialize(saved);
  assert.equal(f.Player.count(restored.player, "nightfall"), 1);
  assert.equal(f.Player.bankCount(restored.player, "stardust"), 123);
  assert.equal(restored.player.quests.starless_forge, 30);
  assert.equal(restored.player.pets.star_mote, 500);
  assert.equal(restored.player.pet, "star_mote");
  assert.equal(restored.player.kc.astravor, 42);
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
});

test("legacy NPC IDs, dead timers, and earned Hero's mantle eligibility are preserved", () => {
  const f = fixture();
  assert.equal(f.World.SPAWNS.find(n => n.id === "vesna").uid, 18);
  assert.equal(f.World.SPAWNS.find(n => n.id === "hollow_king").uid, 137);
  assert.equal(f.World.SPAWNS.find(n => n.id === "smoulderjaw").uid, 159);
  assert.ok(f.World.SPAWNS.filter(n => n.map === "starforge").every(n => n.uid > 159));
  for (const qid of Object.keys(f.Data.quests)) {
    if (!["beyond_crown", "starless_forge"].includes(qid)) f.p.quests[qid] = 100;
  }
  f.Player.add(f.p, "heros_mantle", 1);
  assert.equal(f.Player.equip(f.state, 0), true);
  assert.equal(f.Script.test(f.state, { allQuests: true }), false);
  const saved = f.Engine.serialize(f.state);
  saved.dead = [["smoulderjaw", 159, 100]];
  const restored = f.Engine.deserialize(saved);
  assert.equal(restored.npcs[158].deadUntil, restored.tick + 100);
  assert.equal(restored.player.eq.cape, "heros_mantle");
  assert.equal(restored.player.quests.starless_forge || 0, 0);
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
});
