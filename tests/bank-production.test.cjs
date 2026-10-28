const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "..", "cloud_plugin-fdb0-3b0d-ec7f-95be18c.py"), "utf8");
const engine = source.split("/*ENGINE-START*/")[1].split("/*ENGINE-END*/")[0];
const engineScript = new vm.Script(engine + "\n({ Engine, Data, Rules, Player, Sim, Script, Util });");

function fixture(rid = "smelt_steel", bank = [{ id: "iron_ore", qty: 100 }, { id: "coal", qty: 200 }]) {
  const api = engineScript.runInNewContext();
  const { Engine, Sim, Util, Script } = api;
  const state = Engine.createState(12345);
  const p = state.player;
  p.map = "overworld";
  p.x = p.px = p.mx = 44;
  p.y = p.py = p.my = 45;
  p.xp10.smithing = 130344310;
  p.xp10.cooking = 130344310;
  p.xp10.crafting = 130344310;
  p.inv.fill(null);
  p.bank = bank.map(e => ({ ...e }));
  const recipe = api.Data.recipes[rid];
  const station = recipe.at[0];
  if (station) {
    Sim.setObj(state, p.map, 45, 45, station, 100000);
    assert.equal(Script.openMake(state, station, Util.refObj(45, 45)), true);
    assert.ok(p.iface.rids.includes(rid));
  } else {
    p.iface = { t: "make", at: null, station: null, rids: [rid] };
  }
  return { ...api, state, p, rid, recipe };
}

function run(f, count = -1, ticks = 8) {
  assert.equal(f.Engine.setMakeBankFeed(f.state, true), true);
  assert.equal(f.Engine.make(f.state, f.rid, count), true);
  for (let i = 0; i < ticks; i++) f.Engine.tick(f.state);
}

function bankQty(f, id) {
  return f.Player.bankCount(f.p, id);
}

function valid(f) {
  assert.deepEqual(Array.from(f.Engine.check(f.state)), []);
}

function fillBank(f, excluded) {
  for (let i = 0; f.p.bank.length < f.Rules.BANK_MAX; i++) {
    const id = "test_bank_" + i;
    f.Data.items[id] = { ...f.Data.items.hammer };
    if (!excluded.includes(id)) f.p.bank.push({ id, qty: 1 });
  }
}

test("the complete embedded JavaScript parses", () => {
  new vm.Script(source.split("<script>")[1].split("</script>")[0]);
});

test("station lists recipes whose materials exist only in the bank", () => {
  const f = fixture();
  assert.equal(f.Engine.view.make(f.state).bankFeed, false);
  assert.equal(f.Engine.view.make(f.state).bankAvailable, true);
  assert.equal(f.Engine.view.make(f.state).rows.find(r => r.rid === f.rid).ok, false);
  f.Engine.setMakeBankFeed(f.state, true);
  const row = f.Engine.view.make(f.state).rows.find(r => r.rid === f.rid);
  assert.equal(row.ok, true);
  assert.equal(row.inputs[0][2], 100);
});

test("bank-fed smelting runs far beyond pack size and stores every bar", () => {
  const f = fixture();
  const before = f.p.xp10.smithing;
  run(f, -1, 405);
  assert.equal(bankQty(f, "steel_bar"), 100);
  assert.equal(bankQty(f, "iron_ore"), 0);
  assert.equal(bankQty(f, "coal"), 0);
  assert.equal(f.p.inv.every(s => s === null), true);
  assert.equal(f.state.ground.length, 0);
  assert.equal(f.p.act, null);
  assert.equal(f.p.stop, "out of materials");
  assert.ok(f.p.xp10.smithing > before);
  valid(f);
});

test("finite counts stop after the requested number, including custom quantities", () => {
  for (const n of [1, 5, 10, 37]) {
    const f = fixture();
    run(f, n, n * 4 + 8);
    assert.equal(bankQty(f, "steel_bar"), n);
    assert.equal(bankQty(f, "iron_ore"), 100 - n);
    assert.equal(bankQty(f, "coal"), 200 - n * 2);
    assert.equal(f.p.act, null);
    valid(f);
  }
});

test("bank mode never spends inventory ingredients", () => {
  const f = fixture("smelt_steel", [{ id: "iron_ore", qty: 1 }, { id: "coal", qty: 2 }]);
  f.Player.add(f.p, "iron_ore", 3);
  f.Player.add(f.p, "coal", 6);
  run(f, -1, 12);
  assert.equal(bankQty(f, "steel_bar"), 1);
  assert.equal(f.Player.count(f.p, "iron_ore"), 3);
  assert.equal(f.Player.count(f.p, "coal"), 6);
});

