const { readFileSync } = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "..", "cloud_plugin-fdb0-3b0d-ec7f-95be18c.py"), "utf8");
const engine = source.split("/*ENGINE-START*/")[1].split("/*ENGINE-END*/")[0];
const script = new vm.Script(engine + "\n({ Engine, Data, Rules, Player, Sim, Script, Util, World });");

module.exports = {
  source,
  loadEngine: () => script.runInNewContext()
};