test("normal inventory crafting keeps its existing inputs and output destination", () => {
  const f = fixture();
  f.Player.add(f.p, "iron_ore", 2);
  f.Player.add(f.p, "coal", 4);
  assert.equal(f.Engine.make(f.state, f.rid, -1), true);
  for (let i = 0; i < 16; i++) f.Engine.tick(f.state);
  assert.equal(f.Player.count(f.p, "steel_bar"), 2);
  assert.equal(bankQty(f, "steel_bar"), 0);
  assert.equal(bankQty(f, "iron_ore"), 100);
  valid(f);
});

test("missing coal refuses before spending any ore", () => {
  const f = fixture("smelt_steel", [{ id: "iron_ore", qty: 5 }, { id: "coal", qty: 1 }]);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, -1), false);
  assert.equal(bankQty(f, "iron_ore"), 5);
  assert.equal(bankQty(f, "coal"), 1);
  assert.match(f.Engine.view.make(f.state).rows.find(r => r.rid === f.rid).why, /bank/);
});

test("level and carried-tool requirements still apply", () => {
  const low = fixture();
  low.p.xp10.smithing = 0;
  low.Engine.setMakeBankFeed(low.state, true);
  assert.equal(low.Engine.make(low.state, low.rid, 1), false);
  const f = fixture("smith_iron_dagger", [{ id: "iron_bar", qty: 3 }, { id: "hammer", qty: 1 }]);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, 1), false);
  f.Player.add(f.p, "hammer", 1);
  assert.equal(f.Engine.make(f.state, f.rid, 1), true);
  for (let i = 0; i < 6; i++) f.Engine.tick(f.state);
  assert.equal(bankQty(f, "iron_dagger"), 1);
  assert.equal(f.Player.count(f.p, "hammer"), 1);
});

test("a full pack does not block bank-fed production", () => {
  const f = fixture();
  f.p.inv = Array.from({ length: 28 }, () => ({ id: "hammer", qty: 1 }));
  run(f, 2, 9);
  assert.equal(bankQty(f, "steel_bar"), 2);
  assert.equal(f.state.ground.length, 0);
  valid(f);
});

test("full bank rejects production without consuming inputs", () => {
  const f = fixture();
  fillBank(f, ["steel_bar"]);
  assert.equal(f.p.bank.length, f.Rules.BANK_MAX);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, -1), false);
  assert.equal(bankQty(f, "iron_ore"), 100);
  assert.equal(bankQty(f, "coal"), 200);
  assert.match(f.Engine.view.make(f.state).rows.find(r => r.rid === f.rid).why, /no room/);
});

test("consuming the last input can free a bank slot for the output", () => {
  const f = fixture("smelt_gold", [{ id: "gold_ore", qty: 1 }]);
  fillBank(f, ["gold_bar"]);
  run(f, 1, 5);
  assert.equal(bankQty(f, "gold_ore"), 0);
  assert.equal(bankQty(f, "gold_bar"), 1);
  assert.equal(f.p.bank.length, f.Rules.BANK_MAX);
});

test("stack limits refuse a batch atomically", () => {
  const f = fixture();
  f.p.bank.push({ id: "steel_bar", qty: 2147483647 });
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, 1), false);
  assert.equal(bankQty(f, "iron_ore"), 100);
  assert.equal(bankQty(f, "steel_bar"), 2147483647);
});

test("all perk products and refunded inputs go back to the bank", () => {
  const f = fixture();
  const original = f.Player.perkRoll;
  f.Player.perkRoll = (s, skill, fx) => fx === "save" || fx === "twice";
  run(f, 1, 4);
  f.Player.perkRoll = original;
  assert.equal(bankQty(f, "steel_bar"), 2);
  assert.equal(bankQty(f, "iron_ore"), 100);
  assert.equal(bankQty(f, "coal"), 198);
  assert.equal(f.p.inv.every(s => s === null), true);
  valid(f);
});

test("capacity includes a possible double-output perk", () => {
  const f = fixture();
  f.p.bank.push({ id: "steel_bar", qty: 2147483646 });
  const original = f.Player.perkVal;
  f.Player.perkVal = (p, skill, fx, group) => fx === "twice" ? 0.1 : original(p, skill, fx, group);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, 1), false);
  assert.equal(bankQty(f, "iron_ore"), 100);
});

test("failed recipes bank their failure products without success XP", () => {
  const f = fixture("smelt_iron", [{ id: "iron_ore", qty: 2 }]);
  f.recipe.full = 99;
  f.recipe.fail = [["burnt_food", 1]];
  f.p.xp10.smithing = 24110;
  const before = f.p.xp10.smithing;
  f.Rules.makeChance = () => 0;
  run(f, 1, 4);
  assert.equal(bankQty(f, "burnt_food"), 1);
  assert.equal(bankQty(f, "iron_bar"), 0);
  assert.equal(f.p.xp10.smithing, before);
  assert.equal(bankQty(f, "iron_ore"), 1);
});

test("bank-fed jobs do not reload or produce offline, but stored goods persist", () => {
  const f = fixture();
  run(f, -1, 8);
  assert.equal(bankQty(f, "steel_bar"), 2);
  assert.match(f.Engine.status(f.state).doing.text, /bank-fed/);
  const saved = f.Engine.serialize(f.state);
  assert.equal(saved.act, null);
  const restored = f.Engine.deserialize(saved);
  assert.equal(restored.player.act, null);
  f.Engine.catchUp(restored, 1000);
  assert.equal(f.Player.bankCount(restored.player, "steel_bar"), 2);
  assert.deepEqual(Array.from(f.Engine.check(restored)), []);
});

test("inventory jobs still serialize for the original offline behavior", () => {
  const f = fixture();
  f.Player.add(f.p, "iron_ore", 5);
  f.Player.add(f.p, "coal", 10);
  assert.equal(f.Engine.make(f.state, f.rid, -1), true);
  assert.equal(f.Engine.serialize(f.state).act[0], "make");
});

test("removing a station stops production without spending another batch", () => {
  const f = fixture();
  run(f, -1, 4);
  f.Sim.setObj(f.state, f.p.map, 45, 45, "stump", 100000);
  for (let i = 0; i < 5; i++) f.Engine.tick(f.state);
  assert.equal(bankQty(f, "steel_bar"), 1);
  assert.equal(bankQty(f, "iron_ore"), 99);
  assert.equal(f.p.act, null);
});

test("bank feeding is unavailable for fire placement", () => {
  const f = fixture("light_amber_logs", [{ id: "amber_logs", qty: 10 }]);
  f.Player.add(f.p, "tinderbox", 1);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, 1), false);
  assert.equal(bankQty(f, "amber_logs"), 10);
});

test("mode controls only apply to an open make sheet", () => {
  const f = fixture();
  f.Engine.closeInterface(f.state);
  assert.equal(f.Engine.setMakeBankFeed(f.state, true), false);
});

test("open-game background catch-up continues a bank-fed job", () => {
  const f = fixture();
  run(f, -1, 0);
  f.Engine.catchUp(f.state, 405);
  assert.equal(bankQty(f, "steel_bar"), 100);
  assert.equal(f.p.act, null);
  valid(f);
});

test("cooking and jewellery use the same bank-fed path", () => {
  const cooked = fixture("cook_raw_vale_eel", [{ id: "raw_vale_eel", qty: 3 }]);
  run(cooked, 3, 30);
  assert.equal(bankQty(cooked, "vale_eel"), 3);
  assert.equal(bankQty(cooked, "raw_vale_eel"), 0);
  valid(cooked);
  const jewellery = fixture("craft_sapphire_amulet", [{ id: "gold_bar", qty: 3 }, { id: "sapphire", qty: 3 }]);
  jewellery.Player.add(jewellery.p, "jewellery_mould", 1);
  run(jewellery, 3, 15);
  assert.equal(bankQty(jewellery, "sapphire_amulet"), 3);
  valid(jewellery);
});

test("quest-gated recipes still require unlocks and still advance crafting objectives", () => {
  const f = fixture("smith_emberward", [{ id: "steel_bar", qty: 3 }, { id: "sapphire", qty: 1 }]);
  f.Player.add(f.p, "hammer", 1);
  f.Engine.setMakeBankFeed(f.state, true);
  assert.equal(f.Engine.make(f.state, f.rid, 1), false);
  assert.equal(bankQty(f, "steel_bar"), 3);
  f.p.quests.embers_beneath = 10;
  assert.equal(f.Engine.make(f.state, f.rid, 1), true);
  for (let i = 0; i < 6; i++) f.Engine.tick(f.state);
  assert.equal(bankQty(f, "emberward"), 1);
  assert.equal(f.p.quests.embers_beneath, 20);
});

test("capacity is rechecked during a job, not just at startup", () => {
  const f = fixture();
  run(f, -1, 4);
  f.p.bank.find(e => e.id === "steel_bar").qty = 2147483647;
  for (let i = 0; i < 5; i++) f.Engine.tick(f.state);
  assert.equal(bankQty(f, "iron_ore"), 99);
  assert.equal(bankQty(f, "coal"), 198);
  assert.equal(f.p.stop, "bank full");
  assert.equal(f.p.act, null);
});

test("bank-fed production preserves the recipe's XP and timing", () => {
  const bank = fixture();
  const pack = fixture();
  pack.Player.add(pack.p, "iron_ore", 3);
  pack.Player.add(pack.p, "coal", 6);
  run(bank, 3, 0);
  assert.equal(pack.Engine.make(pack.state, pack.rid, 3), true);
  for (let i = 0; i < 12; i++) {
    bank.Engine.tick(bank.state);
    pack.Engine.tick(pack.state);
    assert.equal(bank.p.xp10.smithing, pack.p.xp10.smithing);
    assert.equal(bankQty(bank, "steel_bar"), pack.Player.count(pack.p, "steel_bar"));
  }
});
