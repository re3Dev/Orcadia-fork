# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# name = "Orcadia"
# description = "A click-to-move fantasy adventure in a panel beside the 3D view: chop, mine, fish, smith, cook, craft, fight and quest. Skilling keeps going on its own while you slice."
# author = "OrcaCloud"
# version = "0.2.0"
# type = "script"
# ///
"""Orcadia -- a single-player medieval adventure for OrcaSlicer.

Run it from the Plugins dialog. It opens a panel docked on the right of the 3D view (the Options
tab can switch it to a separate window). Click to walk; chop, mine, fish, smith, cook, craft and
fight across a hand-drawn world, then take on five quests. Skilling and fighting keep going on
their own, so the game plays along while you slice, and time spent away is caught up on return.

The game is self-contained: it does not read or change anything in OrcaSlicer and starts at once.
The plugin only keeps the save (a JSON string) and the panel placement:

  page   --orca.postMessage({command: 'hello'})-->        plugin posts {command: 'state', save, dock}
  page   --orca.postMessage({command: 'save', save})-->   plugin.save_config()
  page   --orca.postMessage({command: 'dock', dock})-->   plugin.save_config()
  plugin --{command: 'reset'}-->                         page starts a new character

The save lives in this capability's config under "save", so "Restore defaults" in the Config tab
starts a new character (an open panel is told to reset). The defaults carry "restored", the time
they were written, and the next save drops it. Only a "restored" newer than the panel's last save
resets, so pressing Save on an old copy of the config in the Config tab never wipes the character.
A save the page cannot read is copied to "save_bad" before the new character's first save replaces
it. No network, files, subprocesses or threads.

Play Orcadia in one OrcaSlicer window at a time: each OrcaSlicer process reads the plugin config
once at startup, so a second window holds an older copy of the save and will overwrite newer
progress.
"""
import json
import time

import orca

DOCKS = ("left", "right", "bottom", "float")
DOCK_CHOICES = DOCKS + ("window",)
MAX_SAVE_CHARS = 100_000

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><style>/* ----------------------------------------------------------------
   ------------------ Orcadia page: chrome + overlays ---------------
   ----------------------------------------------------------------
   Three palettes. Host chrome (status strip, tooltips, modal) uses the host's --orca-* variables. Chat,
   side panel and the minimap surround are a fallen parchment scroll, one fixed palette in both OrcaSlicer
   themes. Everything in or over #view (windows, sheets, menu, banner, toast) uses the fixed game palette.
   Pure gradients: no images or external assets. */
:root{--bg:var(--orca-bg,#2d2d31);--fg:var(--orca-fg,#efeff0);--mu:var(--orca-muted,#909090);--bd:var(--orca-border,#36363b);--ac:var(--orca-accent,#00675b);--acf:var(--orca-accent-fg,#fff);--font:var(--orca-font,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif)}
html,body{height:100%;margin:0;overflow:hidden;overscroll-behavior:none}
body{background:var(--bg);color:var(--fg);font:13px/1.3 var(--font)}
[hidden]{display:none!important}
html button{font:inherit;color:inherit;background:none;border:0;border-radius:0;padding:0;margin:0;cursor:pointer;filter:none;outline:none}
html button:hover{filter:none}
html button:disabled{cursor:default;opacity:.4}
svg{display:block;flex:none}

/* ---------------------------- Grid ---------------------------- */
/* T at every width; C only when the panel is too small for T (Layout). */
#app{display:grid;height:100%;position:relative;-webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
#app>*{min-width:0;min-height:0}
#game,#minimap,#inv{touch-action:none}
#game,#minimap{image-rendering:pixelated}
#app[data-layout=T]{grid-template:"status status" 26px "view view" 1fr "chat side" var(--bottom) / 1fr var(--side)}
#app[data-layout=C]{grid-template:"status" 26px "view" 1fr "tabs" var(--bottom,30px) / 1fr}
#app[data-layout=C] #side{grid-area:tabs}

/* ------------------------ Status strip ------------------------ */
#status{grid-area:status;position:relative;display:flex;align-items:center;gap:6px;padding:0 8px;box-shadow:inset 0 -1px var(--bd);background:rgba(128,128,128,.07);font-size:12px;white-space:nowrap;overflow:hidden}
#status.stop{background:rgba(255,170,0,.18)}
#st-dot{flex:none;width:8px;height:8px;border-radius:50%;background:var(--mu)}
#st-dot[data-dot=walk]{background:var(--fg)}
#st-dot[data-dot=work]{background:#37c871}
#st-dot[data-dot=fight],#st-dot[data-dot=dead]{background:#ff6b6b}
#st-dot[data-dot=stop]{background:#ffb000;animation:pulse 1.2s ease-in-out infinite}
/* The doing text keeps its room; the goal (10.15) fills what is left and is cut first. */
#st-text{flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis}
#st-goal{flex:1 1 0;min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--mu)}
#st-nosave{flex:none;padding:1px 7px;border-radius:9px;background:rgba(255,176,0,.2);color:#ffb000;font-size:11px;font-weight:600}
#st-grave{flex:none;padding:1px 7px;border-radius:9px;background:rgba(128,128,128,.22);font-size:11px;font-weight:600}
/* Rested (10.14): host ink on a gold tint, readable in both OrcaSlicer themes. */
#st-rested{flex:none;padding:1px 7px;border-radius:9px;background:rgba(240,184,30,.3);box-shadow:inset 0 0 0 1px rgba(240,184,30,.55);font-size:11px;font-weight:600}
#st-season{flex:none;display:flex;align-items:center;gap:4px;color:var(--mu);font-size:11px;font-weight:600}
#st-season .ico{width:16px;height:16px}
#st-pack{flex:none;display:flex;align-items:center;gap:3px;color:var(--mu)}
#st-pack svg{width:13px;height:13px}
#st-pack.full{color:#ffb000}
#st-bar{position:absolute;left:0;right:0;bottom:0;height:2px}
#st-fill{display:block;height:100%;width:0;transition:width .3s}
@keyframes pulse{50%{opacity:.25}}
@keyframes flash{0%,60%{background:#f3cf6a;box-shadow:inset 0 0 0 1px #6b4a17,0 0 8px rgba(243,207,106,.75)}}
@keyframes fadein{from{opacity:0}}

/* ---------------------------- View ---------------------------- */
#view{grid-area:view;position:relative;overflow:hidden;background:#0e0b09}
#game{position:absolute;left:0;top:0;display:block;cursor:default}
#hover{position:absolute;left:6px;top:6px;z-index:5;pointer-events:none;font:bold 13px/16px var(--font);color:#fff;text-shadow:1px 1px 0 #000;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.k-npc{color:#ffff00}.k-pet{color:#ffb060}.k-obj{color:#00ffff}.k-item{color:#ff9040}.k-more{color:#b0a080;font-weight:normal}
#banner{position:absolute;top:28px;left:8px;right:var(--mmr,8px);z-index:2;pointer-events:none;display:flex;justify-content:center;animation:fadein .2s}
#banner span{max-width:100%;padding:4px 12px;border-radius:12px;background:rgba(27,20,13,.9);border:1px solid #6a5a44;color:#f0e6d0;font:600 12px/16px var(--font);text-align:center;box-sizing:border-box}
#banner.warn span{border-color:#ffb000;color:#ffd166}
#banner.good span{border-color:#2c9c3c;color:#8fe08f}
#banner.season span{display:flex;align-items:center;gap:6px;border-color:#b0a080}
#banner.season .ico{flex:none;width:16px;height:16px}
#app.asking #banner{top:calc(32px + var(--ask-h,48px))}
#ask{position:absolute;top:28px;left:8px;right:var(--mmr,8px);z-index:3;pointer-events:none;display:flex;justify-content:center;animation:fadein .2s}
#ask .ab{pointer-events:auto;display:flex;flex-direction:column;align-items:center;gap:5px;max-width:100%;padding:6px 10px;box-sizing:border-box;border-radius:10px;background:rgba(27,20,13,.94);border:1px solid #ffb000;color:#f0e6d0;font:600 12px/16px var(--font);text-align:center}
#ask .ab div{display:flex;flex-wrap:wrap;justify-content:center;gap:6px}
#toast{position:absolute;left:50%;bottom:calc(var(--toast-b,var(--sheet-h,0px)) + 8px);transform:translateX(-50%);width:min(300px,calc(100% - 16px));height:64px;z-index:2;pointer-events:none;display:flex;align-items:center;gap:10px;padding:0 12px;box-sizing:border-box;background:#2a231b;border:2px solid #6a5a44;box-shadow:inset 0 0 0 2px #15100b,0 4px 12px rgba(0,0,0,.4);color:#f0e6d0;animation:fadein .25s}
#app[data-layout=T] #toast{bottom:calc(var(--toast-b,var(--sheet-h,0px)) + 14px)}
#toast b{display:block;font:bold 14px/18px var(--font);color:#ff9a2a}
#toast span{display:block;font-size:12px;color:#b0a080;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#toast div{min-width:0}
#toast em{display:block;font:bold 11px/14px var(--font);font-style:normal;color:#f3cf6a}

/* ---------------------- Parchment palette ---------------------- */
/* Inks for the scroll. #chat (T) and #side re-scope the chrome variables, so muted captions, rules and
   the selection colour follow without per-rule overrides. Red ink marks a selection, green ink an "on". */
#chat,#side,#mm{--ink:#26170a;--ink2:#4f371d;--inkr:#7a1d10;--ing:#2c5e22;--rule:rgba(92,54,20,.36);--tint:rgba(120,74,28,.12);--tint2:rgba(120,74,28,.21)}
#app[data-layout=T] #chat,#side{--fg:#26170a;--mu:#4f371d;--bd:rgba(92,54,20,.36);--ac:#7a1d10;--acf:#f7ebcf;color:var(--ink)}
/* The sheet: burnt, foxed edges and corners, warm stains and highlights, a faint grain, then the paper. */
:root{--parch:
  radial-gradient(ellipse 11px 46px at 0 36%,rgba(70,36,10,.55),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 9px 30px at 0 79%,rgba(70,36,10,.5),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 7px 18px at 0 57%,rgba(70,36,10,.42),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 11px 40px at 100% 26%,rgba(70,36,10,.55),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 9px 28px at 100% 66%,rgba(70,36,10,.5),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 60px 9px at 22% 100%,rgba(70,36,10,.55),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 84px 8px at 60% 100%,rgba(70,36,10,.5),rgba(70,36,10,0) 70%),
  radial-gradient(ellipse 46px 9px at 88% 100%,rgba(70,36,10,.55),rgba(70,36,10,0) 70%),
  radial-gradient(circle at 0 100%,rgba(54,26,4,.82),rgba(54,26,4,0) 24px),
  radial-gradient(circle at 100% 100%,rgba(54,26,4,.82),rgba(54,26,4,0) 24px),
  linear-gradient(90deg,rgba(50,24,4,.9),rgba(96,54,18,.44) 2.5px,rgba(140,92,40,.12) 6px,rgba(140,92,40,0) 10px),
  linear-gradient(270deg,rgba(50,24,4,.9),rgba(96,54,18,.44) 2.5px,rgba(140,92,40,.12) 6px,rgba(140,92,40,0) 10px),
  linear-gradient(0deg,rgba(50,24,4,.92),rgba(96,54,18,.44) 2.5px,rgba(140,92,40,.12) 6px,rgba(140,92,40,0) 10px),
  radial-gradient(circle at 5px 22%,rgba(112,64,20,.5),rgba(112,64,20,.18) 1.5px,rgba(112,64,20,0) 3.5px),
  radial-gradient(circle at 4px 63%,rgba(112,64,20,.4),rgba(112,64,20,.14) 1px,rgba(112,64,20,0) 2.5px),
  radial-gradient(circle at calc(100% - 5px) 44%,rgba(112,64,20,.46),rgba(112,64,20,.16) 1.5px,rgba(112,64,20,0) 3.5px),
  radial-gradient(circle at 47% calc(100% - 4px),rgba(112,64,20,.44),rgba(112,64,20,.16) 1.5px,rgba(112,64,20,0) 3.5px),
  radial-gradient(circle at 31% calc(100% - 3px),rgba(112,64,20,.36),rgba(112,64,20,.12) 1px,rgba(112,64,20,0) 2.5px),
  radial-gradient(circle at calc(100% - 64px) calc(100% - 18px),rgba(112,64,20,.3),rgba(112,64,20,.1) 1.5px,rgba(112,64,20,0) 3px),
  radial-gradient(ellipse 130% 160% at 45% 35%,rgba(104,60,20,0) 64%,rgba(104,60,20,.14) 100%),
  radial-gradient(ellipse 150px 110px at 70px 72%,rgba(160,106,44,.11),rgba(160,106,44,0) 72%),
  radial-gradient(ellipse 28% 42% at 58% 30%,rgba(146,96,38,.1),rgba(146,96,38,0) 72%),
  radial-gradient(ellipse 90px 120px at calc(100% - 60px) 40%,rgba(154,98,40,.12),rgba(154,98,40,0) 72%),
  radial-gradient(ellipse 30% 40% at 34% 30%,rgba(255,247,222,.26),rgba(255,247,222,0) 72%),
  radial-gradient(ellipse 24% 34% at 79% 64%,rgba(255,247,222,.2),rgba(255,247,222,0) 72%),
  repeating-linear-gradient(33deg,rgba(116,76,28,.03) 0 1px,rgba(116,76,28,0) 1px 4px),
  repeating-linear-gradient(-58deg,rgba(255,248,226,.045) 0 1px,rgba(255,248,226,0) 1px 5px),
  linear-gradient(180deg,#d7b77d,#dfc48e 16%,#ddc18a 62%,#d3b278)}

/* T: one sheet spans the chat + side band under the view and hangs from a paper roll on the seam (z 3,
   click-through, 11 px into the view; the toast and windows sit 6 px higher to clear it). #chat and #side
   are positioned so they paint above the sheet. */
#app[data-layout=T]::before{content:"";position:absolute;left:0;right:0;bottom:0;height:var(--bottom);background:linear-gradient(180deg,rgba(62,32,8,.55),rgba(62,32,8,.14) 7px,rgba(62,32,8,0) 13px),var(--parch)}
#app[data-layout=T]::after{content:"";position:absolute;left:0;right:0;bottom:calc(var(--bottom) - 7px);z-index:3;height:18px;pointer-events:none;filter:drop-shadow(0 2px 1.5px rgba(30,14,2,.5));background:
  radial-gradient(circle at 8px 7px,#eabb7c 0,#b27a42 3px,#7a4620 6.5px,#3c1c08 8.6px,rgba(60,28,8,0) 9px) 0 0/18px 18px no-repeat,
  radial-gradient(circle at 10px 7px,#eabb7c 0,#b27a42 3px,#7a4620 6.5px,#3c1c08 8.6px,rgba(60,28,8,0) 9px) 100% 0/18px 18px no-repeat,
  linear-gradient(90deg,rgba(20,8,0,.45),rgba(20,8,0,0) 40%,rgba(20,8,0,0) 60%,rgba(20,8,0,.45)) 16px 50%/4px 13px no-repeat,
  linear-gradient(90deg,rgba(20,8,0,.45),rgba(20,8,0,0) 40%,rgba(20,8,0,0) 60%,rgba(20,8,0,.45)) calc(100% - 16px) 50%/4px 13px no-repeat,
  linear-gradient(180deg,#220e04,#7a4a22 30%,#c48c54 44%,#6a3c18 72%,#1e0c02) 16px 50%/4px 13px no-repeat,
  linear-gradient(180deg,#220e04,#7a4a22 30%,#c48c54 44%,#6a3c18 72%,#1e0c02) calc(100% - 16px) 50%/4px 13px no-repeat,
  radial-gradient(ellipse closest-side,#5a3a18 0 18%,rgba(90,58,24,0) 24%,#a8834e 32%,#e2c896 40%,#a17a46 50%,#e6cd9c 60%,#9a7444 70%,#dcc08a 80%,#6b4520 92%,rgba(70,40,14,0) 100%) 27px 50%/6px 16px no-repeat,
  radial-gradient(ellipse closest-side,#5a3a18 0 18%,rgba(90,58,24,0) 24%,#a8834e 32%,#e2c896 40%,#a17a46 50%,#e6cd9c 60%,#9a7444 70%,#dcc08a 80%,#6b4520 92%,rgba(70,40,14,0) 100%) calc(100% - 27px) 50%/6px 16px no-repeat,
  linear-gradient(90deg,rgba(74,38,10,.62),rgba(74,38,10,.18) 4px,rgba(80,44,12,0) 9px,rgba(80,44,12,0) 8%,rgba(120,74,26,.2) 13%,rgba(120,74,26,0) 19%,rgba(255,248,226,.12) 31%,rgba(255,248,226,0) 38%,rgba(120,74,26,.16) 50%,rgba(120,74,26,.04) 54%,rgba(120,74,26,0) 58%,rgba(120,74,26,.22) 69%,rgba(120,74,26,0) 76%,rgba(255,248,226,.1) 86%,rgba(80,44,12,0) calc(100% - 9px),rgba(74,38,10,.18) calc(100% - 4px),rgba(74,38,10,.62)) 50% 50%/calc(100% - 60px) 16px no-repeat,
  linear-gradient(180deg,#54320e,#8a6031 9%,#bb965c 24%,#d6b983 38%,#e0c795 45%,#d0b17a 57%,#b38f53 72%,#8a6031 87%,#502e0b) 50% 50%/calc(100% - 60px) 16px no-repeat,
  linear-gradient(180deg,#241105,#5a3416 16%,#9a6434 38%,#c48e58 46%,#8a5a2e 60%,#4e2a10 82%,#1f0e04) 50% 50%/calc(100% - 36px) 9px no-repeat}
#app[data-layout=T] #side{position:relative}

/* ------------------- Minimap: parchment disc ------------------- */
#mm{position:absolute;z-index:1;width:var(--mm,84px);height:var(--mm,84px)}
#mm::before{content:"";position:absolute;left:-7px;top:-7px;width:calc(var(--mm,84px) + 14px);height:calc(var(--mm,84px) + 14px);border-radius:50%;box-shadow:0 2px 6px rgba(20,10,2,.55),0 0 0 1px rgba(46,22,4,.55);background:
  radial-gradient(circle at 17% 83%,rgba(108,60,18,.5),rgba(108,60,18,.16) 1.2px,rgba(108,60,18,0) 2.6px),
  radial-gradient(circle at 73% 10%,rgba(108,60,18,.42),rgba(108,60,18,.12) 1px,rgba(108,60,18,0) 2.2px),
  radial-gradient(circle at 96% 58%,rgba(108,60,18,.4),rgba(108,60,18,.12) 1px,rgba(108,60,18,0) 2.2px),
  radial-gradient(circle closest-side,rgba(60,30,8,0) calc(100% - 8px),rgba(60,30,8,.5) calc(100% - 7px),rgba(60,30,8,0) calc(100% - 4.8px),rgba(255,248,226,0) calc(100% - 4.2px),rgba(255,248,226,.3) calc(100% - 3.2px),rgba(140,90,40,.1) calc(100% - 2.3px),rgba(64,32,8,.62) calc(100% - .6px),rgba(64,32,8,0) 100%),
  radial-gradient(ellipse 60% 45% at 80% 78%,rgba(116,68,22,.3),rgba(116,68,22,0) 70%),
  radial-gradient(ellipse 50% 40% at 12% 40%,rgba(136,82,30,.24),rgba(136,82,30,0) 70%),
  radial-gradient(circle at 36% 30%,#dfc48f,#d2b37a 55%,#b9965b)}
#minimap{position:absolute;right:0;top:0;width:var(--mm,84px);height:var(--mm,84px);border-radius:50%;cursor:pointer}
.orb{position:absolute;right:0;display:flex;align-items:center;gap:4px;height:22px;min-width:52px;padding:0 7px 0 3px;border-radius:11px;box-sizing:border-box;background:linear-gradient(180deg,#e4cc98,#cfb077);border:1px solid #6e4520;box-shadow:0 1px 3px rgba(20,10,2,.5),inset 0 1px rgba(255,248,228,.55);color:#26170a;font:bold 12px/1 var(--font);white-space:nowrap}
.orb i{flex:none;width:14px;height:14px;border-radius:50%;box-shadow:inset 0 0 0 1px #2a1606;background:#8a6a42}
#orb-hp{top:calc(var(--mm,84px) + 6px)}
#orb-hp i{background:linear-gradient(to top,#c02828 var(--p,100%),#8a6a42 var(--p,100%))}
#orb-hp.low b{color:#7a110b}
#orb-run{top:calc(var(--mm,84px) + 34px);cursor:pointer}
#orb-run.on i{background:#2c9c3c}
#orb-run:hover{border-color:#26170a}
#mm-map{position:absolute;left:-12px;bottom:-8px;display:flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;box-sizing:border-box;background:radial-gradient(circle at 36% 30%,#e4cc98,#cfb077 60%,#b9965b);border:1px solid #6e4520;box-shadow:0 1px 3px rgba(20,10,2,.5),inset 0 1px rgba(255,248,228,.55)}
#mm-map svg{width:18px;height:18px}
#mm-map:hover{border-color:#26170a}
#win[data-kind=map] .wb{display:flex;align-items:center;justify-content:center;overflow:hidden}
#win[data-kind=map] canvas{flex:none;image-rendering:pixelated;box-shadow:0 0 0 2px #5a4528;touch-action:none;cursor:grab}
#win[data-kind=map] canvas:active{cursor:grabbing}

/* ---------------------------- Chat ---------------------------- */
/* T: inks on the sheet. C: a click-through overlay of bright lines over the world. */
#chat{grid-area:chat;position:relative;display:flex;flex-direction:column;overflow:hidden}
#chatlog{flex:1;overflow-y:auto;margin-top:8px;padding:4px 8px 3px 11px;font-size:var(--cf,12px);line-height:var(--cl,15px);overflow-wrap:anywhere;text-shadow:0 1px 0 rgba(255,246,220,.28)}
#chatlog .x{color:var(--mu)}
#chatempty{position:absolute;left:0;right:0;top:0;padding:12px 8px 3px 11px;font-size:var(--cf,12px);line-height:var(--cl,15px);color:var(--mu)}
#chatempty button{color:var(--fg);text-decoration:underline}
#chatlog[data-filter=game] .ln:not(.f-game),#chatlog[data-filter=skill] .ln:not(.f-skill),#chatlog[data-filter=loot] .ln:not(.f-loot),#chatlog[data-filter=fight] .ln:not(.f-fight){display:none}
.c-game,.c-npc{color:var(--fg)}.c-skill{color:#134415}.c-loot{color:#6b2a00}.c-fight{color:#7a110b}.c-quest{color:#4c1d78}.c-warn{color:#524000;font-weight:500}.c-examine{color:var(--mu);font-style:italic}
#chatfilters{flex:none;display:flex;gap:4px;height:24px;margin:0 8px 5px;padding:0 4px;box-shadow:inset 0 1px var(--rule),inset 0 2px rgba(255,246,220,.3)}
#chatfilters button{flex:1;max-width:112px;font-size:11px;color:var(--mu)}
@media (max-width:439px){#chatfilters button{font-size:10px}}
/* The narrowest T (340..379): the labels need the row's whole width, raised and right of the burnt corner. */
@media (max-width:379px){#chatfilters{margin:0 1px 10px 12px;padding:0 2px}}
#chatfilters button:hover{color:var(--fg)}
#chatfilters button.on{color:var(--fg);font-weight:600;box-shadow:inset 0 -2px var(--ac)}
#newmsgs{position:absolute;left:50%;bottom:30px;transform:translateX(-50%);padding:2px 10px;border-radius:10px;background:var(--ac);color:var(--acf);box-shadow:0 0 0 1px #4a1208,0 2px 4px rgba(40,18,4,.35);font-size:11px;white-space:nowrap}
#chatlog::-webkit-scrollbar,#pane>section::-webkit-scrollbar{width:8px}
#chatlog::-webkit-scrollbar-track,#pane>section::-webkit-scrollbar-track{background:transparent}
#chatlog::-webkit-scrollbar-thumb,#pane>section::-webkit-scrollbar-thumb{background:rgba(104,62,24,.45);border-radius:4px;border:2px solid transparent;background-clip:padding-box}
#chatlog::-webkit-scrollbar-thumb:hover,#pane>section::-webkit-scrollbar-thumb:hover{background-color:rgba(104,62,24,.7)}
#app[data-layout=C] #chat{position:absolute;left:0;right:0;bottom:var(--bottom,30px);height:66px;z-index:2;pointer-events:none;background:linear-gradient(rgba(0,0,0,0),rgba(0,0,0,.4))}
#app[data-layout=C] #chatlog{overflow:hidden;text-shadow:1px 1px 0 #000;padding:0 6px;margin:3px 0}
#app[data-layout=C] #chatlog .x{color:inherit;opacity:.65}
#app[data-layout=C] #chatlog .c-game,#app[data-layout=C] #chatlog .c-npc{color:#fff}
#app[data-layout=C] #chatlog .c-skill{color:#6fd36f}#app[data-layout=C] #chatlog .c-loot{color:#ffb050}#app[data-layout=C] #chatlog .c-fight{color:#ff7070}#app[data-layout=C] #chatlog .c-quest{color:#c9a0ff}#app[data-layout=C] #chatlog .c-warn{color:#ffd166}
#app[data-layout=C] #chatlog .c-examine{color:#c8c0b0}
#app[data-layout=C] #chatfilters,#app[data-layout=C] #newmsgs,#app[data-layout=C] #chatempty,#app[data-layout=C].chat-off #chat,#app[data-layout=C].pane-open #chat,#app[data-layout=C].sheet-open #chat{display:none}

/* ------------------------ Side column ------------------------- */
/* T: the right part of the sheet (a seam on its left). C: the tab row and the opened pane are parchment
   sheets of their own. */
#side{grid-area:side;display:flex;flex-direction:column;overflow:hidden;box-shadow:inset 1px 0 rgba(92,54,20,.32),inset 2px 0 rgba(255,246,220,.34)}
#tabs{flex:none;display:flex;height:var(--tabs,36px);margin:0 4px;box-shadow:inset 0 -1px var(--rule),0 1px rgba(255,246,220,.3)}
/* Interface size (--ui): each pane section's blocks and windows' contents (not the map) are drawn at that zoom;
   their containers keep the sizes Layout gives, so only content-sized boxes are zoomed. The tab row is sized by
   Layout instead (--tabs, --tab-ico), so its glyphs stay whole multiples of their art. */
#pane>section>*,#win:not([data-kind=map]) .wh,#win:not([data-kind=map]) .wb>*,#win:not([data-kind=map]) .wf{zoom:var(--ui,1)}
.pet canvas{image-rendering:pixelated}
#tabs button{flex:1;position:relative;display:flex;align-items:center;justify-content:center;color:var(--mu)}
#app[data-layout=T] #tabs button{align-items:flex-end;padding-bottom:3px}
#tabs button:hover{color:var(--fg);background:var(--tint)}
#tabs button.on{color:var(--fg);background:var(--tint2);box-shadow:inset 0 -2px var(--ac)}
#tabs .ico{width:var(--tab-ico,24px);height:var(--tab-ico,24px)}
#tabs button.badge::after{content:"";position:absolute;top:calc(50% - var(--tab-ico,24px) / 2 - 2px);right:calc(50% - var(--tab-ico,24px) / 2 - 3px);width:6px;height:6px;border-radius:50%;background:#e08a00;box-shadow:0 0 0 1px #4a260c}
#app[data-layout=T] #tabs button.badge::after{top:auto;bottom:calc(var(--tab-ico,24px) - 4px)}
#pane{flex:1;position:relative;overflow:hidden}
#pane>section{display:none;height:100%;overflow-y:auto;overflow-x:hidden;padding:6px;box-sizing:border-box}
#pane>section.on{display:block}
#app[data-layout=C] #side{display:block;box-shadow:inset 0 1px rgba(60,30,8,.6);background:linear-gradient(180deg,rgba(62,32,8,.28),rgba(62,32,8,0) 6px),linear-gradient(90deg,rgba(50,24,4,.8),rgba(96,54,18,.3) 3px,rgba(96,54,18,0) 9px),linear-gradient(270deg,rgba(50,24,4,.8),rgba(96,54,18,.3) 3px,rgba(96,54,18,0) 9px),radial-gradient(ellipse 40% 120% at 30% 40%,rgba(255,247,222,.22),rgba(255,247,222,0) 72%),repeating-linear-gradient(33deg,rgba(116,76,28,.03) 0 1px,rgba(116,76,28,0) 1px 4px),linear-gradient(180deg,#dabd85,#d3b27a)}
#app[data-layout=C] #pane{position:absolute;left:0;right:0;bottom:var(--bottom,30px);height:var(--pane-c,264px);z-index:4;background:linear-gradient(180deg,rgba(62,32,8,.3),rgba(62,32,8,0) 8px),var(--parch);box-shadow:0 -1px #4a260c,0 -4px 12px rgba(0,0,0,.35)}
#app[data-layout=C]:not(.pane-open) #pane{display:none}
/* C: the pane is a full-width sheet; text keeps clear of its burnt sides. */
#app[data-layout=C] #pane>section{padding:6px 12px}
#app[data-layout=C].store #pane{height:var(--pane-cs,192px)}
.muted{color:var(--mu)}
.hd{font-weight:600;margin:0 0 6px}

/* ----------------------- Items and slots ---------------------- */
/* Stack numbers: classic yellow/white/green. Stone windows give them a drop shadow; on the scroll they are
   outlined in ink so they hold on the paper. */
.ico{display:block;width:32px;height:32px;background-repeat:no-repeat;pointer-events:none}
.i16{display:inline-block;width:16px;height:16px;overflow:hidden;vertical-align:-3px}
.i16 .ico{transform:scale(.5);transform-origin:0 0}
.q{position:absolute;left:2px;top:0;font:bold 11px/13px var(--font);text-shadow:1px 1px 0 #000;pointer-events:none}
.q-y{color:#ffff00}.q-w{color:#fff}.q-g{color:#00ff80}
#side .q{text-shadow:-1px 0 0 #1b0f04,1px 0 0 #1b0f04,0 -1px 0 #1b0f04,0 1px 0 #1b0f04,1px 1px 0 #1b0f04}
#side .q-y{color:#ffe14a}#side .q-w{color:#fff8e6}#side .q-g{color:#3ce87a}
#inv{display:grid;grid-template-columns:repeat(4,var(--sw,44px));grid-auto-rows:var(--sh,36px);justify-content:center}
.slot{position:relative;display:flex;align-items:center;justify-content:center;border-radius:3px}
#inv .slot.has:hover{background:var(--tint2)}
.slot.use{box-shadow:inset 0 0 0 1px #26170a,0 0 0 1px rgba(255,246,220,.7)}
.slot.drag .ico,.slot.drag .q{opacity:.3}
/* A note: the item at 3/4 size on a slip of paper. */
.note{display:flex;align-items:center;justify-content:center;width:28px;height:26px;box-sizing:border-box;background:linear-gradient(180deg,#f4ead0,#dccb9c);border:1px solid #7a5a32;border-radius:2px;box-shadow:1px 1px 0 rgba(27,15,4,.45);pointer-events:none}
.note .ico{flex:none;transform:scale(.72)}
.slot.drag .note{opacity:.3}.slot.drag .note .ico{opacity:1}
.wf .as{display:flex;align-items:center;gap:4px;margin-left:6px}
#ghost{position:fixed;z-index:10;pointer-events:none;opacity:.8;width:32px;height:32px}
/* The gap gives way on a short T band (slots under 36) so the cross and its stats fit without a scroll. */
#equip{display:grid;grid-template-columns:repeat(3,36px);grid-template-rows:repeat(5,36px);gap:min(8px,calc(var(--sh,36px) * 1.75 - 55px));justify-content:center;grid-template-areas:". head ." "cape neck ." "weapon body shield" ". legs ." "hands feet ring"}
.eq{position:relative;display:flex;align-items:center;justify-content:center;border-radius:4px;background:var(--tint);box-shadow:inset 0 0 0 1px var(--rule),inset 0 1px 3px rgba(70,40,12,.22),0 1px 0 rgba(255,246,220,.4)}
.eq.has:hover{background:var(--tint2)}
.eq .ghost{opacity:.42;filter:sepia(1) saturate(.7) brightness(.62)}
#eqstats{margin-top:6px;text-align:center;font-size:12px;color:var(--mu);line-height:15px}

/* ------------------------- Side panes ------------------------- */
/* Selection is red ink (--ac on the scroll); an "on" switch is green ink; a level-up flashes gold. */
.cb-w{display:flex;align-items:center;gap:6px;height:32px}
.cb-w div{min-width:0}
.cb-w b,.cb-w span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cb-w span{font-size:12px;color:var(--mu)}
.cb-lvl{font-weight:600;line-height:16px;margin:2px 0 4px}
.cb-eatrow{display:flex;align-items:center;gap:8px;margin:2px 0 0}
.cb-eatrow span{flex:none;font-size:12px;color:var(--mu)}
.cb-eatrow .seg{flex:1}
.cb-ph{display:flex;justify-content:space-between;align-items:baseline;margin:10px 0 4px;border-top:1px solid var(--rule);padding-top:6px}
.cb-ph span{font-size:12px;color:var(--mu)}
.pet{display:flex;align-items:center;gap:6px;min-height:40px;padding:3px 4px;margin-bottom:3px;border-radius:4px;background:var(--tint);box-shadow:inset 0 0 0 1px var(--rule)}
.pet.on{box-shadow:inset 0 0 0 1px var(--ing),inset 0 0 0 2px rgba(40,90,30,.25)}
.pet canvas{flex:none}
.pet>div{flex:1;min-width:0}
.pet b{display:block;font-size:12px;line-height:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pet span{display:block;font-size:11px;line-height:13px;color:var(--mu);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pet button{flex:none;height:24px;padding:0 5px;border-radius:4px;font-size:11px;box-shadow:inset 0 0 0 1px var(--rule);background:rgba(255,246,220,.3)}
.pet button:hover{background:var(--tint2)}
.pet.lock{opacity:.6}
.pet-q{flex:none;width:36px;text-align:center;font-style:normal;font-weight:700;color:var(--mu)}
.pet-bar{display:block;height:2px;margin-top:2px;background:rgba(80,48,18,.2)}
.pet-bar i{display:block;height:100%;background:var(--ing)}
.cb-st{display:grid;grid-template-columns:repeat(2,minmax(0,88px));gap:4px;justify-content:center}
.cb-st button{height:44px;border-radius:4px;background:var(--tint);box-shadow:inset 0 0 0 1px var(--rule);font-size:12px;line-height:14px}
.cb-st button:hover:not(.on){background:var(--tint2)}
.cb-st button span{display:block;font-size:11px;color:var(--mu)}
.cb-st button.on{background:var(--ac);color:var(--acf);box-shadow:inset 0 0 0 1px #4a1208}
.cb-st button.on span{color:var(--acf);opacity:.85}
.tgl{display:flex;align-items:center;justify-content:space-between;width:100%;height:32px;gap:8px;text-align:left}
.sw{flex:none;position:relative;width:30px;height:16px;border-radius:8px;background:var(--bd);box-shadow:inset 0 1px 2px rgba(40,18,4,.3);transition:background .15s}
.sw::after{content:"";position:absolute;left:2px;top:2px;width:12px;height:12px;border-radius:50%;background:#fbf2dc;box-shadow:0 1px 1px rgba(40,18,4,.4);transition:left .15s}
.tgl.on .sw{background:var(--ing);box-shadow:inset 0 0 0 1px #1c3d15}
.tgl.on .sw::after{left:16px}
.lbl{display:block;font-size:12px;color:var(--mu);margin:4px 0 3px}
.seg{display:flex;border-radius:4px;background:rgba(255,246,220,.22);box-shadow:inset 0 0 0 1px var(--bd);overflow:hidden}
.seg button{flex:1;min-height:24px;padding:3px 2px;font-size:12px;line-height:13px;box-shadow:inset -1px 0 var(--bd)}
.seg button:last-child{box-shadow:none}
.seg button:not(.on):not(.lock):not(:disabled):hover{background:var(--tint2)}
.seg button.on{background:var(--ac);color:var(--acf)}
.seg button.lock{cursor:default;opacity:.4}
.btn{display:block;width:100%;height:28px;margin-top:6px;border-radius:4px;box-shadow:inset 0 0 0 1px var(--rule),0 1px 0 rgba(255,246,220,.36);background:rgba(255,246,220,.24)}
.btn:hover:not(:disabled){background:var(--tint2)}
.btn.ready{box-shadow:inset 0 0 0 1px var(--ac)}
.btn.quiet{color:#7a110b;box-shadow:none;background:none;text-align:left;padding:0}
.opt-note{font-size:11px;color:var(--mu);line-height:14px;margin:4px 0 0}
.opt{margin:0 0 10px}
.sk-grid{display:grid;grid-template-columns:repeat(3,minmax(0,58px));gap:4px;justify-content:center}
.sk{position:relative;display:flex;align-items:center;gap:4px;height:36px;padding:0 4px;border-radius:4px;background:var(--tint);box-shadow:inset 0 0 0 1px rgba(92,54,20,.24);box-sizing:border-box;font:bold 12px var(--font);cursor:pointer;overflow:hidden}
.sk:hover{background:var(--tint2)}
.sk .ico{width:16px;height:16px;flex:none}
.sk .bar{position:absolute;left:4px;right:4px;bottom:3px;height:2px;background:rgba(80,48,18,.2)}
.sk .bar i{display:block;height:100%}
.sk.total{cursor:default;font-size:11px;line-height:12px}
.sk.hp{gap:1px;padding:0 2px}
.sk.hp span{font-size:11px}
.sk.lo span{color:#6b2a00}
.sk.flash{animation:flash 2s}
.sk.pts::after{content:"";position:absolute;top:3px;right:3px;width:6px;height:6px;border-radius:50%;background:#f0b81e;box-shadow:0 0 0 1px #4a260c}
.qh{font-size:12px;color:var(--mu);margin:0 0 4px}
.qr{display:block;width:100%;height:22px;line-height:22px;padding:0 4px;border-radius:3px;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;box-sizing:border-box}
.qr:hover{background:var(--tint2)}
.qs-todo{color:#7a110b}.qs-active{color:#524000}.qs-done{color:#134415}

/* ------------------- Windows (stone/parchment) ------------------ */
#win{position:absolute;top:28px;left:4px;right:4px;bottom:var(--win-b,4px);max-width:calc(560px * var(--ui,1));margin:0 auto;z-index:4;display:flex;flex-direction:column;background:#2a231b;border:2px solid #6a5a44;box-shadow:inset 0 0 0 2px #15100b,0 6px 18px rgba(0,0,0,.5);color:#f0e6d0;animation:fadein .12s}
#win[data-kind=journal],#win[data-kind=guide],#win[data-kind=away],#win[data-kind=questdone],#win[data-kind=pet]{bottom:auto;max-height:calc(100% - 28px - var(--win-b,4px))}
#win[data-kind=pet]{max-width:calc(420px * var(--ui,1))}
.pd-top{display:flex;gap:10px;align-items:center;margin:2px 0 6px}
.pd-pic{flex:none;width:96px;height:80px;border-radius:6px;background:radial-gradient(circle at 50% 60%,#f4e8c4,#cdb98a);box-shadow:inset 0 0 0 1px #8a7450;image-rendering:pixelated}
.pd-id{flex:1;min-width:0}
.pd-id b{display:block;font-size:16px;line-height:20px}
.pd-id>span{display:block;color:#6a5434;font-size:12px}
.pd-forms{display:flex;flex-wrap:wrap;gap:3px;margin-top:4px}
.pd-forms i{font-style:normal;font-size:11px;line-height:16px;padding:0 5px;border-radius:8px;background:#d4c294;color:#6a5434}
.pd-forms i.on{background:#6a4a1a;color:#ffe8b0}
.pd-forms i.lock{opacity:.7}
.pd-xp{display:flex;align-items:center;gap:6px;font-size:12px;margin:2px 0 4px}
.pd-xp b{flex:none}
.pd-xp span{flex:none;color:#6a5434}
.pd-bar{flex:1;height:6px;border-radius:3px;background:#c9b886;box-shadow:inset 0 0 0 1px #a8946a;overflow:hidden}
.pd-bar i{display:block;height:100%;background:#3f7a2e}
#win .pd h4{margin:8px 0 3px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#7a3a1a;border-bottom:1px solid #b8a274;padding-bottom:1px}
.pd-dl{display:grid;grid-template-columns:auto 1fr;gap:1px 10px;margin:0;font-size:12px;line-height:17px}
.pd-dl dt{color:#6a5434}
.pd-dl dd{margin:0;font-weight:600}
.pd-note{margin:3px 0 0;font-size:12px;color:#4a3820;font-style:italic}
.pd-facts{margin:2px 0 0;padding-left:18px;font-size:12px;line-height:16px}
.pd-facts li{margin:2px 0}
.pd-facts li.lock{color:#8a7450;font-style:italic}
.pet[data-act=petinfo]{cursor:pointer}
.pet[data-act=petinfo]:hover{background:var(--tint2)}
#win ::-webkit-scrollbar{width:8px}
#win ::-webkit-scrollbar-thumb{background:#6a5a44;border-radius:4px}
.wh{flex:none;display:flex;align-items:center;gap:8px;height:32px;padding:0 4px 0 10px}
.wt{flex:1;min-width:0;font:bold 14px var(--font);color:#ff9a2a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ws{flex:none;color:#b0a080;font-size:12px;white-space:nowrap}
.wx{flex:none;display:flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:3px;color:#b0a080}
.wx:hover{background:#3b3227;color:#f0e6d0}
.wx svg{width:12px;height:12px;stroke:currentColor;stroke-width:2;fill:none}
.wb{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:2px 8px 8px}
.wf{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:6px 8px;box-shadow:inset 0 1px #4a3d2e}
.wf .sp{flex:1}
.wf .dep{display:flex;gap:4px;margin-left:auto}
.wf .lb{color:#b0a080;font-size:12px;margin-right:2px}
.gb{height:24px;min-width:28px;padding:0 8px;box-sizing:border-box;background:#3b3227;border:1px solid #6a5a44;border-radius:2px;color:#f0e6d0;font-size:12px;white-space:nowrap}
.gb:hover{background:#4a3f31}
.gb.on{background:#6a4a1a;color:#ffd27a}
.mt{color:#b0a080}
#win.parch{background:#e3d4aa;border-color:#5a4528;box-shadow:0 6px 18px rgba(0,0,0,.45);color:#23180c}
#win.parch .wt{font-size:16px;color:#23180c}
#win.parch .wx{color:#5a4528}
#win.parch .wx:hover{background:#c9b886;color:#23180c}
#win.parch ::-webkit-scrollbar-thumb{background:#a8946a}
.grid{display:grid;grid-template-columns:repeat(var(--bc,8),minmax(0,var(--bw,44px)));grid-auto-rows:var(--bh,36px);justify-content:start}
.cell{position:relative;display:flex;align-items:center;justify-content:center;border-radius:3px;cursor:pointer}
.cell:hover{background:rgba(255,230,180,.1)}
.shop{display:grid;grid-template-columns:repeat(auto-fill,52px);gap:3px;justify-content:center}
.sc{position:relative;display:flex;flex-direction:column;align-items:center;width:52px;height:52px;padding-top:4px;box-sizing:border-box;background:#221c15;border:1px solid #3b3227;border-radius:2px;cursor:pointer}
.sc:hover{border-color:#6a5a44;background:#2e261d}
.sc.out .ico{opacity:.4}
.sc .pr{position:absolute;left:0;right:0;bottom:1px;text-align:center;font:bold 11px/12px var(--font);color:#ffd24a;transition:color .1s}
.sc .pr.no{color:#ff3030}
.ln2{margin:4px 0;line-height:18px}
.strike{text-decoration:line-through;color:#6b5a3a}
.nm{color:#7d1f12;font-weight:600}
.rw{display:flex;align-items:center;gap:8px;min-height:34px}
.rw .ico{flex:none}
.sec{margin:10px 0 4px;font-weight:bold;color:#ff9a2a}
#win.parch .sec{color:#7d1f12}
.gr{display:flex;align-items:center;gap:8px;height:40px}
.gr .lv{flex:none;width:28px;text-align:right;font-weight:bold}
.gr .nt{display:block;font-size:11px;color:#b0a080}
.gr.lock{opacity:.45}
/* Guide perks: a parchment card on the stone window, in the side panel's inks; gold pips mark ranks. */
.perks{--ink:#26170a;--ink2:#4f371d;--inkr:#7a1d10;--rule:rgba(92,54,20,.32);margin:4px 0 2px;padding:0 10px 2px;border-radius:3px;background:var(--parch);box-shadow:0 0 0 1px #4a260c,0 2px 6px rgba(0,0,0,.35);color:var(--ink)}
.pkh{display:flex;align-items:center;gap:8px;height:32px;box-shadow:inset 0 -1px var(--rule)}
.pkh b{flex:none;font-size:13px;color:var(--inkr)}
.pkf{flex:1;min-width:0;font-size:12px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.perks.has .pkf{color:var(--ink);font-weight:bold}
.pk{display:flex;align-items:center;gap:8px;min-height:42px;padding:5px 0;box-sizing:border-box;box-shadow:inset 0 -1px var(--rule)}
.pk:last-child{box-shadow:none}
.pkt{flex:1;min-width:0}
.pkt b{display:block;font-size:12px;line-height:15px}
.pkt span{display:block;font-size:11px;line-height:14px;color:var(--ink2)}
.pips{flex:none;display:flex;gap:5px;padding:0 3px}
.pips i{width:8px;height:8px;transform:rotate(45deg);background:rgba(92,54,20,.16);box-shadow:inset 0 0 0 1px rgba(74,38,12,.6)}
.pips i.on{background:#e8ae1c;box-shadow:inset 0 0 0 1px #4a260c,0 0 3px rgba(232,174,28,.7)}
html .pkb,html .pkr{flex:none;border-radius:3px;background:linear-gradient(180deg,#e9d3a2,#cfb077);border:1px solid #6e4520;box-shadow:0 1px 2px rgba(20,10,2,.4),inset 0 1px rgba(255,248,228,.55);color:var(--ink);font-weight:bold}
html .pkb{width:24px;height:24px;font-size:16px;line-height:20px}
html .pkr{height:22px;padding:0 8px;font-size:11px;white-space:nowrap}
html .pkb:hover:not(:disabled),html .pkr:hover:not(:disabled){background:linear-gradient(180deg,#f1dfb6,#d9bd86)}
html .pkb:disabled,html .pkr:disabled{opacity:.35;box-shadow:none}
html .pkr.no{color:var(--inkr)}
.rw .pkn{color:#f3cf6a;font-size:12px}
.ig{display:flex;flex-wrap:wrap;gap:2px}
.ig .cell{width:40px;height:36px;cursor:default}
.ctr{text-align:center}

/* --------------------------- Sheets --------------------------- */
#sheet{position:absolute;left:0;right:0;bottom:0;z-index:3;max-height:calc(100% - 40px);overflow-y:auto;background:#e3d4aa;border-top:2px solid #5a4528;box-shadow:0 -3px 10px rgba(0,0,0,.35);color:#23180c}
#app[data-layout=C] #sheet{z-index:5}
/* T: the last row clears the scroll's roll, 11 px into the view bottom. */
#app[data-layout=T] #sheet{padding-bottom:8px}
#sheet ::-webkit-scrollbar,#sheet::-webkit-scrollbar{width:8px}
#sheet ::-webkit-scrollbar-thumb,#sheet::-webkit-scrollbar-thumb{background:#a8946a;border-radius:4px}
.dlg{display:flex;gap:10px;min-height:102px;max-height:158px;padding:10px 12px;box-sizing:border-box;overflow-y:auto;cursor:pointer}
.pf{flex:none;width:56px;height:56px;box-sizing:border-box;border:2px solid #5a4528;background:#c9b886;display:flex;align-items:center;justify-content:center;overflow:hidden}
.pf canvas{width:48px;height:48px;image-rendering:pixelated}
.dl{flex:1;min-width:0}
.dn{font:bold 13px/16px var(--font);color:#7d1f12;margin-bottom:2px}
.dt{font-size:13px;line-height:18px}
.dc{font-size:12px;color:#1f4fbf;margin-top:4px}
.dop{display:block;width:100%;height:22px;line-height:22px;padding:0 6px;box-sizing:border-box;border-radius:2px;text-align:left;color:#1f4fbf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dop:hover{background:#c9b886}
.mkt{height:22px;line-height:22px;margin-top:4px;text-align:center;font-weight:bold}
.mkg{display:grid;grid-template-columns:repeat(var(--mc,5),minmax(0,60px));grid-auto-rows:60px;justify-content:center;max-height:120px;overflow-y:auto}
.mk{position:relative;display:flex;flex-direction:column;align-items:center;padding-top:4px;box-sizing:border-box;border-radius:3px}
.mk:hover{background:#c9b886}
.mk span{display:block;max-height:24px;overflow:hidden;padding:0 2px;font-size:11px;line-height:12px;text-align:center}
.mk.lock .ico,.mk.lock span{opacity:.4}
.mk .lv{position:absolute;top:2px;right:2px;padding:0 3px;border-radius:2px;background:#5a4528;color:#e3d4aa;font:bold 10px/13px var(--font)}
.row{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:4px;padding:6px 8px 8px}
.amt{display:flex;align-items:center;justify-content:center;gap:8px;padding:12px}
#amt-in{width:110px;height:26px;padding:0 6px;box-sizing:border-box;border:1px solid #5a4528;border-radius:2px;background:#f3ead0;color:#23180c;font:13px var(--font);outline:none;user-select:text;-webkit-user-select:text}

/* ------------------------- Veil, menu ------------------------- */
/* ---------------------- Character creation -------------------- */
#create{position:absolute;top:0;right:0;bottom:0;left:0;z-index:7;display:flex;align-items:center;justify-content:center;padding:12px;background:rgba(20,12,4,.72)}
#cr-card{width:min(340px,100%);max-height:100%;overflow-y:auto;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;gap:8px;padding:14px 16px;border-radius:6px;background:var(--parch);color:#26170a;box-shadow:0 0 0 2px #4a260c,0 10px 30px rgba(0,0,0,.5)}
#cr-title{font-size:16px}
#cr-doll{display:block;image-rendering:pixelated;border-radius:4px;background:rgba(120,74,28,.12)}
#cr-name{width:100%;box-sizing:border-box;font:inherit;font-size:14px;padding:6px 8px;border:1px solid #7a4a1c;border-radius:4px;background:#fbf2dc;color:#26170a;-webkit-user-select:text;user-select:text;outline:none}
#cr-name:focus{border-color:#26170a;box-shadow:0 0 0 2px rgba(122,29,16,.25)}
#cr-rows{width:100%;display:grid;grid-template-columns:auto 28px 1fr 28px;gap:4px 6px;align-items:center}
#cr-rows span{font-size:12px;color:#4f371d}
#cr-rows b{display:flex;align-items:center;justify-content:center;gap:6px;font-size:12px}
#cr-rows b i{width:14px;height:14px;border-radius:3px;box-shadow:0 0 0 1px #26170a}
#cr-rows button{height:24px;border-radius:4px;background:rgba(120,74,28,.18);color:#26170a;font-size:15px;line-height:1}
#cr-rows button:hover,#cr-foot button:hover{background:rgba(120,74,28,.32)}
#cr-err{min-height:14px;font-size:11px;color:#7a1d10;text-align:center}
#cr-foot{width:100%;display:flex;gap:8px}
#cr-foot button{flex:1;height:30px;border-radius:4px;background:rgba(120,74,28,.18);color:#26170a}
#cr-foot #cr-go{background:#7a1d10;color:#f7ebcf;font-weight:bold}
#cr-foot #cr-go:disabled{opacity:.45}
#veil{position:absolute;top:0;right:0;bottom:0;left:0;z-index:8;display:flex;align-items:center;justify-content:center;background:var(--bg)}
#veil[data-kind=""]{display:none}
#veil[data-kind=catchup]{background:rgba(0,0,0,.62)}
#veil[data-kind=death]{background:rgba(0,0,0,.6);animation:fadein .6s;cursor:pointer}
#veil-box{display:flex;flex-direction:column;align-items:center;gap:8px;max-width:300px;padding:16px;text-align:center}
#veil-title{font-size:16px}
#veil-text{font-size:13px;color:var(--mu)}
#veil[data-kind=catchup] #veil-box{color:#f0e6d0}
#veil[data-kind=catchup] #veil-text,#veil[data-kind=death] #veil-text{color:#e8dcc4}
#veil[data-kind=death] #veil-title{font:bold 20px var(--font);color:#ff3030;text-shadow:1px 1px 0 #000}
#veil-bar{width:180px;height:4px;border-radius:2px;background:rgba(255,255,255,.15);overflow:hidden}
#veil-fill{display:block;height:100%;width:0;background:var(--ac)}
#veil:not([data-kind=catchup]) #veil-bar{display:none}
#menu{position:fixed;z-index:6;min-width:120px;box-sizing:border-box;background:#2a231b;border:1px solid #6a5a44;box-shadow:0 4px 14px rgba(0,0,0,.5);font:13px var(--font);color:#f0e6d0}
#menu .mh{height:20px;line-height:20px;padding:0 8px;background:#15100b;color:#b0a080;font-weight:bold}
#menu .mb{max-height:240px;overflow-y:auto}
#menu .mr{height:20px;line-height:20px;padding:0 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
#menu .mr:hover{background:#3b3227}
#tip{position:fixed;z-index:7;pointer-events:none;max-width:220px;padding:4px 8px;border-radius:4px;background:var(--bg);box-shadow:inset 0 0 0 1px var(--bd),0 2px 8px rgba(0,0,0,.3);color:var(--fg);font-size:12px;line-height:16px}
#tip.game{background:#2a231b;color:#f0e6d0;box-shadow:inset 0 0 0 1px #6a5a44,0 2px 8px rgba(0,0,0,.4)}
#modal{position:fixed;top:0;right:0;bottom:0;left:0;z-index:9;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.5)}
.md{width:min(300px,calc(100% - 32px));padding:16px;box-sizing:border-box;border-radius:8px;background:var(--bg);box-shadow:inset 0 0 0 1px var(--bd),0 8px 24px rgba(0,0,0,.4);color:var(--fg)}
.md b{display:block;font-size:14px;margin-bottom:6px}
.md p{margin:0;color:var(--mu)}
.mdb{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.mdb button{height:28px;padding:0 12px;border-radius:4px;box-shadow:inset 0 0 0 1px var(--bd)}
.mdb .danger{background:#c62828;color:#fff;box-shadow:none}
.mdb .ok{background:var(--ac);color:var(--acf);box-shadow:none}
body[data-motion=reduce] *{animation:none!important;transition:none!important}</style></head><body>
<div id="app" data-layout="T">
 <div id="status">
  <i id="st-dot"></i><span id="st-text">Loading…</span><span id="st-goal"></span>
  <span id="st-nosave" hidden data-tip="Progress is not being saved yet">Not saving</span>
  <span id="st-grave" hidden data-tip=""></span>
  <span id="st-rested" hidden data-tip=""></span>
  <span id="st-season" hidden data-tip=""><i class="ico"></i><b></b></span>
  <span id="st-pack" data-tip="Pack slots used"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 5V4a3 3 0 0 1 6 0v1h2l1 10H2L3 5h2zm1 0h4V4a2 2 0 0 0-4 0v1z" fill="currentColor"/></svg><b id="st-packn">0/28</b></span>
  <div id="st-bar"><i id="st-fill"></i></div>
 </div>
 <div id="view">
  <canvas id="game"></canvas>
  <div id="hover"></div>
  <div id="banner" hidden></div>
  <div id="ask" hidden></div>
  <div id="toast" hidden></div>
  <div id="sheet" data-kind="" hidden></div>
  <div id="win" data-kind="" hidden></div>
 </div>
 <div id="mm">
  <canvas id="minimap"></canvas>
  <button id="mm-map" data-act="map" data-tip="World map" aria-label="World map"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="#3a78b8" stroke="#1b140d"/><path d="M3.6 5.2c1.4-.6 2.6.2 3 1.3s-.9 1.9-1.8 2.4-.9 1.9 0 2.8l-1.3.4A6 6 0 0 1 3.6 5.2zM8.8 2.6c1.5 0 2.8.9 3.4 1.9-.9.5-1.4 1.4-.9 2.3s1.4 1 1.9 2.1c-.5 1.4-1.7 2.5-3 3-.3-1.2.2-2.2-.6-3.1S7.9 7.6 8.3 6.2s1.2-2 .5-3.6z" fill="#5aa040"/></svg></button>
  <div id="orb-hp" class="orb" role="img" aria-label="Vitality" data-tip="Vitality"><i></i><b>10</b></div>
  <div id="orb-run" class="orb" role="button" aria-label="Run" aria-pressed="true" data-act="run" data-tip="Run: click to toggle"><i></i><b>Run</b></div>
 </div>
 <div id="chat">
  <div id="chatlog"></div>
  <div id="chatempty" hidden><span id="chatempty-t"></span> <button data-filter="all">Show all</button></div>
  <button id="newmsgs" data-act="newmsgs" hidden>New messages</button>
  <div id="chatfilters"><button data-filter="all">All</button><button data-filter="game">Game</button><button data-filter="skill">Skill</button><button data-filter="loot">Loot</button><button data-filter="fight">Fight</button></div>
 </div>
 <div id="side">
  <div id="tabs"><button data-tab="combat"></button><button data-tab="skills"></button><button data-tab="quests"></button><button data-tab="inventory"></button><button data-tab="equipment"></button><button data-tab="options"></button></div>
  <div id="pane">
   <section data-pane="combat"></section>
   <section data-pane="skills"></section>
   <section data-pane="quests"></section>
   <section data-pane="inventory"><div id="inv"></div></section>
   <section data-pane="equipment"><div id="equip"></div><div id="eqstats"></div></section>
   <section data-pane="options"></section>
  </div>
 </div>
 <div id="create" hidden role="dialog" aria-label="Create your character"><div id="cr-card"><b id="cr-title">Create your character</b><canvas id="cr-doll"></canvas><input id="cr-name" maxlength="12" placeholder="Your name" autocomplete="off" spellcheck="false" aria-label="Character name"><div id="cr-rows"></div><span id="cr-err"></span><div id="cr-foot"><button data-act="crRandom">Random</button><button data-act="crGo" id="cr-go">Begin adventure</button></div></div></div>
 <div id="veil" data-kind="loading"><div id="veil-box"><b id="veil-title">Orcadia</b><span id="veil-text">Loading…</span><div id="veil-bar"><i id="veil-fill"></i></div></div></div>
</div>
<div id="menu" hidden></div><div id="tip" hidden></div><div id="modal" hidden></div>
<script>
(function () {
"use strict";
/*ENGINE-START*/
// ==== src/engine/util.js ====
// ----------------------------------------------------------------
// ---------------------- Util: pure helpers ----------------------
// ----------------------------------------------------------------
// Own-property lookups, the seeded RNG (mulberry32 on state.rng), refs, events and number formats.
// No module state: everything works on its arguments.
const Util = (function () {
  "use strict";

  var EVENTS_MAX = 500;
  var DIRS = [7, 0, 1, 6, 4, 2, 5, 4, 3];   // indexed by (sign(dy)+1)*3 + sign(dx)+1
  var TILE_RE = /^(\d{1,4}),(\d{1,4})$/;
  var NUM_RE = /^\d{1,9}$/;
  var SLOT_RE = /^[a-z]{1,16}$/;

  // ----------------------------------------------------------------
  // ------------------------ Basic checks --------------------------
  // ----------------------------------------------------------------

  function has(o, k) {
    return o !== null && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
  }

  function clamp(v, lo, hi) {
    return v < lo ? lo : v > hi ? hi : v;
  }

  // A finite number floored and clamped to lo..hi; anything else gives dflt. "+ 0" drops -0.
  function int(v, lo, hi, dflt) {
    if (typeof v !== "number" || !isFinite(v)) return dflt;
    return clamp(Math.floor(v), lo, hi) + 0;
  }

  // ----------------------------------------------------------------
  // ----------------------- Seeded randomness ----------------------
  // ----------------------------------------------------------------

  // mulberry32: state.rng is the uint32 seed, advanced once per call. Returns [0,1).
  function rand(state) {
    var a = ((state.rng >>> 0) + 0x6d2b79f5) >>> 0;
    state.rng = a;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  // 0..n-1; n < 1 gives 0 without consuming the RNG.
  function randInt(state, n) {
    if (!(n >= 1)) return 0;
    return Math.floor(rand(state) * Math.floor(n));
  }

  // Picks a row by its weight in column wi; null when the roll lands past the listed weights.
  function weighted(state, rows, total, wi) {
    if (!rows || !rows.length || !(total > 0)) return null;
    var r = rand(state) * total;
    var acc = 0;
    for (var i = 0; i < rows.length; i++) {
      acc += rows[i][wi];
      if (r < acc) return rows[i];
    }
    return null;
  }

  // ----------------------------------------------------------------
  // ------------------------ Tiles and refs ------------------------
  // ----------------------------------------------------------------

  function dist(ax, ay, bx, by) {
    return Math.max(Math.abs(ax - bx), Math.abs(ay - by));
  }

  function inRect(r, x, y) {
    return x >= r[0] && y >= r[1] && x <= r[2] && y <= r[3];
  }

  function key(map, x, y) { return map + ":" + x + "," + y; }
  function refTile(x, y) { return "tile:" + x + "," + y; }
  function refObj(x, y) { return "obj:" + x + "," + y; }
  function refNpc(uid) { return "npc:" + uid; }
  function refGround(gid) { return "ground:" + gid; }
  function refGrave() { return "grave:0"; }
  function refInv(slot) { return "inv:" + slot; }
  function refEquip(slot) { return "equip:" + slot; }
  function refBank(i) { return "bank:" + i; }
  function refShop(i) { return "shop:" + i; }

  // "tile:3,4" -> {t:"tile", x:3, y:4}; "npc:7" -> {t:"npc", n:7}; "equip:head" -> {t:"equip", s:"head"}.
  // Anything malformed gives null; never throws.
  function parseRef(s) {
    if (typeof s !== "string" || s.length > 40) return null;
    var c = s.indexOf(":");
    if (c < 1) return null;
    var t = s.slice(0, c);
    var rest = s.slice(c + 1);
    var m;
    switch (t) {
      case "tile":
      case "obj":
        m = TILE_RE.exec(rest);
        return m ? { t: t, x: +m[1], y: +m[2] } : null;
      case "npc":
      case "ground":
      case "inv":
      case "bank":
      case "shop":
        return NUM_RE.test(rest) ? { t: t, n: +rest } : null;
      case "grave":
        return rest === "0" ? { t: t, n: 0 } : null;
      case "equip":
        return SLOT_RE.test(rest) ? { t: t, s: rest } : null;
      default:
        return null;
    }
  }

  // ----------------------------------------------------------------
  // --------------------------- Events -----------------------------
  // ----------------------------------------------------------------

  function emit(state, ev) {
    if (!Array.isArray(state.events)) state.events = [];
    var evs = state.events;
    evs.push(ev);
    if (evs.length > EVENTS_MAX) evs.splice(0, evs.length - EVENTS_MAX);
  }

  function msg(state, text, c) {
    emit(state, { type: "msg", text: text, c: c || "game" });
  }

  // 0=N 1=NE 2=E 3=SE 4=S 5=SW 6=W 7=NW; (0,0) faces south.
  function dirIndex(dx, dy) {
    var sx = dx > 0 ? 1 : dx < 0 ? -1 : 0;
    var sy = dy > 0 ? 1 : dy < 0 ? -1 : 0;
    return DIRS[(sy + 1) * 3 + sx + 1];
  }

  // ----------------------------------------------------------------
  // --------------------------- Formats ----------------------------
  // ----------------------------------------------------------------

  // 1234567 -> "1,234,567" (truncates fractions; junk -> "0").
  function fmtInt(n) {
    var v = Math.trunc(Number(n)) || 0;
    var s = String(Math.abs(v));
    var out = "";
    while (s.length > 3) {
      out = "," + s.slice(s.length - 3) + out;
      s = s.slice(0, s.length - 3);
    }
    return (v < 0 ? "-" : "") + s + out;
  }

  // Stack labels: below 100,000 as is, then K, then M.
  function fmtQty(n) {
    if (n < 100000) return String(n);
    if (n < 10000000) return Math.floor(n / 1000) + "K";
    return Math.floor(n / 1000000) + "M";
  }

  // Amount-prompt text -> a count in 1..max, or null: "12", "5k", "2m", with up to 3 decimals before a k/m
  // suffix ("1.5k" = 1,500; "2.25m" = 2,250,000; integer maths, so "1.001k" = 1,001). "1.5" alone is null.
  function parseQty(t, max) {
    var m = /^\s*(\d{1,10})(?:\.(\d{1,3}))?\s*([kKmM]?)\s*$/.exec(String(t));
    if (!m || (m[2] && !m[3])) return null;
    var d = !m[3] ? 0 : m[3] === "k" || m[3] === "K" ? 3 : 6;
    var n = Number(m[1]) * Math.pow(10, d) + (m[2] ? Number((m[2] + "000000").slice(0, d)) : 0);
    if (!(n >= 1)) return null;
    return typeof max === "number" ? Math.min(n, max) : n;
  }

  function qtyClass(n) {
    return n < 100000 ? "y" : n < 10000000 ? "w" : "g";
  }

  // Ticks as play time: "2h 14m" from an hour up, else "m:ss".
  function fmtDur(ticks) {
    var s = Math.max(0, Math.floor((Number(ticks) || 0) * 3 / 5));
    if (s >= 3600) return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
    var sec = s % 60;
    return Math.floor(s / 60) + ":" + (sec < 10 ? "0" : "") + sec;
  }

  return {
    has: has, clamp: clamp, int: int, rand: rand, randInt: randInt, weighted: weighted, dist: dist,
    inRect: inRect, key: key, refTile: refTile, refObj: refObj, refNpc: refNpc, refGround: refGround,
    refGrave: refGrave, refInv: refInv, refEquip: refEquip, refBank: refBank, refShop: refShop,
    parseRef: parseRef, emit: emit, msg: msg, dirIndex: dirIndex, fmtInt: fmtInt, fmtQty: fmtQty,
    parseQty: parseQty, qtyClass: qtyClass, fmtDur: fmtDur
  };
})();
// ==== src/engine/layout.js ====
// ----------------------------------------------------------------
// ------------------ Layout: panel layout picker -----------------
// ----------------------------------------------------------------
// Picks the panel layout (T tall, C compact) and the chrome sizes of DESIGN.md 19.1. T at every width;
// C only when the panel is too small for T. Pure numbers: the UI applies the result to the DOM and hands
// it to Render.resize. scale is the Interface size pref (0.75, 1, 1.25, 1.5): the side column's contents are
// drawn at that zoom, so the column and the band under the view grow with it while slot sizes stay in the
// column's own (unzoomed) px. The tab row is not zoomed: its height and glyph size are given here.
const Layout = (function () {
  "use strict";

  var LAYOUTS = ["C", "T"];
  var STEPS = [-12, 0, 12];
  var STATUS_H = 26;
  var TABS_H = 36;
  var PANE_PAD = 12;         // #pane > section padding, top + bottom
  var T_MIN_W = 340;         // narrower than this: C
  var T_MIN_VIEW = 240;      // a T view shorter than this: C
  var T_KEEP_VIEW = 360;     // the T band under the view gives up slot height (down to SLOT_MIN_H) to keep this
  var SLOT_MIN_H = 34;       // a 32 px icon plus 1 px each side
  var CHAT_MIN = 140;        // T keeps at least this much chat beside the side column
  var SCALES = [0.75, 1, 1.25, 1.5];
  var TAB_ICONS = [16, 24, 32, 40];   // tab glyph css px per scale: whole multiples of 8, crisp at dpr 2

  function clamp(v, lo, hi) {
    return v < lo ? lo : v > hi ? hi : v;
  }

  function dim(v) {
    var n = Math.floor(Number(v));
    return isFinite(n) && n > 0 ? n : 0;
  }

  // One of SCALES; anything else is 1.
  function scaleOf(v) {
    return SCALES.indexOf(v) >= 0 ? v : 1;
  }

  // ----------------------------------------------------------------
  // ------------------------ Chrome sizes --------------------------
  // ----------------------------------------------------------------

  function result(vw, vh, side, bottom, sw, sh, mm, tooSmall, s) {
    return { view: { w: Math.max(0, vw), h: Math.max(0, vh) }, side: side, bottom: bottom, slot: { w: sw, h: sh },
      mmDiam: mm, mmPx: 2, chatFont: 12, chatLine: 15, tooSmall: tooSmall, scale: s,
      tabs: Math.round(TABS_H * s), tabIco: TAB_ICONS[SCALES.indexOf(s)] };
  }

  // T: view on top, chat + side column below (two widths around 440; a wider panel gives the chat the room).
  // The band under the view fits the 4x7 inventory exactly; on a short panel its slots shrink so the view
  // keeps T_KEEP_VIEW px. At scale s the tab row and the slots are s times larger.
  function tall(w, h, s) {
    var narrow = w < 440;
    var tabs = Math.round(TABS_H * s);
    var sh = clamp(Math.floor((h - STATUS_H - tabs - PANE_PAD - T_KEEP_VIEW) / (7 * s)), SLOT_MIN_H, narrow ? 36 : 38);
    var bottom = tabs + PANE_PAD + Math.ceil(7 * sh * s);
    return result(w, h - STATUS_H - bottom, Math.round((narrow ? 196 : 212) * s), bottom, narrow ? 44 : 48, sh,
      narrow ? 84 : 100, false, s);
  }

  // C: the view fills the panel; tabs get their own row and the pane opens as a sheet over the view.
  function compact(w, h, s) {
    var tabs = Math.round(TABS_H * s);
    return result(w, h - STATUS_H - tabs, w, tabs, 44, 36, 72, w < 300 || h < 380, s);
  }

  // ----------------------------------------------------------------
  // ----------------------- Pick the layout ------------------------
  // ----------------------------------------------------------------

  // T whenever it fits (a wider panel never switches away from it); C below the T minimum, or when a large
  // interface would leave the chat narrower than CHAT_MIN.
  function raw(w, h, s) {
    var t = tall(w, h, s);
    return w < T_MIN_W || t.view.h < T_MIN_VIEW || w - t.side < CHAT_MIN ? "C" : "T";
  }

  // Hysteresis at the T/C edge: keep prev while a 12 px nudge in any direction would still give it.
  function layoutFor(w, h, prev, scale) {
    var W = dim(w);
    var H = dim(h);
    var s = scaleOf(scale);
    var r = raw(W, H, s);
    if (LAYOUTS.indexOf(prev) < 0 || prev === r) return r;
    for (var i = 0; i < STEPS.length; i++) {
      for (var j = 0; j < STEPS.length; j++) {
        if (raw(W + STEPS[i], H + STEPS[j], s) === prev) return prev;
      }
    }
    return r;
  }

  function sizes(L, w, h, scale) {
    var W = dim(w);
    var H = dim(h);
    var s = scaleOf(scale);
    var lay = LAYOUTS.indexOf(L) >= 0 ? L : raw(W, H, s);
    return lay === "C" ? compact(W, H, s) : tall(W, H, s);
  }

  return {
    layoutFor: layoutFor, sizes: sizes, SCALES: SCALES
  };
})();
// ==== src/engine/data/_init.js ====
// ----------------------------------------------------------------
// --------------------- Data: root and vocab ---------------------
// ----------------------------------------------------------------
// The single Data object (DESIGN.md section 7). Every later data file assigns one owned key.
// vocab lists the draw kinds, icon shapes, minimap glyphs and tool phrases the engine and
// renderer understand; content may only use names from these lists.
const Data = {
  vocab: {
    terrain: ["grass", "grass_dark", "dirt", "path", "sand", "water", "deep_water", "wood_floor", "stone_floor", "ash",
      "swamp", "bog", "wall", "fence", "bridge", "cave_floor", "cave_wall", "lava", "void"],
    obj: ["tree", "oak", "willow", "maple", "yew", "ironbark", "stump", "rock", "rock_empty", "fish_spot", "bank_booth",
      "furnace", "anvil", "range", "fire", "ladder_up", "ladder_down", "gate", "door", "shrine", "banner", "beacon",
      "gravestone", "counter", "table", "crate", "barrel", "well", "sign", "bush", "flowers", "wheat", "statue", "torch",
      "rubble", "tent", "boat", "stalagmite", "amber"],
    npc: ["human", "guard", "robed", "smith", "goblin", "cow", "chicken", "crab", "spider", "skeleton", "wolf", "ogre",
      "lurker", "imp", "golem", "wyrm"],
    item: ["coins", "feather", "tinderbox", "hammer", "chisel", "needle", "net", "rod", "harpoon", "cage", "mould",
      "satchel", "seal", "tusk", "heart", "logs", "ore", "bar", "gem_uncut", "gem", "axe", "pickaxe", "sword", "dagger",
      "mace", "greatsword", "cleaver", "helm", "shield", "greaves", "breastplate", "cape", "ring", "amulet", "gloves",
      "boots", "jerkin", "leggings", "vambraces", "hide", "leather", "shrimp", "fish", "fish_long", "swordfish", "lobster", "shark", "steak", "meat", "burnt", "misc"],
    mapIcon: ["bank", "shop", "general", "quest", "anvil", "furnace", "range", "fish", "mine", "woodcut", "ladder",
      "shrine", "tanner"],
    tools: { axe: "an axe", pickaxe: "a pickaxe", net: "a small fishing net", rod: "a fishing rod",
      harpoon: "a harpoon", cage: "a lobster cage", hammer: "a hammer", chisel: "a chisel", needle: "a needle",
      tinderbox: "a tinderbox", mould: "a jewellery mould" }
  },
  maps: {}
};
// ==== src/engine/data/skills.js ====
// ----------------------------------------------------------------
// ------------------------ Data: skills --------------------------
// ----------------------------------------------------------------
// Display order (DESIGN.md section 11.1). The four combat ids are reserved by the engine; the
// "hitpoints" id stays for saves, while players see the name Vitality.
Data.skills = [
  { id: "attack", name: "Attack", kind: "combat", color: "#c03030" },
  { id: "strength", name: "Strength", kind: "combat", color: "#2f8a3a" },
  { id: "defence", name: "Defence", kind: "combat", color: "#4a6ad0" },
  { id: "hitpoints", name: "Vitality", kind: "combat", color: "#e04848" },
  { id: "woodcutting", name: "Woodcutting", kind: "gather", color: "#7a5530" },
  { id: "mining", name: "Mining", kind: "gather", color: "#6a7078" },
  { id: "fishing", name: "Fishing", kind: "gather", color: "#4a8ad0" },
  { id: "smithing", name: "Smithing", kind: "artisan", color: "#9a9a9a" },
  { id: "cooking", name: "Cooking", kind: "artisan", color: "#9a4ab0" },
  { id: "firemaking", name: "Firemaking", kind: "artisan", color: "#e08020" },
  { id: "crafting", name: "Crafting", kind: "artisan", color: "#b07a3a" }
];

// ----------------------------------------------------------------
// ------------------------ Data: seasons -------------------------
// ----------------------------------------------------------------
// One season per Rules.SEASON_TICKS (an hour of play), in this order from tick 0 (DESIGN.md 10.12).
// mod.gather multiplies that skill's gather chance; mod.xp multiplies the XP of its actions.
Data.seasons = [
  { id: "spring", name: "Spring", effect: "Fish bite more often.", mod: { skill: "fishing", gather: 1.15 } },
  { id: "summer", name: "Summer", effect: "Ore comes loose more easily.", mod: { skill: "mining", gather: 1.1 } },
  { id: "autumn", name: "Autumn", effect: "Trees give wood more readily.", mod: { skill: "woodcutting", gather: 1.15 } },
  { id: "winter", name: "Winter", effect: "Fires burn warmer: more Firemaking XP.", mod: { skill: "firemaking", xp: 1.25 } }
];

// ----------------------------------------------------------------
// ------------------------- Data: perks --------------------------
// ----------------------------------------------------------------
// Three perks per skill, five ranks each, bought with the point a skill earns every 5 levels
// (DESIGN.md 10.13). fx names the engine hook and per is one rank's effect: a chance, a fraction, or
// flat bonus points (strb, defb). groups limits a making perk to those recipe groups; coins is the
// nest's purse; msg is the chat line when a chance perk fires.
Data.perks = {
  attack: [
    { id: "at_precision", name: "Precision", desc: "+3% accuracy per rank.", max: 5, fx: "acc", per: 0.03 },
    { id: "at_spoils", name: "Spoils", desc: "2% chance per rank that a monster drops its common loot twice. Bosses never do.",
      max: 5, fx: "spoils", per: 0.02, msg: "Spoils! The loot comes twice." },
    { id: "at_keen", name: "Keen eye", desc: "+3% Attack XP per rank.", max: 5, fx: "xp", per: 0.03 }
  ],
  strength: [
    { id: "st_brute", name: "Brute", desc: "+2 strength bonus per rank.", max: 5, fx: "strb", per: 2 },
    { id: "st_momentum", name: "Momentum", desc: "+3% Strength XP per rank.", max: 5, fx: "xp", per: 0.03 },
    { id: "st_finisher", name: "Finisher", desc: "+4% damage per rank to foes under 25% health (at least +1 from rank 3).",
      max: 5, fx: "finish", per: 0.04 }
  ],
  defence: [
    { id: "df_guard", name: "Guard", desc: "2% chance per rank to block a hit completely.", max: 5, fx: "block", per: 0.02,
      msg: "You block the blow." },
    { id: "df_bulwark", name: "Bulwark", desc: "+2 defence bonus per rank.", max: 5, fx: "defb", per: 2 },
    { id: "df_steadfast", name: "Steadfast", desc: "+3% Defence XP per rank.", max: 5, fx: "xp", per: 0.03 }
  ],
  hitpoints: [
    { id: "hp_wind", name: "Second wind", desc: "You regain health 10% faster per rank.", max: 5, fx: "regen", per: 0.1 },
    { id: "hp_irongut", name: "Iron gut", desc: "Food heals 4% more per rank.", max: 5, fx: "heal", per: 0.04 },
    { id: "hp_last", name: "Last stand", desc: "+5% defence per rank while you are under 25% health.", max: 5,
      fx: "last", per: 0.05 }
  ],
  woodcutting: [
    { id: "wc_lucky", name: "Lucky day", desc: "2% chance per rank to get double logs.", max: 5, fx: "double", per: 0.02,
      msg: "Lucky day! A second log comes free." },
    { id: "wc_swing", name: "Quick swing", desc: "+3% chance per rank to cut logs with each swing.", max: 5, fx: "gather",
      per: 0.03 },
    { id: "wc_nest", name: "Bird's nest", desc: "0.5% chance per rank per log to find a nest holding 5 to 25 coins.",
      max: 5, fx: "nest", per: 0.005, coins: [5, 25] }
  ],
  mining: [
    { id: "mn_lucky", name: "Lucky day", desc: "2% chance per rank to get double ore.", max: 5, fx: "double", per: 0.02,
      msg: "Lucky day! A second chunk breaks loose." },
    { id: "mn_gem", name: "Gem eye", desc: "+10% chance per rank to find a gem while mining.", max: 5, fx: "gem", per: 0.1 },
    { id: "mn_prospect", name: "Prospector", desc: "Rocks you empty refill 6% faster per rank.", max: 5, fx: "respawn",
      per: 0.06 }
  ],
  fishing: [
    { id: "fi_lucky", name: "Lucky day", desc: "2% chance per rank to get a double catch.", max: 5, fx: "double", per: 0.02,
      msg: "Lucky day! Two fish on one line." },
    { id: "fi_bait", name: "Bait saver", desc: "5% chance per rank to keep your feather when a fish bites.", max: 5,
      fx: "bait", per: 0.05 },
    { id: "fi_big", name: "Big one", desc: "+4% chance per rank that the better fish bites at spots with two catches.",
      max: 5, fx: "better", per: 0.04 }
  ],
  smithing: [
    { id: "sm_thrifty", name: "Thrifty", desc: "3% chance per rank to save a bar when you forge.", max: 5, fx: "save",
      per: 0.03, groups: ["smith"], msg: "Thrifty! You save a bar." },
    { id: "sm_swift", name: "Swift hammer", desc: "+3% Smithing XP per rank.", max: 5, fx: "xp", per: 0.03 },
    { id: "sm_master", name: "Master's touch", desc: "3% chance per rank that a smelt or forge gives double XP.", max: 5,
      fx: "xp2x", per: 0.03, groups: ["smelt", "smith"], msg: "Master's touch! Double XP." }
  ],
  cooking: [
    { id: "ck_steady", name: "Steady hand", desc: "6% less chance per rank to burn food.", max: 5, fx: "burn", per: 0.06,
      groups: ["cook"] },
    { id: "ck_hearty", name: "Hearty", desc: "Food heals 4% more per rank.", max: 5, fx: "heal", per: 0.04 },
    { id: "ck_double", name: "Double batch", desc: "2% chance per rank to cook two from one raw.", max: 5, fx: "twice",
      per: 0.02, groups: ["cook"], msg: "Double batch! An extra portion." }
  ],
  firemaking: [
    { id: "fm_kindling", name: "Kindling", desc: "4% chance per rank to keep the log when you light or burn it.", max: 5,
      fx: "save", per: 0.04, groups: ["light", "burn"], msg: "Kindling! You keep the log." },
    { id: "fm_long", name: "Long burn", desc: "Your fires burn 10% longer per rank.", max: 5, fx: "fire", per: 0.1 },
    { id: "fm_spark", name: "Ember spark", desc: "+3% Firemaking XP per rank.", max: 5, fx: "xp", per: 0.03 }
  ],
  crafting: [
    { id: "cr_thrifty", name: "Thrifty", desc: "3% chance per rank to save the main material.", max: 5, fx: "save",
      per: 0.03, groups: ["leather", "gold", "cut"], msg: "Thrifty! You save your material." },
    { id: "cr_clean", name: "Clean cut", desc: "+3% Crafting XP per rank.", max: 5, fx: "xp", per: 0.03 },
    { id: "cr_quick", name: "Quick stitch", desc: "2% chance per rank to make two at once.", max: 5, fx: "twice", per: 0.02,
      groups: ["leather", "gold", "cut"], msg: "Quick stitch! You make two." }
  ]
};
// ==== src/engine/data/items.js ====
// ----------------------------------------------------------------
// ------------------------- Data: items --------------------------
// ----------------------------------------------------------------
// All 148 item ids (DESIGN.md section 12). icon = [shape, c1, c2?, c3?]; metal gear uses the tier
// base colour as c1 so the renderer can pick the tier's shade and highlight. equip.twoHanded weapons
// leave no room for a shield (Player.equip moves one to the pack).
Data.items = {
  // ----------------------------------------------------------------
  // -------------- Currency, tools, quest and special --------------
  // ----------------------------------------------------------------
  coins: { name: "Coins", examine: "Orcadian crowns, slightly bent.", value: 1, cat: "currency", stack: true,
    icon: ["coins", "#e8c040", "#a07a18", "#f8e070"] },
  feather: { name: "Feather", examine: "Light as a whisper.", value: 2, cat: "misc", stack: true,
    icon: ["feather", "#f0ece0", "#c9c9c4"] },
  tinderbox: { name: "Tinderbox", examine: "Flint, steel and patience.", value: 4, cat: "tool",
    icon: ["tinderbox", "#a3abb0", "#7a5532"], tool: { cat: "tinderbox" } },
  hammer: { name: "Hammer", examine: "For hot metal, not thumbs.", value: 8, cat: "tool",
    icon: ["hammer", "#6d6a66", "#7a5532"], tool: { cat: "hammer" } },
  chisel: { name: "Chisel", examine: "Small, sharp, precise.", value: 6, cat: "tool",
    icon: ["chisel", "#a3abb0", "#7a5532"], tool: { cat: "chisel" } },
  needle: { name: "Needle", examine: "Mind your fingers.", value: 4, cat: "tool",
    icon: ["needle", "#c9c9c4", "#8a5a30"], tool: { cat: "needle" } },
  small_net: { name: "Small fishing net", examine: "For scooping small fry.", value: 10, cat: "tool",
    icon: ["net", "#d8d0b8", "#7a5532"], tool: { cat: "net" } },
  fishing_rod: { name: "Fishing rod", examine: "Bendy, with a hopeful hook.", value: 15, cat: "tool",
    icon: ["rod", "#7a5532", "#d8d0b8"], tool: { cat: "rod" } },
  harpoon: { name: "Harpoon", examine: "Barbed for the big ones.", value: 60, cat: "tool",
    icon: ["harpoon", "#6d6a66", "#7a5532"], tool: { cat: "harpoon" } },
  lobster_cage: { name: "Lobster cage", examine: "Lobsters walk in. Few walk out.", value: 40, cat: "tool",
    icon: ["cage", "#7a5532", "#c9c9c4"], tool: { cat: "cage" } },
  jewellery_mould: { name: "Jewellery mould", examine: "Shapes rings and amulets.", value: 25, cat: "tool",
    icon: ["mould", "#7e7b73", "#e8c040"], tool: { cat: "mould" } },
  courier_satchel: { name: "Courier's satchel", examine: "Bram's runners will find you.", value: 0, cat: "quest",
    untradeable: true, icon: ["satchel", "#8a5a30", "#e8c040"] },
  courier_seal: { name: "Courier seal", examine: "Brass, river-polished.", value: 0, cat: "quest",
    untradeable: true, icon: ["seal", "#b0743a", "#dca06a"] },
  skarg_tusk: { name: "Skarg's tusk", examine: "Yellow, chipped, and still angry.", value: 0, cat: "quest",
    untradeable: true, icon: ["tusk", "#f0ece0", "#a9925e"] },
  ember_heart: { name: "Ember heart", examine: "It beats. Slowly.", value: 0, cat: "quest",
    untradeable: true, icon: ["heart", "#b8433a", "#ffb050"] },
  emberward: { name: "Emberward", examine: "Steel rim, sapphire boss, cool to the touch.", value: 0, cat: "armour",
    untradeable: true, icon: ["shield", "#a3abb0", "#3a5fd0"],
    equip: { slot: "shield", att: 0, str: 0, def: 22, req: { defence: 20 } } },
  heros_mantle: { name: "Hero's mantle", examine: "Orcadia remembers.", value: 0, cat: "armour", untradeable: true,
    icon: ["cape", "#7d1f12", "#ffd24a"],
    equip: { slot: "cape", att: 4, str: 4, def: 4, if: [{ allQuests: true }],
      ifMsg: "Only one who has finished every quest may wear this." } },
  mastery_cape: { name: "Mastery cape", examine: "Earned, not bought.", value: 0, cat: "armour", untradeable: true,
    icon: ["cape", "#2a6662", "#ffd24a"],
    equip: { slot: "cape", att: 6, str: 6, def: 6, if: [{ anyLvl: 99 }], ifMsg: "You need a skill at level 99." } },
  cinderfang: { name: "Cinderfang", examine: "The blade is still smouldering.", value: 50000, cat: "weapon",
    icon: ["sword", "#ff9a3a", "#2a2522"],
    equip: { slot: "weapon", att: 48, str: 46, def: 0, speed: 4, req: { attack: 50 } } },
  smoulderfang: { name: "Smoulderfang", examine: "Too hot to sheathe, too heavy to hurry.", value: 60000, cat: "weapon",
    icon: ["greatsword", "#ffb050", "#7e2a24"],
    equip: { slot: "weapon", att: 50, str: 160, def: 0, speed: 7, twoHanded: true, req: { attack: 50 } } },
  skarg_cleaver: { name: "Skarg's cleaver", examine: "Notched, greasy, and heavier than it looks.", value: 450,
    cat: "weapon", icon: ["cleaver", "#8f8a80", "#4b7a2a"],
    equip: { slot: "weapon", att: 16, str: 22, def: 0, speed: 4, req: { attack: 15 } } },
  burnt_food: { name: "Burnt food", examine: "Charred beyond saving.", value: 1, cat: "junk",
    icon: ["burnt", "#2b2118", "#4a3a2a"] },

  // ----------------------------------------------------------------
  // ----------------------- Logs, ores, bars -----------------------
  // ----------------------------------------------------------------
  logs: { name: "Logs", examine: "Ordinary firewood.", value: 5, cat: "log", icon: ["logs", "#5a3b22", "#c8a070"],
    iops: [{ id: "light", label: "Light", rids: ["light_logs"] }] },
  oak_logs: { name: "Oak logs", examine: "Dense and slow-burning.", value: 15, cat: "log",
    icon: ["logs", "#6c512d", "#d8b880"], iops: [{ id: "light", label: "Light", rids: ["light_oak_logs"] }] },
  willow_logs: { name: "Willow logs", examine: "Pale and springy.", value: 25, cat: "log",
    icon: ["logs", "#5f7a2e", "#e0d8a0"], iops: [{ id: "light", label: "Light", rids: ["light_willow_logs"] }] },
  maple_logs: { name: "Maple logs", examine: "Smells faintly sweet.", value: 50, cat: "log",
    icon: ["logs", "#8a3a1e", "#e0b080"], iops: [{ id: "light", label: "Light", rids: ["light_maple_logs"] }] },
  yew_logs: { name: "Yew logs", examine: "Dark, tight-grained wood.", value: 80, cat: "log",
    icon: ["logs", "#3f2915", "#c89060"], iops: [{ id: "light", label: "Light", rids: ["light_yew_logs"] }] },
  ironbark_logs: { name: "Ironbark logs", examine: "Heavy as metal.", value: 200, cat: "log",
    icon: ["logs", "#2a6662", "#79cfc6"], iops: [{ id: "light", label: "Light", rids: ["light_ironbark_logs"] }] },
  copper_ore: { name: "Copper ore", examine: "A reddish lump.", value: 5, cat: "ore", icon: ["ore", "#c8763a", "#5b5852"] },
  tin_ore: { name: "Tin ore", examine: "Dull and soft.", value: 5, cat: "ore", icon: ["ore", "#c9c9c4", "#5b5852"] },
  iron_ore: { name: "Iron ore", examine: "Rust-flecked.", value: 20, cat: "ore", icon: ["ore", "#8a4e3a", "#5b5852"] },
  coal: { name: "Coal", examine: "Fuel for the furnace.", value: 35, cat: "ore", icon: ["ore", "#262626", "#4a4a4a"] },
  gold_ore: { name: "Gold ore", examine: "Glints even in the dark.", value: 80, cat: "ore",
    icon: ["ore", "#e8c040", "#5b5852"] },
  cobalt_ore: { name: "Cobalt ore", examine: "Deep blue, cold to the touch.", value: 120, cat: "ore",
    icon: ["ore", "#8aa6f0", "#5b5852"] },
  verdite_ore: { name: "Verdite ore", examine: "Green-veined and stubborn.", value: 220, cat: "ore",
    icon: ["ore", "#78c99c", "#5b5852"] },
  emberite_ore: { name: "Emberite ore", examine: "Warm. Always warm.", value: 400, cat: "ore",
    icon: ["ore", "#e5806f", "#5b5852"] },
  bronze_bar: { name: "Bronze bar", examine: "A bar of bronze.", value: 14, cat: "bar", icon: ["bar", "#b0743a"] },
  iron_bar: { name: "Iron bar", examine: "A bar of iron.", value: 35, cat: "bar", icon: ["bar", "#6d6a66"] },
  steel_bar: { name: "Steel bar", examine: "A bar of steel.", value: 100, cat: "bar", icon: ["bar", "#a3abb0"] },
  gold_bar: { name: "Gold bar", examine: "Too soft for blades.", value: 180, cat: "bar", icon: ["bar", "#e8c040"] },
  cobalt_bar: { name: "Cobalt bar", examine: "A bar of cobalt.", value: 300, cat: "bar", icon: ["bar", "#4d6fd0"] },
  verdite_bar: { name: "Verdite bar", examine: "A bar of verdite.", value: 550, cat: "bar", icon: ["bar", "#3f9a6c"] },
  emberite_bar: { name: "Emberite bar", examine: "A bar of emberite.", value: 900, cat: "bar",
    icon: ["bar", "#b8433a"] },

  // ----------------------------------------------------------------
  // --------------------- Metal gear: bronze -----------------------
  // ----------------------------------------------------------------
  bronze_axe: { name: "Bronze axe", examine: "Fells trees. Fights, badly.", value: 18, cat: "weapon",
    icon: ["axe", "#b0743a", "#7a5532"], tool: { cat: "axe", mult: 1, lvl: 1 },
    equip: { slot: "weapon", att: 3, str: 4, def: 0, speed: 5, req: { attack: 1 } } },
  bronze_pickaxe: { name: "Bronze pickaxe", examine: "Breaks rock. Fights, badly.", value: 36, cat: "weapon",
    icon: ["pickaxe", "#b0743a", "#7a5532"], tool: { cat: "pickaxe", mult: 1, lvl: 1 },
    equip: { slot: "weapon", att: 3, str: 4, def: 0, speed: 5, req: { attack: 1 } } },
  bronze_sword: { name: "Bronze sword", examine: "A balanced one-handed blade.", value: 18, cat: "weapon",
    icon: ["sword", "#b0743a", "#5a3c22"], equip: { slot: "weapon", att: 6, str: 5, def: 0, speed: 4, req: { attack: 1 } } },
  bronze_dagger: { name: "Bronze dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 18,
    cat: "weapon", icon: ["dagger", "#b0743a", "#5a3c22"],
    equip: { slot: "weapon", att: -13, str: 2, def: 0, speed: 3, req: { attack: 1 } } },
  bronze_mace: { name: "Bronze mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 36,
    cat: "weapon", icon: ["mace", "#b0743a", "#7a5532"],
    equip: { slot: "weapon", att: 5, str: 18, def: 0, speed: 5, req: { attack: 1 } } },
  bronze_greatsword: { name: "Bronze greatsword", examine: "Two hands, one swing, no shield.", value: 55,
    cat: "weapon", icon: ["greatsword", "#b0743a", "#5a3c22"],
    equip: { slot: "weapon", att: 7, str: 44, def: 0, speed: 7, twoHanded: true, req: { attack: 1 } } },
  bronze_helm: { name: "Bronze helm", examine: "Keeps your thoughts inside.", value: 36, cat: "armour",
    icon: ["helm", "#b0743a"], equip: { slot: "head", att: 0, str: 0, def: 4, req: { defence: 1 } } },
  bronze_shield: { name: "Bronze shield", examine: "Stand behind it.", value: 55, cat: "armour",
    icon: ["shield", "#b0743a"], equip: { slot: "shield", att: 0, str: 0, def: 6, req: { defence: 1 } } },
  bronze_greaves: { name: "Bronze greaves", examine: "Armoured leg plates.", value: 55, cat: "armour",
    icon: ["greaves", "#b0743a"], equip: { slot: "legs", att: 0, str: 0, def: 8, req: { defence: 1 } } },
  bronze_breastplate: { name: "Bronze breastplate", examine: "Heavy, hot, worth it.", value: 91, cat: "armour",
    icon: ["breastplate", "#b0743a"], equip: { slot: "body", att: 0, str: 0, def: 15, req: { defence: 1 } } },

  // ----------------------------------------------------------------
  // ---------------------- Metal gear: iron ------------------------
  // ----------------------------------------------------------------
  iron_axe: { name: "Iron axe", examine: "Fells trees. Fights, badly.", value: 46, cat: "weapon",
    icon: ["axe", "#6d6a66", "#7a5532"], tool: { cat: "axe", mult: 1.1, lvl: 5 },
    equip: { slot: "weapon", att: 5, str: 6, def: 0, speed: 5, req: { attack: 5 } } },
  iron_pickaxe: { name: "Iron pickaxe", examine: "Breaks rock. Fights, badly.", value: 91, cat: "weapon",
    icon: ["pickaxe", "#6d6a66", "#7a5532"], tool: { cat: "pickaxe", mult: 1.1, lvl: 5 },
    equip: { slot: "weapon", att: 5, str: 6, def: 0, speed: 5, req: { attack: 5 } } },
  iron_sword: { name: "Iron sword", examine: "A balanced one-handed blade.", value: 46, cat: "weapon",
    icon: ["sword", "#6d6a66", "#5a3c22"], equip: { slot: "weapon", att: 9, str: 8, def: 0, speed: 4, req: { attack: 5 } } },
  iron_dagger: { name: "Iron dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 46,
    cat: "weapon", icon: ["dagger", "#6d6a66", "#5a3c22"],
    equip: { slot: "weapon", att: -7, str: 3, def: 0, speed: 3, req: { attack: 5 } } },
  iron_mace: { name: "Iron mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 91,
    cat: "weapon", icon: ["mace", "#6d6a66", "#7a5532"],
    equip: { slot: "weapon", att: 7, str: 24, def: 0, speed: 5, req: { attack: 5 } } },
  iron_greatsword: { name: "Iron greatsword", examine: "Two hands, one swing, no shield.", value: 137,
    cat: "weapon", icon: ["greatsword", "#6d6a66", "#5a3c22"],
    equip: { slot: "weapon", att: 10, str: 56, def: 0, speed: 7, twoHanded: true, req: { attack: 5 } } },
  iron_helm: { name: "Iron helm", examine: "Keeps your thoughts inside.", value: 91, cat: "armour",
    icon: ["helm", "#6d6a66"], equip: { slot: "head", att: 0, str: 0, def: 6, req: { defence: 5 } } },
  iron_shield: { name: "Iron shield", examine: "Stand behind it.", value: 137, cat: "armour",
    icon: ["shield", "#6d6a66"], equip: { slot: "shield", att: 0, str: 0, def: 8, req: { defence: 5 } } },
  iron_greaves: { name: "Iron greaves", examine: "Armoured leg plates.", value: 137, cat: "armour",
    icon: ["greaves", "#6d6a66"], equip: { slot: "legs", att: 0, str: 0, def: 11, req: { defence: 5 } } },
  iron_breastplate: { name: "Iron breastplate", examine: "Heavy, hot, worth it.", value: 228, cat: "armour",
    icon: ["breastplate", "#6d6a66"], equip: { slot: "body", att: 0, str: 0, def: 21, req: { defence: 5 } } },

  // ----------------------------------------------------------------
  // ---------------------- Metal gear: steel -----------------------
  // ----------------------------------------------------------------
  steel_axe: { name: "Steel axe", examine: "Fells trees. Fights, badly.", value: 130, cat: "weapon",
    icon: ["axe", "#a3abb0", "#7a5532"], tool: { cat: "axe", mult: 1.2, lvl: 10 },
    equip: { slot: "weapon", att: 8, str: 9, def: 0, speed: 5, req: { attack: 10 } } },
  steel_pickaxe: { name: "Steel pickaxe", examine: "Breaks rock. Fights, badly.", value: 260, cat: "weapon",
    icon: ["pickaxe", "#a3abb0", "#7a5532"], tool: { cat: "pickaxe", mult: 1.2, lvl: 10 },
    equip: { slot: "weapon", att: 8, str: 9, def: 0, speed: 5, req: { attack: 10 } } },
  steel_sword: { name: "Steel sword", examine: "A balanced one-handed blade.", value: 130, cat: "weapon",
    icon: ["sword", "#a3abb0", "#5a3c22"],
    equip: { slot: "weapon", att: 14, str: 13, def: 0, speed: 4, req: { attack: 10 } } },
  steel_dagger: { name: "Steel dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 130,
    cat: "weapon", icon: ["dagger", "#a3abb0", "#5a3c22"],
    equip: { slot: "weapon", att: 1, str: 5, def: 0, speed: 3, req: { attack: 10 } } },
  steel_mace: { name: "Steel mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 260,
    cat: "weapon", icon: ["mace", "#a3abb0", "#7a5532"],
    equip: { slot: "weapon", att: 11, str: 34, def: 0, speed: 5, req: { attack: 10 } } },
  steel_greatsword: { name: "Steel greatsword", examine: "Two hands, one swing, no shield.", value: 390,
    cat: "weapon", icon: ["greatsword", "#a3abb0", "#5a3c22"],
    equip: { slot: "weapon", att: 15, str: 74, def: 0, speed: 7, twoHanded: true, req: { attack: 10 } } },
  steel_helm: { name: "Steel helm", examine: "Keeps your thoughts inside.", value: 260, cat: "armour",
    icon: ["helm", "#a3abb0"], equip: { slot: "head", att: 0, str: 0, def: 9, req: { defence: 10 } } },
  steel_shield: { name: "Steel shield", examine: "Stand behind it.", value: 390, cat: "armour",
    icon: ["shield", "#a3abb0"], equip: { slot: "shield", att: 0, str: 0, def: 12, req: { defence: 10 } } },
  steel_greaves: { name: "Steel greaves", examine: "Armoured leg plates.", value: 390, cat: "armour",
    icon: ["greaves", "#a3abb0"], equip: { slot: "legs", att: 0, str: 0, def: 17, req: { defence: 10 } } },
  steel_breastplate: { name: "Steel breastplate", examine: "Heavy, hot, worth it.", value: 650, cat: "armour",
    icon: ["breastplate", "#a3abb0"], equip: { slot: "body", att: 0, str: 0, def: 32, req: { defence: 10 } } },

  // ----------------------------------------------------------------
  // --------------------- Metal gear: cobalt -----------------------
  // ----------------------------------------------------------------
  cobalt_axe: { name: "Cobalt axe", examine: "Fells trees. Fights, badly.", value: 390, cat: "weapon",
    icon: ["axe", "#4d6fd0", "#7a5532"], tool: { cat: "axe", mult: 1.35, lvl: 20 },
    equip: { slot: "weapon", att: 12, str: 13, def: 0, speed: 5, req: { attack: 20 } } },
  cobalt_pickaxe: { name: "Cobalt pickaxe", examine: "Breaks rock. Fights, badly.", value: 780, cat: "weapon",
    icon: ["pickaxe", "#4d6fd0", "#7a5532"], tool: { cat: "pickaxe", mult: 1.35, lvl: 20 },
    equip: { slot: "weapon", att: 12, str: 13, def: 0, speed: 5, req: { attack: 20 } } },
  cobalt_sword: { name: "Cobalt sword", examine: "A balanced one-handed blade.", value: 390, cat: "weapon",
    icon: ["sword", "#4d6fd0", "#5a3c22"],
    equip: { slot: "weapon", att: 20, str: 19, def: 0, speed: 4, req: { attack: 20 } } },
  cobalt_dagger: { name: "Cobalt dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 390,
    cat: "weapon", icon: ["dagger", "#4d6fd0", "#5a3c22"],
    equip: { slot: "weapon", att: 1, str: 8, def: 0, speed: 3, req: { attack: 20 } } },
  cobalt_mace: { name: "Cobalt mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 780,
    cat: "weapon", icon: ["mace", "#4d6fd0", "#7a5532"],
    equip: { slot: "weapon", att: 15, str: 45, def: 0, speed: 5, req: { attack: 20 } } },
  cobalt_greatsword: { name: "Cobalt greatsword", examine: "Two hands, one swing, no shield.", value: 1170,
    cat: "weapon", icon: ["greatsword", "#4d6fd0", "#5a3c22"],
    equip: { slot: "weapon", att: 21, str: 96, def: 0, speed: 7, twoHanded: true, req: { attack: 20 } } },
  cobalt_helm: { name: "Cobalt helm", examine: "Keeps your thoughts inside.", value: 780, cat: "armour",
    icon: ["helm", "#4d6fd0"], equip: { slot: "head", att: 0, str: 0, def: 13, req: { defence: 20 } } },
  cobalt_shield: { name: "Cobalt shield", examine: "Stand behind it.", value: 1170, cat: "armour",
    icon: ["shield", "#4d6fd0"], equip: { slot: "shield", att: 0, str: 0, def: 17, req: { defence: 20 } } },
  cobalt_greaves: { name: "Cobalt greaves", examine: "Armoured leg plates.", value: 1170, cat: "armour",
    icon: ["greaves", "#4d6fd0"], equip: { slot: "legs", att: 0, str: 0, def: 25, req: { defence: 20 } } },
  cobalt_breastplate: { name: "Cobalt breastplate", examine: "Heavy, hot, worth it.", value: 1950, cat: "armour",
    icon: ["breastplate", "#4d6fd0"], equip: { slot: "body", att: 0, str: 0, def: 46, req: { defence: 20 } } },

  // ----------------------------------------------------------------
  // --------------------- Metal gear: verdite ----------------------
  // ----------------------------------------------------------------
  verdite_axe: { name: "Verdite axe", examine: "Fells trees. Fights, badly.", value: 715, cat: "weapon",
    icon: ["axe", "#3f9a6c", "#7a5532"], tool: { cat: "axe", mult: 1.5, lvl: 30 },
    equip: { slot: "weapon", att: 17, str: 18, def: 0, speed: 5, req: { attack: 30 } } },
  verdite_pickaxe: { name: "Verdite pickaxe", examine: "Breaks rock. Fights, badly.", value: 1430, cat: "weapon",
    icon: ["pickaxe", "#3f9a6c", "#7a5532"], tool: { cat: "pickaxe", mult: 1.5, lvl: 30 },
    equip: { slot: "weapon", att: 17, str: 18, def: 0, speed: 5, req: { attack: 30 } } },
  verdite_sword: { name: "Verdite sword", examine: "A balanced one-handed blade.", value: 715, cat: "weapon",
    icon: ["sword", "#3f9a6c", "#5a3c22"],
    equip: { slot: "weapon", att: 28, str: 27, def: 0, speed: 4, req: { attack: 30 } } },
  verdite_dagger: { name: "Verdite dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 715,
    cat: "weapon", icon: ["dagger", "#3f9a6c", "#5a3c22"],
    equip: { slot: "weapon", att: 11, str: 11, def: 0, speed: 3, req: { attack: 30 } } },
  verdite_mace: { name: "Verdite mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 1430,
    cat: "weapon", icon: ["mace", "#3f9a6c", "#7a5532"],
    equip: { slot: "weapon", att: 21, str: 58, def: 0, speed: 5, req: { attack: 30 } } },
  verdite_greatsword: { name: "Verdite greatsword", examine: "Two hands, one swing, no shield.", value: 2145,
    cat: "weapon", icon: ["greatsword", "#3f9a6c", "#5a3c22"],
    equip: { slot: "weapon", att: 29, str: 120, def: 0, speed: 7, twoHanded: true, req: { attack: 30 } } },
  verdite_helm: { name: "Verdite helm", examine: "Keeps your thoughts inside.", value: 1430, cat: "armour",
    icon: ["helm", "#3f9a6c"], equip: { slot: "head", att: 0, str: 0, def: 18, req: { defence: 30 } } },
  verdite_shield: { name: "Verdite shield", examine: "Stand behind it.", value: 2145, cat: "armour",
    icon: ["shield", "#3f9a6c"], equip: { slot: "shield", att: 0, str: 0, def: 24, req: { defence: 30 } } },
  verdite_greaves: { name: "Verdite greaves", examine: "Armoured leg plates.", value: 2145, cat: "armour",
    icon: ["greaves", "#3f9a6c"], equip: { slot: "legs", att: 0, str: 0, def: 35, req: { defence: 30 } } },
  verdite_breastplate: { name: "Verdite breastplate", examine: "Heavy, hot, worth it.", value: 3575, cat: "armour",
    icon: ["breastplate", "#3f9a6c"], equip: { slot: "body", att: 0, str: 0, def: 65, req: { defence: 30 } } },

  // ----------------------------------------------------------------
  // -------------------- Metal gear: emberite ----------------------
  // ----------------------------------------------------------------
  emberite_axe: { name: "Emberite axe", examine: "Fells trees. Fights, badly.", value: 1170, cat: "weapon",
    icon: ["axe", "#b8433a", "#7a5532"], tool: { cat: "axe", mult: 1.7, lvl: 40 },
    equip: { slot: "weapon", att: 24, str: 26, def: 0, speed: 5, req: { attack: 40 } } },
  emberite_pickaxe: { name: "Emberite pickaxe", examine: "Breaks rock. Fights, badly.", value: 2340, cat: "weapon",
    icon: ["pickaxe", "#b8433a", "#7a5532"], tool: { cat: "pickaxe", mult: 1.7, lvl: 40 },
    equip: { slot: "weapon", att: 24, str: 26, def: 0, speed: 5, req: { attack: 40 } } },
  emberite_sword: { name: "Emberite sword", examine: "A balanced one-handed blade.", value: 1170, cat: "weapon",
    icon: ["sword", "#b8433a", "#5a3c22"],
    equip: { slot: "weapon", att: 40, str: 38, def: 0, speed: 4, req: { attack: 40 } } },
  emberite_dagger: { name: "Emberite dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 1170,
    cat: "weapon", icon: ["dagger", "#b8433a", "#5a3c22"],
    equip: { slot: "weapon", att: 28, str: 15, def: 0, speed: 3, req: { attack: 40 } } },
  emberite_mace: { name: "Emberite mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 2340,
    cat: "weapon", icon: ["mace", "#b8433a", "#7a5532"],
    equip: { slot: "weapon", att: 30, str: 74, def: 0, speed: 5, req: { attack: 40 } } },
  emberite_greatsword: { name: "Emberite greatsword", examine: "Two hands, one swing, no shield.", value: 3510,
    cat: "weapon", icon: ["greatsword", "#b8433a", "#5a3c22"],
    equip: { slot: "weapon", att: 42, str: 150, def: 0, speed: 7, twoHanded: true, req: { attack: 40 } } },
  emberite_helm: { name: "Emberite helm", examine: "Keeps your thoughts inside.", value: 2340, cat: "armour",
    icon: ["helm", "#b8433a"], equip: { slot: "head", att: 0, str: 0, def: 25, req: { defence: 40 } } },
  emberite_shield: { name: "Emberite shield", examine: "Stand behind it.", value: 3510, cat: "armour",
    icon: ["shield", "#b8433a"], equip: { slot: "shield", att: 0, str: 0, def: 34, req: { defence: 40 } } },
  emberite_greaves: { name: "Emberite greaves", examine: "Armoured leg plates.", value: 3510, cat: "armour",
    icon: ["greaves", "#b8433a"], equip: { slot: "legs", att: 0, str: 0, def: 50, req: { defence: 40 } } },
  emberite_breastplate: { name: "Emberite breastplate", examine: "Heavy, hot, worth it.", value: 5850, cat: "armour",
    icon: ["breastplate", "#b8433a"], equip: { slot: "body", att: 0, str: 0, def: 82, req: { defence: 40 } } },

  // ----------------------------------------------------------------
  // ----------------------------- Food -----------------------------
  // ----------------------------------------------------------------
  raw_shrimp: { name: "Raw shrimp", examine: "Raw shrimp. Cook it first.", value: 2, cat: "raw_food",
    icon: ["shrimp", "#e89a8a", "#c0503a"] },
  shrimp: { name: "Shrimp", examine: "A mouthful of the sea.", value: 5, cat: "food", food: { heal: 3 },
    icon: ["shrimp", "#f07a50", "#c04a2a"] },
  raw_sardine: { name: "Raw sardine", examine: "Raw sardine. Cook it first.", value: 4, cat: "raw_food",
    icon: ["fish", "#8aa0b0", "#5b6a78", "#c8d8e4"] },
  sardine: { name: "Sardine", examine: "Small, oily, salty.", value: 8, cat: "food", food: { heal: 4 },
    icon: ["fish", "#b89870", "#5b5040", "#4a3a28"] },
  raw_chicken: { name: "Raw chicken", examine: "Raw chicken. Cook it first.", value: 2, cat: "raw_food",
    icon: ["meat", "#f0c8b0", "#f0ece0"] },
  cooked_chicken: { name: "Cooked chicken", examine: "Golden and greasy.", value: 4, cat: "food", food: { heal: 3 },
    icon: ["meat", "#c89040", "#e8dcc0"] },
  raw_beef: { name: "Raw beef", examine: "Raw beef. Cook it first.", value: 2, cat: "raw_food",
    icon: ["meat", "#c04040", "#f0ece0"] },
  cooked_beef: { name: "Cooked beef", examine: "Chewy but honest.", value: 4, cat: "food", food: { heal: 3 },
    icon: ["meat", "#7a4426", "#e8dcc0"] },
  raw_trout: { name: "Raw trout", examine: "Raw trout. Cook it first.", value: 10, cat: "raw_food",
    icon: ["fish", "#8f9a68", "#e89a8a", "#d0d8b0"] },
  trout: { name: "Trout", examine: "Flaky and pink.", value: 20, cat: "food", food: { heal: 7 },
    icon: ["fish", "#c8864e", "#7a4a2a", "#5a3218"] },
  raw_salmon: { name: "Raw salmon", examine: "Raw salmon. Cook it first.", value: 18, cat: "raw_food",
    icon: ["fish", "#b8a4a8", "#e07a5a", "#eef0f4"] },
  salmon: { name: "Salmon", examine: "Rich river fish.", value: 35, cat: "food", food: { heal: 9 },
    icon: ["fish", "#f0a080", "#a04a2a", "#7a3018"] },
  raw_tuna: { name: "Raw tuna", examine: "Raw tuna. Cook it first.", value: 25, cat: "raw_food",
    icon: ["fish_long", "#4a5a7a", "#a0a8b0"] },
  tuna: { name: "Tuna", examine: "A thick steak of tuna.", value: 50, cat: "food", food: { heal: 10 },
    icon: ["steak", "#c87a68", "#6a3e1e"] },
  raw_lobster: { name: "Raw lobster", examine: "Raw lobster. Cook it first.", value: 50, cat: "raw_food",
    icon: ["lobster", "#3a5a6a", "#c0503a"] },
  lobster: { name: "Lobster", examine: "Cracked and buttery.", value: 100, cat: "food", food: { heal: 12 },
    icon: ["lobster", "#d8402a", "#8a2018"] },
  raw_swordfish: { name: "Raw swordfish", examine: "Raw swordfish. Cook it first.", value: 80, cat: "raw_food",
    icon: ["swordfish", "#5a6a8a", "#c0c8d0"] },
  swordfish: { name: "Swordfish", examine: "Dense, meaty, regal.", value: 160, cat: "food", food: { heal: 14 },
    icon: ["swordfish", "#b88a70", "#5a3a26"] },
  raw_shark: { name: "Raw shark", examine: "Raw shark. Cook it first.", value: 150, cat: "raw_food",
    icon: ["shark", "#7a8088", "#d0d4d8"] },
  shark: { name: "Shark", examine: "Eat it before it eats you.", value: 300, cat: "food", food: { heal: 20 },
    icon: ["shark", "#9a7a60", "#4a3a2a"] },

  // ----------------------------------------------------------------
  // ---------------- Crafting materials and products ---------------
  // ----------------------------------------------------------------
  cowhide: { name: "Cowhide", examine: "Smells of cow.", value: 5, cat: "hide", icon: ["hide", "#f0ece0", "#2b2118"] },
  leather: { name: "Leather", examine: "Tanned and supple.", value: 15, cat: "hide", icon: ["leather", "#8a5a30"],
    iops: [{ id: "craft", label: "Craft", rids: ["craft_leather_gloves", "craft_leather_boots",
      "craft_leather_jerkin", "craft_leather_leggings"] }] },
  wolf_pelt: { name: "Wolf pelt", examine: "Coarse grey fur, ash in every hair.", value: 60, cat: "hide",
    icon: ["hide", "#6b6660", "#4e4a45"] },
  wolf_leather: { name: "Wolf leather", examine: "Tough, smoky leather.", value: 100, cat: "hide",
    icon: ["leather", "#5a5450"],
    iops: [{ id: "craft", label: "Craft", rids: ["craft_wolfhide_vambraces", "craft_wolfhide_leggings",
      "craft_wolfhide_jerkin"] }] },
  leather_gloves: { name: "Leather gloves", examine: "Soft gloves.", value: 20, cat: "leather",
    icon: ["gloves", "#8a5a30"], equip: { slot: "hands", att: 0, str: 0, def: 1 } },
  leather_boots: { name: "Leather boots", examine: "Good for long walks.", value: 22, cat: "leather",
    icon: ["boots", "#8a5a30"], equip: { slot: "feet", att: 0, str: 0, def: 1 } },
  leather_jerkin: { name: "Leather jerkin", examine: "Light and flexible.", value: 40, cat: "leather",
    icon: ["jerkin", "#8a5a30"], equip: { slot: "body", att: 0, str: 0, def: 8 } },
  leather_leggings: { name: "Leather leggings", examine: "Creak when you walk.", value: 35, cat: "leather",
    icon: ["leggings", "#8a5a30"], equip: { slot: "legs", att: 0, str: 0, def: 4 } },
  wolfhide_vambraces: { name: "Wolfhide vambraces", examine: "Bracers of smoked wolfhide.", value: 300, cat: "leather",
    icon: ["vambraces", "#5a5450"], equip: { slot: "hands", att: 4, str: 2, def: 4, req: { defence: 30 } } },
  wolfhide_leggings: { name: "Wolfhide leggings", examine: "Smoky, sturdy leggings.", value: 600, cat: "leather",
    icon: ["leggings", "#5a5450"], equip: { slot: "legs", att: 2, str: 0, def: 16, req: { defence: 30 } } },
  wolfhide_jerkin: { name: "Wolfhide jerkin", examine: "Smells of ash and victory.", value: 900, cat: "leather",
    icon: ["jerkin", "#5a5450"], equip: { slot: "body", att: 3, str: 0, def: 34, req: { defence: 30 } } },
  uncut_sapphire: { name: "Uncut sapphire", examine: "A rough, cloudy gem.", value: 50, cat: "gem_uncut",
    icon: ["gem_uncut", "#3a5fd0"], iops: [{ id: "cut", label: "Cut", rids: ["cut_sapphire"] }] },
  uncut_emerald: { name: "Uncut emerald", examine: "A rough, cloudy gem.", value: 100, cat: "gem_uncut",
    icon: ["gem_uncut", "#2f9a5a"], iops: [{ id: "cut", label: "Cut", rids: ["cut_emerald"] }] },
  uncut_ruby: { name: "Uncut ruby", examine: "A rough, cloudy gem.", value: 200, cat: "gem_uncut",
    icon: ["gem_uncut", "#c02838"], iops: [{ id: "cut", label: "Cut", rids: ["cut_ruby"] }] },
  uncut_diamond: { name: "Uncut diamond", examine: "A rough, cloudy gem.", value: 500, cat: "gem_uncut",
    icon: ["gem_uncut", "#e8f4ff"], iops: [{ id: "cut", label: "Cut", rids: ["cut_diamond"] }] },
  sapphire: { name: "Sapphire", examine: "A cut sapphire. It sparkles.", value: 100, cat: "gem", icon: ["gem", "#3a5fd0"] },
  emerald: { name: "Emerald", examine: "A cut emerald. It sparkles.", value: 200, cat: "gem", icon: ["gem", "#2f9a5a"] },
  ruby: { name: "Ruby", examine: "A cut ruby. It sparkles.", value: 400, cat: "gem", icon: ["gem", "#c02838"] },
  diamond: { name: "Diamond", examine: "A cut diamond. It sparkles.", value: 1000, cat: "gem", icon: ["gem", "#e8f4ff"] },
  gold_ring: { name: "Gold ring", examine: "A plain gold band.", value: 220, cat: "jewellery",
    icon: ["ring", "#e8c040"], equip: { slot: "ring", att: 0, str: 0, def: 1 } },
  gold_amulet: { name: "Gold amulet", examine: "Simple, bright.", value: 260, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#f8e070"], equip: { slot: "neck", att: 2, str: 2, def: 2 } },
  sapphire_amulet: { name: "Sapphire amulet", examine: "Steadies the hand.", value: 500, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#3a5fd0"], equip: { slot: "neck", att: 6, str: 0, def: 0 } },
  emerald_amulet: { name: "Emerald amulet", examine: "Calm, green, guarded.", value: 750, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#2f9a5a"], equip: { slot: "neck", att: 0, str: 0, def: 8 } },
  ruby_amulet: { name: "Ruby amulet", examine: "Warm against the skin.", value: 1200, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#c02838"], equip: { slot: "neck", att: 0, str: 8, def: 0 } },
  diamond_amulet: { name: "Diamond amulet", examine: "Clear as resolve.", value: 2600, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#e8f4ff"], equip: { slot: "neck", att: 8, str: 8, def: 8 } },

  // ----------------------------------------------------------------
  // ------------------- Across the Sound (12.6) --------------------
  // ----------------------------------------------------------------
  uncut_sunstone: { name: "Uncut sunstone", examine: "Warm to the touch, even in shade.", value: 700, cat: "gem_uncut",
    icon: ["gem_uncut", "#f0a020"], iops: [{ id: "cut", label: "Cut", rids: ["cut_sunstone"] }] },
  sunstone: { name: "Sunstone", examine: "A cut sunstone. It holds the light.", value: 1400, cat: "gem",
    icon: ["gem", "#ffb830"] },
  sunstone_ring: { name: "Sunstone ring", examine: "A gold band around a captured sunset.", value: 2400, cat: "jewellery",
    icon: ["ring", "#e8c040", "#ffb830"], equip: { slot: "ring", att: 2, str: 2, def: 2 } },
  sunstone_amulet: { name: "Sunstone amulet", examine: "It glows faintly against your chest.", value: 3600,
    cat: "jewellery", icon: ["amulet", "#e8c040", "#ffb830"], equip: { slot: "neck", att: 10, str: 10, def: 10 } },
  sunstone_circlet: { name: "Sunstone circlet", examine: "A thin gold crown set with one bright stone.", value: 3200,
    cat: "jewellery", icon: ["helm", "#e8c040", "#ffb830"], equip: { slot: "head", att: 4, str: 0, def: 12 } },
  raw_vale_eel: { name: "Raw vale eel", examine: "Raw vale eel. Cook it first.", value: 60, cat: "raw_food",
    icon: ["fish_long", "#4a5a3a", "#a0b080"] },
  vale_eel: { name: "Vale eel", examine: "Smoky, rich and slightly alarming.", value: 120, cat: "food", food: { heal: 15 },
    icon: ["fish_long", "#8a6040", "#4a3420"] },
  meat_pie: { name: "Meat pie", examine: "Wyn's best. The crust holds up to anything.", value: 30, cat: "food",
    food: { heal: 11 }, icon: ["meat", "#e0b860", "#7a4426"] },
  kings_seal: { name: "King's seal", examine: "A cold iron seal, heavy as a grave.", value: 0, cat: "quest",
    untradeable: true, icon: ["seal", "#5a5a6a", "#c8e8ff"] },
  hollow_crown: { name: "Hollow crown", examine: "A crown of dark iron. It sits lightly, and watches.", value: 0,
    cat: "armour", untradeable: true, icon: ["helm", "#3a3530", "#c8e8ff"],
    equip: { slot: "head", att: 6, str: 6, def: 20 } },
  amber_logs: { name: "Amber logs", examine: "Golden wood that smells of honey and smoke.", value: 400, cat: "log",
    icon: ["logs", "#9a6018", "#f0c050"], iops: [{ id: "light", label: "Light", rids: ["light_amber_logs"] }] },
  amber_sap: { name: "Amber sap", examine: "A bead of golden sap, hard as glass.", value: 300, cat: "misc",
    icon: ["misc", "#e8a020", "#7a4a10"] },
  amber_charm: { name: "Amber charm", examine: "A gold charm around a bead of old sunlight.", value: 5200, cat: "jewellery",
    icon: ["amulet", "#e8c040", "#f08a20"], equip: { slot: "neck", att: 12, str: 12, def: 12 } },
  raw_lanternfish: { name: "Raw lanternfish", examine: "Raw lanternfish. Cook it first.", value: 90, cat: "raw_food",
    icon: ["fish", "#3a4a6a", "#e8d070", "#8a9ab8"] },
  lanternfish: { name: "Lanternfish", examine: "It still glows a little. Eat it anyway.", value: 180, cat: "food",
    food: { heal: 17 }, icon: ["fish", "#d8b060", "#7a5a2a", "#5a3a18"] },
  raw_stormray: { name: "Raw stormray", examine: "Raw stormray. Cook it first.", value: 220, cat: "raw_food",
    icon: ["shark", "#3a3f5a", "#9aa8c8"] },
  stormray: { name: "Stormray", examine: "Thick, smoky fillets. A meal for a storm.", value: 440, cat: "food",
    food: { heal: 23 }, icon: ["shark", "#c8a080", "#5a3a26"] },
  salt: { name: "Salt", examine: "Coarse grey salt from the Brinemarsh pans.", value: 10, cat: "misc",
    icon: ["ore", "#f4f1e8", "#9a968c"] },
  cured_beef: { name: "Cured beef", examine: "Salted hard. It keeps for a year.", value: 40, cat: "food", food: { heal: 14 },
    icon: ["meat", "#5a2018", "#e8dcc0"] },
  cured_swordfish: { name: "Cured swordfish", examine: "Salt-dried steaks, wrapped in cloth.", value: 200, cat: "food",
    food: { heal: 18 }, icon: ["swordfish", "#d8c0a0", "#7a5a3a"] },
  cured_lanternfish: { name: "Cured lanternfish", examine: "Salted, smoked, and faintly glowing.", value: 240,
    cat: "food", food: { heal: 21 }, icon: ["fish", "#a07a50", "#5a3a20", "#e8d070"] },
  starmetal_ore: { name: "Starmetal ore", examine: "Cold, heavy, and humming.", value: 650, cat: "ore",
    icon: ["ore", "#9fd6ff", "#3a4a5a"] },
  starsteel_bar: { name: "Starsteel bar", examine: "A bar of starsteel. It rings like a bell.", value: 1500, cat: "bar",
    icon: ["bar", "#c8e8ff"] },
  starsteel_axe: { name: "Starsteel axe", examine: "Fells trees. Fights, badly.", value: 1950, cat: "weapon",
    icon: ["axe", "#c8e8ff", "#7a5532"], tool: { cat: "axe", mult: 1.9, lvl: 50 },
    equip: { slot: "weapon", att: 32, str: 34, def: 0, speed: 5, req: { attack: 50 } } },
  starsteel_pickaxe: { name: "Starsteel pickaxe", examine: "Breaks rock. Fights, badly.", value: 3900, cat: "weapon",
    icon: ["pickaxe", "#c8e8ff", "#7a5532"], tool: { cat: "pickaxe", mult: 1.9, lvl: 50 },
    equip: { slot: "weapon", att: 32, str: 34, def: 0, speed: 5, req: { attack: 50 } } },
  starsteel_sword: { name: "Starsteel sword", examine: "A balanced one-handed blade.", value: 1950, cat: "weapon",
    icon: ["sword", "#c8e8ff", "#5a3c22"],
    equip: { slot: "weapon", att: 52, str: 50, def: 0, speed: 4, req: { attack: 50 } } },
  starsteel_dagger: { name: "Starsteel dagger", examine: "Quick and light: it strikes often, if a little wild.", value: 1950, cat: "weapon",
    icon: ["dagger", "#c8e8ff", "#5a3c22"],
    equip: { slot: "weapon", att: 38, str: 20, def: 0, speed: 3, req: { attack: 50 } } },
  starsteel_mace: { name: "Starsteel mace", examine: "Flanged and heavy; it hits harder than it aims.", value: 3900, cat: "weapon",
    icon: ["mace", "#c8e8ff", "#5a3c22"],
    equip: { slot: "weapon", att: 40, str: 96, def: 0, speed: 5, req: { attack: 50 } } },
  starsteel_greatsword: { name: "Starsteel greatsword", examine: "Two hands, one swing, no shield.", value: 5850, cat: "weapon",
    icon: ["greatsword", "#c8e8ff", "#5a3c22"],
    equip: { slot: "weapon", att: 56, str: 195, def: 0, speed: 7, twoHanded: true, req: { attack: 50 } } },
  starsteel_helm: { name: "Starsteel helm", examine: "Keeps your thoughts inside.", value: 3900, cat: "armour",
    icon: ["helm", "#c8e8ff"], equip: { slot: "head", att: 0, str: 0, def: 33, req: { defence: 50 } } },
  starsteel_shield: { name: "Starsteel shield", examine: "Stand behind it.", value: 5850, cat: "armour",
    icon: ["shield", "#c8e8ff"], equip: { slot: "shield", att: 0, str: 0, def: 45, req: { defence: 50 } } },
  starsteel_greaves: { name: "Starsteel greaves", examine: "Armoured leg plates.", value: 5850, cat: "armour",
    icon: ["greaves", "#c8e8ff"], equip: { slot: "legs", att: 0, str: 0, def: 66, req: { defence: 50 } } },
  starsteel_breastplate: { name: "Starsteel breastplate", examine: "Heavy, hot, worth it.", value: 9750, cat: "armour",
    icon: ["breastplate", "#c8e8ff"], equip: { slot: "body", att: 0, str: 0, def: 104, req: { defence: 50 } } }
};
// ==== src/engine/data/objects.js ====
// ----------------------------------------------------------------
// ------------------------ Data: objects -------------------------
// ----------------------------------------------------------------
// Gather nodes, stations, ladders, quest objects and decor (DESIGN.md sections 7, 11, 13, 16).
// Placement is MAP's job (legend chars, place entries, fish groups); fire is placed by recipes.
Data.objects = {
  // ----------------------------------------------------------------
  // ---------------------------- Trees -----------------------------
  // ----------------------------------------------------------------
  tree: { name: "Tree", examine: "A sturdy tree. Good for logs.", draw: ["tree"], mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "logs", lvl: 1, xp: 25, low: 128, high: 256 }], deplete: 0.25, respawn: 25,
      depleted: "stump" }] },
  oak_tree: { name: "Oak tree", examine: "Broad, old and in no hurry.", draw: ["oak"], mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "oak_logs", lvl: 15, xp: 37.5, low: 80, high: 230 }], deplete: 0.125, respawn: 30,
      depleted: "stump" }] },
  willow_tree: { name: "Willow tree", examine: "Its branches trail in the water.", draw: ["willow"], mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "willow_logs", lvl: 30, xp: 67.5, low: 40, high: 160 }], deplete: 0.125, respawn: 35,
      depleted: "stump" }] },
  maple_tree: { name: "Maple tree", examine: "Its leaves are always turning.", draw: ["maple"], mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "maple_logs", lvl: 45, xp: 100, low: 28, high: 128 }], deplete: 0.1, respawn: 60,
      depleted: "stump" }] },
  yew_tree: { name: "Yew tree", examine: "Dark needles, older than the town.", draw: ["yew"], mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "yew_logs", lvl: 60, xp: 175, low: 18, high: 96 }], deplete: 0.0833, respawn: 100,
      depleted: "stump" }] },
  ironbark_tree: { name: "Ironbark tree", examine: "The bark rings when you tap it.", draw: ["ironbark"],
    mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      yields: [{ item: "ironbark_logs", lvl: 75, xp: 250, low: 12, high: 80 }], deplete: 0.0714, respawn: 150,
      depleted: "stump" }] },
  stump: { name: "Tree stump", examine: "Someone has been busy here.", draw: ["stump"], ops: [] },

  // ----------------------------------------------------------------
  // ---------------------------- Rocks -----------------------------
  // ----------------------------------------------------------------
  copper_rock: { name: "Copper rock", examine: "Streaked with reddish ore.", draw: ["rock", "#c8763a"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "copper_ore", lvl: 1, xp: 17.5, low: 160, high: 256 }], deplete: 1, respawn: 4,
      depleted: "rock_empty", gem: 200 }] },
  tin_rock: { name: "Tin rock", examine: "Dull grey ore glints in the stone.", draw: ["rock", "#c9c9c4"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "tin_ore", lvl: 1, xp: 17.5, low: 160, high: 256 }], deplete: 1, respawn: 4,
      depleted: "rock_empty", gem: 200 }] },
  iron_rock: { name: "Iron rock", examine: "Rusty seams run through it.", draw: ["rock", "#8a4e3a"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "iron_ore", lvl: 15, xp: 35, low: 96, high: 256 }], deplete: 1, respawn: 8,
      depleted: "rock_empty", gem: 200 }] },
  coal_rock: { name: "Coal rock", examine: "Black, crumbly and useful.", draw: ["rock", "#262626", "#4a4a4a"],
    mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "coal", lvl: 30, xp: 50, low: 48, high: 200 }], deplete: 1, respawn: 20,
      depleted: "rock_empty", gem: 200 }] },
  gold_rock: { name: "Gold rock", examine: "Bright flecks catch the light.", draw: ["rock", "#e8c040"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "gold_ore", lvl: 40, xp: 65, low: 32, high: 160 }], deplete: 1, respawn: 30,
      depleted: "rock_empty", gem: 200 }] },
  // Amberwood (11.6): Elin's grove. Risk tier: bark stalkers prowl among them. An autumn windfall adds a log.
  amberheart_tree: { name: "Amberheart tree", examine: "Golden sap beads on bark warm as skin.", draw: ["amber"],
    mapIcon: "woodcut",
    ops: [{ id: "chop", label: "Chop down", kind: "gather", skill: "woodcutting", tool: "axe", ticks: 4,
      if: [{ q: "amber_grove", eq: 100 }], fail: "Elin's mark is cut into the bark. Ask the woodward first.",
      yields: [{ item: "amber_logs", lvl: 85, xp: 300, low: 10, high: 70 }], deplete: 0.0625, respawn: 180,
      depleted: "stump",
      bonus: [{ item: "amber_sap", chance: 0.05, msg: "Golden sap wells from the cut." },
        { item: "amber_logs", chance: 0.25, if: [{ season: "autumn" }], msg: "An autumn windfall: a storm-felled branch." }] }] },
  // Brinemarsh (11.6): salt crusts mine like soft rock.
  salt_crust: { name: "Salt crust", examine: "A grey-white crust over the dried pan.", draw: ["rock", "#f4f1e8", "#c9c4b8"],
    mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "salt", lvl: 20, xp: 30, low: 120, high: 240 }], deplete: 1, respawn: 10, depleted: "rock_empty" }] },
  // Starfall Crater (11.6): risk tier, behind Vesna's quest.
  starmetal_rock: { name: "Starmetal rock", examine: "Pale metal veins hum inside the stone.",
    draw: ["rock", "#9fd6ff", "#ffffff"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      if: [{ q: "fallen_star", gte: 10 }], fail: "The stone hums, but it won't yield. Astronomer Vesna in Saltmere knows why.",
      yields: [{ item: "starmetal_ore", lvl: 80, xp: 220, low: 12, high: 100 }], deplete: 1, respawn: 45,
      depleted: "rock_empty", gem: 200 }] },
  // Redcliff Depths (11.4a): risk tier, like Greyspire's gold.
  sunstone_rock: { name: "Sunstone rock", examine: "Orange light glows deep in the sandstone.", draw: ["rock", "#f0a030"],
    mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "uncut_sunstone", lvl: 65, xp: 150, low: 18, high: 120 }], deplete: 1, respawn: 35,
      depleted: "rock_empty", gem: 200,
      bonus: [{ item: "uncut_sunstone", chance: 0.2, if: [{ season: "summer" }], msg: "The summer heat cracks loose a second stone." }] }] },
  gem_rock: { name: "Gem rock", examine: "Coloured flecks wink from the stone.",
    draw: ["rock", "#4d6fd0", "#3f9a6c", "#b8433a"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ table: "gem", lvl: 40, xp: 65, low: 32, high: 160 }], deplete: 1, respawn: 40,
      depleted: "rock_empty" }] },
  cobalt_rock: { name: "Cobalt rock", examine: "Blue ore, cold even down here.", draw: ["rock", "#8aa6f0"], mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "cobalt_ore", lvl: 45, xp: 85, low: 28, high: 150 }], deplete: 1, respawn: 25,
      depleted: "rock_empty", gem: 200 }] },
  verdite_rock: { name: "Verdite rock", examine: "Green veins twist through it.", draw: ["rock", "#78c99c"],
    mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      yields: [{ item: "verdite_ore", lvl: 60, xp: 130, low: 20, high: 125 }], deplete: 1, respawn: 30,
      depleted: "rock_empty", gem: 200 }] },
  emberite_rock: { name: "Emberite rock", examine: "The stone glows like a banked fire.", draw: ["rock", "#e5806f"],
    mapIcon: "mine",
    ops: [{ id: "mine", label: "Mine", kind: "gather", skill: "mining", tool: "pickaxe", ticks: 4,
      if: [{ q: "embers_beneath", gte: 100 }], fail: "The ore is too hot to touch while Smoulderjaw lives.",
      yields: [{ item: "emberite_ore", lvl: 75, xp: 195, low: 14, high: 110 }], deplete: 1, respawn: 40,
      depleted: "rock_empty", gem: 200 }] },
  rock_empty: { name: "Rocks", examine: "There's no ore left in it.", draw: ["rock_empty"], ops: [] },

  // ----------------------------------------------------------------
  // ------------------------ Fishing spots -------------------------
  // ----------------------------------------------------------------
  spot_net: { name: "Fishing spot", examine: "Small fish dart below the surface.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "net", label: "Net", kind: "gather", skill: "fishing", tool: "net", ticks: 5,
      yields: [{ item: "raw_shrimp", lvl: 1, xp: 15, low: 160, high: 256 },
        { item: "raw_sardine", lvl: 10, xp: 25, low: 48, high: 176 }],
      deplete: 0, respawn: 0, depleted: null }] },
  spot_lure: { name: "Fishing spot", examine: "Something quick flashes in the current.", draw: ["fish_spot"],
    block: false, mapIcon: "fish",
    ops: [{ id: "lure", label: "Lure", kind: "gather", skill: "fishing", tool: "rod", ticks: 5, bait: "feather",
      yields: [{ item: "raw_trout", lvl: 20, xp: 50, low: 72, high: 220 },
        { item: "raw_salmon", lvl: 30, xp: 70, low: 16, high: 128 }],
      deplete: 0, respawn: 0, depleted: null,
      bonus: [{ item: "courier_seal", chance: 0.125,
        if: [{ q: "river_courier", gte: 10, lt: 100 }, { not: { owns: "courier_seal" } }],
        msg: "Something brassy tangles on your line!" }] }] },
  spot_cage: { name: "Fishing spot", examine: "Claws click somewhere under the rocks.", draw: ["fish_spot"],
    block: false, mapIcon: "fish",
    ops: [{ id: "cage", label: "Cage", kind: "gather", skill: "fishing", tool: "cage", ticks: 5,
      yields: [{ item: "raw_lobster", lvl: 40, xp: 95, low: 48, high: 190 }],
      deplete: 0, respawn: 0, depleted: null }] },
  // Sunken Vale pools (11.5a)
  spot_eel: { name: "Fishing spot", examine: "Long shapes coil in the murky pool.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "lure", label: "Lure", kind: "gather", skill: "fishing", tool: "rod", ticks: 5, bait: "feather",
      yields: [{ item: "raw_vale_eel", lvl: 55, xp: 110, low: 24, high: 140 }], deplete: 0, respawn: 0, depleted: null,
      bonus: [{ item: "raw_vale_eel", chance: 0.25, if: [{ season: "spring" }], msg: "Spring floods bring the eels up thick." }] }] },
  // Stormcoast (11.6): lantern pots use a lobster cage; stormrays take a harpoon.
  spot_lantern: { name: "Fishing spot", examine: "Faint lights drift below the waves.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "cage", label: "Cage", kind: "gather", skill: "fishing", tool: "cage", ticks: 5,
      yields: [{ item: "raw_lanternfish", lvl: 62, xp: 120, low: 30, high: 150 }], deplete: 0, respawn: 0, depleted: null }] },
  spot_storm: { name: "Fishing spot", examine: "Wide dark wings ripple under the surf.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "harpoon", label: "Harpoon", kind: "gather", skill: "fishing", tool: "harpoon", ticks: 5,
      yields: [{ item: "raw_stormray", lvl: 88, xp: 240, low: 20, high: 120 }], deplete: 0, respawn: 0, depleted: null }] },
  spot_harpoon: { name: "Fishing spot", examine: "Big fins break the swell.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "harpoon", label: "Harpoon", kind: "gather", skill: "fishing", tool: "harpoon", ticks: 5,
      yields: [{ item: "raw_tuna", lvl: 35, xp: 85, low: 48, high: 180 },
        { item: "raw_swordfish", lvl: 50, xp: 130, low: 36, high: 170 }],
      deplete: 0, respawn: 0, depleted: null }] },
  spot_deep: { name: "Fishing spot", examine: "A long grey shadow circles below.", draw: ["fish_spot"], block: false,
    mapIcon: "fish",
    ops: [{ id: "harpoon", label: "Harpoon", kind: "gather", skill: "fishing", tool: "harpoon", ticks: 5,
      yields: [{ item: "raw_shark", lvl: 76, xp: 210, low: 28, high: 150 }],
      deplete: 0, respawn: 0, depleted: null }] },

  // ----------------------------------------------------------------
  // ------------------- Stations, ladders, shrine ------------------
  // ----------------------------------------------------------------
  bank_booth: { name: "Bank booth", examine: "The vault's polished counter.", draw: ["bank_booth"], from: "s",
    mapIcon: "bank", ops: [{ id: "bank", label: "Bank", kind: "bank" }] },
  furnace: { name: "Furnace", examine: "Hot enough to melt ore.", draw: ["furnace"], mapIcon: "furnace",
    ops: [{ id: "smelt", label: "Smelt", kind: "make", station: "furnace" }] },
  anvil: { name: "Anvil", examine: "Scarred by a thousand hammer blows.", draw: ["anvil"], mapIcon: "anvil",
    ops: [{ id: "smith", label: "Smith", kind: "make", station: "anvil" }] },
  range: { name: "Range", examine: "A sturdy iron stove, always warm.", draw: ["range"], mapIcon: "range",
    ops: [{ id: "cook", label: "Cook", kind: "make", station: "range" }] },
  fire: { name: "Fire", examine: "Warm and crackling.", draw: ["fire"], block: true,
    ops: [{ id: "cook", label: "Cook", kind: "make", station: "fire" }] },
  ladder_down: { name: "Ladder", examine: "It leads down into the dark.", draw: ["ladder_down"], mapIcon: "ladder",
    ops: [{ id: "climb", label: "Climb-down", kind: "climb" }] },
  ladder_up: { name: "Ladder", examine: "Daylight glimmers far above.", draw: ["ladder_up"], mapIcon: "ladder",
    ops: [{ id: "climb", label: "Climb-up", kind: "climb" }] },
  hearth_shrine: { name: "Hearth Shrine", examine: "A warm hearthstone. You always wake here.", draw: ["shrine"],
    block: false, mapIcon: "shrine", ops: [] },
  gravestone: { name: "Gravestone", examine: "Your belongings wait beneath it.", draw: ["gravestone"], block: false,
    ops: [] },

  // ----------------------------------------------------------------
  // ------------------------ Quest objects -------------------------
  // ----------------------------------------------------------------
  war_banner: { name: "War banner", examine: "Gnarltooth colours on a crooked pole.", draw: ["banner"],
    ops: [{ id: "burn", label: "Burn", kind: "script",
      if: [{ q: "gnarltooth_tolls", eq: 20 }, { has: "tinderbox" }, { lvl: "firemaking", gte: 10 }],
      fail: "You'd need a tinderbox, Firemaking 10 and a good reason.",
      do: [{ stage: ["gnarltooth_tolls", 30] },
        { msg: "The banner goes up in flames. A roar sounds from the largest tent!", c: "quest" }] }],
    uses: [{ item: "tinderbox", if: [{ q: "gnarltooth_tolls", eq: 20 }, { lvl: "firemaking", gte: 10 }],
      do: [{ stage: ["gnarltooth_tolls", 30] },
        { msg: "The banner goes up in flames. A roar sounds from the largest tent!", c: "quest" }],
      fail: "You'd need Firemaking 10 and a good reason." }],
    alt: { if: [{ q: "gnarltooth_tolls", gte: 30 }], name: "Burnt banner" } },
  beacon_west: { name: "Beacon", examine: "A cold iron brazier on the ridge.", draw: ["beacon"],
    ops: [{ id: "light", label: "Light", kind: "script",
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_west" } },
        { hasAny: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5 }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30.",
      do: [{ takeAny: [["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], 5] }, { flag: "beacon_west" },
        { xp: ["firemaking", 450] }, { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }] }],
    uses: [{ item: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5,
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_west" } }],
      do: [{ flag: "beacon_west" }, { xp: ["firemaking", 450] },
        { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30." }],
    alt: { if: [{ flag: "beacon_west" }], name: "Lit beacon" } },
  beacon_mid: { name: "Beacon", examine: "A cold iron brazier on the ridge.", draw: ["beacon"],
    ops: [{ id: "light", label: "Light", kind: "script",
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_mid" } },
        { hasAny: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5 }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30.",
      do: [{ takeAny: [["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], 5] }, { flag: "beacon_mid" },
        { xp: ["firemaking", 450] }, { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }] }],
    uses: [{ item: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5,
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_mid" } }],
      do: [{ flag: "beacon_mid" }, { xp: ["firemaking", 450] },
        { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30." }],
    alt: { if: [{ flag: "beacon_mid" }], name: "Lit beacon" } },
  beacon_east: { name: "Beacon", examine: "A cold iron brazier on the ridge.", draw: ["beacon"],
    ops: [{ id: "light", label: "Light", kind: "script",
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_east" } },
        { hasAny: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5 }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30.",
      do: [{ takeAny: [["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], 5] }, { flag: "beacon_east" },
        { xp: ["firemaking", 450] }, { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }] }],
    uses: [{ item: ["willow_logs", "maple_logs", "yew_logs", "ironbark_logs"], qty: 5,
      if: [{ q: "embers_beneath", eq: 20 }, { lvl: "firemaking", gte: 30 }, { not: { flag: "beacon_east" } }],
      do: [{ flag: "beacon_east" }, { xp: ["firemaking", 450] },
        { msg: "The beacon roars back to life. Far below, something shifts.", c: "quest" }],
      fail: "The beacon needs five logs of willow or better, and Firemaking 30." }],
    alt: { if: [{ flag: "beacon_east" }], name: "Lit beacon" } },
  lair_door: { name: "Lair door", examine: "Heat seeps around its edges.", draw: ["door"], from: "ew",
    ops: [{ id: "enter", label: "Enter", kind: "pass", if: [{ flag: "lair_ok" }] },
      { id: "enter_warn", label: "Enter", kind: "script", if: [{ not: { flag: "lair_ok" } }],
        do: [{ dialogue: "lair_warning" }] }] },
  ironbound_gate: { name: "Ironbound gate", examine: "Iron bands, a heavy lock and a warden's stool.", draw: ["gate"],
    from: "ns",
    ops: [{ id: "open", label: "Open", kind: "pass", if: [{ q: "gnarltooth_tolls", gte: 100 }],
      fail: "The gate is locked. Captain Marrick's wardens stand guard." }] },
  sealed_door: { name: "Sealed door", examine: "Cold stone that feels warm to the touch.", draw: ["door"], from: "ew",
    ops: [{ id: "open", label: "Open", kind: "pass", if: [{ q: "embers_beneath", gte: 30 }],
      fail: "The door is sealed by a cold, dead weight." }] },

  // ----------------------------------------------------------------
  // ----------------------------- Decor ----------------------------
  // ----------------------------------------------------------------
  counter: { name: "Counter", examine: "Polished by a thousand elbows.", draw: ["counter"], ops: [] },
  table: { name: "Table", examine: "Sturdy, if a little sticky.", draw: ["table"], ops: [] },
  crate: { name: "Crate", examine: "Packed with straw and odds and ends.", draw: ["crate"], ops: [] },
  barrel: { name: "Barrel", examine: "Something sloshes inside.", draw: ["barrel"], ops: [] },
  well: { name: "Well", examine: "The water smells of cold stone.", draw: ["well"], ops: [] },
  bush: { name: "Bush", examine: "Prickly and unremarkable.", draw: ["bush"], ops: [] },
  flowers: { name: "Flowers", examine: "A cheerful patch of colour.", draw: ["flowers"], block: false, ops: [] },
  wheat: { name: "Wheat", examine: "Swaying golden stalks.", draw: ["wheat"], block: false, ops: [] },
  statue: { name: "Statue", examine: "A founder of Brackenford, chin held high.", draw: ["statue"], ops: [] },
  torch: { name: "Torch", examine: "Pitch-soaked and crackling.", draw: ["torch"], ops: [] },
  rubble: { name: "Rubble", examine: "Loose stone from an old collapse.", draw: ["rubble"], block: false, ops: [] },
  tent: { name: "Tent", examine: "Patched hide on crooked poles.", draw: ["tent"], ops: [] },
  boat: { name: "Rowing boat", examine: "Bram's ferry, tied up and bobbing.", draw: ["boat"], ops: [] },
  // The winter ice road across Gull Sound (10.12a): a crossing marker on each shore, open only in winter.
  ice_road_west: { name: "Ice road", examine: "Stakes mark where the Sound freezes over to the east shore each winter.",
    draw: ["gate"], from: "w",
    ops: [{ id: "cross", label: "Cross the ice", kind: "climb", if: [{ season: "winter" }],
      fail: "The Sound is open water. It only freezes in winter." }] },
  ice_road_east: { name: "Ice road", examine: "Stakes mark where the Sound freezes over to Gullhaven each winter.",
    draw: ["gate"], from: "e",
    ops: [{ id: "cross", label: "Cross the ice", kind: "climb", if: [{ season: "winter" }],
      fail: "The Sound is open water. It only freezes in winter." }] },
  // Southfold's strongbox opens the vault once the mill is safe (The Mill of Southfold).
  southfold_strongbox: { name: "Strongbox", examine: "An iron-banded chest. It opens onto the same vault as any bank.",
    draw: ["crate"], mapIcon: "bank",
    ops: [{ id: "bank", label: "Bank", kind: "bank", if: [{ q: "mill_southfold", eq: 100 }],
      fail: "It's locked. Miller Aldo keeps the key." }] },
  // The Gullwing crosses Gull Sound once Pell has patched her (Crossing the Sound, stage 20).
  ferry_gullhaven: { name: "The Gullwing", examine: "Pell's ferry to Saltmere, moored off the pier.", draw: ["boat"],
    from: "s", ops: [{ id: "board", label: "Board", kind: "climb", if: [{ q: "crossing_sound", gte: 20 }],
      fail: "The Gullwing is holed below the waterline. Pell is trying to patch her." }] },
  ferry_saltmere: { name: "The Gullwing", examine: "Pell's ferry back to Gullhaven.", draw: ["boat"], from: "s",
    ops: [{ id: "board", label: "Board", kind: "climb", if: [{ q: "crossing_sound", gte: 20 }],
      fail: "The Gullwing is holed below the waterline. Pell is trying to patch her." }] },
  stalagmite: { name: "Stalagmite", examine: "Dripping, patient stone.", draw: ["stalagmite"], ops: [] },

  // ----------------------------------------------------------------
  // --------------------------- Signposts --------------------------
  // ----------------------------------------------------------------
  // One per road sign (placed from the map's place list); Examine reads the arms: "Direction: regions".
  sign_north_fork: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "North: Greyspire Quarry. North-west: Copperdell Mine and the Ashen Reach. North-east: the toll bridge to Gnarltooth Camp. East, over the river: Willowmere. South: Brackenford." },
  sign_north_gate: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "North-west: Copperdell Mine, then the Ashen Reach. West: Hollowpine Wood. North-east: Gnarltooth Camp. South: Brackenford." },
  sign_west_gate: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "West: Hollowpine Wood. North-west: Copperdell Mine. South-west: Gloomfen. South: Dunmoor Farm. East: Brackenford." },
  sign_east_gate: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "North-east, over the bridge: Willowmere, then Gnarltooth Camp. South-east: Gullhaven and Shellback Shore. West: Brackenford." },
  sign_south_gate: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "South: Dunmoor Farm. South-west: Gloomfen. West: Hollowpine Wood. South-east, over the ford: Shellback Shore. North: Brackenford." },
  sign_ford: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "East, over the ford: Shellback Shore. North-east: Gullhaven. West: Gloomfen, past Farmer Odo's. North: Brackenford." },
  sign_saltmere: { name: "Signpost", draw: ["sign"], ops: [],
    examine: "North: Amberwood. East: Stormcoast. South: Brinemarsh, and Starfall Crater beyond. West: Saltmere and the ferry." }
};
Data.gemTable = [[10, "uncut_sapphire"], [6, "uncut_emerald"], [3, "uncut_ruby"], [1, "uncut_diamond"]];
// ==== src/engine/data/npcs.js ====
// ----------------------------------------------------------------
// -------------------------- Data: npcs --------------------------
// ----------------------------------------------------------------
// Townsfolk (DESIGN.md section 15.1) and monsters (section 14.1). Op order is menu order.
// Humanoid draw = [kind, torso, legs, accessory colour, accessory]; monsters = [kind, body, detail].
Data.npcs = {
  // ----------------------------------------------------------------
  // -------------------------- Townsfolk ---------------------------
  // ----------------------------------------------------------------
  mirella: { name: "Mirella the Banker", examine: "She counts everything twice.", wander: 0,
    draw: ["human", "#2a2f4a", "#3a3f5a", "#e8c040", "chain"], mapIcon: "bank",
    ops: [{ id: "bank", label: "Bank", kind: "bank" }, { id: "talk", label: "Talk-to", kind: "talk", dialogue: "mirella" }] },
  tobin: { name: "Tobin", examine: "A shopkeeper with a little of everything.", wander: 0,
    draw: ["human", "#6a4a2a", "#3f2915", "#d8d0b8", "apron"], mapIcon: "general",
    barks: ["Tinderboxes! Hammers! Nets!", "Buying junk, selling better junk!", "Fair prices, mostly."],
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "tobin_general" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "tobin" }] },
  brenna: { name: "Brenna", examine: "Forge-scarred arms and a patient glare.", wander: 0,
    draw: ["smith", "#8a2a2a", "#3f2915", "#8a5a30", "apron"], mapIcon: "anvil",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "brenna" },
      { id: "trade", label: "Trade", kind: "shop", shop: "brenna_smithy" }] },
  hob: { name: "Hob", examine: "The innkeeper. Smells of onions and woodsmoke.", wander: 0,
    draw: ["human", "#d8d0b8", "#6a4a2a", "#ffffff", "cook_hat"], mapIcon: "shop",
    barks: ["Hot stew, fresh off the range!", "Mind the step, it's slippery.", "Trout's good today."],
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "hob_inn" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "hob" }] },
  ysolde: { name: "Ysolde", examine: "Her fingers are stained with dye and dust.", wander: 0,
    draw: ["robed", "#3f7a3a", "#e8c040"], mapIcon: "shop",
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "ysolde_goods" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "ysolde" }] },
  vael: { name: "Sergeant Vael", examine: "A drill sergeant with a voice like a gong.", wander: 0,
    draw: ["guard", "#8a2a2a", "#a3abb0"],
    barks: ["Guard up! Feet apart!", "Eat before you need to.", "Swing, step, breathe."],
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "vael" }] },
  marrick: { name: "Captain Marrick", examine: "The captain of the town watch. Tired eyes.", wander: 0,
    draw: ["guard", "#3a5fa0", "#a3abb0", "#c02838", "plume"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "marrick" },
      { id: "trade", label: "Trade", kind: "shop", shop: "marrick_armoury", if: [{ q: "gnarltooth_tolls", gte: 100 }] }] },
  odo: { name: "Farmer Odo", examine: "A farmer with a worried frown.", wander: 2,
    draw: ["human", "#6a4a2a", "#3a5fa0", "#e8c040", "straw_hat"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "odo" }] },
  hesk: { name: "Hesk the Tanner", examine: "Tough hands and a stronger nose.", wander: 0,
    draw: ["human", "#6a4a2a", "#3f2915", "#8a5a30", "apron"], mapIcon: "tanner",
    ops: [{ id: "tan", label: "Tan", kind: "make", station: "tanner" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "hesk" }] },
  dagny: { name: "Dagny", examine: "Coal dust in every wrinkle.", wander: 0,
    draw: ["smith", "#6a7078", "#3f2915", "#5a3c22", "apron"], mapIcon: "shop",
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "dagny_ores" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "dagny" }] },
  bram: { name: "Bram the Ferryman", examine: "He smells of lake weed and coin.", wander: 0,
    draw: ["human", "#3a5fa0", "#6a4a2a"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "bram" }] },
  pell: { name: "Pell", examine: "Hooks on her hat, scales on her boots.", wander: 0,
    draw: ["human", "#d8d0b8", "#3a5fa0", "#e8c040", "straw_hat"], mapIcon: "fish",
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "pell_tackle" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "pell" }] },
  ilvara: { name: "Ilvara the Sage", examine: "Her eyes reflect a fire that is not there.", wander: 0,
    draw: ["robed", "#5e3a96", "#e8c040", "#43286e", "hood"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "ilvara" }] },
  // Saltmere (DESIGN.md 15.1a)
  osric: { name: "Osric the Banker", examine: "He writes every coin into a salt-stained ledger.", wander: 0,
    draw: ["human", "#2f4a4a", "#3a3f5a", "#c9c9c4", "chain"], mapIcon: "bank",
    ops: [{ id: "bank", label: "Bank", kind: "bank" }, { id: "talk", label: "Talk-to", kind: "talk", dialogue: "osric" }] },
  corran: { name: "Harbourmaster Corran", examine: "A weathered sailor with a ledger under one arm.", wander: 0,
    draw: ["guard", "#2a4a6a", "#5a3c22", "#e8c040", "plume"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "corran" }] },
  greta: { name: "Greta", examine: "The landlady of the Salt Wife. Her stew could float a boat.", wander: 0,
    draw: ["human", "#8a3a2a", "#3f2915", "#ffffff", "cook_hat"], mapIcon: "shop",
    barks: ["Chowder's hot!", "Mind the salt on the floor.", "Swordfish steaks, fresh off the boats!"],
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "salt_wife_inn" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "greta" }] },
  vesna: { name: "Astronomer Vesna", examine: "Ink on her fingers, stars in her notes.", wander: 0,
    draw: ["robed", "#2a3a6a", "#c8e8ff", "#1a2a4a", "hood"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "vesna" }] },
  // Amberwood
  elin: { name: "Woodward Elin", examine: "She knows every tree in the wood by name.", wander: 0,
    draw: ["human", "#3f6a2a", "#5a3c22", "#2a4a1a", "hood"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "elin" }] },
  // Southfold (DESIGN.md 15.1a)
  aldo: { name: "Miller Aldo", examine: "Flour in his beard and worry in his eyes.", wander: 0,
    draw: ["human", "#d8d0b8", "#6a4a2a", "#c9a94a", "straw_hat"], mapIcon: "quest",
    ops: [{ id: "talk", label: "Talk-to", kind: "talk", dialogue: "aldo" }] },
  wyn: { name: "Wyn the Baker", examine: "Her apron has seen a thousand pies.", wander: 0,
    draw: ["human", "#c89048", "#3f2915", "#ffffff", "cook_hat"], mapIcon: "shop",
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "wyn_bakery", if: [{ q: "mill_southfold", eq: 100 }] },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "wyn" }] },
  maren: { name: "Maren", examine: "A fishmonger with forearms like rope.", wander: 0,
    draw: ["human", "#3a6a7a", "#3f2915", "#d8d0b8", "apron"], mapIcon: "fish",
    ops: [{ id: "trade", label: "Trade", kind: "shop", shop: "maren_fish" },
      { id: "talk", label: "Talk-to", kind: "talk", dialogue: "maren" }] },

  // ----------------------------------------------------------------
  // --------------------------- Monsters ---------------------------
  // ----------------------------------------------------------------
  chicken: { name: "Chicken", examine: "Plump, loud and suspicious of you.", draw: ["chicken", "#f0ece0", "#d83a2a"],
    barks: ["Bwaak!", "Bok bok bok.", "Bwaaak bok!"], ops: [],
    combat: { lvl: 1, hp: 3, att: 1, str: 1, def: 1, attB: 0, defB: 0, maxHit: 1, speed: 4, aggro: 0,
      respawn: 25, drops: "chicken" } },
  cow: { name: "Cow", examine: "Placid, and full of beef.", draw: ["cow", "#f0ece0", "#2b2118"],
    barks: ["Moo.", "Mooo! Moo.", "Mrrooo."], ops: [],
    combat: { lvl: 2, hp: 8, att: 1, str: 1, def: 1, attB: 0, defB: 0, maxHit: 1, speed: 4, aggro: 0,
      respawn: 30, drops: "cow" } },
  goblin: { name: "Goblin", examine: "Small, green and greedy.", draw: ["goblin", "#5a9a3a", "#6a4a2a"],
    barks: ["Shinies! Give shinies!", "Gnarltooth takes what it wants!", "Toll! Pay the toll!"], ops: [],
    combat: { lvl: 2, hp: 5, att: 1, str: 1, def: 1, attB: -25, defB: 0, maxHit: 1, speed: 4, aggro: 0,
      respawn: 30, drops: "goblin" } },
  goblin_brute: { name: "Goblin brute", examine: "A goblin who ate the other goblins' dinners.",
    draw: ["goblin", "#3f6a2a", "#6d6a66"], ops: [],
    combat: { lvl: 11, hp: 16, att: 9, str: 9, def: 8, attB: 5, defB: 5, maxHit: 3, speed: 5, aggro: 0,
      respawn: 40, drops: "goblin_brute" } },
  shellback_crab: { name: "Shellback crab", examine: "Its shell is crusted with barnacles.",
    draw: ["crab", "#c0503a", "#7e2a24"], ops: [],
    combat: { lvl: 15, hp: 60, att: 1, str: 1, def: 1, attB: -30, defB: 0, maxHit: 1, speed: 4, aggro: 2, always: true,
      respawn: 20, drops: "shellback_crab" } },
  cave_spider: { name: "Cave spider", examine: "Too many legs, all of them quick.", draw: ["spider", "#3a3430", "#c02838"],
    ops: [],
    combat: { lvl: 15, hp: 18, att: 14, str: 12, def: 10, attB: 10, defB: 5, maxHit: 3, speed: 4, aggro: 4,
      respawn: 30, drops: "cave_spider" } },
  skeleton: { name: "Skeleton", examine: "It rattles with grim purpose.", draw: ["skeleton", "#e8e0c8", "#5a5450"], ops: [],
    combat: { lvl: 22, hp: 26, att: 20, str: 18, def: 16, attB: 10, defB: 15, maxHit: 4, speed: 5, aggro: 4,
      respawn: 40, drops: "skeleton" } },
  bandit: { name: "Bandit", examine: "Hooded, armed and short on manners.",
    draw: ["human", "#5a3c22", "#3f2915", "#2a2522", "hood"], ops: [],
    combat: { lvl: 26, hp: 30, att: 24, str: 22, def: 18, attB: 15, defB: 15, maxHit: 5, speed: 4, aggro: 4,
      respawn: 50, drops: "bandit" } },
  skarg: { name: "Skarg the Warchief", examine: "The Gnarltooth warchief, all tusk and temper.", scale: 2,
    draw: ["goblin", "#4b7a2a", "#8a2a2a"], ops: [],
    combat: { lvl: 32, hp: 55, att: 22, str: 24, def: 20, attB: 15, defB: 15, maxHit: 5, speed: 5, aggro: 4,
      always: true, respawn: 50, drops: "skarg", boss: true,
      special: { k: "rally", hp: 28, heal: 14, msg: "Skarg bellows for help, and his warband's cheers steady him!" } } },
  ashen_wolf: { name: "Ashen wolf", examine: "Grey fur, ash-dusted, hungry.", draw: ["wolf", "#6b6660", "#4e4a45"], ops: [],
    combat: { lvl: 34, hp: 36, att: 30, str: 28, def: 25, attB: 20, defB: 15, maxHit: 6, speed: 4, aggro: 4,
      respawn: 50, drops: "ashen_wolf" } },
  tunnel_lurker: { name: "Tunnel lurker", examine: "Pale, eyeless and very patient.", draw: ["lurker", "#4a4440", "#c9c9c4"],
    ops: [],
    combat: { lvl: 38, hp: 41, att: 33, str: 32, def: 29, attB: 20, defB: 25, maxHit: 7, speed: 4, aggro: 4,
      respawn: 50, drops: "tunnel_lurker" } },
  hill_ogre: { name: "Hill ogre", examine: "Big, slow, and holding a tree trunk.", draw: ["ogre", "#8a7a4a", "#5a3c22"], ops: [],
    combat: { lvl: 48, hp: 62, att: 37, str: 42, def: 30, attB: 15, defB: 10, maxHit: 9, speed: 6, aggro: 0,
      respawn: 60, drops: "hill_ogre" } },
  ember_imp: { name: "Ember imp", examine: "A spark with a grudge.", draw: ["imp", "#b8433a", "#ffb050"], ops: [],
    combat: { lvl: 52, hp: 54, att: 45, str: 43, def: 42, attB: 30, defB: 30, maxHit: 8, speed: 4, aggro: 4,
      respawn: 50, drops: "ember_imp" } },
  magma_golem: { name: "Magma golem", examine: "Molten rock, stubbornly walking.", draw: ["golem", "#4e4a45", "#ffb050"],
    ops: [],
    combat: { lvl: 68, hp: 80, att: 52, str: 58, def: 52, attB: 30, defB: 60, maxHit: 12, speed: 6, aggro: 4,
      respawn: 80, drops: "magma_golem" } },
  smoulderjaw: { name: "Smoulderjaw", examine: "An ember wyrm, coiled in its own heat.", scale: 2, wander: 0,
    draw: ["wyrm", "#7e2a24", "#ffb050"], ops: [],
    combat: { lvl: 86, hp: 200, att: 55, str: 60, def: 44, attB: 20, defB: 10, maxHit: 8, speed: 5, aggro: 4,
      always: true, respawn: 200, drops: "smoulderjaw", boss: true,
      special: { k: "breath", every: 12, warn: 3, min: 12, max: 20, ward: "emberward", arena: "lair", reset: 10,
        enterMsg: "Smoulderjaw uncoils from the embers.",
        enrage: { hp: 65, every: 8, speed: 4, msg: "Smoulderjaw's scales blaze white-hot!" } } } },

  // ----------------------------------------------------------------
  // ------------------ Across the Sound monsters -------------------
  // ----------------------------------------------------------------
  mill_rat: { name: "Mill rat", examine: "Fat on Aldo's flour.", draw: ["lurker", "#7a6a5a", "#c9a0a0"], ops: [],
    combat: { lvl: 4, hp: 6, att: 3, str: 3, def: 2, attB: 0, defB: 0, maxHit: 1, speed: 4, aggro: 0,
      respawn: 25, drops: "mill_rat" } },
  canyon_jackal: { name: "Canyon jackal", examine: "Lean, quick and always hungry.", draw: ["wolf", "#c09050", "#7a5530"],
    ops: [],
    combat: { lvl: 18, hp: 22, att: 16, str: 15, def: 12, attB: 10, defB: 5, maxHit: 3, speed: 4, aggro: 0,
      respawn: 30, drops: "canyon_jackal" } },
  drowned_soldier: { name: "Drowned soldier", examine: "Weed in its ribs, a rusted oath in its grip.",
    draw: ["skeleton", "#9aa890", "#3f5a4a"], ops: [],
    combat: { lvl: 40, hp: 44, att: 34, str: 33, def: 30, attB: 20, defB: 20, maxHit: 7, speed: 5, aggro: 4,
      respawn: 50, drops: "drowned_soldier" } },
  mire_witch: { name: "Mire witch", examine: "She hums to the frogs. The frogs hum back.",
    draw: ["robed", "#3a4a2a", "#7a9a4a", "#2a3a1a", "hood"], ops: [],
    combat: { lvl: 46, hp: 48, att: 40, str: 34, def: 30, attB: 25, defB: 20, maxHit: 8, speed: 5, aggro: 4,
      respawn: 50, drops: "mire_witch" } },
  canyon_harpy: { name: "Canyon harpy", examine: "All talons and shrieking.", draw: ["imp", "#b08050", "#e8d0a0"], ops: [],
    combat: { lvl: 50, hp: 52, att: 44, str: 42, def: 36, attB: 25, defB: 20, maxHit: 8, speed: 4, aggro: 4,
      respawn: 50, drops: "canyon_harpy" } },
  sand_wyrmling: { name: "Sand wyrmling", examine: "A young wyrm, sand-coloured and furious.",
    draw: ["wyrm", "#d0a050", "#7e3a1a"], ops: [],
    combat: { lvl: 64, hp: 74, att: 50, str: 54, def: 48, attB: 25, defB: 40, maxHit: 11, speed: 5, aggro: 4,
      respawn: 70, drops: "sand_wyrmling" } },
  mire_toad: { name: "Mire toad", examine: "It croaks in a voice deeper than yours.", draw: ["crab", "#5a7a3a", "#c8c060"], ops: [],
    combat: { lvl: 24, hp: 28, att: 20, str: 18, def: 18, attB: 10, defB: 15, maxHit: 4, speed: 5, aggro: 0,
      respawn: 30, drops: "mire_toad" } },
  thornback_boar: { name: "Thornback boar", examine: "Bristles like briars, temper like a bonfire.",
    draw: ["cow", "#4a3020", "#c0a080"], ops: [],
    combat: { lvl: 40, hp: 46, att: 34, str: 36, def: 30, attB: 20, defB: 25, maxHit: 7, speed: 5, aggro: 0,
      respawn: 45, drops: "thornback_boar" } },
  bog_wraith: { name: "Bog wraith", examine: "Marsh mist with a face in it.", draw: ["imp", "#7a8a7a", "#c8e0c0"], ops: [],
    combat: { lvl: 56, hp: 58, att: 48, str: 44, def: 40, attB: 30, defB: 30, maxHit: 9, speed: 4, aggro: 4,
      respawn: 55, drops: "bog_wraith" } },
  bark_stalker: { name: "Bark stalker", examine: "It looks like a fallen branch until it moves.",
    draw: ["spider", "#5a4028", "#c08a30"], ops: [],
    combat: { lvl: 58, hp: 62, att: 50, str: 46, def: 44, attB: 30, defB: 35, maxHit: 9, speed: 4, aggro: 4,
      respawn: 55, drops: "bark_stalker" } },
  crater_sentinel: { name: "Crater sentinel", examine: "Star-stone, set walking by something old.",
    draw: ["golem", "#6a7a8a", "#9fd6ff"], ops: [],
    combat: { lvl: 72, hp: 86, att: 56, str: 60, def: 56, attB: 35, defB: 55, maxHit: 12, speed: 5, aggro: 4,
      respawn: 80, drops: "crater_sentinel" } },
  shardback_golem: { name: "Shardback golem", examine: "Crystal spines grind along its back.",
    draw: ["golem", "#3a4a5a", "#c0e8ff"], ops: [],
    combat: { lvl: 78, hp: 96, att: 60, str: 66, def: 62, attB: 35, defB: 65, maxHit: 13, speed: 6, aggro: 4,
      respawn: 90, drops: "shardback_golem" } },
  hollow_knight: { name: "Hollow knight", examine: "Empty armour that still remembers its oath.",
    draw: ["guard", "#2a2a30", "#5a5a6a", "#c8e8ff", "plume"], ops: [],
    combat: { lvl: 84, hp: 98, att: 64, str: 66, def: 62, attB: 40, defB: 60, maxHit: 14, speed: 5, aggro: 4,
      respawn: 90, drops: "hollow_knight" } },
  hollow_king: { name: "The Hollow King", examine: "A crowned shadow on a cold throne.", scale: 2, wander: 0,
    draw: ["skeleton", "#3a3530", "#c8e8ff"], ops: [],
    combat: { lvl: 99, hp: 380, att: 96, str: 90, def: 76, attB: 40, defB: 50, maxHit: 26, speed: 4, aggro: 4,
      respawn: 200, drops: "hollow_king", boss: true,
      special: { k: "rally", hp: 140, heal: 80, msg: "The Hollow King raises his blade, and the keep's dead stir to steady him!" } } }
};

// ----------------------------------------------------------------
// ------------------------------ Pets ----------------------------
// ----------------------------------------------------------------
// Combat pets (DESIGN.md section 10.16), found only on boss kills: each kill of `from` rolls 1 in `rate`
// for each of its pets the player doesn't own. A pet only fights, with its own stats (never the player's):
// att and maxHit at pet level 1, rising with its level. It takes no tile and is never attacked.
// name/draw: the young form (drawn at two-thirds size); grows: the adult (level 7) and mythic (level 14) forms,
// drawn full size. dex: the pet's dex page; facts[i] unlocks at stage i. perk: a Rules.PET_PERKS id.
Data.pets = {
  // Smoulderjaw, in the Deeps.
  ember_whelp: { name: "Ember whelp", examine: "Warm to hold. Too warm, sometimes.", draw: ["wyrm", "#9a3a2a", "#ffc060"],
    grows: [{ name: "Ember drake", draw: ["wyrm", "#b4402a", "#ffd070"] },
      { name: "Ember wyrm", draw: ["wyrm", "#d8582a", "#fff0a0"] }],
    from: "smoulderjaw", rate: 200, att: 20, maxHit: 1, perk: "scorch",
    dex: { kind: "Fire wyrm", habitat: "Smoulderjaw's Lair", likes: "Warm coals and shiny buttons",
      size: ["9 in", "3 ft", "7 ft"], weight: ["4 lb", "60 lb", "400 lb"],
      facts: ["Whelps hiccup sparks when they're happy. Keep it away from your bedding.",
        "A drake's scales cool to black while it sleeps and glow again just before it wakes.",
        "Ember wyrms remember every warm place they have ever slept, and try to go back."] } },
  cinder_imp: { name: "Cinder imp", examine: "A spark that decided to stay.", draw: ["imp", "#c84a30", "#ffd070"],
    grows: [{ name: "Cinder fiend", draw: ["imp", "#d2502a", "#ffe080"] },
      { name: "Inferno fiend", draw: ["imp", "#ff6a2a", "#fff4b0"] }],
    from: "smoulderjaw", rate: 200, att: 20, maxHit: 1, perk: "flurry",
    dex: { kind: "Fire imp", habitat: "The Deeps", likes: "Matches and mischief",
      size: ["1 ft", "2 ft 6 in", "4 ft"], weight: ["2 lb", "18 lb", "45 lb"],
      facts: ["Imps can't sit still. This one has tried to set your boots alight twice already.",
        "A cinder fiend juggles live coals to keep its hands warm.",
        "An inferno fiend's laugh crackles like a log fire: the bigger the fire, the louder it laughs."] } },
  magmaling: { name: "Magmaling", examine: "A pebble of the deep fire, cooling slowly.", draw: ["golem", "#5a4a40", "#ff9040"],
    grows: [{ name: "Magma brute", draw: ["golem", "#6a4a3a", "#ff8a30"] },
      { name: "Magma colossus", draw: ["golem", "#7a3a2a", "#ffc040"] }],
    from: "smoulderjaw", rate: 200, att: 20, maxHit: 1, perk: "guard",
    dex: { kind: "Rock elemental", habitat: "The Golem Forge", likes: "Sitting very still near furnaces",
      size: ["1 ft", "4 ft", "8 ft"], weight: ["30 lb", "600 lb", "2 tons"],
      facts: ["A magmaling is born when a drop of the deep fire cools around a heartbeat.",
        "Brutes grow by eating gravel. They are not fussy about whose gravel.",
        "A colossus is warm enough to cook on, if you can get it to hold still."] } },
  ash_pup: { name: "Ash pup", examine: "It rolls in cinders and calls it a bath.", draw: ["wolf", "#8a847c", "#5a5650"],
    grows: [{ name: "Ash hound", draw: ["wolf", "#7a746c", "#4a4640"] },
      { name: "Cinder wolf", draw: ["wolf", "#5a5450", "#ff9a40"] }],
    from: "smoulderjaw", rate: 200, att: 20, maxHit: 1, perk: "quick",
    dex: { kind: "Ash wolf", habitat: "The Ashen Reach", likes: "Rolling in cinders",
      size: ["1 ft", "2 ft 6 in", "4 ft"], weight: ["9 lb", "70 lb", "160 lb"],
      facts: ["Ash pups sneeze little grey clouds. It is the most adorable thing in the Deeps.",
        "An ash hound can follow a trail through smoke that would blind a person.",
        "Cinder wolves run so fast that the embers in their fur flare as they go."] } },
  // The Hollow King, in Duskhollow Keep.
  crownling: { name: "Crownling", examine: "A small shadow in a smaller crown.", draw: ["skeleton", "#4a4440", "#d8f0ff"],
    grows: [{ name: "Crowned shade", draw: ["skeleton", "#3a3640", "#b8d8ff"] },
      { name: "Hollow regent", draw: ["skeleton", "#2a2a36", "#e0f4ff"] }],
    from: "hollow_king", rate: 200, att: 50, maxHit: 5, perk: "dread",
    dex: { kind: "Royal shade", habitat: "Duskhollow Keep", likes: "Being bowed to",
      size: ["1 ft", "4 ft", "6 ft"], weight: ["1 lb", "5 lb", "None (it floats)"],
      facts: ["Crownlings insist on being carried. They are very light and very bossy.",
        "A crowned shade practises its decrees on mice. The mice do not listen.",
        "A hollow regent's crown is cold enough to frost the air around it, even in summer."] } },
  grave_wisp: { name: "Grave wisp", examine: "A cold little light that hums old hymns.", draw: ["imp", "#8a9aa8", "#e8f4ff"],
    grows: [{ name: "Grave spirit", draw: ["imp", "#9aaab8", "#f0f8ff"] },
      { name: "Lantern saint", draw: ["imp", "#b8c8d8", "#fffbe0"] }],
    from: "hollow_king", rate: 200, att: 50, maxHit: 5, perk: "mend",
    dex: { kind: "Spirit light", habitat: "Duskhollow Ruins", likes: "Old hymns and candlelight",
      size: ["6 in", "2 ft", "4 ft"], weight: ["None", "None", "None"],
      facts: ["Wisps hum when someone near them is hurt, and glow a little warmer.",
        "A grave spirit can't stand a tune sung off-key. It will hum the right notes, loudly.",
        "Lantern saints are said to have guided lost knights home long after the keep fell."] } },
  bone_hound: { name: "Bone hound", examine: "It fetches. You'd rather not ask what.", draw: ["wolf", "#e0d8c0", "#6a6458"],
    grows: [{ name: "Bone mastiff", draw: ["wolf", "#d8d0b8", "#5a5448"] },
      { name: "Ossuary warhound", draw: ["wolf", "#f0e8d0", "#7ab0e0"] }],
    from: "hollow_king", rate: 200, att: 50, maxHit: 5, perk: "gore",
    dex: { kind: "Skeletal hound", habitat: "Duskhollow Ruins", likes: "Fetch, with its own bones",
      size: ["1 ft", "3 ft", "5 ft"], weight: ["4 lb", "40 lb", "90 lb"],
      facts: ["Bone hounds bury things. Mostly their own tails.",
        "A bone mastiff rattles its whole body like a happy dog shaking off water.",
        "Ossuary warhounds once guarded the Hollow King's crypt, and still growl at locked doors."] } },
  gravecrawler: { name: "Gravecrawler", examine: "Eight legs, one tiny crown of frost.", draw: ["spider", "#3a3a44", "#a8d8ff"],
    grows: [{ name: "Gravestalker", draw: ["spider", "#34343e", "#90c8ff"] },
      { name: "Frostweb matriarch", draw: ["spider", "#2a2a38", "#d0f0ff"] }],
    from: "hollow_king", rate: 200, att: 50, maxHit: 5, perk: "keen",
    dex: { kind: "Crypt spider", habitat: "Duskhollow Keep", likes: "Cold corners and quiet",
      size: ["2 in", "1 ft 6 in", "4 ft"], weight: ["A tenth of an ounce", "6 lb", "70 lb"],
      facts: ["Its crown of frost is really eight frozen dewdrops. It polishes them every morning.",
        "Gravestalkers spin webs so cold that dust freezes in them like little stars.",
        "A frostweb matriarch can hear a heartbeat through a stone wall."] } }
};
// ==== src/engine/data/drops.js ====
// ----------------------------------------------------------------
// ------------------------- Data: drops --------------------------
// ----------------------------------------------------------------
// One table per monster, id = npc id (DESIGN.md section 14.2). main weights sum to 128;
// null rows are "nothing". Quest drops are gated so a lost one can be earned again.
Data.drops = {
  chicken: { always: [["raw_chicken", 1, 1], ["feather", 5, 10]] },
  cow: { always: [["cowhide", 1, 1], ["raw_beef", 1, 1]] },
  goblin: { main: [[64, "coins", 1, 12], [8, "copper_ore", 1, 1], [8, "tin_ore", 1, 1], [10, "feather", 5, 10],
    [5, "bronze_sword", 1, 1], [5, "bronze_helm", 1, 1], [28, null, 0, 0]], gem: 128 },
  goblin_brute: { main: [[60, "coins", 5, 30], [12, "iron_ore", 1, 1], [12, "raw_beef", 1, 1], [6, "bronze_shield", 1, 1],
    [5, "iron_sword", 1, 1], [5, "iron_helm", 1, 1], [28, null, 0, 0]], gem: 96 },
  shellback_crab: { main: [[32, "coins", 1, 8], [16, "raw_sardine", 1, 1], [80, null, 0, 0]], gem: 256 },
  cave_spider: { main: [[40, "coins", 3, 20], [16, "coal", 1, 1], [72, null, 0, 0]], gem: 64 },
  skeleton: { main: [[50, "coins", 10, 40], [12, "iron_ore", 2, 2], [10, "coal", 1, 1], [6, "iron_sword", 1, 1],
    [3, "steel_sword", 1, 1], [3, "steel_helm", 1, 1], [44, null, 0, 0]], gem: 64 },
  bandit: { main: [[64, "coins", 20, 80], [16, "trout", 1, 1], [10, "salmon", 1, 1], [6, "steel_sword", 1, 1],
    [3, "steel_shield", 1, 1], [1, "cobalt_sword", 1, 1], [28, null, 0, 0]], gem: 48 },
  // Skarg keeps spawning until the hand-in (a lost tusk can be won again); his purse and cleaver come with
  // the tusk only.
  skarg: { always: [["coins", 250, 250, [{ q: "gnarltooth_tolls", gte: 30, lt: 100 }, { not: { owns: "skarg_tusk" } }]],
    ["skarg_tusk", 1, 1, [{ q: "gnarltooth_tolls", gte: 30, lt: 100 }, { not: { owns: "skarg_tusk" } }]],
    ["skarg_cleaver", 1, 1, [{ q: "gnarltooth_tolls", gte: 30, lt: 100 }, { not: { owns: "skarg_tusk" } }]]] },
  ashen_wolf: { always: [["wolf_pelt", 1, 1]], gem: 64 },
  tunnel_lurker: { main: [[50, "coins", 30, 120], [20, "coal", 2, 4], [16, "cobalt_ore", 1, 1], [4, "verdite_ore", 1, 1],
    [3, "cobalt_helm", 1, 1], [35, null, 0, 0]], gem: 48 },
  hill_ogre: { main: [[64, "coins", 50, 200], [16, "maple_logs", 5, 10], [16, "lobster", 1, 1], [8, "yew_logs", 2, 5],
    [3, "cobalt_shield", 1, 1], [1, "verdite_sword", 1, 1], [20, null, 0, 0]], gem: 32 },
  ember_imp: { main: [[60, "coins", 60, 250], [24, "coal", 3, 6], [8, "verdite_ore", 1, 1], [4, "emberite_ore", 1, 1],
    [32, null, 0, 0]], gem: 32 },
  magma_golem: { main: [[60, "coins", 100, 400], [12, "emberite_ore", 1, 2], [10, "shark", 1, 1], [8, "verdite_bar", 1, 1],
    [4, "cobalt_greaves", 1, 1], [1, "emberite_helm", 1, 1], [33, null, 0, 0]], gem: 24 },
  smoulderjaw: {
    always: [["coins", 1000, 3000],
      ["ember_heart", 1, 1, [{ q: "embers_beneath", gte: 30, lt: 100 }, { not: { owns: "ember_heart" } }]]],
    main: [[36, "emberite_bar", 2, 4], [30, "emberite_ore", 4, 8], [30, "shark", 3, 5], [12, "uncut_diamond", 1, 2],
      [12, "verdite_breastplate", 1, 1], [8, "emberite_shield", 1, 1]],
    unique: [["cinderfang", 40], ["smoulderfang", 60]] },
  // Across the Sound (14.2a)
  mill_rat: { main: [[64, "coins", 1, 6], [64, null, 0, 0]] },
  canyon_jackal: { main: [[48, "coins", 4, 18], [20, "raw_beef", 1, 1], [60, null, 0, 0]], gem: 128 },
  drowned_soldier: { main: [[50, "coins", 30, 110], [14, "raw_swordfish", 1, 1], [8, "steel_sword", 1, 1],
    [6, "steel_shield", 1, 1], [4, "cobalt_helm", 1, 1], [2, "cobalt_sword", 1, 1], [44, null, 0, 0]], gem: 48 },
  mire_witch: { main: [[56, "coins", 40, 140], [16, "uncut_sapphire", 1, 1], [8, "uncut_emerald", 1, 1],
    [4, "emerald_amulet", 1, 1], [44, null, 0, 0]], gem: 32 },
  canyon_harpy: { always: [["feather", 10, 30]], main: [[56, "coins", 50, 180], [12, "gold_ore", 1, 2],
    [8, "uncut_ruby", 1, 1], [52, null, 0, 0]], gem: 32 },
  sand_wyrmling: { main: [[56, "coins", 80, 300], [16, "gold_ore", 2, 4], [10, "uncut_sunstone", 1, 1],
    [6, "verdite_ore", 1, 2], [40, null, 0, 0]], gem: 24 },
  mire_toad: { main: [[56, "coins", 8, 30], [24, "salt", 2, 5], [48, null, 0, 0]], gem: 128 },
  thornback_boar: { always: [["raw_beef", 1, 1]], main: [[56, "coins", 20, 70], [16, "maple_logs", 2, 4], [56, null, 0, 0]],
    gem: 96 },
  bog_wraith: { main: [[56, "coins", 60, 200], [16, "salt", 5, 10], [10, "uncut_emerald", 1, 1], [6, "cobalt_greaves", 1, 1],
    [2, "verdite_helm", 1, 1], [38, null, 0, 0]], gem: 32 },
  bark_stalker: { main: [[56, "coins", 60, 220], [20, "yew_logs", 2, 4], [10, "amber_sap", 1, 1], [4, "verdite_shield", 1, 1],
    [38, null, 0, 0]], gem: 32 },
  crater_sentinel: { main: [[60, "coins", 120, 420], [14, "starmetal_ore", 1, 1], [10, "coal", 5, 10], [6, "verdite_bar", 1, 2],
    [2, "emberite_helm", 1, 1], [36, null, 0, 0]], gem: 24 },
  shardback_golem: { main: [[60, "coins", 150, 500], [16, "starmetal_ore", 1, 2], [10, "shark", 1, 1], [6, "emberite_bar", 1, 1],
    [2, "starsteel_helm", 1, 1], [34, null, 0, 0]], gem: 20 },
  hollow_knight: { main: [[56, "coins", 150, 500], [14, "starmetal_ore", 1, 1], [10, "stormray", 1, 1], [6, "emberite_bar", 1, 2],
    [4, "starsteel_shield", 1, 1], [38, null, 0, 0]], gem: 20 },
  // The King stays on his throne (re-challengeable); his seal drops only while the quest wants it.
  hollow_king: {
    always: [["coins", 2000, 5000],
      ["kings_seal", 1, 1, [{ q: "hollow_king", gte: 20, lt: 100 }, { not: { owns: "kings_seal" } }]]],
    main: [[36, "starsteel_bar", 2, 4], [30, "starmetal_ore", 4, 8], [30, "stormray", 3, 5], [16, "uncut_diamond", 1, 2],
      [10, "starsteel_breastplate", 1, 1], [6, "starsteel_greatsword", 1, 1]],
    unique: [["hollow_crown", 80]] }
};
// ==== src/engine/data/recipes.js ====
// ----------------------------------------------------------------
// ------------------- Data: recipes and stations -----------------
// ----------------------------------------------------------------
// Smelting, smithing, cooking, firemaking, tanning and crafting (DESIGN.md section 13).
// Smith level = metal base + kind offset; smith XP = bars x per-bar XP. Light and burn have
// no output item, so they carry a name for the make sheet and the skill guide.
Data.recipes = {
  // ----------------------------------------------------------------
  // --------------------------- Smelting ---------------------------
  // ----------------------------------------------------------------
  smelt_bronze: { group: "smelt", skill: "smithing", lvl: 1, xp: 6, at: ["furnace"], tools: [],
    in: [["copper_ore", 1], ["tin_ore", 1]], out: [["bronze_bar", 1]], ticks: 4, msg: "You smelt a bronze bar." },
  smelt_iron: { group: "smelt", skill: "smithing", lvl: 15, xp: 50, at: ["furnace"], tools: [],
    in: [["iron_ore", 1]], out: [["iron_bar", 1]], ticks: 1, full: 45, fail: [], failMsg: "The iron crumbles in the heat.",
    msg: "You smelt an iron bar." },
  smelt_steel: { group: "smelt", skill: "smithing", lvl: 30, xp: 17.5, at: ["furnace"], tools: [],
    in: [["iron_ore", 1], ["coal", 2]], out: [["steel_bar", 1]], ticks: 4, msg: "You smelt a steel bar." },
  smelt_gold: { group: "smelt", skill: "smithing", lvl: 40, xp: 22.5, at: ["furnace"], tools: [],
    in: [["gold_ore", 1]], out: [["gold_bar", 1]], ticks: 4, msg: "You smelt a gold bar." },
  smelt_cobalt: { group: "smelt", skill: "smithing", lvl: 45, xp: 30, at: ["furnace"], tools: [],
    in: [["cobalt_ore", 1], ["coal", 4]], out: [["cobalt_bar", 1]], ticks: 4, msg: "You smelt a cobalt bar." },
  smelt_verdite: { group: "smelt", skill: "smithing", lvl: 60, xp: 37.5, at: ["furnace"], tools: [],
    in: [["verdite_ore", 1], ["coal", 6]], out: [["verdite_bar", 1]], ticks: 4, msg: "You smelt a verdite bar." },
  smelt_emberite: { group: "smelt", skill: "smithing", lvl: 75, xp: 50, at: ["furnace"], tools: [],
    in: [["emberite_ore", 1], ["coal", 8]], out: [["emberite_bar", 1]], ticks: 4, msg: "You smelt an emberite bar." },

  // ----------------------------------------------------------------
  // --------------------------- Smithing ---------------------------
  // ----------------------------------------------------------------
  smith_bronze_axe: { group: "smith", skill: "smithing", lvl: 1, xp: 12.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 1]], out: [["bronze_axe", 1]], ticks: 5, msg: "You hammer out a bronze axe." },
  smith_bronze_dagger: { group: "smith", skill: "smithing", lvl: 2, xp: 12.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 1]], out: [["bronze_dagger", 1]], ticks: 5, msg: "You hammer out a bronze dagger." },
  smith_bronze_sword: { group: "smith", skill: "smithing", lvl: 3, xp: 12.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 1]], out: [["bronze_sword", 1]], ticks: 5, msg: "You hammer out a bronze sword." },
  smith_bronze_pickaxe: { group: "smith", skill: "smithing", lvl: 5, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 2]], out: [["bronze_pickaxe", 1]], ticks: 5, msg: "You hammer out a bronze pickaxe." },
  smith_bronze_helm: { group: "smith", skill: "smithing", lvl: 7, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 2]], out: [["bronze_helm", 1]], ticks: 5, msg: "You hammer out a bronze helm." },
  smith_bronze_mace: { group: "smith", skill: "smithing", lvl: 9, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 2]], out: [["bronze_mace", 1]], ticks: 5, msg: "You hammer out a bronze mace." },
  smith_bronze_shield: { group: "smith", skill: "smithing", lvl: 11, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 3]], out: [["bronze_shield", 1]], ticks: 5, msg: "You hammer out a bronze shield." },
  smith_bronze_greatsword: { group: "smith", skill: "smithing", lvl: 13, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 3]], out: [["bronze_greatsword", 1]], ticks: 5, msg: "You hammer out a bronze greatsword." },
  smith_bronze_greaves: { group: "smith", skill: "smithing", lvl: 15, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 3]], out: [["bronze_greaves", 1]], ticks: 5, msg: "You hammer out bronze greaves." },
  smith_bronze_breastplate: { group: "smith", skill: "smithing", lvl: 19, xp: 62.5, at: ["anvil"], tools: ["hammer"],
    in: [["bronze_bar", 5]], out: [["bronze_breastplate", 1]], ticks: 5, msg: "You hammer out a bronze breastplate." },
  smith_iron_axe: { group: "smith", skill: "smithing", lvl: 15, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 1]], out: [["iron_axe", 1]], ticks: 5, msg: "You hammer out an iron axe." },
  smith_iron_dagger: { group: "smith", skill: "smithing", lvl: 16, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 1]], out: [["iron_dagger", 1]], ticks: 5, msg: "You hammer out an iron dagger." },
  smith_iron_sword: { group: "smith", skill: "smithing", lvl: 17, xp: 25, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 1]], out: [["iron_sword", 1]], ticks: 5, msg: "You hammer out an iron sword." },
  smith_iron_pickaxe: { group: "smith", skill: "smithing", lvl: 19, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 2]], out: [["iron_pickaxe", 1]], ticks: 5, msg: "You hammer out an iron pickaxe." },
  smith_iron_helm: { group: "smith", skill: "smithing", lvl: 21, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 2]], out: [["iron_helm", 1]], ticks: 5, msg: "You hammer out an iron helm." },
  smith_iron_mace: { group: "smith", skill: "smithing", lvl: 23, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 2]], out: [["iron_mace", 1]], ticks: 5, msg: "You hammer out an iron mace." },
  smith_iron_shield: { group: "smith", skill: "smithing", lvl: 25, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 3]], out: [["iron_shield", 1]], ticks: 5, msg: "You hammer out an iron shield." },
  smith_iron_greatsword: { group: "smith", skill: "smithing", lvl: 27, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 3]], out: [["iron_greatsword", 1]], ticks: 5, msg: "You hammer out an iron greatsword." },
  smith_iron_greaves: { group: "smith", skill: "smithing", lvl: 29, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 3]], out: [["iron_greaves", 1]], ticks: 5, msg: "You hammer out iron greaves." },
  smith_iron_breastplate: { group: "smith", skill: "smithing", lvl: 33, xp: 125, at: ["anvil"], tools: ["hammer"],
    in: [["iron_bar", 5]], out: [["iron_breastplate", 1]], ticks: 5, msg: "You hammer out an iron breastplate." },
  smith_steel_axe: { group: "smith", skill: "smithing", lvl: 30, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 1]], out: [["steel_axe", 1]], ticks: 5, msg: "You hammer out a steel axe." },
  smith_steel_dagger: { group: "smith", skill: "smithing", lvl: 31, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 1]], out: [["steel_dagger", 1]], ticks: 5, msg: "You hammer out a steel dagger." },
  smith_steel_sword: { group: "smith", skill: "smithing", lvl: 32, xp: 37.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 1]], out: [["steel_sword", 1]], ticks: 5, msg: "You hammer out a steel sword." },
  smith_steel_pickaxe: { group: "smith", skill: "smithing", lvl: 34, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 2]], out: [["steel_pickaxe", 1]], ticks: 5, msg: "You hammer out a steel pickaxe." },
  smith_steel_helm: { group: "smith", skill: "smithing", lvl: 36, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 2]], out: [["steel_helm", 1]], ticks: 5, msg: "You hammer out a steel helm." },
  smith_steel_mace: { group: "smith", skill: "smithing", lvl: 38, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 2]], out: [["steel_mace", 1]], ticks: 5, msg: "You hammer out a steel mace." },
  smith_steel_shield: { group: "smith", skill: "smithing", lvl: 40, xp: 112.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 3]], out: [["steel_shield", 1]], ticks: 5, msg: "You hammer out a steel shield." },
  smith_steel_greatsword: { group: "smith", skill: "smithing", lvl: 42, xp: 112.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 3]], out: [["steel_greatsword", 1]], ticks: 5, msg: "You hammer out a steel greatsword." },
  smith_steel_greaves: { group: "smith", skill: "smithing", lvl: 44, xp: 112.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 3]], out: [["steel_greaves", 1]], ticks: 5, msg: "You hammer out steel greaves." },
  smith_steel_breastplate: { group: "smith", skill: "smithing", lvl: 48, xp: 187.5, at: ["anvil"], tools: ["hammer"],
    in: [["steel_bar", 5]], out: [["steel_breastplate", 1]], ticks: 5, msg: "You hammer out a steel breastplate." },
  smith_cobalt_axe: { group: "smith", skill: "smithing", lvl: 45, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 1]], out: [["cobalt_axe", 1]], ticks: 5, msg: "You hammer out a cobalt axe." },
  smith_cobalt_dagger: { group: "smith", skill: "smithing", lvl: 46, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 1]], out: [["cobalt_dagger", 1]], ticks: 5, msg: "You hammer out a cobalt dagger." },
  smith_cobalt_sword: { group: "smith", skill: "smithing", lvl: 47, xp: 50, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 1]], out: [["cobalt_sword", 1]], ticks: 5, msg: "You hammer out a cobalt sword." },
  smith_cobalt_pickaxe: { group: "smith", skill: "smithing", lvl: 49, xp: 100, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 2]], out: [["cobalt_pickaxe", 1]], ticks: 5, msg: "You hammer out a cobalt pickaxe." },
  smith_cobalt_helm: { group: "smith", skill: "smithing", lvl: 51, xp: 100, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 2]], out: [["cobalt_helm", 1]], ticks: 5, msg: "You hammer out a cobalt helm." },
  smith_cobalt_mace: { group: "smith", skill: "smithing", lvl: 53, xp: 100, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 2]], out: [["cobalt_mace", 1]], ticks: 5, msg: "You hammer out a cobalt mace." },
  smith_cobalt_shield: { group: "smith", skill: "smithing", lvl: 55, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 3]], out: [["cobalt_shield", 1]], ticks: 5, msg: "You hammer out a cobalt shield." },
  smith_cobalt_greatsword: { group: "smith", skill: "smithing", lvl: 57, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 3]], out: [["cobalt_greatsword", 1]], ticks: 5, msg: "You hammer out a cobalt greatsword." },
  smith_cobalt_greaves: { group: "smith", skill: "smithing", lvl: 59, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 3]], out: [["cobalt_greaves", 1]], ticks: 5, msg: "You hammer out cobalt greaves." },
  smith_cobalt_breastplate: { group: "smith", skill: "smithing", lvl: 63, xp: 250, at: ["anvil"], tools: ["hammer"],
    in: [["cobalt_bar", 5]], out: [["cobalt_breastplate", 1]], ticks: 5, msg: "You hammer out a cobalt breastplate." },
  smith_verdite_axe: { group: "smith", skill: "smithing", lvl: 60, xp: 62.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 1]], out: [["verdite_axe", 1]], ticks: 5, msg: "You hammer out a verdite axe." },
  smith_verdite_dagger: { group: "smith", skill: "smithing", lvl: 61, xp: 62.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 1]], out: [["verdite_dagger", 1]], ticks: 5, msg: "You hammer out a verdite dagger." },
  smith_verdite_sword: { group: "smith", skill: "smithing", lvl: 62, xp: 62.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 1]], out: [["verdite_sword", 1]], ticks: 5, msg: "You hammer out a verdite sword." },
  smith_verdite_pickaxe: { group: "smith", skill: "smithing", lvl: 64, xp: 125, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 2]], out: [["verdite_pickaxe", 1]], ticks: 5, msg: "You hammer out a verdite pickaxe." },
  smith_verdite_helm: { group: "smith", skill: "smithing", lvl: 66, xp: 125, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 2]], out: [["verdite_helm", 1]], ticks: 5, msg: "You hammer out a verdite helm." },
  smith_verdite_mace: { group: "smith", skill: "smithing", lvl: 68, xp: 125, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 2]], out: [["verdite_mace", 1]], ticks: 5, msg: "You hammer out a verdite mace." },
  smith_verdite_shield: { group: "smith", skill: "smithing", lvl: 70, xp: 187.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 3]], out: [["verdite_shield", 1]], ticks: 5, msg: "You hammer out a verdite shield." },
  smith_verdite_greatsword: { group: "smith", skill: "smithing", lvl: 72, xp: 187.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 3]], out: [["verdite_greatsword", 1]], ticks: 5, msg: "You hammer out a verdite greatsword." },
  smith_verdite_greaves: { group: "smith", skill: "smithing", lvl: 74, xp: 187.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 3]], out: [["verdite_greaves", 1]], ticks: 5, msg: "You hammer out verdite greaves." },
  smith_verdite_breastplate: { group: "smith", skill: "smithing", lvl: 78, xp: 312.5, at: ["anvil"], tools: ["hammer"],
    in: [["verdite_bar", 5]], out: [["verdite_breastplate", 1]], ticks: 5,
    msg: "You hammer out a verdite breastplate." },
  smith_emberite_axe: { group: "smith", skill: "smithing", lvl: 75, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 1]], out: [["emberite_axe", 1]], ticks: 5, msg: "You hammer out an emberite axe." },
  smith_emberite_dagger: { group: "smith", skill: "smithing", lvl: 76, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 1]], out: [["emberite_dagger", 1]], ticks: 5, msg: "You hammer out an emberite dagger." },
  smith_emberite_sword: { group: "smith", skill: "smithing", lvl: 77, xp: 75, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 1]], out: [["emberite_sword", 1]], ticks: 5, msg: "You hammer out an emberite sword." },
  smith_emberite_pickaxe: { group: "smith", skill: "smithing", lvl: 79, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 2]], out: [["emberite_pickaxe", 1]], ticks: 5, msg: "You hammer out an emberite pickaxe." },
  smith_emberite_helm: { group: "smith", skill: "smithing", lvl: 81, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 2]], out: [["emberite_helm", 1]], ticks: 5, msg: "You hammer out an emberite helm." },
  smith_emberite_mace: { group: "smith", skill: "smithing", lvl: 83, xp: 150, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 2]], out: [["emberite_mace", 1]], ticks: 5, msg: "You hammer out an emberite mace." },
  smith_emberite_shield: { group: "smith", skill: "smithing", lvl: 85, xp: 225, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 3]], out: [["emberite_shield", 1]], ticks: 5, msg: "You hammer out an emberite shield." },
  smith_emberite_greatsword: { group: "smith", skill: "smithing", lvl: 87, xp: 225, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 3]], out: [["emberite_greatsword", 1]], ticks: 5, msg: "You hammer out an emberite greatsword." },
  smith_emberite_greaves: { group: "smith", skill: "smithing", lvl: 89, xp: 225, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 3]], out: [["emberite_greaves", 1]], ticks: 5, msg: "You hammer out emberite greaves." },
  smith_emberite_breastplate: { group: "smith", skill: "smithing", lvl: 93, xp: 375, at: ["anvil"], tools: ["hammer"],
    in: [["emberite_bar", 5]], out: [["emberite_breastplate", 1]], ticks: 5,
    msg: "You hammer out an emberite breastplate." },
  smith_emberward: { group: "smith", skill: "smithing", lvl: 35, xp: 150, xp2: ["crafting", 50], at: ["anvil"],
    tools: ["hammer"], in: [["steel_bar", 3], ["sapphire", 1]], out: [["emberward", 1]], ticks: 5,
    if: [{ lvl: "crafting", gte: 20 }, { q: "embers_beneath", gte: 10 }], ifMsg: "You need Crafting 20 and Ilvara's design to forge that.",
    msg: "The sapphire drinks the heat. The Emberward is finished." },

  // ----------------------------------------------------------------
  // --------------------------- Cooking ----------------------------
  // ----------------------------------------------------------------
  cook_raw_shrimp: { group: "cook", skill: "cooking", lvl: 1, xp: 30, at: ["range", "fire"], tools: [],
    in: [["raw_shrimp", 1]], out: [["shrimp", 1]], ticks: 4, full: 34,
    fail: [["burnt_food", 1]], failMsg: "You burn the shrimp.", msg: "You cook the shrimp." },
  cook_raw_sardine: { group: "cook", skill: "cooking", lvl: 5, xp: 40, at: ["range", "fire"], tools: [],
    in: [["raw_sardine", 1]], out: [["sardine", 1]], ticks: 4, full: 38,
    fail: [["burnt_food", 1]], failMsg: "You burn the sardine.", msg: "You cook the sardine." },
  cook_raw_chicken: { group: "cook", skill: "cooking", lvl: 1, xp: 30, at: ["range", "fire"], tools: [],
    in: [["raw_chicken", 1]], out: [["cooked_chicken", 1]], ticks: 4, full: 31,
    fail: [["burnt_food", 1]], failMsg: "You burn the chicken.", msg: "You cook the chicken." },
  cook_raw_beef: { group: "cook", skill: "cooking", lvl: 1, xp: 30, at: ["range", "fire"], tools: [],
    in: [["raw_beef", 1]], out: [["cooked_beef", 1]], ticks: 4, full: 31,
    fail: [["burnt_food", 1]], failMsg: "You burn the beef.", msg: "You cook the beef." },
  cook_raw_trout: { group: "cook", skill: "cooking", lvl: 15, xp: 70, at: ["range", "fire"], tools: [],
    in: [["raw_trout", 1]], out: [["trout", 1]], ticks: 4, full: 50,
    fail: [["burnt_food", 1]], failMsg: "You burn the trout.", msg: "You cook the trout." },
  cook_raw_salmon: { group: "cook", skill: "cooking", lvl: 25, xp: 90, at: ["range", "fire"], tools: [],
    in: [["raw_salmon", 1]], out: [["salmon", 1]], ticks: 4, full: 58,
    fail: [["burnt_food", 1]], failMsg: "You burn the salmon.", msg: "You cook the salmon." },
  cook_raw_tuna: { group: "cook", skill: "cooking", lvl: 30, xp: 100, at: ["range", "fire"], tools: [],
    in: [["raw_tuna", 1]], out: [["tuna", 1]], ticks: 4, full: 63,
    fail: [["burnt_food", 1]], failMsg: "You burn the tuna.", msg: "You cook the tuna." },
  cook_raw_lobster: { group: "cook", skill: "cooking", lvl: 40, xp: 120, at: ["range", "fire"], tools: [],
    in: [["raw_lobster", 1]], out: [["lobster", 1]], ticks: 4, full: 74,
    fail: [["burnt_food", 1]], failMsg: "You burn the lobster.", msg: "You cook the lobster." },
  cook_raw_swordfish: { group: "cook", skill: "cooking", lvl: 45, xp: 140, at: ["range", "fire"], tools: [],
    in: [["raw_swordfish", 1]], out: [["swordfish", 1]], ticks: 4, full: 86,
    fail: [["burnt_food", 1]], failMsg: "You burn the swordfish.", msg: "You cook the swordfish." },
  cook_raw_shark: { group: "cook", skill: "cooking", lvl: 80, xp: 210, at: ["range", "fire"], tools: [],
    in: [["raw_shark", 1]], out: [["shark", 1]], ticks: 4, full: 94,
    fail: [["burnt_food", 1]], failMsg: "You burn the shark.", msg: "You cook the shark." },

  // ----------------------------------------------------------------
  // ------------------ Firemaking: light and burn ------------------
  // ----------------------------------------------------------------
  light_logs: { name: "Light logs", group: "light", skill: "firemaking", lvl: 1, xp: 40, at: [], tools: ["tinderbox"],
    in: [["logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 }, msg: "Your fire crackles to life." },
  light_oak_logs: { name: "Light oak logs", group: "light", skill: "firemaking", lvl: 15, xp: 60, at: [],
    tools: ["tinderbox"], in: [["oak_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  light_willow_logs: { name: "Light willow logs", group: "light", skill: "firemaking", lvl: 30, xp: 90, at: [],
    tools: ["tinderbox"], in: [["willow_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  light_maple_logs: { name: "Light maple logs", group: "light", skill: "firemaking", lvl: 45, xp: 135, at: [],
    tools: ["tinderbox"], in: [["maple_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  light_yew_logs: { name: "Light yew logs", group: "light", skill: "firemaking", lvl: 60, xp: 200, at: [],
    tools: ["tinderbox"], in: [["yew_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  light_ironbark_logs: { name: "Light ironbark logs", group: "light", skill: "firemaking", lvl: 75, xp: 300, at: [],
    tools: ["tinderbox"], in: [["ironbark_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  burn_logs: { name: "Burn logs", group: "burn", skill: "firemaking", lvl: 1, xp: 40, at: ["fire"], tools: [],
    in: [["logs", 1]], out: [], ticks: 6, refuel: 100 },
  burn_oak_logs: { name: "Burn oak logs", group: "burn", skill: "firemaking", lvl: 15, xp: 60, at: ["fire"], tools: [],
    in: [["oak_logs", 1]], out: [], ticks: 6, refuel: 100 },
  burn_willow_logs: { name: "Burn willow logs", group: "burn", skill: "firemaking", lvl: 30, xp: 90, at: ["fire"],
    tools: [], in: [["willow_logs", 1]], out: [], ticks: 6, refuel: 100 },
  burn_maple_logs: { name: "Burn maple logs", group: "burn", skill: "firemaking", lvl: 45, xp: 135, at: ["fire"],
    tools: [], in: [["maple_logs", 1]], out: [], ticks: 6, refuel: 100 },
  burn_yew_logs: { name: "Burn yew logs", group: "burn", skill: "firemaking", lvl: 60, xp: 200, at: ["fire"], tools: [],
    in: [["yew_logs", 1]], out: [], ticks: 6, refuel: 100 },
  burn_ironbark_logs: { name: "Burn ironbark logs", group: "burn", skill: "firemaking", lvl: 75, xp: 300, at: ["fire"],
    tools: [], in: [["ironbark_logs", 1]], out: [], ticks: 6, refuel: 100 },

  // ----------------------------------------------------------------
  // ---------------------- Tanning and crafting --------------------
  // ----------------------------------------------------------------
  tan_leather: { group: "tan", skill: "crafting", lvl: 1, xp: 0, at: ["tanner"], tools: [],
    in: [["cowhide", 1], ["coins", 2]], out: [["leather", 1]], ticks: 0, msg: "Hesk tans the cowhide." },
  tan_wolf: { group: "tan", skill: "crafting", lvl: 1, xp: 0, at: ["tanner"], tools: [],
    in: [["wolf_pelt", 1], ["coins", 20]], out: [["wolf_leather", 1]], ticks: 0, msg: "Hesk tans the wolf pelt." },
  craft_leather_gloves: { group: "leather", skill: "crafting", lvl: 1, xp: 14, at: [], tools: ["needle"],
    in: [["leather", 1]], out: [["leather_gloves", 1]], ticks: 3, msg: "You sew leather gloves." },
  craft_leather_boots: { group: "leather", skill: "crafting", lvl: 7, xp: 16, at: [], tools: ["needle"],
    in: [["leather", 1]], out: [["leather_boots", 1]], ticks: 3, msg: "You sew leather boots." },
  craft_leather_jerkin: { group: "leather", skill: "crafting", lvl: 14, xp: 25, at: [], tools: ["needle"],
    in: [["leather", 1]], out: [["leather_jerkin", 1]], ticks: 3, msg: "You sew a leather jerkin." },
  craft_leather_leggings: { group: "leather", skill: "crafting", lvl: 18, xp: 27, at: [], tools: ["needle"],
    in: [["leather", 1]], out: [["leather_leggings", 1]], ticks: 3, msg: "You sew leather leggings." },
  craft_wolfhide_vambraces: { group: "leather", skill: "crafting", lvl: 45, xp: 62, at: [], tools: ["needle"],
    in: [["wolf_leather", 1]], out: [["wolfhide_vambraces", 1]], ticks: 3, msg: "You sew wolfhide vambraces." },
  craft_wolfhide_leggings: { group: "leather", skill: "crafting", lvl: 55, xp: 124, at: [], tools: ["needle"],
    in: [["wolf_leather", 2]], out: [["wolfhide_leggings", 1]], ticks: 3, msg: "You sew wolfhide leggings." },
  craft_wolfhide_jerkin: { group: "leather", skill: "crafting", lvl: 65, xp: 186, at: [], tools: ["needle"],
    in: [["wolf_leather", 3]], out: [["wolfhide_jerkin", 1]], ticks: 3, msg: "You sew a wolfhide jerkin." },
  craft_gold_ring: { group: "gold", skill: "crafting", lvl: 5, xp: 15, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1]], out: [["gold_ring", 1]], ticks: 4, msg: "You cast a gold ring." },
  craft_gold_amulet: { group: "gold", skill: "crafting", lvl: 8, xp: 30, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1]], out: [["gold_amulet", 1]], ticks: 4, msg: "You cast a gold amulet." },
  craft_sapphire_amulet: { group: "gold", skill: "crafting", lvl: 24, xp: 65, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["sapphire", 1]], out: [["sapphire_amulet", 1]], ticks: 4,
    msg: "You cast a sapphire amulet." },
  craft_emerald_amulet: { group: "gold", skill: "crafting", lvl: 31, xp: 70, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["emerald", 1]], out: [["emerald_amulet", 1]], ticks: 4, msg: "You cast an emerald amulet." },
  craft_ruby_amulet: { group: "gold", skill: "crafting", lvl: 50, xp: 85, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["ruby", 1]], out: [["ruby_amulet", 1]], ticks: 4, msg: "You cast a ruby amulet." },
  craft_diamond_amulet: { group: "gold", skill: "crafting", lvl: 70, xp: 100, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["diamond", 1]], out: [["diamond_amulet", 1]], ticks: 4, msg: "You cast a diamond amulet." },
  cut_sapphire: { group: "cut", skill: "crafting", lvl: 20, xp: 50, at: [], tools: ["chisel"],
    in: [["uncut_sapphire", 1]], out: [["sapphire", 1]], ticks: 2, msg: "You cut the sapphire." },
  cut_emerald: { group: "cut", skill: "crafting", lvl: 27, xp: 68, at: [], tools: ["chisel"],
    in: [["uncut_emerald", 1]], out: [["emerald", 1]], ticks: 2, msg: "You cut the emerald." },
  cut_ruby: { group: "cut", skill: "crafting", lvl: 34, xp: 85, at: [], tools: ["chisel"],
    in: [["uncut_ruby", 1]], out: [["ruby", 1]], ticks: 2, msg: "You cut the ruby." },
  cut_diamond: { group: "cut", skill: "crafting", lvl: 43, xp: 108, at: [], tools: ["chisel"],
    in: [["uncut_diamond", 1]], out: [["diamond", 1]], ticks: 2, msg: "You cut the diamond." },

  // Across the Sound (13a): sunstone from Redcliff, eels from Sunken Vale
  cut_sunstone: { group: "cut", skill: "crafting", lvl: 72, xp: 140, at: [], tools: ["chisel"],
    in: [["uncut_sunstone", 1]], out: [["sunstone", 1]], ticks: 2, msg: "You cut the sunstone." },
  craft_sunstone_ring: { group: "gold", skill: "crafting", lvl: 76, xp: 160, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["sunstone", 1]], out: [["sunstone_ring", 1]], ticks: 4, msg: "You cast a sunstone ring." },
  craft_sunstone_amulet: { group: "gold", skill: "crafting", lvl: 80, xp: 180, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["sunstone", 1]], out: [["sunstone_amulet", 1]], ticks: 4, msg: "You cast a sunstone amulet." },
  craft_sunstone_circlet: { group: "gold", skill: "crafting", lvl: 85, xp: 220, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 2], ["sunstone", 1]], out: [["sunstone_circlet", 1]], ticks: 4, msg: "You cast a sunstone circlet." },
  cook_raw_vale_eel: { group: "cook", skill: "cooking", lvl: 55, xp: 150, at: ["range", "fire"], tools: [],
    in: [["raw_vale_eel", 1]], out: [["vale_eel", 1]], ticks: 4, full: 88,
    fail: [["burnt_food", 1]], failMsg: "You burn the eel.", msg: "You cook the eel." },
  // Across the Sound (13a): the high east
  smelt_starsteel: { group: "smelt", skill: "smithing", lvl: 80, xp: 62.5, at: ["furnace"], tools: [],
    in: [["starmetal_ore", 1], ["coal", 10]], out: [["starsteel_bar", 1]], ticks: 4, msg: "You smelt a starsteel bar." },
  smith_starsteel_axe: { group: "smith", skill: "smithing", lvl: 81, xp: 87.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 1]], out: [["starsteel_axe", 1]], ticks: 5, msg: "You hammer out a starsteel axe." },
  smith_starsteel_pickaxe: { group: "smith", skill: "smithing", lvl: 85, xp: 175, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 2]], out: [["starsteel_pickaxe", 1]], ticks: 5, msg: "You hammer out a starsteel pickaxe." },
  smith_starsteel_sword: { group: "smith", skill: "smithing", lvl: 83, xp: 87.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 1]], out: [["starsteel_sword", 1]], ticks: 5, msg: "You hammer out a starsteel sword." },
  smith_starsteel_dagger: { group: "smith", skill: "smithing", lvl: 82, xp: 87.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 1]], out: [["starsteel_dagger", 1]], ticks: 5, msg: "You hammer out a starsteel dagger." },
  smith_starsteel_mace: { group: "smith", skill: "smithing", lvl: 89, xp: 175, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 2]], out: [["starsteel_mace", 1]], ticks: 5, msg: "You hammer out a starsteel mace." },
  smith_starsteel_greatsword: { group: "smith", skill: "smithing", lvl: 93, xp: 262.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 3]], out: [["starsteel_greatsword", 1]], ticks: 5, msg: "You hammer out a starsteel greatsword." },
  smith_starsteel_helm: { group: "smith", skill: "smithing", lvl: 87, xp: 175, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 2]], out: [["starsteel_helm", 1]], ticks: 5, msg: "You hammer out a starsteel helm." },
  smith_starsteel_shield: { group: "smith", skill: "smithing", lvl: 91, xp: 262.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 3]], out: [["starsteel_shield", 1]], ticks: 5, msg: "You hammer out a starsteel shield." },
  smith_starsteel_greaves: { group: "smith", skill: "smithing", lvl: 95, xp: 262.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 3]], out: [["starsteel_greaves", 1]], ticks: 5, msg: "You hammer out a starsteel greaves." },
  smith_starsteel_breastplate: { group: "smith", skill: "smithing", lvl: 99, xp: 437.5, at: ["anvil"], tools: ["hammer"],
    in: [["starsteel_bar", 5]], out: [["starsteel_breastplate", 1]], ticks: 5, msg: "You hammer out a starsteel breastplate." },
  light_amber_logs: { name: "Light amber logs", group: "light", skill: "firemaking", lvl: 85, xp: 400, at: [],
    tools: ["tinderbox"], in: [["amber_logs", 1]], out: [], ticks: 4, place: { obj: "fire", ticks: 100 },
    msg: "Your fire crackles to life." },
  burn_amber_logs: { name: "Burn amber logs", group: "burn", skill: "firemaking", lvl: 85, xp: 400, at: ["fire"],
    tools: [], in: [["amber_logs", 1]], out: [], ticks: 6, refuel: 100 },
  craft_amber_charm: { group: "gold", skill: "crafting", lvl: 90, xp: 260, at: ["furnace"], tools: ["mould"],
    in: [["gold_bar", 1], ["amber_sap", 3]], out: [["amber_charm", 1]], ticks: 4, msg: "You cast an amber charm." },
  cook_raw_lanternfish: { group: "cook", skill: "cooking", lvl: 62, xp: 170, at: ["range", "fire"], tools: [],
    in: [["raw_lanternfish", 1]], out: [["lanternfish", 1]], ticks: 4, full: 92,
    fail: [["burnt_food", 1]], failMsg: "You burn the lanternfish.", msg: "You cook the lanternfish." },
  cook_raw_stormray: { group: "cook", skill: "cooking", lvl: 88, xp: 260, at: ["range", "fire"], tools: [],
    in: [["raw_stormray", 1]], out: [["stormray", 1]], ticks: 4, full: 99,
    fail: [["burnt_food", 1]], failMsg: "You burn the stormray.", msg: "You cook the stormray." },
  cure_beef: { group: "cure", skill: "cooking", lvl: 50, xp: 120, at: ["range"], tools: [],
    in: [["raw_beef", 1], ["salt", 2]], out: [["cured_beef", 1]], ticks: 4, full: 84, fail: [["burnt_food", 1]],
    failMsg: "You burn the beef.", msg: "You cure the beef.",
    if: [{ q: "salt_iron", eq: 100 }], ifMsg: "Harbourmaster Corran hasn't shared his curing recipe yet." },
  cure_swordfish: { group: "cure", skill: "cooking", lvl: 60, xp: 200, at: ["range"], tools: [],
    in: [["raw_swordfish", 1], ["salt", 2]], out: [["cured_swordfish", 1]], ticks: 4, full: 90, fail: [["burnt_food", 1]],
    failMsg: "You burn the swordfish.", msg: "You cure the swordfish.",
    if: [{ q: "salt_iron", eq: 100 }], ifMsg: "Harbourmaster Corran hasn't shared his curing recipe yet." },
  cure_lanternfish: { group: "cure", skill: "cooking", lvl: 70, xp: 240, at: ["range"], tools: [],
    in: [["raw_lanternfish", 1], ["salt", 2]], out: [["cured_lanternfish", 1]], ticks: 4, full: 95, fail: [["burnt_food", 1]],
    failMsg: "You burn the lanternfish.", msg: "You cure the lanternfish.",
    if: [{ q: "salt_iron", eq: 100 }], ifMsg: "Harbourmaster Corran hasn't shared his curing recipe yet." }
};
Data.stations = {
  furnace: { name: "Furnace", empty: "You have nothing to smelt." },
  anvil: { name: "Anvil", empty: "You need bars to smith." },
  range: { name: "Range", empty: "You have nothing to cook." },
  fire: { name: "Fire", empty: "You have nothing to cook." },
  tanner: { name: "Tanning", empty: "You have no hides to tan." }
};
// ==== src/engine/data/shops.js ====
// ----------------------------------------------------------------
// ------------------------- Data: shops --------------------------
// ----------------------------------------------------------------
// stock rows = [item, base stock, price?]; price defaults to the item value (DESIGN.md 15.2).
// Shops buy at floor(value x rate); sold items never enter stock.
Data.shops = {
  tobin_general: { name: "Tobin's General Store", buys: "all", rate: 0.4,
    stock: [["tinderbox", 10], ["hammer", 10], ["chisel", 5], ["needle", 5], ["small_net", 5], ["fishing_rod", 5],
      ["jewellery_mould", 5], ["bronze_axe", 5], ["bronze_pickaxe", 5], ["shrimp", 20]] },
  brenna_smithy: { name: "Brenna's Smithy", buys: ["weapon", "armour", "bar"], rate: 0.5,
    stock: [["bronze_axe", 3], ["bronze_sword", 3], ["bronze_helm", 3], ["bronze_shield", 3], ["bronze_greaves", 3],
      ["bronze_breastplate", 3], ["iron_axe", 3], ["iron_sword", 3], ["iron_helm", 3], ["iron_shield", 3],
      ["iron_greaves", 3], ["iron_breastplate", 3], ["steel_axe", 3], ["steel_sword", 3], ["steel_helm", 3],
      ["steel_shield", 3], ["steel_greaves", 3], ["steel_breastplate", 3], ["cobalt_axe", 2, 600],
      ["verdite_axe", 1, 4000], ["hammer", 5], ["bronze_bar", 50, 28], ["iron_bar", 30, 70], ["steel_bar", 20, 200],
      ["bronze_dagger", 3], ["bronze_mace", 3], ["iron_dagger", 3], ["iron_mace", 3]] },
  dagny_ores: { name: "Dagny's Pick & Ore", buys: ["ore", "bar", "gem_uncut"], rate: 0.5,
    stock: [["bronze_pickaxe", 3], ["iron_pickaxe", 3], ["steel_pickaxe", 3], ["cobalt_pickaxe", 2, 1200],
      ["verdite_pickaxe", 1, 8000], ["coal", 100, 70]] },
  pell_tackle: { name: "Pell's Tackle", buys: ["raw_food", "food"], rate: 0.5,
    stock: [["small_net", 5], ["fishing_rod", 5], ["harpoon", 3], ["lobster_cage", 3], ["feather", 2000, 3]] },
  hob_inn: { name: "Hob's Hearth Inn", buys: ["food"], rate: 0.5,
    stock: [["cooked_chicken", 20, 6], ["trout", 15, 40], ["salmon", 10, 70], ["tuna", 10, 100], ["lobster", 10, 200]] },
  ysolde_goods: { name: "Ysolde's Gems & Leather", buys: ["hide", "leather", "gem", "gem_uncut", "jewellery"], rate: 0.5,
    stock: [["needle", 5], ["chisel", 5], ["jewellery_mould", 5], ["leather", 50, 30], ["gold_bar", 20, 360],
      ["uncut_sapphire", 5, 120], ["leather_gloves", 3], ["leather_boots", 3], ["leather_jerkin", 3],
      ["leather_leggings", 3]] },
  marrick_armoury: { name: "Marrick's Armoury", buys: [], rate: 0,
    stock: [["cobalt_sword", 1, 975], ["cobalt_helm", 1, 1950], ["cobalt_shield", 1, 2925], ["cobalt_greaves", 1, 2925],
      ["cobalt_breastplate", 1, 4875]] },
  // Saltmere (DESIGN.md 15.2a)
  maren_fish: { name: "Maren's Fish Stall", buys: ["raw_food", "food"], rate: 0.5,
    stock: [["harpoon", 3], ["lobster_cage", 3], ["feather", 1000, 3], ["raw_tuna", 20, 50], ["raw_lobster", 15, 100],
      ["raw_swordfish", 10, 160]] },
  salt_wife_inn: { name: "The Salt Wife", buys: ["food"], rate: 0.5,
    stock: [["salmon", 10, 70], ["tuna", 10, 100], ["lobster", 10, 200], ["swordfish", 8, 320]] },
  // Southfold (15.2a); Wyn trades once the mill is safe
  wyn_bakery: { name: "Wyn's Bakery", buys: ["food"], rate: 0.5,
    stock: [["meat_pie", 20, 60], ["cooked_chicken", 10, 6]] }
};
// ==== src/engine/data/dialogues.js ====
// ----------------------------------------------------------------
// ----------------------- Data: dialogues ------------------------
// ----------------------------------------------------------------
// One graph per townsfolk NPC (same id) plus lair_warning (DESIGN.md sections 7, 9, 15, 16).
// Quest givers start on a branch node keyed by quest stage. Effects that take items sit on
// the node reached straight from the branch that checked them, so nothing can change between.
Data.dialogues = {
  // ----------------------------------------------------------------
  // ------------------------- Brackenford --------------------------
  // ----------------------------------------------------------------
  mirella: { start: "hi", nodes: {
    hi: { say: "npc", text: "Coin, ore or old boots: the vault keeps it all.", next: "ask" },
    ask: { opts: [{ text: "I'd like to use the bank.", go: "bank" }, { text: "What can I store?", go: "what" },
      { text: "Just looking.", go: "bye" }] },
    bank: { say: "npc", text: "Right this way.", do: [{ open: "bank" }], next: null },
    what: { say: "npc", text: "Anything you can carry, as much as you like. The booths by the door open the same vault.",
      next: "ask" },
    bye: { say: "npc", text: "The vault will be here.", next: null }
  } },
  tobin: { start: "hi", nodes: {
    hi: { say: "npc", text: "Tools, trinkets, and whatever you're trying to be rid of.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Will you buy anything?", go: "buy" },
      { text: "Not today.", go: "bye" }] },
    trade: { say: "npc", text: "Have a look.", do: [{ open: "shop", shop: "tobin_general" }], next: null },
    buy: { say: "npc", text: "Anything at all, though the specialists pay better. Brenna wants metal; Pell wants fish.",
      next: "ask" },
    bye: { say: "npc", text: "Mind how you go.", next: null }
  } },
  brenna: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "hammer_hearth", eq: 100 }], go: "after" },
      { if: [{ q: "hammer_hearth", eq: 30 }], go: "done" },
      { if: [{ q: "hammer_hearth", eq: 20 }], go: "anvil" },
      { if: [{ q: "hammer_hearth", eq: 10 }], go: "ore" }], else: "offer" },
    offer: { say: "npc", text: "Forge is cold and my apprentice bolted. Ever swung a pick?", next: "offer2" },
    offer2: { say: "npc", text: "Copper and tin, up the north-west road. One of each smelts to bronze.", next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Good. Bring the ore back to this furnace, then show me what you can hammer out.",
      do: [{ stage: ["hammer_hearth", 10] }], next: null },
    decline: { say: "npc", text: "The ore won't mine itself.", next: null },
    ore: { say: "npc", text: "Copper and tin from Copperdell, up the north-west road. One of each smelts to a bar here.",
      next: null },
    anvil: { say: "npc", text: "Good colour on that bar. Now take it to the anvil and hammer out anything you like.",
      next: null },
    done: { say: "npc", text: "Not bad for a first strike. The smithy's yours to use.", next: "done2" },
    done2: { say: "npc", text: "Farmer Odo, south of town, has goblin trouble.", do: [{ complete: "hammer_hearth" }],
      next: null },
    after: { say: "npc", text: "Mind the sparks.", next: "after_ask" },
    after_ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Any smithing tips?", go: "tips" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Take your pick.", do: [{ open: "shop", shop: "brenna_smithy" }], next: null },
    tips: { say: "npc", text: "Iron crumbles half the time until you're practised. Steel wants two coal for every ore.",
      next: "after_ask" },
    bye: { say: "npc", text: "Keep the fire fed.", next: null }
  } },
  hob: { start: "hi", nodes: {
    hi: { say: "npc", text: "Hot food, cold ale, no credit.", next: "ask" },
    ask: { opts: [{ text: "What's cooking?", go: "trade" }, { text: "Can I use your range?", go: "range" },
      { text: "Not hungry.", go: "bye" }] },
    trade: { say: "npc", text: "Fresh today.", do: [{ open: "shop", shop: "hob_inn" }], next: null },
    range: { say: "npc", text: "Help yourself to the one in the back. Burn the fish, not my inn.", next: null },
    bye: { say: "npc", text: "Door's always open.", next: null }
  } },
  ysolde: { start: "hi", nodes: {
    hi: { say: "npc", text: "Leather for beginners, gems for the patient.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Any crafting tips?", go: "tip" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Careful with the stones.", do: [{ open: "shop", shop: "ysolde_goods" }], next: null },
    tip: { say: "npc", text: "Hesk at Dunmoor tans cowhide for two coins. Stitch leather with a needle; gloves first.",
      next: "tip2" },
    tip2: { say: "npc", text: "Rough gems turn up in rock. Cut them with a chisel, then set them in gold at a furnace.",
      next: "ask" },
    bye: { say: "npc", text: "Come back with steady hands.", next: null }
  } },
  vael: { start: "hi", nodes: {
    hi: { say: "npc", text: "Accurate to land it, aggressive to hurt, defensive to live.", next: "ask" },
    ask: { opts: [{ text: "Tell me about the styles.", go: "styles" }, { text: "Any advice for a fight?", go: "advice" },
      { text: "I've mastered a skill.", go: "cape", if: [{ anyLvl: 99 }, { not: { owns: "mastery_cape" } }] },
      { text: "Goodbye.", go: "bye" }] },
    styles: { say: "npc", text: "Accurate trains Attack and lands more blows. Aggressive trains Strength and hits harder.",
      next: "styles2" },
    styles2: { say: "npc", text: "Defensive trains Defence. Controlled splits the work three ways, and the gains with it.",
      next: "ask" },
    advice: { say: "npc", text: "Pack food, keep auto-eat on, and read a foe's level colour before you swing.",
      next: "advice2" },
    advice2: { say: "npc", text: "If it goes badly, the Hearth recall on your combat tab brings you home.", next: "ask" },
    cape: { say: "npc", text: "Ninety-nine. I've seen that twice in my life. Wear this, and stand up straight.",
      do: [{ give: ["mastery_cape", 1] }], next: null },
    bye: { say: "npc", text: "Dismissed.", next: null }
  } },
  marrick: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "gnarltooth_tolls", eq: 100 }], go: "after" },
      { if: [{ q: "gnarltooth_tolls", eq: 40 }, { has: "skarg_tusk" }], go: "done" },
      { if: [{ q: "gnarltooth_tolls", eq: 40 }, { owns: "skarg_tusk" }], go: "stashed" },
      { if: [{ q: "gnarltooth_tolls", eq: 40 }], go: "tusk" },
      { if: [{ q: "gnarltooth_tolls", eq: 30 }], go: "skarg" },
      { if: [{ q: "gnarltooth_tolls", eq: 20 }], go: "banner" },
      { if: [{ q: "gnarltooth_tolls", eq: 10 }], go: "brutes" },
      { if: [{ q: "trouble_dunmoor", eq: 100 }, { lvl: "firemaking", gte: 10 }], go: "offer" },
      { if: [{ q: "trouble_dunmoor", eq: 100 }], go: "unready" }], else: "greet" },
    greet: { say: "npc", text: "The north road's not safe. Yet.", next: "greet2" },
    greet2: { say: "npc", text: "Farmer Odo has goblin trouble of his own. Help him first, then we'll talk.", next: null },
    unready: { say: "npc", text: "Odo says you're useful. This job needs fire, though: come back with Firemaking 10.",
      next: "unready2" },
    unready2: { say: "npc", text: "Light some logs with your tinderbox. Every fire teaches you a little more.", next: null },
    offer: { say: "npc", text: "Goblins took the north bridge and want a toll in coin or blood. Odo says you're useful.",
      next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Their brutes hold the camp over the toll bridge, east across the river. Put four down.",
      do: [{ stage: ["gnarltooth_tolls", 10] }], next: null },
    decline: { say: "npc", text: "The toll won't pay itself. Suit yourself.", next: null },
    brutes: { say: "npc", text: "Four brutes. They're the big ones in the camp over the toll bridge.", next: null },
    banner: { say: "npc", text: "Now burn their war banner. Nothing breaks a warband faster. Bring a tinderbox.",
      next: null },
    skarg: { say: "npc", text: "That roar was Skarg himself. Bring me his tusk and the bridge is ours.", next: null },
    stashed: { say: "npc", text: "You've got the tusk stashed somewhere: your bank, or your gravestone. Bring it here.",
      next: null },
    tusk: { say: "npc", text: "No tusk, no bridge. Skarg will be back in his tent; fetch it again.", next: null },
    done: { say: "npc", text: "The bridge is ours. I've told the wardens at the Ironbound gate below Copperdell to let you through; the miners swear there's cobalt down there.",
      do: [{ take: ["skarg_tusk", 1] }, { complete: "gnarltooth_tolls" }], next: "done2" },
    done2: { say: "npc", text: "Ilvara the Sage at the old watchtower has been asking for someone handy.", next: null },
    after: { say: "npc", text: "The north road's quiet, thanks to you.", next: "after_ask" },
    after_ask: { opts: [{ text: "Show me the armoury.", go: "trade" }, { text: "Carry on.", go: "bye" }] },
    trade: { say: "npc", text: "Cobalt, fresh from the Deeps. It isn't cheap.",
      do: [{ open: "shop", shop: "marrick_armoury" }], next: null },
    bye: { say: "npc", text: "As you were.", next: null }
  } },

  // ----------------------------------------------------------------
  // ------------------------ Dunmoor Farm --------------------------
  // ----------------------------------------------------------------
  odo: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "trouble_dunmoor", eq: 100 }], go: "after" },
      { if: [{ q: "trouble_dunmoor", eq: 30 }], go: "done" },
      { if: [{ q: "trouble_dunmoor", eq: 20 }], go: "hunt" },
      { if: [{ q: "trouble_dunmoor", gte: 10, lt: 20 }, { has: "logs", qty: 10 }], go: "logs" },
      { if: [{ q: "trouble_dunmoor", eq: 15 }], go: "need" },
      { if: [{ q: "trouble_dunmoor", eq: 10 }], go: "chop" }], else: "offer" },
    offer: { say: "npc", text: "Gnarltooth goblins flattened my fence and ran off with three hens. I need timber, and I need them gone.",
      next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Bless you. Ten logs for the fence first. Hollowpine Wood is west of town.",
      do: [{ stage: ["trouble_dunmoor", 10] }], next: null },
    decline: { say: "npc", text: "Then mind the hens on your way out.", next: null },
    chop: { say: "npc", text: "Ten logs, friend. The trees at the edge of Hollowpine fall easy.", next: null },
    need: { say: "npc", text: "That's fewer than ten logs. The fence won't mend itself.", next: null },
    logs: { say: "npc", text: "That'll mend it. Six goblins should teach the rest. Take some of the wife's chicken; they bite.",
      do: [{ take: ["logs", 10] }, { give: ["cooked_chicken", 5] }, { stage: ["trouble_dunmoor", 20] }], next: "hunt" },
    hunt: { say: "npc", text: "Six goblins. Their camp is north-east, over the toll bridge across the river.", next: null },
    done: { say: "npc", text: "Not a feather out of place. Take these, and my thanks.", next: "done2" },
    done2: { say: "npc", text: "Captain Marrick wants hands on the north road, and Bram the Ferryman lost something in the river.",
      do: [{ complete: "trouble_dunmoor" }], next: null },
    after: { say: "npc", text: "Mind the hens.", next: "after2" },
    after2: { say: "npc", text: "The fence is holding, and not a goblin in sight. Thanks to you.", next: null }
  } },
  hesk: { start: "hi", nodes: {
    hi: { say: "npc", text: "Two coins a hide. Wolf pelts are twenty; they stink.", next: "ask" },
    ask: { opts: [{ text: "Tan my hides.", go: "tan" }, { text: "Where do hides come from?", go: "where" },
      { text: "Not today.", go: "bye" }] },
    tan: { say: "npc", text: "Let's see them.", do: [{ open: "make", station: "tanner" }], next: null },
    where: { say: "npc", text: "Cowhide from the field next door. Wolf pelts from the ash wolves up north, if you're brave.",
      next: "ask" },
    bye: { say: "npc", text: "Suit yourself.", next: null }
  } },

  // ----------------------------------------------------------------
  // ------------------- Copperdell and the coast -------------------
  // ----------------------------------------------------------------
  dagny: { start: "hi", nodes: {
    hi: { say: "npc", text: "Picks, coal, and no whining about the dust.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Where's the good ore?", go: "ore" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Cash first.", do: [{ open: "shop", shop: "dagny_ores" }], next: null },
    ore: { say: "npc", text: "Copper and tin by the entrance, iron further in, coal at the back. The ladder goes down to more.",
      next: "ore2" },
    ore2: { say: "npc", text: "Gold sits up at Greyspire Quarry, but bandits like it there too.", next: "ask" },
    bye: { say: "npc", text: "Watch your head.", next: null }
  } },
  bram: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "river_courier", eq: 100 }], go: "after" },
      { if: [{ q: "river_courier", eq: 20 }, { has: "courier_seal" }, { has: "trout", qty: 5 }], go: "done" },
      { if: [{ q: "river_courier", eq: 20 }, { not: { has: "courier_seal" } }, { owns: "courier_seal" }], go: "stashed" },
      { if: [{ q: "river_courier", eq: 20 }, { not: { owns: "courier_seal" } }], go: "lost" },
      { if: [{ q: "river_courier", eq: 20 }], go: "need" },
      { if: [{ q: "river_courier", eq: 10 }], go: "seek" },
      { if: [{ lvl: "fishing", gte: 20 }, { lvl: "cooking", gte: 15 }], go: "offer" }], else: "greet" },
    greet: { say: "npc", text: "Everything floats if you pay me.", next: "unready" },
    unready: { say: "npc", text: "Come back when you can work a rod (Fishing 20) and a pan (Cooking 15).", next: null },
    offer: { say: "npc", text: "My courier seal slipped into the Wend. Without it, no runner carries a thing.",
      next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Fish the lure spots in the river just west of here. Bring feathers. It'll snag on a line.",
      do: [{ stage: ["river_courier", 10] }], next: null },
    decline: { say: "npc", text: "The river keeps what it takes. Usually.", next: null },
    seek: { say: "npc", text: "Keep at the lure spots in the Wend. Pell sells feathers if you run short.", next: null },
    need: { say: "npc", text: "The seal, and five cooked trout. Runners don't run hungry.", next: "need2" },
    need2: { say: "npc", text: "Trout burn easily at first. Cook a few extra.", next: null },
    stashed: { say: "npc", text: "My seal's not on you. Fetch it from the bank, or your gravestone.", next: null },
    lost: { say: "npc", text: "You've lost my seal? The Wend keeps what it takes. Back to the lure spots.", next: null },
    done: { say: "npc", text: "The runners are yours. Fill your pack, and your haul goes straight to the vault.",
      do: [{ take: ["courier_seal", 1] }, { take: ["trout", 5] }, { complete: "river_courier" }], next: null },
    after: { say: "npc", text: "Everything floats if you pay me.", next: "after_ask" },
    after_ask: { opts: [{ text: "I lost my satchel.", go: "reclaim", if: [{ not: { owns: "courier_satchel" } }] },
      { text: "Just passing.", go: "bye" }] },
    reclaim: { say: "npc", text: "Again? Here. Try not to drown this one.", do: [{ give: ["courier_satchel", 1] }],
      next: null },
    bye: { say: "npc", text: "Mind the current.", next: null }
  } },
  pell: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "crossing_sound", eq: 100 }], go: "hi" },
      { if: [{ q: "crossing_sound", eq: 20 }], go: "sail" },
      { if: [{ q: "crossing_sound", eq: 10 }, { has: "oak_logs", qty: 6 }, { has: "iron_bar", qty: 2 }], go: "patch" },
      { if: [{ q: "crossing_sound", eq: 10 }], go: "need" },
      { if: [{ q: "river_courier", eq: 100 }, { lvl: "fishing", gte: 25 }], go: "offer" }], else: "hi" },
    hi: { say: "npc", text: "Feathers for the river, cages for the coast.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Where should I fish?", go: "where" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Everything's dry, mostly.", do: [{ open: "shop", shop: "pell_tackle" }], next: null },
    where: { say: "npc", text: "Net the lake at Willowmere for shrimp. Lure the river for trout; the hooks eat feathers.",
      next: "where2" },
    where2: { say: "npc", text: "Off the pier here: cages for lobster, a harpoon for tuna. Sharks circle the far end.",
      next: "ask" },
    bye: { say: "npc", text: "Tight lines.", next: null },
    offer: { say: "npc",
      text: "See the Gullwing off the pier? My ferry to Saltmere. She kissed a rock in the last storm, and now she drinks the Sound.",
      next: "offer2" },
    offer2: { say: "npc", text: "Bram says you're handy. Help me patch her and she'll carry you east for nothing.",
      next: "offer_ask" },
    offer_ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    decline: { say: "npc", text: "Then she sits and drinks the Sound. Anything else?", next: "ask" },
    accept: { say: "npc",
      text: "Six oak logs for planks and two iron bars for the fittings. Oaks grow in Hollowpine; Brenna's furnace smelts iron.",
      do: [{ stage: ["crossing_sound", 10] }], next: null },
    need: { say: "npc", text: "Six oak logs and two iron bars. The Gullwing won't patch herself.", next: "ask" },
    patch: { say: "npc", text: "Good timber, good iron. Hold this... and this... There. She floats!",
      do: [{ take: ["oak_logs", 6] }, { take: ["iron_bar", 2] }, { stage: ["crossing_sound", 20] }], next: "patch2" },
    patch2: { say: "npc",
      text: "Board her at the end of the pier. Report to Harbourmaster Corran in Saltmere; he keeps the crossing ledger.",
      next: null },
    sail: { say: "npc", text: "The Gullwing waits at the end of the pier. Corran will want your name in his ledger.",
      next: "ask" }
  } },

  // ----------------------------------------------------------------
  // ------------------------- Ashen Reach --------------------------
  // ----------------------------------------------------------------
  ilvara: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "hollow_king", eq: 100 }], go: "hk_after" },
      { if: [{ q: "hollow_king", eq: 30 }, { has: "kings_seal" }], go: "hk_done" },
      { if: [{ q: "hollow_king", eq: 30 }, { owns: "kings_seal" }], go: "hk_stashed" },
      { if: [{ q: "hollow_king", eq: 30 }], go: "hk_lost" },
      { if: [{ q: "hollow_king", eq: 20 }], go: "hk_king" },
      { if: [{ q: "hollow_king", eq: 10 }], go: "hk_knights" },
      { if: [{ q: "fallen_star", eq: 100 }], go: "hk_offer" },
      { if: [{ q: "embers_beneath", eq: 100 }], go: "after" },
      { if: [{ q: "embers_beneath", eq: 40 }, { has: "ember_heart" }], go: "done" },
      { if: [{ q: "embers_beneath", eq: 40 }, { owns: "ember_heart" }], go: "stashed" },
      { if: [{ q: "embers_beneath", eq: 40 }], go: "heart" },
      { if: [{ q: "embers_beneath", eq: 30 }], go: "lair" },
      { if: [{ q: "embers_beneath", eq: 20 }], go: "beacons" },
      { if: [{ q: "embers_beneath", eq: 10 }], go: "ward" },
      { if: [{ q: "hammer_hearth", eq: 100 }, { q: "trouble_dunmoor", eq: 100 }, { q: "river_courier", eq: 100 },
        { q: "gnarltooth_tolls", eq: 100 }], go: "offer" }], else: "greet" },
    greet: { say: "npc", text: "The ground is warmer than it should be.", next: "unready" },
    hk_offer: { say: "npc",
      text: "Vesna's star woke something. Across the Sound, in Duskhollow, a dead king has taken his throne again.",
      next: "hk_offer2" },
    hk_offer2: { say: "npc", text: "His knights walk the ruins. Break them, then break him, and bring me his seal.",
      next: "hk_ask" },
    hk_ask: { opts: [{ text: "I'll help.", go: "hk_accept" }, { text: "Not right now.", go: "hk_decline" }] },
    hk_accept: { say: "npc", text: "Duskhollow lies south of the Brinemarsh. Three of his knights first; the keep will open.",
      do: [{ stage: ["hollow_king", 10] }], next: null },
    hk_decline: { say: "npc", text: "He has waited centuries. He will wait for you.", next: null },
    hk_knights: { say: "npc", text: "Three hollow knights in Duskhollow. Their armour is empty; their swords are not.", next: null },
    hk_king: { say: "npc", text: "The keep is open. The King sits his throne. Take his seal from what is left of him.", next: null },
    hk_stashed: { say: "npc", text: "The seal is not on you. Fetch it from the bank, or your gravestone.", next: null },
    hk_lost: { say: "npc", text: "Lost? He will be back on his throne. Take it from him again.", next: null },
    hk_done: { say: "npc", text: "His seal. It is cold, and it is done. Wear his crown; it remembers who beat him.",
      do: [{ take: ["kings_seal", 1] }, { complete: "hollow_king" }], next: null },
    hk_after: { say: "npc", text: "The ground is quiet, both sides of the Sound. For now.", next: null },
    unready: { say: "npc", text: "Brackenford has troubles of its own. Help Brenna, Odo, Bram and Captain Marrick, then come back.",
      next: null },
    offer: { say: "npc", text: "Three beacons on this ridge sealed something beneath Copperdell. They are cooling. The ground is not.",
      next: "offer2" },
    offer2: { say: "npc", text: "Steel to hold, sapphire to drink the heat. Forge a ward.", next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Three steel bars and a cut sapphire, worked at an anvil. You'll need Smithing 35 and Crafting 20.",
      do: [{ stage: ["embers_beneath", 10] }], next: null },
    decline: { say: "npc", text: "The embers will keep. For now.", next: null },
    ward: { say: "npc", text: "The ward first: three steel bars and a cut sapphire, at an anvil.", next: null },
    beacons: { say: "npc", text: "Relight the beacons: one west, one below this tower, one east. Five willow logs or better each.",
      next: null },
    lair: { say: "npc", text: "The sealed door beneath Copperdell stands open. Go down through the Deeps, and wear the ward.",
      next: null },
    stashed: { say: "npc", text: "You have the heart, but not on you. Fetch it from the bank, or your gravestone.",
      next: null },
    heart: { say: "npc", text: "The wyrm still has its heart. Go back down and bring it to me.", next: null },
    done: { say: "npc", text: "Its heart still burns. Wear this. Orcadia owes you.",
      do: [{ take: ["ember_heart", 1] }, { complete: "embers_beneath" }], next: null },
    after: { say: "npc", text: "The ground is cooling at last.", next: "after_ask" },
    after_ask: { opts: [{ text: "I lost my mantle.", go: "reclaim", if: [{ not: { owns: "heros_mantle" } }] },
      { text: "Farewell.", go: "bye" }] },
    reclaim: { say: "npc", text: "Careless. Here, another. Try to keep this one.", do: [{ give: ["heros_mantle", 1] }],
      next: null },
    bye: { say: "npc", text: "Walk warm.", next: null }
  } },

  // ----------------------------------------------------------------
  // ------------------------- The Deeps ----------------------------
  // ----------------------------------------------------------------
  lair_warning: { start: "warn", nodes: {
    warn: { say: "none", text: "Heat pours through the cracks. This is a danger zone: if you fall here, most of what you carry stays behind.",
      next: "ask" },
    ask: { opts: [{ text: "Enter the Lair.", go: "enter" }, { text: "Not yet.", go: "back" }] },
    enter: { say: "none", text: "You shoulder through the door into the heat.",
      do: [{ flag: "lair_ok" }, { teleport: ["deeps", 36, 39] }], next: null },
    back: { say: "none", text: "You step back from the door.", next: null }
  } },
  // ----------------------------------------------------------------
  // --------------------------- Saltmere ---------------------------
  // ----------------------------------------------------------------
  osric: { start: "hi", nodes: {
    hi: { say: "npc", text: "Every coin counted, every coin kept. Brackenford's vault and mine are the same vault.",
      next: "ask" },
    ask: { opts: [{ text: "I'd like to use the bank.", go: "bank" }, { text: "Just looking.", go: "bye" }] },
    bank: { say: "npc", text: "Sign here. And here.", do: [{ open: "bank" }], next: null },
    bye: { say: "npc", text: "Mind the salt on your boots.", next: null }
  } },
  corran: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "crossing_sound", eq: 20 }], go: "register" },
      { if: [{ q: "salt_iron", eq: 30 }, { has: "salt", qty: 10 }], go: "salt_done" },
      { if: [{ q: "salt_iron", eq: 30 }], go: "salt_need" },
      { if: [{ q: "salt_iron", eq: 20 }], go: "salt_wraiths" },
      { if: [{ q: "salt_iron", eq: 10 }], go: "salt_mine" },
      { if: [{ q: "salt_iron", eq: 0 }, { q: "crossing_sound", eq: 100 }, { lvl: "cooking", gte: 40 }], go: "salt_offer" }],
      else: "hi" },
    salt_offer: { say: "npc",
      text: "Our salt pans feed every barrel in this port, and now wraiths walk the Brinemarsh. No salt, no cured fish, no trade.",
      next: "salt_ask" },
    salt_ask: { opts: [{ text: "I'll help.", go: "salt_accept" }, { text: "Not right now.", go: "salt_decline" }] },
    salt_accept: { say: "npc", text: "Mine ten salt from the crusts south of town. A pickaxe does it. Then we'll see about the wraiths.",
      do: [{ stage: ["salt_iron", 10] }], next: null },
    salt_decline: { say: "npc", text: "The barrels will wait. Not long, mind.", next: null },
    salt_mine: { say: "npc", text: "Ten salt from the crusts in the Brinemarsh, south of the gate.", next: null },
    salt_wraiths: { say: "npc", text: "Three bog wraiths drift near the pans. Put them to rest and the rakers will come back.",
      next: null },
    salt_need: { say: "npc", text: "The wraiths are gone? Then bring me ten salt for the barrels.", next: null },
    salt_done: { say: "npc", text: "Ten good salt. Here's the recipe my mother cured with: salt, a hot range, and patience.",
      do: [{ take: ["salt", 10] }, { complete: "salt_iron" }], next: null },
    register: { say: "npc",
      text: "A new face off the Gullwing! Name? ...Written. Welcome to Saltmere, where the fish are fresh and the ledgers honest.",
      do: [{ complete: "crossing_sound" }], next: null },
    hi: { say: "npc", text: "Ships in, ships out, and every crate in my ledger.", next: "ask" },
    ask: { opts: [{ text: "What's in Saltmere?", go: "town" }, { text: "What lies beyond the walls?", go: "beyond" },
      { text: "Goodbye.", go: "bye" }] },
    town: { say: "npc", text: "Osric keeps the counting house, Greta the Salt Wife, Maren the fish stall. The smithy's open to all.",
      next: "ask" },
    beyond: { say: "npc",
      text: "North, Amberwood. East, the Stormcoast shoals. South, the Brinemarsh, and past it a crater where a star fell.",
      next: "ask" },
    bye: { say: "npc", text: "Fair winds.", next: null }
  } },
  greta: { start: "hi", nodes: {
    hi: { say: "npc", text: "Sit, eat, and don't feed the gulls.", next: "ask" },
    ask: { opts: [{ text: "What's cooking?", go: "trade" }, { text: "Can I use your range?", go: "range" },
      { text: "Not hungry.", go: "bye" }] },
    trade: { say: "npc", text: "Swordfish today. Swordfish most days.", do: [{ open: "shop", shop: "salt_wife_inn" }],
      next: null },
    range: { say: "npc", text: "It's by the door. Scrape the pan when you're done.", next: null },
    bye: { say: "npc", text: "The pot's always on.", next: null }
  } },
  maren: { start: "hi", nodes: {
    hi: { say: "npc", text: "Fresh off the boats, or fresh enough.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Where's the fishing good?", go: "where" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Pick your fish.", do: [{ open: "shop", shop: "maren_fish" }], next: null },
    where: { say: "npc", text: "Pell's pier for lobster and tuna. The Stormcoast, out the east gate, is wild water.",
      next: "ask" },
    bye: { say: "npc", text: "Come back before it turns.", next: null }
  } },
  // ----------------------------------------------------------------
  // --------------------------- Southfold --------------------------
  // ----------------------------------------------------------------
  aldo: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "mill_southfold", eq: 100 }], go: "after" },
      { if: [{ q: "mill_southfold", eq: 20 }], go: "done" },
      { if: [{ q: "mill_southfold", eq: 10 }], go: "remind" },
      { if: [{ q: "gnarltooth_tolls", eq: 100 }], go: "offer" }], else: "unready" },
    unready: { say: "npc", text: "I've a job for someone the watch trusts. Help Captain Marrick in Brackenford first.",
      next: null },
    offer: { say: "npc", text: "Jackals. Up from the canyons every night, into my flour and off with my hens.", next: "offer2" },
    offer2: { say: "npc", text: "Thin them out, would you? Five should teach the rest some manners.", next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc",
      text: "East over the bridge, into Redcliff Canyons. Mind the deep end: worse than jackals live down there.",
      do: [{ stage: ["mill_southfold", 10] }], next: null },
    decline: { say: "npc", text: "The jackals thank you.", next: null },
    remind: { say: "npc", text: "Five jackals from Redcliff Canyons. East, over the bridge.", next: null },
    done: { say: "npc", text: "Five fewer jackals! Here: Wyn's pies, and the strongbox key. It opens onto your bank.",
      do: [{ complete: "mill_southfold" }], next: null },
    after: { say: "npc", text: "The sails turn and the flour stays put. Southfold owes you.", next: null }
  } },
  wyn: { start: "root", nodes: {
    root: { branch: [{ if: [{ q: "mill_southfold", eq: 100 }], go: "open" }], else: "closed" },
    closed: { say: "npc", text: "No pies until those jackals stop raiding Aldo's flour. He's at the mill.", next: null },
    open: { say: "npc", text: "Fresh from the oven, and still too hot.", next: "ask" },
    ask: { opts: [{ text: "Let's trade.", go: "trade" }, { text: "Can I use your range?", go: "range" },
      { text: "Goodbye.", go: "bye" }] },
    trade: { say: "npc", text: "Take two, they're small.", do: [{ open: "shop", shop: "wyn_bakery" }], next: null },
    range: { say: "npc", text: "Go on. Just don't touch the pie on the left.", next: null },
    bye: { say: "npc", text: "Mind the flour on the step.", next: null }
  } },
  vesna: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "fallen_star", eq: 100 }], go: "after" },
      { if: [{ q: "fallen_star", eq: 30 }, { has: "starsteel_bar" }], go: "done" },
      { if: [{ q: "fallen_star", eq: 30 }], go: "need" },
      { if: [{ q: "fallen_star", eq: 20 }], go: "smelt" },
      { if: [{ q: "fallen_star", eq: 10 }], go: "mine" },
      { if: [{ q: "embers_beneath", eq: 100 }, { lvl: "mining", gte: 80 }, { lvl: "smithing", gte: 80 }], go: "offer" }],
      else: "unready" },
    unready: { say: "npc",
      text: "A star fell south-east of here. I need a smith who has tamed emberite, with Mining 80 and Smithing 80.",
      next: null },
    offer: { say: "npc", text: "A star fell into the hills beyond the Brinemarsh. Its metal sings, and nobody has worked it.",
      next: "offer2" },
    offer2: { say: "npc", text: "Bring me a bar of it and I'll tell you what it is. The crater is guarded; go armed.", next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Here: my sigil. Touch it to the stone and it will yield. Mine a shard at Starfall Crater.",
      do: [{ stage: ["fallen_star", 10] }], next: null },
    decline: { say: "npc", text: "The star isn't going anywhere.", next: null },
    mine: { say: "npc", text: "Starfall Crater, south-east past the Brinemarsh. Mine one shard of starmetal.", next: null },
    smelt: { say: "npc", text: "Smelt the shard at a furnace with ten coal. It takes a smith of eighty to hold it.", next: null },
    need: { say: "npc", text: "Bring me the starsteel bar. Smelt another if you must.", next: null },
    done: { say: "npc", text: "Starsteel! It rings like a bell. Keep forging; nothing in the kingdom is harder.",
      do: [{ take: ["starsteel_bar", 1] }, { complete: "fallen_star" }], next: null },
    after: { say: "npc", text: "Some nights the crater still glows. Something else fell with that star, I think.", next: null }
  } },
  elin: { start: "root", nodes: {
    root: { branch: [
      { if: [{ q: "amber_grove", eq: 100 }], go: "after" },
      { if: [{ q: "amber_grove", eq: 20 }, { has: "yew_logs", qty: 10 }], go: "done" },
      { if: [{ q: "amber_grove", eq: 20 }], go: "need" },
      { if: [{ q: "amber_grove", eq: 10 }], go: "stalkers" },
      { if: [{ q: "crossing_sound", eq: 100 }, { lvl: "woodcutting", gte: 70 }], go: "offer" }], else: "unready" },
    unready: { say: "npc", text: "These trees are older than Saltmere. Come back when your axe is sure (Woodcutting 70).",
      next: null },
    offer: { say: "npc", text: "Bark stalkers gnaw the amberhearts to the core. If they're thinned out, I'll let you fell one.",
      next: "ask" },
    ask: { opts: [{ text: "I'll help.", go: "accept" }, { text: "Not right now.", go: "decline" }] },
    accept: { say: "npc", text: "Four stalkers, then. They hide among the golden trees, north and east of here.",
      do: [{ stage: ["amber_grove", 10] }], next: null },
    decline: { say: "npc", text: "The wood is patient.", next: null },
    stalkers: { say: "npc", text: "Four bark stalkers. They look like fallen branches until they bite.", next: null },
    need: { say: "npc", text: "Now ten yew logs, to stake the young amberhearts against the wind.", next: null },
    done: { say: "npc", text: "Good yew. I've marked the grove for you: fell an amberheart when you like, and fell it clean.",
      do: [{ take: ["yew_logs", 10] }, { complete: "amber_grove" }], next: null },
    after: { say: "npc", text: "In autumn the storms bring branches down. Keep your eyes open.", next: null }
  } }
};
// ==== src/engine/data/quests.js ====
// ----------------------------------------------------------------
// --------------------- Data: quests and flags -------------------
// ----------------------------------------------------------------
// Quests in hint order (DESIGN.md section 16; the expansion's quests in 16a). Key order drives
// Script.hint. advance[stage] moves to the next listed stage (or 100 after the last). Stage setters that are not an
// advance live in dialogues (accept, hand-ins) and objects (war banner).
// keep: AFK drop/courier modes leave these quest materials in the pack.
Data.quests = {
  hammer_hearth: { name: "Hammer and Hearth", npc: "brenna", qp: 1,
    start: "Speak to Brenna at the smithy in Brackenford.",
    reqs: [], reqText: [], stages: [10, 20, 30],
    journal: {
      10: "Mine copper and tin at Copperdell, then smelt a bronze bar at the furnace.",
      20: "Smith something at Brenna's anvil.",
      30: "Show Brenna your work." },
    advance: {
      10: { made: ["bronze_bar"], msg: "Brenna calls out: 'Good colour! Now the anvil.'" },
      20: { made: ["bronze_axe", "bronze_sword", "bronze_pickaxe", "bronze_helm", "bronze_shield", "bronze_greaves",
        "bronze_breastplate"], msg: "Brenna will want to see that." } },
    hint: { 0: [["npc", "brenna"]],
      10: [["obj", "furnace", [{ has: "copper_ore" }, { has: "tin_ore" }]], ["obj", "tin_rock", [{ has: "copper_ore" }]],
        ["obj", "copper_rock"]],
      20: [["obj", "anvil"]], 30: [["npc", "brenna"]] },
    keep: { 10: [["copper_ore", 1], ["tin_ore", 1]] },
    rewards: { xp: [["mining", 350], ["smithing", 450]], items: [["coins", 250]],
      lines: ["Brenna's smithy is yours to use."] } },

  trouble_dunmoor: { name: "Trouble at Dunmoor", npc: "odo", qp: 1,
    start: "Speak to Farmer Odo at Dunmoor Farm, south of Brackenford.",
    reqs: [], reqText: [], stages: [10, 15, 20, 30],
    journal: {
      10: "Chop 10 logs for Farmer Odo's fence.",
      15: "Bring Farmer Odo 10 logs.",
      20: "Kill 6 goblins ({qc}/6).",
      30: "Return to Farmer Odo." },
    advance: {
      10: { have: ["logs", 10], msg: "That's enough logs for Farmer Odo." },
      20: { kill: "goblin", n: 6, msg: "That's six goblins. Farmer Odo will want to hear." } },
    hint: { 0: [["npc", "odo"]], 10: [["obj", "tree"]], 15: [["npc", "odo"]], 20: [["npc", "goblin"]],
      30: [["npc", "odo"]] },
    keep: { 10: [["logs", 10]], 15: [["logs", 10]] },
    rewards: { xp: [["attack", 500], ["strength", 500], ["woodcutting", 300]], items: [["cooked_chicken", 5]],
      lines: ["Dunmoor's hens are safe again."] } },

  river_courier: { name: "The River Courier", npc: "bram", qp: 1,
    start: "Speak to Bram the Ferryman at Willowmere, north-east of Brackenford.",
    reqs: [{ lvl: "fishing", gte: 20 }, { lvl: "cooking", gte: 15 }], reqText: ["Fishing 20", "Cooking 15"],
    stages: [10, 20],
    journal: {
      10: "Fish the River Wend lure spots until you hook Bram's seal.",
      20: "Bring Bram the seal and 5 cooked trout." },
    advance: {
      10: { have: ["courier_seal", 1], msg: "Bram's seal! Now for five cooked trout." } },
    hint: { 0: [["npc", "bram"]], 10: [["obj", "spot_lure"]],
      20: [["obj", "spot_lure", [{ not: { owns: "courier_seal" } }]], ["npc", "bram"]] },
    keep: { 10: [["raw_trout", 12]], 20: [["raw_trout", 12]] },
    rewards: { xp: [["fishing", 2000], ["cooking", 1500]], items: [["courier_satchel", 1]], do: [{ fullCourier: 1 }],
      lines: ["Courier: full packs can be sent to the bank."] } },

  gnarltooth_tolls: { name: "Tolls of the Gnarltooth", npc: "marrick", qp: 2,
    start: "Speak to Captain Marrick by Brackenford's north gate.",
    reqs: [{ q: "trouble_dunmoor", eq: 100 }, { lvl: "firemaking", gte: 10 }],
    reqText: ["Trouble at Dunmoor", "Firemaking 10"], recCmb: 20,
    stages: [10, 20, 30, 40],
    journal: {
      10: "Kill 4 goblin brutes ({qc}/4).",
      20: "Burn the Gnarltooth war banner.",
      30: "Defeat Skarg the Warchief.",
      40: "Bring Captain Marrick the tusk." },
    advance: {
      10: { kill: "goblin_brute", n: 4, msg: "The brutes are down. Now for their war banner." },
      30: { have: ["skarg_tusk", 1], msg: "Skarg's tusk! Captain Marrick will want this." } },
    hint: { 0: [["npc", "marrick"]], 10: [["npc", "goblin_brute"]], 20: [["obj", "war_banner"]],
      30: [["npc", "skarg"]], 40: [["npc", "skarg", [{ not: { owns: "skarg_tusk" } }]], ["npc", "marrick"]] },
    rewards: { xp: [["attack", 2000], ["strength", 2000], ["defence", 2000]], items: [["coins", 1000]],
      lines: ["The Ironbound gate in the Deeps is open to you.", "Marrick's Armoury is open to you."] } },

  embers_beneath: { name: "Embers Beneath", npc: "ilvara", qp: 3,
    start: "Speak to Ilvara the Sage at the old watchtower in Ashen Reach.",
    reqs: [{ q: "hammer_hearth", eq: 100 }, { q: "trouble_dunmoor", eq: 100 }, { q: "river_courier", eq: 100 },
      { q: "gnarltooth_tolls", eq: 100 }],
    reqText: ["Hammer and Hearth", "Trouble at Dunmoor", "The River Courier", "Tolls of the Gnarltooth",
      "Recommended: Smithing 35, Crafting 20, Firemaking 30."], recCmb: 40,
    stages: [10, 20, 30, 40],
    journal: {
      10: "Forge an Emberward at an anvil: 3 steel bars and a cut sapphire (Smithing 35, Crafting 20).",
      20: "Relight the three Ashen beacons with 5 willow logs or better each (Firemaking 30).",
      30: "Descend through the Deeps and slay Smoulderjaw.",
      40: "Bring Ilvara the Ember heart." },
    advance: {
      10: { made: ["emberward"], msg: "The Emberward is cool in your hands. Ilvara spoke of three beacons." },
      20: { flags: ["beacon_west", "beacon_mid", "beacon_east"], msg: "The sealed door beneath Copperdell groans open." },
      30: { have: ["ember_heart", 1], msg: "The Ember heart pulses in your hand. Ilvara must see this." } },
    hint: { 0: [["npc", "ilvara"]], 10: [["obj", "anvil"]],
      20: [["obj", "beacon_west"], ["obj", "beacon_mid"], ["obj", "beacon_east"]],
      30: [["npc", "smoulderjaw"]], 40: [["npc", "smoulderjaw", [{ not: { owns: "ember_heart" } }]], ["npc", "ilvara"]] },
    keep: { 10: [["iron_ore", 3], ["coal", 6], ["uncut_sapphire", 1]], 20: [["willow_logs", 15]] },
    rewards: { xp: [["hitpoints", 10000], ["smithing", 5000], ["firemaking", 5000], ["crafting", 5000]],
      items: [["heros_mantle", 1]],
      lines: ["Smoulderjaw can be challenged again.", "Emberite can be mined in the Golem Forge."] } },

  // ----------------------------------------------------------------
  // ------------------- Across the Sound (16a) ---------------------
  // ----------------------------------------------------------------
  crossing_sound: { name: "Crossing the Sound", npc: "pell", qp: 1,
    start: "Speak to Pell on Gullhaven's pier.",
    reqs: [{ q: "river_courier", eq: 100 }, { lvl: "fishing", gte: 25 }], reqText: ["The River Courier", "Fishing 25"],
    stages: [10, 20],
    journal: {
      10: "Bring Pell 6 oak logs and 2 iron bars to patch the Gullwing.",
      20: "Board the Gullwing at the end of Gullhaven's pier and report to Harbourmaster Corran in Saltmere." },
    hint: { 0: [["npc", "pell"]],
      10: [["obj", "oak_tree", [{ not: { has: "oak_logs", qty: 6 } }]],
        ["obj", "furnace", [{ not: { has: "iron_bar", qty: 2 } }]], ["npc", "pell"]],
      20: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "corran"]] },
    keep: { 10: [["oak_logs", 6], ["iron_bar", 2]] },
    rewards: { xp: [["fishing", 2500], ["woodcutting", 1000]], items: [["coins", 500]],
      lines: ["The Gullwing ferries you between Gullhaven and Saltmere for free."] } },

  mill_southfold: { name: "The Mill of Southfold", npc: "aldo", qp: 1,
    start: "Speak to Miller Aldo at the mill in Southfold, south of Dunmoor Farm.",
    reqs: [{ q: "gnarltooth_tolls", eq: 100 }], reqText: ["Tolls of the Gnarltooth"], stages: [10, 20],
    journal: {
      10: "Kill 5 canyon jackals in Redcliff Canyons ({qc}/5).",
      20: "Return to Miller Aldo." },
    advance: {
      10: { kill: "canyon_jackal", n: 5, msg: "That's five jackals. Miller Aldo will want to know." } },
    hint: { 0: [["npc", "aldo"]], 10: [["npc", "canyon_jackal"]], 20: [["npc", "aldo"]] },
    rewards: { xp: [["attack", 800], ["strength", 800], ["defence", 800], ["cooking", 600]], items: [["meat_pie", 5]],
      lines: ["Wyn's bakery is open.", "The Southfold strongbox opens onto your bank."] } },

  salt_iron: { name: "Salt and Iron", npc: "corran", qp: 2,
    start: "Speak to Harbourmaster Corran in Saltmere.",
    reqs: [{ q: "crossing_sound", eq: 100 }, { lvl: "cooking", gte: 40 }], reqText: ["Crossing the Sound", "Cooking 40"],
    stages: [10, 20, 30],
    journal: {
      10: "Mine 10 salt from the crusts in the Brinemarsh, south of Saltmere.",
      20: "Kill 3 bog wraiths in the Brinemarsh ({qc}/3).",
      30: "Bring Harbourmaster Corran 10 salt." },
    advance: {
      10: { have: ["salt", 10], msg: "Ten salt. Now for the wraiths that haunt the pans." },
      20: { kill: "bog_wraith", n: 3, msg: "The marsh is quieter. Corran will want his salt." } },
    hint: { 0: [["npc", "corran"]],
      10: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["obj", "salt_crust"]],
      20: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "bog_wraith"]],
      30: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["obj", "salt_crust", [{ not: { has: "salt", qty: 10 } }]],
        ["npc", "corran"]] },
    keep: { 10: [["salt", 10]], 20: [["salt", 10]], 30: [["salt", 10]] },
    rewards: { xp: [["cooking", 4000], ["mining", 2000]], items: [["coins", 1500]],
      lines: ["Curing: salt meat and fish at a range (Cooking 50, 60 and 70)."] } },

  amber_grove: { name: "The Amber Grove", npc: "elin", qp: 2,
    start: "Speak to Woodward Elin in Amberwood, north of Saltmere.",
    reqs: [{ q: "crossing_sound", eq: 100 }, { lvl: "woodcutting", gte: 70 }],
    reqText: ["Crossing the Sound", "Woodcutting 70"], recCmb: 50, stages: [10, 20],
    journal: {
      10: "Kill 4 bark stalkers in Amberwood ({qc}/4).",
      20: "Bring Woodward Elin 10 yew logs." },
    advance: {
      10: { kill: "bark_stalker", n: 4, msg: "Four stalkers down. Elin wants yew logs next." } },
    hint: { 0: [["npc", "elin"]],
      10: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "bark_stalker"]],
      20: [["obj", "yew_tree", [{ not: { has: "yew_logs", qty: 10 } }]],
        ["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "elin"]] },
    keep: { 20: [["yew_logs", 10]] },
    rewards: { xp: [["woodcutting", 8000], ["firemaking", 4000]], items: [["amber_logs", 5]],
      lines: ["Elin lets you fell the amberheart trees."] } },

  fallen_star: { name: "Fallen Star", npc: "vesna", qp: 3,
    start: "Speak to Astronomer Vesna in Saltmere.",
    reqs: [{ q: "embers_beneath", eq: 100 }, { lvl: "mining", gte: 80 }, { lvl: "smithing", gte: 80 }],
    reqText: ["Embers Beneath", "Mining 80", "Smithing 80"], recCmb: 70, stages: [10, 20, 30],
    journal: {
      10: "Mine a shard of starmetal at Starfall Crater.",
      20: "Smelt a starsteel bar at a furnace (Smithing 80, 10 coal).",
      30: "Bring Astronomer Vesna the starsteel bar." },
    advance: {
      10: { have: ["starmetal_ore", 1], msg: "The shard hums against your palm. Now to smelt it." },
      20: { made: ["starsteel_bar"], msg: "Starsteel! Vesna must see this." } },
    hint: { 0: [["npc", "vesna"]],
      10: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["obj", "starmetal_rock"]],
      20: [["obj", "furnace"]],
      30: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "vesna"]] },
    keep: { 10: [["starmetal_ore", 1]], 20: [["starmetal_ore", 1], ["coal", 10]], 30: [["starsteel_bar", 1]] },
    rewards: { xp: [["mining", 15000], ["smithing", 20000]],
      lines: ["Starsteel can be smelted and smithed (Smithing 80 to 99)."] } },

  hollow_king: { name: "The Hollow King", npc: "ilvara", qp: 4,
    start: "Speak to Ilvara the Sage at the old watchtower in Ashen Reach.",
    reqs: [{ q: "fallen_star", eq: 100 }], reqText: ["Fallen Star", "Recommended: combat 85."], recCmb: 85,
    stages: [10, 20, 30],
    journal: {
      10: "Kill 3 hollow knights in Duskhollow Ruins ({qc}/3).",
      20: "Defeat the Hollow King in his keep and take his seal.",
      30: "Bring Ilvara the King's seal." },
    advance: {
      10: { kill: "hollow_knight", n: 3, msg: "The keep's doors grind open. Something stirs on the throne." },
      20: { have: ["kings_seal", 1], msg: "The seal is cold as a grave. Ilvara must see it." } },
    hint: { 0: [["npc", "ilvara"]],
      10: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "hollow_knight"]],
      20: [["obj", "ferry_gullhaven", [{ in: ["overworld", 0, 0, 95, 143] }]], ["npc", "hollow_king"]],
      30: [["npc", "hollow_king", [{ not: { owns: "kings_seal" } }]], ["obj", "ferry_saltmere", [{ in: ["overworld", 96, 0, 159, 143] }]],
        ["npc", "ilvara"]] },
    rewards: { xp: [["hitpoints", 20000], ["attack", 10000], ["strength", 10000], ["defence", 10000]],
      items: [["hollow_crown", 1]], lines: ["The Hollow King waits on his throne for any who return."] } }
};
Data.flags = ["beacon_west", "beacon_mid", "beacon_east", "lair_ok"];
// ==== src/engine/data/terrain.js ====
// ----------------------------------------------------------------
// ------------------- Data: terrain and legend -------------------
// ----------------------------------------------------------------
// Walkability per DESIGN.md 17.4. Legend chars are global: punctuation is bare terrain, letters are
// an object on the terrain it implies. Unique objects (ladders, shrine, quest objects, gates) come
// from each map's place list instead.
Data.terrain = {
  grass: { walk: true }, grass_dark: { walk: true }, dirt: { walk: true },
  path: { walk: true }, sand: { walk: true }, water: { walk: false, water: true },
  deep_water: { walk: false, water: true }, wood_floor: { walk: true }, stone_floor: { walk: true },
  ash: { walk: true }, swamp: { walk: true }, bog: { walk: false, water: true }, wall: { walk: false },
  fence: { walk: false }, bridge: { walk: true }, cave_floor: { walk: true },
  cave_wall: { walk: false }, lava: { walk: false }, void: { walk: false }
};
Data.legend = {
  ".": { t: "grass" }, ",": { t: "grass_dark" }, ":": { t: "dirt" }, "=": { t: "path" }, "_": { t: "sand" },
  "~": { t: "water" }, "-": { t: "deep_water" }, ";": { t: "wood_floor" }, "[": { t: "stone_floor" },
  "%": { t: "ash" }, "!": { t: "swamp" }, "$": { t: "bog" }, "#": { t: "wall" }, "+": { t: "fence" }, "]": { t: "bridge" },
  "*": { t: "cave_floor" }, "^": { t: "cave_wall" }, "{": { t: "lava" }, " ": { t: "void" },
  "T": { t: "grass", o: "tree" }, "O": { t: "grass", o: "oak_tree" }, "W": { t: "grass", o: "willow_tree" },
  "M": { t: "grass", o: "maple_tree" }, "Y": { t: "swamp", o: "yew_tree" }, "y": { t: "ash", o: "yew_tree" },
  "I": { t: "ash", o: "ironbark_tree" }, "c": { t: "dirt", o: "copper_rock" }, "t": { t: "dirt", o: "tin_rock" },
  "i": { t: "dirt", o: "iron_rock" }, "k": { t: "dirt", o: "coal_rock" }, "g": { t: "dirt", o: "gold_rock" },
  "K": { t: "cave_floor", o: "coal_rock" }, "G": { t: "cave_floor", o: "gold_rock" },
  "J": { t: "cave_floor", o: "gem_rock" }, "C": { t: "cave_floor", o: "cobalt_rock" },
  "V": { t: "cave_floor", o: "verdite_rock" }, "E": { t: "cave_floor", o: "emberite_rock" },
  "B": { t: "wood_floor", o: "bank_booth" }, "F": { t: "stone_floor", o: "furnace" },
  "A": { t: "stone_floor", o: "anvil" }, "R": { t: "wood_floor", o: "range" }, "b": { t: "grass", o: "bush" },
  "d": { t: "grass_dark", o: "bush" }, "f": { t: "grass", o: "flowers" }, "h": { t: "dirt", o: "wheat" },
  "x": { t: "dirt", o: "crate" }, "X": { t: "wood_floor", o: "crate" }, "Q": { t: "cave_floor", o: "crate" },
  "q": { t: "sand", o: "crate" }, "l": { t: "dirt", o: "barrel" }, "L": { t: "wood_floor", o: "barrel" },
  "u": { t: "sand", o: "barrel" }, "P": { t: "cave_floor", o: "barrel" }, "r": { t: "dirt", o: "rubble" },
  "a": { t: "ash", o: "rubble" }, "U": { t: "cave_floor", o: "rubble" }, "e": { t: "wood_floor", o: "table" },
  "z": { t: "wood_floor", o: "counter" }, "s": { t: "cave_floor", o: "stalagmite" },
  "j": { t: "cave_floor", o: "torch" }, "H": { t: "grass", o: "statue" },
  "w": { t: "grass", o: "well" }, "D": { t: "water", o: "boat" }, "m": { t: "dirt", o: "tent" },
  "Z": { t: "dirt", o: "sunstone_rock" }, "N": { t: "grass_dark", o: "amberheart_tree" },
  "n": { t: "sand", o: "salt_crust" }, "S": { t: "cave_floor", o: "starmetal_rock" },
  "0": { t: "stone_floor", o: "torch" }
};
// ==== src/engine/data/regions.js ====
// ----------------------------------------------------------------
// ------------------------ Data: regions -------------------------
// ----------------------------------------------------------------
// First match wins (DESIGN.md 17.2 then 17.3 order). Rects are inclusive [x0, y0, x1, y1]. The regions
// after the River Wend are the east and south lands (DESIGN.md 17.2a).
Data.regions = [
  { id: "brackenford", name: "Brackenford", map: "overworld", rect: [40, 40, 57, 57], town: true },
  { id: "copperdell", name: "Copperdell Mine", map: "overworld", rect: [14, 18, 35, 33] },
  { id: "hollowpine", name: "Hollowpine Wood", map: "overworld", rect: [4, 36, 37, 61] },
  { id: "dunmoor", name: "Dunmoor Farm", map: "overworld", rect: [34, 62, 59, 86] },
  { id: "willowmere", name: "Willowmere", map: "overworld", rect: [66, 30, 77, 44] },
  { id: "gnarltooth", name: "Gnarltooth Camp", map: "overworld", rect: [66, 4, 87, 24] },
  { id: "gullhaven", name: "Gullhaven", map: "overworld", rect: [74, 52, 87, 70] },
  { id: "shellback", name: "Shellback Shore", map: "overworld", rect: [80, 72, 87, 93] },
  { id: "gloomfen", name: "Gloomfen", map: "overworld", rect: [2, 64, 30, 93] },
  { id: "greyspire", name: "Greyspire Quarry", map: "overworld", rect: [40, 2, 52, 10], danger: true },
  { id: "ashen_reach", name: "Ashen Reach", map: "overworld", rect: [0, 0, 59, 15], danger: true },
  { id: "river_wend", name: "River Wend", map: "overworld", rect: [62, 0, 63, 135] },
  { id: "saltmere", name: "Saltmere", map: "overworld", rect: [104, 38, 130, 58], town: true },
  { id: "amberwood", name: "Amberwood", map: "overworld", rect: [106, 2, 152, 32] },
  { id: "stormcoast", name: "Stormcoast", map: "overworld", rect: [138, 38, 156, 70] },
  { id: "brinemarsh", name: "Brinemarsh", map: "overworld", rect: [104, 62, 134, 94] },
  { id: "starfall", name: "Starfall Crater", map: "overworld", rect: [135, 76, 156, 106], danger: true },
  { id: "duskhollow", name: "Duskhollow Ruins", map: "overworld", rect: [106, 110, 154, 139], danger: true },
  { id: "southfold", name: "Southfold", map: "overworld", rect: [38, 98, 60, 114], town: true },
  { id: "brightwater", name: "Brightwater Bay", map: "overworld", rect: [36, 116, 60, 140] },
  { id: "redcliff", name: "Redcliff Canyons", map: "overworld", rect: [66, 98, 90, 118] },
  { id: "redcliff_depths", name: "Redcliff Depths", map: "overworld", rect: [66, 119, 90, 137], danger: true },
  { id: "sunken_vale", name: "Sunken Vale", map: "overworld", rect: [2, 100, 34, 137] },
  { id: "lair", name: "Smoulderjaw's Lair", map: "deeps", rect: [36, 34, 47, 45],
    danger: true, freeze: true, graveAt: ["deeps", 34, 39] },
  { id: "cinder_hall", name: "Cinder Hall", map: "deeps", rect: [25, 30, 33, 40], danger: true },
  { id: "golem_forge", name: "Golem Forge", map: "deeps", rect: [34, 0, 47, 20], danger: true },
  { id: "emberdeep", name: "Emberdeep", map: "deeps", rect: [25, 0, 47, 47], danger: true },
  { id: "upper_deeps", name: "Upper Deeps", map: "deeps", rect: [0, 0, 23, 23] },
  { id: "lower_deeps", name: "Lower Deeps", map: "deeps", rect: [0, 25, 23, 47] }
];
// ==== src/engine/data/map_overworld.js ====
// ----------------------------------------------------------------
// ---------------- Data: overworld map (160x144) -----------------
// ----------------------------------------------------------------
// 160x144, x east and y south. Brackenford sits in the old 96x96 heart; roads run to every region
// (DESIGN.md 17.2). The River Wend is x62-63 and runs on to the south coast. Gull Sound (deep water,
// x88-103) separates the old kingdom from the east; the Gullwing ferry crosses from Gullhaven's pier
// to the Saltmere jetty. The south lands start at y96.
Data.maps.overworld = {
  name: "Kingdom of Orcadia",
  rows: [
    ":::::%%%%%%%:%%%%%%%%%%%:%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%~~...........b...b...,,___---------------~~_________________________________________________~~----", // 0
    "::%%%%%%%%%%:%%%%%%%%I%%%%%%%%%%%%a%%%%%%%%%%%%%%%%%%%%%%%%%%%~~.........b..........,__~---------------~~_,,,,,......b..,,,,,..,,,,d,d...,,.......b......_~~----", // 1
    ":%%%%%%%%%y%:%%%%%I%%%%%%%%%%%%%%%%%%%%%%%:::::::k:%%%%%%%%%%%~~b................b...__~---------------~~~_,,,,......,,.,,,,,d,,,,,,,,,,,,,,,,,,,,,......_~~----", // 2
    ":%%%%y%%%%%%%%%%%%%%%%%%I%%:%%%%%%%%%%%%%::::g::::::%%%%%%a%%~~~..b..b..b.....b......___---------------~~~_,,,,,,d,,,,,,,,,,,,,,,,d,,,,,,,,,,,d,,,,d...,,_~~----", // 3
    ":%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%:g::::::::k:%%%%%%%%~~~~....................___---------------~~~_,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,...,,_~~----", // 4
    ":%%%%%%%%%%%%%%::%%%I%%%%%%%%###%:%%a%%%%:::::::g::::%%%%%%%%~~~~........+++++++++....__---------------~~_,d,,,,,,,,,,,,,,,,,,,,,,,,d,,,,,d,,,,d,,,,,d,,_~~~----", // 5
    ":%%%%%%%%%%%%y%::%%%%%%%%%%%#[[[#:%%%%%%:::::::::::::%%%%%%%%%~~~......++m:::::::+++..__---------------~~_,d,,,,,,,,d,,,,,,,,,,,N,,,,d,,,,,,,,,,,,,,,,,,_~~~----", // 6
    "%%%%%%%%%%%%%%%%%%%%%%%%%%%#[[[[[#%%%%%:::::g::::::::%%%%%%%%%~~~....+++:::::::::::++.__---------------~~_,,,,,d,,d,,,,,d,,,,,,,,,,,,,d,,,,,,,,,d,,,,,,,_~~-----", // 7
    "%%%%%%%%%:%%%%%%%%%%%%%%:%%#[[[[[#%%%%%%:k::::::::g:%%%%%%%%%~~~~...++::::::::::::::++__---------------~~_,,,,,,,d,,,,,,d,,,,,,,,,,,,,,,,,,,d,,,N,,,,,,,_~~-----", // 8
    "%%%%y%%%%:%%%%%%%%%%%%%:r:%#[[==[#%%%%%%:::::::g::::%%%%%%%%%~~~,,,.+:m:::::m::::::::++_---------------~~_,,,,,,,,,,,,,,,,,,,,,,,,,,,d,,,,,,,,,,,d.,,,,,_~~-----", // 9
    "%%%%%%%%%%%%%%%a%%%%%%%:::%%#[==#%%%%%%%%::k::::::a%%%%%%%%%%~~~,,,++::::::::::::::mm:+~---------------~~~_,,,,,d...,,,,d,,,,,,d,,,,,,,,N,,,,,,,,d,,,,,,_~~-----", // 10
    "%%%%%%%%%%%y%%%%%%%%%%%:::%%%===%%%%::%%%%%%%%::%%%%%%%%%%%%%~~~~,,+:::::::::::::::mm:+~---------------~~~_,,,,d.....,,...,,,,d,,,,,,,,d,,........,....,_~~-----", // 11
    "%%a%%%%%%%%%%%%%%%%%%%%::::%%%==%%%::r%%%%%%%%r:%%%%%a%%%%%%%%~~~,.+:::::::::::::::::::~----------------~~_,,,,d....N.....,d,,,dd,,,,,,,,d..d.....,,..d,_~~-----", // 12
    "%%%%%%%%%a%%%%%%%%%%%%%%%%a%%%==%%%%%%%%%%%%%%::%%%%%%%%%%%%%%~~~..+:::::::::::::::::::~----------------~~_d,,,,.....d....,,d,,,,,,,,,,,,........,,,,,,,_~~-----", // 13
    "%%%%%%%%%%%%%%%%%a%%%%%%%%%%%%==%%%%%%%%%%%%%%::%%%%%%%%%%%%%%~~..++:::::::::::::::::::~---------------~~~_,,,,...........,,,,,,,d,,,,,,,...d..,,,,,,..d_~~-----", // 14
    "%%%%%%%%%%%%%%%%%%:%%%%%%%%%%%==%%%%%%%%%%%%%%::%%%%%%%%%%%%%%~~..++::::::::::::::::::++---------------~~~_.,.....ddd....,d,,dd,,,,,dd,,,dd...,,d,,,,..._~~-----", // 15
    "%%...%%%....b....,,,%%%....,%%==%%%%.%%%%%.b..::...........%%%~~...+:::m::::::::::m:::+_---------------~~_.....d.........,,,,,,,,,,,,,,,,,...,,,,,,,,..d_~~-----", // 16
    "......%.bf........,,%%%,...,,:==:::,f.%%%....f::..f.b.b.....%%~~...++::::::::::::::::++_---------------~~_.............,d,,,,,,,,,,,,,,.,,...,,,,,,,,N.,_~~-----", // 17
    ".............f...:::r::,.::.::==:k::,.........::..............~~....+:::::::::m:::::++_~---------------~~_....d........,,,,,,,,,,,,,,,,.,,...,,,,,,,,..._~~-----", // 18
    "....b......b..f.::::::::::::k:==::::,.........::bf.~~~...b....~~,,,.++::::::::::::::+._~---------------~~_......d.dd...,,,,,,.d,,,,,,,,.....,,,,d,,,.dd._~~-----", // 19
    "b..............:::i::::::::r::==::::,.f.......::f.b~~~~.....==]]=====::::::::::::::++__~---------------~~_............,,,,,.d...,,,d,,,.....N,,,,,,,...._~~-----", // 20
    "...............::::::i::r:::::==::k:,.b.......::...~~~...b..==]]======:::+:::::::+++.__~---------------~~_.........d.d.,,,,,....,,,,,,,d......,,,,,....._~~-----", // 21
    "..............::i:::::::::::k:==::::,........,::............==~~,,,,..f..+++::++++...__~---------------~~_,,..d,.......,,,,::....d,,,,,..d............._~~~-----", // 22
    "d,.....f......::::::::i:::x:::==::::,.......,,::.....,,,,...==~~,,,,,,,,,,,,::..f....._~---------------~~_,,,.,,,......d,,,::...d,,,,,ddd.d...........d_~~~-----", // 23
    ",,,,.....d,,..:::::i::::::l:::==:::::.......,,::,...,,,,,,.===~~,,,,,,,,,,.:::..f....._~---------------~~_,,,,,,,.....,,,,:::d...,,,,,,........d.d....d_~~~-----", // 24
    ",,,,~~~~,,,,,,:r::::::::::::::==::r::.......,,::,,,,,,,,,,===.~~,,,d,,,,,,:::.......f.__---------------~~~_,,,,,,....,,,,,::,....,,,,,,d.d............._~~~-----", // 25
    ",,,,~~~~~,,,,::::i:::::::=================f.,,::,,,,,,,,,===..~~,,,,,,,,,,::b.........__---------------~~~_,,,,,,...,d,,,,::.....,,,,,,,....,.....d....._~~-----", // 26
    ",,,,~~~~,,,,::::::::r::::==================.,,::,,,,,,,,===...~~,,,,,,,,,:::,........._~----------------~~_,,,,,,,d.,,,,.,::....,,,,,,,,....,......d...d_~~-----", // 27
    ".d,,,,,,,d,,::::::::::c::t::c::t::::,,...===,,::,,,,,,,===.W..~~........:::,,,..f....._~----------------~~_,,,d,,,,,,,,,.d::....,,,,,,,d...,d,..d......._~~-----", // 28
    "...,,,,,,,,,,::::::x::::::::::::::,,,,,,,,===,::,,,,,,===.....~~........::,,,,.f.....___----------------~~_,,,,dd,,,,,,.d:::....,,,,,,,d,..,,,.........._~~-----", // 29
    "...,,,,,,,,,,:,,:::::::t::c::t::cf,,,,,,,,,===:::,,,,===,....f~~.......:::,,,,...b..f___----------------~~_,,,,,,,,,,dd..::.....,,,,,,,,,,,,,,.........,_~~-----", // 30
    "...d,,d,,,,,,,,,::l:::::::::::::..,,,,,,,,,,===::...===,,...W.~~....___::__,,,....f..___----------------~~_,,,,,,,,,,,...::.....,,d,,,,,,,d,,,......,,,,_~~-----", // 31
    "b,,,,,,,,.....,,..::x:::c::t::c:.t,,,,,,.....===:..===...f..f.~~b..__~~~~~___f.......___----------------~~_,,,,,d,,,,,,..::,....,,,,,,,,,,,,d,,,..,,,,,,_~~~----", // 32
    ",,,,,,,,....b......::::::::::::..,,,,,,.......===.===.........~~..f_~~~~~~~~_.........__----------------~~_.,,,,,,,,,,,..::.....,,,..,,d,,,,,,,,,.,,,,,,_~~~----", // 33
    ",,,d,,,,b.b.ff........::b..::fb.,,,,,,.........=====..b..fW...~~..._~~~~~~~~__........__----------------~~_.b.,,,,,,,....::,,...,,...,,,,,,,,,....,.d,,.._~~----", // 34
    ",,,,,,,,....b..,...b......,d,,,,,,d,d,d..b..b,..===...........~~..__~~~~~~~~~_.b......__----------------~~_....,,,,,,...:::,,,,,,,.....,,,,,,,,..,,,,,,.._~~----", // 35
    ",,,,d,d,..f...fb.......b.b,,,,d,d,,,,,,......,..==.f...b.f..W.~~.._~~~~~~~~~~_....b...__----------------~~_.....,,,,....::,d,,,,,,......,,,d,,,,...,,,,,,_~~----", // 36
    ",,,,,,,,,.b...,,,....b....,,,,,,,,,,,,,b....,,,.==............~~.._~~~~~~~~~~_...~~~..__----------------~~_.............::b,d,,,,,......,,,,,,,,,b..,,,,d_~~----", // 37
    ",,,,d,d,,..,,,,,,...,,,..b,,,,,,,T,,,d,.....d,..==.........W..~~..__~~~~~~~~~_b.~~~~~d__----------------~~_.............::....b,,,..b..,,__,,d,__,_...____~~----", // 38
    ",,b,,,,,d,,,,,d,,..,,d,O..,,,,T,,,,,,,,....,,,,,==............~~..._~~~~~~~~__...~~~,,_~----------------~~_,............::...........,,,_______.......____~~----", // 39
    ",,f,,d,,,,,,,,,,,,.O,,,,..,,,,,,,,,,T,,.########==########....~~..._~~~~~~~__......b,,_~----------------~~_d,,,.########==#######..,,,,,_____..........___~~----", // 40
    ",,....,,,M,,,,,,,d,,,,,,,,.O,,,,,,,,,,d.#==========#######....~~..._~~~~~~__........,___----------------~~_,d,..#f.....f==f....f#.b,,,,,_____.........___~~~----", // 41
    ",,,b....,,,d,d,,,,,,,,,d,,f.,d,T,,,,,...#==#######=#z;;X##....~~..._~D_____..f.b...,,___--------------~~~~_,....#.######==.######...,,,,,___....__.._____~~~----", // 42
    ",,,..M..,,,,,,,,,,,d,O,,,O..,,,,,,T,,,,.#==#;BBBz#=#;;;;##....~~..==___...........,,,___--------------~~~~_,....#.#BBB;#==.#F[[##...,,,,,_.....________._~~-----", // 43
    ",,,,...,,,d,M,,d,,,,,,,,,..d,d,,,,,,,T,.#==#;;;;;#=###;###....~~..==.b...d,,,,,d,,,,,,__--------------~~__,,....#.#;;;;#==.#[[A##....d,,,,...._________._~~-----", // 44
    ",,,,,..,,,,,,,,,,,d,,,,b..,,,,,,T,,,,,,.#==#;;;;;#=======#....~~..==..,,,,,,,d,,,,,,,,__--------------~~_,,,....#.#;;;;#==.#[[[##..b.,,,,,,...._______.._~~-----", // 45
    ",,,,,,d,,,,,,,d,,,,,d=========d,,,,T,,..#l:#####;#=#####=#..,.~~b.==..,,,,,,,,,,,,,,,___--------------~~_,,,...d#.###;##==.#[####....,,,,,,_.._____.__.._~~-----", // 46
    ",,,,,,,,,b,,d::::::::==========,,,,,,,,.#:::::x====#;;e#=#.,,,~~..==..,,,,,,,,,d,d,,d___--------------~~_,,,,.,,#.......==......#,...,,,,,,________....__~~-----", // 47
    ",,,,,d,,.::::::::::::::,d.,,,============::::::====##;##======]]====..,,,,,,,,,,,,,,,___--------]]]]]]]]=============================,,,,,,,_______....__~~-----", // 48
    ",,,d,,,,d:::::d,,,,,,,,,,,d,d,================================]]===...,,,,d,,,,,d,,d.___--------]]]]]]]]==================================,,_______...._~~~-----", // 49
    ",,,,,M,,,,,,,,,,,,,,,,:O,,,,,,,,,.d,,,.b#f###[##==f##;####,,,,~~.===..,,,,,,,,,___,.____--------------~~_,,,,,,,#.....w.==......#,,.==========_____...__~~~-----", // 50
    ",,d,,,,,d,,,M,,,,,,O,::,,d,,,d,T,.f,,T..#.#F[[[#==.#;;;R##,,,,~~..====...,,,,d,_________--------------~~_,,,,,,,#.##;###==.#;####,,,,,d,,=======___...._~~------", // 51
    ",,,,d,,,,,,,,,,.,,,,,:,d,,,O,,,,,.T,,,..#w#[[AA#==H#e;;;##....~~...====.......____####__--------------~~_,,,,,,,#.#;;;;#==.#;;;##,,,,,,,,,,..=====_...__~~------", // 52
    ",,,,,,,,,M,d,d,.,,,,,:,,,,,,,,,,,,,,,d.b#.#[[[[#==.#L;;e##....~~...f.===...#####__#;X#__--------------~~_,,,,,,,#.#;;;;#==.#;;X##,,,,,,,,,,....===__..__~~------", // 53
    "....b,,d,,,,,,..,,d,,O,...,d,d,,T,,,,...#f######==f#######..W.~~......===..#e;L#__#;;#__--------------~~~_,,d,,,#.#R;;e#==.#;;X##,,,,,,,,,.__.._..______~~------", // 54
    "..b..,,,,,,,,,bf,,,,::,,.O,,,,,,,,,T,d..#================#....~~.......===.#;;;#__#;##__--------------~~~_,,,,,,#f######==.####f#,,,,,,,,,______..._____~~------", // 55
    "....b,,d,d,d,,..,d,,:d,,,,...,,,,d,,,,.b#f.f..f.==.f..f.f#....~~~.......===##;##________---------------~~_,,,,,,########==#######,d,,,,d,._____...._____~~------", // 56
    "...,,,,,........,,,,:.,,,,....T,,,,,,,..########==########.W..~~~........===___u_q______---------------~~_,,,,,,,,,,,,,.==.....b,,,,,,,,..____....______~~------", // 57
    "...d,,,d,,d,,,d,,d,::,d,,d...,,,,T,,T,bf........==............~~~.........=====_________---------------~~_,.....,,,,,,..==.......,,,,,,,..____......____~~~-----", // 58
    "...,,,,,,,,,d,,,,,::,.,,,,,,,,,,,.,,,,..........==......f.....~~~........._=====________---------------~~_.....,d,,,,...==....b...,,,,,,,.___.........__~~~-----", // 59
    "...,d,,,,,,,,,,,,d:d.b,d,,,,,,,,,b..,.,.........==,.....f...W.~~~.........____===___~D~~---------------~~_.....,,,,,,...==........,,,,,,,._______.....___~~-----", // 60
    "...,,,,,d,,,...,,.:.,,,,,d,d,,,,,....=============............~~~........._____==_u_~~~~---------------~~_!!...d,,,,,...==.!!!!....,,,!!.._______......__~~-----", // 61
    "b.b,,d,,,,d....d,::b,,,..,,,,d,d,b..==============............~~~........._____===__]]]]]]-------------~~_!!!...!!,,...;==!!!!!!!...!!!!.._____.....___._~~-----", // 62
    "...........!!!.,::!!.b.b...b.....,,===.....................W..~~~.........______==__]]]]]]-------------~~_________!$$$!;;!!$$!!!!!!!!!!............_____~~~-----", // 63
    ".........b!!!!.d:!!d....f........,==++++++++++++..+++++++f.,,.~~~...f....._##;##==q_~~~~---------------~~_n__n__n_!$$$!;;!!..!!!!!!!!!!............_____~~~-----", // 64
    "...bf..!!!!!!!!!:,,,,!..b.b.b....,==+::::::++.........f.+,,,,,~~.........._#;;;#==__~D~~---------------~~_________!$$$!;;!!!!!!!!!!!!!!.._........._____~~~-----", // 65
    "..!!!!!!!!!!!!!::d,,,!!!!,!!!....d==:::::::++...........+.,,W,~~.f.........#e;;#==______---------------~~~________$$$$!;;!!!!!!$$!!!!!...___......____._~~~-----", // 66
    "b.!!!!!$$$$!!!::,,,,,!!!!,,!!b..,,==:::::::++...........+..,,,~~~..........#;;L#==______---------------~~~_n__n___$$$$!;;!!!!!!$$$$!!!....____....____.._~~-----", // 67
    "..!!!!!$$$$$!!:,,,,,,!!!!,,!!,,,d,==+::::::++...........+..,,,~~~.........,#####==______---------------~~~________$$$$$;;!!!!!!$$!!!!...._____...._____._~~-----", // 68
    ".b!!!!!!$$$!!!:!!!!!!!!!!!!!!!!,,,==+++++++++...........+..,,,~~~........,,_____==______---------------~~_________$$$$$;;!!!!!!$$!!!!...._____...______._~~~----", // 69
    "..!!,,!!!!!!!!!!!!!!!!!!!!!!!!!!d,==,....f..+...........+..,,,~~.b.......,,,,,__==______---------------~~_n__n__n_$$$!!;;!!!!!!$$!!!!........_.._____,.._~~~----", // 70
    "..!!!!!!!!!!!!!!!!!!!!!!!!$$$!!!,,==,f.f....+...........+...,,~~...b.....,,,,,,,==______---------------~~_________$$!!!;;!!!!!!$$$!!!!.........,d,,,,,,,,_~~----", // 71
    "b.,,!!!!!!,!!!!!!!!!!!!!!$$$$$!!!.==.......f+...........+....~~~.........,,,,,,.==______---------------~~~________$$!!!;;!!!!!!$$$!!!!!........,,d,,,,,,,_~~----", // 72
    "..,d!!!!!!!!!!!!!!!!!!!!!,$$$!d!!b==f######.+f..........+....~~~.bf...,,,,d,,,._==______---------------~~~_!!!!!$$$$!!!;;!!!!!!$$$!!!!!!......,,,,,d,,,.b_~~----", // 73
    ".b,,,,!!!!!!!!!!!!!!!!!!!,!!!!,!..==.#L;;e#.+++++++++++++....~~~....,,,,,,,,,b.________~----------------~~_!!!$$!!!!$!!;;!!!!!!!$$!!!!!!!....b,,,,,,d,..._~~----", // 74
    "..,,,,,!!!!!,,!!!!,,,!!!!,!!!!,!..==.#;;;;#...........,,.....~~~....,,,,,,,,,._________~----------------~~_!!!!!!!!!!!!;;!!!!!!!!!!!!!!!!%....,,,,,,,,,.._~~----", // 75
    ".b!$$$!!!!!!!!!!!!!,,!!!!!!!!!,!..==.#;;;;#.fhhhhhhhh:::::...~~~.b.b,,,d,,,,,._________~----------------~~_$!!!!!!!!!!!;;!!!!!!!!!!!!!!!!%%...d,,,,,,,,,_~~~----", // 76
    "!!!$$$!!!!!!!!!,!!!!,,!!!!!!!!!!!.==.#X;;;#..::::::::m::l:...~~~....,,,,,,,,,,__________----------------~~_$!!!!!!!!!!!;;!!!!!!!!!!!!!!%%%%%..%%%...,%%%%~~~----", // 77
    "!!$$$$!!!!!!!$$,!!!!,!!!!!!!!!!!!.==.###;##..hhhhhhhh:::::...~~~.....,,,,,,,,,__________----------------~~!!!!!!!!!!!!!;;!!!!!!!!!!!!!!%%%%%%%%%%%%%%%%%%~~~----", // 78
    "!!!$$$!!!!!!$$$$$!!!!!!!!!!!!!!!!.==f.::::::.hhhhhhhh:::::...~~~.b....b...,,,,__________----------------~~$!!!!!!!!!!!!;;!!!!!!!!!!!!!%%%%%%%%%%%%%%%%%%%~~~----", // 79
    "b.!$$$!!!!!!$$$$$,d!!!!!!!!!!!!!b.==..::::::.::::::::::::x...~~~..........,d,,_________~---------------~~~$!!!!!!!!!!!!;;!!!!!!!!$$!!!%%%%%%%%%%%%%%%%%%%%~~----", // 80
    "..!!!!!!!!!!$$$$$,,!!!!!!!!!!!!!..==..::::::.hhhhhhhh:::::...~~~....f........,_________~---------------~~~_!!!!!!!!!!!!;;!!!!!!$$$!!!!%%%%%%%%%%%%%%%%%%%%~~----", // 81
    ".b,,!!!!,,,,,,!!!!!!!!!!!!!!!!!!..====::::::.........l::::....~~b........b...._________~---------------~~_!!!!!!!!!!!!!;;!!!!$$$$$$!!!%%%%%%%%%aaaaa%a%%%%~~----", // 82
    "..,d!!!!,,,,,!!!!!!!!!!!!!!!!!.....=======================,...~~..............__________---------------~~_!!!!!!!!!!!!!;;!!!!$$$$$$$$%%%%%%%aaaaaaaaaa%%%%~~----", // 83
    "b.!!!!!d,Y!!!!!!!!!!!!!!!!!!!b.......=======================,,~~.b.......f...:::________---------------~~_!!!!!!!!!!$!!;;!!!!$$$$!$$$%%%%%aaaa*******aaa%%~~----", // 84
    "..!!!!!,,!!!!!!!!!!,d!!!!!!,,........f.......==..,,,,,,,,====,~~........b.::::::________---------------~~_!!!!!!!!!!!!!;;!!!$$$$$$$$$%%%%%aa***********aa~~~----", // 85
    "..!!!!Y!!!!!!!!!!!,,,!!!!!!!!!...............==..,,,,,,,,,,===]]===:::::::::::.________~---------------~~_!!!!!!!!!!!!!;;!!!$$$$$$$!!%%!%%a******S******a~~~----", // 86
    "..,,!!!!!!!!!!!!!,,,!!!!!!!!!..b.......,,...b==.d,,,,,,,,,..==]]===::::::::...._________---------------~~_!!!!!!!!!!!!!;;!!!!$$$$$$!!!%%%aa*************aa~-----", // 87
    "..,,!!!!!!!Y!!!$$$d,!!!!!!!!!......b..,,,,,.f==,,,,,,.........~~..............._________--------------~~~_!!!!!!!!!!!!$;;!!!!!$$$$!!!!!%%a**************~a~-----", // 88
    "ff!!!!!!!!!!!!$$$$$!!!!!!!!!!........d,,,,,,,==,,,,,,.....b...~~..........,,,,,_________--------------~~~_!!!!!!!!!!!!$;;!$!!!!$$$!!!!!!aa*****S***S****~aa-----", // 89
    ".f!!!!!Y!!!!!!!$$$$!,!!!!,!!!........,,~~~~,,==,,,,,..f....f..~~..........,,,,,_________--------------~~_!!!!!!!!!!!!!$;;$$$$!!$$$!!!!!!!a***************aa-----", // 90
    "b.!!!d!!!!!!!!!!!!!!!!!!!,!!!..b......~~~~~,,==,d,,,..........~~f.ff......,,,,,_________--------------~~~_!!!!!!!!!!!$$;;!!$$$$$$$!!!!!!!%***************aa-----", // 91
    "..!!!,!!!!!!!!::!!!!!!!!!d,,,b........b~~~~,.==,,,,,,....fb...~~f...........,d,_________--------------~~~_!!!!!!!!!!!$$;;!!:::::::::::::aa***S***********aa-----", // 92
    "..b...!!,d,!!!::!.,,!!!!!,,......b..........b==b,,,,,...f.....~~..............,_________---------------~~_!!!!!!!!!!!!$;;$$:::::::::::::aa*******S***S***aa-----", // 93
    "f....d,,,,,,!!:::.d,!!!!!d,...b..............==.,,,,,.........~~..............,_________---------------~~_!!!!!!!!,,,,$;;,.!!$$$,...!!!!!a***************a~-----", // 94
    "...,,,,,,d,,,..::,,,!!!,,,,..........f..f....==b.,,,,,b......b~~..b...........__________---------------~~~_$!!$$,,,,,dd,::...,,,,....!!$!aa*************aa~-----", // 95
    "_.....b..~~~,,.::.....,,,,,..~!,,,,,,,,,,,d,,==,,,,,,,,,......~~,,,,,b....::::........._~~-------------~~~_.$$$d,,,,,,,,::..,,,,,...b...%%a*************a~~-----", // 96
    "_.........,,,,.::.,,!!!,,.!!~~!,,,,,,,,,,,,,,===,,,,,,,,.b....~~,,,,......:::::.....b.._~~--------------~~_,,,,,,,,,,,,,:::.,,,,.......%%%aa***********aa~~-----", // 97
    "_....!...d,,,,.:::!,!!!!!!!!!!!!!!,,,,,,,,,,,,==,,,,,d......,,~~,,,,....._::::::::___.._~~--------------~~_....,,,,,,,,,,::.d,,,......%%%%%aaa*******aaa%~~-----", // 98
    "_.!,,,!,,,,...!!::!,!!,,,,,!!!!~~!!,,,,f,,,,,,==...b.......f,,~~,,,,b....____:::::____::~~--------------~~_.......,,....,:::.,,......%%%%%%%%aaaa%aaaa%%%~~-----", // 99
    "_.!,,,,,,,,,,,!!::!!!!,,,,,!!!!~~~!,,,,,,######=....######.,,,~~,,,:.^.^___:::::________~~--------------~~_...b.........,,::.........%%%%%%%%aaa%%aa%%%%%~~-----", // 100
    "_,,,,,,,,!,,,!!!::!!!,Y,,!!!!!!~~~!,,,,,,#;;;;#==...#;;;;#,,,,~~,,,^:^^^:^:::::::^:^^___~~--------------~~_....b..........:::.......,%%%%%%%%%%%%%%%%%%%%~~-----", // 101
    "_,,,,,!!!!!!!!!!::!!,,,,!!!!!!!~~~!!,,,,,#;;e;#==...#;;R;#,,,,~~,,,^^:::^^:::^^^^^^^^___~~--------------~~_...............,::......,,%%%%%%%%%%%%%%%%%%%%~~-----", // 102
    "_,,,!!!!!!!!!!!!::!!,,,,!!!Y!!!~!!!!,,,,,#;;;;#===b.#;;;;#,,,,~~,,,,::::g:::^^^^:::_____~~-------------~~~_...............,:::....,,,%%%%%%%%%%%%%%%%%%%%~~-----", // 103
    "_,,,!!~~~!!~~~~~::!!!!!!!!!!,!~~!!!,,,,,,##;###.==.=##;###====]]:::,:::::::::::::::::::^~~-------------~~~_...............,,::....,,,,%%%%%%%%%%%%%%%%%%%~~-----", // 104
    "_,,.!!!~~!!~~~~~::!!!!!!!!!!!!~~!!!,,,,f,,,,....==w===========]]::::::::::::::::::::::::~~-------------~~_................,,::....,,,,......%%%%%%%%%%%%%~~-----", // 105
    "_,,.,!!~~!!!!!!~::!!Y!!!!!!!!!!!!!!!,,,,,,,,,...====..b..,,f,,~~,,::::::.:::::::::::::::~~~------------~~_.................,:::,,,,,,,,,...........%%%%%%~~~----", // 106
    "_,,,.,!!!!,!!,,!::!!!!!!!!!!~~!!!~~!,,,,##;##...====.......,,,~~,,,,::::::::::::::__:::_~~~------------~~_........b..b.....,d:::,,,,,,%,,,%,,...........%~~~----", // 107
    "_,,,,,!!!!,,,,,,::,,,!!!!!!!!!Y!~~.,,,,,#;;;#...====.##;##.,,,~~,,,,::::::::::::::::g::::~~------------~~_...................b::,,,,,,,,,,%,,,,.........._~~----", // 108
    "_,,,,,!!!!,,,,,,::,,,!!!!!!!!!!!!!b.,,,,#;;;#...====.#;;;#.,,,~~,d.::::::::::::::::::::::~~------------~~~_...................::.,,,,,,,,,d%%,,b...,,,,,,,~~----", // 109
    "_,,,,,,,,,,,,,,,::,,,!!!!!!,,,!!!!..,,,,#####b..====.#;;;#..,,~~d,.:::::::::::..:::::::__~~------------~~~_.................%b:::.,,,,,,,d,,,,..,,,,,,,,,,~~----", // 110
    "_,,.,,,,,,,,,,,,::,,!!!,!!,,,,,,,,....,,,,,,,,,.====.#####d..,~~,,.:::^:::::::...::::::__~~------------~~~%%%%%%.........,,%%%.:::a[,,%,,,,,,,.,[[a,,,,,,,~~----", // 111
    "_..,,,,,,,,,,,,,::!!!,,,,,,,,,,,,,,....,hhhhhhh,====hhhhhhh..,~~,..:^^^^^:.::::::::^^:::_~~------------~~~%%%%%,,,,,,,,,,,,%%%%%::[[,,%%,%%d,,,,a[[,,,%%,,~~----", // 112
    "_.,,!,,,,,,!,,,,::!!!!,,,,,,,,,,,,!....,hhhhhhh,==,,hhhhhhh,,,~~...^^^^^^^.::::^^:^^^::::~~------------~~,,,,,,,,,,,,,,,,,,%%%%,::[a,,%,,,,,,,,,[[[,,%%%,,~~----", // 113
    "_,,!!,,!!!!!!,,,::!!!!!,,!,,,,,,,,!....,,,,,,..:::,,.,,,,,,d,,~~...^...::::::^^^^^:::::^:~~------------~~,,,,,,,,,,,,,,,,,,,,%%,,,,,,,%,,,[[[,,,[[[,%%%,_~~~----", // 114
    "_,,!!!!!~~~!!!!!::!!!!!!!!,,,,,!,!!....,,,,,,.::::,...,,,.,,,,~~..::::::::::^^^g::::::^^:~~------------~~,,,,,,,,,,,,,,%,,,,,%%,,,,,,,%,,,[[[,,,[[a,%%%%_~~~----", // 115
    "_..~!!!~~~~!!~!!::!!!!!!!,!!,!!!!!!!.....,,:::::==............~~..::::::::::::::::::::::~~~------------~~,,,,,,,,,,,,,,,,,,,####a#######a####,,,aaa,,%%%%~~-----", // 116
    "_.~!!!!!~~~!!~~!::!!!!!!!,,,!!!!,!!!......:::::,==............~~..::::g::::::...::::::::~~~------------~~_,,,,,,,,,,,,,,,,,[#[[[[[[[[[[[[[[[#,,,,,,,,%%%%~~-----", // 117
    "_.!!!!!!~~~!!~~~::!!!!!!,,,,!!,,,!!...::::::.,,,==..........,,~~..:::::::::::..::::_::::~~-------------~~_,,,,,,,,,,,,,,,,,[#[0#[[[[[[[[[#0[#,,,,,,,,%%%%~~-----", // 118
    "_.!!,!!~~~~!!!~~::,,,,,,,,,,!!!!!::::::::::...,,==........,,,,~~..::::::::::::::::_:::::~~-------------~~_.,,,,,,,,,,,,,,,,[#[[#[[[[[[[[[#[[#,,,,,,,,%%%%~~-----", // 119
    "_.,,,!!~~~!!!!!~:::::::::::::::::::::::.......,,==........,,,,~~..::::::::::::::::::::::~~-------------~~_.,,,,,,,,,,,,,,,,,#[[[[[[[[[[[[#[[#[[[,,,,,%%%%~~-----", // 120
    "_!,,,!!~~~~!!!!~::::::::::::::::::..............==........,,,,~~..:::::..:::::::::::::::~~~------------~~_.,,,,,,,,,,,,,,,,,a[[#[[[[[[[[[[[[#[aa,,,,,%%%%~~-----", // 121
    "_..!!!!!!~~!!!!!::!!,,,,!!!!!,,!!!,.............==.........,,,]],::::.......::::::::::::~~~------------~~_.,,,,,,,,,,,,,,,,%#[[#[[[[[[[[[#[[#aa[,,,,,%%%%~~-----", // 122
    "_...!!~!!~~~~~!!::,,,!!!!!!!,,!!!!!.............==..........,,]]::::^^^.^......:::::^::::~~------------~~_,,,,,,,,[a[,,,,,,%#[[#[[[[[[[[[#[[#,,,,,,,,,[[[~~-----", // 123
    "_...!!~!!~~~~~!!::,,,!!!!!!!,!!!!!!!............==..........,,~~::::^:^^^^..:::.^:^^^::::~~------------~~,,,,,,,,,[[[%%%%%%%#[[[[[[[[[[[[[[[a,,,,%%,,,[[~~~-----", // 124
    "_...!!!!!~~~~!!!::,!,,!!!!!!,,,!!!!.......,,,...==............~~:::^:::::...^^^:::^::::^:~~------------~~,,%,,,,,,[[[%%%%%%%#[[[[[[[[[[[[[[[#,,,%%%%,,[a~~~-----", // 125
    "_..!!!!!!!!!!!!!::!!!,!!!,!!,,!!!!.......,,,,...==............~~::::::Z:::.^^^^Z::::::^^^~~------------~~%,,,,,,,,[[[%%%[[[%#[[[[[[[[[[[[[[[#,,%%%%%,,[[~~------", // 126
    "_..,,!!,,!!!!,!!::!!!!!,,,!!!!!!!!b.......,,..__==_____.......~~:::::::::::::::::::::::Z^~~------------~~,,,,,,,,,[[[%%%[[a%#[[[[[[[[[[[[[[[#,,%%%%%%,[[~~------", // 127
    "_..,,!!,,,!!!,!!::!!!!!,,,,!!!!!!!..........._~~~~~~~~~_......~~:::::::::::::::::::::::::~~------------~~,,,,,,,,,a[[,,,a[[,#[0[[[[[[[[[[[0[#,,%%%%%%,[[~~~-----", // 128
    "_.,,,,,,,,!!!!!!::!~!!,,,!,,!!!!!!.......,.._~~~~~~~~~~~_.....~~::::::::::Z:::::::::::::~~~------------~~,,,,,,,,,,,,,,,a[[[#[[[[[[[[[[[[[[[#,,%%%%%%,,,~~~-----", // 129
    "_,,!!!,,,,!!!!!!::!!!!,,!!,,!!!!!!.......,,_~~~~-----~~~~_....~~.::::::::::::::::::Z::::~~~------------~~~,,,,,,,,,,,,,,[[[a#######[[[#######,,,%%%,,%%%%~~-----", // 130
    "_,,,~!!,,,!!~!~~::!!!!!!!!!!!!!!!,......,,_~~~~-------~~~~_...~~.::::::::::::..::::::..:~~-------------~~~,,,,%%,,,,,,,%[[[a[[,,,,,,::[,,,,,,,,,,,,,,%%%%~~-----", // 131
    "_,,~~~!,,,!!~!~~::!!!!!!!!!!!!!,,,,......_~~~~---------~~~~_..~~__:::::::::::..........:~~--------------~~,,,,%%%,,,,,,%[[[,,,,,,,,,::[,,,[aa,,,,,,,%%%%%~~-----", // 132
    "_,!~~!!!!!!__!~~::!!!!!!!!!!!!,,,,,,...._~~~~-----------~~~~__~~~~_::::::::::Z:......:::~~--------------~~,,,%%%%,,,,,,%a[[,,,,,,%%:::a,,,[[[,,,,,,%%%%%%~~-----", // 133
    "_,!~~______~~__~::____!!_______,,,,!!..._~~~-------------~~~_~~~~~~~~~~~~~~~:::::::::~~~~~--------------~~,,%%%%%,,,,,,%a[[,,,,,%%%::[a,,,a[[,,,,,,,%%%%%~~~----", // 134
    "___~~~~~~~~~~~~~~~~~~~__~~~~~~~_____~____~~---------------~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~--------------~~_a[[[[aa[a[,,,,,,,,,,,%%:::,,[[[,,,,,,,,,,%%[[_~~~----", // 135
    "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~---------------~~~~~~----------~~~~~~~~~~~~~-----------------~~_a[[a[[[a[[,,,,,,,,,,,%%::,,,[a[,,,,,,,,,,%%[[,_~~----", // 136
    "~~~~~---------------~~~~~~---~~~~~~~~~~~~~~-------------------~~----------------------------------------~~__a~~~~[[[[,~,,,,,,,,,%%::%,,[[[,,~~~,,,,,%%[[__~~----", // 137
    "--------------------------------------------------------------~~----------------------------------------~~~~~~~~~~~~~~~~~~~~~~~~~~~~~,~~~~~~~~~~~~~~~~~~~~~~----", // 138
    "--------------------------------------------------------------~~----------------------------------------~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~----", // 139
    "--------------------------------------------------------------~~-------------------------------------------------------------------~~~~~------------------------", // 140
    "--------------------------------------------------------------~~------------------------------------------------------------------------------------------------", // 141
    "--------------------------------------------------------------~~------------------------------------------------------------------------------------------------", // 142
    "--------------------------------------------------------------~~------------------------------------------------------------------------------------------------"  // 143
  ],
  place: [
    { o: "hearth_shrine", x: 49, y: 55 },
    { o: "ladder_down", x: 24, y: 24, to: ["deeps", 6, 7] },
    { o: "war_banner", x: 80, y: 8 },
    { o: "beacon_west", x: 8, y: 6 },
    { o: "beacon_mid", x: 30, y: 13 },
    { o: "beacon_east", x: 56, y: 6 },
    { o: "sign_north_fork", x: 52, y: 35 },
    { o: "sign_north_gate", x: 46, y: 38 },
    { o: "sign_west_gate", x: 38, y: 46 },
    { o: "sign_east_gate", x: 59, y: 46 },
    { o: "sign_south_gate", x: 46, y: 59 },
    { o: "sign_ford", x: 59, y: 82 },
    { o: "ferry_gullhaven", x: 89, y: 61, to: ["overworld", 97, 48] },
    { o: "ferry_saltmere", x: 96, y: 47, to: ["overworld", 88, 62] },
    { o: "sign_saltmere", x: 130, y: 46 },
    { o: "southfold_strongbox", x: 47, y: 107 },
    { o: "ice_road_west", x: 87, y: 71, to: ["overworld", 106, 56] },
    { o: "ice_road_east", x: 105, y: 56, to: ["overworld", 86, 71] }
  ],
  spawns: [
    // Townsfolk (DESIGN.md 15.1); r 0 keeps them at their posts, Odo strolls his yard
    { n: "mirella", x: 44, y: 44, r: 0 },
    { n: "tobin", x: 53, y: 43, r: 0 },
    { n: "brenna", x: 44, y: 53, r: 0 },
    { n: "hob", x: 54, y: 52, r: 0 },
    { n: "ysolde", x: 52, y: 47, r: 0 },
    { n: "vael", x: 44, y: 47, r: 0 },
    { n: "marrick", x: 49, y: 41, r: 0 },
    { n: "odo", x: 40, y: 82, r: 2 },
    { n: "hesk", x: 54, y: 80, r: 0 },
    { n: "dagny", x: 20, y: 30, r: 0 },
    { n: "bram", x: 68, y: 43, r: 0 },
    { n: "pell", x: 80, y: 58, r: 0 },
    { n: "ilvara", x: 30, y: 8, r: 0 },
    // Saltmere
    { n: "osric", x: 118, y: 43, r: 0 },
    { n: "corran", x: 114, y: 49, r: 0 },
    { n: "greta", x: 117, y: 52, r: 0 },
    { n: "maren", x: 124, y: 53, r: 0 },
    { n: "vesna", x: 126, y: 48, r: 0 },
    // Amberwood
    { n: "elin", x: 124, y: 24, r: 0 },
    // Southfold
    { n: "aldo", x: 42, y: 102, r: 0 },
    { n: "wyn", x: 53, y: 102, r: 0 },
    // Dunmoor pen and field
    { n: "chicken", x: 38, y: 66 }, { n: "chicken", x: 40, y: 65 }, { n: "chicken", x: 42, y: 66 },
    { n: "chicken", x: 37, y: 68 }, { n: "chicken", x: 39, y: 67 }, { n: "chicken", x: 41, y: 68 },
    { n: "cow", x: 46, y: 66 }, { n: "cow", x: 50, y: 66 }, { n: "cow", x: 54, y: 67 }, { n: "cow", x: 47, y: 70 },
    { n: "cow", x: 51, y: 70 }, { n: "cow", x: 54, y: 72 }, { n: "cow", x: 48, y: 73 },
    // Gnarltooth Camp
    { n: "goblin", x: 69, y: 13 }, { n: "goblin", x: 72, y: 11 }, { n: "goblin", x: 74, y: 15 },
    { n: "goblin", x: 70, y: 18 }, { n: "goblin", x: 74, y: 20 }, { n: "goblin", x: 77, y: 21 },
    { n: "goblin", x: 79, y: 14 }, { n: "goblin", x: 81, y: 19 }, { n: "goblin", x: 84, y: 15 },
    { n: "goblin", x: 73, y: 9 },
    { n: "goblin_brute", x: 77, y: 6 }, { n: "goblin_brute", x: 81, y: 7 }, { n: "goblin_brute", x: 86, y: 13 },
    { n: "goblin_brute", x: 79, y: 11 },
    // Shellback Shore (crabs keep 7 clear of the gull spots)
    { n: "shellback_crab", x: 81, y: 78 }, { n: "shellback_crab", x: 85, y: 79 },
    { n: "shellback_crab", x: 83, y: 82 }, { n: "shellback_crab", x: 80, y: 85 },
    { n: "shellback_crab", x: 86, y: 86 }, { n: "shellback_crab", x: 82, y: 89 },
    { n: "shellback_crab", x: 85, y: 92 }, { n: "shellback_crab", x: 80, y: 92 },
    // Gloomfen (9 clear of the yews, Dunmoor and Hollowpine)
    { n: "skeleton", x: 5, y: 71 }, { n: "skeleton", x: 10, y: 74 }, { n: "skeleton", x: 15, y: 71 },
    { n: "skeleton", x: 20, y: 73 }, { n: "skeleton", x: 24, y: 77 }, { n: "skeleton", x: 22, y: 82 },
    { n: "skeleton", x: 25, y: 87 }, { n: "skeleton", x: 21, y: 91 },
    // Ashen Reach: aggressive spawns at y <= 7, x <= 21 or x >= 39 (17.3a); ogres are passive
    { n: "bandit", x: 3, y: 6 }, { n: "bandit", x: 16, y: 4 }, { n: "bandit", x: 13, y: 0 },
    { n: "bandit", x: 53, y: 3 },
    { n: "ashen_wolf", x: 1, y: 2 }, { n: "ashen_wolf", x: 8, y: 1 }, { n: "ashen_wolf", x: 15, y: 7 },
    { n: "ashen_wolf", x: 19, y: 7 }, { n: "ashen_wolf", x: 21, y: 3 }, { n: "ashen_wolf", x: 53, y: 7 },
    { n: "hill_ogre", x: 12, y: 13 }, { n: "hill_ogre", x: 22, y: 11 }, { n: "hill_ogre", x: 40, y: 13 },
    { n: "hill_ogre", x: 54, y: 11 },
    { n: "bandit", x: 46, y: 5 }, { n: "bandit", x: 51, y: 7 },
    // Southfold's wheat
    { n: "mill_rat", x: 41, y: 112 }, { n: "mill_rat", x: 44, y: 113 }, { n: "mill_rat", x: 53, y: 112 },
    { n: "mill_rat", x: 57, y: 113 },
    // Redcliff Canyons (passive jackals) and the Depths (aggressive spawns at y >= 127, x >= 72; 17.3a)
    { n: "canyon_jackal", x: 74, y: 100 }, { n: "canyon_jackal", x: 80, y: 105 }, { n: "canyon_jackal", x: 86, y: 110 },
    { n: "canyon_jackal", x: 75, y: 111 }, { n: "canyon_jackal", x: 68, y: 114 }, { n: "canyon_jackal", x: 84, y: 116 },
    { n: "canyon_harpy", x: 73, y: 128 }, { n: "canyon_harpy", x: 80, y: 129 }, { n: "canyon_harpy", x: 86, y: 132 },
    { n: "canyon_harpy", x: 82, y: 127 },
    { n: "sand_wyrmling", x: 78, y: 131 }, { n: "sand_wyrmling", x: 84, y: 134 }, { n: "sand_wyrmling", x: 75, y: 127 },
    // Sunken Vale: the drowned keep to the south half, 9 clear of the eel pools and yews
    { n: "drowned_soldier", x: 5, y: 127 }, { n: "drowned_soldier", x: 10, y: 129 }, { n: "drowned_soldier", x: 20, y: 127 },
    { n: "drowned_soldier", x: 25, y: 130 }, { n: "drowned_soldier", x: 11, y: 132 },
    { n: "mire_witch", x: 26, y: 129 }, { n: "mire_witch", x: 4, y: 126 }, { n: "mire_witch", x: 22, y: 133 },
    // Amberwood: passive boars; bark stalkers among the amberhearts (y <= 20, 10+ from Elin and the road)
    { n: "thornback_boar", x: 110, y: 20 }, { n: "thornback_boar", x: 118, y: 28 }, { n: "thornback_boar", x: 130, y: 26 },
    { n: "thornback_boar", x: 147, y: 25 }, { n: "thornback_boar", x: 112, y: 30 },
    { n: "bark_stalker", x: 141, y: 9 }, { n: "bark_stalker", x: 148, y: 13 }, { n: "bark_stalker", x: 112, y: 6 },
    { n: "bark_stalker", x: 132, y: 4 },
    // Brinemarsh: passive toads; bog wraiths in the south-east, 9 clear of the salt flats, Saltmere and Stormcoast
    { n: "mire_toad", x: 125, y: 66 }, { n: "mire_toad", x: 131, y: 72 }, { n: "mire_toad", x: 110, y: 80 },
    { n: "mire_toad", x: 114, y: 88 }, { n: "mire_toad", x: 124, y: 76 }, { n: "mire_toad", x: 108, y: 92 },
    { n: "bog_wraith", x: 131, y: 87 }, { n: "bog_wraith", x: 130, y: 90 }, { n: "bog_wraith", x: 123, y: 93 },
    { n: "bog_wraith", x: 131, y: 80 },
    // Starfall Crater (danger): the guardians keep x >= 144, y >= 80
    { n: "crater_sentinel", x: 146, y: 84 }, { n: "crater_sentinel", x: 150, y: 88 }, { n: "crater_sentinel", x: 147, y: 97 },
    { n: "crater_sentinel", x: 144, y: 100 },
    { n: "shardback_golem", x: 150, y: 96 }, { n: "shardback_golem", x: 149, y: 101 }, { n: "shardback_golem", x: 151, y: 84 },
    // Duskhollow Ruins (danger): hollow knights in and around the keep; the King appears on his throne at stage 20
    { n: "hollow_knight", x: 129, y: 127 }, { n: "hollow_knight", x: 135, y: 127 }, { n: "hollow_knight", x: 118, y: 124 },
    { n: "hollow_knight", x: 146, y: 120 }, { n: "hollow_knight", x: 112, y: 132 },
    { n: "hollow_king", x: 132, y: 119, r: 2, if: [{ q: "hollow_king", gte: 20 }] },
    // Skarg appears once the war banner burns
    { n: "skarg", x: 82, y: 10, r: 2, if: [{ q: "gnarltooth_tolls", gte: 30, lt: 100 }] }
  ],
  fish: [
    { group: "willowmere_net", obj: "spot_net", n: 3, tiles: [[70, 41], [69, 32], [75, 33], [75, 39], [67, 36], [72, 32]] },
    { group: "wend_lure", obj: "spot_lure", n: 3, tiles: [[62, 27], [63, 29], [62, 32], [63, 35], [62, 37], [63, 40]] },
    { group: "gull_cage", obj: "spot_cage", n: 2, tiles: [[88, 52], [88, 55], [88, 58], [88, 67]] },
    { group: "gull_harpoon", obj: "spot_harpoon", n: 2, tiles: [[88, 54], [88, 57], [88, 66], [88, 69]] },
    { group: "gull_deep", obj: "spot_deep", n: 1, tiles: [[90, 62], [90, 63]] },
    { group: "bright_net", obj: "spot_net", n: 2, tiles: [[46, 128], [54, 128], [45, 129], [55, 129]] },
    { group: "bright_cage", obj: "spot_cage", n: 2, tiles: [[44, 130], [56, 130], [43, 131], [57, 131]] },
    { group: "vale_eel", obj: "spot_eel", n: 2, tiles: [[6, 104], [11, 104], [15, 104], [8, 115], [10, 116]] },
    { group: "storm_pots", obj: "spot_lantern", n: 2, tiles: [[153, 41], [152, 49], [152, 53], [152, 57]] },
    { group: "storm_harpoon", obj: "spot_storm", n: 1, tiles: [[152, 59], [152, 63], [152, 66]] }
  ]
};
// ==== src/engine/data/map_deeps.js ====
// ----------------------------------------------------------------
// ----------------- Data: the Deeps map (48x48) ------------------
// ----------------------------------------------------------------
// 48x48 cave map below Copperdell (DESIGN.md 17.3). Upper Deeps -> Ironbound gate (12,24) ->
// Lower Deeps -> sealed door (24,36) -> Cinder Hall and Emberdeep -> Golem Forge and the Lair.
Data.maps.deeps = {
  name: "The Deeps", dark: true,
  rows: [
    "^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^", // 0
    "^^^^^^^^^^^^^^^^^^***^^^^^^^^^^^^^^^^^^^^^**^^^^", // 1
    "^^^^^^^^^^^^^^^^^****s^^^^^^^^^^^^^^^^^E****E^^^", // 2
    "^^^^^****^^^^^^^^******^^^^^^^^^^^^^^^*******^^^", // 3
    "^^^^P*****^^^^^^*******^^^^^^^^^^^^^E******{{{^^", // 4
    "^^^Q****j**^^^^^**U*****^^^^^^^^^^^^*******{{{*^", // 5
    "^^************^*********^^^^^^^^^^^****s***{{{*^", // 6
    "^^**********************^^^^^^^^^^^*********s**^", // 7
    "^^*s******^^^**********^^^^^^^^^^^^***********E^", // 8
    "^^*******Q^^^^^^****U***^^^^^^^^^^^*****U******^", // 9
    "^^^******^^^^^^^s******^^^^^^^^^^^^*E**********^", // 10
    "^^^**K**^^^^^^^^*******^^^^^^^^^^^^**********U{^", // 11
    "^^K******^^^^^^^******^^^^^^^^^^^^^**********{{{", // 12
    "^*******K*^^^^^^^****^^^^^^^^^^^^^^^{{{**U***{{^", // 13
    "^****U****^^^^^^^^^^^^^^^^^^^^^^^^^^{{{******{{^", // 14
    "^**K*******^^^^^^^^^^^^^^^^^^^^^^^^^^{{*******{^", // 15
    "^J*****K******^^^^^^^^^^^^^^^^^^^^^^*********E*^", // 16
    "^***J**********^^^^^^^^^^^^^^^^^^^************^^", // 17
    "^*K******s*****^^^^^^^^^^^^^^^^^^****^^***s^*^^^", // 18
    "^^***G***^*****^^^^^^^^^^^^^^^^^***^^^^^^^^^^^^^", // 19
    "^^^*****G^*****^^^^^^^^^^^^^^^^***^^^^^^^^^^^^^^", // 20
    "^^^G*****^*****^^^^^^^^^^^^^^^***^^^^^^^^^^^^^^^", // 21
    "^^^^^^J*^^^j*j^^^^^^^^^^^^^^^***^^^^^^^^^^^^^^^^", // 22
    "^^^^^^^^^^^^**^^^^^^^^^^^^^^***^^^^^^^^^^^^^^^^^", // 23
    "^^^^^^^^^^^^*^^^^^^^^^^^^^^^**^^^^^^^^^^^^^^^^^^", // 24
    "^^^^^^^^^^^***^^^^^^^^^^^^^^*U^^^^^^^^^^^^^^^^^^", // 25
    "^^^****^^**j*j*^^^^*^^^^^^^^**^^^^^^^^^^^^^^^^^^", // 26
    "^^***C**^*****s*^**V**^^^^^^**^^^^^^^^^^^^^^^^^^", // 27
    "^^C*************V******^^^^^**^^^^^^^^^^^^^^^^^^", // 28
    "^*********************V*^^^^**^^^^^^^^^^^^^^^^^^", // 29
    "^***C***C********U******^^^****^^^^^^^^^^^^^^^^^", // 30
    "^^*******^^***^^*****V*^^^*s****^^^^^^^^^^^^^^^^", // 31
    "^^C******^^**^^^*V*****^^^*{*****^^^^^^^^^^^^^^^", // 32
    "^^***C**^^^**^******V*^^^^{{{*****^^^^^^^^^^^^^^", // 33
    "^^^^***^^^^**^*Q*****^^^^**{******^^{{****{{*{{{", // 34
    "^^^^^^^^^^^**^^^******^^^*j*******^^{**********{", // 35
    "^^^^^^^^^^^**^^^^^****************^^*****U*****{", // 36
    "^^^^^^^^^^^**^^^^^^^^***^*****U**^^^***{********", // 37
    "^^^^^^^^^^^**^^^^^^^^^^^^^********j^j*******U***", // 38
    "^^^^^^^^^^^**^^^^^^^^^^^^^***{{{****************", // 39
    "^^^^^^^^********^^^^^^^^^^^****^**j^j***********", // 40
    "^^^^****************^^^^^^^^^^^^^^^^*********{**", // 41
    "^^^s************U*****^^^^^^^^^^^^^^**U*********", // 42
    "^^^*****s*U***********^^^^^^^^^^^^^^*U**{******{", // 43
    "^^^***U*******U***s**^^^^^^^^^^^^^^^{**********{", // 44
    "^^^^***************^^^^^^^^^^^^^^^^^{{*****{{*{{", // 45
    "^^^^^^^*********^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^", // 46
    "^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^"  // 47
  ],
  place: [
    { o: "ladder_up", x: 6, y: 6, to: ["overworld", 24, 25] },
    { o: "ironbound_gate", x: 12, y: 24 },
    { o: "sealed_door", x: 24, y: 36 },
    { o: "lair_door", x: 35, y: 39 }
  ],
  spawns: [
    // Upper Deeps spider den (9 clear of the ladder, the gate and every rock)
    { n: "cave_spider", x: 17, y: 3 }, { n: "cave_spider", x: 21, y: 5 }, { n: "cave_spider", x: 19, y: 8 },
    { n: "cave_spider", x: 22, y: 10 }, { n: "cave_spider", x: 17, y: 12 }, { n: "cave_spider", x: 20, y: 12 },
    // Lower Deeps warren (9 clear of the gate and every rock)
    { n: "tunnel_lurker", x: 4, y: 43 }, { n: "tunnel_lurker", x: 8, y: 45 }, { n: "tunnel_lurker", x: 12, y: 42 },
    { n: "tunnel_lurker", x: 15, y: 45 }, { n: "tunnel_lurker", x: 19, y: 43 },
    { n: "tunnel_lurker", x: 11, y: 46 },
    // Emberdeep: Cinder Hall imps, then the Golem Forge
    { n: "ember_imp", x: 31, y: 32 }, { n: "ember_imp", x: 31, y: 37 }, { n: "ember_imp", x: 38, y: 12 },
    { n: "ember_imp", x: 42, y: 17 },
    { n: "magma_golem", x: 40, y: 6 }, { n: "magma_golem", x: 43, y: 11 }, { n: "magma_golem", x: 39, y: 16 },
    { n: "magma_golem", x: 41, y: 2 },
    // Smoulderjaw wakes for Embers Beneath stage 30 and never leaves the Lair
    { n: "smoulderjaw", x: 42, y: 40, r: 0, if: [{ q: "embers_beneath", gte: 30 }] }
  ],
  fish: []
};
// ==== src/engine/data/start.js ====
// ----------------------------------------------------------------
// ------------------ Data: start kit and renames -----------------
// ----------------------------------------------------------------
// New characters spawn in Brackenford's square; deaths and recalls return to the Hearth
// Shrine (DESIGN.md section 17.1). renames maps retired ids to current ones for old saves.
Data.start = { map: "overworld", x: 48, y: 48,
  kit: [["bronze_axe", 1], ["bronze_pickaxe", 1], ["small_net", 1], ["tinderbox", 1], ["hammer", 1], ["shrimp", 5],
    ["coins", 50]],
  eq: { weapon: "bronze_sword" }, respawn: ["overworld", 49, 55],
  welcome: "Welcome to Orcadia. Brenna the smith could use a hand; look for her at the forge." };
Data.renames = { items: {}, objs: {}, npcs: {} };
// ==== src/engine/rules.js ====
// ----------------------------------------------------------------
// ---------------- Rules: constants and formulas -----------------
// ----------------------------------------------------------------
// Pure numbers of the game (DESIGN.md section 9 Rules). Every function is a formula with test vectors
// in tests/rules.test.mjs; nothing here touches state.
const Rules = (function () {
  "use strict";

  var SKILLS = ["attack", "strength", "defence", "hitpoints", "woodcutting", "mining", "fishing", "smithing",
    "cooking", "firemaking", "crafting"];
  var EQUIP_SLOTS = ["head", "cape", "neck", "weapon", "body", "shield", "legs", "hands", "feet", "ring"];

  // Ordered list; att/str/def are the invisible level boosts, xp the skills a hit trains.
  var STYLES = [
    { id: "accurate", name: "Accurate", att: 3, str: 0, def: 0, xp: ["attack"] },
    { id: "aggressive", name: "Aggressive", att: 0, str: 3, def: 0, xp: ["strength"] },
    { id: "defensive", name: "Defensive", att: 0, str: 0, def: 3, xp: ["defence"] },
    { id: "controlled", name: "Controlled", att: 1, str: 1, def: 1, xp: ["attack", "strength", "defence"] }
  ];

  // ----------------------------------------------------------------
  // ----------------------- Experience table -----------------------
  // ----------------------------------------------------------------

  // XP_TABLE[L] = real XP needed for level L (index 0 unused, XP(1) = 0).
  var XP_TABLE = (function () {
    var t = new Int32Array(100);
    var pts = 0;
    for (var L = 2; L <= 99; L++) {
      pts += Math.floor(L - 1 + 300 * Math.pow(2, (L - 1) / 7));
      t[L] = Math.floor(pts / 4);
    }
    return t;
  })();

  // Highest level 1..99 whose threshold is at most xp (binary search).
  function levelForXp(xp) {
    if (!(xp >= XP_TABLE[2])) return 1;
    var lo = 2;
    var hi = 99;
    while (lo < hi) {
      var mid = (lo + hi + 1) >> 1;
      if (XP_TABLE[mid] <= xp) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }

  function xpForLevel(L) {
    var l = Math.floor(Number(L)) || 1;
    return XP_TABLE[l < 1 ? 1 : l > 99 ? 99 : l];
  }

  // ----------------------------------------------------------------
  // ------------------ Gathering and making odds -------------------
  // ----------------------------------------------------------------

  // The tool multiplier applies after the /256.
  function gatherChance(L, low, high, mult) {
    var m = typeof mult === "number" ? mult : 1;
    var base = (1 + Math.floor(low * (99 - L) / 98 + high * (L - 1) / 98 + 0.5)) / 256;
    return Math.min(1, base * m);
  }

  // Burn/fail odds; Sim passes full' = min(99, full + 5) when cooking on a fire.
  function makeChance(L, lvl, full) {
    if (L >= full || full <= lvl) return 1;
    return Math.max(0, Math.min(1, 0.5 + 0.5 * (L - lvl) / (full - lvl)));
  }

  // ----------------------------------------------------------------
  // --------------------------- Seasons ----------------------------
  // ----------------------------------------------------------------

  // Four seasons of SEASON_TICKS each, from tick 0: index into Data.seasons, and ticks until the next.
  var SEASON_TICKS = 6000;
  var SEASONS = 4;

  function seasonIndex(tick) {
    var t = Math.max(0, Math.floor(Number(tick)) || 0);
    return Math.floor(t / SEASON_TICKS) % SEASONS;
  }

  function seasonLeft(tick) {
    var t = Math.max(0, Math.floor(Number(tick)) || 0);
    return SEASON_TICKS - t % SEASON_TICKS;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Perks -----------------------------
  // ----------------------------------------------------------------

  // One perk point per PERK_EVERY levels of a skill: 1 at level 5, 19 at 99 (junk levels earn none).
  var PERK_EVERY = 5;

  function perkPoints(L) {
    var l = Math.floor(Number(L)) || 0;
    return l > 0 ? Math.floor(Math.min(99, l) / PERK_EVERY) : 0;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Pets -----------------------------
  // ----------------------------------------------------------------

  // Section 10.16. A pet swings every PET_SPEED ticks (Quick: PET_QUICK) with its own stats, never the
  // player's: at pet level L its attack is att + 2 x (L - 1) and its max hit maxHit + floor((L - 1) / 5).
  // Level L needs 25 x (L - 1)^2 pet XP (one per damage).
  var PET_SPEED = 6;
  var PET_QUICK = 4;
  var PET_MAX_LVL = 20;
  var PET_XP_MAX = 25 * (PET_MAX_LVL - 1) * (PET_MAX_LVL - 1);
  // The eight combat perks a pet may carry; none touches skilling.
  var PET_PERKS = {
    quick: { name: "Quick", desc: "Strikes every 4 ticks instead of 6." },
    flurry: { name: "Flurry", desc: "1 in 5 attacks strike twice." },
    keen: { name: "Keen", desc: "Lands its attacks 25% more often." },
    gore: { name: "Gore", desc: "1 in 4 landed hits delay the foe's next attack by a tick." },
    mend: { name: "Mend", desc: "Each landed hit heals you 1." },
    guard: { name: "Guard", desc: "Foes' landed melee hits on you are 1 lower (never below 1)." },
    scorch: { name: "Scorch", desc: "Its max hit is a quarter higher (at least +1)." },
    dread: { name: "Dread", desc: "Your foe lands its attacks 10% less often." }
  };

  function petXpFor(L) {
    var l = Math.max(1, Math.min(PET_MAX_LVL, Math.floor(Number(L)) || 1));
    return 25 * (l - 1) * (l - 1);
  }

  function petLevel(xp) {
    var l = 1;
    while (l < PET_MAX_LVL && petXpFor(l + 1) <= xp) l++;
    return l;
  }

  function petLvl(L) { return Math.max(1, Math.min(PET_MAX_LVL, Math.floor(Number(L)) || 1)); }

  // Growth: a pet is young until level 7, an adult from 7 and mythic from 14 (DESIGN.md 10.16a).
  var PET_STAGES = [{ lvl: 1, name: "Young" }, { lvl: 7, name: "Adult" }, { lvl: 14, name: "Mythic" }];

  function petStage(L) {
    var l = petLvl(L), st = 0;
    for (var i = 1; i < PET_STAGES.length; i++) if (l >= PET_STAGES[i].lvl) st = i;
    return st;
  }

  // The pet's attack level, and its attack roll as if it had a +64 attack bonus.
  function petAttack(att, L) { return Math.max(1, att | 0) + 2 * (petLvl(L) - 1); }
  function petAttackRoll(att, L) { return (petAttack(att, L) + 8) * 128; }

  // The pet's max hit, at least 1; Scorch adds a quarter (at least +1).
  function petMaxHit(maxHit, L, perk) {
    var m = Math.max(1, (maxHit | 0) + Math.floor((petLvl(L) - 1) / 5));
    return perk === "scorch" ? m + Math.max(1, Math.floor(m / 4)) : m;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Combat ----------------------------
  // ----------------------------------------------------------------

  // A style id or a STYLES entry; unknown ids fall back to accurate.
  function style(s) {
    if (s && typeof s === "object") return s;
    for (var i = 0; i < STYLES.length; i++) if (STYLES[i].id === s) return STYLES[i];
    return STYLES[0];
  }

  function playerAttackRoll(lvl, s, attB) {
    return (lvl + style(s).att + 8) * (attB + 64);
  }

  function playerDefenceRoll(lvl, s, defB) {
    return (lvl + style(s).def + 8) * (defB + 64);
  }

  function playerMaxHit(lvl, s, strB) {
    return Math.floor(0.5 + (lvl + style(s).str + 8) * (strB + 64) / 640);
  }

  function npcAttackRoll(c) { return (c.att + 9) * (c.attB + 64); }
  function npcDefenceRoll(c) { return (c.def + 9) * (c.defB + 64); }

  function hitChance(a, d) {
    var p = a > d ? 1 - (d + 2) / (2 * (a + 1)) : a / (2 * (d + 1));
    return p > 0 ? Math.min(1, p) : 0;
  }

  function combatLevel(att, str, def, hp) {
    return Math.floor(0.25 * (def + hp) + 0.325 * (att + str));
  }

  // { skill: xp10 } for a hit of dmg; a miss trains nothing.
  function combatXp10(dmg, s) {
    var out = {};
    if (!(dmg > 0)) return out;
    var st = style(s);
    var third = Math.round(dmg * 40 / 3);
    if (st.xp.length > 1) {
      for (var i = 0; i < st.xp.length; i++) out[st.xp[i]] = third;
    } else {
      out[st.xp[0]] = 40 * dmg;
    }
    out.hitpoints = third;
    return out;
  }

  // ----------------------------------------------------------------
  // ---------------------- Prices and colours ----------------------
  // ----------------------------------------------------------------

  function buyPrice(value, price) {
    var p = typeof price === "number" ? price : value;
    return Math.max(1, Math.floor(p) || 0);
  }

  // 0 = unsellable. The epsilon keeps 35 * 0.4 from flooring to 13.
  function sellPrice(value, rate) {
    var v = Math.floor(value * rate + 1e-9);
    return v > 0 ? v : 0;
  }

  function hex2(n) {
    var s = Math.max(0, Math.min(255, Math.round(n))).toString(16);
    return s.length < 2 ? "0" + s : s;
  }

  // diff = npc level - player combat level: green, yellow-green ramp, yellow, orange ramp, red.
  function levelColor(diff) {
    if (typeof diff !== "number" || !isFinite(diff) || diff === 0) return "#ffff00";
    if (diff <= -10) return "#00ff00";
    if (diff < 0) return "#" + hex2(0xc0 * (10 + diff) / 9) + "ff00";
    if (diff < 10) return "#ff" + hex2(0xff - (0xff - 0x80) * diff / 9) + "00";
    return "#ff3030";
  }

  // ----------------------------------------------------------------
  // --------------------- Character name and look -------------------
  // ----------------------------------------------------------------

  // Options per look part (Sprites holds the matching palettes and hair styles).
  var LOOK = { skin: 6, hair: 5, hairCol: 8, top: 8, legs: 6 };
  var LOOK_KEYS = ["skin", "hair", "hairCol", "top", "legs"];
  var NAME_MAX = 12;

  // Letters, digits and single inner spaces, 1..12 characters; anything else gives "".
  function cleanName(v) {
    if (typeof v !== "string") return "";
    var n = v.replace(/\s+/g, " ").trim();
    return n.length >= 1 && n.length <= NAME_MAX && /^[A-Za-z0-9 ]+$/.test(n) ? n : "";
  }

  // A look with every part an integer index in range (bad or missing parts become 0).
  function cleanLook(v) {
    var o = {};
    LOOK_KEYS.forEach(function (k) {
      var x = v && typeof v === "object" ? v[k] : 0;
      o[k] = typeof x === "number" && x % 1 === 0 && x >= 0 && x < LOOK[k] ? x : 0;
    });
    return o;
  }

  return {
    TICK_MS: 600, INV_SIZE: 28, BANK_MAX: 200,
    GROUND_MAX: 64, GROUND_TICKS: 300, HP_REGEN_TICKS: 100, EAT_DELAY: 3, COMBAT_TICKS: 8, UNARMED_SPEED: 4,
    AGGRO_RANGE: 4, WANDER: 3, LEASH: 8,
    RETARGET_RANGE: 10, FIGHT_RANGE: 8, RESUME_RANGE: 10,
    FIRE_TICKS: 100, RECALL_CAST: 6, RECALL_CD: 500, RECALL_BLOCK: 8,
    GRAVE_SAFE: 3000, GRAVE_DANGER: 1000, KEEP_UNITS: 3,
    SHOP_RESTOCK: 50, FISH_MOVE: [250, 400],
    COURIER_TICKS: 3, DROP_TICKS: 1,
    GIVE_UP_TICKS: 10, BARK_RANGE: 8, BARK_GAP: 100, BARK_P: 1 / 200,
    CAP_HIDDEN: 24000, CAP_CLOSED: 6000,
    // Rested (10.14): every RESTED_RATE ticks away past a catch-up cap bank one tick of double XP, up to RESTED_MAX.
    RESTED_RATE: 10, RESTED_MAX: 6000,
    SEASON_TICKS: SEASON_TICKS, seasonIndex: seasonIndex, seasonLeft: seasonLeft,
    PERK_EVERY: PERK_EVERY, PERK_RESET_COINS: 25, perkPoints: perkPoints,
    PET_SPEED: PET_SPEED, PET_QUICK: PET_QUICK, PET_MAX_LVL: PET_MAX_LVL, PET_XP_MAX: PET_XP_MAX, PET_PERKS: PET_PERKS,
    PET_STAGES: PET_STAGES, petStage: petStage, petXpFor: petXpFor, petLevel: petLevel, petAttack: petAttack, petAttackRoll: petAttackRoll, petMaxHit: petMaxHit,
    MAX_XP10: 2000000000,
    SKILLS: SKILLS, EQUIP_SLOTS: EQUIP_SLOTS, STYLES: STYLES, XP_TABLE: XP_TABLE,
    style: style, levelForXp: levelForXp, xpForLevel: xpForLevel, gatherChance: gatherChance,
    makeChance: makeChance, playerAttackRoll: playerAttackRoll, playerDefenceRoll: playerDefenceRoll,
    playerMaxHit: playerMaxHit, npcAttackRoll: npcAttackRoll, npcDefenceRoll: npcDefenceRoll,
    hitChance: hitChance, combatLevel: combatLevel, combatXp10: combatXp10, buyPrice: buyPrice,
    sellPrice: sellPrice, levelColor: levelColor,
    LOOK: LOOK, LOOK_KEYS: LOOK_KEYS, NAME_MAX: NAME_MAX, cleanName: cleanName, cleanLook: cleanLook
  };
})();
// ==== src/engine/world.js ====
// ----------------------------------------------------------------
// --------------- World: maps, collision, pathing ----------------
// ----------------------------------------------------------------
// Parses Data.maps once at load (DESIGN.md section 8), builds SPAWNS and the fishing groups, and answers
// collision and pathing queries. The per-state blocked cache lives in state._blk (rebuilt when
// state.objVer changes); BFS uses scratch typed arrays that every call rewrites.
const World = (function () {
  "use strict";

  var T_IDS = Data.vocab && Array.isArray(Data.vocab.terrain) ? Data.vocab.terrain : [];
  var DX = [-1, 1, 0, 0, -1, 1, -1, 1];   // W, E, S, N, SW, SE, NW, NE
  var DY = [0, 0, 1, -1, 1, 1, -1, -1];
  var NEAR_RANGE = 10;

  // ----------------------------------------------------------------
  // ------------------------- Data lookups -------------------------
  // ----------------------------------------------------------------

  function objDef(id) {
    return typeof id === "string" && Util.has(Data.objects, id) ? Data.objects[id] : null;
  }

  function objBlocks(id) {
    var d = objDef(id);
    return !!d && d.block !== false;
  }

  function isInt(v) {
    return typeof v === "number" && Math.floor(v) === v;
  }

  // ----------------------------------------------------------------
  // -------------------------- Map parsing -------------------------
  // ----------------------------------------------------------------

  function terrainIndex() {
    var idx = {};
    for (var i = 0; i < T_IDS.length; i++) idx[T_IDS[i]] = i;
    return idx;
  }

  function walkable(tid) {
    return Util.has(Data.terrain, tid) && Data.terrain[tid].walk === true;
  }

  function parseRows(m, rows, tIndex) {
    var voidT = Util.has(tIndex, "void") ? tIndex["void"] : 0;
    for (var y = 0; y < m.h; y++) {
      var row = typeof rows[y] === "string" ? rows[y] : "";
      for (var x = 0; x < m.w; x++) {
        var ch = x < row.length ? row.charAt(x) : " ";
        var leg = Util.has(Data.legend, ch) ? Data.legend[ch] : null;
        var i = x + y * m.w;
        m.terr[i] = leg && Util.has(tIndex, leg.t) ? tIndex[leg.t] : voidT;
        m.sobj[i] = leg && objDef(leg.o) ? leg.o : null;
      }
    }
  }

  function applyPlacements(m, place) {
    for (var k = 0; k < place.length; k++) {
      var pl = place[k];
      if (!pl || !objDef(pl.o) || !isInt(pl.x) || !isInt(pl.y)) continue;
      if (pl.x < 0 || pl.y < 0 || pl.x >= m.w || pl.y >= m.h) continue;
      var i = pl.x + pl.y * m.w;
      m.sobj[i] = pl.o;
      if (Array.isArray(pl.to) && pl.to.length === 3) m.to[i] = [pl.to[0], pl.to[1], pl.to[2]];
    }
  }

  // Static blocking: _tb = terrain only, _ob = terrain plus static objects.
  function buildBlocking(m) {
    for (var i = 0; i < m.terr.length; i++) {
      var tb = walkable(m.tIds[m.terr[i]]) ? 0 : 1;
      m._tb[i] = tb;
      m._ob[i] = tb || (m.sobj[i] && objBlocks(m.sobj[i]) ? 1 : 0);
    }
  }

  function buildNodes(m) {
    for (var y = 0; y < m.h; y++) {
      for (var x = 0; x < m.w; x++) {
        var o = m.sobj[x + y * m.w];
        if (!o) continue;
        if (!Util.has(m.nodes, o)) m.nodes[o] = [];
        m.nodes[o].push([x, y]);
      }
    }
  }

  function parseMap(id, src, tIndex) {
    var rows = Array.isArray(src.rows) ? src.rows : [];
    var w = 0;
    for (var r = 0; r < rows.length; r++) if (typeof rows[r] === "string" && rows[r].length > w) w = rows[r].length;
    var h = w ? rows.length : 0;
    var n = w * h;
    var m = { id: id, name: typeof src.name === "string" ? src.name : id, dark: !!src.dark, w: w, h: h,
      terr: new Uint8Array(n), tIds: T_IDS, sobj: new Array(n), to: {}, nodes: {},
      _tb: new Uint8Array(n), _ob: new Uint8Array(n) };
    parseRows(m, rows, tIndex);
    applyPlacements(m, Array.isArray(src.place) ? src.place : []);
    buildBlocking(m);
    buildNodes(m);
    return m;
  }

  var maps = (function () {
    var out = {};
    var tIndex = terrainIndex();
    var ids = Data.maps ? Object.keys(Data.maps) : [];
    for (var k = 0; k < ids.length; k++) {
      var src = Data.maps[ids[k]];
      if (src && typeof src === "object") out[ids[k]] = parseMap(ids[k], src, tIndex);
    }
    return out;
  })();

  function getMap(id) {
    return typeof id === "string" && Util.has(maps, id) ? maps[id] : null;
  }

  function inMap(m, x, y) {
    return isInt(x) && isInt(y) && x >= 0 && y >= 0 && x < m.w && y < m.h;
  }

  function inBounds(map, x, y) {
    var m = getMap(map);
    return !!m && inMap(m, x, y);
  }

  function terrain(map, x, y) {
    var m = getMap(map);
    return m && inMap(m, x, y) ? m.tIds[m.terr[x + y * m.w]] : null;
  }

  function staticObj(map, x, y) {
    var m = getMap(map);
    if (!m || !inMap(m, x, y)) return null;
    var i = x + y * m.w;
    var o = m.sobj[i];
    return o ? { o: o, to: Util.has(m.to, i) ? m.to[i] : null } : null;
  }

  // ----------------------------------------------------------------
  // ------------------ Spawns and fishing groups -------------------
  // ----------------------------------------------------------------

  // uid = 1 + index; ordered by Data.maps key order, then each map's spawns order.
  var SPAWNS = (function () {
    var out = [];
    var ids = Object.keys(maps);
    for (var k = 0; k < ids.length; k++) {
      var list = Array.isArray(Data.maps[ids[k]].spawns) ? Data.maps[ids[k]].spawns : [];
      for (var j = 0; j < list.length; j++) {
        var sp = list[j];
        if (!sp || !Util.has(Data.npcs, sp.n) || !inBounds(ids[k], sp.x, sp.y)) continue;
        var def = Data.npcs[sp.n];
        var r = isInt(sp.r) ? sp.r : isInt(def.wander) ? def.wander : Rules.WANDER;
        out.push({ uid: out.length + 1, map: ids[k], x: sp.x, y: sp.y, id: sp.n, r: Math.max(0, r),
          cond: Array.isArray(sp.if) && sp.if.length ? sp.if : null });
      }
    }
    return out;
  })();

  // { [group]: { group, map, obj, n, tiles: [x, y][] } } in map order, then list order.
  var FISH = (function () {
    var out = {};
    var ids = Object.keys(maps);
    for (var k = 0; k < ids.length; k++) {
      var list = Array.isArray(Data.maps[ids[k]].fish) ? Data.maps[ids[k]].fish : [];
      for (var j = 0; j < list.length; j++) {
        var g = list[j];
        if (!g || typeof g.group !== "string" || Util.has(out, g.group) || !objDef(g.obj)) continue;
        var tiles = [];
        var src = Array.isArray(g.tiles) ? g.tiles : [];
        for (var t = 0; t < src.length; t++) {
          if (Array.isArray(src[t]) && inBounds(ids[k], src[t][0], src[t][1])) tiles.push([src[t][0], src[t][1]]);
        }
        out[g.group] = { group: g.group, map: ids[k], obj: g.obj, n: Util.int(g.n, 0, tiles.length, 0),
          tiles: tiles };
      }
    }
    return out;
  })();

  // ----------------------------------------------------------------
  // ------------------------ Blocked cache -------------------------
  // ----------------------------------------------------------------

  // state._blk[map] = { ver, a }: _ob with state.objs overrides applied (an override wins).
  function blockArray(state, m) {
    if (!state._blk || typeof state._blk !== "object") state._blk = {};
    var c = Util.has(state._blk, m.id) ? state._blk[m.id] : null;
    if (c && c.ver === state.objVer && c.a.length === m._ob.length) return c.a;
    var a = c && c.a.length === m._ob.length ? c.a : new Uint8Array(m._ob.length);
    a.set(m._ob);
    var pre = m.id + ":";
    var keys = state.objs ? Object.keys(state.objs) : [];
    for (var k = 0; k < keys.length; k++) {
      if (keys[k].lastIndexOf(pre, 0) !== 0) continue;
      var xy = keys[k].slice(pre.length).split(",");
      var x = +xy[0];
      var y = +xy[1];
      if (!inMap(m, x, y)) continue;
      var i = x + y * m.w;
      a[i] = m._tb[i] || (objBlocks(state.objs[keys[k]].o) ? 1 : 0);
    }
    state._blk[m.id] = { ver: state.objVer, a: a };
    return a;
  }

  function blocked(state, map, x, y) {
    var m = getMap(map);
    if (!m || !inMap(m, x, y)) return true;
    return blockArray(state, m)[x + y * m.w] === 1;
  }

  // Cardinal: the destination is free. Diagonal: the destination and both orthogonal tiles are free.
  function canStep(state, map, x, y, dx, dy) {
    var m = getMap(map);
    if (!m || !inMap(m, x, y) || (!dx && !dy) || dx < -1 || dx > 1 || dy < -1 || dy > 1) return false;
    var nx = x + dx;
    var ny = y + dy;
    if (!inMap(m, nx, ny)) return false;
    var a = blockArray(state, m);
    if (a[nx + ny * m.w]) return false;
    return !(dx && dy && (a[nx + y * m.w] || a[x + ny * m.w]));
  }

  // The player stands on a cardinal neighbour of (ox,oy), on a side listed in from ("s" = south of it).
  function adjacent(px, py, ox, oy, from) {
    var f = typeof from === "string" && from ? from : "nsew";
    if (px === ox && py === oy - 1) return f.indexOf("n") >= 0;
    if (px === ox && py === oy + 1) return f.indexOf("s") >= 0;
    if (py === oy && px === ox + 1) return f.indexOf("e") >= 0;
    if (py === oy && px === ox - 1) return f.indexOf("w") >= 0;
    return false;
  }

  // ----------------------------------------------------------------
  // ------------------------------ BFS -----------------------------
  // ----------------------------------------------------------------

  var MAX_N = (function () {
    var n = 1;
    var ids = Object.keys(maps);
    for (var k = 0; k < ids.length; k++) n = Math.max(n, maps[ids[k]].w * maps[ids[k]].h);
    return n;
  })();
  var PREV = new Int32Array(MAX_N);    // parent index, -1 = unvisited
  var QUEUE = new Int32Array(MAX_N);   // visit order (BFS order)

  function radiusOf(m, radius) {
    return typeof radius === "number" && radius >= 0 ? radius : Math.max(m.w, m.h);
  }

  // BFS from (sx,sy) inside the Chebyshev window; test(x, y, i) marks a goal. Returns { end, count }:
  // end = goal index or -1, and QUEUE[0..count) holds the visited tiles in BFS order.
  function search(state, m, sx, sy, r, test) {
    var w = m.w;
    var h = m.h;
    var a = blockArray(state, m);
    PREV.fill(-1, 0, w * h);
    var s = sx + sy * w;
    PREV[s] = s;
    QUEUE[0] = s;
    var head = 0;
    var tail = 1;
    while (head < tail) {
      var i = QUEUE[head++];
      var x = i % w;
      var y = (i - x) / w;
      if (test(x, y, i)) return { end: i, count: tail };
      for (var d = 0; d < 8; d++) {
        var nx = x + DX[d];
        var ny = y + DY[d];
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        if (nx - sx > r || sx - nx > r || ny - sy > r || sy - ny > r) continue;
        var j = nx + ny * w;
        if (PREV[j] !== -1 || a[j]) continue;
        if (d >= 4 && (a[nx + y * w] || a[x + ny * w])) continue;
        PREV[j] = i;
        QUEUE[tail++] = j;
      }
    }
    return { end: -1, count: tail };
  }

  // Steps from the start to end, excluding the start.
  function trace(m, end) {
    var out = [];
    var i = end;
    while (PREV[i] !== i) {
      out.push([i % m.w, (i - (i % m.w)) / m.w]);
      i = PREV[i];
    }
    out.reverse();
    return out;
  }

  // Unreachable "near" walk: the visited tile within 10 of the target with the smallest dx^2+dy^2
  // (ties: fewer steps, then BFS order, which is the visit order).
  function nearest(m, count, gx, gy) {
    var best = -1;
    var bestD = Infinity;
    for (var k = 0; k < count; k++) {
      var i = QUEUE[k];
      var dx = (i % m.w) - gx;
      var dy = (i - (i % m.w)) / m.w - gy;
      if (Math.max(Math.abs(dx), Math.abs(dy)) > NEAR_RANGE) continue;
      var d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    return best;
  }

  // goal = {x, y, mode:"tile", near?} | {x, y, mode:"adj", from?}. Returns steps, [] or null.
  function findPath(state, map, sx, sy, goal, radius) {
    var m = getMap(map);
    if (!m || !inMap(m, sx, sy) || !goal || !isInt(goal.x) || !isInt(goal.y)) return null;
    var gx = goal.x;
    var gy = goal.y;
    var test;
    if (goal.mode === "adj") test = function (x, y) { return adjacent(x, y, gx, gy, goal.from); };
    else if (goal.mode === "tile") test = function (x, y) { return x === gx && y === gy; };
    else return null;
    var res = search(state, m, sx, sy, radiusOf(m, radius), test);
    if (res.end >= 0) return trace(m, res.end);
    if (goal.mode !== "tile" || !goal.near) return null;
    var best = nearest(m, res.count, gx, gy);
    return best >= 0 ? trace(m, best) : null;
  }

  // cands = [x, y, from][]: path to the first tile adjacent to any candidate (lowest index wins a tile).
  function findPathAny(state, map, sx, sy, cands, radius) {
    var m = getMap(map);
    if (!m || !inMap(m, sx, sy) || !Array.isArray(cands) || !cands.length) return null;
    var goals = {};
    for (var c = cands.length - 1; c >= 0; c--) {
      var cd = cands[c];
      if (!Array.isArray(cd) || !inMap(m, cd[0], cd[1])) continue;
      for (var d = 0; d < 4; d++) {
        var nx = cd[0] + DX[d];
        var ny = cd[1] + DY[d];
        if (inMap(m, nx, ny) && adjacent(nx, ny, cd[0], cd[1], cd[2])) goals[nx + ny * m.w] = c;
      }
    }
    var res = search(state, m, sx, sy, radiusOf(m, radius), function (x, y, i) { return Util.has(goals, i); });
    return res.end >= 0 ? { path: trace(m, res.end), i: goals[res.end] } : null;
  }

  // Naive NPC step toward (tx,ty): the diagonal, then the x axis, then the y axis. Returns [x, y] or null.
  function step(state, map, x, y, tx, ty, avoid) {
    var sx = tx > x ? 1 : tx < x ? -1 : 0;
    var sy = ty > y ? 1 : ty < y ? -1 : 0;
    if (sx && sy && free(state, map, x, y, sx, sy, avoid)) return [x + sx, y + sy];
    if (sx && free(state, map, x, y, sx, 0, avoid)) return [x + sx, y];
    if (sy && free(state, map, x, y, 0, sy, avoid)) return [x, y + sy];
    return null;
  }

  function free(state, map, x, y, dx, dy, avoid) {
    return canStep(state, map, x, y, dx, dy) && !(avoid && avoid(x + dx, y + dy));
  }

  // ----------------------------------------------------------------
  // ---------------------------- Regions ---------------------------
  // ----------------------------------------------------------------

  function regionAt(map, x, y) {
    var list = Array.isArray(Data.regions) ? Data.regions : [];
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r && r.map === map && Array.isArray(r.rect) && Util.inRect(r.rect, x, y)) return r;
    }
    return null;
  }

  return {
    maps: maps, SPAWNS: SPAWNS, FISH: FISH, inBounds: inBounds, terrain: terrain, staticObj: staticObj,
    blocked: blocked, canStep: canStep, adjacent: adjacent, findPath: findPath, findPathAny: findPathAny,
    step: step, regionAt: regionAt
  };
})();
// ==== src/engine/player.js ====
// ----------------------------------------------------------------
// --------------- Player: inventory, bank, gear, XP --------------
// ----------------------------------------------------------------
// Levels and XP, the 28-slot pack, ground drops, food, tools, equipment, the bank, the death split and
// teleport (DESIGN.md section 9 Player). Every function validates its own arguments and never throws.
const Player = (function () {
  "use strict";

  var QTY_MAX = 2147483647;
  var FULL = "Your pack is full.";
  var NOTHING = "That doesn't do anything.";
  var NO_ROOM_SHIELD = "Your pack has no room for your shield.";
  var NO_ROOM_WEAPON = "Your pack has no room for your weapon.";

  function item(id) {
    return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id] : null;
  }

  function stackable(id) {
    var it = item(id);
    return !!it && it.stack === true;
  }

  // Notes: a noted slot { id, qty, note: true } is a stack of a non-stackable item, withdrawn from the bank
  // in Note mode. Notes bank, sell, drop and stack; count, has, remove and every use (eat, wear, tools,
  // recipes, quests) ignore them. Quest and untradeable items can't be noted.
  function notable(id) {
    var it = item(id);
    return !!it && it.stack !== true && it.cat !== "quest" && it.untradeable !== true;
  }

  function isSlot(p, slot) {
    return typeof slot === "number" && Math.floor(slot) === slot && slot >= 0 && slot < p.inv.length;
  }

  // n as an amount: -1 = all of have, -2 = all but 1, else 1..have; anything else gives 0.
  function amount(n, have) {
    if (n === -1) return have;
    if (n === -2) return Math.max(0, have - 1);
    if (typeof n !== "number" || Math.floor(n) !== n || n < 1) return 0;
    return Math.min(n, have);
  }

  // ----------------------------------------------------------------
  // ------------------------- Levels and XP ------------------------
  // ----------------------------------------------------------------

  function xp10Of(p, skill) {
    return Util.has(p.xp10, skill) ? p.xp10[skill] : 0;
  }

  // xp10 / 10 is exact at every whole-XP threshold, so the real-XP table applies directly.
  function level(p, skill) {
    return Rules.levelForXp(xp10Of(p, skill) / 10);
  }

  function maxHp(p) {
    return level(p, "hitpoints");
  }

  function combatLevel(p) {
    return Rules.combatLevel(level(p, "attack"), level(p, "strength"), level(p, "defence"), level(p, "hitpoints"));
  }

  function totalLevel(p) {
    var t = 0;
    for (var i = 0; i < Rules.SKILLS.length; i++) t += level(p, Rules.SKILLS[i]);
    return t;
  }

  function skillName(id) {
    var list = Array.isArray(Data.skills) ? Data.skills : [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i].name;
    return id;
  }

  // Adds n xp10 (capped). Emits xp, then level (+ chat line), cmb and save on a level-up.
  // active: XP from gathering, making or a combat hit, which doubles while rested (10.14); quest and
  // script rewards never do.
  function addXp10(state, skill, n, active) {
    var p = state.player;
    var add = Math.floor(n);
    if (!(add > 0) || Rules.SKILLS.indexOf(skill) < 0) return;
    var rested = active === true && p.rested > 0;
    if (rested) add *= 2;
    var before = level(p, skill);
    var cmbBefore = combatLevel(p);
    p.xp10[skill] = Math.min(Rules.MAX_XP10, xp10Of(p, skill) + add);
    Util.emit(state, rested ? { type: "xp", skill: skill, amt: add / 10, rested: true } : { type: "xp", skill: skill, amt: add / 10 });
    var after = level(p, skill);
    if (after <= before) return;
    if (skill === "hitpoints" && p.hp > 0) p.hp = Math.min(after, p.hp + (after - before));
    Util.emit(state, { type: "level", skill: skill, lvl: after });
    Util.msg(state, skillName(skill) + " level up! You are now level " + after + ".", "skill");
    // Crossing one or more multiples of 5 earns perk points (only a skill that has perks says so).
    if (Rules.perkPoints(after) > Rules.perkPoints(before) && perkList(skill).length) {
      Util.emit(state, { type: "perkpoint", skill: skill, free: perkFree(p, skill) });
    }
    var cmbAfter = combatLevel(p);
    if (cmbAfter !== cmbBefore) {
      Util.emit(state, { type: "cmb", lvl: cmbAfter });
      Util.msg(state, "Combat level is now " + cmbAfter + ".", "game");
    }
    Util.emit(state, { type: "save" });
  }

  function addXp(state, skill, real, active) {
    if (typeof real === "number" && isFinite(real)) addXp10(state, skill, Math.round(real * 10), active);
  }

  // ----------------------------------------------------------------
  // ----------------------------- Perks ----------------------------
  // ----------------------------------------------------------------
  // p.perks = { perkId: rank } (ranks > 0 only). Points are derived from levels, so nothing migrates:
  // free = Rules.perkPoints(level) - the ranks spent in that skill (DESIGN.md 10.13).

  // The perk defs of a skill (Data.perks); [] for unknown skills or data without perks.
  function perkList(skill) {
    var all = Data.perks;
    return typeof skill === "string" && all && Util.has(all, skill) && Array.isArray(all[skill]) ? all[skill] : [];
  }

  // { def, skill } of a perk id, or null.
  function perkDef(id) {
    if (typeof id !== "string") return null;
    for (var i = 0; i < Rules.SKILLS.length; i++) {
      var list = perkList(Rules.SKILLS[i]);
      for (var k = 0; k < list.length; k++) if (list[k] && list[k].id === id) return { def: list[k], skill: Rules.SKILLS[i] };
    }
    return null;
  }

  function perkRank(p, id) {
    return p.perks && Util.has(p.perks, id) ? p.perks[id] : 0;
  }

  function perkPoints(p, skill) {
    return Rules.perkPoints(level(p, skill));
  }

  function perkSpent(p, skill) {
    var n = 0;
    perkList(skill).forEach(function (d) { n += perkRank(p, d.id); });
    return n;
  }

  function perkFree(p, skill) {
    return Math.max(0, perkPoints(p, skill) - perkSpent(p, skill));
  }

  // A perk with `groups` only works on recipes of those groups; without, on every action of its skill.
  function perkFits(d, group) {
    return !Array.isArray(d.groups) || d.groups.indexOf(group) >= 0;
  }

  // rank x per summed over the skill's perks with effect fx (0 while none is taken).
  function perkVal(p, skill, fx, group) {
    var v = 0;
    perkList(skill).forEach(function (d) {
      if (d.fx === fx && typeof d.per === "number" && perkFits(d, group)) v += perkRank(p, d.id) * d.per;
    });
    return v;
  }

  // Ranks taken in the skill's perks with effect fx.
  function perkRanks(p, skill, fx) {
    var n = 0;
    perkList(skill).forEach(function (d) { if (d.fx === fx) n += perkRank(p, d.id); });
    return n;
  }

  // A chance perk firing: one roll on state.rng, and no roll at all while it has no ranks, so an
  // unperked character plays exactly as before.
  function perkRoll(state, skill, fx, group) {
    var v = perkVal(state.player, skill, fx, group);
    return v > 0 && Util.rand(state) < v;
  }

  // The chat line (Data msg) of a chance perk that fired.
  function perkMsg(state, skill, fx, group, c) {
    perkList(skill).forEach(function (d) {
      if (d.fx === fx && perkFits(d, group) && typeof d.msg === "string") Util.msg(state, d.msg, c || "skill");
    });
  }

  // Engine.perkUp: one more rank, paid with a free point of the perk's skill.
  function perkUp(state, id) {
    var p = state.player;
    var f = perkDef(id);
    if (!f || perkRank(p, id) >= f.def.max || perkFree(p, f.skill) < 1) return false;
    p.perks[id] = perkRank(p, id) + 1;
    return true;
  }

  // Engine.perkReset: every rank of the skill back as points, for PERK_RESET_COINS a point from the pack.
  function perkReset(state, skill) {
    var p = state.player;
    var spent = Rules.SKILLS.indexOf(skill) >= 0 ? perkSpent(p, skill) : 0;
    if (!(spent > 0)) return false;
    var cost = spent * Rules.PERK_RESET_COINS;
    if (count(p, "coins") < cost) {
      Util.msg(state, "You need " + Util.fmtInt(cost) + " coins to reset these perks.", "warn");
      return false;
    }
    remove(p, "coins", cost);
    perkList(skill).forEach(function (d) { delete p.perks[d.id]; });
    Util.msg(state, "Your " + skillName(skill) + " perks are reset for " + Util.fmtInt(cost) + " coins.", "game");
    return true;
  }

  // ----------------------------------------------------------------
  // -------------------------- Inventory ---------------------------
  // ----------------------------------------------------------------

  function count(p, id) {
    var n = 0;
    for (var i = 0; i < p.inv.length; i++) if (p.inv[i] && p.inv[i].id === id && !p.inv[i].note) n += p.inv[i].qty;
    return n;
  }

  function has(p, id, qty) {
    return count(p, id) >= (typeof qty === "number" ? qty : 1);
  }

  function free(p) {
    var n = 0;
    for (var i = 0; i < p.inv.length; i++) if (!p.inv[i]) n++;
    return n;
  }

  function stackSlot(p, id) {
    for (var i = 0; i < p.inv.length; i++) if (p.inv[i] && p.inv[i].id === id && !p.inv[i].note) return i;
    return -1;
  }

  function noteSlot(p, id) {
    for (var i = 0; i < p.inv.length; i++) if (p.inv[i] && p.inv[i].id === id && p.inv[i].note) return i;
    return -1;
  }

  function canAdd(p, id, qty) {
    if (!item(id) || !(qty >= 1)) return false;
    if (stackable(id)) return stackSlot(p, id) >= 0 ? count(p, id) + qty <= QTY_MAX : free(p) > 0;
    return free(p) >= qty;
  }

  // Adds up to qty; stackables (and notes, when `note` is set and the item is notable) merge into one slot.
  // Returns the number added.
  function add(p, id, qty, note) {
    var n = Math.floor(qty);
    if (!item(id) || !(n >= 1)) return 0;
    var noted = !!note && notable(id);
    if (noted || stackable(id)) {
      var s = noted ? noteSlot(p, id) : stackSlot(p, id);
      if (s >= 0) {
        var put = Math.min(QTY_MAX - p.inv[s].qty, n);
        p.inv[s].qty += put;
        return put;
      }
      s = p.inv.indexOf(null);
      if (s < 0) return 0;
      p.inv[s] = noted ? { id: id, qty: Math.min(n, QTY_MAX), note: true } : { id: id, qty: Math.min(n, QTY_MAX) };
      return p.inv[s].qty;
    }
    var added = 0;
    for (var i = 0; i < p.inv.length && added < n; i++) {
      if (p.inv[i]) continue;
      p.inv[i] = { id: id, qty: 1 };
      added++;
    }
    return added;
  }

  // Removes up to qty, lowest slot first. Returns the number removed.
  function remove(p, id, qty) {
    var left = Math.floor(qty);
    var removed = 0;
    for (var i = 0; i < p.inv.length && left > 0; i++) {
      var s = p.inv[i];
      if (!s || s.id !== id || s.note) continue;
      var take = Math.min(s.qty, left);
      s.qty -= take;
      left -= take;
      removed += take;
      if (s.qty <= 0) p.inv[i] = null;
    }
    return removed;
  }

  // Takes up to qty from one slot; returns the removed { id, qty } (note: true from a noted slot) or null.
  function removeAt(p, slot, qty) {
    if (!isSlot(p, slot) || !p.inv[slot]) return null;
    var s = p.inv[slot];
    var take = Math.min(s.qty, Math.max(1, Math.floor(qty) || 1));
    s.qty -= take;
    if (s.qty <= 0) p.inv[slot] = null;
    return s.note ? { id: s.id, qty: take, note: true } : { id: s.id, qty: take };
  }

  // Removes n of the item in `slot`: that slot first, then the lowest other slots (a noted slot only
  // gives its own). Returns the count.
  function takeFrom(p, slot, n) {
    var s = p.inv[slot];
    var id = s.id;
    var first = removeAt(p, slot, Math.min(n, s.qty));
    var got = first ? first.qty : 0;
    return got + (got < n && !s.note ? remove(p, id, n - got) : 0);
  }

  // Swaps two slots.
  function move(p, from, to) {
    if (!isSlot(p, from) || !isSlot(p, to) || from === to) return false;
    var t = p.inv[from];
    p.inv[from] = p.inv[to];
    p.inv[to] = t;
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------ Ground and give -----------------------
  // ----------------------------------------------------------------

  // A ground pile: the same id (and noted-ness) on the same tile merges and its timer restarts (the merged
  // pile moves to the newest end); past GROUND_MAX the oldest entries go. Returns false when nothing was placed.
  function toGround(state, map, x, y, id, qty, note) {
    var n = Math.floor(qty);
    if (!item(id) || !(n >= 1) || !World.inBounds(map, x, y)) return false;
    var noted = !!note && notable(id);
    var list = state.ground;
    var until = state.tick + Rules.GROUND_TICKS;
    for (var i = 0; i < list.length; i++) {
      var g = list[i];
      if (g.map !== map || g.x !== x || g.y !== y || g.id !== id || !!g.note !== noted) continue;
      list.splice(i, 1);
      g.qty = Math.min(QTY_MAX, g.qty + n);
      g.until = until;
      list.push(g);
      return true;
    }
    var e = { gid: state.gid, map: map, x: x, y: y, id: id, qty: Math.min(n, QTY_MAX), until: until };
    if (noted) e.note = true;
    list.push(e);
    state.gid++;
    if (list.length > Rules.GROUND_MAX) list.splice(0, list.length - Rules.GROUND_MAX);
    return true;
  }

  // Into the pack; whatever doesn't fit drops under the player. Returns the number that went in the pack.
  function give(state, id, qty) {
    var n = Math.floor(qty);
    if (!item(id) || !(n >= 1)) return 0;
    var p = state.player;
    var added = add(p, id, n);
    if (added < n && toGround(state, p.map, p.x, p.y, id, n - added)) {
      Util.msg(state, "Your pack is full; it drops at your feet.", "warn");
    }
    return added;
  }

  // Drops a whole slot on the player's tile. Quest items can't be dropped.
  function drop(state, slot) {
    var p = state.player;
    var s = isSlot(p, slot) ? p.inv[slot] : null;
    var d = s ? item(s.id) : null;
    if (!d || d.cat === "quest") return false;
    if (!toGround(state, p.map, p.x, p.y, s.id, s.qty, s.note)) return false;
    p.inv[slot] = null;
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------------ Food ----------------------------
  // ----------------------------------------------------------------

  // A food slot's heal with Hearty (cooking) and Iron gut (Vitality) added together; -1 for non-food.
  function healOf(p, slot) {
    var d = p.inv[slot] && !p.inv[slot].note ? item(p.inv[slot].id) : null;
    if (!d || !d.food) return -1;
    var heal = Util.int(d.food.heal, 0, QTY_MAX, 0);
    var v = perkVal(p, "cooking", "heal") + perkVal(p, "hitpoints", "heal");
    return v > 0 ? Math.round(heal * (1 + v)) : heal;
  }

  // Food slot indices, lowest heal first, then slot order.
  function foods(p) {
    var out = [];
    for (var i = 0; i < p.inv.length; i++) if (healOf(p, i) >= 0) out.push(i);
    return out.sort(function (a, b) { return healOf(p, a) - healOf(p, b) || a - b; });
  }

  // Section 10.5: needs eatTimer 0; heals at once, eatTimer = 3, atkTimer += 3. Never touches the act.
  function eat(state, slot) {
    var p = state.player;
    var heal = isSlot(p, slot) ? healOf(p, slot) : -1;
    if (heal < 0 || p.eatTimer > 0 || p.hp <= 0) return false;
    var s = removeAt(p, slot, 1);
    var amt = Math.max(0, Math.min(heal, maxHp(p) - p.hp));
    p.hp += amt;
    p.eatTimer = Rules.EAT_DELAY;
    p.atkTimer += Rules.EAT_DELAY;
    p.anim = "eat";
    p.animAt = state.tick;
    Util.emit(state, { type: "eat", id: s.id });
    Util.msg(state, "You eat " + item(s.id).name.toLowerCase() + ".", "game");
    if (amt > 0) Util.emit(state, { type: "heal", on: 0, amt: amt });
    return true;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Tools ----------------------------
  // ----------------------------------------------------------------

  var TOOL_SKILL = { axe: "woodcutting", pickaxe: "mining" };

  // Tool items held in the pack or the weapon slot.
  function heldTools(p, cat) {
    var out = [];
    var ids = p.inv.map(function (s) { return s && !s.note ? s.id : null; }).concat([p.eq.weapon]);
    for (var i = 0; i < ids.length; i++) {
      var it = item(ids[i]);
      if (it && it.tool && it.tool.cat === cat && out.indexOf(ids[i]) < 0) out.push(ids[i]);
    }
    return out;
  }

  // Highest mult among usable tools of cat (axes/pickaxes need their gather level).
  function bestTool(p, cat) {
    var best = null;
    var bestMult = -1;
    var list = heldTools(p, cat);
    for (var i = 0; i < list.length; i++) {
      var t = item(list[i]).tool;
      var mult = typeof t.mult === "number" ? t.mult : 1;
      var lvl = typeof t.lvl === "number" ? t.lvl : 1;
      if (Util.has(TOOL_SKILL, cat) && level(p, TOOL_SKILL[cat]) < lvl) continue;
      if (mult > bestMult) {
        best = list[i];
        bestMult = mult;
      }
    }
    return best;
  }

  function hasTools(p, cats) {
    var list = Array.isArray(cats) ? cats : [];
    for (var i = 0; i < list.length; i++) if (!heldTools(p, list[i]).length) return false;
    return true;
  }

  // ----------------------------------------------------------------
  // --------------------------- Equipment --------------------------
  // ----------------------------------------------------------------

  // Level requirements, then the `if` conditions (Script.test at runtime); warns on the first failure.
  function canWear(state, e) {
    var p = state.player;
    var req = e.req && typeof e.req === "object" ? e.req : {};
    var keys = Object.keys(req);
    for (var i = 0; i < keys.length; i++) {
      if (Rules.SKILLS.indexOf(keys[i]) < 0 || level(p, keys[i]) >= req[keys[i]]) continue;
      Util.msg(state, "You need " + skillName(keys[i]) + " level " + req[keys[i]] + " for this.", "warn");
      return false;
    }
    if (e.if && !Script.test(state, e.if)) {
      Util.msg(state, typeof e.ifMsg === "string" ? e.ifMsg : NOTHING, "warn");
      return false;
    }
    return true;
  }

  function twoHanded(id) {
    var it = item(id);
    return !!it && !!it.equip && it.equip.slot === "weapon" && it.equip.twoHanded === true;
  }

  // Wield/wear from an inventory slot; the replaced item takes that same slot. A two-handed weapon and
  // a shield never share the hands: wielding one sends the other to the pack too, or nothing changes.
  function equip(state, slot) {
    var p = state.player;
    var s = isSlot(p, slot) ? p.inv[slot] : null;
    var e = s && !s.note && item(s.id) ? item(s.id).equip : null;
    if (!e || Rules.EQUIP_SLOTS.indexOf(e.slot) < 0 || !canWear(state, e)) return false;
    var old = p.eq[e.slot];
    var clash = e.slot === "weapon" && twoHanded(s.id) ? "shield"
      : e.slot === "shield" && twoHanded(p.eq.weapon) ? "weapon" : null;
    var off = clash ? p.eq[clash] : null;
    // the slot being emptied takes one of them; the rest need free slots
    if ((old ? 1 : 0) + (off ? 1 : 0) > free(p) + (s.qty === 1 ? 1 : 0)) {
      Util.msg(state, !off ? FULL : clash === "shield" ? NO_ROOM_SHIELD : NO_ROOM_WEAPON, "warn");
      return false;
    }
    removeAt(p, slot, 1);
    p.eq[e.slot] = s.id;
    if (clash) p.eq[clash] = null;
    [old, off].forEach(function (id) {
      if (id && !p.inv[slot]) p.inv[slot] = { id: id, qty: 1 };
      else if (id) add(p, id, 1);
    });
    return true;
  }

  // Into the first free slot; needs room.
  function unequip(state, eqSlot) {
    var p = state.player;
    if (Rules.EQUIP_SLOTS.indexOf(eqSlot) < 0 || !p.eq[eqSlot]) return false;
    if (!canAdd(p, p.eq[eqSlot], 1)) {
      Util.msg(state, FULL, "warn");
      return false;
    }
    add(p, p.eq[eqSlot], 1);
    p.eq[eqSlot] = null;
    return true;
  }

  function stat(e, k) {
    return typeof e[k] === "number" && isFinite(e[k]) ? e[k] : 0;
  }

  // Summed att/str/def of worn items plus the Brute and Bulwark perks; speed is the weapon's, or unarmed.
  function bonuses(p) {
    var b = { att: 0, str: 0, def: 0, speed: Rules.UNARMED_SPEED };
    for (var i = 0; i < Rules.EQUIP_SLOTS.length; i++) {
      var d = item(p.eq[Rules.EQUIP_SLOTS[i]]);
      if (!d || !d.equip) continue;
      b.att += stat(d.equip, "att");
      b.str += stat(d.equip, "str");
      b.def += stat(d.equip, "def");
    }
    var w = item(p.eq.weapon);
    if (w && w.equip && stat(w.equip, "speed") >= 1) b.speed = w.equip.speed;
    b.str += perkVal(p, "strength", "strb");   // Brute
    b.def += perkVal(p, "defence", "defb");    // Bulwark
    return b;
  }

  // ----------------------------------------------------------------
  // ------------------------------ Bank ----------------------------
  // ----------------------------------------------------------------

  function bankAt(p, id) {
    for (var i = 0; i < p.bank.length; i++) if (p.bank[i].id === id) return i;
    return -1;
  }

  // How many of id the bank can still take.
  function bankRoom(p, id) {
    var i = bankAt(p, id);
    if (i >= 0) return QTY_MAX - p.bank[i].qty;
    return p.bank.length < Rules.BANK_MAX ? QTY_MAX : 0;
  }

  // Adds qty (call with qty <= bankRoom); a new id is appended at the end.
  function bankPut(p, id, qty) {
    var i = bankAt(p, id);
    if (i >= 0) p.bank[i].qty += qty;
    else p.bank.push({ id: id, qty: qty });
  }

  function bankCount(p, id) {
    var i = bankAt(p, id);
    return i >= 0 ? p.bank[i].qty : 0;
  }

  function bankRemove(p, id, qty) {
    var i = bankAt(p, id);
    if (i < 0 || p.bank[i].qty < qty) return false;
    p.bank[i].qty -= qty;
    if (p.bank[i].qty === 0) p.bank.splice(i, 1);
    return true;
  }

  // n of the clicked item's id: that slot first, then the lowest other slots (a noted slot: only itself).
  // Notes bank as the plain item.
  function deposit(state, slot, n) {
    var p = state.player;
    var s = isSlot(p, slot) ? p.inv[slot] : null;
    if (!s || !item(s.id)) return false;
    var id = s.id;
    var k = Math.min(amount(n, s.note ? s.qty : count(p, id)), bankRoom(p, id));
    if (k <= 0) return false;
    bankPut(p, id, takeFrom(p, slot, k));
    return true;
  }

  function depositAll(state) {
    var p = state.player;
    var moved = false;
    for (var i = 0; i < p.inv.length; i++) {
      var s = p.inv[i];
      var k = s && item(s.id) ? Math.min(s.qty, bankRoom(p, s.id)) : 0;
      if (k <= 0) continue;
      removeAt(p, i, k);
      bankPut(p, s.id, k);
      moved = true;
    }
    return moved;
  }

  function depositWorn(state) {
    var p = state.player;
    var moved = false;
    for (var i = 0; i < Rules.EQUIP_SLOTS.length; i++) {
      var slot = Rules.EQUIP_SLOTS[i];
      var id = p.eq[slot];
      if (!id || !item(id) || bankRoom(p, id) < 1) continue;
      bankPut(p, id, 1);
      p.eq[slot] = null;
      moved = true;
    }
    return moved;
  }

  // Non-stackables fill free slots, or one noted stack while p.bankNote is on; an entry that reaches 0 is
  // removed. Items that can't be noted come out as items.
  function withdraw(state, bankIndex, n) {
    var p = state.player;
    var ok = typeof bankIndex === "number" && Math.floor(bankIndex) === bankIndex && bankIndex >= 0 &&
      bankIndex < p.bank.length;
    var e = ok ? p.bank[bankIndex] : null;
    var k = e ? amount(n, e.qty) : 0;
    if (k <= 0) return false;
    var note = p.bankNote === true && !stackable(e.id);
    if (note && !notable(e.id)) {
      Util.msg(state, "That item can't be withdrawn as a note.", "warn");
      note = false;
    }
    var got = add(p, e.id, k, note);
    if (got < k) Util.msg(state, FULL, "warn");
    if (got <= 0) return false;
    e.qty -= got;
    if (e.qty <= 0) p.bank.splice(bankIndex, 1);
    return true;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Death -----------------------------
  // ----------------------------------------------------------------

  function alwaysKept(d) {
    return !!d && (!!d.tool || d.untradeable === true);
  }

  // Merges a pile into a per-id (and noted-ness) list (first-seen order).
  function pile(list, id, qty, note) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id !== id || !!list[i].note !== !!note) continue;
      list[i].qty = Math.min(QTY_MAX, list[i].qty + qty);
      return;
    }
    list.push(note ? { id: id, qty: qty, note: true } : { id: id, qty: qty });
  }

  // Section 10.8. keepInv: kept inventory piles in slot order; keepEq: {slot: id}; lose: one pile per id
  // (worn items first, then the pack). The top KEEP_UNITS units by value are picked among the rest:
  // the pack only in a safe area, worn items and pack in a danger region (ties: worn by EQUIP_SLOTS, then slot).
  function deathSplit(p, danger) {
    var keepInv = [];
    var keepEq = {};
    var units = [];
    for (var k = 0; k < Rules.EQUIP_SLOTS.length; k++) {
      var slot = Rules.EQUIP_SLOTS[k];
      var d = item(p.eq[slot]);
      if (!d) continue;
      if (!danger || alwaysKept(d)) keepEq[slot] = p.eq[slot];
      else units.push({ v: d.value || 0, order: k, eq: slot, id: p.eq[slot], qty: 1, keep: 0 });
    }
    for (var i = 0; i < p.inv.length; i++) {
      var s = p.inv[i];
      var di = s ? item(s.id) : null;
      if (!di) continue;
      if (alwaysKept(di)) keepInv.push({ i: i, id: s.id, qty: s.qty, note: !!s.note });
      else units.push({ v: di.value || 0, order: 100 + i, inv: i, id: s.id, qty: s.qty, keep: 0, note: !!s.note });
    }
    pickKept(units);
    var lose = [];
    for (var u = 0; u < units.length; u++) {
      var e = units[u];
      if (e.keep && e.eq) keepEq[e.eq] = e.id;
      else if (e.keep) keepInv.push({ i: e.inv, id: e.id, qty: e.keep, note: e.note });
      if (e.qty > e.keep) pile(lose, e.id, e.qty - e.keep, e.note);
    }
    keepInv.sort(function (a, b) { return a.i - b.i; });
    return {
      keepInv: keepInv.map(function (x) { return x.note ? { id: x.id, qty: x.qty, note: true } : { id: x.id, qty: x.qty }; }),
      keepEq: keepEq, lose: lose
    };
  }

  // Marks the KEEP_UNITS most valuable units (a stack gives its units one by one).
  function pickKept(units) {
    var order = units.slice().sort(function (a, b) { return b.v - a.v || a.order - b.order; });
    var left = Rules.KEEP_UNITS;
    for (var i = 0; i < order.length && left > 0; i++) {
      order[i].keep = Math.min(left, order[i].qty);
      left -= order[i].keep;
    }
  }

  // ----------------------------------------------------------------
  // --------------------------- Teleport ---------------------------
  // ----------------------------------------------------------------

  // A blocked arrival (a fire lit on a ladder's landing tile) lands on its first free side, W, E, S, N.
  function teleport(state, map, x, y) {
    var p = state.player;
    if (World.blocked(state, map, x, y)) {
      var dx = [-1, 1, 0, 0];
      var dy = [0, 0, 1, -1];
      for (var d = 0; d < 4; d++) {
        if (World.blocked(state, map, x + dx[d], y + dy[d])) continue;
        x += dx[d];
        y += dy[d];
        break;
      }
    }
    p.map = map;
    p.x = p.px = p.mx = x;
    p.y = p.py = p.my = y;
    p.path = [];
    Util.emit(state, { type: "tp", map: map });
  }

  return {
    level: level, maxHp: maxHp, combatLevel: combatLevel, totalLevel: totalLevel, skillName: skillName,
    addXp10: addXp10, addXp: addXp, count: count, has: has, free: free, canAdd: canAdd, add: add, remove: remove,
    notable: notable, noteSlot: noteSlot,
    removeAt: removeAt, move: move, toGround: toGround, give: give, drop: drop, foods: foods, eat: eat,
    heldTools: heldTools, bestTool: bestTool, hasTools: hasTools, equip: equip, unequip: unequip, bonuses: bonuses,
    twoHanded: twoHanded,
    bankCount: bankCount, bankRemove: bankRemove, bankPut: bankPut,
    deposit: deposit, depositAll: depositAll, depositWorn: depositWorn, withdraw: withdraw, deathSplit: deathSplit, teleport: teleport,
    healOf: healOf, perkList: perkList, perkDef: perkDef, perkRank: perkRank, perkPoints: perkPoints, perkSpent: perkSpent,
    perkFree: perkFree, perkVal: perkVal, perkRanks: perkRanks, perkRoll: perkRoll, perkMsg: perkMsg, perkUp: perkUp,
    perkReset: perkReset
  };
})();
// ==== src/engine/script.js ====
// ----------------------------------------------------------------
// ------------ Script: conds, effects, dialogue, quests ----------
// ----------------------------------------------------------------
// Conditions, effects, the dialogue runner, quest stages/advance/rewards, hints and keep lists
// (DESIGN.md section 9 Script). Also the shared helpers setIface, openMake and useOn (Sim and Engine
// call them). Recursion through dialogue/effect chains is bounded by a depth argument, never module state.
const Script = (function () {
  "use strict";

  var QTY_MAX = 2147483647;
  var NOTHING = "That doesn't do anything.";
  var MSG_C = ["game", "warn", "skill", "loot", "fight", "quest", "examine", "npc"];
  var MAX_DEPTH = 6;
  var MAX_HOPS = 32;

  function questDef(qid) {
    return typeof qid === "string" && Util.has(Data.quests, qid) ? Data.quests[qid] : null;
  }

  function questIds() {
    return Object.keys(Data.quests || {});
  }

  function isInt(v) {
    return typeof v === "number" && Math.floor(v) === v;
  }

  // ----------------------------------------------------------------
  // -------------------------- Interfaces --------------------------
  // ----------------------------------------------------------------

  // The single writer of player.iface; emits iface whenever it changes.
  function setIface(state, iface) {
    var p = state.player;
    if (!p.iface && !iface) return;
    p.iface = iface || null;
    Util.emit(state, { type: "iface" });
  }

  // Recipes at this station with an input in the pack or bank (coins, a fee, don't count),
  // or with `id` among the inputs when an item is used on the station. Prints the
  // station's `empty` message when nothing qualifies (not for a use: the caller says "nothing").
  function openMake(state, station, at, id) {
    var p = state.player;
    if (typeof station !== "string" || !Util.has(Data.stations, station)) return false;
    var rids = Object.keys(Data.recipes || {}).filter(function (rid) {
      var r = Data.recipes[rid];
      var ins = Array.isArray(r.in) ? r.in : [];
      if (!Array.isArray(r.at) || r.at.indexOf(station) < 0) return false;
      return ins.some(function (e) {
        return Array.isArray(e) && (id ? e[0] === id : e[0] !== "coins" &&
          (Player.count(p, e[0]) >= 1 || (Sim.bankMakeAllowed(r) && Player.bankCount(p, e[0]) >= 1)));
      });
    });
    if (!rids.length) {
      if (!id) Util.msg(state, Data.stations[station].empty, "game");
      return false;
    }
    setIface(state, { t: "make", station: station, at: typeof at === "string" ? at : null, rids: rids });
    return true;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Quests ----------------------------
  // ----------------------------------------------------------------

  function stage(state, qid) {
    var q = state.player.quests;
    return Util.has(q, qid) ? q[qid] : 0;
  }

  function qp(state) {
    var n = 0;
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) if (stage(state, ids[i]) === 100) n += Data.quests[ids[i]].qp || 0;
    return n;
  }

  function questState(state, qid) {
    var s = stage(state, qid);
    return s >= 100 ? "done" : s > 0 ? "active" : "todo";
  }

  // The quest's listed stages (1..99), ascending.
  function stagesOf(qid) {
    var q = questDef(qid);
    var list = q && Array.isArray(q.stages) ? q.stages : [];
    return list.filter(function (v) { return isInt(v) && v > 0 && v < 100; }).sort(function (a, b) { return a - b; });
  }

  // Moves an unfinished quest to stage n (0 or a listed stage; 100 completes it). Resets qc.
  function setStage(state, qid, n) {
    if (!questDef(qid) || !isInt(n)) return false;
    if (n === 100) return complete(state, qid);
    var cur = stage(state, qid);
    if (cur === 100 || cur === n || (n !== 0 && stagesOf(qid).indexOf(n) < 0)) return false;
    var p = state.player;
    if (n === 0) delete p.quests[qid];
    else p.quests[qid] = n;
    delete p.qc[qid];
    Util.emit(state, { type: "quest", id: qid, stage: n });
    Util.emit(state, { type: "save" });
    return true;
  }

  // Stage 100 and the rewards, exactly once.
  function complete(state, qid) {
    return completeAt(state, qid, 0);
  }

  function completeAt(state, qid, depth) {
    var q = questDef(qid);
    if (!q || stage(state, qid) === 100) return false;
    var p = state.player;
    p.quests[qid] = 100;
    delete p.qc[qid];
    Util.msg(state, "Quest complete: " + q.name + "!", "quest");
    Util.emit(state, { type: "questDone", id: qid });
    var r = q.rewards && typeof q.rewards === "object" ? q.rewards : {};
    (Array.isArray(r.xp) ? r.xp : []).forEach(function (x) { if (Array.isArray(x)) Player.addXp(state, x[0], x[1]); });
    (Array.isArray(r.items) ? r.items : []).forEach(function (x) { if (Array.isArray(x)) Player.give(state, x[0], x[1]); });
    applyAt(state, r.do, depth + 1);
    Util.emit(state, { type: "save" });
    return true;
  }

  // ----------------------------------------------------------------
  // -------------------------- Conditions --------------------------
  // ----------------------------------------------------------------

  // Count of id held in the pack, worn, banked or waiting at the grave.
  function owned(state, id) {
    var p = state.player;
    var n = Player.count(p, id);
    var slots = Rules.EQUIP_SLOTS;
    for (var i = 0; i < slots.length; i++) if (p.eq[slots[i]] === id) n++;
    for (var b = 0; b < p.bank.length; b++) if (p.bank[b].id === id) n += p.bank[b].qty;
    var g = state.grave;
    if (g) for (var k = 0; k < g.items.length; k++) if (g.items[k].id === id) n += g.items[k].qty;
    return n;
  }

  function questCond(state, c) {
    var s = stage(state, c.q);
    var any = false;
    if (typeof c.eq === "number") { any = true; if (s !== c.eq) return false; }
    if (typeof c.gte === "number") { any = true; if (s < c.gte) return false; }
    if (typeof c.lt === "number") { any = true; if (s >= c.lt) return false; }
    return any;
  }

  function anyLevel(p, n) {
    for (var i = 0; i < Rules.SKILLS.length; i++) if (Player.level(p, Rules.SKILLS[i]) >= n) return true;
    return false;
  }

  function allQuests(state) {
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) if (stage(state, ids[i]) !== 100) return false;
    return true;
  }

  function hasAny(p, ids, qty) {
    if (!Array.isArray(ids)) return false;
    for (var i = 0; i < ids.length; i++) if (Player.count(p, ids[i]) >= qty) return true;
    return false;
  }

  // { in: [map, x0, y0, x1, y1] }: the player stands inside the rect (inclusive).
  function inRect(p, r) {
    return Array.isArray(r) && p.map === r[0] && p.x >= r[1] && p.y >= r[2] && p.x <= r[3] && p.y <= r[4];
  }

  // The current season's id (Data.seasons order from tick 0), or null without seasons.
  function seasonId(state) {
    var list = Array.isArray(Data.seasons) ? Data.seasons : [];
    var s = list.length ? list[Rules.seasonIndex(state.tick) % list.length] : null;
    return s ? s.id : null;
  }

  // One Cond object. Unknown shapes are false.
  function test1(state, c) {
    var p = state.player;
    if (!c || typeof c !== "object") return false;
    if (Util.has(c, "q")) return questCond(state, c);
    if (Util.has(c, "has")) return Player.count(p, c.has) >= (typeof c.qty === "number" ? c.qty : 1);
    if (Util.has(c, "hasAny")) return hasAny(p, c.hasAny, typeof c.qty === "number" ? c.qty : 1);
    if (Util.has(c, "owns")) return owned(state, c.owns) > 0;
    if (Util.has(c, "lvl")) return Player.level(p, c.lvl) >= c.gte;
    if (Util.has(c, "anyLvl")) return anyLevel(p, c.anyLvl);
    if (Util.has(c, "kc")) return (Util.has(p.kc, c.kc) ? p.kc[c.kc] : 0) >= c.gte;
    if (Util.has(c, "qc")) return Array.isArray(c.qc) && (Util.has(p.qc, c.qc[0]) ? p.qc[c.qc[0]] : 0) >= c.qc[1];
    if (Util.has(c, "flag")) return Util.has(p.flags, c.flag) && p.flags[c.flag] === 1;
    if (Util.has(c, "qp")) return qp(state) >= c.qp;
    if (Util.has(c, "allQuests")) return allQuests(state);
    if (Util.has(c, "in")) return inRect(p, c.in);
    if (Util.has(c, "season")) return seasonId(state) === c.season;
    if (Util.has(c, "not")) return !test(state, c.not);
    if (Util.has(c, "any")) return Array.isArray(c.any) && c.any.some(function (x) { return test(state, x); });
    return false;
  }

  // A Cond or Cond[] (AND). Missing conditions pass.
  function test(state, cond) {
    if (cond === undefined || cond === null) return true;
    if (!Array.isArray(cond)) return test1(state, cond);
    for (var i = 0; i < cond.length; i++) if (!test1(state, cond[i])) return false;
    return true;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Effects ---------------------------
  // ----------------------------------------------------------------

  function pair(v) {
    return Array.isArray(v) && v.length >= 2 ? v : null;
  }

  function flagOk(f) {
    return typeof f === "string" && Array.isArray(Data.flags) && Data.flags.indexOf(f) >= 0;
  }

  // Q3 reward: every afk.full value still at its default (Sim.afkDefaults, all stop) becomes courier.
  function fullCourier(state) {
    var full = state.player.afk.full;
    var dflt = Sim.afkDefaults().full;
    Object.keys(dflt).forEach(function (k) { if (full[k] === dflt[k]) full[k] = "courier"; });
  }

  function openEffect(state, e) {
    if (e.open === "bank") setIface(state, { t: "bank" });
    else if (e.open === "shop" && typeof e.shop === "string" && Util.has(Data.shops, e.shop)) setIface(state, { t: "shop", id: e.shop });
    else if (e.open === "make" && !openMake(state, e.station, null)) setIface(state, null);
  }

  function takeAny(p, v) {
    var ids = Array.isArray(v[0]) ? v[0] : [];
    for (var i = 0; i < ids.length; i++) {
      if (Player.count(p, ids[i]) >= v[1]) return Player.remove(p, ids[i], v[1]);
    }
    return 0;
  }

  function dialogueUid(state) {
    var f = state.player.iface;
    return f && f.t === "dialogue" ? f.uid : 0;
  }

  // Effect handlers in the order their keys are checked (section 7 Effect).
  var EFFECTS = [
    ["stage", function (state, e) { if (pair(e.stage)) setStage(state, e.stage[0], e.stage[1]); }],
    ["complete", function (state, e, d) { completeAt(state, e.complete, d); }],
    ["give", function (state, e) { if (pair(e.give)) Player.give(state, e.give[0], e.give[1]); }],
    ["take", function (state, e) { if (pair(e.take)) Player.remove(state.player, e.take[0], e.take[1]); }],
    ["takeAny", function (state, e) { if (pair(e.takeAny)) takeAny(state.player, e.takeAny); }],
    ["xp", function (state, e) { if (pair(e.xp)) Player.addXp(state, e.xp[0], e.xp[1]); }],
    ["flag", function (state, e) { if (flagOk(e.flag)) state.player.flags[e.flag] = 1; }],
    ["unflag", function (state, e) { if (flagOk(e.unflag)) delete state.player.flags[e.unflag]; }],
    ["open", openEffect],
    // Like every other teleport, NPCs targeting the player let go first (else an imp left outside the lair
    // door keeps the player "already fighting" when they reach Smoulderjaw), and so does the player: a
    // self-defence fight left behind the wall would end in "You can't get there from here."
    ["teleport", function (state, e) {
      var t = e.teleport;
      if (!Array.isArray(t) || !World.inBounds(t[0], t[1], t[2])) return;
      Combat.breakOff(state);
      Player.teleport(state, t[0], t[1], t[2]);
    }],
    ["msg", function (state, e) {
      if (typeof e.msg === "string") Util.msg(state, e.msg, MSG_C.indexOf(e.c) >= 0 ? e.c : "game");
    }],
    ["dialogue", function (state, e, d) { startAt(state, e.dialogue, dialogueUid(state), d); }],
    ["fullCourier", function (state) { fullCourier(state); }]
  ];

  function applyAt(state, effects, depth) {
    if (!Array.isArray(effects) || depth > MAX_DEPTH) return;
    for (var i = 0; i < effects.length; i++) {
      var e = effects[i];
      if (!e || typeof e !== "object") continue;
      for (var k = 0; k < EFFECTS.length; k++) {
        if (!Util.has(e, EFFECTS[k][0])) continue;
        EFFECTS[k][1](state, e, depth);
        break;
      }
    }
  }

  function apply(state, effects) {
    applyAt(state, effects, 0);
  }

  // A Use list entry for item id (section 7 Use): true = ran, false = matched but its qty/`if` failed
  // (fail printed), null = no entry for this item. The used qty is consumed before `do`.
  function useOn(state, uses, id) {
    var list = Array.isArray(uses) ? uses : [];
    var p = state.player;
    for (var i = 0; i < list.length; i++) {
      var u = list[i];
      if (!u || typeof u !== "object") continue;
      var ids = Array.isArray(u.item) ? u.item : [u.item];
      if (ids.indexOf(id) < 0) continue;
      var qty = Util.int(u.qty, 0, QTY_MAX, 0);
      if (Player.count(p, id) < Math.max(1, qty) || !test(state, u.if)) {
        Util.msg(state, typeof u.fail === "string" ? u.fail : NOTHING, "game");
        return false;
      }
      if (qty > 0) Player.remove(p, id, qty);
      apply(state, u.do);
      return true;
    }
    return null;
  }

  // ----------------------------------------------------------------
  // --------------------------- Dialogue ---------------------------
  // ----------------------------------------------------------------

  function dlg(id) {
    return typeof id === "string" && Util.has(Data.dialogues, id) ? Data.dialogues[id] : null;
  }

  function nodeOf(def, n) {
    return def && def.nodes && typeof n === "string" && Util.has(def.nodes, n) ? def.nodes[n] : null;
  }

  function visibleOpts(state, node) {
    return node.opts.filter(function (o) { return o && typeof o === "object" && test(state, o.if); });
  }

  function branchTo(state, node) {
    for (var i = 0; i < node.branch.length; i++) {
      var b = node.branch[i];
      if (b && typeof b === "object" && test(state, b.if)) return b.go;
    }
    return node.else;
  }

  // The speaking NPC: the one talked to, else the NPC the dialogue is named after.
  function speaker(state, f) {
    var n = isInt(f.uid) && f.uid >= 1 && f.uid <= state.npcs.length ? state.npcs[f.uid - 1] : null;
    if (n && Util.has(Data.npcs, n.id)) return n.id;
    return Util.has(Data.npcs, f.d) ? f.d : null;
  }

  // A say node cut short by an `open` effect still has its line said, in chat.
  function echo(state, node, f) {
    if (typeof node.text !== "string" || !node.text) return;
    var sp = node.say === "npc" || !node.say ? speaker(state, f) : null;
    Util.msg(state, sp ? Data.npcs[sp].name + ": " + node.text : node.text, "npc");
  }

  // Enters node n: branch nodes resolve at once, then the node's `do` runs once. An open or dialogue
  // effect replaces the iface, which ends this dialogue. A missing node ends it.
  function enter(state, d, n, uid, depth) {
    var def = dlg(d);
    var id = n;
    for (var hop = 0; hop < MAX_HOPS; hop++) {
      var node = nodeOf(def, id);
      if (!node) break;
      if (Array.isArray(node.branch)) {
        id = branchTo(state, node);
        continue;
      }
      var f = { t: "dialogue", d: d, n: id, uid: uid };
      setIface(state, f);
      applyAt(state, node.do, depth + 1);
      var now = state.player.iface;
      if (now !== f && now && now.t !== "dialogue" && !Array.isArray(node.opts)) echo(state, node, f);
      return true;
    }
    var cur = state.player.iface;
    if (cur && cur.t === "dialogue") setIface(state, null);
    return false;
  }

  function startAt(state, id, uid, depth) {
    var def = dlg(id);
    if (!def || depth > MAX_DEPTH) return false;
    var u = isInt(uid) && uid >= 1 && uid <= state.npcs.length ? uid : 0;
    return enter(state, id, def.start, u, depth);
  }

  function startDialogue(state, id, uid) {
    return startAt(state, id, uid, 0);
  }

  function current(state) {
    var f = state.player.iface;
    if (!f || f.t !== "dialogue") return null;
    return { f: f, node: nodeOf(dlg(f.d), f.n) };
  }

  function view(state) {
    var c = current(state);
    if (!c || !c.node) return null;
    var node = c.node;
    if (Array.isArray(node.opts)) {
      var opts = visibleOpts(state, node).map(function (o) { return String(o.text); });
      return { who: "none", name: "", npc: null, text: "What will you say?", opts: opts };
    }
    var who = node.say === "player" || node.say === "none" ? node.say : "npc";
    var sp = who === "npc" ? speaker(state, c.f) : null;
    var name = who === "player" ? state.player.name || "You" : sp ? Data.npcs[sp].name : "";
    return { who: who, name: name, npc: sp, text: typeof node.text === "string" ? node.text : "", opts: null };
  }

  // Continue: a say node goes to `next` (null or missing ends it). Option nodes need choose(),
  // unless every option is hidden.
  function next(state) {
    var c = current(state);
    if (!c) return false;
    var node = c.node;
    if (node && Array.isArray(node.opts) && visibleOpts(state, node).length) return false;
    if (!node || Array.isArray(node.opts) || typeof node.next !== "string") {
      setIface(state, null);
      return true;
    }
    enter(state, c.f.d, node.next, c.f.uid, 0);
    return true;
  }

  // i indexes the visible options.
  function choose(state, i) {
    var c = current(state);
    if (!c || !c.node || !Array.isArray(c.node.opts) || !isInt(i)) return false;
    var vis = visibleOpts(state, c.node);
    if (i < 0 || i >= vis.length) return false;
    enter(state, c.f.d, vis[i].go, c.f.uid, 0);
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------- Quest advance ------------------------
  // ----------------------------------------------------------------

  function advanceOf(qid, st) {
    var q = questDef(qid);
    var a = q && q.advance && typeof q.advance === "object" && Util.has(q.advance, String(st)) ? q.advance[st] : null;
    return a && typeof a === "object" ? a : null;
  }

  function nextStage(qid, st) {
    var list = stagesOf(qid);
    for (var i = 0; i < list.length; i++) if (list[i] > st) return list[i];
    return 100;
  }

  // An advance fires: its msg, then the next stage (or completion), then its `do`.
  function fire(state, qid, a) {
    var st = stage(state, qid);
    if (typeof a.msg === "string") Util.msg(state, a.msg, "quest");
    var nx = nextStage(qid, st);
    if (nx === 100) complete(state, qid);
    else setStage(state, qid, nx);
    apply(state, a.do);
  }

  // Active quests whose current advance passes pred(a).
  function eachActive(state, pred) {
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) {
      var st = stage(state, ids[i]);
      if (st <= 0 || st >= 100) continue;
      var a = advanceOf(ids[i], st);
      if (a && pred(ids[i], a)) fire(state, ids[i], a);
    }
  }

  function onKill(state, npcId) {
    var p = state.player;
    eachActive(state, function (qid, a) {
      if (a.kill !== npcId) return false;
      p.qc[qid] = Math.min(QTY_MAX, (Util.has(p.qc, qid) ? p.qc[qid] : 0) + 1);
      return p.qc[qid] >= Util.int(a.n, 1, QTY_MAX, 1);
    });
  }

  function onMade(state, itemId) {
    eachActive(state, function (qid, a) { return Array.isArray(a.made) && a.made.indexOf(itemId) >= 0; });
  }

  function triggered(state, a) {
    var p = state.player;
    if (Array.isArray(a.have)) return Player.count(p, a.have[0]) >= Util.int(a.have[1], 1, QTY_MAX, 1);
    if (Array.isArray(a.flags)) {
      return a.flags.every(function (f) { return Util.has(p.flags, f) && p.flags[f] === 1; });
    }
    return false;
  }

  // End of tick: `have` and `flags` advances (a chain may advance several stages at once).
  function checkTriggers(state) {
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) {
      for (var guard = 0; guard < MAX_HOPS; guard++) {
        var st = stage(state, ids[i]);
        var a = st > 0 && st < 100 ? advanceOf(ids[i], st) : null;
        if (!a || !triggered(state, a)) break;
        fire(state, ids[i], a);
      }
    }
  }

  // ----------------------------------------------------------------
  // ---------------------- Journal and keep list -------------------
  // ----------------------------------------------------------------

  // {qc} is the kill counter: live on the current step, the target on finished ones.
  function journalText(state, qid, s, cur) {
    var q = questDef(qid);
    var text = q.journal && Util.has(q.journal, String(s)) ? String(q.journal[s]) : "";
    if (text.indexOf("{qc}") < 0) return text;
    var a = advanceOf(qid, s);
    var n = a && a.kill ? Util.int(a.n, 1, QTY_MAX, 1) : 0;
    var have = Util.has(state.player.qc, qid) ? state.player.qc[qid] : 0;
    var v = s < cur ? n : n ? Math.min(have, n) : have;
    return text.split("{qc}").join(Util.fmtInt(v));
  }

  function journal(state, qid) {
    var q = questDef(qid);
    if (!q) return [];
    var cur = stage(state, qid);
    if (cur <= 0) return [{ text: String(q.start || ""), done: false }];
    var out = [{ text: String(q.start || ""), done: true }];
    stagesOf(qid).forEach(function (s) {
      if (s > cur || !q.journal || !Util.has(q.journal, String(s))) return;
      out.push({ text: journalText(state, qid, s, cur), done: s < cur });
    });
    return out;
  }

  // Section 10.7: the active quests' keep[stage] entries, summed per item.
  function keep(state) {
    var out = {};
    questIds().forEach(function (qid) {
      var st = stage(state, qid);
      var q = Data.quests[qid];
      if (st <= 0 || st >= 100 || !q.keep || !Util.has(q.keep, String(st)) || !Array.isArray(q.keep[st])) return;
      q.keep[st].forEach(function (e) {
        if (!Array.isArray(e) || typeof e[0] !== "string") return;
        out[e[0]] = (Util.has(out, e[0]) ? out[e[0]] : 0) + Util.int(e[1], 0, QTY_MAX, 0);
      });
    });
    return out;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Hints ----------------------------
  // ----------------------------------------------------------------

  // Nearest [x, y] of list to the player (Chebyshev; ties keep list order), or null.
  function nearestOf(p, list) {
    var best = null;
    var bestD = Infinity;
    for (var i = 0; i < list.length; i++) {
      var d = Util.dist(p.x, p.y, list[i][0], list[i][1]);
      if (d < bestD) {
        bestD = d;
        best = list[i];
      }
    }
    return best;
  }

  // Tiles of entry [kind, id] on map: static nodes or active fishing spots; NPCs alive, else spawns.
  function tilesOn(state, kind, id, map) {
    var out = [];
    if (kind === "obj") {
      var m = World.maps[map];
      if (m && Util.has(m.nodes, id)) out = m.nodes[id].slice();
      Object.keys(World.FISH).forEach(function (g) {
        var grp = World.FISH[g];
        if (grp.map !== map || grp.obj !== id || !Util.has(state.fish, g)) return;
        state.fish[g].at.forEach(function (c) { if (grp.tiles[c]) out.push(grp.tiles[c]); });
      });
      return out;
    }
    state.npcs.forEach(function (n) { if (n.id === id && n.map === map && n.on && n.hp > 0) out.push([n.x, n.y]); });
    if (out.length) return out;
    World.SPAWNS.forEach(function (sp) { if (sp.id === id && sp.map === map) out.push([sp.x, sp.y]); });
    return out;
  }

  // The nearest climb object on the player's map whose destination is on `target`.
  function ladderTo(state, target) {
    var p = state.player;
    var m = World.maps[p.map];
    var list = [];
    Object.keys(m.nodes).forEach(function (oid) {
      var def = Util.has(Data.objects, oid) ? Data.objects[oid] : null;
      var climbs = def && Array.isArray(def.ops) && def.ops.some(function (op) { return op && op.kind === "climb"; });
      if (!climbs) return;
      m.nodes[oid].forEach(function (t) {
        var so = World.staticObj(p.map, t[0], t[1]);
        if (so && so.to && so.to[0] === target) list.push(t);
      });
    });
    return nearestOf(p, list);
  }

  function resolveHint(state, e) {
    var p = state.player;
    if (!Array.isArray(e) || (e[0] !== "obj" && e[0] !== "npc") || typeof e[1] !== "string") return null;
    if (e.length > 2 && !(Array.isArray(e[2]) && test(state, e[2]))) return null;   // a conditional entry
    if (e[0] === "obj") {
      var def = Util.has(Data.objects, e[1]) ? Data.objects[e[1]] : null;
      if (!def || (def.alt && test(state, def.alt.if))) return null;
    } else if (!Util.has(Data.npcs, e[1])) {
      return null;
    }
    var here = nearestOf(p, tilesOn(state, e[0], e[1], p.map));
    if (here) return { map: p.map, x: here[0], y: here[1] };
    var maps = Object.keys(World.maps);
    for (var i = 0; i < maps.length; i++) {
      if (maps[i] === p.map || !tilesOn(state, e[0], e[1], maps[i]).length) continue;
      var l = ladderTo(state, maps[i]);
      if (l) return { map: p.map, x: l[0], y: l[1] };
    }
    return null;
  }

  // Section 9 hint step 1: the first active quest with hint[stage], else the first startable quest's hint[0],
  // else the giver of the todo quest closest to its level reqs (its other reqs met; the giver names the levels).
  function hintList(state) {
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) {
      var q = Data.quests[ids[i]];
      var st = stage(state, ids[i]);
      if (st > 0 && st < 100 && q.hint && Util.has(q.hint, String(st))) return q.hint[st];
    }
    for (var k = 0; k < ids.length; k++) {
      var t = Data.quests[ids[k]];
      if (stage(state, ids[k]) === 0 && test(state, t.reqs) && t.hint && Util.has(t.hint, "0")) return t.hint[0];
    }
    var best = null;
    var gap = Infinity;
    for (var j = 0; j < ids.length; j++) {
      var u = Data.quests[ids[j]];
      var reqs = Array.isArray(u.reqs) ? u.reqs : [];
      if (stage(state, ids[j]) !== 0 || !u.hint || !Util.has(u.hint, "0")) continue;
      if (!test(state, reqs.filter(function (c) { return !(c && c.lvl); }))) continue;
      var g = 0;
      reqs.forEach(function (c) { if (c && c.lvl) g += Math.max(0, c.gte - Player.level(state.player, c.lvl)); });
      if (g < gap) {
        gap = g;
        best = u.hint[0];
      }
    }
    return best;
  }

  // Steps 2-4: the chosen quest's entries in order; the first that resolves wins.
  function hint(state) {
    if (!World.maps[state.player.map]) return null;
    var list = hintList(state);
    if (!Array.isArray(list)) return null;
    for (var i = 0; i < list.length; i++) {
      var t = resolveHint(state, list[i]);
      if (t) return t;
    }
    return null;
  }

  return {
    test: test, apply: apply, stage: stage, setStage: setStage, complete: complete, qp: qp, journal: journal,
    questState: questState, hint: hint, ladderTo: ladderTo, keep: keep, startDialogue: startDialogue, view: view, next: next,
    choose: choose, onKill: onKill, onMade: onMade, checkTriggers: checkTriggers, owned: owned,
    setIface: setIface, openMake: openMake, useOn: useOn
  };
})();
// ==== src/engine/combat.js ====
// ----------------------------------------------------------------
// ---------------- Combat: NPC AI, hits and death ----------------
// ----------------------------------------------------------------
// The NPC phase (specials, aggro, chase, attack, give-up, leash, wander, barks), the player's fight
// action, hits both ways, auto-eat, emergency recall, kills with their drops, combat pets and the player's
// death (DESIGN.md sections 10.6 to 10.8, 10.16 and 14.3). Sim calls in; Combat calls Sim back at runtime
// only.
const Combat = (function () {
  "use strict";

  var QTY_MAX = 2147483647;
  var REACH = "You can't get there from here.";
  var DX = [-1, 1, 0, 0];   // W, E, S, N
  var DY = [0, 0, 1, -1];

  function npcDef(id) { return typeof id === "string" && Util.has(Data.npcs, id) ? Data.npcs[id] : null; }
  function itemDef(id) { return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id] : null; }
  function alive(n) { return !!n && n.on && n.hp > 0; }

  function combatOf(n) {
    var d = n ? npcDef(n.id) : null;
    return d && d.combat ? d.combat : null;
  }

  function npcAt(state, uid) {
    return typeof uid === "number" && uid >= 1 && uid <= state.npcs.length ? state.npcs[uid - 1] : null;
  }

  function adjacent(ax, ay, bx, by) {
    return World.adjacent(ax, ay, bx, by, "nsew");
  }

  function breathOf(c) {
    return c && c.special && c.special.k === "breath" ? c.special : null;
  }

  function inRegion(id, map, x, y) {
    var list = Array.isArray(Data.regions) ? Data.regions : [];
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r && r.id === id) return r.map === map && Array.isArray(r.rect) && Util.inRect(r.rect, x, y);
    }
    return false;
  }

  function speedOf(n, c) {
    var sp = breathOf(c);
    return sp && sp.enrage && n.spec && n.spec.enraged ? sp.enrage.speed : c.speed;
  }

  // ----------------------------------------------------------------
  // --------------------- Targeting and leashing -------------------
  // ----------------------------------------------------------------

  // The NPC targets the player; a breath boss announces itself the first time per spawn.
  function target(state, n) {
    var sp = breathOf(combatOf(n));
    n.target = true;
    n.dest = null;
    n.actAt = state.tick;
    if (!sp || !n.spec || n.spec.used) return;
    n.spec.used = true;
    n.spec.next = state.tick + sp.every;
    Util.msg(state, sp.enterMsg, "fight");
  }

  // Drops the target (give-up, single-way); the player's foe link goes with it.
  function drop(state, n) {
    n.target = false;
    if (n.spec) n.spec.land = 0;
    if (state.player.foe === n.uid) state.player.foe = 0;
  }

  // Heals up to max hp; the heal splat only shows on the player's map.
  function heal(state, n, amt) {
    var c = combatOf(n);
    var add = c ? Math.max(0, Math.min(amt, c.hp - n.hp)) : 0;
    n.hp += add;
    if (add > 0 && n.map === state.player.map) Util.emit(state, { type: "heal", on: n.uid, amt: add });
  }

  // Leash: drop the target, heal to full and walk home; a breath boss also resets its fight.
  function leash(state, n) {
    drop(state, n);
    heal(state, n, QTY_MAX);
    n.dest = [n.sx, n.sy];
    if (n.spec && breathOf(combatOf(n))) {
      n.spec.enraged = false;
      n.spec.used = false;
      n.spec.outAt = 0;
    }
  }

  // Every NPC targeting the player lets go (death, recall, flight).
  function disengage(state) {
    for (var i = 0; i < state.npcs.length; i++) if (state.npcs[i].target) leash(state, state.npcs[i]);
  }

  // Both sides let go before a scripted teleport: the NPCs leash, and the player's fight (a self-defence one
  // too) ends with its resume, foe link and combat timer.
  function breakOff(state) {
    var p = state.player;
    disengage(state);
    if (p.act && p.act.k === "fight") Sim.setAct(state, null);
    p.resume = null;
    p.foe = 0;
    p.combatUntil = 0;
  }

  // Walking home after a leash: no aggro until back inside the wander box.
  function returning(n) {
    return !!n.dest && n.dest[0] === n.sx && n.dest[1] === n.sy && Util.dist(n.x, n.y, n.sx, n.sy) > n.r;
  }

  // ----------------------------------------------------------------
  // -------------------------- NPC movement ------------------------
  // ----------------------------------------------------------------

  // Tiles an NPC may not enter: the player's, another living NPC's, and outside a breath boss's arena.
  function blocker(state, n) {
    var p = state.player;
    var sp = breathOf(combatOf(n));
    return function (x, y) {
      if (p.map === n.map && p.x === x && p.y === y) return true;
      if (sp && !inRegion(sp.arena, n.map, x, y)) return true;
      for (var i = 0; i < state.npcs.length; i++) {
        var o = state.npcs[i];
        if (o !== n && o.map === n.map && o.x === x && o.y === y && alive(o)) return true;
      }
      return false;
    };
  }

  function stepTo(state, n, tx, ty, avoid) {
    var s = World.step(state, n.map, n.x, n.y, tx, ty, avoid);
    if (!s) return false;
    n.face = Util.dirIndex(s[0] - n.x, s[1] - n.y);
    n.x = s[0];
    n.y = s[1];
    return true;
  }

  // The chase goal from (nx,ny): the nearest free cardinal neighbour of the player (ties W, E, S, N), or null.
  function chaseGoal(state, nx, ny, avoid) {
    var p = state.player;
    var best = null;
    var bestK = Infinity;
    for (var d = 0; d < 4; d++) {
      var x = p.x + DX[d];
      var y = p.y + DY[d];
      if (World.blocked(state, p.map, x, y) || avoid(x, y)) continue;
      var dx = x - nx;
      var dy = y - ny;
      var k = Math.max(Math.abs(dx), Math.abs(dy)) * 10000 + dx * dx + dy * dy;
      if (k < bestK) {
        bestK = k;
        best = [x, y];
      }
    }
    return best;
  }

  // Chase: one naive step toward the chase goal. True when it stepped.
  function chase(state, n) {
    var p = state.player;
    if (adjacent(n.x, n.y, p.x, p.y)) return false;
    var avoid = blocker(state, n);
    var best = chaseGoal(state, n.x, n.y, avoid);
    return !!best && stepTo(state, n, best[0], best[1], avoid);
  }

  // The chase above, dry-run with the player standing still: true when it ends next to the player within
  // `steps` steps. A real path is not enough: the chase steps naively and sticks behind a stalagmite.
  function canChase(state, n, steps) {
    var p = state.player;
    var avoid = blocker(state, n);
    var x = n.x;
    var y = n.y;
    for (var i = 0; i <= steps; i++) {
      if (adjacent(x, y, p.x, p.y)) return true;
      var best = chaseGoal(state, x, y, avoid);
      var s = best ? World.step(state, n.map, x, y, best[0], best[1], avoid) : null;
      if (!s) return false;
      x = s[0];
      y = s[1];
    }
    return false;
  }

  // Idle NPCs: with p = 1/8 pick a tile within r of the spawn, then step there; leashed ones walk home.
  function wander(state, n) {
    var f = state.player.iface;
    if (f && f.t === "dialogue" && f.uid === n.uid) return;   // stands still while talking
    var home = returning(n);
    if (!n.dest) {
      if (n.r <= 0 || Util.rand(state) >= 0.125) return;
      n.dest = [n.sx - n.r + Util.randInt(state, 2 * n.r + 1), n.sy - n.r + Util.randInt(state, 2 * n.r + 1)];
    }
    var there = n.x === n.dest[0] && n.y === n.dest[1];
    if (!there && !stepTo(state, n, n.dest[0], n.dest[1], blocker(state, n))) {
      if (!home) n.dest = null;   // a blocked walk home retries next tick
      return;
    }
    if (n.x === n.dest[0] && n.y === n.dest[1]) n.dest = null;
  }

  // At most one overhead line per tick, never in catch-up (section 10.6 Barks).
  function bark(state, n) {
    var d = npcDef(n.id);
    var p = state.player;
    if (!Array.isArray(d.barks) || !d.barks.length || n.target) return false;
    if (Util.dist(n.x, n.y, p.x, p.y) > Rules.BARK_RANGE || state.tick - n.barkAt < Rules.BARK_GAP) return false;
    if (Util.rand(state) >= Rules.BARK_P) return false;
    n.barkAt = state.tick;
    Util.emit(state, { type: "overhead", uid: n.uid, text: String(d.barks[Util.randInt(state, d.barks.length)]) });
    return true;
  }

  // ----------------------------------------------------------------
  // --------------------------- Specials ---------------------------
  // ----------------------------------------------------------------

  function rally(state, n, sp) {
    if (n.spec.used || n.hp > sp.hp) return;
    n.spec.used = true;
    heal(state, n, sp.heal);
    Util.emit(state, { type: "overhead", uid: n.uid, text: sp.msg });
    Util.msg(state, sp.msg, "fight");
  }

  // A pending breath lands on the 3x3 it marked: unblockable, halved by the ward.
  function land(state, n, sp) {
    var p = state.player;
    var s = n.spec;
    if (p.map === n.map && p.hp > 0 && Util.dist(p.x, p.y, s.cx, s.cy) <= 1) {
      var dmg = sp.min + Util.randInt(state, sp.max - sp.min + 1);
      if (p.eq.shield === sp.ward) dmg = Math.floor(dmg / 2);
      hitPlayer(state, n, dmg, true);
    }
    s.land = 0;
    s.next = state.tick + (s.enraged && sp.enrage ? sp.enrage.every : sp.every);
  }

  // Section 14.3: enrage, land, reset after `reset` ticks outside the arena, then the telegraph.
  function breath(state, n, c, sp) {
    var p = state.player;
    var s = n.spec;
    if (!s.enraged && sp.enrage && n.hp <= sp.enrage.hp) {
      s.enraged = true;
      Util.msg(state, sp.enrage.msg, "fight");
    }
    if (s.land > 0 && state.tick >= s.land) land(state, n, sp);
    var inside = inRegion(sp.arena, p.map, p.x, p.y);
    if (inside) s.outAt = 0;
    else if (!s.outAt) s.outAt = state.tick;
    else if (state.tick - s.outAt >= sp.reset && (n.target || s.used || s.enraged || n.hp < c.hp)) leash(state, n);
    if (!n.target || !inside || s.land > 0 || s.next > state.tick || p.hp <= 0) return;
    s.cx = p.x;
    s.cy = p.y;
    s.land = state.tick + sp.warn;
    n.actAt = state.tick;
    Util.emit(state, { type: "breath", uid: n.uid, cx: s.cx, cy: s.cy, land: s.land });
  }

  function special(state, n, c) {
    var sp = c.special;
    if (!sp || !n.spec) return;
    if (sp.k === "rally") rally(state, n, sp);
    else if (sp.k === "breath") breath(state, n, c, sp);
  }

  // ----------------------------------------------------------------
  // --------------------------- NPC phase --------------------------
  // ----------------------------------------------------------------

  // Section 10.6 Aggro, with single-way: the player's foe slot must be free, this NPC's, or cold.
  function aggro(state, n, c) {
    var p = state.player;
    var sp = breathOf(c);
    if (!(c.aggro > 0) || p.hp <= 0 || returning(n) || Util.dist(n.x, n.y, p.x, p.y) > c.aggro) return;
    // Bosses never wake during catch-up: a boss foe freezes it, so Skarg stepping in between two camp goblins
    // would throw away the rest of the time away.
    if (c.boss && state.away) return;
    if (!c.always && Player.combatLevel(p) > 2 * c.lvl) return;
    if (p.foe !== 0 && p.foe !== n.uid && p.combatUntil > state.tick) return;
    if (sp && !inRegion(sp.arena, p.map, p.x, p.y)) return;
    // No aggro it can't follow up: the chase itself must reach the player. Without it, an imp behind the lair
    // wall (or a spider behind a stalagmite) gives up and re-aggroes forever, keeping the player "already
    // fighting" (single-way) with nothing ever landing.
    if (!canChase(state, n, c.aggro + 2)) return;
    target(state, n);
    p.foe = n.uid;
    p.combatUntil = state.tick + Rules.COMBAT_TICKS;
    // A breath boss already announced itself in target().
    if (!sp) Util.msg(state, npcDef(n.id).name + " attacks you!", "fight");
  }

  // The player's defence roll; Last stand raises it while under 25% health.
  function defenceRoll(p) {
    var def = Rules.playerDefenceRoll(Player.level(p, "defence"), p.style, Player.bonuses(p).def);
    var v = p.hp * 4 < Player.maxHp(p) ? Player.perkVal(p, "hitpoints", "last") : 0;
    return v > 0 ? def * (1 + v) : def;
  }

  // A melee swing when adjacent and ready; a foreign foe makes it give up instead. Guard may block a
  // landed hit outright (a breath is never blockable). A summoned pet's Dread and Guard apply here.
  function attack(state, n, c) {
    var p = state.player;
    if (n.atkTimer > 0 || (n.spec && n.spec.land > 0) || !adjacent(n.x, n.y, p.x, p.y)) return false;
    if (p.foe !== n.uid && p.combatUntil > state.tick) {
      drop(state, n);
      return false;
    }
    var perk = petPerk(p);
    var acc = Rules.hitChance(Rules.npcAttackRoll(c), defenceRoll(p));
    var hit = Util.rand(state) < (perk === "dread" ? acc * 0.9 : acc);
    n.face = Util.dirIndex(p.x - n.x, p.y - n.y);
    n.anim = "attack";
    n.animAt = state.tick;
    n.atkTimer = speedOf(n, c);
    var dmg = hit ? 1 + Util.randInt(state, c.maxHit) : 0;
    if (dmg > 1 && perk === "guard") dmg--;
    if (dmg > 0 && Player.perkRoll(state, "defence", "block")) {
      dmg = 0;
      Player.perkMsg(state, "defence", "block", null, "fight");
    }
    hitPlayer(state, n, dmg, false);
    return true;
  }

  function fightStep(state, n, c) {
    var p = state.player;
    special(state, n, c);
    if (!n.target) aggro(state, n, c);
    if (!n.target || p.hp <= 0) return;
    var acted = chase(state, n);
    if (attack(state, n, c)) acted = true;
    if (!n.target) return;
    if (acted) n.actAt = state.tick;
    if (state.tick - n.actAt >= Rules.GIVE_UP_TICKS) {
      drop(state, n);
      Util.msg(state, npcDef(n.id).name + " loses interest.", "fight");
    } else if (Util.dist(n.x, n.y, n.sx, n.sy) > Rules.LEASH) {
      leash(state, n);
      Util.msg(state, npcDef(n.id).name + " retreats.", "fight");
    }
  }

  // Step 3: living NPCs on the player's map in uid order. NPCs left behind on another map let go.
  function npcPhase(state) {
    var p = state.player;
    var barked = !!state.away;
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (!alive(n)) continue;
      if (n.map !== p.map) {
        if (n.target) leash(state, n);
        continue;
      }
      if (n.atkTimer > 0) n.atkTimer--;
      var c = combatOf(n);
      if (c) fightStep(state, n, c);
      if (!n.target && p.hp > 0) wander(state, n);
      if (!barked) barked = bark(state, n);
    }
    var f = npcAt(state, p.foe);
    if (p.foe && !(alive(f) && f.map === p.map)) p.foe = 0;
  }

  // ----------------------------------------------------------------
  // ---------------------------- AFK safety ------------------------
  // ----------------------------------------------------------------

  // Section 10.7: away, an auto fight, a gather or a make, or a pending resume.
  function isAfk(state) {
    var p = state.player;
    var a = p.act;
    return !!state.away || !!p.resume ||
      (!!a && (a.k === "gather" || a.k === "make" || (a.k === "fight" && a.auto === true)));
  }

  function eatLevel(state) {
    var e = state.player.afk.eat;
    return state.away ? Math.max(e, 50) : e;
  }

  function foeNpc(state) {
    var p = state.player;
    var n = npcAt(state, p.foe);
    return alive(n) && n.map === p.map ? n : null;
  }

  // The foe's max hit plus a breath pending on the player's tiles (halved by the ward).
  function threat(state) {
    var p = state.player;
    var n = foeNpc(state);
    var c = combatOf(n);
    if (!c) return 0;
    var t = c.maxHit;
    var sp = breathOf(c);
    if (sp && n.spec && n.spec.land > 0 && Util.dist(p.x, p.y, n.spec.cx, n.spec.cy) <= 1) {
      t += p.eq.shield === sp.ward ? Math.floor(sp.max / 2) : sp.max;
    }
    return t;
  }

  // What eating the slot heals, food perks included.
  function healOf(p, slot) {
    return Player.healOf(p, slot);
  }

  // Below eat% the lowest-heal food; else, at or below the threat, the cheapest food that covers it.
  function autoEat(state) {
    var p = state.player;
    var eat = eatLevel(state);
    var max = Player.maxHp(p);
    if (!(eat > 0) || p.hp <= 0 || p.hp >= max || p.eatTimer > 0) return;
    var foods = Player.foods(p);
    if (!foods.length) return;
    if (p.hp <= Math.ceil(max * eat / 100)) {
      Player.eat(state, foods[0]);
      return;
    }
    var th = threat(state);
    if (p.hp > th) return;
    var pick = foods[0];
    for (var i = 0; i < foods.length; i++) {
      if (p.hp + healOf(p, foods[i]) > th) {
        Player.eat(state, foods[i]);
        return;
      }
      if (healOf(p, foods[i]) > healOf(p, pick)) pick = foods[i];
    }
    Player.eat(state, pick);
  }

  // Emergency recall: an instant trip to the shrine that ends everything.
  function flee(state) {
    var p = state.player;
    var r = Sim.respawnPos();
    disengage(state);
    p.foe = 0;
    p.combatUntil = 0;
    p.hitAt = -1000;   // safe at the shrine: Hearth recall is not "under attack"
    Sim.setIface(state, null);
    Player.teleport(state, r[0], r[1], r[2]);
    Util.msg(state, "You flee to the Hearth Shrine.", "warn");
    Sim.stop(state, "retreated at low HP");
    Util.emit(state, { type: "recall" });
  }

  // While AFK and in combat, outside freeze regions: low hp with no food (or eating off) flees.
  function emergency(state) {
    var p = state.player;
    if (p.hp <= 0 || p.combatUntil <= state.tick || !isAfk(state) || Sim.inFreeze(state)) return false;
    var max = Player.maxHp(p);
    if (p.hp > Math.max(Math.ceil(0.2 * max), threat(state))) return false;
    if (Player.foods(p).length && eatLevel(state) > 0) return false;
    flee(state);
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------ Hits on the player --------------------
  // ----------------------------------------------------------------

  // Section 10.6 Auto-retaliate: an idle, gathering, making, casting or waiting player fights back.
  function retaliate(state, n) {
    var p = state.player;
    var a = p.act;
    if (!p.afk.ret || !alive(n)) return;
    if (a && a.k !== "gather" && a.k !== "make" && !(a.k === "fight" && a.uid === 0)) return;
    if (a) p.resume = a;
    Sim.setAct(state, { k: "fight", uid: n.uid, npc: n.id, ax: n.x, ay: n.y, auto: false });
    p.path = [];
  }

  // dmg 0 is a miss. A lethal hit while AFK (outside freeze regions) leaves 1 hp and flees instead.
  function hitPlayer(state, npc, dmg, unblockable) {
    var p = state.player;
    if (p.hp <= 0) return;
    var d = Math.max(0, Math.min(Math.floor(dmg) || 0, p.hp));
    var saved = d > 0 && d >= p.hp && isAfk(state) && !Sim.inFreeze(state);
    var applied = saved ? p.hp - 1 : d;
    p.hp -= applied;
    Util.emit(state, { type: "hit", on: 0, dmg: applied, miss: !(d > 0) });
    p.foe = npc.uid;
    p.combatUntil = state.tick + Rules.COMBAT_TICKS;
    p.hitAt = state.tick;
    if (!unblockable) {
      p.anim = "block";
      p.animAt = state.tick;
    }
    if (p.act && p.act.k === "cast") Sim.setAct(state, null);
    if (saved) flee(state);
    else if (p.hp > 0) retaliate(state, npc);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Drops -----------------------------
  // ----------------------------------------------------------------

  function qtyRoll(state, lo, hi) {
    var a = Util.int(lo, 1, QTY_MAX, 1);
    var b = Util.int(hi, a, QTY_MAX, a);
    return b > a ? a + Util.randInt(state, b - a + 1) : a;
  }

  function addSlot(out, id, qty) {
    for (var i = 0; i < out.length; i++) {
      if (out[i].id !== id) continue;
      out[i].qty = Math.min(QTY_MAX, out[i].qty + qty);
      return;
    }
    out.push({ id: id, qty: qty });
  }

  // One roll on Data.gemTable, or null.
  function gemRoll(state) {
    var rows = Array.isArray(Data.gemTable) ? Data.gemTable : [];
    var total = 0;
    for (var i = 0; i < rows.length; i++) total += rows[i][0];
    var row = Util.weighted(state, rows, total, 0);
    return row && itemDef(row[1]) ? row[1] : null;
  }

  // A drop Spoils may double: not a quest item, not untradeable.
  function plain(id) {
    var it = itemDef(id);
    return !!it && it.cat !== "quest" && !it.untradeable;
  }

  // always (with conds), one main-table row (/128), the gem roll, then each unique's own 1/N roll.
  // common = the unconditional always rows and the main row (what Spoils doubles); never gems or uniques.
  function rollDrops(state, npcId) {
    var d = npcDef(npcId);
    var key = d && d.combat ? d.combat.drops : null;
    var t = typeof key === "string" && Util.has(Data.drops, key) ? Data.drops[key] : null;
    var out = [];
    var rare = [];
    var common = [];
    if (!t) return { slots: out, rare: rare, common: common };
    (Array.isArray(t.always) ? t.always : []).forEach(function (r) {
      if (!Array.isArray(r) || !itemDef(r[0]) || !Script.test(state, r[3])) return;
      var q = qtyRoll(state, r[1], r[2]);
      addSlot(out, r[0], q);
      if (!r[3] && plain(r[0])) common.push({ id: r[0], qty: q });
    });
    if (Array.isArray(t.main) && t.main.length) {
      var row = Util.weighted(state, t.main, 128, 0);
      if (row && itemDef(row[1])) {
        var mq = qtyRoll(state, row[2], row[3]);
        addSlot(out, row[1], mq);
        if (plain(row[1])) common.push({ id: row[1], qty: mq });
      }
    }
    if (t.gem > 0 && Util.randInt(state, t.gem) === 0) {
      var g = gemRoll(state);
      if (g) addSlot(out, g, 1);
    }
    (Array.isArray(t.unique) ? t.unique : []).forEach(function (u) {
      if (!Array.isArray(u) || !itemDef(u[0]) || !(u[1] > 0) || Util.randInt(state, u[1]) !== 0) return;
      addSlot(out, u[0], 1);
      rare.push(u[0]);
    });
    return { slots: out, rare: rare, common: common };
  }

  // Spoils: a non-boss kill's common rows come twice. True when it fired.
  function spoils(state, c, roll) {
    if (c.boss || !roll.common.length || !Player.perkRoll(state, "attack", "spoils")) return false;
    roll.common.forEach(function (e) { addSlot(roll.slots, e.id, e.qty); });
    return true;
  }

  function dropFor(state, npcId) {
    return rollDrops(state, npcId).slots;
  }

  // Into the pack as far as it fits (a loot event each); returns what is left over.
  function intoPack(state, slots) {
    var rest = [];
    for (var i = 0; i < slots.length; i++) {
      var got = Player.add(state.player, slots[i].id, slots[i].qty);
      if (got > 0) Util.emit(state, { type: "loot", id: slots[i].id, qty: got });
      if (got < slots[i].qty) rest.push({ id: slots[i].id, qty: slots[i].qty - got });
    }
    return rest;
  }

  // Auto-loot (section 1 #17): the pack first, a courier run when that mode is on, the rest on the NPC's tile.
  function loot(state, n, slots) {
    var p = state.player;
    var rest = slots;
    if (p.afk.loot) {
      rest = intoPack(state, slots);
      if (rest.length && p.afk.full.combat === "courier" && Script.owned(state, "courier_satchel") > 0 &&
        Sim.courier(state) > 0) {
        p.atkTimer = Math.max(p.atkTimer, Rules.COURIER_TICKS);
        rest = intoPack(state, rest);
      }
    }
    for (var i = 0; i < rest.length; i++) Player.toGround(state, n.map, n.x, n.y, rest[i].id, rest[i].qty);
  }

  // ----------------------------------------------------------------
  // ----------------------------- Kills ----------------------------
  // ----------------------------------------------------------------

  function killNpc(state, n) {
    var p = state.player;
    var d = npcDef(n.id);
    var c = d.combat;
    n.hp = 0;
    n.target = false;
    n.dest = null;
    if (n.spec) n.spec.land = 0;
    Util.emit(state, { type: "death", on: n.uid });
    var roll = rollDrops(state, n.id);
    var twice = spoils(state, c, roll);
    loot(state, n, roll.slots);
    Script.onKill(state, n.id);
    n.deadUntil = state.tick + Util.int(c.respawn, 1, 100000, 1);
    var kc = Math.min(QTY_MAX, (Util.has(p.kc, n.id) ? p.kc[n.id] : 0) + 1);
    p.kc[n.id] = kc;
    petRoll(state, n.id, kc);
    if (p.foe === n.uid) p.foe = 0;
    Util.msg(state, d.name + " defeated.", "fight");
    if (twice) Player.perkMsg(state, "attack", "spoils", null, "loot");
    if (c.boss) {
      Util.msg(state, d.name + " kills: " + Util.fmtInt(kc) + ".", "game");
      Util.emit(state, { type: "save" });
    }
    roll.rare.forEach(function (id) {
      Util.msg(state, "Rare drop: " + itemDef(id).name + "!", "loot");
      Util.emit(state, { type: "rare", id: id });
    });
    if (roll.rare.length) Util.emit(state, { type: "save" });
  }

  // ----------------------------------------------------------------
  // ------------------------ The player's fight --------------------
  // ----------------------------------------------------------------

  // Single-way: another foe is alive, still targeting the player and in combat.
  function busyWith(state, n) {
    var p = state.player;
    var f = npcAt(state, p.foe);
    return !!n && p.foe !== n.uid && p.combatUntil > state.tick && alive(f) && f.target && f.map === p.map;
  }

  // Finisher on a foe under 25% health: +floor(dmg x v), at least +1 from rank 3; never past its hp.
  function finisher(p, n, c, dmg) {
    var v = dmg > 0 && n.hp * 4 < c.hp ? Player.perkVal(p, "strength", "finish") : 0;
    if (!(v > 0)) return dmg;
    var extra = Math.max(Math.floor(dmg * v), Player.perkRanks(p, "strength", "finish") >= 3 ? 1 : 0);
    return Math.min(n.hp, dmg + extra);
  }

  // Accuracy roll (Precision raises it), damage (Finisher), XP (each skill's XP perk); the NPC targets
  // the player. Returns true on a kill.
  function playerSwing(state) {
    var p = state.player;
    var n = npcAt(state, p.act && p.act.k === "fight" ? p.act.uid : 0);
    var c = combatOf(n);
    if (!alive(n) || !c) return false;
    var b = Player.bonuses(p);
    var acc = Rules.hitChance(Rules.playerAttackRoll(Player.level(p, "attack"), p.style, b.att), Rules.npcDefenceRoll(c));
    var prec = Player.perkVal(p, "attack", "acc");
    if (prec > 0) acc = Math.min(1, acc * (1 + prec));
    var max = Math.max(1, Rules.playerMaxHit(Player.level(p, "strength"), p.style, b.str));
    var dmg = finisher(p, n, c, Util.rand(state) < acc ? Math.min(n.hp, 1 + Util.randInt(state, max)) : 0);
    n.hp -= dmg;
    Util.emit(state, { type: "hit", on: n.uid, dmg: dmg, miss: dmg === 0 });
    var xp = Rules.combatXp10(dmg, p.style);
    Object.keys(xp).forEach(function (k) {
      var v = Player.perkVal(p, k, "xp");
      Player.addXp10(state, k, v > 0 ? Math.round(xp[k] * (1 + v)) : xp[k], true);
    });
    p.atkTimer = b.speed;
    p.face = Util.dirIndex(n.x - p.x, n.y - p.y);
    p.anim = "attack";
    p.animAt = state.tick;
    p.foe = n.uid;
    p.combatUntil = state.tick + Rules.COMBAT_TICKS;
    if (n.hp <= 0) {
      killNpc(state, n);
      return true;
    }
    if (!n.target) target(state, n);
    return false;
  }

  function spawnNear(a, map) {
    for (var i = 0; i < World.SPAWNS.length; i++) {
      var sp = World.SPAWNS[i];
      if (sp.id === a.npc && sp.map === map && Util.dist(sp.x, sp.y, a.ax, a.ay) <= Rules.FIGHT_RANGE) return true;
    }
    return false;
  }

  // Target acquisition for uid 0: the nearest living, non-boss NPC of the act's id within 8 of the anchor,
  // by path. None: wait when a spawn of that id is near the anchor, else stop.
  function acquire(state, a) {
    var p = state.player;
    var cands = [];
    var list = [];
    for (var i = 0; i < state.npcs.length; i++) {
      var m = state.npcs[i];
      var c = combatOf(m);
      if (m.id !== a.npc || m.map !== p.map || !alive(m) || !c || c.boss) continue;
      if (Util.dist(m.x, m.y, a.ax, a.ay) > Rules.FIGHT_RANGE) continue;
      cands.push([m.x, m.y, "nsew"]);
      list.push(m);
    }
    // The BFS window covers every tile next to a candidate, with room for detours.
    var radius = Util.dist(p.x, p.y, a.ax, a.ay) + Rules.FIGHT_RANGE + 6;
    var r = cands.length ? World.findPathAny(state, p.map, p.x, p.y, cands, radius) : null;
    a.uid = r ? list[r.i].uid : 0;
    if (r) {
      p.path = r.path;
      return list[r.i];
    }
    if (!spawnNear(a, p.map)) Sim.stop(state, "no " + String(npcDef(a.npc).name).toLowerCase() + " nearby");
    return null;
  }

  // Back to the interrupted activity when it is close enough, else idle.
  function endFight(state) {
    var p = state.player;
    var r = p.resume;
    p.resume = null;
    Sim.setAct(state, r && Util.dist(p.x, p.y, r.ax, r.ay) <= Rules.RESUME_RANGE ? r : null);
    p.path = [];
  }

  // The fight action, each tick after movement: (re)acquire, approach, swing when the timer is ready.
  function runFight(state) {
    var p = state.player;
    var a = p.act;
    var n = npcAt(state, a.uid);
    if (a.uid > 0 && !(alive(n) && n.map === p.map && n.id === a.npc)) {
      if (!a.auto) {
        endFight(state);
        return;
      }
      a.uid = 0;
    }
    if (a.uid === 0 && !(n = acquire(state, a))) return;
    if (!adjacent(p.x, p.y, n.x, n.y)) {
      if (p.path.length) return;
      var path = World.findPath(state, p.map, p.x, p.y, { x: n.x, y: n.y, mode: "adj" });
      if (path) p.path = path;
      else if (a.auto) a.uid = 0;
      else {
        Util.msg(state, REACH, "warn");
        endFight(state);
      }
      return;
    }
    p.face = Util.dirIndex(n.x - p.x, n.y - p.y);
    if (p.atkTimer > 0 || !playerSwing(state)) return;
    afterKill(state);
  }

  // After the player or the pet kills the fight's foe: the next foe of an auto fight, else end the fight.
  function afterKill(state) {
    var p = state.player;
    var a = p.act;
    if (!a || a.k !== "fight") return;
    if (!p.resume && a.auto && p.afk.cont) acquire(state, a);
    else endFight(state);
  }

  // Arrival of an Attack: the fight starts (auto unless a boss) and swings at once when ready.
  function startFight(state, n) {
    if (busyWith(state, n)) {
      Util.msg(state, "You're already fighting.", "warn");
      return false;
    }
    var c = combatOf(n);
    Sim.setAct(state, { k: "fight", uid: n.uid, npc: n.id, ax: n.x, ay: n.y, auto: !c.boss });
    runFight(state);
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------------ Pets ----------------------------
  // ----------------------------------------------------------------

  function petDef(id) { return typeof id === "string" && Data.pets && Util.has(Data.pets, id) ? Data.pets[id] : null; }

  // The summoned pet's definition, or null.
  function summoned(p) {
    var d = petDef(p.pet);
    return d && p.pets && Util.has(p.pets, p.pet) ? d : null;
  }

  function petPerk(p) {
    var d = summoned(p);
    return d ? d.perk : "";
  }

  // The pet's form at a growth stage (0 young, 1 adult, 2 mythic): { name, draw }.
  function petForm(d, stage) {
    var g = stage > 0 && Array.isArray(d.grows) ? d.grows[stage - 1] : null;
    return g && typeof g.name === "string" ? g : { name: d.name, draw: d.draw };
  }

  function petName(p, id) {
    var d = petDef(id);
    return d ? petForm(d, Rules.petStage(Rules.petLevel(Util.has(p.pets, id) ? p.pets[id] : 0))).name : "";
  }

  // The pet's records, made on first use: total damage, killing blows, best hit, the boss kill count it
  // was found on (0 = before records), and ticks summoned.
  function petLog(p, id) {
    if (!p.petLog || typeof p.petLog !== "object") p.petLog = {};
    if (!Util.has(p.petLog, id)) p.petLog[id] = { dmg: 0, kills: 0, best: 0, kc: 0, out: 0 };
    return p.petLog[id];
  }

  // [0, 1) from the seed, a count and an id without advancing state.rng, so a kill's pet roll leaves
  // every other roll's sequence alone (murmur3 finaliser).
  function hashRoll(seed, n, id) {
    var h = ((seed >>> 0) ^ Math.imul(n | 0, 0x9e3779b1)) >>> 0;
    for (var i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 0x01000193);
    h ^= h >>> 16;
    h = Math.imul(h, 0x85ebca6b);
    h ^= h >>> 13;
    h = Math.imul(h, 0xc2b2ae35);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  }

  // Section 10.16: each pet the kill's monster gives, not owned yet, at 1 in rate. The first pet found
  // while none is summoned comes along at once.
  function petRoll(state, npcId, kc) {
    var p = state.player;
    Object.keys(Data.pets || {}).forEach(function (id) {
      var d = Data.pets[id];
      if (!d || d.from !== npcId || Util.has(p.pets, id) || !(hashRoll(state.rng, kc, id) * d.rate < 1)) return;
      p.pets[id] = 0;
      petLog(p, id).kc = kc;
      if (!summoned(p)) {
        p.pet = id;
        p.petTimer = 0;
      }
      Util.msg(state, "Pet: " + d.name + "! It has taken a shine to you.", "loot");
      Util.emit(state, { type: "pet", id: id });
      Util.emit(state, { type: "save" });
    });
  }

  // The pet's foe: the player's fight act on a living foe the player can swing at (beside them, nsew).
  function petFoe(state) {
    var p = state.player;
    var a = p.act;
    var n = a && a.k === "fight" ? npcAt(state, a.uid) : null;
    return alive(n) && n.map === p.map && combatOf(n) && adjacent(p.x, p.y, n.x, n.y) ? n : null;
  }

  // 1 pet XP per damage. A level gained says so; crossing a growth stage says what it grew into.
  function petXp(state, d, dmg) {
    var p = state.player;
    var before = Rules.petLevel(p.pets[p.pet]);
    p.pets[p.pet] = Math.min(Rules.PET_XP_MAX, p.pets[p.pet] + dmg);
    var after = Rules.petLevel(p.pets[p.pet]);
    if (after <= before) return;
    var was = petForm(d, Rules.petStage(before)).name, now = petForm(d, Rules.petStage(after)).name;
    if (Rules.petStage(after) > Rules.petStage(before)) {
      Util.msg(state, "Your " + String(was).toLowerCase() + " grew into " + (/^[aeiou]/i.test(now) ? "an " : "a ") + now + "!",
        "game");
      Util.emit(state, { type: "petGrow", id: p.pet, stage: Rules.petStage(after) });
      Util.emit(state, { type: "save" });
    }
    Util.msg(state, "Your " + String(now).toLowerCase() + " is now level " + after + ".", "game");
  }

  // One strike with the pet's own stats (never the player's): its attack roll against the foe's defence
  // (Keen x1.25) for 1..petMaxHit, full damage on bosses too. No player XP; the pet earns 1 XP per damage.
  // Mend heals 1 and Gore delays the foe on a landed hit. True on a kill.
  function petSwing(state, d, n) {
    var p = state.player;
    var c = combatOf(n);
    var lvl = Rules.petLevel(p.pets[p.pet]);
    var acc = Rules.hitChance(Rules.petAttackRoll(d.att, lvl), Rules.npcDefenceRoll(c));
    if (d.perk === "keen") acc = Math.min(1, acc * 1.25);
    var max = Rules.petMaxHit(d.maxHit, lvl, d.perk);
    var dmg = Util.rand(state) < acc ? Math.min(n.hp, 1 + Util.randInt(state, max)) : 0;
    n.hp -= dmg;
    Util.emit(state, { type: "hit", on: n.uid, dmg: dmg, miss: dmg === 0, pet: true });
    p.petAt = state.tick;
    p.foe = n.uid;
    p.combatUntil = state.tick + Rules.COMBAT_TICKS;
    var log = petLog(p, p.pet);
    if (dmg > 0) {
      log.dmg = Math.min(QTY_MAX, log.dmg + dmg);
      log.best = Math.max(log.best, dmg);
      petXp(state, d, dmg);
      if (d.perk === "mend" && p.hp < Player.maxHp(p)) p.hp++;
      if (d.perk === "gore" && Util.rand(state) < 0.25) n.atkTimer++;
    }
    if (n.hp <= 0) {
      log.kills = Math.min(QTY_MAX, log.kills + 1);
      killNpc(state, n);
      return true;
    }
    if (!n.target) target(state, n);
    return false;
  }

  // Each tick after the player's action: the timer runs down; when ready, the summoned pet strikes the
  // player's foe (Flurry: 1 in 5 turns strike twice) and waits PET_SPEED ticks (Quick: PET_QUICK).
  function petPhase(state) {
    var p = state.player;
    if (p.petTimer > 0) p.petTimer--;
    var d = summoned(p);
    if (!d || p.hp <= 0) return;
    var log = petLog(p, p.pet);
    log.out = Math.min(QTY_MAX, log.out + 1);
    if (p.petTimer > 0) return;
    var n = petFoe(state);
    if (!n) return;
    p.petTimer = d.perk === "quick" ? Rules.PET_QUICK : Rules.PET_SPEED;
    var strikes = d.perk === "flurry" && Util.rand(state) < 0.2 ? 2 : 1;
    for (var i = 0; i < strikes; i++) {
      if (petSwing(state, d, n)) {
        afterKill(state);
        return;
      }
    }
  }

  // ----------------------------------------------------------------
  // ------------------------- Player death -------------------------
  // ----------------------------------------------------------------

  // The new grave takes the lost piles, then the old grave's items merged by id and noted-ness (<= 128 piles).
  function makeGrave(state, at, lose, life) {
    var items = lose.map(function (s) { return s.note ? { id: s.id, qty: s.qty, note: true } : { id: s.id, qty: s.qty }; });
    var old = state.grave ? state.grave.items : [];
    for (var i = 0; i < old.length; i++) {
      var id = old[i].id, note = !!old[i].note;
      var hit = items.filter(function (s) { return s.id === id && !!s.note === note; })[0];
      if (hit) hit.qty = Math.min(QTY_MAX, hit.qty + old[i].qty);
      else if (items.length < 128) items.push(note ? { id: id, qty: old[i].qty, note: true } : { id: id, qty: old[i].qty });
    }
    state.grave = { map: at[0], x: at[1], y: at[2], until: state.tick + life, items: items };
  }

  function placeName(map, x, y) {
    var r = World.regionAt(map, x, y);
    return r ? r.name : World.maps[map] ? World.maps[map].name : "";
  }

  // Section 10.8: split, grave (at region.graveAt when set), respawn at the shrine with full hp.
  function playerDeath(state) {
    var p = state.player;
    var reg = World.regionAt(p.map, p.x, p.y);
    var danger = !!(reg && reg.danger);
    var ga = reg && Array.isArray(reg.graveAt) ? reg.graveAt : null;
    var at = ga && World.inBounds(ga[0], ga[1], ga[2]) ? [ga[0], ga[1], ga[2]] : [p.map, p.x, p.y];
    var life = danger ? Rules.GRAVE_DANGER : Rules.GRAVE_SAFE;
    var split = Player.deathSplit(p, danger);
    var text = "You have fallen. You kept everything.";
    if (split.lose.length) {
      makeGrave(state, at, split.lose, life);
      text = "You have fallen. Your belongings wait at a gravestone in " + placeName(at[0], at[1], at[2]) + " for " +
        Util.fmtDur(life) + ".";
    }
    for (var i = 0; i < p.inv.length; i++) p.inv[i] = i < split.keepInv.length ? split.keepInv[i] : null;
    Rules.EQUIP_SLOTS.forEach(function (k) { p.eq[k] = Util.has(split.keepEq, k) ? split.keepEq[k] : null; });
    disengage(state);
    Sim.setAct(state, null);
    Sim.setIface(state, null);
    p.resume = null;
    p.stop = null;
    p.foe = 0;
    p.combatUntil = 0;
    p.hitAt = -1000;
    p.atkTimer = 0;
    p.eatTimer = 0;
    p.petTimer = 0;
    p.anim = null;
    var r = Sim.respawnPos();
    Player.teleport(state, r[0], r[1], r[2]);
    p.hp = Player.maxHp(p);
    Util.emit(state, { type: "death", on: 0, text: text });
    Util.emit(state, { type: "save" });
  }

  return {
    npcPhase: npcPhase, playerSwing: playerSwing, hitPlayer: hitPlayer, autoEat: autoEat, emergency: emergency,
    killNpc: killNpc, playerDeath: playerDeath, dropFor: dropFor, gemRoll: gemRoll, runFight: runFight,
    startFight: startFight, busyWith: busyWith, disengage: disengage, breakOff: breakOff, isAfk: isAfk, threat: threat,
    defenceRoll: defenceRoll, petPhase: petPhase, petRoll: petRoll, summoned: summoned, petForm: petForm, petName: petName
  };
})();
// ==== src/engine/sim.js ====
// ----------------------------------------------------------------
// ---------------------- Sim: state and tick ---------------------
// ----------------------------------------------------------------
// State construction, objects and fishing spots, world commands, gathering, full packs, making and the
// tick itself (DESIGN.md sections 9 Sim and 10.1 to 10.5), plus status texts and catch-up Summaries.
// Conventions: an NPC is present iff on && hp > 0; a blocked respawn retries next tick (deadUntil + 1);
// non-combat NPCs carry hp 1. A gather act on a fishing spot has base = the spot's obj id. Stop reasons
// print their message as "warn" first, then emit the stop event.
const Sim = (function () {
  "use strict";

  var QTY_MAX = 2147483647;
  var REACH = "You can't get there from here.";
  var FULL = "Your pack is full.";
  var NOTHING = "That doesn't do anything.";
  var CONT_ANIMS = { chop: 1, mine: 1, fish: 1, smith: 1, smelt: 1, cook: 1, craft: 1, fire: 1 };

  function npcDef(id) { return Util.has(Data.npcs, id) ? Data.npcs[id] : null; }
  function itemDef(id) { return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id] : null; }

  // ----------------------------------------------------------------
  // ---------------------- State construction ----------------------
  // ----------------------------------------------------------------

  // A full pack stops every activity until the player picks Drop or Courier (the UI offers Drop once).
  function afkDefaults() {
    return { cont: true, ret: true, loot: true, eat: 50,
      full: { woodcutting: "stop", mining: "stop", fishing: "stop", combat: "stop" } };
  }

  function emptyEq() {
    var eq = {};
    for (var i = 0; i < Rules.EQUIP_SLOTS.length; i++) eq[Rules.EQUIP_SLOTS[i]] = null;
    return eq;
  }

  function startXp() {
    var xp = {};
    for (var i = 0; i < Rules.SKILLS.length; i++) xp[Rules.SKILLS[i]] = 0;
    xp.hitpoints = 11540;
    return xp;
  }

  // Data.start, or the first map's origin when the start is not on a parsed map.
  function startPos() {
    var st = Data.start || {};
    if (World.inBounds(st.map, st.x, st.y)) return [st.map, st.x, st.y];
    var ids = Object.keys(World.maps);
    return [ids.length ? ids[0] : "overworld", 0, 0];
  }

  function respawnPos() {
    var r = Data.start && Array.isArray(Data.start.respawn) ? Data.start.respawn : [];
    return World.inBounds(r[0], r[1], r[2]) ? [r[0], r[1], r[2]] : startPos();
  }

  function newPlayer(pos) {
    var inv = [];
    for (var i = 0; i < Rules.INV_SIZE; i++) inv.push(null);
    return { map: pos[0], x: pos[1], y: pos[2], px: pos[1], py: pos[2], mx: pos[1], my: pos[2], face: 4, path: [],
      run: true, hp: 10, xp10: startXp(), inv: inv, eq: emptyEq(), bank: [], bankNote: false, quests: {}, qc: {}, flags: {}, kc: {},
      perks: {}, rested: 0, pets: {}, pet: null, petLog: {}, name: "", look: Rules.cleanLook(null),
      style: "accurate", afk: afkDefaults(), recallAt: 0, act: null, resume: null, iface: null, stop: null,
      atkTimer: 0, eatTimer: 0, petTimer: 0, petAt: -1000, foe: 0, combatUntil: 0, hitAt: -1000, anim: null, animAt: 0 };
  }

  function newSpec(c) {
    return c && c.special ? { next: 0, cx: 0, cy: 0, land: 0, used: false, enraged: false, outAt: 0 } : null;
  }

  function maxNpcHp(id) {
    var d = npcDef(id);
    return d && d.combat ? d.combat.hp : 1;
  }

  function newNpc(sp) {
    var d = npcDef(sp.id);
    return { uid: sp.uid, id: sp.id, map: sp.map, x: sp.x, y: sp.y, px: sp.x, py: sp.y, face: 4, sx: sp.x, sy: sp.y,
      r: sp.r, cond: sp.cond, on: !sp.cond, hp: maxNpcHp(sp.id), dest: null, target: false, atkTimer: 0,
      deadUntil: 0, spec: newSpec(d.combat), anim: null, animAt: 0, actAt: 0, barkAt: 0 };
  }

  function baseShops() {
    var out = {};
    var ids = Object.keys(Data.shops || {});
    for (var i = 0; i < ids.length; i++) {
      var stock = Array.isArray(Data.shops[ids[i]].stock) ? Data.shops[ids[i]].stock : [];
      var s = {};
      for (var k = 0; k < stock.length; k++) if (itemDef(stock[k][0])) s[stock[k][0]] = Util.int(stock[k][1], 0, QTY_MAX, 0);
      out[ids[i]] = s;
    }
    return out;
  }

  // Bare world: a kit-less player at the start, NPCs at spawn, shops at base, no fishing yet.
  function blank(rng) {
    return { v: 1, tick: 0, rng: rng >>> 0, gid: 1, objVer: 0, _blk: {}, away: false, player: newPlayer(startPos()),
      npcs: World.SPAWNS.map(newNpc), objs: {}, ground: [], grave: null, fish: {}, shops: baseShops(), events: [] };
  }

  // Once the player is in place: conditional spawns take their state, fishing spots are placed.
  function settle(state) {
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (n.cond) n.on = Script.test(state, n.cond);
    }
    placeFish(state);
    return state;
  }

  function createState(seed) {
    var s = blank(Number(seed) >>> 0);
    var p = s.player;
    var st = Data.start || {};
    var kit = Array.isArray(st.kit) ? st.kit : [];
    for (var i = 0; i < kit.length; i++) {
      if (Array.isArray(kit[i])) Player.add(p, kit[i][0], Util.int(kit[i][1], 1, QTY_MAX, 1));
    }
    for (var k = 0; k < Rules.EQUIP_SLOTS.length; k++) {
      var slot = Rules.EQUIP_SLOTS[k];
      var id = st.eq && Util.has(st.eq, slot) ? st.eq[slot] : null;
      var it = itemDef(id);
      if (it && it.equip && it.equip.slot === slot) p.eq[slot] = id;
    }
    settle(s);
    if (typeof st.welcome === "string" && st.welcome) Util.msg(s, st.welcome, "game");
    return s;
  }

  // ----------------------------------------------------------------
  // ------------------------- Fishing spots ------------------------
  // ----------------------------------------------------------------

  // A random candidate index not in `taken`, or -1. r is any object with an rng field.
  function pickFree(r, g, taken) {
    var free = [];
    for (var i = 0; i < g.tiles.length; i++) if (taken.indexOf(i) < 0) free.push(i);
    return free.length ? free[Util.randInt(r, free.length)] : -1;
  }

  function nextMove(r, tick) {
    return tick + Rules.FISH_MOVE[0] + Util.randInt(r, Rules.FISH_MOVE[1] - Rules.FISH_MOVE[0] + 1);
  }

  // Deterministic from state.rng without advancing it (section 6: a local mulberry32 seed).
  function placeFish(state) {
    var local = { rng: (state.rng ^ 0x5f3759df) >>> 0 };
    var groups = Object.keys(World.FISH);
    state.fish = {};
    for (var i = 0; i < groups.length; i++) {
      var g = World.FISH[groups[i]];
      var f = { at: [], move: [] };
      for (var k = 0; k < g.n; k++) {
        var c = pickFree(local, g, f.at);
        if (c < 0) break;
        f.at.push(c);
        f.move.push(nextMove(local, state.tick));
      }
      state.fish[groups[i]] = f;
    }
  }

  // Step 2: spots whose move is due jump to a random free candidate of their group.
  function moveFish(state) {
    var groups = Object.keys(state.fish);
    for (var i = 0; i < groups.length; i++) {
      var g = World.FISH[groups[i]];
      var f = state.fish[groups[i]];
      if (!g) continue;
      for (var k = 0; k < f.at.length; k++) {
        if (f.move[k] > state.tick) continue;
        var c = pickFree(state, g, f.at);
        if (c >= 0) f.at[k] = c;
        f.move[k] = nextMove(state, state.tick);
      }
    }
  }

  // The group id of the active spot at (x,y) on map, or null.
  function fishAt(state, map, x, y) {
    var groups = Object.keys(state.fish);
    for (var i = 0; i < groups.length; i++) {
      var g = World.FISH[groups[i]];
      if (!g || g.map !== map) continue;
      var at = state.fish[groups[i]].at;
      for (var k = 0; k < at.length; k++) {
        var t = g.tiles[at[k]];
        if (t && t[0] === x && t[1] === y) return groups[i];
      }
    }
    return null;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Objects ---------------------------
  // ----------------------------------------------------------------

  // Effective object at a tile: fishing spot, then override, then static object.
  function objectAt(state, map, x, y) {
    if (!World.inBounds(map, x, y)) return null;
    var so = World.staticObj(map, x, y);
    var base = so ? so.o : null;
    var o = { id: null, def: null, x: x, y: y, base: base, to: so ? so.to : null, alt: false, name: "" };
    var group = fishAt(state, map, x, y);
    var k = Util.key(map, x, y);
    if (group) {
      o.id = World.FISH[group].obj;
      o.group = group;
    } else if (Util.has(state.objs, k)) {
      o.id = state.objs[k].o;
      o.until = state.objs[k].until;
    } else {
      o.id = base;
    }
    if (!o.id || !Util.has(Data.objects, o.id)) return null;
    o.def = Data.objects[o.id];
    o.alt = !!o.def.alt && Script.test(state, o.def.alt.if);
    o.name = o.alt && o.def.alt.name ? o.def.alt.name : o.def.name;
    return o;
  }

  // The only writer of state.objs (I6).
  function setObj(state, map, x, y, objId, until) {
    var k = Util.key(map, x, y);
    if (objId) state.objs[k] = { o: objId, until: until };
    else delete state.objs[k];
    state.objVer = (state.objVer | 0) + 1;
  }

  // Ops of an objectAt result, alt-aware (an active alt has alt.ops or none).
  function objOps(o) {
    var list = o.alt ? o.def.alt.ops : o.def.ops;
    return Array.isArray(list) ? list : [];
  }

  // ----------------------------------------------------------------
  // ---------------------- Interfaces and acts ---------------------
  // ----------------------------------------------------------------

  // Script owns the single iface writer (dialogue effects need it too).
  function setIface(state, iface) {
    Script.setIface(state, iface);
  }

  // Replaces the act; a continuous anim ends with the act it belonged to.
  function setAct(state, act) {
    var p = state.player;
    if (p.anim && Util.has(CONT_ANIMS, p.anim)) p.anim = null;
    p.act = act || null;
  }

  // A world command: new act and path, interface closed, stop and resume cleared.
  function beginWorld(state, act, path) {
    var p = state.player;
    setAct(state, act);
    p.path = path || [];
    p.resume = null;
    p.stop = null;
    setIface(state, null);
  }

  // A failed check ends the activity with a reason (section 10.11) and a stop event. A pack-full stop
  // names the gather it ended (ref, op, base), so the UI's "Drop when full" resumes that one.
  function stop(state, why, a) {
    var p = state.player;
    setAct(state, null);
    p.resume = null;
    p.path = [];
    p.stop = why;
    Util.emit(state, a ? { type: "stop", why: why, ref: a.ref, op: a.op, base: a.base } : { type: "stop", why: why });
  }

  // Walking or waiting: the continuous work anim pauses.
  function idleAnim(p) {
    if (p.anim && Util.has(CONT_ANIMS, p.anim)) p.anim = null;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Targets ---------------------------
  // ----------------------------------------------------------------

  function alive(npc) {
    return !!npc && npc.on && npc.hp > 0;
  }

  // A ref resolved on player.map: { t, ref (canonical), x, y, o | npc | g } or null.
  function resolve(state, ref) {
    var r = typeof ref === "string" ? Util.parseRef(ref) : null;
    var p = state.player;
    if (!r) return null;
    if (r.t === "tile") return World.inBounds(p.map, r.x, r.y) ? { t: "tile", ref: Util.refTile(r.x, r.y), x: r.x, y: r.y } : null;
    if (r.t === "obj") {
      var o = objectAt(state, p.map, r.x, r.y);
      return o ? { t: "obj", ref: Util.refObj(r.x, r.y), x: r.x, y: r.y, o: o } : null;
    }
    if (r.t === "npc") {
      var n = r.n >= 1 && r.n <= state.npcs.length ? state.npcs[r.n - 1] : null;
      return alive(n) && n.map === p.map ? { t: "npc", ref: Util.refNpc(n.uid), x: n.x, y: n.y, npc: n } : null;
    }
    if (r.t === "ground") {
      for (var i = 0; i < state.ground.length; i++) {
        var g = state.ground[i];
        if (g.gid === r.n && g.map === p.map) return { t: "ground", ref: Util.refGround(g.gid), x: g.x, y: g.y, g: g };
      }
      return null;
    }
    if (r.t === "grave") {
      var gr = state.grave;
      return gr && gr.map === p.map ? { t: "grave", ref: Util.refGrave(), x: gr.x, y: gr.y, g: gr } : null;
    }
    return null;
  }

  function reached(state, t) {
    var p = state.player;
    if (t.t === "obj") return World.adjacent(p.x, p.y, t.x, t.y, t.o.def.from);
    if (t.t === "npc") return World.adjacent(p.x, p.y, t.npc.x, t.npc.y, "nsew");
    return p.x === t.x && p.y === t.y;
  }

  // Objects and NPCs are used from an allowed cardinal neighbour; ground items and graves from the tile.
  function pathTo(state, t) {
    var p = state.player;
    if (t.t === "obj") return World.findPath(state, p.map, p.x, p.y, { x: t.x, y: t.y, mode: "adj", from: t.o.def.from });
    if (t.t === "npc") return World.findPath(state, p.map, p.x, p.y, { x: t.npc.x, y: t.npc.y, mode: "adj" });
    return World.findPath(state, p.map, p.x, p.y, { x: t.x, y: t.y, mode: "tile" });
  }

  // The op `op` on target t: { kind, def, fail } (fail = text when its `if` fails), or null if not offered.
  // "use" (an inventory item on the target) is offered on objects, NPCs and ground items.
  function findOp(state, t, op) {
    if (op === "use") return t.t === "obj" || t.t === "npc" || t.t === "ground" ? { kind: "use", def: null, fail: null } : null;
    if (t.t === "ground") return op === "take" ? { kind: "take", def: null, fail: null } : null;
    if (t.t === "grave") return op === "loot" ? { kind: "loot", def: null, fail: null } : null;
    if (t.t === "npc") {
      var d = npcDef(t.npc.id);
      if (op === "attack") return d.combat ? { kind: "attack", def: null, fail: null } : null;
      var nops = Array.isArray(d.ops) ? d.ops : [];
      for (var i = 0; i < nops.length; i++) {
        if (nops[i].id === op) return Script.test(state, nops[i].if) ? { kind: nops[i].kind, def: nops[i], fail: null } : null;
      }
      return null;
    }
    if (t.t !== "obj") return null;
    var ops = objOps(t.o);
    for (var k = 0; k < ops.length; k++) {
      if (ops[k].id !== op) continue;
      if (Script.test(state, ops[k].if)) return { kind: ops[k].kind, def: ops[k], fail: null };
      return typeof ops[k].fail === "string" ? { kind: ops[k].kind, def: ops[k], fail: ops[k].fail } : null;
    }
    return null;
  }

  function examineText(t) {
    if (t.t === "obj") return t.o.def.examine;
    if (t.t === "npc") return npcDef(t.npc.id).examine;
    if (t.t === "ground") return itemDef(t.g.id) ? itemDef(t.g.id).examine : "";
    if (t.t === "grave") return Util.has(Data.objects, "gravestone") ? Data.objects.gravestone.examine : "";
    return "";
  }

  // ----------------------------------------------------------------
  // ------------------------ World commands ------------------------
  // ----------------------------------------------------------------

  // Walk: the path (with the near fallback) is computed once, here.
  function walkTo(state, x, y) {
    var p = state.player;
    if (!World.inBounds(p.map, x, y)) return false;
    var path = World.findPath(state, p.map, p.x, p.y, { x: x, y: y, mode: "tile", near: true });
    if (!path) return false;
    beginWorld(state, path.length ? { k: "walk" } : null, path);
    return true;
  }

  // Any op on an obj/npc/ground/grave ref (examine and use are Engine's): sets act = goto.
  function worldOp(state, ref, op, arg) {
    var t = resolve(state, ref);
    if (!t || t.t === "tile") return false;
    var f = findOp(state, t, op);
    if (!f) return false;
    if (f.fail !== null) {
      Util.msg(state, f.fail, "game");
      return false;
    }
    var a = state.player.act;
    if (a && a.ref === t.ref && a.op === op && (op !== "use" || a.arg === arg)) return true;
    if (op === "attack" && a && a.k === "fight" && a.uid === t.npc.uid) return true;
    if (op === "attack" && Combat.busyWith(state, t.npc)) {
      Util.msg(state, "You're already fighting.", "warn");
      return false;
    }
    var path = pathTo(state, t);
    if (!path) {
      Util.msg(state, REACH, "warn");
      return false;
    }
    var g = { k: "goto", ref: t.ref, op: op };
    if (typeof arg === "number" || arg === "x") g.arg = arg;
    beginWorld(state, g, path);
    return true;
  }

  function inFreeze(state) {
    var p = state.player;
    var r = World.regionAt(p.map, p.x, p.y);
    return !!r && !!r.freeze;
  }

  // Hearth recall (section 10.5): a 6-tick cast.
  function recall(state) {
    var p = state.player;
    if (p.act && p.act.k === "cast") return false;
    if (inFreeze(state)) {
      Util.msg(state, "The shrine can't reach you here.", "warn");
      return false;
    }
    if (state.tick - p.hitAt <= Rules.RECALL_BLOCK) {
      Util.msg(state, "You can't recall while under attack.", "warn");
      return false;
    }
    if (p.recallAt > state.tick) {
      Util.msg(state, "The shrine's blessing returns in " + Util.fmtDur(p.recallAt - state.tick) + ".", "warn");
      return false;
    }
    beginWorld(state, { k: "cast", until: state.tick + Rules.RECALL_CAST }, []);
    p.anim = "cast";
    p.animAt = state.tick;
    return true;
  }

  // ----------------------------------------------------------------
  // ------------------------ Tick: timers --------------------------
  // ----------------------------------------------------------------

  function snapshot(state) {
    var p = state.player;
    p.px = p.mx = p.x;
    p.py = p.my = p.y;
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (n.map !== p.map) continue;
      n.px = n.x;
      n.py = n.y;
    }
  }

  function expireObjs(state) {
    var keys = Object.keys(state.objs);
    for (var i = 0; i < keys.length; i++) {
      if (state.objs[keys[i]].until > state.tick) continue;
      var c = keys[i].lastIndexOf(":");
      var xy = keys[i].slice(c + 1).split(",");
      setObj(state, keys[i].slice(0, c), +xy[0], +xy[1], null, 0);
    }
  }

  function expireGround(state) {
    var g = state.ground;
    for (var i = 0; i < g.length; i++) {
      if (g[i].until > state.tick) continue;
      state.ground = g.filter(function (e) { return e.until > state.tick; });
      return;
    }
  }

  // Grave timers count live ticks only: catch-up extends them instead.
  function graveTimer(state) {
    var g = state.grave;
    if (!g) return;
    if (state.away) g.until += 1;
    else if (g.until <= state.tick) {
      state.grave = null;
      Util.msg(state, "Your gravestone crumbles to dust.", "warn");
    }
  }

  function spawnFree(state, n) {
    var p = state.player;
    if (p.map === n.map && p.x === n.sx && p.y === n.sy) return false;
    if (World.blocked(state, n.map, n.sx, n.sy)) return false;
    for (var i = 0; i < state.npcs.length; i++) {
      var o = state.npcs[i];
      if (o !== n && alive(o) && o.map === n.map && o.x === n.sx && o.y === n.sy) return false;
    }
    return true;
  }

  // A slain breath boss stays down while the player is still inside its arena: no respawn onto an idle winner
  // (the arena is a freeze region, so it would be a real fight with a real death).
  function inArena(state, n) {
    var d = npcDef(n.id);
    var sp = d && d.combat && d.combat.special && d.combat.special.k === "breath" ? d.combat.special : null;
    var p = state.player;
    var list = sp && Array.isArray(Data.regions) ? Data.regions : [];
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r && r.id === sp.arena) return r.map === p.map && Array.isArray(r.rect) && Util.inRect(r.rect, p.x, p.y);
    }
    return false;
  }

  function respawn(n) {
    n.on = true;
    n.hp = maxNpcHp(n.id);
    n.x = n.px = n.sx;
    n.y = n.py = n.sy;
    n.face = 4;
    n.dest = null;
    n.target = false;
    n.atkTimer = 0;
    n.spec = newSpec(npcDef(n.id).combat);
    n.anim = null;
    n.actAt = 0;
  }

  // Respawns and conditional (de)spawns; a blocked spawn tile retries next tick.
  function npcSpawns(state) {
    var p = state.player;
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (n.cond) {
        var ok = Script.test(state, n.cond);
        if (!ok && n.on && !(n.target && p.foe === n.uid)) {
          n.on = false;
          n.target = false;
          n.dest = null;
          n.px = n.x;
          n.py = n.y;
        } else if (ok && !n.on && n.deadUntil <= state.tick && spawnFree(state, n)) {
          respawn(n);
        }
      }
      if (n.on && n.hp <= 0 && n.deadUntil <= state.tick) {
        if (spawnFree(state, n) && !inArena(state, n)) respawn(n);
        else n.deadUntil = state.tick + 1;
      }
    }
  }

  function restock(state) {
    if (state.tick % Rules.SHOP_RESTOCK !== 0) return;
    var ids = Object.keys(Data.shops || {});
    for (var i = 0; i < ids.length; i++) {
      var cur = state.shops[ids[i]];
      var stock = Data.shops[ids[i]].stock || [];
      for (var k = 0; k < stock.length; k++) {
        var id = stock[k][0];
        if (Util.has(cur, id) && cur[id] < stock[k][1]) cur[id]++;
      }
    }
  }

  function timers(state) {
    expireObjs(state);
    expireGround(state);
    graveTimer(state);
    npcSpawns(state);
    moveFish(state);
    restock(state);
  }

  // ----------------------------------------------------------------
  // ---------------------- Tick: player phase ----------------------
  // ----------------------------------------------------------------

  function runCast(state) {
    var p = state.player;
    if (state.tick < p.act.until) return;
    var r = respawnPos();
    setAct(state, null);
    Combat.disengage(state);
    Player.teleport(state, r[0], r[1], r[2]);
    p.recallAt = state.tick + Rules.RECALL_CD;
    Util.emit(state, { type: "recall" });
  }

  // A chased NPC (goto or fight target) that moved this tick gets a fresh path before the player steps.
  function chase(state) {
    var p = state.player;
    var a = p.act;
    var n = null;
    if (a.k === "goto") {
      var t = resolve(state, a.ref);
      n = t && t.t === "npc" ? t.npc : null;
    } else if (a.k === "fight" && a.uid > 0) {
      n = state.npcs[a.uid - 1];
      if (!alive(n) || n.map !== p.map) n = null;
    }
    if (!n || (n.x === n.px && n.y === n.py)) return;
    if (World.adjacent(p.x, p.y, n.x, n.y, "nsew")) p.path = [];
    else {
      var path = World.findPath(state, p.map, p.x, p.y, { x: n.x, y: n.y, mode: "adj" });
      if (path) p.path = path;
    }
  }

  // A pass path ([x, y, 1] steps) goes through the gate tile in one tick; it needs a free exit.
  function stepOk(state, p, s, dx, dy) {
    if (s[2] !== 1) return World.canStep(state, p.map, p.x, p.y, dx, dy);
    var last = p.path[p.path.length - 1];
    return Math.abs(dx) <= 1 && Math.abs(dy) <= 1 && World.inBounds(p.map, s[0], s[1]) &&
      !World.blocked(state, p.map, last[0], last[1]);
  }

  // 1 step, or 2 when running (always 2 through a gate); mx,my = the first of 2 steps. Moving closes the interface.
  function move(state) {
    var p = state.player;
    var n = p.run || (p.path.length && p.path[0][2] === 1) ? 2 : 1;
    var steps = 0;
    while (steps < n && p.path.length) {
      var s = p.path[0];
      var dx = s[0] - p.x;
      var dy = s[1] - p.y;
      if (!stepOk(state, p, s, dx, dy)) {
        p.path = [];
        break;
      }
      p.path.shift();
      p.x = s[0];
      p.y = s[1];
      p.face = Util.dirIndex(dx, dy);
      steps++;
      if (steps === 1) {
        p.mx = p.x;
        p.my = p.y;
      }
    }
    if (steps < 2) {
      p.mx = p.x;
      p.my = p.y;
    }
    if (steps && p.iface) setIface(state, null);
  }

  // ----------------------------------------------------------------
  // ------------------- Arrival: take, loot, use -------------------
  // ----------------------------------------------------------------

  // Takes as many as fit from a ground pile (loot event per take); the rest stays.
  // The loot event comes before the full-pack warning, so a partial take doesn't read as a failure.
  function takeGround(state, g) {
    var got = Player.add(state.player, g.id, g.qty, g.note);
    if (got > 0) {
      Util.emit(state, { type: "loot", id: g.id, qty: got });
      g.qty -= got;
      if (g.qty <= 0) state.ground.splice(state.ground.indexOf(g), 1);
      Util.emit(state, { type: "save" });
    }
    if (g.qty > 0) Util.msg(state, FULL, "warn");
  }

  // Moves what fits from the grave; it persists until it is empty or expires.
  function lootGrave(state) {
    var g = state.grave;
    var left = [];
    var any = false;
    for (var i = 0; i < g.items.length; i++) {
      var s = g.items[i];
      var got = Player.add(state.player, s.id, s.qty, s.note);
      if (got > 0) {
        any = true;
        Util.emit(state, { type: "loot", id: s.id, qty: got });
      }
      if (got < s.qty) left.push(s.note ? { id: s.id, qty: s.qty - got, note: true } : { id: s.id, qty: s.qty - got });
    }
    if (left.length) Util.msg(state, FULL, "warn");
    g.items = left;
    if (!left.length) state.grave = null;
    if (any) Util.emit(state, { type: "save" });
  }

  // The make station offered by an object's or NPC's ops (`if` passing), or null.
  function stationOf(state, t) {
    var ops = t.t === "obj" ? objOps(t.o) : t.t === "npc" && Array.isArray(npcDef(t.npc.id).ops) ? npcDef(t.npc.id).ops : [];
    for (var i = 0; i < ops.length; i++) {
      if (ops[i] && ops[i].kind === "make" && Script.test(state, ops[i].if)) return ops[i].station;
    }
    return null;
  }

  // An active alt ignores the object's uses.
  function usesOf(t) {
    if (t.t === "obj") return t.o.alt ? null : t.o.def.uses;
    return t.t === "npc" ? npcDef(t.npc.id).uses : null;
  }

  // Section 9 Use resolution, steps 1, 2 and 4, for an item used on a world target.
  function useArrive(state, t, slot) {
    var p = state.player;
    var s = typeof slot === "number" && slot >= 0 && slot < p.inv.length ? p.inv[slot] : null;
    if (!s) return;
    if (Script.useOn(state, usesOf(t), s.id) !== null) return;
    var st = stationOf(state, t);
    if (st && Script.openMake(state, st, t.t === "obj" ? t.ref : null, s.id)) return;
    Util.msg(state, NOTHING, "game");
  }

  // Whether using item id on target t would do something (the use-mode outline).
  function canUseOn(state, t, id) {
    if (!t || (t.t !== "obj" && t.t !== "npc")) return false;
    var uses = usesOf(t);
    if (Array.isArray(uses) && uses.some(function (u) {
      return u && (Array.isArray(u.item) ? u.item.indexOf(id) >= 0 : u.item === id);
    })) return true;
    var st = stationOf(state, t);
    return !!st && Object.keys(Data.recipes || {}).some(function (rid) {
      var r = Data.recipes[rid];
      return Array.isArray(r.at) && r.at.indexOf(st) >= 0 && Array.isArray(r.in) &&
        r.in.some(function (e) { return Array.isArray(e) && e[0] === id; });
    });
  }

  // ----------------------------------------------------------------
  // ----------------------- Approach and pass ----------------------
  // ----------------------------------------------------------------

  function lower(s) { return String(s || "").toLowerCase(); }
  function objFrom(id) { return Util.has(Data.objects, id) ? Data.objects[id].from : undefined; }

  function toolText(cat) {
    var t = Data.vocab && Data.vocab.tools;
    return t && Util.has(t, cat) ? t[cat] : String(cat);
  }

  // Walks to an allowed side of (x,y). True while on the way, or when it can't be reached (the act ends);
  // the first roll or product waits a full cycle after arriving.
  function approach(state, a, x, y, from, ticks) {
    var p = state.player;
    if (!p.path.length && !World.adjacent(p.x, p.y, x, y, from)) {
      var path = World.findPath(state, p.map, p.x, p.y, { x: x, y: y, mode: "adj", from: from });
      if (!path) {
        Util.msg(state, REACH, "warn");
        setAct(state, null);
        return true;
      }
      p.path = path;
    }
    if (!p.path.length) return false;
    a.next = Math.max(a.next, state.tick + 1 + ticks);
    idleAnim(p);
    return true;
  }

  // Section 10.2 pass: a forced 2-step walk through the gate to the far side, if that tile is free.
  function passGate(state, t) {
    var p = state.player;
    var ex = 2 * t.x - p.x;
    var ey = 2 * t.y - p.y;
    if (World.blocked(state, p.map, ex, ey)) {
      Util.msg(state, "Something is in the way.", "warn");
      return;
    }
    setAct(state, { k: "walk" });
    p.path = [[t.x, t.y, 1], [ex, ey, 1]];
  }

  // ----------------------------------------------------------------
  // --------------------------- Gathering --------------------------
  // ----------------------------------------------------------------

  var SKILL_ANIM = { woodcutting: "chop", mining: "mine", fishing: "fish" };

  // The gather op of an act: the base object's op with that id.
  function gatherOp(a) {
    var d = Util.has(Data.objects, a.base) ? Data.objects[a.base] : null;
    var ops = d && Array.isArray(d.ops) ? d.ops : [];
    for (var i = 0; i < ops.length; i++) if (ops[i] && ops[i].id === a.op && ops[i].kind === "gather") return ops[i];
    return null;
  }

  function yieldsOf(op) {
    return (Array.isArray(op.yields) ? op.yields : []).filter(function (y) { return y && typeof y.lvl === "number"; });
  }

  // Yields the level allows, highest level first.
  function eligible(p, op) {
    var L = Player.level(p, op.skill);
    return yieldsOf(op).filter(function (y) { return y.lvl <= L; }).sort(function (a, b) { return b.lvl - a.lvl; });
  }

  // Every allowed yield fits (a gem-table yield needs a free slot).
  function fits(p, op) {
    return eligible(p, op).every(function (y) {
      return y.table === "gem" ? Player.free(p) > 0 : Player.canAdd(p, y.item, 1);
    });
  }

  // Section 10.3 checks per roll: { msg, why }, { full: true } or null.
  function gatherCheck(state, op) {
    var p = state.player;
    var min = Infinity;
    yieldsOf(op).forEach(function (y) { min = Math.min(min, y.lvl); });
    if (Player.level(p, op.skill) < min) {
      return { msg: "You need " + Player.skillName(op.skill) + " level " + Util.fmtInt(min) + " for this.", why: "level too low" };
    }
    if (op.tool && !Player.bestTool(p, op.tool)) {
      // Holding only tools above your level (a steel axe bought at Woodcutting 1) names the level, not "an axe".
      var held = Player.heldTools(p, op.tool).map(itemDef).sort(function (x, y) { return x.tool.lvl - y.tool.lvl; })[0];
      if (held && typeof held.tool.lvl === "number") {
        return { msg: "You need " + Player.skillName(op.skill) + " level " + Util.fmtInt(held.tool.lvl) + " to use your " +
          lower(held.name) + ".", why: "level too low" };
      }
      return { msg: "You need " + toolText(op.tool) + " for this.", why: "no tool" };
    }
    if (op.bait && Player.count(p, op.bait) < 1) return { msg: "You have no feathers left.", why: "out of feathers" };
    return fits(p, op) ? null : { full: true };
  }

  function failGather(state, a, op, why) {
    if (why.full) return onFull(state, a, op);
    Util.msg(state, why.msg, "warn");
    stop(state, why.why);
  }

  function startText(state, o, op) {
    if (op.skill === "mining") return "You start mining the " + lower(o.name) + ".";
    if (op.skill !== "fishing") return "You start chopping the " + lower(o.name) + ".";
    var tool = op.tool ? Player.bestTool(state.player, op.tool) : null;
    return tool ? "You wade in with your " + lower(itemDef(tool).name) + "." : null;
  }

  // Arrival on a gather op: the checks, then the act with the anchor on the node.
  function startGather(state, t, op) {
    var p = state.player;
    var why = gatherCheck(state, op);
    if (why && !why.full) return failGather(state, null, op, why);
    var a = { k: "gather", ref: t.ref, op: op.id, base: t.o.id, group: t.o.group || null, ax: t.x, ay: t.y,
      next: state.tick + op.ticks, wait: false, sub: null, subAt: 0 };
    setAct(state, a);
    if (why) onFull(state, a, op);
    if (p.act !== a) return;
    var text = startText(state, t.o, op);
    if (text) Util.msg(state, text, "game");
    if (!a.sub) p.anim = SKILL_ANIM[op.skill] || null;
  }

  function setNode(state, a, c, path, wait, ticks) {
    a.ref = Util.refObj(c[0], c[1]);
    a.wait = wait;
    a.next = state.tick + ticks;
    state.player.path = path;
    if (wait) idleAnim(state.player);
  }

  // Nodes of the act's base within RETARGET_RANGE of the anchor: the nearest available one by path, or
  // (orWait) the nearest depleted one to wait at. True when a node was chosen.
  function research(state, a, ticks, orWait) {
    var p = state.player;
    var m = World.maps[p.map];
    var list = m && Util.has(m.nodes, a.base) ? m.nodes[a.base] : [];
    var from = objFrom(a.base);
    var up = [];
    var down = [];
    for (var i = 0; i < list.length; i++) {
      var t = list[i];
      if (Util.dist(t[0], t[1], a.ax, a.ay) > Rules.RETARGET_RANGE) continue;
      var o = objectAt(state, p.map, t[0], t[1]);
      (o && o.id === a.base ? up : down).push([t[0], t[1], from]);
    }
    var r = up.length ? World.findPathAny(state, p.map, p.x, p.y, up) : null;
    if (r) setNode(state, a, up[r.i], r.path, false, ticks);
    else if (orWait && down.length && (r = World.findPathAny(state, p.map, p.x, p.y, down))) {
      setNode(state, a, down[r.i], r.path, true, ticks);
    }
    return !!r;
  }

  // Depleted node: retarget (afk.cont) or stop silently.
  function retarget(state, a, op) {
    if (!state.player.afk.cont) setAct(state, null);
    else if (!research(state, a, op.ticks, true)) stop(state, "no " + lower(Data.objects[a.base].name) + " nearby");
  }

  // Fishing follows the nearest active spot of its group when its own spot moves.
  function followSpot(state, a, op) {
    var p = state.player;
    var g = World.FISH[a.group];
    var f = Util.has(state.fish, a.group) ? state.fish[a.group] : null;
    var from = objFrom(g ? g.obj : null);
    var cands = [];
    if (g && f && g.map === p.map) f.at.forEach(function (i) { if (g.tiles[i]) cands.push([g.tiles[i][0], g.tiles[i][1], from]); });
    var r = cands.length ? World.findPathAny(state, p.map, p.x, p.y, cands) : null;
    if (!r) {
      stop(state, "no " + lower(Data.objects[a.base].name) + " nearby");
      return false;
    }
    setNode(state, a, cands[r.i], r.path, false, op.ticks);
    return true;
  }

  // The act's node is there to work: fishing spot still active, node not depleted, not waiting.
  function locate(state, a, op) {
    var p = state.player;
    var r = Util.parseRef(a.ref);
    if (a.group) return (!!r && fishAt(state, p.map, r.x, r.y) === a.group) || followSpot(state, a, op);
    var o = r ? objectAt(state, p.map, r.x, r.y) : null;
    var up = !!o && o.id === a.base;
    if (a.wait && up) {
      a.wait = false;
      a.next = Math.max(a.next, state.tick + op.ticks);
    } else if (a.wait) {
      if (state.tick % 10 === 0) research(state, a, op.ticks, false);
      idleAnim(p);
      return false;
    } else if (!up) {
      retarget(state, a, op);
      return p.act === a && !a.wait;
    }
    return true;
  }

  // Lucky day: a second unit of the yield when it fits; never a quest item or an untradeable.
  function lucky(state, op, id) {
    var d = itemDef(id);
    if (d.cat === "quest" || d.untradeable || !Player.canAdd(state.player, id, 1)) return;
    if (!Player.perkRoll(state, op.skill, "double")) return;
    Player.give(state, id, 1);
    Player.perkMsg(state, op.skill, "double", null, "loot");
  }

  // Bird's nest: a purse of coins with a log, when the coins fit.
  function nest(state, op) {
    var f = Player.perkList(op.skill).filter(function (d) { return d.fx === "nest" && Array.isArray(d.coins); })[0];
    if (!f || !Player.canAdd(state.player, "coins", f.coins[1]) || !Player.perkRoll(state, op.skill, "nest")) return;
    var n = f.coins[0] + Util.randInt(state, f.coins[1] - f.coins[0] + 1);
    Player.give(state, "coins", n);
    Util.msg(state, "You find a bird's nest with " + Util.fmtInt(n) + " coins in it.", "loot");
  }

  // The 1/op.gem extra gem; Gem eye raises it by its fraction (the same single roll either way).
  function gemFound(state, op) {
    var v = Player.perkVal(state.player, op.skill, "gem");
    return v > 0 ? Util.rand(state) < (1 + v) / op.gem : Util.randInt(state, op.gem) === 0;
  }

  // Ticks until a node the player emptied comes back; Prospector shortens it (at least 1).
  function respawnTicks(state, op) {
    var t = Util.int(op.respawn, 1, 100000, 1);
    var v = Player.perkVal(state.player, op.skill, "respawn");
    return v > 0 ? Math.max(1, Math.round(t * Math.max(0, 1 - v))) : t;
  }

  // Success: the item (or a gem-table roll) and its perks, bait, XP, the extra gem roll, bonuses, then
  // maybe deplete. Every perk roll is skipped at rank 0, so the RNG stream is unchanged without perks.
  function gain(state, a, op, y, r) {
    var p = state.player;
    var id = y.table === "gem" ? Combat.gemRoll(state) : y.item;
    if (itemDef(id)) {
      Player.give(state, id, 1);
      Util.msg(state, "You gather " + lower(itemDef(id).name) + ".", "game");
      lucky(state, op, id);
      nest(state, op);
    }
    if (op.bait && !Player.perkRoll(state, op.skill, "bait")) Player.remove(p, op.bait, 1);
    Player.addXp(state, op.skill, y.xp * seasonMod(state, op.skill, "xp"), true);
    if (op.gem > 0 && gemFound(state, op)) {
      var g = Combat.gemRoll(state);
      if (g) {
        Player.give(state, g, 1);
        Util.msg(state, "You gather " + lower(itemDef(g).name) + ".", "loot");
      }
    }
    // A bonus never rolls into a full pack: at your feet it is not "owned", so a second seal could roll.
    (Array.isArray(op.bonus) ? op.bonus : []).forEach(function (b) {
      if (!b || !itemDef(b.item) || !Player.canAdd(p, b.item, 1) || !Script.test(state, b.if)) return;
      if (!(Util.rand(state) < b.chance)) return;
      Player.give(state, b.item, 1);
      if (typeof b.msg === "string") Util.msg(state, b.msg, "loot");
    });
    var gone = !a.group && Util.has(Data.objects, op.depleted) && op.deplete > 0 &&
      (op.deplete >= 1 || Util.rand(state) < op.deplete);
    if (gone) setObj(state, p.map, r.x, r.y, op.depleted, state.tick + respawnTicks(state, op));
    // Stop at once; drop and courier wait for the next roll (gatherCheck), so the full pack shows for one
    // cycle and a click away still keeps it.
    if (!fits(p, op) && fullMode(state, op) === "stop") onFull(state, a, op);
    if (gone && p.act === a) retarget(state, a, op);
  }

  // One roll per op.ticks: allowed yields, highest level first; the first success wins. The season's
  // gather mod and Quick swing multiply the tool's (gatherChance still caps at 1); Big one raises the
  // better catch where two are allowed.
  function roll(state, a, op, r) {
    var p = state.player;
    var L = Player.level(p, op.skill);
    var tool = op.skill === "fishing" || !op.tool ? null : itemDef(Player.bestTool(p, op.tool));
    var mult = (tool && typeof tool.tool.mult === "number" ? tool.tool.mult : 1) * seasonMod(state, op.skill, "gather") *
      (1 + Player.perkVal(p, op.skill, "gather"));
    var ys = eligible(p, op);
    var big = ys.length > 1 ? 1 + Player.perkVal(p, op.skill, "better") : 1;
    a.next = a.next + op.ticks > state.tick ? a.next + op.ticks : state.tick + op.ticks;
    for (var i = 0; i < ys.length; i++) {
      var m = i === 0 ? mult * big : mult;
      if (Util.rand(state) < Rules.gatherChance(L, ys[i].low, ys[i].high, m)) return gain(state, a, op, ys[i], r);
    }
  }

  // Per tick: follow or wait for the node, walk to it, then roll when the cycle is due.
  function runGather(state) {
    var p = state.player;
    var a = p.act;
    var op = gatherOp(a);
    if (!op) return setAct(state, null);
    if (a.sub && state.tick >= a.subAt) {
      a.sub = null;
      a.subAt = 0;
    }
    if (!locate(state, a, op)) return;
    var r = Util.parseRef(a.ref);
    if (approach(state, a, r.x, r.y, objFrom(a.base), op.ticks)) return;
    p.face = Util.dirIndex(r.x - p.x, r.y - p.y);
    if (a.sub) return;
    p.anim = SKILL_ANIM[op.skill] || null;
    if (state.tick < a.next) return;
    var why = gatherCheck(state, op);
    if (why) failGather(state, a, op, why);
    else roll(state, a, op, r);
  }

  // ----------------------------------------------------------------
  // -------------------------- Full packs --------------------------
  // ----------------------------------------------------------------

  // The op's yield items (a gem-table yield means every gem on the table).
  function yieldIds(op) {
    var out = [];
    yieldsOf(op).forEach(function (y) {
      var ids = y.table === "gem" ? (Data.gemTable || []).map(function (g) { return g[1]; }) : [y.item];
      ids.forEach(function (id) { if (itemDef(id) && out.indexOf(id) < 0) out.push(id); });
    });
    return out;
  }

  // Drop mode: every unit of the yield items beyond `keep`, one pile per id on the player's tile.
  function dropYields(state, op) {
    var p = state.player;
    var keep = Script.keep(state);
    var items = [];
    yieldIds(op).forEach(function (id) {
      var n = Player.count(p, id) - (Util.has(keep, id) ? keep[id] : 0);
      if (n <= 0) return;
      Player.remove(p, id, n);
      Player.toGround(state, p.map, p.x, p.y, id, n);
      items.push([id, n]);
      Util.msg(state, "Pack full: dropped " + Util.fmtInt(n) + " " + lower(itemDef(id).name) + " at your feet.", "game");
    });
    if (items.length) Util.emit(state, { type: "full", mode: "drop", items: items });
    return items.length;
  }

  // Every item some gather op uses as bait (feathers): the courier leaves them in the pack.
  function baitIds() {
    var out = {};
    Object.keys(Data.objects || {}).forEach(function (k) {
      var d = Data.objects[k];
      var ops = (d && Array.isArray(d.ops) ? d.ops : []).concat(d && d.alt && Array.isArray(d.alt.ops) ? d.alt.ops : []);
      ops.forEach(function (op) { if (op && typeof op.bait === "string") out[op.bait] = 1; });
    });
    return out;
  }

  // "21 willow logs, 2 burnt fish": up to three ids, then "and N more".
  function haulText(items) {
    var parts = items.slice(0, 3).map(function (e) { return Util.fmtInt(e[1]) + " " + lower(itemDef(e[0]).name); });
    var more = items.length - parts.length;
    return parts.join(", ") + (more > 0 ? " and " + Util.fmtInt(more) + " more" : "");
  }

  // Courier mode: everything but tools, bait (for any op), food, untradeables, coins and `keep` goes to the
  // bank; junk such as burnt food goes too. Returns the units moved.
  function courier(state) {
    var p = state.player;
    var keep = Script.keep(state);
    var bait = baitIds();
    var items = [];
    var done = {};
    var units = 0;
    for (var i = 0; i < p.inv.length; i++) {
      var s = p.inv[i];
      var d = s ? itemDef(s.id) : null;
      if (!d || s.note || Util.has(done, s.id) || s.id === "coins" || Util.has(bait, s.id) || d.tool || d.food || d.untradeable) continue;
      var id = s.id;
      var have = Player.count(p, id);
      done[id] = 1;
      var n = have - (Util.has(keep, id) ? keep[id] : 0);
      if (n <= 0 || !Player.deposit(state, i, n)) continue;
      items.push([id, have - Player.count(p, id)]);
      units += have - Player.count(p, id);
    }
    if (!units) return 0;
    Util.msg(state, "Courier: " + haulText(items) + " sent to the bank.", "game");
    Util.emit(state, { type: "full", mode: "courier", items: items });
    return units;
  }

  // The op skill's full mode in effect: courier without the satchel is stop.
  function fullMode(state, op) {
    var p = state.player;
    var mode = Util.has(p.afk.full, op.skill) ? p.afk.full[op.skill] : "stop";
    // The satchel works from the pack, worn or the bank (Deposit-All must not switch courier off).
    if (mode === "courier" && !(Script.owned(state, "courier_satchel") > 0)) mode = "stop";
    return mode;
  }

  // Section 10.7: stop, or drop (1 tick) / courier (3 ticks) and carry on.
  function onFull(state, a, op) {
    var p = state.player;
    var mode = fullMode(state, op);
    var done = mode === "drop" ? dropYields(state, op) : mode === "courier" ? courier(state) : 0;
    if (!done) {
      Util.msg(state, FULL, "warn");
      stop(state, "pack full", a);
      return;
    }
    var cost = mode === "drop" ? Rules.DROP_TICKS : Rules.COURIER_TICKS;
    a.sub = mode;
    a.subAt = state.tick + cost;
    a.next = Math.max(a.next, state.tick) + cost;
    idleAnim(p);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Making ----------------------------
  // ----------------------------------------------------------------

  function makeAnim(r) {
    if (r.group === "smelt" || r.group === "smith") return r.group;
    return r.skill === "cooking" ? "cook" : r.skill === "firemaking" ? "fire" : "craft";
  }

  // The station object of a make act, while it still offers one of the recipe's stations.
  function stationAt(state, ref, r) {
    var t = Util.parseRef(ref);
    var o = t && t.t === "obj" ? objectAt(state, state.player.map, t.x, t.y) : null;
    var ops = o ? objOps(o) : [];
    var at = Array.isArray(r.at) ? r.at : [];
    for (var i = 0; i < ops.length; i++) {
      if (ops[i] && ops[i].kind === "make" && at.indexOf(ops[i].station) >= 0) return { o: o, x: t.x, y: t.y, st: ops[i].station };
    }
    return null;
  }

  // The first free cardinal neighbour (W, E, S, N) of the player, or null.
  function freeSide(state) {
    var p = state.player;
    var dx = [-1, 1, 0, 0];
    var dy = [0, 0, 1, -1];
    for (var d = 0; d < 4; d++) {
      if (!World.blocked(state, p.map, p.x + dx[d], p.y + dy[d])) return [p.x + dx[d], p.y + dy[d]];
    }
    return null;
  }

  // Section 10.4 place: no object, fishing spot, grave or NPC on the tile, and a free side to step to; no
  // ground pile either (a fire would bury it: piles are taken from their own tile). The refusal, or null.
  function placeWhy(state) {
    var p = state.player;
    var g = state.grave;
    var no = "There's no room for a fire here.";
    if (objectAt(state, p.map, p.x, p.y) || (g && g.map === p.map && g.x === p.x && g.y === p.y)) return no;
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (alive(n) && n.map === p.map && n.x === p.x && n.y === p.y) return no;
    }
    if (!freeSide(state)) return no;
    for (var k = 0; k < state.ground.length; k++) {
      var gi = state.ground[k];
      if (gi.map === p.map && gi.x === p.x && gi.y === p.y) return "Step off the pile to light a fire.";
    }
    return null;
  }

  function bankMakeAllowed(r) {
    return !r.place && !r.refuel && Array.isArray(r.out) && r.out.length > 0;
  }

  function makeCount(p, id, bankFeed) {
    return bankFeed ? Player.bankCount(p, id) : Player.count(p, id);
  }

  // Reserve space for either outcome, including every possible perk bonus, before consuming inputs.
  function bankMakeRoom(p, r) {
    var base = Object.create(null);
    p.bank.forEach(function (e) { base[e.id] = e.qty; });
    (r.in || []).forEach(function (e) { base[e[0]] -= e[1]; });
    function fits(outs, success) {
      var qty = Object.assign(Object.create(null), base);
      var twice = success && Player.perkVal(p, r.skill, "twice", r.group) > 0;
      outs.forEach(function (e) { qty[e[0]] = (qty[e[0]] || 0) + e[1] * (twice ? 2 : 1); });
      if (success && r.in && r.in.length && Player.perkVal(p, r.skill, "save", r.group) > 0) {
        var id = r.in[0][0];
        qty[id] = (qty[id] || 0) + 1;
      }
      var ids = Object.keys(qty).filter(function (id) { return qty[id] > 0; });
      return ids.length <= Rules.BANK_MAX && ids.every(function (id) { return qty[id] <= QTY_MAX; });
    }
    return fits(r.out || [], true) && fits(r.fail || [], false);
  }

  // Each product: { msg, why, mat? } for the first failed check, else null.
  function makeCheck(state, a, r) {
    var p = state.player;
    if (a.bankFeed && !bankMakeAllowed(r)) {
      return { msg: "Bank-fed production is not available for this recipe.", why: "unsupported bank recipe" };
    }
    if (a.at && !stationAt(state, a.at, r)) return { msg: null, why: "the fire went out" };
    if (Player.level(p, r.skill) < r.lvl) {
      return { msg: "You need " + Player.skillName(r.skill) + " level " + Util.fmtInt(r.lvl) + " for this.", why: "level too low" };
    }
    if (r.if && !Script.test(state, r.if)) return { msg: typeof r.ifMsg === "string" ? r.ifMsg : NOTHING, why: null };
    var tools = Array.isArray(r.tools) ? r.tools : [];
    for (var i = 0; i < tools.length; i++) {
      if (!Player.hasTools(p, [tools[i]])) return { msg: "You need " + toolText(tools[i]) + " for this.", why: "no tool" };
    }
    var ins = Array.isArray(r.in) ? r.in : [];
    for (var k = 0; k < ins.length; k++) {
      if (makeCount(p, ins[k][0], a.bankFeed) < ins[k][1]) {
        return { msg: a.bankFeed ? "You've run out of materials in the bank." : "You've run out of materials.",
          why: "out of materials", mat: true };
      }
    }
    if (a.bankFeed && !bankMakeRoom(p, r)) return { msg: "Your bank has no room for the products or possible perk bonuses.", why: "bank full" };
    var nope = r.place ? placeWhy(state) : null;
    if (nope) return { msg: nope, why: null };
    return null;
  }

  // Engine.make: starts a recipe from the open make sheet (station and at come from the sheet).
  function startMake(state, rid, count) {
    var p = state.player;
    var f = p.iface;
    var n = count === -1 ? -1 : typeof count === "number" && Math.floor(count) === count && count >= 1 ? Math.min(count, QTY_MAX) : 0;
    if (!n || !f || f.t !== "make" || !Array.isArray(f.rids) || f.rids.indexOf(rid) < 0 || !Util.has(Data.recipes, rid)) return false;
    var r = Data.recipes[rid];
    var t = typeof f.at === "string" ? Util.parseRef(f.at) : null;
    var a = { k: "make", rid: rid, left: n, next: state.tick + Util.int(r.ticks, 0, 100000, 0), at: t ? f.at : null,
      ax: t ? t.x : p.x, ay: t ? t.y : p.y, bankFeed: f.bankFeed === true };
    var why = makeCheck(state, a, r);
    if (why && why.why === "the fire went out") {
      setIface(state, null);
      stop(state, why.why);
      return false;
    }
    if (why) {
      Util.msg(state, why.msg, "warn");
      return false;
    }
    beginWorld(state, a, []);
    p.anim = makeAnim(r);
    return true;
  }

  // Fire ticks with Long burn (lighting and refuelling).
  function fireTicks(state, skill, ticks) {
    var v = Player.perkVal(state.player, skill, "fire");
    return v > 0 ? Math.round(ticks * (1 + v)) : ticks;
  }

  // Lighting: the object goes on the player's tile, then the player steps W, E, S or N.
  function place(state, pl, skill) {
    var p = state.player;
    var side = freeSide(state);
    if (!side || !Util.has(Data.objects, pl.obj)) return;
    setObj(state, p.map, p.x, p.y, pl.obj, state.tick + fireTicks(state, skill, Util.int(pl.ticks, 1, 100000, Rules.FIRE_TICKS)));
    p.face = Util.dirIndex(side[0] - p.x, side[1] - p.y);
    p.x = p.mx = side[0];
    p.y = p.my = side[1];
  }

  // XP of a make in skill: season, the skill's XP perks, and (rolled once for the main skill) Master's touch.
  function makeXp(state, r, skill, xp, main) {
    var m = seasonMod(state, skill, "xp") * (1 + Player.perkVal(state.player, skill, "xp"));
    if (main && Player.perkRoll(state, skill, "xp2x", r.group)) {
      m *= 2;
      Player.perkMsg(state, skill, "xp2x", r.group);
    }
    Player.addXp(state, skill, xp * m, true);
  }

  // Thrifty and Kindling give one unit of the first input back; Double batch and Quick stitch make the
  // products again. Inventory jobs drop overflow at the player's feet; bank jobs reserve space first.
  function makeGive(state, id, qty, bankFeed) {
    if (bankFeed) Player.bankPut(state.player, id, qty);
    else Player.give(state, id, qty);
  }

  function extras(state, r, outs, bankFeed) {
    var ins = Array.isArray(r.in) ? r.in : [];
    if (ins.length && Player.perkRoll(state, r.skill, "save", r.group)) {
      Player.perkMsg(state, r.skill, "save", r.group);
      makeGive(state, ins[0][0], 1, bankFeed);
    }
    if (outs.length && Player.perkRoll(state, r.skill, "twice", r.group)) {
      Player.perkMsg(state, r.skill, "twice", r.group, "loot");
      outs.forEach(function (e) { makeGive(state, e[0], e[1], bankFeed); });
    }
  }

  function made(state, r, st, bankFeed) {
    var p = state.player;
    var outs = Array.isArray(r.out) ? r.out : [];
    if (r.place) place(state, r.place, r.skill);
    outs.forEach(function (e) { makeGive(state, e[0], e[1], bankFeed); });
    makeXp(state, r, r.skill, r.xp, true);
    if (Array.isArray(r.xp2)) makeXp(state, r, r.xp2[0], r.xp2[1], false);
    if (typeof r.msg === "string") Util.msg(state, r.msg, "game");
    extras(state, r, outs, bankFeed);
    if (r.refuel > 0 && st && typeof st.o.until === "number") {
      setObj(state, p.map, st.x, st.y, st.o.id, Math.max(st.o.until, state.tick + fireTicks(state, r.skill, r.refuel)));
    }
    outs.forEach(function (e) { Script.onMade(state, e[0]); });
  }

  // Success odds of one product: makeChance (fires burn more), with Steady hand taking off part of the burn.
  function makeOdds(state, r, st) {
    var p = state.player;
    var full = st && st.st === "fire" ? Math.min(99, r.full + 5) : r.full;
    var chance = typeof r.full === "number" ? Rules.makeChance(Player.level(p, r.skill), r.lvl, full) : 1;
    var v = chance < 1 ? Player.perkVal(p, r.skill, "burn", r.group) : 0;
    return v > 0 ? 1 - (1 - chance) * Math.max(0, 1 - v) : chance;
  }

  // One product: checks, inputs, the success roll (fires burn more), then the count. False when it ended.
  function makeOne(state, a, r) {
    var p = state.player;
    var why = makeCheck(state, a, r);
    if (why) {
      if (why.mat && a.left === -1 && !a.bankFeed) setAct(state, null);   // Make-All used everything up
      else {
        if (why.msg) Util.msg(state, why.msg, "warn");
        if (why.why) stop(state, why.why);
        else setAct(state, null);
      }
      return false;
    }
    (r.in || []).forEach(function (e) {
      if (a.bankFeed) Player.bankRemove(p, e[0], e[1]);
      else Player.remove(p, e[0], e[1]);
    });
    var st = a.at ? stationAt(state, a.at, r) : null;
    var chance = makeOdds(state, r, st);
    if (chance >= 1 || Util.rand(state) < chance) made(state, r, st, a.bankFeed);
    else {
      (r.fail || []).forEach(function (e) { makeGive(state, e[0], e[1], a.bankFeed); });
      if (typeof r.failMsg === "string") Util.msg(state, r.failMsg, "game");
    }
    if (a.left > 0 && --a.left === 0) {
      setAct(state, null);
      return false;
    }
    return true;
  }

  // Per tick: walk back to the station if needed, then one product per cycle (all at once when instant).
  function runMake(state) {
    var p = state.player;
    var a = p.act;
    var r = Util.has(Data.recipes, a.rid) ? Data.recipes[a.rid] : null;
    if (!r) return setAct(state, null);
    if (a.at) {
      var st = stationAt(state, a.at, r);
      if (!st) return stop(state, "the fire went out");
      if (approach(state, a, st.x, st.y, st.o.def.from, r.ticks)) return;
      p.face = Util.dirIndex(st.x - p.x, st.y - p.y);
    }
    p.anim = makeAnim(r);
    if (state.tick < a.next) return;
    for (var guard = 0; guard < 1000 && makeOne(state, a, r) && r.ticks <= 0; guard++) { /* instant: the whole count */ }
    if (p.act === a) a.next = state.tick + Math.max(1, r.ticks);
  }

  // Arrival handlers by op kind, run on the arrival tick (section 10.2). t = resolve() target, f = findOp(),
  // a = the finished goto.
  var ARRIVE = {
    gather: function (state, t, f) { startGather(state, t, f.def); },
    attack: function (state, t) { Combat.startFight(state, t.npc); },
    pass: function (state, t) { passGate(state, t); },
    bank: function (state) { setIface(state, { t: "bank" }); },
    shop: function (state, t, f) { if (Util.has(Data.shops, f.def.shop)) setIface(state, { t: "shop", id: f.def.shop }); },
    talk: function (state, t, f) { Script.startDialogue(state, f.def.dialogue, t.npc ? t.npc.uid : 0); },
    make: function (state, t, f) { Script.openMake(state, f.def.station, t.t === "obj" ? t.ref : null); },
    script: function (state, t, f) { Script.apply(state, f.def.do); },
    take: function (state, t) { takeGround(state, t.g); },
    loot: function (state) { lootGrave(state); },
    use: function (state, t, f, a) { useArrive(state, t, a.arg); },
    climb: function (state, t) {
      var to = t.o.to;
      if (to && World.inBounds(to[0], to[1], to[2])) Player.teleport(state, to[0], to[1], to[2]);
    }
  };

  function arrive(state, t, f, a) {
    var p = state.player;
    if (t.t !== "ground" && t.t !== "grave") p.face = Util.dirIndex(t.x - p.x, t.y - p.y);
    if (Util.has(ARRIVE, f.kind)) ARRIVE[f.kind](state, t, f, a);
  }

  function runWalk(state) {
    if (!state.player.path.length) setAct(state, null);
  }

  function runGoto(state) {
    var p = state.player;
    var a = p.act;
    var t = resolve(state, a.ref);
    if (!t) {
      setAct(state, null);
      p.path = [];
      return;
    }
    if (p.path.length) return;
    if (!reached(state, t)) {
      var path = pathTo(state, t);
      if (path) p.path = path;
      else {
        Util.msg(state, REACH, "warn");
        setAct(state, null);
      }
      return;
    }
    var f = findOp(state, t, a.op);
    setAct(state, null);
    if (!f) return;
    if (f.fail !== null) Util.msg(state, f.fail, "game");
    else arrive(state, t, f, a);
  }

  // Per-tick action bodies by act.k, after movement (sections 10.2 to 10.6).
  var RUN = {
    walk: runWalk,
    goto: runGoto,
    gather: runGather,
    make: runMake,
    fight: function (state) { Combat.runFight(state); }
  };

  function runAction(state) {
    var a = state.player.act;
    if (a && Util.has(RUN, a.k)) RUN[a.k](state);
  }

  // Step 4: timers -1 -> autoEat -> emergency -> cast -> movement -> action.
  function playerPhase(state) {
    var p = state.player;
    if (p.atkTimer > 0) p.atkTimer--;
    if (p.eatTimer > 0) p.eatTimer--;
    Combat.autoEat(state);
    if (Combat.emergency(state)) return;
    if (p.act && p.act.k === "cast") runCast(state);
    if (p.act && (p.act.k === "goto" || p.act.k === "fight")) chase(state);
    move(state);
    runAction(state);
    Combat.petPhase(state);
  }

  // +1 hp every HP_REGEN_TICKS; Second wind shortens the gap (100 ticks / (1 + v), rounded).
  function regen(state) {
    var p = state.player;
    var v = Player.perkVal(p, "hitpoints", "regen");
    var every = v > 0 ? Math.max(1, Math.round(Rules.HP_REGEN_TICKS / (1 + v))) : Rules.HP_REGEN_TICKS;
    if (state.tick % every === 0 && p.hp > 0 && p.hp < Player.maxHp(p)) p.hp++;
  }

  // Rested (10.14): each tick spent gathering, making or fighting uses one tick of the pool; the last one says so.
  function restTick(state) {
    var p = state.player;
    var a = p.act;
    if (!(p.rested > 0) || !a || (a.k !== "gather" && a.k !== "make" && a.k !== "fight")) return;
    p.rested--;
    if (p.rested === 0) Util.msg(state, "You no longer feel rested.", "game");
  }

  // ----------------------------------------------------------------
  // ---------------------------- Seasons ---------------------------
  // ----------------------------------------------------------------

  // The Data.seasons entry for state.tick, or null when the data has none (nothing is saved).
  function season(state) {
    var list = Array.isArray(Data.seasons) ? Data.seasons : [];
    var s = list[Rules.seasonIndex(state.tick)];
    return s && typeof s === "object" ? s : null;
  }

  // The season's multiplier for a skill's "gather" chance or "xp"; 1 when it doesn't apply.
  function seasonMod(state, skill, key) {
    var s = season(state);
    var m = s && s.mod;
    return m && m.skill === skill && typeof m[key] === "number" && m[key] > 0 ? m[key] : 1;
  }

  // On the first tick of each season: a season event and its chat line.
  function seasonTurn(state) {
    var s = state.tick % Rules.SEASON_TICKS === 0 ? season(state) : null;
    if (!s) return;
    Util.emit(state, { type: "season", id: s.id });
    Util.msg(state, s.name + " arrives. " + s.effect, "game");
  }

  // ----------------------------------------------------------------
  // ----------------------------- Tick -----------------------------
  // ----------------------------------------------------------------

  // Section 10.1, in order.
  function tick(state) {
    var p = state.player;
    state.tick++;
    seasonTurn(state);
    snapshot(state);
    timers(state);
    Combat.npcPhase(state);
    if (p.hp > 0) {
      playerPhase(state);
      restTick(state);
      regen(state);
      Script.checkTriggers(state);
    }
    if (p.hp <= 0) Combat.playerDeath(state);
  }

  // ----------------------------------------------------------------
  // -------------------------- Status text -------------------------
  // ----------------------------------------------------------------

  function gatherDoing(state, a) {
    var o = objectAt(state, state.player.map, a.ax, a.ay);
    var name = Util.has(Data.objects, a.base) ? Data.objects[a.base].name : o ? o.name : "";
    var skill = null;
    var ops = a.group && World.FISH[a.group] ? Data.objects[World.FISH[a.group].obj].ops
      : Util.has(Data.objects, a.base) ? Data.objects[a.base].ops : [];
    for (var i = 0; i < (ops || []).length; i++) if (ops[i].id === a.op) skill = ops[i].skill || null;
    var text = a.wait ? "Waiting for " + name + "…" : skill === "fishing" ? "Fishing"
      : skill === "mining" ? "Mining " + name : "Chopping " + name;
    return { text: text, dot: "work", skill: skill, left: null };
  }

  function fightDoing(state, a) {
    var d = npcDef(a.npc);
    var n = a.uid >= 1 ? state.npcs[a.uid - 1] : null;
    var name = d ? d.name : "";
    if (!alive(n)) return { text: "Waiting for " + name + "…", dot: "fight", skill: null, left: null };
    return { text: "Fighting " + name, dot: "fight", skill: null, left: null };
  }

  // "Making {Item}"; a recipe with no product (light, burn) shows its own name ("Burn logs").
  function makeDoing(a) {
    var r = Util.has(Data.recipes, a.rid) ? Data.recipes[a.rid] : null;
    var made = !!r && Array.isArray(r.out) && r.out.length > 0;
    var name = r ? (made ? "Making " : "") + recipeName(r) : "Making";
    var left = a.left > 0 ? a.left : null;
    // The count only helps for several products: a single fire reads "Light logs", not "(1 left)".
    return { text: name + (a.bankFeed ? " [bank-fed]" : "") + (left > 1 ? " (" + Util.fmtInt(left) + " left)" : ""), dot: "work",
      skill: r ? r.skill : null, left: left };
  }

  function recipeName(r) {
    if (typeof r.name === "string") return r.name;
    var src = r.out && r.out.length ? r.out : r.in || [];
    return src.length && itemDef(src[0][0]) ? itemDef(src[0][0]).name : "";
  }

  // status.doing (section 10.11 doing texts).
  function doing(state) {
    var p = state.player;
    var a = p.act;
    if (p.hp <= 0) return { text: "Idle", dot: "dead", skill: null, left: null };
    if (!a) return { text: "Idle", dot: p.stop ? "stop" : "idle", skill: null, left: null };
    if (a.k === "walk" || a.k === "goto") return { text: "Walking", dot: "walk", skill: null, left: null };
    if (a.k === "cast") return { text: "Recalling…", dot: "work", skill: null, left: null };
    if (a.k === "gather") return gatherDoing(state, a);
    if (a.k === "fight") return fightDoing(state, a);
    if (a.k === "make") return makeDoing(a);
    return { text: "Idle", dot: "idle", skill: null, left: null };
  }

  // ----------------------------------------------------------------
  // --------------------------- Catch-up ---------------------------
  // ----------------------------------------------------------------

  // inv + eq + bank counts per item id.
  function holdings(state) {
    var p = state.player;
    var out = {};
    function put(id, n) { out[id] = (Util.has(out, id) ? out[id] : 0) + n; }
    for (var i = 0; i < p.inv.length; i++) if (p.inv[i]) put(p.inv[i].id, p.inv[i].qty);
    for (var k = 0; k < Rules.EQUIP_SLOTS.length; k++) if (p.eq[Rules.EQUIP_SLOTS[k]]) put(p.eq[Rules.EQUIP_SLOTS[k]], 1);
    for (var b = 0; b < p.bank.length; b++) put(p.bank[b].id, p.bank[b].qty);
    return out;
  }

  function hidden(o, k, v) {
    Object.defineProperty(o, k, { value: v, writable: true, enumerable: false, configurable: true });
  }

  // Transient states the away headline looks past: walking there, waiting for a node or a respawn.
  function passing(state) {
    var a = state.player.act;
    if (!a) return false;
    if (a.k === "walk" || a.k === "goto") return true;
    if (a.k === "gather") return !!a.wait;
    return a.k === "fight" && !(a.uid > 0 && alive(state.npcs[a.uid - 1]));
  }

  // doing = the status text at the start, or (when that is passing) the first activity after it.
  function newSummary(state) {
    var s = { ticks: 0, frozen: false, capped: false, doing: doing(state).text, xp: {}, levels: {}, items: {},
      couriered: {}, dropped: {}, kills: {}, eaten: {}, recalls: 0, quests: [], stages: [], notes: [], stop: null,
      stopAt: 0 };
    var lv = {};
    for (var i = 0; i < Rules.SKILLS.length; i++) lv[Rules.SKILLS[i]] = Player.level(state.player, Rules.SKILLS[i]);
    hidden(s, "_items0", holdings(state));
    hidden(s, "_lv0", lv);
    hidden(s, "_pending", passing(state));
    return s;
  }

  function bump(o, k, n) { o[k] = (Util.has(o, k) ? o[k] : 0) + n; }

  function fold(state, s, evs) {
    for (var i = 0; i < evs.length; i++) {
      var e = evs[i];
      if (e.type === "xp") s.xp[e.skill] = Math.round(((Util.has(s.xp, e.skill) ? s.xp[e.skill] : 0) + e.amt) * 10) / 10;
      else if (e.type === "level") s.levels[e.skill] = [s._lv0 && Util.has(s._lv0, e.skill) ? s._lv0[e.skill] : e.lvl - 1, e.lvl];
      else if (e.type === "death" && e.on > 0 && state.npcs[e.on - 1]) bump(s.kills, state.npcs[e.on - 1].id, 1);
      else if (e.type === "eat") bump(s.eaten, e.id, 1);
      else if (e.type === "recall") s.recalls++;
      else if (e.type === "questDone") s.quests.push(e.id);
      else if (e.type === "quest") s.stages.push([e.id, e.stage]);
      else if (e.type === "msg" && e.c === "quest" && s.notes.length < 8) s.notes.push(e.text);
      else if (e.type === "pet" && s.notes.length < 8 && Data.pets && Util.has(Data.pets, e.id)) {
        s.notes.push("Pet: " + Data.pets[e.id].name + "! It has taken a shine to you.");
      }
      else if (e.type === "stop") {
        s.stop = e.why;
        s.stopAt = s.ticks + 1;
      }
      else if (e.type === "full") {
        for (var k = 0; k < e.items.length; k++) bump(e.mode === "courier" ? s.couriered : s.dropped, e.items[k][0], e.items[k][1]);
      }
    }
  }

  function finishSummary(state, s) {
    var now = holdings(state);
    var start = s._items0 || {};
    var items = {};
    var ids = Object.keys(start).concat(Object.keys(now));
    for (var i = 0; i < ids.length; i++) {
      var d = (Util.has(now, ids[i]) ? now[ids[i]] : 0) - (Util.has(start, ids[i]) ? start[ids[i]] : 0);
      if (d) items[ids[i]] = d;
    }
    s.items = items;
  }

  // Frozen before a tick: inside a freeze region, or fighting a boss.
  function frozen(state) {
    var p = state.player;
    if (inFreeze(state)) return true;
    var n = p.foe > 0 ? state.npcs[p.foe - 1] : null;
    var d = n ? npcDef(n.id) : null;
    return !!(d && d.combat && d.combat.boss);
  }

  // A Summary passed back in keeps folding; a partial one gets its missing fields.
  function summaryOf(state, sum) {
    if (sum && typeof sum === "object" && sum._items0 && sum._lv0 && sum.xp && sum.levels) return sum;
    var s = newSummary(state);
    if (!sum || typeof sum !== "object") return s;
    var own = Util.has(sum, "doing");
    Object.keys(s).forEach(function (k) { if (!Util.has(sum, k)) sum[k] = s[k]; });
    if (!sum._items0) hidden(sum, "_items0", s._items0);
    if (!sum._lv0) hidden(sum, "_lv0", s._lv0);
    if (sum._pending === undefined) hidden(sum, "_pending", !own && s._pending);
    return sum;
  }

  // Runs up to n ticks with away set, folding each tick's events into the Summary.
  function catchUp(state, n, sum) {
    var s = summaryOf(state, sum);
    var count = Util.int(n, 0, 1000000, 0);
    state.away = true;
    for (var i = 0; i < count; i++) {
      if (frozen(state)) {
        s.frozen = true;
        break;
      }
      tick(state);
      var evs = state.events;
      state.events = [];
      fold(state, s, evs);
      s.ticks++;
      if (s._pending && !passing(state)) {
        if (state.player.act) s.doing = doing(state).text;
        s._pending = false;
      }
    }
    state.away = false;
    finishSummary(state, s);
    return s;
  }

  return {
    createState: createState, blank: blank, settle: settle, objectAt: objectAt, setObj: setObj, tick: tick,
    catchUp: catchUp, objOps: objOps, alive: alive, resolve: resolve, findOp: findOp, examineText: examineText,
    setIface: setIface, setAct: setAct, beginWorld: beginWorld, walkTo: walkTo, worldOp: worldOp, recall: recall,
    doing: doing, recipeName: recipeName, afkDefaults: afkDefaults, respawnPos: respawnPos, inFreeze: inFreeze,
    canUseOn: canUseOn, stop: stop, courier: courier, startMake: startMake, season: season, seasonMod: seasonMod,
    makeCheck: makeCheck, makeCount: makeCount, bankMakeAllowed: bankMakeAllowed
  };
})();
// ==== src/engine/save.js ====
// ----------------------------------------------------------------
// --------------- Save: serialize, deserialize, check ------------
// ----------------------------------------------------------------
// The SaveGame format and its loader (DESIGN.md section 6). deserialize never throws and never advances
// state.rng; each field falls back on its own. check() lists invariant violations (I9).
const Save = (function () {
  "use strict";

  var VERSION = 1;
  var MIGRATIONS = {};
  var QTY_MAX = 2147483647;
  var TICK_MAX = 4503599627370495;   // 2^52 - 1: far past any real run, exact in JSON
  var LIFE_MAX = 100000;
  var GRAVE_MAX = 128;
  var FULL_MODES = ["stop", "drop", "courier"];
  var CMB_MODES = ["stop", "courier"];
  var EAT_VALUES = [0, 30, 50, 70];

  function item(id) { return Util.has(Data.items, id) ? Data.items[id] : null; }
  function isStack(id) { return !!item(id) && item(id).stack === true; }
  function questIds() { return Object.keys(Data.quests || {}); }
  function flagList() { return Array.isArray(Data.flags) ? Data.flags : []; }

  // ----------------------------------------------------------------
  // --------------------------- Serialize --------------------------
  // ----------------------------------------------------------------

  function xpOut(p) {
    var out = {};
    for (var i = 0; i < Rules.SKILLS.length; i++) {
      var k = Rules.SKILLS[i];
      if (Util.has(p.xp10, k) && p.xp10[k] > 0) out[k] = p.xp10[k];
    }
    return out;
  }

  function eqOut(p) {
    var out = {};
    for (var i = 0; i < Rules.EQUIP_SLOTS.length; i++) {
      var s = Rules.EQUIP_SLOTS[i];
      if (p.eq[s]) out[s] = p.eq[s];
    }
    return out;
  }

  // { petId: pet XP } in Data.pets order, every owned pet (a new pet has 0 XP).
  function petsOut(p) {
    var out = {};
    petIds().forEach(function (id) { if (Util.has(p.pets, id)) out[id] = p.pets[id]; });
    return out;
  }

  function petIds() { return Object.keys(Data.pets || {}); }

  var LOG_KEYS = ["dmg", "kills", "best", "kc", "out"];

  // { petId: [dmg, kills, best, kc, out] } for owned pets with records, in Data.pets order.
  function petLogOut(p) {
    var out = {};
    petIds().forEach(function (id) {
      if (Util.has(p.pets, id) && p.petLog && Util.has(p.petLog, id)) {
        out[id] = LOG_KEYS.map(function (k) { return p.petLog[id][k]; });
      }
    });
    return out;
  }

  // { perkId: rank } in Data.perks order, ranks > 0 only.
  function perksOut(p) {
    var out = {};
    Rules.SKILLS.forEach(function (k) {
      Player.perkList(k).forEach(function (d) { if (Player.perkRank(p, d.id) > 0) out[d.id] = p.perks[d.id]; });
    });
    return out;
  }

  // Positive values of src in the order of keys.
  function positive(src, keys) {
    var out = {};
    for (var i = 0; i < keys.length; i++) if (Util.has(src, keys[i]) && src[keys[i]] > 0) out[keys[i]] = src[keys[i]];
    return out;
  }

  function shopsOut(state) {
    var out = [];
    var ids = Object.keys(Data.shops || {});
    for (var i = 0; i < ids.length; i++) {
      var cur = state.shops[ids[i]] || {};
      var stock = Data.shops[ids[i]].stock || [];
      var seen = {};
      for (var k = 0; k < stock.length; k++) {
        var id = stock[k][0];
        if (Util.has(seen, id) || !Util.has(cur, id)) continue;
        seen[id] = 1;
        if (cur[id] < baseStock(ids[i], id)) out.push([ids[i], id, cur[id]]);
      }
    }
    return out;
  }

  // The act as saved; null when a reload would not restore it, so round trips stay exact. A retaliation
  // fight (auto false) saves the activity it interrupted instead, or nothing: self-defence must not come
  // back as an auto fight that farms the attacker.
  function actOut(state) {
    var p = state.player;
    var a = p.act && p.act.k === "fight" && !p.act.auto ? p.resume : p.act;
    var arr = null;
    if (!a) return null;
    if (a.k === "gather") {
      var r = Util.parseRef(a.ref);
      arr = !r ? null : a.group ? ["fish", a.group, a.op, a.ax, a.ay] : ["gather", r.x, r.y, a.op, a.ax, a.ay];
    } else if (a.k === "fight") {
      arr = ["fight", a.npc, a.ax, a.ay];
    } else if (a.k === "make") {
      if (a.bankFeed) return null;   // Bank-fed jobs run only in the open game, never after closing.
      var at = a.at ? Util.parseRef(a.at) : null;
      arr = ["make", a.rid, a.left, at ? at.x : -1, at ? at.y : -1];
    }
    return arr && restoreAct(state, arr) ? arr : null;
  }

  // A save inside a living breath boss's arena wakes at the region's graveAt (outside its door): NPCs are
  // rebuilt at spawn on load, so the boss would be back at full hp beside a player who kept their losses.
  // Written here, not on load, so serialize(deserialize(x)) == x still holds.
  function posOut(state) {
    var p = state.player;
    var r = World.regionAt(p.map, p.x, p.y);
    var ga = r && r.freeze && Array.isArray(r.graveAt) ? r.graveAt : null;
    if (!ga || !World.inBounds(ga[0], ga[1], ga[2])) return [p.map, p.x, p.y];
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      var d = Util.has(Data.npcs, n.id) ? Data.npcs[n.id] : null;
      var sp = d && d.combat && d.combat.special;
      if (sp && sp.arena === r.id && Sim.alive(n)) return [ga[0], ga[1], ga[2]];
    }
    return [p.map, p.x, p.y];
  }

  function serialize(state) {
    var p = state.player;
    var f = p.afk.full;
    var g = state.grave;
    var pos = posOut(state);
    var moved = pos[1] !== p.x || pos[2] !== p.y || pos[0] !== p.map;
    return {
      v: VERSION, tick: state.tick, rng: state.rng >>> 0, gid: state.gid, pos: pos, hp: p.hp,
      run: p.run ? 1 : 0, bn: p.bankNote ? 1 : 0, sty: p.style, rc: p.recallAt, nm: p.name,
      lk: Rules.LOOK_KEYS.map(function (k) { return p.look[k]; }),
      afk: [p.afk.cont ? 1 : 0, p.afk.ret ? 1 : 0, p.afk.loot ? 1 : 0, p.afk.eat, f.woodcutting, f.mining, f.fishing,
        f.combat],
      xp: xpOut(p),
      pk: perksOut(p), rs: p.rested,
      pt: petsOut(p), pa: p.pet, pr: petLogOut(p),
      inv: p.inv.map(function (s) { return s ? noteOut([s.id, s.qty], s) : 0; }),
      eq: eqOut(p),
      bank: p.bank.map(function (b) { return [b.id, b.qty]; }),
      q: positive(p.quests, questIds()),
      qc: positive(p.qc, questIds()),
      fl: flagList().filter(function (k) { return Util.has(p.flags, k) && p.flags[k] === 1; }),
      kc: positive(p.kc, Object.keys(Data.npcs || {})),
      act: moved ? null : actOut(state),
      objs: Object.keys(state.objs).map(function (k) {
        var c = k.lastIndexOf(":");
        var xy = k.slice(c + 1).split(",");
        return [k.slice(0, c), +xy[0], +xy[1], state.objs[k].o, state.objs[k].until];
      }),
      gr: state.ground.map(function (e) { return noteOut([e.map, e.x, e.y, e.id, e.qty, e.until], e); }),
      grave: g ? [g.map, g.x, g.y, g.until, g.items.map(function (s) { return noteOut([s.id, s.qty], s); })] : null,
      dead: state.npcs.filter(function (n) { return n.deadUntil > state.tick; })
        .map(function (n) { return [n.id, n.uid, n.deadUntil - state.tick]; }),
      sh: shopsOut(state)
    };
  }

  // ----------------------------------------------------------------
  // ------------------------ Shared lookups ------------------------
  // ----------------------------------------------------------------

  function renamed(kind, id) {
    if (typeof id !== "string") return null;
    var r = Data.renames && Data.renames[kind];
    return r && Util.has(r, id) && typeof r[id] === "string" ? r[id] : id;
  }

  function itemId(id) { var k = renamed("items", id); return k && item(k) ? k : null; }
  function objId(id) { var k = renamed("objs", id); return k && Util.has(Data.objects, k) ? k : null; }
  function npcId(id) { var k = renamed("npcs", id); return k && Util.has(Data.npcs, k) ? k : null; }

  function baseStock(shop, id) {
    var stock = Util.has(Data.shops, shop) && Array.isArray(Data.shops[shop].stock) ? Data.shops[shop].stock : [];
    for (var i = 0; i < stock.length; i++) if (stock[i][0] === id) return stock[i][1];
    return 0;
  }

  // The gather op `op` of object id, or null.
  function gatherOp(id, op) {
    var ops = Util.has(Data.objects, id) && Array.isArray(Data.objects[id].ops) ? Data.objects[id].ops : [];
    for (var i = 0; i < ops.length; i++) if (ops[i].id === op && ops[i].kind === "gather") return ops[i];
    return null;
  }

  function fightable(id) {
    var d = Util.has(Data.npcs, id) ? Data.npcs[id] : null;
    return !!(d && d.combat && !d.combat.boss);
  }

  function isInt(v) { return typeof v === "number" && Math.floor(v) === v; }

  // Counters past max are junk (not clamped), so a loaded value can always keep counting and round-trip.
  function upTo(v, max, dflt) {
    return typeof v === "number" && v <= max ? Util.int(v, dflt, max, dflt) : dflt;
  }

  // ----------------------------------------------------------------
  // ------------------------ Load: the player ----------------------
  // ----------------------------------------------------------------

  function loadSettings(s, o) {
    var p = s.player;
    p.run = o.run === 0 ? false : true;
    p.bankNote = o.bn === 1;
    p.style = Rules.STYLES.some(function (st) { return st.id === o.sty; }) ? o.sty : "accurate";
    p.name = Rules.cleanName(o.nm);
    var lk = {};
    if (Array.isArray(o.lk)) Rules.LOOK_KEYS.forEach(function (k, i) { lk[k] = o.lk[i]; });
    p.look = Rules.cleanLook(lk);
    p.recallAt = Util.int(o.rc, 0, s.tick + Rules.RECALL_CD, 0);
    p.rested = Util.int(o.rs, 0, Rules.RESTED_MAX, 0);
    var a = Array.isArray(o.afk) ? o.afk : [];
    var d = Sim.afkDefaults();
    p.afk = {
      cont: a[0] === 0 ? false : a[0] === 1 ? true : d.cont,
      ret: a[1] === 0 ? false : a[1] === 1 ? true : d.ret,
      loot: a[2] === 0 ? false : a[2] === 1 ? true : d.loot,
      eat: EAT_VALUES.indexOf(a[3]) >= 0 ? a[3] : d.eat,
      full: {
        woodcutting: FULL_MODES.indexOf(a[4]) >= 0 ? a[4] : d.full.woodcutting,
        mining: FULL_MODES.indexOf(a[5]) >= 0 ? a[5] : d.full.mining,
        fishing: FULL_MODES.indexOf(a[6]) >= 0 ? a[6] : d.full.fishing,
        combat: CMB_MODES.indexOf(a[7]) >= 0 ? a[7] : d.full.combat
      }
    };
  }

  function loadXp(p, xp) {
    if (!xp || typeof xp !== "object") return;
    for (var i = 0; i < Rules.SKILLS.length; i++) {
      var k = Rules.SKILLS[i];
      p.xp10[k] = Util.has(xp, k) ? Util.int(xp[k], 0, Rules.MAX_XP10, 0) : 0;
    }
  }

  // Known perk ids only, ranks clamped to 0..max. A skill holding more ranks than its levels earn (a
  // hand-edited save) loses them from its last perk back.
  function loadPerks(p, pk) {
    if (!pk || typeof pk !== "object") return;
    Rules.SKILLS.forEach(function (k) {
      var list = Player.perkList(k);
      list.forEach(function (d) {
        var r = Util.has(pk, d.id) ? Util.int(pk[d.id], 0, Util.int(d.max, 0, 99, 0), 0) : 0;
        if (r > 0) p.perks[d.id] = r;
      });
      var over = Player.perkSpent(p, k) - Player.perkPoints(p, k);
      for (var i = list.length - 1; i >= 0 && over > 0; i--) {
        var cut = Math.min(Player.perkRank(p, list[i].id), over);
        if (!cut) continue;
        over -= cut;
        if (Player.perkRank(p, list[i].id) > cut) p.perks[list[i].id] -= cut;
        else delete p.perks[list[i].id];
      }
    });
  }

  // Known pet ids with XP clamped to 0..PET_XP_MAX; the summoned pet must be owned, else none.
  function loadPets(p, pt, pa) {
    var o = pt && typeof pt === "object" && !Array.isArray(pt) ? pt : {};
    petIds().forEach(function (id) {
      if (Util.has(o, id)) p.pets[id] = Util.int(o[id], 0, Rules.PET_XP_MAX, 0);
    });
    p.pet = typeof pa === "string" && Util.has(p.pets, pa) ? pa : null;
  }

  // Records of owned pets only, each count clamped to 0..QTY_MAX.
  function loadPetLog(p, pr) {
    var o = pr && typeof pr === "object" && !Array.isArray(pr) ? pr : {};
    Object.keys(p.pets).forEach(function (id) {
      if (!Util.has(o, id) || !Array.isArray(o[id])) return;
      var rec = {};
      LOG_KEYS.forEach(function (k, i) { rec[k] = Util.int(o[id][i], 0, QTY_MAX, 0); });
      p.petLog[id] = rec;
    });
  }

  // Clamped to 0..100 and snapped down to a listed stage.
  function normStage(qid, v) {
    var n = Util.int(v, 0, 100, 0);
    var stages = [0, 100].concat(Array.isArray(Data.quests[qid].stages) ? Data.quests[qid].stages : []);
    var best = 0;
    for (var i = 0; i < stages.length; i++) if (stages[i] <= n && stages[i] > best) best = stages[i];
    return best;
  }

  function loadQuests(p, o) {
    var ids = questIds();
    for (var i = 0; i < ids.length; i++) {
      var q = ids[i];
      var st = o.q && Util.has(o.q, q) ? normStage(q, o.q[q]) : 0;
      if (st > 0) p.quests[q] = st;
      var c = o.qc && Util.has(o.qc, q) ? Util.int(o.qc[q], 0, QTY_MAX, 0) : 0;
      if (c > 0) p.qc[q] = c;
    }
    var fl = Array.isArray(o.fl) ? o.fl : [];
    flagList().forEach(function (f) { if (fl.indexOf(f) >= 0) p.flags[f] = 1; });
    var kc = o.kc && typeof o.kc === "object" ? o.kc : {};
    Object.keys(kc).forEach(function (k) {
      var id = npcId(k);
      var n = Util.int(kc[k], 0, QTY_MAX, 0);
      if (id && n > 0) p.kc[id] = Math.min(QTY_MAX, (Util.has(p.kc, id) ? p.kc[id] : 0) + n);
    });
  }

  function bankAdd(p, id, qty) {
    for (var i = 0; i < p.bank.length; i++) {
      if (p.bank[i].id !== id) continue;
      p.bank[i].qty = Math.min(QTY_MAX, p.bank[i].qty + qty);
      return;
    }
    if (p.bank.length < Rules.BANK_MAX) p.bank.push({ id: id, qty: qty });
  }

  // Into the pack as far as it fits (as a note when noted), the rest to the bank.
  function stash(p, id, qty, note) {
    var rest = qty - Player.add(p, id, qty, note);
    if (rest > 0) bankAdd(p, id, rest);
  }

  // A noted pack slot, ground pile or grave pile saves a trailing 1; older pages read the rest and split it.
  function noteOut(arr, e) {
    if (e.note) arr.push(1);
    return arr;
  }

  function slotOf(e) {
    if (!Array.isArray(e)) return null;
    var id = itemId(e[0]);
    if (!id) return null;
    var out = { id: id, qty: Util.int(e[1], 1, QTY_MAX, 1) };
    if (e[2] === 1 && Player.notable(id)) out.note = true;
    return out;
  }

  function loadBank(p, arr) {
    if (!Array.isArray(arr)) return;
    for (var i = 0; i < arr.length; i++) {
      var e = slotOf(arr[i]);
      if (e) bankAdd(p, e.id, e.qty);
    }
  }

  // Slots keep their index; split piles, duplicate stacks and slots past 28 go through stash().
  function loadInv(p, arr) {
    if (!Array.isArray(arr)) return;
    var pending = [];
    for (var i = 0; i < arr.length; i++) {
      var e = slotOf(arr[i]);
      if (!e) continue;
      if (i >= Rules.INV_SIZE) {
        pending.push(e);
      } else if (e.note) {
        if (Player.noteSlot(p, e.id) >= 0) pending.push(e);
        else p.inv[i] = e;
      } else if (isStack(e.id)) {
        if (Player.count(p, e.id) > 0) pending.push(e);
        else p.inv[i] = e;
      } else {
        p.inv[i] = { id: e.id, qty: 1 };
        if (e.qty > 1) pending.push({ id: e.id, qty: e.qty - 1 });
      }
    }
    for (var k = 0; k < pending.length; k++) stash(p, pending[k].id, pending[k].qty, pending[k].note);
  }

  function loadEq(p, eq) {
    if (!eq || typeof eq !== "object") return;
    for (var i = 0; i < Rules.EQUIP_SLOTS.length; i++) {
      var slot = Rules.EQUIP_SLOTS[i];
      var id = Util.has(eq, slot) ? itemId(eq[slot]) : null;
      if (!id) continue;
      var e = item(id).equip;
      if (e && e.slot === slot) p.eq[slot] = id;
      else stash(p, id, 1);
    }
    // a shield never loads beside a two-handed weapon
    if (p.eq.shield && Player.twoHanded(p.eq.weapon)) {
      stash(p, p.eq.shield, 1);
      p.eq.shield = null;
    }
  }

  function loadPos(s, pos) {
    var p = s.player;
    var at = Array.isArray(pos) && World.inBounds(pos[0], pos[1], pos[2]) && !World.blocked(s, pos[0], pos[1], pos[2])
      ? pos : Sim.respawnPos();
    p.map = at[0];
    p.x = p.px = p.mx = at[1];
    p.y = p.py = p.my = at[2];
  }

  // ----------------------------------------------------------------
  // ------------------------ Load: the world -----------------------
  // ----------------------------------------------------------------

  // Timers must satisfy tick < until <= tick + 100,000.
  function lifeOk(s, until) {
    return isInt(until) && until > s.tick && until <= s.tick + LIFE_MAX;
  }

  function loadObjs(s, arr) {
    if (!Array.isArray(arr)) return;
    for (var i = 0; i < arr.length; i++) {
      var e = arr[i];
      if (!Array.isArray(e) || !World.inBounds(e[0], e[1], e[2]) || !lifeOk(s, e[4])) continue;
      var id = objId(e[3]);
      if (id) Sim.setObj(s, e[0], e[1], e[2], id, e[4]);
    }
  }

  function loadGround(s, arr, gid) {
    var list = [];
    var src = Array.isArray(arr) ? arr : [];
    for (var i = 0; i < src.length; i++) {
      var e = src[i];
      if (!Array.isArray(e) || !World.inBounds(e[0], e[1], e[2]) || !lifeOk(s, e[5])) continue;
      var id = itemId(e[3]);
      if (!id) continue;
      var g = { gid: 0, map: e[0], x: e[1], y: e[2], id: id, qty: Util.int(e[4], 1, QTY_MAX, 1), until: e[5] };
      if (e[6] === 1 && Player.notable(id)) g.note = true;
      list.push(g);
    }
    if (list.length > Rules.GROUND_MAX) list = list.slice(list.length - Rules.GROUND_MAX);
    for (var k = 0; k < list.length; k++) list[k].gid = k + 1;
    s.ground = list;
    s.gid = Math.max(upTo(gid, TICK_MAX, 1), list.length + 1);
  }

  function loadGrave(s, g) {
    if (!Array.isArray(g) || !World.inBounds(g[0], g[1], g[2]) || !lifeOk(s, g[3]) || !Array.isArray(g[4])) return;
    var items = [];
    for (var i = 0; i < g[4].length; i++) {
      var e = slotOf(g[4][i]);
      if (!e) continue;
      var hit = items.filter(function (x) { return x.id === e.id && !!x.note === !!e.note; })[0];
      if (hit) hit.qty = Math.min(QTY_MAX, hit.qty + e.qty);
      else if (items.length < GRAVE_MAX) items.push(e);
    }
    if (items.length) s.grave = { map: g[0], x: g[1], y: g[2], until: g[3], items: items };
  }

  function loadDead(s, arr) {
    if (!Array.isArray(arr)) return;
    for (var i = 0; i < arr.length; i++) {
      var e = arr[i];
      if (!Array.isArray(e) || !isInt(e[1]) || e[1] < 1 || e[1] > s.npcs.length) continue;
      var n = s.npcs[e[1] - 1];
      if (n.id !== npcId(e[0]) || !isInt(e[2]) || e[2] < 1 || e[2] > LIFE_MAX) continue;
      n.hp = 0;
      n.deadUntil = s.tick + e[2];
    }
  }

  // A living NPC whose spawn tile is now blocked (a saved fire on it) waits like a respawn: it appears
  // once the tile frees up, so it is never inside a wall.
  function unblockNpcs(s) {
    for (var i = 0; i < s.npcs.length; i++) {
      var n = s.npcs[i];
      if (n.hp > 0 && World.blocked(s, n.map, n.x, n.y)) {
        n.hp = 0;
        n.deadUntil = s.tick + 1;
      }
    }
  }

  function loadShops(s, arr) {
    if (!Array.isArray(arr)) return;
    for (var i = 0; i < arr.length; i++) {
      var e = arr[i];
      if (!Array.isArray(e) || typeof e[0] !== "string" || !Util.has(s.shops, e[0])) continue;
      var id = itemId(e[1]);
      if (!id || !Util.has(s.shops[e[0]], id) || !isInt(e[2])) continue;
      if (e[2] >= 0 && e[2] < baseStock(e[0], id)) s.shops[e[0]][id] = e[2];
    }
  }

  // ----------------------------------------------------------------
  // ------------------------- Load: the act ------------------------
  // ----------------------------------------------------------------

  function anchor(map, v, w, dx, dy) {
    return World.inBounds(map, v, w) ? [v, w] : [dx, dy];
  }

  function gatherAct(s, a) {
    var p = s.player;
    var so = World.staticObj(p.map, a[1], a[2]);
    if (!so || !gatherOp(so.o, a[3])) return null;
    var cur = Sim.objectAt(s, p.map, a[1], a[2]);
    var an = anchor(p.map, a[4], a[5], a[1], a[2]);
    return { k: "gather", ref: Util.refObj(a[1], a[2]), op: a[3], base: so.o, group: null, ax: an[0], ay: an[1],
      next: s.tick + 1, wait: !cur || cur.id !== so.o, sub: null, subAt: 0 };
  }

  // Resumes on the active spot of the group nearest to the player.
  function fishAct(s, a) {
    var p = s.player;
    var g = typeof a[1] === "string" && Util.has(World.FISH, a[1]) ? World.FISH[a[1]] : null;
    if (!g || g.map !== p.map || !gatherOp(g.obj, a[2]) || !Util.has(s.fish, g.group)) return null;
    var best = null;
    var at = s.fish[g.group].at;
    for (var i = 0; i < at.length; i++) {
      var t = g.tiles[at[i]];
      if (!best || Util.dist(p.x, p.y, t[0], t[1]) < Util.dist(p.x, p.y, best[0], best[1])) best = t;
    }
    if (!best) return null;
    var an = anchor(p.map, a[3], a[4], best[0], best[1]);
    return { k: "gather", ref: Util.refObj(best[0], best[1]), op: a[2], base: g.obj, group: g.group, ax: an[0], ay: an[1],
      next: s.tick + 1, wait: false, sub: null, subAt: 0 };
  }

  function fightAct(s, a) {
    var p = s.player;
    var id = npcId(a[1]);
    if (!id || !fightable(id)) return null;
    var an = anchor(p.map, a[2], a[3], p.x, p.y);
    return { k: "fight", uid: 0, npc: id, ax: an[0], ay: an[1], auto: true };
  }

  // The station at (sx,sy) must offer a make op for one of the recipe's stations.
  function makeAct(s, a) {
    var p = s.player;
    var rid = typeof a[1] === "string" && Util.has(Data.recipes, a[1]) ? a[1] : null;
    var left = a[2] === -1 ? -1 : Util.int(a[2], 0, QTY_MAX, 0);
    if (!rid || left === 0) return null;
    if (a[3] === -1) return { k: "make", rid: rid, left: left, next: s.tick + 1, at: null, ax: p.x, ay: p.y };
    var o = Sim.objectAt(s, p.map, a[3], a[4]);
    var at = Data.recipes[rid].at || [];
    var ok = !!o && Sim.objOps(o).some(function (op) { return op.kind === "make" && at.indexOf(op.station) >= 0; });
    return ok ? { k: "make", rid: rid, left: left, next: s.tick + 1, at: Util.refObj(a[3], a[4]), ax: a[3], ay: a[4] } : null;
  }

  // A saved act as a restored Action, or null (shared with actOut).
  function restoreAct(s, a) {
    if (!Array.isArray(a)) return null;
    if (a[0] === "gather") return gatherAct(s, a);
    if (a[0] === "fish") return fishAct(s, a);
    if (a[0] === "fight") return fightAct(s, a);
    if (a[0] === "make") return makeAct(s, a);
    return null;
  }

  // ----------------------------------------------------------------
  // ------------------------- Deserialize --------------------------
  // ----------------------------------------------------------------

  function load(raw, seed) {
    var m = raw && typeof raw === "object" && !Array.isArray(raw) ? migrate(raw) : null;
    var o = m && typeof m === "object" && !Array.isArray(m) ? m : {};
    var rng = typeof o.rng === "number" && o.rng >>> 0 === o.rng ? o.rng : Number(seed) >>> 0;
    var s = Sim.blank(rng);
    var p = s.player;
    s.tick = upTo(o.tick, TICK_MAX, 0);
    loadSettings(s, o);
    loadXp(p, o.xp);
    loadPerks(p, o.pk);
    loadPets(p, o.pt, o.pa);
    loadPetLog(p, o.pr);
    loadQuests(p, o);
    loadBank(p, o.bank);
    loadInv(p, o.inv);
    loadEq(p, o.eq);
    loadObjs(s, o.objs);
    loadGround(s, o.gr, o.gid);
    loadGrave(s, o.grave);
    loadDead(s, o.dead);
    unblockNpcs(s);
    loadShops(s, o.sh);
    loadPos(s, o.pos);
    p.hp = Util.int(o.hp, 1, Player.maxHp(p), Player.maxHp(p));
    Sim.settle(s);
    p.act = restoreAct(s, o.act);
    return s;
  }

  // Never throws: a loader bug degrades to a fresh character rather than a dead page.
  function deserialize(obj, seed) {
    try {
      return load(obj, seed);
    } catch (e) {
      return Sim.createState(seed);
    }
  }

  // MIGRATIONS[v] maps a vN save to v(N+1).
  function migrate(obj, migrations, target) {
    var mig = migrations && typeof migrations === "object" ? migrations : MIGRATIONS;
    var tgt = typeof target === "number" ? target : VERSION;
    if (!obj || typeof obj !== "object") return obj;
    var v = Util.int(obj.v, 0, tgt, tgt);
    var cur = obj;
    while (v < tgt && Util.has(mig, v) && typeof mig[v] === "function") {
      var next = mig[v](cur);
      if (!next || typeof next !== "object") break;
      cur = next;
      v++;
      cur.v = v;
    }
    return cur;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Check -----------------------------
  // ----------------------------------------------------------------

  function noteOk(e) {
    return e.note === undefined || (e.note === true && Player.notable(e.id));
  }

  function slotOk(s) {
    return !!s && !!item(s.id) && isInt(s.qty) && s.qty >= 1 && s.qty <= QTY_MAX && noteOk(s) &&
      (s.note === true || isStack(s.id) || s.qty === 1);
  }

  function checkPlayer(state, out) {
    var p = state.player;
    if (!World.inBounds(p.map, p.x, p.y)) out.push("player off the map: " + p.map + " " + p.x + "," + p.y);
    else if (World.blocked(state, p.map, p.x, p.y)) out.push("player on a blocked tile: " + p.x + "," + p.y);
    var max = Player.maxHp(p);
    if (!isInt(p.hp) || p.hp < 1 || p.hp > max) out.push("hp " + p.hp + " outside 1.." + max);
    if (!Array.isArray(p.path)) out.push("path is not an array");
    if (!Rules.STYLES.some(function (st) { return st.id === p.style; })) out.push("bad style " + p.style);
    if (!isInt(p.rested) || p.rested < 0 || p.rested > Rules.RESTED_MAX) out.push("bad rested " + p.rested);
    if (typeof p.name !== "string" || (p.name !== "" && Rules.cleanName(p.name) !== p.name)) out.push("bad name");
    if (!p.look || JSON.stringify(Rules.cleanLook(p.look)) !== JSON.stringify(p.look)) out.push("bad look");
    Rules.SKILLS.forEach(function (k) {
      var v = p.xp10[k];
      if (!isInt(v) || v < 0 || v > Rules.MAX_XP10) out.push("bad xp10 " + k + "=" + v);
    });
    if (!Array.isArray(p.inv) || p.inv.length !== Rules.INV_SIZE) out.push("inventory is not 28 slots");
    else p.inv.forEach(function (s, i) { if (s !== null && !slotOk(s)) out.push("bad inv slot " + i); });
    Rules.EQUIP_SLOTS.forEach(function (k) {
      var id = p.eq[k];
      if (id === null) return;
      if (!item(id) || !item(id).equip || item(id).equip.slot !== k) out.push("bad equipment in " + k);
    });
    if (p.eq.shield && Player.twoHanded(p.eq.weapon)) out.push("a shield beside a two-handed weapon");
    checkBank(p, out);
    checkProgress(p, out);
    checkPerks(p, out);
    checkPets(p, out);
    checkAfk(p, out);
  }

  // Known pet ids with integer XP in 0..PET_XP_MAX; the summoned pet is null or owned.
  function checkPets(p, out) {
    if (!p.pets || typeof p.pets !== "object" || Array.isArray(p.pets)) return out.push("pets is not an object");
    Object.keys(p.pets).forEach(function (id) {
      var v = p.pets[id];
      if (petIds().indexOf(id) < 0 || !isInt(v) || v < 0 || v > Rules.PET_XP_MAX) out.push("bad pet " + id);
    });
    if (p.pet !== null && !Util.has(p.pets, p.pet)) out.push("summoned pet " + p.pet + " is not owned");
    if (!p.petLog || typeof p.petLog !== "object" || Array.isArray(p.petLog)) return out.push("petLog is not an object");
    Object.keys(p.petLog).forEach(function (id) {
      var r = p.petLog[id];
      if (!Util.has(p.pets, id) || !r || !LOG_KEYS.every(function (k) { return isInt(r[k]) && r[k] >= 0; })) {
        out.push("bad pet records " + id);
      }
    });
    if (!isInt(p.petTimer) || p.petTimer < 0) out.push("bad pet timer");
  }

  // Known ids at ranks 1..max, and no skill spending more points than its level earns.
  function checkPerks(p, out) {
    if (!p.perks || typeof p.perks !== "object" || Array.isArray(p.perks)) return out.push("perks is not an object");
    Object.keys(p.perks).forEach(function (id) {
      var f = Player.perkDef(id);
      var r = p.perks[id];
      if (!f || !isInt(r) || r < 1 || r > f.def.max) out.push("bad perk " + id);
    });
    Rules.SKILLS.forEach(function (k) {
      if (Player.perkSpent(p, k) > Player.perkPoints(p, k)) out.push("perks of " + k + " spend more points than earned");
    });
  }

  function checkBank(p, out) {
    if (!Array.isArray(p.bank) || p.bank.length > Rules.BANK_MAX) return out.push("bank is not a list of <= 200");
    var seen = {};
    p.bank.forEach(function (b, i) {
      if (!b || !item(b.id) || !isInt(b.qty) || b.qty < 1) out.push("bad bank entry " + i);
      else if (Util.has(seen, b.id)) out.push("duplicate bank entry " + b.id);
      else seen[b.id] = 1;
    });
  }

  function checkProgress(p, out) {
    Object.keys(p.quests).forEach(function (q) {
      if (!Util.has(Data.quests, q) || normStage(q, p.quests[q]) !== p.quests[q] || p.quests[q] <= 0) out.push("bad quest " + q);
    });
    Object.keys(p.qc).forEach(function (q) {
      if (!Util.has(Data.quests, q) || !isInt(p.qc[q]) || p.qc[q] < 1) out.push("bad quest counter " + q);
    });
    Object.keys(p.flags).forEach(function (f) {
      if (flagList().indexOf(f) < 0 || p.flags[f] !== 1) out.push("bad flag " + f);
    });
    Object.keys(p.kc).forEach(function (k) {
      if (!Util.has(Data.npcs, k) || !isInt(p.kc[k]) || p.kc[k] < 1) out.push("bad kill count " + k);
    });
  }

  function checkAfk(p, out) {
    var a = p.afk;
    if (!a || typeof a.cont !== "boolean" || typeof a.ret !== "boolean" || typeof a.loot !== "boolean" ||
      EAT_VALUES.indexOf(a.eat) < 0 || !a.full || FULL_MODES.indexOf(a.full.woodcutting) < 0 ||
      FULL_MODES.indexOf(a.full.mining) < 0 || FULL_MODES.indexOf(a.full.fishing) < 0 ||
      CMB_MODES.indexOf(a.full.combat) < 0) out.push("bad afk settings");
    var acts = ["walk", "goto", "gather", "fight", "make", "cast"];
    if (p.act !== null && (!p.act || acts.indexOf(p.act.k) < 0)) out.push("bad act");
    var ifaces = ["bank", "shop", "dialogue", "make"];
    if (p.iface !== null && (!p.iface || ifaces.indexOf(p.iface.t) < 0)) out.push("bad iface");
  }

  function checkNpcs(state, out) {
    if (state.npcs.length !== World.SPAWNS.length) return out.push("npc count differs from SPAWNS");
    state.npcs.forEach(function (n, i) {
      var sp = World.SPAWNS[i];
      if (n.uid !== i + 1 || n.id !== sp.id) return out.push("npc " + i + " does not match its spawn");
      var d = Data.npcs[n.id];
      var max = d.combat ? d.combat.hp : 1;
      if (!isInt(n.hp) || n.hp < 0 || n.hp > max) out.push("npc " + n.uid + " hp " + n.hp);
      if (!Sim.alive(n)) return;
      if (!World.inBounds(n.map, n.x, n.y)) out.push("npc " + n.uid + " off the map");
      else if (World.blocked(state, n.map, n.x, n.y)) out.push("npc " + n.uid + " on a blocked tile");
    });
  }

  function checkWorld(state, out) {
    Object.keys(state.objs).forEach(function (k) {
      var e = state.objs[k];
      var c = k.lastIndexOf(":");
      var xy = k.slice(c + 1).split(",");
      if (!World.inBounds(k.slice(0, c), +xy[0], +xy[1]) || !Util.has(Data.objects, e.o) || !(e.until > state.tick)) {
        out.push("bad object override " + k);
      }
    });
    if (!Array.isArray(state.ground) || state.ground.length > Rules.GROUND_MAX) out.push("too many ground items");
    var gids = {};
    (state.ground || []).forEach(function (g) {
      if (!item(g.id) || !isInt(g.qty) || g.qty < 1 || !(g.until > state.tick) || !World.inBounds(g.map, g.x, g.y) || !noteOk(g) ||
        !isInt(g.gid) || g.gid < 1 || g.gid >= state.gid || Util.has(gids, g.gid)) out.push("bad ground item " + g.gid);
      gids[g.gid] = 1;
    });
    var gr = state.grave;
    if (gr && (!World.inBounds(gr.map, gr.x, gr.y) || !(gr.until > state.tick) || !gr.items.length ||
      gr.items.length > GRAVE_MAX || !gr.items.every(function (s) { return item(s.id) && isInt(s.qty) && s.qty >= 1 && noteOk(s); }))) {
      out.push("bad grave");
    }
    Object.keys(Data.shops || {}).forEach(function (sh) {
      var cur = state.shops[sh] || {};
      Object.keys(cur).forEach(function (id) {
        if (!isInt(cur[id]) || cur[id] < 0 || cur[id] > baseStock(sh, id)) out.push("bad stock " + sh + "/" + id);
      });
    });
    Object.keys(World.FISH).forEach(function (g) {
      var f = state.fish[g];
      var n = World.FISH[g].tiles.length;
      if (!f || !Array.isArray(f.at) || f.at.some(function (c, i) { return !isInt(c) || c < 0 || c >= n || f.at.indexOf(c) !== i; })) {
        out.push("bad fishing group " + g);
      }
    });
  }

  function check(state) {
    var out = [];
    try {
      if (!state || state.v !== VERSION) return ["bad state version"];
      if (!isInt(state.tick) || state.tick < 0) out.push("bad tick");
      if (typeof state.rng !== "number" || state.rng >>> 0 !== state.rng) out.push("rng is not a uint32");
      if (!isInt(state.gid) || state.gid < 1) out.push("bad gid");
      if (!Array.isArray(state.events) || state.events.length > 500) out.push("bad event queue");
      checkPlayer(state, out);
      checkNpcs(state, out);
      checkWorld(state, out);
    } catch (e) {
      out.push("check threw: " + (e && e.message));
    }
    return out;
  }

  return {
    VERSION: VERSION, MIGRATIONS: MIGRATIONS, serialize: serialize, deserialize: deserialize, migrate: migrate,
    check: check
  };
})();
// ==== src/engine/engine.js ====
// ----------------------------------------------------------------
// ------------------- Engine: the public game API ----------------
// ----------------------------------------------------------------
// The only API UI, Input, Render-queries and Main call (DESIGN.md section 9 Engine). Commands validate
// everything, never throw and never advance time; a successful non-world command emits "save" (I19).
const Engine = (function () {
  "use strict";

  var NOTHING = "That doesn't do anything.";
  var QTY_MAX = 2147483647;
  var COUNT_LABELS = { 1: "1", 5: "5", 10: "10", 50: "50", "-1": "All", "-2": "All-but-1", x: "X" };

  function itemDef(id) { return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id] : null; }
  function itemName(id) { var d = itemDef(id); return d ? d.name : ""; }
  function isState(s) { return !!s && typeof s === "object" && !!s.player; }

  // A successful non-world command: cancels a recall cast (examine and value don't), clears the last
  // stop reason and asks Main to persist. A refused command leaves a cast running; world ops replace
  // the act themselves when they succeed.
  function finish(state, ok, keepCast) {
    if (!ok) return false;
    var p = state.player;
    if (!keepCast && p.act && p.act.k === "cast") Sim.setAct(state, null);
    p.stop = null;
    Util.emit(state, { type: "save" });
    return true;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Menus -----------------------------
  // ----------------------------------------------------------------

  function entry(label, target, kind, ref, op, arg, lvl) {
    var e = { label: label, target: target, kind: kind, ref: ref, op: op };
    if (arg !== undefined) e.arg = arg;
    if (lvl !== undefined) e.lvl = lvl;
    return e;
  }

  function npcLvl(npc) {
    var d = Data.npcs[npc.id];
    return d.combat ? d.combat.lvl : undefined;
  }

  // Name and menu kind of a resolved world target.
  function describe(t) {
    if (t.t === "npc") return { name: Data.npcs[t.npc.id].name, kind: "npc", lvl: npcLvl(t.npc) };
    if (t.t === "obj") return { name: t.o.name, kind: "obj" };
    if (t.t === "ground") return { name: itemName(t.g.id), kind: "item" };
    var gs = Util.has(Data.objects, "gravestone") ? Data.objects.gravestone.name : "";
    return { name: gs, kind: "obj" };
  }

  // Section 9 menuAt step 1 for one target.
  function entriesFor(state, t) {
    var d = describe(t);
    var out = [];
    if (t.t === "npc") {
      var def = Data.npcs[t.npc.id];
      if (def.combat) out.push(entry("Attack", d.name, "npc", t.ref, "attack", undefined, d.lvl));
      (def.ops || []).forEach(function (op) {
        if (Script.test(state, op.if)) out.push(entry(op.label, d.name, "npc", t.ref, op.id, undefined, d.lvl));
      });
    } else if (t.t === "obj") {
      Sim.objOps(t.o).forEach(function (op) {
        if (Script.test(state, op.if) || typeof op.fail === "string") out.push(entry(op.label, d.name, "obj", t.ref, op.id));
      });
    } else if (t.t === "ground") {
      out.push(entry("Take", d.name, "item", t.ref, "take"));
    } else {
      out.push(entry("Loot", d.name, "obj", t.ref, "loot"));
    }
    return out;
  }

  function targetsOf(state, refs) {
    var out = [];
    var seen = {};
    for (var i = 0; i < refs.length && i < 32; i++) {
      var t = Sim.resolve(state, refs[i]);
      if (!t || t.t === "tile" || Util.has(seen, t.ref)) continue;
      seen[t.ref] = 1;
      out.push(t);
    }
    return out;
  }

  // [0] is the left-click action. Use mode lists one Use per target, then Walk here.
  function menuAt(state, pick, opt) {
    if (!isState(state) || !pick || typeof pick !== "object") return [];
    var p = state.player;
    var o = opt && typeof opt === "object" ? opt : {};
    var targets = targetsOf(state, Array.isArray(pick.refs) ? pick.refs : []);
    var walk = World.inBounds(p.map, pick.x, pick.y)
      ? entry("Walk here", "", "none", Util.refTile(pick.x, pick.y), "walk") : null;
    var slot = o.useSlot;
    var used = slotItem(p, slot);
    var out = [];
    if (used) {
      targets.forEach(function (t) {
        if (t.t === "grave") return;   // graves only offer Loot and Examine
        var d = describe(t);
        out.push(entry("Use", itemName(used.id) + " -> " + d.name, d.kind, t.ref, "use", slot, d.lvl));
      });
      if (walk) out.push(walk);
      return out;
    }
    var atk = o.atk === 1 || o.atk === 2 ? o.atk : 0;
    var cmb = Player.combatLevel(p);
    var demoted = [];
    targets.forEach(function (t) {
      entriesFor(state, t).forEach(function (e) {
        var low = e.op === "attack" && (atk === 2 || (atk === 0 && e.lvl > cmb));
        (low ? demoted : out).push(e);
      });
    });
    if (walk) out.push(walk);
    out = out.concat(demoted);
    targets.forEach(function (t) {
      var d = describe(t);
      out.push(entry("Examine", d.name, d.kind, t.ref, "examine", undefined, d.lvl));
    });
    return out;
  }

  // ----------------------------------------------------------------
  // -------------------------- Item menus --------------------------
  // ----------------------------------------------------------------

  function counts(list, label, op, name, ref) {
    return list.map(function (n) { return entry(label + "-" + COUNT_LABELS[n], name, "item", ref, op, n); });
  }

  function invOptions(state, r, ref) {
    var p = state.player;
    var s = r.n < Rules.INV_SIZE ? p.inv[r.n] : null;
    var d = s ? itemDef(s.id) : null;
    if (!d) return [];
    var f = p.iface;
    if (f && f.t === "bank") return counts([1, 5, 10, "x", -1], "Deposit", "deposit", d.name, ref);
    if (f && f.t === "shop") {
      return [entry("Value", d.name, "item", ref, "value")].concat(counts([1, 5, 10, 50], "Sell", "sell", d.name, ref),
        [entry("Examine", d.name, "item", ref, "examine")]);
    }
    // A note only banks, sells and drops; Examine comes first so a stray click never drops the stack.
    if (s.note) return [entry("Examine", d.name, "item", ref, "examine"), entry("Drop", d.name, "item", ref, "drop")];
    var out = (d.iops || []).map(function (io) { return entry(io.label, d.name, "item", ref, io.id); });
    if (d.food) out.push(entry("Eat", d.name, "item", ref, "eat"));
    if (d.equip) {
      var wield = d.equip.slot === "weapon" || d.equip.slot === "shield";
      out.push(entry(wield ? "Wield" : "Wear", d.name, "item", ref, wield ? "wield" : "wear"));
    }
    out.push(entry("Use", d.name, "item", ref, "use"));
    if (d.cat !== "quest") out.push(entry("Drop", d.name, "item", ref, "drop"));
    out.push(entry("Examine", d.name, "item", ref, "examine"));
    return out;
  }

  // The item id behind an inv/equip/bank/shop ref, or null.
  function refItem(state, r) {
    var p = state.player;
    if (r.t === "inv") return r.n < Rules.INV_SIZE && p.inv[r.n] ? p.inv[r.n].id : null;
    if (r.t === "equip") return Util.has(p.eq, r.s) ? p.eq[r.s] : null;
    if (r.t === "bank") return r.n < p.bank.length ? p.bank[r.n].id : null;
    if (r.t === "shop") {
      var f = p.iface;
      var stock = f && f.t === "shop" && Util.has(Data.shops, f.id) ? Data.shops[f.id].stock : [];
      return r.n < stock.length && itemDef(stock[r.n][0]) ? stock[r.n][0] : null;
    }
    return null;
  }

  // Default first (section 9 options table).
  function options(state, ref, opt) {
    if (!isState(state)) return [];
    var r = Util.parseRef(ref);
    if (!r) return [];
    if (r.t === "inv") return invOptions(state, r, ref);
    if (r.t === "grave") {
      var t = Sim.resolve(state, ref);
      if (!t) return [];
      var d = describe(t);
      return [entry("Loot", d.name, "obj", ref, "loot"), entry("Examine", d.name, "obj", ref, "examine")];
    }
    var id = refItem(state, r);
    if (!id) return [];
    var name = itemName(id);
    var ex = entry("Examine", name, "item", ref, "examine");
    if (r.t === "equip") return [entry("Remove", name, "item", ref, "remove"), ex];
    if (r.t === "bank") return counts([1, 5, 10, "x", -1, -2], "Withdraw", "withdraw", name, ref).concat([ex]);
    if (r.t === "shop") return [entry("Value", name, "item", ref, "value")].concat(counts([1, 5, 10, 50], "Buy", "buy", name, ref), [ex]);
    return [];
  }

  // ----------------------------------------------------------------
  // --------------------------- Commands ---------------------------
  // ----------------------------------------------------------------

  // World refs: examine prints at once; any other op becomes a goto (no save: I19).
  function worldAct(state, ref, op, arg) {
    if (op === "examine") {
      var t = Sim.resolve(state, ref);
      if (!t || t.t === "tile") return false;
      Util.msg(state, Sim.examineText(t), "examine");
      return true;
    }
    return Sim.worldOp(state, ref, op, arg);
  }

  // ----------------------------------------------------------------
  // ------------------------- Item commands ------------------------
  // ----------------------------------------------------------------

  // A count argument: an int >= 1, -1 (all) or -2 (all but 1); anything else ("x" included) is null.
  function countArg(arg) {
    if (arg === -1 || arg === -2) return arg;
    return typeof arg === "number" && Math.floor(arg) === arg && arg >= 1 ? Math.min(arg, QTY_MAX) : null;
  }

  function ifaceIs(state, t) {
    var f = state.player.iface;
    return !!f && f.t === t;
  }

  function openShop(state) {
    var f = state.player.iface;
    return f && f.t === "shop" && Util.has(Data.shops, f.id) ? f.id : null;
  }

  // What the open shop pays for one id, or null after telling the player why not (section 10.10).
  function sellQuote(state, sid, id) {
    var shop = Data.shops[sid];
    if (!buys(shop, id)) {
      Util.msg(state, "They won't buy that.", "warn");
      return null;
    }
    var price = Rules.sellPrice(itemDef(id).value, shop.rate);
    if (price <= 0) {
      Util.msg(state, "They won't pay anything for that.", "warn");
      return null;
    }
    return price;
  }

  // Buys up to n, unit by unit; stops at stock, coins or space with a warn.
  function buy(state, i, arg) {
    var sid = openShop(state);
    var n = countArg(arg);
    var stock = sid ? Data.shops[sid].stock || [] : [];
    var row = i < stock.length ? stock[i] : null;
    var cur = sid ? state.shops[sid] : null;
    if (!row || n === null || !itemDef(row[0]) || !Util.has(cur, row[0])) return false;
    var p = state.player;
    var id = row[0];
    var price = Rules.buyPrice(itemDef(id).value, row[2]);
    var want = n === -1 ? cur[id] : n === -2 ? cur[id] - 1 : n;
    var bought = 0;
    var why = null;
    while (bought < want && !why) {
      if (cur[id] <= 0) why = "Sold out.";
      else if (Player.count(p, "coins") < price) why = "You can't afford that.";
      else {
        Player.remove(p, "coins", price);
        if (Player.add(p, id, 1) === 1) {
          cur[id]--;
          bought++;
        } else {
          Player.add(p, "coins", price);
          why = "Your pack is full.";
        }
      }
    }
    if (why) Util.msg(state, why, "warn");
    return bought > 0;
  }

  // Sells up to n of the slot's id (that slot first); sold items never enter stock.
  function sell(state, slot, arg) {
    var sid = openShop(state);
    var n = countArg(arg);
    var p = state.player;
    var s = p.inv[slot];
    var price = sid && s && n !== null ? sellQuote(state, sid, s.id) : null;
    if (price === null) return false;
    var id = s.id;
    var have = s.note ? s.qty : Player.count(p, id);
    var k = Math.min(n === -1 ? have : n === -2 ? have - 1 : n, Math.floor((QTY_MAX - Player.count(p, "coins")) / price));
    if (k <= 0) return false;
    var first = Player.removeAt(p, slot, Math.min(k, s.qty));
    var sold = first.qty + (first.qty < k && !s.note ? Player.remove(p, id, k - first.qty) : 0);
    var paid = Player.add(p, "coins", sold * price);
    if (paid === sold * price) return true;
    Player.remove(p, "coins", paid);   // no room for the coins: undo the sale
    Player.add(p, id, sold, s.note);
    Util.msg(state, "Your pack is full.", "warn");
    return false;
  }

  // Value: a shop row's price, or what the open shop pays for a pack item.
  function valueOf(state, r) {
    var sid = openShop(state);
    var id = r.t === "inv" || r.t === "shop" ? refItem(state, r) : null;
    if (!sid || !id) return false;
    var name = itemDef(id).name;
    if (r.t === "shop") {
      var row = Data.shops[sid].stock[r.n];
      Util.msg(state, name + " costs " + Util.fmtInt(Rules.buyPrice(itemDef(id).value, row[2])) + " coins.", "game");
      return true;
    }
    var price = sellQuote(state, sid, id);
    if (price !== null) Util.msg(state, name + ": they'll pay " + Util.fmtInt(price) + " coins.", "game");
    return price !== null;
  }

  var NOTE_EXAMINE = "Swap this note at any bank for the equivalent item.";
  var NOTE_OPS = ["drop", "deposit", "sell"];

  // Inventory ops by id (section 9 Op ids); none of them touches the act.
  var INV_OPS = {
    eat: function (state, n) { return Player.eat(state, n); },
    wield: function (state, n) { return Player.equip(state, n); },
    wear: function (state, n) { return Player.equip(state, n); },
    drop: function (state, n) { return Player.drop(state, n); },
    deposit: function (state, n, arg) {
      return ifaceIs(state, "bank") && countArg(arg) !== null && Player.deposit(state, n, countArg(arg));
    },
    sell: sell
  };

  // ----------------------------------------------------------------
  // ---------------------- Make sheets and use ---------------------
  // ----------------------------------------------------------------

  // iops and item-on-item uses replace the act, then show the make sheet (no station: made anywhere).
  // A single recipe with `place` starts at once (section 9 act(inv:N, iop)); if it can't, the sheet closes
  // again and the reason stays in chat.
  function makeSheet(state, rids) {
    Sim.beginWorld(state, null, []);
    Sim.setIface(state, { t: "make", station: null, at: null, rids: rids });
    if (rids.length === 1 && Data.recipes[rids[0]].place && !make(state, rids[0], 1)) Sim.setIface(state, null);
    return true;
  }

  function iopAct(state, id, op) {
    var list = Array.isArray(itemDef(id).iops) ? itemDef(id).iops : [];
    var io = list.filter(function (x) { return x && x.id === op; })[0];
    if (!io || !Array.isArray(io.rids)) return false;
    var rids = io.rids.filter(function (rid) {
      return typeof rid === "string" && Util.has(Data.recipes, rid) && Script.test(state, Data.recipes[rid].if);
    });
    return rids.length > 0 && makeSheet(state, rids);
  }

  // A recipe "uses" an item when it is an input, or a tool whose category the recipe needs.
  function usesItem(r, id) {
    var d = itemDef(id);
    if ((r.in || []).some(function (e) { return Array.isArray(e) && e[0] === id; })) return true;
    return !!(d && d.tool && (r.tools || []).indexOf(d.tool.cat) >= 0);
  }

  // Made-anywhere recipes that use both items (Use resolution step 3).
  function recipesFor(a, b) {
    if (a === b) return [];
    return Object.keys(Data.recipes || {}).filter(function (rid) {
      var r = Data.recipes[rid];
      return Array.isArray(r.at) && !r.at.length && usesItem(r, a) && usesItem(r, b);
    });
  }

  // The slot's item for Use; a note can't be used on anything.
  function slotItem(p, slot) {
    var s = typeof slot === "number" && Math.floor(slot) === slot && slot >= 0 && slot < Rules.INV_SIZE ? p.inv[slot] : null;
    return s && !s.note ? s : null;
  }

  function useOnItem(state, slot, other) {
    var p = state.player;
    var a = slotItem(p, slot);
    var b = other !== slot ? slotItem(p, other) : null;
    var rids = a && b ? recipesFor(a.id, b.id) : [];
    if (!rids.length) {
      if (a && b) Util.msg(state, NOTHING, "game");
      return false;
    }
    return makeSheet(state, rids);
  }

  // inv/equip/bank/shop refs.
  function itemAct(state, r, op, arg) {
    var id = refItem(state, r);
    if (!id) return false;
    var note = r.t === "inv" && !!state.player.inv[r.n].note;
    if (op === "examine") {
      Util.msg(state, note ? NOTE_EXAMINE : itemDef(id).examine, "examine");
      return finish(state, true, true);
    }
    if (op === "value") return finish(state, valueOf(state, r), true);
    if (note && NOTE_OPS.indexOf(op) < 0) return false;
    if (r.t === "inv") {
      if (Util.has(INV_OPS, op)) return finish(state, INV_OPS[op](state, r.n, arg));
      return finish(state, iopAct(state, id, op));
    }
    if (r.t === "equip" && op === "remove") return finish(state, Player.unequip(state, r.s));
    if (r.t === "bank" && op === "withdraw") {
      return finish(state, ifaceIs(state, "bank") && countArg(arg) !== null && Player.withdraw(state, r.n, countArg(arg)));
    }
    if (r.t === "shop" && op === "buy") return finish(state, buy(state, r.n, arg));
    return false;
  }

  function act(state, ref, op, arg) {
    if (!isState(state) || typeof op !== "string") return false;
    var r = Util.parseRef(ref);
    if (!r) return false;
    if (op === "use") return typeof arg === "number" ? useItemOn(state, arg, ref) : false;
    if (r.t === "tile") return op === "walk" && walkTo(state, r.x, r.y);
    if (r.t === "obj" || r.t === "npc" || r.t === "ground" || r.t === "grave") return worldAct(state, ref, op, arg);
    return itemAct(state, r, op, arg);
  }

  function walkTo(state, x, y) {
    if (!isState(state)) return false;
    return Sim.walkTo(state, x, y);
  }

  // Section 9 Use resolution. World targets walk there first (a world op: no save); item on item is instant.
  function useItemOn(state, slot, ref) {
    if (!isState(state) || !slotItem(state.player, slot)) return false;
    var r = Util.parseRef(ref);
    if (!r) return false;
    if (r.t === "inv") return finish(state, useOnItem(state, slot, r.n));
    if (r.t === "obj" || r.t === "npc" || r.t === "ground") return Sim.worldOp(state, ref, "use", slot);
    return false;
  }

  // The use-mode outline: true when using the slot on ref would do something.
  function canUse(state, slot, ref) {
    if (!isState(state)) return false;
    var a = slotItem(state.player, slot);
    var r = a ? Util.parseRef(ref) : null;
    if (!r) return false;
    if (r.t === "inv") {
      var b = r.n !== slot ? slotItem(state.player, r.n) : null;
      return !!b && recipesFor(a.id, b.id).length > 0;
    }
    return Sim.canUseOn(state, Sim.resolve(state, ref), a.id);
  }

  function moveItem(state, from, to) {
    if (!isState(state)) return false;
    return finish(state, Player.move(state.player, from, to));
  }

  // Section 10.4 Start: a recipe from the open make sheet; the sheet closes and the act is replaced.
  function make(state, rid, count) {
    if (!isState(state)) return false;
    return finish(state, Sim.startMake(state, rid, count));
  }

  function setMakeBankFeed(state, on) {
    if (!isState(state) || typeof on !== "boolean" || !ifaceIs(state, "make")) return false;
    state.player.iface.bankFeed = on;
    return true;
  }

  function dialogueContinue(state) {
    if (!isState(state)) return false;
    return finish(state, Script.next(state));
  }

  function dialogueChoose(state, i) {
    if (!isState(state)) return false;
    return finish(state, Script.choose(state, i));
  }

  function closeInterface(state) {
    if (isState(state)) Sim.setIface(state, null);
  }

  // The bank window's footer buttons: only while the bank is open.
  function depositAll(state) {
    if (!isState(state) || !ifaceIs(state, "bank")) return false;
    return finish(state, Player.depositAll(state));
  }

  function depositWorn(state) {
    if (!isState(state) || !ifaceIs(state, "bank")) return false;
    return finish(state, Player.depositWorn(state));
  }

  function setStyle(state, id) {
    if (!isState(state) || !Rules.STYLES.some(function (s) { return s.id === id; })) return false;
    state.player.style = id;
    return finish(state, true);
  }

  // Character creation (and later edits): a valid name is required; the first naming greets the player.
  function setLook(state, name, look) {
    var n = Rules.cleanName(name);
    if (!isState(state) || !n) return false;
    var first = !state.player.name;
    state.player.name = n;
    state.player.look = Rules.cleanLook(look);
    if (first) Util.msg(state, "Welcome, " + n + "!", "game");
    return finish(state, true);
  }

  function setRun(state, on) {
    if (!isState(state)) return false;
    state.player.run = !!on;
    return finish(state, true);
  }

  // The bank's Withdraw as: Item (false) or Note (true).
  function setBankNote(state, on) {
    if (!isState(state)) return false;
    state.player.bankNote = !!on;
    return finish(state, true);
  }

  function flag01(v) {
    return v === true || v === 1 ? true : v === false || v === 0 ? false : null;
  }

  // Replaces top-level keys and merges `full` per key; invalid values are ignored.
  function setAfk(state, patch) {
    if (!isState(state) || !patch || typeof patch !== "object") return false;
    var a = state.player.afk;
    var n = 0;
    ["cont", "ret", "loot"].forEach(function (k) {
      var v = Util.has(patch, k) ? flag01(patch[k]) : null;
      if (v !== null) { a[k] = v; n++; }
    });
    if (Util.has(patch, "eat") && [0, 30, 50, 70].indexOf(patch.eat) >= 0) { a.eat = patch.eat; n++; }
    var f = Util.has(patch, "full") && patch.full && typeof patch.full === "object" ? patch.full : {};
    ["woodcutting", "mining", "fishing", "combat"].forEach(function (k) {
      var modes = k === "combat" ? ["stop", "courier"] : ["stop", "drop", "courier"];
      if (Util.has(f, k) && modes.indexOf(f[k]) >= 0) { a.full[k] = f[k]; n++; }
    });
    if (!n) return false;
    return finish(state, true);
  }

  function recall(state) {
    return isState(state) && finish(state, Sim.recall(state), true);
  }

  // Section 10.13: a rank for a free point of the perk's skill; a reset refunds a skill's ranks for coins.
  // Neither cancels a recall cast.
  function perkUp(state, id) {
    return isState(state) && finish(state, Player.perkUp(state, id), true);
  }

  function perkReset(state, skill) {
    return isState(state) && finish(state, Player.perkReset(state, skill), true);
  }

  // Section 10.16: summons an owned pet (its first strike waits PET_SPEED ticks), or dismisses it with null.
  // Never cancels a recall cast.
  function setPet(state, id) {
    if (!isState(state)) return false;
    var p = state.player;
    if (id !== null && !(typeof id === "string" && Util.has(Data.pets || {}, id) && Util.has(p.pets, id))) return false;
    if (p.pet !== id) p.petTimer = Rules.PET_SPEED;
    p.pet = id;
    return finish(state, true, true);
  }

  // "54 min", "1 h", "1 h 5 min" (whole minutes, rounded up).
  function minutes(ticks) {
    var m = Math.ceil(ticks / 100);
    return m < 60 ? m + " min" : Math.floor(m / 60) + " h" + (m % 60 ? " " + (m % 60) + " min" : "");
  }

  // Section 10.14: Main hands over the ticks away past a catch-up cap. Every RESTED_RATE of them bank one
  // tick of double activity XP, up to RESTED_MAX. Not a player command: the stop reason and a cast stay.
  // Returns the ticks added.
  function rest(state, ticks) {
    if (!isState(state)) return 0;
    var p = state.player;
    var add = Math.min(Rules.RESTED_MAX - p.rested, Math.floor(Util.int(ticks, 0, 1e12, 0) / Rules.RESTED_RATE));
    if (!(add > 0)) return 0;
    p.rested += add;
    Util.emit(state, { type: "rested", add: add, total: p.rested });
    Util.msg(state, "You feel well rested: your next " + minutes(p.rested) + " of gathering, making and fighting earn double XP.", "game");
    Util.emit(state, { type: "save" });
    return add;
  }

  // ----------------------------------------------------------------
  // -------------------------- Bot helper --------------------------
  // ----------------------------------------------------------------

  // [x, y, from] of every tile on the player's map whose effective object is id (static nodes,
  // overrides such as fires, active fishing spots).
  function objCands(state, id) {
    var p = state.player;
    var m = World.maps[p.map];
    var tiles = Util.has(m.nodes, id) ? m.nodes[id].slice() : [];
    Object.keys(state.objs).forEach(function (k) {
      var c = k.lastIndexOf(":");
      if (k.slice(0, c) !== p.map || state.objs[k].o !== id) return;
      var xy = k.slice(c + 1).split(",");
      tiles.push([+xy[0], +xy[1]]);
    });
    Object.keys(World.FISH).forEach(function (g) {
      var grp = World.FISH[g];
      if (grp.map !== p.map || grp.obj !== id || !Util.has(state.fish, g)) return;
      state.fish[g].at.forEach(function (i) { if (grp.tiles[i]) tiles.push(grp.tiles[i]); });
    });
    var out = [];
    tiles.forEach(function (t) {
      var o = Sim.objectAt(state, p.map, t[0], t[1]);
      if (o && o.id === id) out.push([t[0], t[1], o.def.from]);
    });
    return out;
  }

  // Ground piles are used from their own tile: the shortest path among them.
  function nearestGround(state, id, max) {
    var p = state.player;
    var best = null;
    var bestLen = Infinity;
    state.ground.forEach(function (g) {
      if (g.id !== id || g.map !== p.map) return;
      var path = World.findPath(state, p.map, p.x, p.y, { x: g.x, y: g.y, mode: "tile" });
      if (path && path.length < bestLen) {
        best = g;
        bestLen = path.length;
      }
    });
    return best && bestLen <= max ? Util.refGround(best.gid) : null;
  }

  // The nearest reachable obj/npc/ground with this id on the player's map, by path length (whole-map BFS).
  function nearest(state, kind, id, maxSteps) {
    if (!isState(state) || typeof id !== "string" || !World.maps[state.player.map]) return null;
    var p = state.player;
    var max = typeof maxSteps === "number" && maxSteps >= 0 ? maxSteps : 256;
    if (kind === "ground") return nearestGround(state, id, max);
    var cands = [];
    var refs = [];
    if (kind === "obj") {
      objCands(state, id).forEach(function (c) { cands.push(c); refs.push(Util.refObj(c[0], c[1])); });
    } else if (kind === "npc") {
      state.npcs.forEach(function (n) {
        if (n.id !== id || n.map !== p.map || !Sim.alive(n)) return;
        cands.push([n.x, n.y, "nsew"]);
        refs.push(Util.refNpc(n.uid));
      });
    }
    var r = cands.length ? World.findPathAny(state, p.map, p.x, p.y, cands) : null;
    return r && r.path.length <= max ? refs[r.i] : null;
  }

  function drainEvents(state) {
    var out = state.events;
    state.events = [];
    return out;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Status ----------------------------
  // ----------------------------------------------------------------

  function foeOf(state) {
    var p = state.player;
    var n = p.foe > 0 ? state.npcs[p.foe - 1] : null;
    if (!Sim.alive(n)) return null;
    var c = Data.npcs[n.id].combat;
    return c ? { name: Data.npcs[n.id].name, lvl: c.lvl, hp: n.hp, maxHp: c.hp } : null;
  }

  function status(state) {
    var p = state.player;
    var r = World.regionAt(p.map, p.x, p.y);
    return {
      hp: p.hp, maxHp: Player.maxHp(p), run: p.run, cmb: Player.combatLevel(p), total: Player.totalLevel(p),
      qp: Script.qp(state), pack: Rules.INV_SIZE - Player.free(p), doing: Sim.doing(state), stop: p.stop,
      foe: foeOf(state), recall: Math.max(0, p.recallAt - state.tick), casting: !!p.act && p.act.k === "cast",
      region: r ? { id: r.id, name: r.name, danger: !!r.danger } : null, rested: p.rested
    };
  }

  // ----------------------------------------------------------------
  // ------------------------- Views: skills ------------------------
  // ----------------------------------------------------------------

  function skillList() {
    return Array.isArray(Data.skills) && Data.skills.length ? Data.skills
      : Rules.SKILLS.map(function (id) { return { id: id, name: id }; });
  }

  function skillName(id) {
    var s = skillList().filter(function (k) { return k.id === id; })[0];
    return s ? s.name : id;
  }

  // { lvl, xp, next, pct } for a skill: next = XP of the next level (null at 99), pct = 0..100 into it.
  function progress(p, id) {
    var lvl = Player.level(p, id);
    var xp = (Util.has(p.xp10, id) ? p.xp10[id] : 0) / 10;
    if (lvl >= 99) return { lvl: lvl, xp: xp, next: null, pct: 100 };
    var lo = Rules.xpForLevel(lvl);
    var hi = Rules.xpForLevel(lvl + 1);
    return { lvl: lvl, xp: xp, next: hi, pct: Math.max(0, Math.min(100, Math.floor((xp - lo) * 100 / (hi - lo)))) };
  }

  function viewSkills(s) {
    var p = s.player;
    var totalXp = 0;
    var list = skillList().map(function (k) {
      var g = progress(p, k.id);
      totalXp += g.xp;
      return { id: k.id, name: k.name, lvl: g.lvl, xp: g.xp, next: g.next, pct: g.pct };
    });
    return { list: list, total: Player.totalLevel(p), totalXp: Math.round(totalXp * 10) / 10, cmb: Player.combatLevel(p) };
  }

  function xpNote(xp) {
    return (Math.floor(xp) === xp ? Util.fmtInt(xp) : String(xp)) + " XP";
  }

  // Gather yields of objects whose op trains skill (gem tables show the first gem). Fishing rows are named
  // after the catch: every spot is a "Fishing spot", which says nothing in a guide or a level-up toast.
  function gatherRows(skill, out) {
    Object.keys(Data.objects || {}).forEach(function (oid) {
      var o = Data.objects[oid];
      (o.ops || []).forEach(function (op) {
        if (op.kind !== "gather" || op.skill !== skill) return;
        (op.yields || []).forEach(function (y) {
          var icon = y.item || (Array.isArray(Data.gemTable) && Data.gemTable.length ? Data.gemTable[0][1] : null);
          var name = skill === "fishing" && itemDef(y.item) ? itemName(y.item) : o.name;
          out.push({ lvl: y.lvl, icon: icon, name: name, note: xpNote(y.xp) });
        });
      });
    });
  }

  function recipeRows(skill, out) {
    Object.keys(Data.recipes || {}).forEach(function (rid) {
      var r = Data.recipes[rid];
      if (r.skill !== skill || !(r.xp > 0)) return;   // xp-0 services (tanning) are not skill unlocks
      var src = r.out && r.out.length ? r.out : r.in || [];
      out.push({ lvl: r.lvl, icon: src.length ? src[0][0] : null, name: Sim.recipeName(r), note: xpNote(r.xp) });
    });
  }

  function itemRows(skill, out) {
    var toolCat = skill === "woodcutting" ? "axe" : skill === "mining" ? "pickaxe" : null;
    Object.keys(Data.items || {}).forEach(function (id) {
      var d = Data.items[id];
      if (toolCat && d.tool && d.tool.cat === toolCat) out.push({ lvl: d.tool.lvl || 1, icon: id, name: d.name, note: "Use" });
      var req = d.equip && d.equip.req;
      if (skill === "attack" && req && req.attack) out.push({ lvl: req.attack, icon: id, name: d.name, note: "Wield" });
      if (skill === "defence" && req && req.defence) out.push({ lvl: req.defence, icon: id, name: d.name, note: "Wear" });
    });
  }

  // Guide rows sorted by level then name; strength and hitpoints have none.
  function guideRows(skill) {
    var out = [];
    gatherRows(skill, out);
    recipeRows(skill, out);
    itemRows(skill, out);
    return out.sort(function (a, b) { return a.lvl - b.lvl || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0); });
  }

  function viewGuide(s, skill) {
    if (Rules.SKILLS.indexOf(skill) < 0) return null;
    var g = progress(s.player, skill);
    var rows = guideRows(skill).map(function (r) {
      return { lvl: r.lvl, icon: r.icon, name: r.name, note: r.note, ok: g.lvl >= r.lvl };
    });
    return { id: skill, lvl: g.lvl, xp: g.xp, next: g.next, pct: g.pct, rows: rows };
  }

  function unlocks(skill, lvl) {
    if (Rules.SKILLS.indexOf(skill) < 0) return [];
    var out = [];
    guideRows(skill).forEach(function (r) { if (r.lvl === lvl && out.indexOf(r.name) < 0) out.push(r.name); });
    return out;
  }

  // Section 10.15: the nearest level above the current one that unlocks something, earns a perk point or
  // is 99 (mastery). need = whole XP still to earn. null at 99 or for an unknown skill.
  function viewGoal(s, skill) {
    if (Rules.SKILLS.indexOf(skill) < 0) return null;
    var g = progress(s.player, skill);
    if (g.next === null) return null;
    var rows = guideRows(skill);
    var perks = Player.perkList(skill).length > 0;
    for (var L = g.lvl + 1; L < 99; L++) {
      var names = [];
      for (var i = 0; i < rows.length; i++) if (rows[i].lvl === L && names.indexOf(rows[i].name) < 0) names.push(rows[i].name);
      var perk = perks && L % Rules.PERK_EVERY === 0;
      if (names.length || perk) return goalAt(skill, g, L, names, perk);
    }
    return goalAt(skill, g, 99, unlocks(skill, 99), false);
  }

  function goalAt(skill, g, L, names, perk) {
    return { skill: skill, lvl: g.lvl, at: L, names: names, perk: perk, mastery: L === 99,
      need: Math.max(0, Math.ceil(Rules.xpForLevel(L) - g.xp)) };
  }

  // ----------------------------------------------------------------
  // ---------------------- Views: panels, windows ------------------
  // ----------------------------------------------------------------

  function viewQuests(s) {
    var ids = Object.keys(Data.quests || {});
    var done = 0;
    var list = ids.map(function (id) {
      var st = Script.questState(s, id);
      if (st === "done") done++;
      return { id: id, name: Data.quests[id].name, state: st, lines: Script.journal(s, id),
        reqs: (Data.quests[id].reqs || []).map(function (c) { return Script.test(s, c); }) };
    });
    return { qp: Script.qp(s), done: done, total: ids.length, list: list };
  }

  // Why a recipe can't be made right now, or null.
  function makeWhy(s, r) {
    var f = s.player.iface;
    var why = Sim.makeCheck(s, { at: f.at, bankFeed: f.bankFeed === true }, r);
    return why ? why.msg || why.why : null;
  }

  function viewMake(s) {
    var p = s.player;
    var f = p.iface;
    if (!f || f.t !== "make") return null;
    var title = f.station && Util.has(Data.stations, f.station) ? Data.stations[f.station].name : "";
    var rows = (f.rids || []).filter(function (rid) { return Util.has(Data.recipes, rid); }).map(function (rid) {
      var r = Data.recipes[rid];
      var src = r.out && r.out.length ? r.out : r.in || [];
      var why = makeWhy(s, r);
      if (!title) title = skillName(r.skill);
      return { rid: rid, out: src.length ? src[0][0] : null, name: Sim.recipeName(r), skill: r.skill, lvl: r.lvl,
        ok: why === null, why: why,
        inputs: (r.in || []).map(function (e) { return [e[0], e[1], Sim.makeCount(p, e[0], f.bankFeed)]; }) };
    });
    return { title: title, rows: rows, bankFeed: f.bankFeed === true,
      bankAvailable: (f.rids || []).some(function (rid) { return Util.has(Data.recipes, rid) && Sim.bankMakeAllowed(Data.recipes[rid]); }) };
  }

  function viewBank(s) {
    var b = s.player.bank;
    return { rows: b.map(function (e, i) { return { i: i, id: e.id, qty: e.qty }; }), used: b.length, max: Rules.BANK_MAX,
      note: s.player.bankNote === true };
  }

  function buys(shop, id) {
    var d = itemDef(id);
    if (!d || d.untradeable || id === "coins") return false;
    return shop.buys === "all" || (Array.isArray(shop.buys) && shop.buys.indexOf(d.cat) >= 0);
  }

  function viewShop(s) {
    var f = s.player.iface;
    if (!f || f.t !== "shop" || !Util.has(Data.shops, f.id)) return null;
    var shop = Data.shops[f.id];
    var cur = s.shops[f.id] || {};
    var rows = [];
    (shop.stock || []).forEach(function (row, i) {
      var d = itemDef(row[0]);
      if (!d) return;
      rows.push({ i: i, id: row[0], stock: Util.has(cur, row[0]) ? cur[row[0]] : 0, price: Rules.buyPrice(d.value, row[2]),
        sell: buys(shop, row[0]) ? Rules.sellPrice(d.value, shop.rate) : 0 });
    });
    return { id: f.id, name: shop.name, coins: Player.count(s.player, "coins"), rows: rows };
  }

  function viewEquipment(s) {
    var p = s.player;
    var b = Player.bonuses(p);
    var slots = {};
    Rules.EQUIP_SLOTS.forEach(function (k) { slots[k] = p.eq[k] || null; });
    return { slots: slots, att: b.att, str: b.str, def: b.def, speed: b.speed,
      maxHit: Rules.playerMaxHit(Player.level(p, "strength"), p.style, b.str), twoHanded: Player.twoHanded(p.eq.weapon) };
  }

  function viewCombat(s) {
    var p = s.player;
    return {
      weapon: p.eq.weapon || null,
      styles: Rules.STYLES.map(function (st) {
        return { id: st.id, name: st.name, xp: st.xp.map(skillName), on: st.id === p.style };
      }),
      cmb: Player.combatLevel(p), afk: JSON.parse(JSON.stringify(p.afk)), recall: Math.max(0, p.recallAt - s.tick),
      courier: Script.owned(s, "courier_satchel") > 0
    };
  }

  // pin: the tile the minimap marks on the player's map: the grave itself, or the nearest ladder toward its map.
  function viewGrave(s) {
    var g = s.grave;
    if (!g) return null;
    return { map: g.map, x: g.x, y: g.y, ticksLeft: Math.max(0, g.until - s.tick),
      items: g.items.map(function (e) { return { id: e.id, qty: e.qty }; }),
      pin: g.map === s.player.map ? [g.x, g.y] : Script.ladderTo(s, g.map) };
  }

  // The season of state.tick and the ticks until the next one starts; null without season data.
  function viewSeason(s) {
    var se = Sim.season(s);
    return se ? { id: se.id, name: se.name, effect: se.effect, ticksLeft: Rules.seasonLeft(s.tick) } : null;
  }

  // A skill's perk sheet: points earned, spent and free, the reset price, and each perk's rank; null for
  // an unknown skill.
  function viewPerks(s, skill) {
    if (Rules.SKILLS.indexOf(skill) < 0) return null;
    var p = s.player;
    var spent = Player.perkSpent(p, skill);
    return { skill: skill, name: skillName(skill), level: Player.level(p, skill), points: Player.perkPoints(p, skill),
      spent: spent, free: Player.perkFree(p, skill), resetCost: spent * Rules.PERK_RESET_COINS,
      perks: Player.perkList(skill).map(function (d) {
        return { id: d.id, name: d.name, desc: d.desc, rank: Player.perkRank(p, d.id), max: d.max };
      }) };
  }

  // Every pet in Data.pets order: owned ones with their current form's name, growth stage, level, XP and the
  // next level's XP (null at the top); the rest show only their source monster. active: the summoned pet or null.
  function viewPets(s) {
    var p = s.player;
    var list = Object.keys(Data.pets || {}).map(function (id) {
      var d = Data.pets[id];
      var src = Util.has(Data.npcs, d.from) ? Data.npcs[d.from].name : "";
      if (!Util.has(p.pets, id)) return { id: id, owned: false, from: src };
      var xp = p.pets[id];
      var lvl = Rules.petLevel(xp);
      var stage = Rules.petStage(lvl);
      var pk = Util.has(Rules.PET_PERKS, d.perk) ? Rules.PET_PERKS[d.perk] : { name: "", desc: "" };
      return { id: id, owned: true, name: Combat.petForm(d, stage).name, species: d.name, stage: stage,
        stageName: Rules.PET_STAGES[stage].name, examine: d.examine, from: src, lvl: lvl, xp: xp,
        next: lvl < Rules.PET_MAX_LVL ? Rules.petXpFor(lvl + 1) : null, perk: d.perk, perkName: pk.name, perkDesc: pk.desc,
        on: p.pet === id };
    });
    return { active: Combat.summoned(p) ? p.pet : null, owned: list.filter(function (e) { return e.owned; }).length,
      list: list };
  }

  // One owned pet's dex page: forms (later ones unnamed until reached), stats from its own level, records,
  // and the dex entry with one fact per stage reached. null for a pet not owned.
  function viewPet(s, id) {
    var p = s.player;
    var d = typeof id === "string" && Util.has(Data.pets || {}, id) ? Data.pets[id] : null;
    if (!d || !Util.has(p.pets, id)) return null;
    var row = viewPets(s).list.filter(function (e) { return e.id === id; })[0];
    var lvl = row.lvl, stage = row.stage, dex = d.dex || {};
    var log = p.petLog && Util.has(p.petLog, id) ? p.petLog[id] : { dmg: 0, kills: 0, best: 0, kc: 0, out: 0 };
    var pick = function (a) { return Array.isArray(a) ? String(a[Math.min(stage, a.length - 1)] || "") : ""; };
    row.forms = Rules.PET_STAGES.map(function (st, i) {
      return { stage: i, stageName: st.name, lvl: st.lvl, reached: i <= stage, name: i <= stage ? Combat.petForm(d, i).name : null };
    });
    row.att = Rules.petAttack(d.att, lvl);
    row.maxHit = Rules.petMaxHit(d.maxHit, lvl, d.perk);
    row.speed = d.perk === "quick" ? Rules.PET_QUICK : Rules.PET_SPEED;
    row.prev = Rules.petXpFor(lvl);
    row.rec = { dmg: log.dmg, kills: log.kills, best: log.best, kc: log.kc, out: log.out };
    row.dex = { kind: String(dex.kind || ""), habitat: String(dex.habitat || ""), likes: String(dex.likes || ""),
      size: pick(dex.size), weight: pick(dex.weight),
      facts: (Array.isArray(dex.facts) ? dex.facts : []).map(function (f, i) {
        return i <= stage ? { open: true, text: String(f) } : { open: false, lvl: Rules.PET_STAGES[Math.min(i, 2)].lvl };
      }) };
    return row;
  }

  // { skillId: free points } for every skill (badges); skills without perks show 0.
  function viewPerkFree(s) {
    var out = {};
    Rules.SKILLS.forEach(function (k) { out[k] = Player.perkList(k).length ? Player.perkFree(s.player, k) : 0; });
    return out;
  }

  var view = {
    skills: viewSkills,
    guide: viewGuide,
    unlocks: unlocks,
    quests: viewQuests,
    dialogue: function (s) { return Script.view(s); },
    make: viewMake,
    bank: viewBank,
    shop: viewShop,
    equipment: viewEquipment,
    combat: viewCombat,
    hint: function (s) { return Script.hint(s); },
    grave: viewGrave,
    season: viewSeason,
    perks: viewPerks,
    perkFree: viewPerkFree,
    pets: viewPets,
    pet: viewPet,
    goal: viewGoal
  };

  return {
    createState: Sim.createState, tick: Sim.tick, catchUp: Sim.catchUp, drainEvents: drainEvents,
    serialize: Save.serialize, deserialize: Save.deserialize, check: Save.check, objectAt: Sim.objectAt,
    menuAt: menuAt, options: options, canUse: canUse, act: act, walkTo: walkTo, useItemOn: useItemOn,
    moveItem: moveItem, make: make, setMakeBankFeed: setMakeBankFeed, dialogueContinue: dialogueContinue, dialogueChoose: dialogueChoose,
    closeInterface: closeInterface, depositAll: depositAll, depositWorn: depositWorn, setStyle: setStyle, setLook: setLook,
    setRun: setRun, setBankNote: setBankNote, setAfk: setAfk, recall: recall, perkUp: perkUp, perkReset: perkReset, setPet: setPet, rest: rest, nearest: nearest, status: status,
    view: view
  };
})();
/*ENGINE-END*/
// ==== src/ui/icons.js ====
// ----------------------------------------------------------------
// ---------------- Icons: item icon atlas and glyphs -------------
// ----------------------------------------------------------------
// Procedural 16x16 pixel icons (DESIGN.md 18.6). Shapes are drawn once at load into masks with the
// legend . o b s h a w, auto-shaded (light from the top-left) and auto-outlined. One atlas holds every
// item, coin pile, skill, tab and equipment-slot glyph, shown at 32 css per cell (2 css per art px).
// The mask helpers (grid, finish, paintRows, ramp) are shared with Sprites.
const Icons = (function () {
  "use strict";

  var OUTLINE = "#1b140d", CELL = 16, COLS = 16, CSS_CELL = 32;

  // ----------------------------------------------------------------
  // ------------------------ Colour ramps --------------------------
  // ----------------------------------------------------------------

  // base -> [shade, highlight] for the fixed tables of 18.4; anything else derives from its base.
  var RAMPS = {
    "#b0743a": ["#7a4c22", "#dca06a"], "#6d6a66": ["#4a4846", "#9a9792"], "#a3abb0": ["#727a80", "#d4dadd"],
    "#4d6fd0": ["#31489a", "#8aa6f0"], "#3f9a6c": ["#2a6a49", "#78c99c"], "#b8433a": ["#7e2a24", "#e5806f"],
    "#e8c040": ["#a07a18", "#f8e070"], "#5a3b22": ["#3f2915", "#7a5333"], "#5a8532": ["#46692a", "#74a047"],
    "#8b6b3e": ["#6c512d", "#a5844f"], "#cdb67e": ["#a9925e", "#e3d0a0"], "#7e7b73": ["#5b5852", "#9d9a90"],
    "#7a5532": ["#5a3c22", "#9a7048"], "#6b6660": ["#4e4a45", "#88837c"], "#4f5f3a": ["#3a4a2c", "#66784c"],
    "#3f6d2a": ["#2d5120", "#5d903a"], "#4b6b24": ["#34501a", "#6c8f33"], "#7f9a3f": ["#5f7a2e", "#a8bf5a"],
    "#b5532a": ["#8a3a1e", "#e07a3a"], "#2b4a33": ["#1d3524", "#3f6a48"], "#3f8f8a": ["#2a6662", "#79cfc6"],
    "#4a4440": ["#2a2522", "#625a54"], "#8d8577": ["#6a6458", "#b6ad9c"]
  };

  function rgb(hex) {
    var n = parseInt(String(hex).slice(1, 7), 16) || 0;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function mix(c, d, t) {
    var a = rgb(c), b = rgb(d), v = [0, 1, 2].map(function (i) { return Math.round(a[i] + (b[i] - a[i]) * t); });
    return "#" + ((1 << 24) | (v[0] << 16) | (v[1] << 8) | v[2]).toString(16).slice(1);
  }

  // [shade, highlight] of a base colour.
  function ramp(c) {
    var k = String(c).toLowerCase();
    return Util.has(RAMPS, k) ? RAMPS[k] : [mix(k, OUTLINE, 0.36), mix(k, "#fff6e0", 0.36)];
  }

  // Mask palette for item colours [c1, c2?, c3?].
  function palette(c1, c2, c3) {
    var r = ramp(c1);
    return { o: OUTLINE, b: c1, s: r[0], h: r[1], a: c2 || r[1], w: c3 || "#ffffff" };
  }

  // ----------------------------------------------------------------
  // ------------------------- Mask toolkit -------------------------
  // ----------------------------------------------------------------

  function grid(w, h) {
    var c = [];
    for (var y = 0; y < h; y++) {
      c.push([]);
      for (var x = 0; x < w; x++) c[y].push(".");
    }
    return { w: w, h: h, c: c };
  }

  function put(g, x, y, ch) { if (x >= 0 && y >= 0 && x < g.w && y < g.h) g.c[y][x] = ch; }

  function get(g, x, y) { return x >= 0 && y >= 0 && x < g.w && y < g.h ? g.c[y][x] : "."; }

  function rect(g, x, y, w, h, ch) { for (var j = 0; j < h; j++) for (var i = 0; i < w; i++) put(g, x + i, y + j, ch); }

  // Bresenham; wd 2 also fills the cell to the right (a solid diagonal band).
  function line(g, x0, y0, x1, y1, ch, wd) {
    var dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1, err = dx + dy;
    for (var n = 0; n < 128; n++) {
      put(g, x0, y0, ch);
      if (wd > 1) put(g, x0 + 1, y0, ch);
      if (x0 === x1 && y0 === y1) break;
      var e2 = 2 * err;
      if (e2 >= dy) { err += dy; x0 += sx; }
      if (e2 <= dx) { err += dx; y0 += sy; }
    }
  }

  // Span-filled ellipse: every cell whose centre lies inside.
  function ell(g, cx, cy, rx, ry, ch) {
    for (var y = Math.floor(cy - ry); y <= Math.ceil(cy + ry); y++) {
      for (var x = Math.floor(cx - rx); x <= Math.ceil(cx + rx); x++) {
        var u = (x + 0.5 - cx) / rx, v = (y + 0.5 - cy) / ry;
        if (u * u + v * v <= 1) put(g, x, y, ch);
      }
    }
  }

  // Even-odd polygon fill by cell centre; pts = [x, y, x, y, ...].
  function poly(g, pts, ch) {
    for (var y = 0; y < g.h; y++) {
      for (var x = 0; x < g.w; x++) {
        var inside = false;
        for (var i = 0, j = pts.length - 2; i < pts.length; j = i, i += 2) {
          var yi = pts[i + 1], yj = pts[j + 1];
          if ((yi > y + 0.5) !== (yj > y + 0.5) && x + 0.5 < (pts[j] - pts[i]) * (y + 0.5 - yi) / (yj - yi) + pts[i]) inside = !inside;
        }
        if (inside) put(g, x, y, ch);
      }
    }
  }

  // Hand-drawn rows at (x, y) ("|"-joined string or array); "." cells are skipped.
  function stamp(g, x, y, rows) {
    var rs = typeof rows === "string" ? rows.split("|") : rows;
    for (var j = 0; j < rs.length; j++) {
      for (var i = 0; i < rs[j].length; i++) if (rs[j].charAt(i) !== ".") put(g, x + i, y + j, rs[j].charAt(i));
    }
  }

  function flipX(g) { g.c.forEach(function (r) { r.reverse(); }); }

  // Auto-shade then auto-outline. "b" becomes h/b/s by its open sides (light from the top-left); with
  // acc set, "a" becomes l/a/d the same way (sprites). "W" is a glint without an outline; it ends as "w".
  function finish(g, acc) {
    var src = g.c.map(function (r) { return r.slice(); });
    function open(x, y) {
      var ch = x < 0 || y < 0 || x >= g.w || y >= g.h ? "." : src[y][x];
      return ch === "." || ch === "o" || ch === "W";
    }
    for (var y = 0; y < g.h; y++) {
      for (var x = 0; x < g.w; x++) {
        var ch = src[y][x];
        if (ch !== "b" && !(acc && ch === "a")) continue;
        var lit = open(x, y - 1) || open(x - 1, y), dark = open(x, y + 1) || open(x + 1, y);
        if (lit !== dark) g.c[y][x] = ch === "b" ? (lit ? "h" : "s") : (lit ? "l" : "d");
      }
    }
    var solid = g.c.map(function (r) { return r.map(function (c) { return c !== "." && c !== "W"; }); });
    for (var yy = 0; yy < g.h; yy++) {
      for (var xx = 0; xx < g.w; xx++) {
        if (g.c[yy][xx] === "." && ((yy > 0 && solid[yy - 1][xx]) || (yy < g.h - 1 && solid[yy + 1][xx]) ||
          (xx > 0 && solid[yy][xx - 1]) || (xx < g.w - 1 && solid[yy][xx + 1]))) g.c[yy][xx] = "o";
      }
    }
    return g.c.map(function (r) { return r.join("").replace(/W/g, "w"); });
  }

  // Paints mask rows with run-length fillRects: (x, y) top-left, s px per mask px, pal char -> colour.
  function paintRows(ctx, rows, x, y, s, pal, flip) {
    for (var j = 0; j < rows.length; j++) {
      var row = rows[j], n = row.length;
      for (var i = 0, k; i < n; i = k) {
        var ch = row.charAt(i);
        for (k = i + 1; k < n && row.charAt(k) === ch;) k++;
        if (ch === "." || !Util.has(pal, ch)) continue;
        ctx.fillStyle = pal[ch];
        ctx.fillRect(x + (flip ? n - k : i) * s, y + j * s, (k - i) * s, s);
      }
    }
  }

  // Draws, shades and outlines a 16x16 icon, then shifts it inside the inner 14x14 when it fits.
  function make(fn) {
    var g = grid(CELL, CELL);
    fn(g);
    var rows = finish(g, false), x0 = 16, x1 = -1, y0 = 16, y1 = -1;
    rows.forEach(function (r, y) {
      for (var x = 0; x < 16; x++) {
        if (r.charAt(x) === ".") continue;
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
      }
    });
    var dx = x0 < 1 ? 1 - x0 : x1 > 14 ? 14 - x1 : 0, dy = y0 < 1 ? 1 - y0 : y1 > 14 ? 14 - y1 : 0;
    if ((!dx && !dy) || x1 - x0 > 13 || y1 - y0 > 13) return rows;
    return rows.map(function (r, y) {
      var src = rows[y - dy] || "................";
      return ".".repeat(Math.max(0, dx)) + src.slice(Math.max(0, -dx), 16 - Math.max(0, dx)) + ".".repeat(Math.max(0, -dx));
    });
  }

  // ----------------------------------------------------------------
  // ----------------------- Item shape art -------------------------
  // ----------------------------------------------------------------

  // Long items run from the bottom-left to the top-right; the outline stays inside the inner 14x14.
  function sword(g) {
    line(g, 6, 9, 12, 3, "b", 2); put(g, 13, 2, "b"); line(g, 3, 8, 7, 12, "b", 1); line(g, 4, 11, 3, 12, "a", 2);
    rect(g, 2, 13, 2, 1, "b");
  }

  // Ring around an ellipse's edge (net hoops).
  function hoop(g, cx, cy, rx, ry, holes) {
    var src = grid(CELL, CELL);
    ell(src, cx, cy, rx, ry, "b");
    ell(g, cx, cy, rx, ry, "b");
    for (var j = 0; j < CELL; j++) {
      for (var i = 0; i < CELL; i++) {
        if (get(src, i, j) !== "b") continue;
        if (get(src, i - 1, j) === "." || get(src, i + 1, j) === "." || get(src, i, j - 1) === "." || get(src, i, j + 1) === ".") put(g, i, j, "a");
        else if (holes && (i + j) % 2 === 0) put(g, i, j, "o");
      }
    }
  }

  var DRAW = {
    feather: function (g) {
      stamp(g, 0, 2, "............bb..|..........bbab..|.........bbab...|........bbab....|.......bbab.....|" +
        "......bbab......|.....bbab.......|....bbab........|....bab.........|...bab..........|...a............|..a.............");
    },
    tinderbox: function (g) {
      stamp(g, 2, 2, "........W...|.......W.W..|........W...|............|.bbbbbbbbbb.|bbbbbbbbbbbb|bbbbbbbbbbbb|" +
        "oooooooooooo|bbbbbaabbbbb|bbbbbaabbbbb|bbbbbbbbbbbb");
    },
    hammer: function (g) {
      line(g, 2, 13, 8, 7, "a", 2);
      stamp(g, 6, 2, ".bb.....|bbbb....|.bbbb...|..bbbb..|...bbbb.|....bbbb|.....bb.");
    },
    chisel: function (g) {
      line(g, 2, 13, 6, 9, "a", 2); line(g, 3, 13, 6, 10, "a", 1); rect(g, 6, 8, 2, 2, "s"); line(g, 8, 7, 12, 3, "b", 2);
      put(g, 13, 3, "."); put(g, 12, 2, "W");
    },
    needle: function (g) {
      line(g, 5, 10, 12, 3, "b", 1); stamp(g, 2, 9, "..bb|.b.b|..b."); line(g, 3, 11, 2, 13, "a", 1);
      line(g, 3, 13, 6, 13, "a", 1); put(g, 12, 2, "W");
    },
    net: function (g) { hoop(g, 8.5, 7, 5.5, 4.5, true); line(g, 2, 13, 5, 10, "a", 2); },
    rod: function (g) {
      line(g, 2, 13, 4, 11, "b", 2); line(g, 5, 10, 12, 3, "b", 1); line(g, 13, 3, 13, 9, "a", 1);
      stamp(g, 11, 10, "..a|a.a|.a.");
    },
    harpoon: function (g) {
      line(g, 2, 13, 8, 7, "a", 2); line(g, 9, 6, 12, 3, "b", 2); put(g, 13, 2, "b"); stamp(g, 8, 3, "b....|.b...");
      stamp(g, 11, 6, ".b.|b.."); put(g, 9, 5, "b");
    },
    cage: function (g) {
      ell(g, 7.5, 11, 5.5, 7.5, "a"); rect(g, 0, 11, 16, 5, ".");
      for (var y = 4; y < 11; y++) for (var x = 2; x < 14; x++) if ((x + y) % 2 === 1 && get(g, x, y) === "a") put(g, x, y, "o");
      line(g, 4, 5, 3, 10, "b", 1); line(g, 11, 5, 12, 10, "b", 1); line(g, 7, 3, 7, 10, "b", 2);
      rect(g, 2, 7, 12, 1, "b"); rect(g, 2, 11, 12, 2, "b");
    },
    mould: function (g) {
      poly(g, [4, 4, 14, 4, 12, 10, 2, 10], "b"); rect(g, 2, 10, 10, 2, "s"); poly(g, [12, 10, 14, 4, 14, 6, 12, 12], "s");
      ell(g, 6, 7, 2, 1.6, "o"); put(g, 6, 7, "a"); put(g, 5, 7, "a"); poly(g, [9.5, 5.5, 12, 5.5, 11, 8.5], "o");
      put(g, 10, 6, "a");
    },
    satchel: function (g) {
      stamp(g, 2, 2, "...bbbbbb...|..b......b..|.b........b.|bbbbbbbbbbbb|bbbbbbbbbbbb|bbbbbbbbbbbb|oooooaaooooo|" +
        "bbbbbaabbbbb|bbbbbbbbbbbb|bbbbbbbbbbbb|bbbbbbbbbbbb|.bbbbbbbbbb.");
    },
    seal: function (g) {
      ell(g, 7.5, 7.5, 5.6, 5.6, "b"); ell(g, 7.5, 7.5, 3.6, 3.6, "o"); ell(g, 7.5, 7.5, 2.8, 2.8, "a");
      stamp(g, 6, 6, "s..|.ss"); put(g, 6, 5, "w");
    },
    tusk: function (g) {
      stamp(g, 2, 2, "...........b|..........bb|..........bb|.........bbb|........bbbb|.......bbbb.|.....bbbbb..|" +
        ".aabbbbbb...|aaabbbbb....|aaabbb......|.aa.........");
      put(g, 11, 6, "w");
    },
    heart: function (g) {
      stamp(g, 2, 2, ".bbbb..bbbb.|bbbbbbbbbbbb|bbbbbbbbbbbb|bbbbbbbbbbbb|.bbbbbbbbbb.|..bbbbbbbb..|...bbbbbb...|" +
        "....bbbb....|.....bb.....");
      stamp(g, 5, 4, "a....a|.a..a.|..aa..|..a..."); rect(g, 3, 3, 2, 2, "w");
    },
    logs: function (g) {
      for (var t = 0; t <= 6; t++) { ell(g, 6.5 + t, 10.5 - t, 1.7, 1.7, "b"); ell(g, 3.5 + t, 12.5 - t, 1.7, 1.7, "b"); }
      ell(g, 3.5, 12.5, 1.7, 1.7, "a"); ell(g, 6.5, 10.5, 1.7, 1.7, "a"); put(g, 3, 12, "s"); put(g, 6, 10, "s");
    },
    // An angular chunk of grey rock (a = the item's rock grey) with veins of the ore colour, like the world rocks.
    ore: function (g) {
      poly(g, [2, 8, 4.5, 4, 8, 2.5, 12, 3.5, 14, 8, 13.5, 12.5, 9, 14, 4, 13.5, 2, 11], "a");
      rect(g, 5, 5, 2, 2, "b"); put(g, 5, 5, "h"); rect(g, 9, 4, 2, 1, "b"); rect(g, 11, 7, 2, 2, "b"); put(g, 11, 7, "h");
      rect(g, 4, 9, 2, 1, "b"); rect(g, 7, 10, 2, 2, "b"); put(g, 7, 10, "h"); put(g, 10, 12, "b"); put(g, 3, 11, "b");
    },
    bar: function (g) {
      stamp(g, 1, 4, "....hhhhhhhh..|...hhwhhhhhbs.|..hhhhhhhhbss.|.bbbbbbbbbsss.|.bbbbbbbbbss..|.bbbbbbbbbs...|.ssssssssss...");
    },
    // A raw crystal: a tall six-sided prism, pointed at both ends, lit face / middle / shade (never an ore's lump).
    gem_uncut: function (g) {
      stamp(g, 3, 2, "....h....|...hhb...|..hhhbs..|.hhhhbbs.|.hhhhbbs.|.hhhhbbs.|.hhhhbbs.|.hhhhbbs.|.hhhhbbs.|" +
        "..hhhbs..|...hbs...|....b....");
      put(g, 5, 6, "W"); put(g, 5, 7, "W");
    },
    gem: function (g) {
      stamp(g, 2, 3, "...hhhhhh...|..hhwhhhbb..|.hhhhhhbbbs.|bbbbbbbbbbss|.bbbbbsbbss.|..bbbbsbss..|...bbbsss...|" +
        "....bbss....|.....bs.....");
    },
    axe: function (g) {
      line(g, 2, 13, 12, 3, "a", 2); put(g, 13, 2, "a");
      poly(g, [4.6, 5.2, 6.6, 1.9, 10.6, 3.6, 12.2, 4.7, 8.5, 8.2, 6, 8.9], "b"); put(g, 5, 4, "W");
    },
    pickaxe: function (g) {
      line(g, 2, 13, 9, 6, "a", 2);
      poly(g, [1.6, 4.4, 4.5, 2.4, 8.5, 2.1, 11.4, 4.4, 13.3, 8.5, 13.2, 12.4, 11.6, 8.8, 9.6, 6.1, 6.2, 4.6, 3.4, 4.4], "b");
      put(g, 5, 3, "W");
    },
    sword: sword,
    // A short, broad-based blade: a stubby guard and a 1-cell grip under it.
    dagger: function (g) {
      line(g, 7, 9, 10, 6, "b", 2); put(g, 11, 5, "b"); put(g, 11, 4, "b"); put(g, 9, 6, "W");
      line(g, 5, 8, 8, 11, "b", 1); line(g, 5, 11, 4, 12, "a", 2); put(g, 3, 13, "b");
    },
    // A flanged ball on a short haft: four studs round the head, a collar where it meets the haft.
    mace: function (g) {
      line(g, 2, 13, 6, 9, "a", 2); rect(g, 7, 8, 2, 1, "s");
      ell(g, 10, 5.5, 3.1, 3.1, "b"); put(g, 10, 2, "b"); put(g, 13, 5, "b"); put(g, 13, 2, "b"); put(g, 7, 3, "b");
      put(g, 9, 4, "W");
    },
    // Longer and broader than the sword: a 3-wide blade with a fuller, a wide guard and a two-hand grip.
    greatsword: function (g) {
      line(g, 6, 8, 11, 3, "b", 2); line(g, 6, 9, 11, 4, "b", 2); put(g, 12, 2, "b"); put(g, 9, 5, "W");
      line(g, 2, 6, 7, 11, "b", 1); line(g, 3, 6, 7, 10, "b", 1); line(g, 4, 10, 2, 12, "a", 2); put(g, 1, 13, "b");
    },
    // A butcher's slab of a blade: wide, square-ended, a hole near the spine and a bright cutting edge.
    cleaver: function (g) {
      poly(g, [4.5, 8.5, 9, 4, 13.5, 4, 13.5, 6.5, 8, 12], "b"); line(g, 8, 11, 13, 6, "h", 1);
      put(g, 11, 5, "o"); line(g, 2, 13, 5, 10, "a", 2);
    },
    helm: function (g) {
      ell(g, 7.5, 7, 5.5, 5, "b"); rect(g, 2, 7, 12, 6, "b"); rect(g, 5, 7, 6, 1, "o"); rect(g, 7, 8, 2, 3, "o");
      rect(g, 6, 11, 4, 2, "."); rect(g, 7, 3, 2, 3, "h");
    },
    shield: function (g) {
      poly(g, [2, 2, 14, 2, 14, 8, 11.5, 12, 8, 14.6, 4.5, 12, 2, 8], "b"); rect(g, 7, 3, 2, 10, "s"); rect(g, 3, 6, 10, 2, "s");
      ell(g, 8, 7, 2, 2, "a"); put(g, 7, 6, "w");
    },
    greaves: function (g) {
      rect(g, 3, 2, 10, 3, "b"); rect(g, 3, 5, 4, 8, "b"); rect(g, 9, 5, 4, 8, "b"); rect(g, 2, 12, 5, 2, "b");
      rect(g, 9, 12, 5, 2, "b"); rect(g, 3, 8, 4, 1, "o"); rect(g, 9, 8, 4, 1, "o"); rect(g, 3, 4, 10, 1, "o");
    },
    breastplate: function (g) {
      poly(g, [2, 3, 6, 2, 7, 4, 9, 4, 10, 2, 14, 3, 13, 8, 12.5, 13, 3.5, 13, 3, 8], "b"); rect(g, 7, 5, 2, 8, "h");
      rect(g, 4, 9, 8, 1, "o"); put(g, 2, 7, "o"); put(g, 13, 7, "o");
    },
    cape: function (g) {
      poly(g, [5, 2, 11, 2, 12, 5, 14, 13, 2, 13, 4, 5], "b"); rect(g, 5, 2, 6, 1, "a"); rect(g, 3, 12, 11, 1, "a");
      line(g, 6, 5, 5, 11, "s", 1); line(g, 9, 5, 10, 11, "s", 1);
    },
    ring: function (g) { ell(g, 7.5, 9, 5, 4, "b"); ell(g, 7.5, 9, 3, 2, "."); rect(g, 6, 3, 4, 3, "a"); put(g, 7, 4, "w"); },
    amulet: function (g) {
      stamp(g, 2, 2, "b..........b|b..........b|.b........b.|.b........b.|..b......b..|...b....b...|....bbbb....");
      ell(g, 7.5, 11, 2.8, 2.6, "b"); ell(g, 7.5, 11, 1.7, 1.6, "a"); put(g, 7, 10, "w");
    },
    gloves: function (g) {
      stamp(g, 3, 2, "...b.b.b..|..bbbbbbb.|..bbbbbbb.|b.bbbbbbb.|bbbbbbbbb.|bbbbbbbbb.|.bbbbbbbb.|..bbbbbbb.|" +
        "..bbbbbbb.|..aaaaaaa.|..bbbbbbb.|..bbbbbbb.");
      rect(g, 7, 4, 1, 3, "o"); rect(g, 9, 4, 1, 3, "o");
    },
    boots: function (g) {
      stamp(g, 2, 2, "....bbbb....|....aaaa....|....bbbb....|bbbbbbbb....|aaaabbbb....|bbbbbbbbbbbb|bbbbbbbbbbbb|" +
        "bbbboooooooo|bbbbbbbbb...|bbbbbbbbb...|ooooooooo...");
    },
    jerkin: function (g) {
      poly(g, [2, 3, 6, 2, 8, 6, 10, 2, 14, 3, 14, 7, 12, 7, 12.5, 13.5, 3.5, 13.5, 4, 7, 2, 7], "b");
      line(g, 8, 7, 8, 12, "o", 1); put(g, 7, 9, "a"); put(g, 7, 11, "a"); rect(g, 4, 11, 8, 1, "a");
    },
    leggings: function (g) {
      rect(g, 3, 2, 10, 3, "b"); poly(g, [3, 5, 7.5, 5, 7, 13.5, 3.5, 13.5], "b"); poly(g, [8.5, 5, 13, 5, 12.5, 13.5, 9, 13.5], "b");
      rect(g, 3, 3, 10, 1, "a");
    },
    vambraces: function (g) {
      rect(g, 8, 2, 5, 10, "b"); rect(g, 2, 4, 5, 10, "b"); rect(g, 8, 4, 5, 1, "a"); rect(g, 8, 9, 5, 1, "a");
      rect(g, 2, 6, 5, 1, "a"); rect(g, 2, 11, 5, 1, "a");
    },
    // A hide pinned out flat: a wide body with four short corner stubs; off-centre patches (centred ones read as a face).
    hide: function (g) {
      stamp(g, 2, 3, "bb...bb...bb|bbbbbbbbbbbb|.bbbbbbbbbb.|.bbbbbbbbbb.|..bbbbbbbb..|.bbbbbbbbbb.|.bbbbbbbbbb.|" +
        "bbbbbbbbbbbb|bb...bb...bb|.....bb.....");
      stamp(g, 3, 5, "aaa..|aaaa.|.aaaa|..aa.|...a."); stamp(g, 9, 9, ".aa|aaa|.a."); rect(g, 10, 4, 2, 1, "a");
    },
    leather: function (g) {
      poly(g, [3, 4, 12, 3, 13, 12, 4, 13], "b");
      for (var i = 4; i < 12; i += 2) { put(g, i, 5, "a"); put(g, i + 1, 11, "a"); }
      put(g, 4, 8, "a"); put(g, 11, 7, "a"); rect(g, 10, 3, 3, 2, "."); poly(g, [10, 5, 12.6, 3.4, 12.6, 5.2], "s");
    },
    // A curled shrimp facing left: feelers and eye at the top, shell segments (s), legs inside the curl, tail fan
    // at the bottom.
    shrimp: function (g) {
      stamp(g, 2, 2, "a.a.........|.a.a........|...abbbb....|..bbbbbbbb..|.bobbsbbbbb.|..bba.sbbbbb|......asbbbb|" +
        "......asbbbb|....bbsbbbb.|..abbbsbbb..|aaabbbb.....|.aa.........");
    },
    // w = two short diagonal dashes: a wet sheen on raw fish, grill marks on cooked fish (c3 picks which).
    fish: function (g) {
      ell(g, 7, 8, 5.2, 3.2, "b"); poly(g, [11, 8, 14.5, 4.5, 14.5, 11.5], "b"); poly(g, [5, 5, 8, 3.5, 9, 5.5], "a");
      line(g, 6, 9, 9, 9, "a", 1); put(g, 7, 10, "a"); put(g, 4, 7, "o"); put(g, 3, 9, "o");
      put(g, 7, 7, "w"); put(g, 8, 6, "w"); put(g, 10, 7, "w"); put(g, 11, 6, "w");
    },
    fish_long: function (g) {
      poly(g, [2.5, 12.5, 5, 8.5, 9, 5.5, 12, 4, 11, 7, 7, 11, 4, 13], "b"); poly(g, [10.5, 5.5, 13.5, 2.5, 13, 5.5, 13.5, 7.5], "b");
      line(g, 6, 10, 9, 7, "a", 1); put(g, 4, 11, "o"); poly(g, [6.5, 8, 8.5, 6, 7.5, 5.5], "a");
    },
    swordfish: function (g) {
      line(g, 2, 13, 5, 10, "b", 1); poly(g, [4, 11.5, 8, 6.5, 12, 4, 11, 7.5, 7, 11, 4.5, 12], "b");
      poly(g, [10.5, 5.5, 13.5, 2.5, 13, 6, 13.5, 8.5], "b"); poly(g, [7, 7.5, 7.5, 3.5, 9.5, 6], "a");
      line(g, 6, 10, 10, 6, "a", 1); put(g, 5, 10, "o");
    },
    lobster: function (g) {
      ell(g, 8, 9, 2.4, 3.6, "b"); ell(g, 4, 5, 1.9, 2.4, "b"); ell(g, 12, 5, 1.9, 2.4, "b"); line(g, 5, 7, 6, 8, "b", 1);
      line(g, 11, 7, 10, 8, "b", 1); put(g, 4, 3, "."); put(g, 11, 3, "."); rect(g, 7, 9, 3, 1, "a");
      rect(g, 7, 11, 3, 1, "a"); poly(g, [6, 12.5, 10, 12.5, 11, 13.8, 5, 13.8], "b");
    },
    shark: function (g) {
      poly(g, [1.5, 10, 5, 7, 10, 6.5, 12.5, 8, 14.5, 4.5, 14.5, 12.5, 12, 10, 8, 12, 4, 12], "b");
      poly(g, [6.5, 7, 8.5, 2.5, 9.5, 7], "b"); poly(g, [3, 11, 10, 11, 8, 12.5, 4, 12.5], "a"); put(g, 4, 9, "o");
      line(g, 6, 9, 6, 10, "o", 1);
    },
    // A grilled slab seen from above, its darker side showing below; a = grill lines.
    steak: function (g) {
      stamp(g, 2, 3, "....bbbbb...|..bbbbbbbbb.|.bbbbabbbabb|bbbbabbbabbb|bbbabbbabbbb|bbabbbabbbbb|babbbabbbbb.|" +
        ".bbbbbbbbb..|.sssssssss..|..sssssss...");
    },
    meat: function (g) {
      ell(g, 6.5, 6.5, 4.6, 4.2, "b"); line(g, 8, 8, 11, 11, "a", 2); ell(g, 11.5, 12.5, 1.3, 1.3, "a");
      ell(g, 12.5, 11.5, 1.3, 1.3, "a"); put(g, 6, 7, "a"); put(g, 4, 5, "a");
    },
    burnt: function (g) {
      poly(g, [2, 11, 4, 7, 8, 5, 12, 6, 14, 10, 12, 13, 5, 13.5], "b"); put(g, 6, 9, "a"); put(g, 9, 8, "a");
      put(g, 11, 11, "a"); stamp(g, 6, 1, "W..W|.W..|W.W.");
    },
    misc: function (g) {
      poly(g, [4, 6, 6, 4, 10, 4, 12, 6, 13, 12, 11, 14, 5, 14, 3, 12], "b"); rect(g, 6, 3, 4, 2, "a"); line(g, 6, 5, 10, 5, "o", 1);
    }
  };

  // ----------------------------------------------------------------
  // --------------------------- Coin piles -------------------------
  // ----------------------------------------------------------------

  var COIN = [".oooooo.", "ohhhhbbo", "ohwbbbso", "obbbbsso", "oaaaaaao", ".oooooo."];
  var COIN_QTY = [1, 2, 3, 5, 25, 100, 1000, 10000];
  // Stacks [x, baseY, count] per pile variant, drawn back (small y) to front.
  var COIN_STACKS = [
    [[4, 9, 1]], [[7, 6, 1], [3, 9, 1]], [[4, 9, 3]], [[7, 8, 2], [2, 9, 3]], [[1, 7, 2], [7, 8, 3], [4, 9, 2]],
    [[2, 6, 2], [7, 6, 3], [1, 9, 2], [6, 9, 3]], [[1, 5, 3], [6, 5, 4], [2, 9, 3], [7, 9, 4]],
    [[4, 4, 4], [1, 7, 3], [7, 7, 4], [1, 9, 2], [5, 9, 3], [8, 9, 2]]
  ];

  function coinPile(stacks) {
    var g = grid(CELL, CELL);
    stacks.slice().sort(function (p, q) { return p[1] - q[1]; }).forEach(function (st) {
      for (var i = 0; i < st[2]; i++) stamp(g, st[0], st[1] - 2 * i, COIN);
    });
    return g.c.map(function (r) { return r.join(""); });
  }

  // Pile variant for a coin count; no count shows the 25-coin pile.
  function coinVariant(qty) {
    var q = typeof qty === "number" && qty > 0 ? qty : 25, v = 0;
    for (var i = 0; i < COIN_QTY.length; i++) if (q >= COIN_QTY[i]) v = i;
    return v;
  }

  // ----------------------------------------------------------------
  // --------------------- Skill and tab glyphs ---------------------
  // ----------------------------------------------------------------

  var GLYPH_DRAW = {
    fist: function (g) {
      stamp(g, 2, 2, ".bbb........|bbbbb.......|bbbbb.......|.bbbb.......|.bbb........|.bbb...bbb..|.bbbb.bbbbb.|" +
        ".bbbbbbbbbbb|..bbbbbbbbbb|...bbbbbbbbb|.....bbbaaaa|........aaaa");
      line(g, 3, 3, 5, 3, "o", 1);
    },
    tree: function (g) { rect(g, 7, 10, 2, 4, "a"); ell(g, 8, 6, 4.5, 4, "b"); ell(g, 5, 8.5, 3, 2.6, "b"); ell(g, 11, 8.5, 3, 2.6, "b"); },
    anvil: function (g) {
      stamp(g, 2, 4, "bbbbbbbbbbbb|.bbbbbbbbbbb|..bbbbbbbb..|....bbbb....|....bbbb....|...bbbbbb...|..bbbbbbbb..|..aaaaaaaa..");
      stamp(g, 9, 1, "...W|..W.|.W..");
    },
    pot: function (g) {
      ell(g, 7.5, 8, 5, 4.2, "b"); rect(g, 2, 4, 12, 2, "b"); rect(g, 3, 5, 10, 1, "o"); rect(g, 4, 12, 8, 1, "a");
      stamp(g, 5, 1, "W..W.|.W..W");
    },
    flame: function (g) {
      stamp(g, 3, 2, "...bb.....|...bbb..b.|..bbbb.bb.|..bbbbbbb.|.bbbbbbbbb|.bbbaabbbb|bbbaaaabbb|bbaaaaaabb|" +
        "bbaawwaabb|bbaawwaabb|.bbaaaabb.|..bbbbbb..");
    },
    star: function (g) { poly(g, [8, 1.5, 10, 6, 14.5, 6.2, 11, 9.2, 12.4, 14, 8, 11.2, 3.6, 14, 5, 9.2, 1.5, 6.2, 6, 6], "b"); put(g, 7, 5, "w"); },
    swords: function (g) {
      var b = grid(CELL, CELL);
      sword(b);
      flipX(b);
      b.c.forEach(function (r, y) { r.forEach(function (ch, x) { if (ch !== ".") put(g, x, y, ch); }); });
      sword(g);
    },
    bars: function (g) { rect(g, 2, 9, 3, 5, "b"); rect(g, 6, 5, 3, 9, "a"); rect(g, 10, 2, 3, 12, "w"); },
    scroll: function (g) {
      rect(g, 3, 3, 10, 10, "b"); rect(g, 2, 2, 12, 2, "b"); rect(g, 2, 12, 12, 2, "b"); rect(g, 2, 3, 12, 1, "o");
      rect(g, 2, 12, 12, 1, "o"); line(g, 5, 6, 10, 6, "s", 1); line(g, 5, 8, 10, 8, "s", 1); line(g, 5, 10, 8, 10, "s", 1);
      ell(g, 11, 11, 1.6, 1.6, "a");
    },
    wrench: function (g) { line(g, 2, 13, 9, 6, "b", 2); ell(g, 11, 5, 3.2, 3.2, "b"); poly(g, [10, 0, 14, 0, 14, 4.5, 12, 5, 11, 3.5], "."); },
    // Season glyphs (status strip): a five-petal blossom, a rayed sun, a falling leaf, a six-armed snowflake.
    blossom: function (g) {
      for (var k = 0; k < 5; k++) {
        var an = (k * 72 - 90) * Math.PI / 180;
        ell(g, 7.5 + Math.cos(an) * 3.3, 7.8 + Math.sin(an) * 3.3, 2.4, 2.4, "b");
      }
      ell(g, 7.5, 7.8, 1.6, 1.6, "a"); put(g, 7, 7, "w");
    },
    sun: function (g) {
      ell(g, 7.5, 7.5, 3.4, 3.4, "b"); put(g, 6, 6, "w");
      [[7, 1], [8, 1], [7, 13], [8, 13], [1, 7], [1, 8], [13, 7], [13, 8], [3, 3], [12, 3], [3, 12], [12, 12]].forEach(function (q) { put(g, q[0], q[1], "a"); });
    },
    leaf: function (g) {
      poly(g, [3, 12, 3.5, 7, 6.5, 3.5, 12.5, 2.5, 12, 8, 8.5, 11.5], "b"); line(g, 4, 11, 11, 4, "a", 1);
      line(g, 2, 13, 3, 12, "a", 1); put(g, 7, 9, "a"); put(g, 9, 5, "a");
    },
    snowflake: function (g) {
      line(g, 7, 2, 7, 13, "b", 2); line(g, 3, 4, 12, 11, "b", 1); line(g, 3, 11, 12, 4, "b", 1);
      stamp(g, 5, 2, "b....b|.b..b."); stamp(g, 5, 12, ".b..b.|b....b"); put(g, 7, 7, "a"); put(g, 8, 8, "a");
    }
  };

  // [id, glyph or item shape, c1, c2?, c3?]
  var SKILL_GLYPHS = [
    ["attack", "sword", "#a3abb0", "#7a5532"], ["strength", "fist", "#d9a77a", "#2f8a3a"],
    ["defence", "shield", "#4a6ad0", "#d4dadd"], ["hitpoints", "heart", "#e04848", "#8a1818"],
    ["woodcutting", "tree", "#3f6d2a", "#5a3b22"], ["mining", "pickaxe", "#6d6a66", "#7a5532"],
    ["fishing", "fish", "#4a8ad0", "#2a5a90", "#a8d0f0"], ["smithing", "anvil", "#6d6a66", "#4a4846"],
    ["cooking", "pot", "#4a4846", "#e08020"], ["firemaking", "flame", "#e08020", "#ffd050", "#fff4c0"],
    ["crafting", "chisel", "#a3abb0", "#b07a3a"], ["total", "star", "#e8c040"]
  ];
  var TAB_GLYPHS = [
    ["combat", "swords", "#a3abb0", "#8a5a30"], ["skills", "bars", "#4a8ad0", "#2f8a3a", "#e8c040"],
    ["quests", "scroll", "#e3d4aa", "#c02838"], ["inventory", "satchel", "#8a5a30", "#e8c040"],
    ["equipment", "helm", "#a3abb0"], ["options", "wrench", "#9a9792"]
  ];
  var SLOT_GLYPHS = [["head", "helm"], ["cape", "cape"], ["neck", "amulet"], ["weapon", "sword"], ["body", "breastplate"],
    ["shield", "shield"], ["legs", "greaves"], ["hands", "gloves"], ["feet", "boots"], ["ring", "ring"]];
  var SEASON_GLYPHS = [
    ["spring", "blossom", "#f4a8c0", "#e8c040"], ["summer", "sun", "#f8c838", "#f0a020"],
    ["autumn", "leaf", "#d8702a", "#7a3a16"], ["winter", "snowflake", "#dcecff", "#8ab0d8"]
  ];

  // ----------------------------------------------------------------
  // -------------------------- Map glyphs --------------------------
  // ----------------------------------------------------------------

  // 7x7 masks: a round badge (b) with a 3x3 symbol (a). kind -> [badge, symbol, symbol rows].
  var BADGE = [".ooooo.", "obbbbbo", "obbbbbo", "obbbbbo", "obbbbbo", "obbbbbo", ".ooooo."];
  var MAP_SYM = {
    bank: ["#e8c040", "#6a4a10", "aaa|a.a|aaa"], shop: ["#3f8f3a", "#ffffff", ".a.|aaa|aaa"],
    general: ["#8a5a30", "#ffffff", ".a.|aaa|aaa"], quest: ["#3a5fa0", "#ffffff", ".a.|.a.|..."],
    anvil: ["#5b5852", "#d4dadd", "aaa|.a.|aaa"], furnace: ["#5b5852", "#ffb050", ".a.|aaa|aaa"],
    range: ["#7a5532", "#ffb050", "aaa|aaa|.a."], fish: ["#2f5f8f", "#ffffff", ".aa|aaa|.aa"],
    mine: ["#6c512d", "#d4dadd", "aaa|.a.|.a."], woodcut: ["#2d5120", "#a8bf5a", ".a.|aaa|.a."],
    ladder: ["#7a5532", "#e3d0a0", "a.a|aaa|a.a"], shrine: ["#8a2a2a", "#ffd050", ".a.|aaa|.a."],
    tanner: ["#a5844f", "#4a3a2a", "a.a|.a.|a.a"]
  };

  function mapGlyph(kind) {
    if (typeof kind !== "string" || !Util.has(MAP_SYM, kind)) return [];
    var g = { w: 7, h: 7, c: BADGE.map(function (r) { return r.split(""); }) };
    stamp(g, 2, 2, MAP_SYM[kind][2]);
    if (kind === "quest") put(g, 3, 5, "a");
    return g.c.map(function (r) { return r.join(""); });
  }

  // Map glyph at (x, y), s device px per mask px.
  function paintGlyph(ctx, kind, x, y, s) {
    var rows = mapGlyph(kind);
    if (rows.length) paintRows(ctx, rows, x, y, s, { o: OUTLINE, b: MAP_SYM[kind][0], a: MAP_SYM[kind][1] }, false);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Atlas -----------------------------
  // ----------------------------------------------------------------

  var SHAPES = {};
  (Data.vocab && Array.isArray(Data.vocab.item) ? Data.vocab.item : []).concat(["misc"]).forEach(function (id) {
    if (id === "coins") SHAPES.coins = coinPile(COIN_STACKS[4]);
    else if (Util.has(DRAW, id)) SHAPES[id] = make(DRAW[id]);
  });

  var cells = [], ITEM = {}, COIN_CELL = [], SKILL = {}, TAB = {}, SLOT = {}, SEASON = {};

  function addCell(rows, pal) { return cells.push({ rows: rows, pal: pal }) - 1; }

  function glyphRows(kind) { return Util.has(GLYPH_DRAW, kind) ? make(GLYPH_DRAW[kind]) : SHAPES[kind] || SHAPES.misc; }

  var MISC_CELL = addCell(SHAPES.misc, palette("#8a7a5a", "#d8d0b8"));
  COIN_STACKS.forEach(function (st) { COIN_CELL.push(addCell(coinPile(st), palette("#e8c040", "#a07a18", "#f8e070"))); });
  Object.keys(Data.items || {}).forEach(function (id) {
    var icon = Data.items[id] && Array.isArray(Data.items[id].icon) ? Data.items[id].icon : null;
    if (id === "coins") ITEM[id] = COIN_CELL[4];
    else if (!icon || !Util.has(SHAPES, icon[0]) || typeof icon[1] !== "string") ITEM[id] = MISC_CELL;
    else ITEM[id] = addCell(SHAPES[icon[0]], palette(icon[1], icon[2], icon[3]));
  });
  SKILL_GLYPHS.forEach(function (s) { SKILL[s[0]] = addCell(glyphRows(s[1]), palette(s[2], s[3], s[4])); });
  TAB_GLYPHS.forEach(function (t) { TAB[t[0]] = addCell(glyphRows(t[1]), palette(t[2], t[3], t[4])); });
  SLOT_GLYPHS.forEach(function (t) { SLOT[t[0]] = addCell(glyphRows(t[1]), palette("#8a8478", "#6a655c")); });
  SEASON_GLYPHS.forEach(function (t) { SEASON[t[0]] = addCell(glyphRows(t[1]), palette(t[2], t[3])); });

  var ROWS = Math.ceil(cells.length / COLS), api = { k: 1 }, dataUrl = "", base1 = null, cellCv = {};

  function canvas(w, h) {
    var cv = document.createElement("canvas");
    cv.width = Math.max(1, w);
    cv.height = Math.max(1, h);
    return cv;
  }

  // Builds the atlas at k = max(1, floor(2 dpr)) device px per art px and installs the .ico rule
  // (background-size = atlas art px x 2, for 32-css cells). At a fractional dpr (1.25, 1.75: Windows scaling)
  // a 32-css cell is not a whole number of device px per art px, so .ico gets zoom k / (2 dpr): every art px
  // is then exactly k device px (25.6 css cells at 1.25) instead of a mix of 2- and 3-px columns.
  function init(dpr) {
    var d = typeof dpr === "number" && dpr > 0 ? dpr : 1, z;
    api.k = Math.max(1, Math.floor(2 * d));
    z = api.k / (2 * d);
    if (!base1) {
      base1 = canvas(COLS * CELL, ROWS * CELL);
      cells.forEach(function (c, i) { paintRows(base1.getContext("2d"), c.rows, (i % COLS) * CELL, Math.floor(i / COLS) * CELL, 1, c.pal, false); });
    }
    var cv = canvas(base1.width * api.k, base1.height * api.k), ctx = cv.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(base1, 0, 0, cv.width, cv.height);
    dataUrl = cv.toDataURL("image/png");
    var el = document.getElementById("atlas");
    if (!el) {
      el = document.createElement("style");
      el.id = "atlas";
      document.head.appendChild(el);
    }
    el.textContent = ".ico{background-image:url(" + dataUrl + ");background-size:" + base1.width * 2 + "px " + base1.height * 2 +
      "px;background-repeat:no-repeat;image-rendering:pixelated}" + (Math.abs(z - 1) > 1e-6 ? ".ico{zoom:" + z + "}.i16 .ico{zoom:1}" : "");
  }

  function url() { return dataUrl; }

  function cellOf(itemId, qty) {
    if (itemId === "coins") return COIN_CELL[coinVariant(qty)];
    return typeof itemId === "string" && Util.has(ITEM, itemId) ? ITEM[itemId] : MISC_CELL;
  }

  // background-position for a cell shown at px css, plus the scaled atlas size when px is not 32.
  function cellCss(cell, px) {
    var out = "background-position:" + -((cell % COLS) * px) + "px " + -(Math.floor(cell / COLS) * px) + "px";
    return px === CSS_CELL ? out : out + ";background-size:" + COLS * px + "px " + ROWS * px + "px";
  }

  function size(cssPx, dflt) { return typeof cssPx === "number" && cssPx > 0 ? cssPx : dflt; }

  function css(itemId, qty) { return cellCss(cellOf(itemId, qty), CSS_CELL); }

  function skillCss(skillId, cssPx) { return cellCss(Util.has(SKILL, skillId) ? SKILL[skillId] : SKILL.total, size(cssPx, 16)); }

  // Tab glyphs default to 16 css (one css px per art px: crisp at every dpr).
  function tabCss(tabId, cssPx) { return cellCss(Util.has(TAB, tabId) ? TAB[tabId] : MISC_CELL, size(cssPx, 16)); }

  // Season glyph (status strip chip), 16 css by default; unknown ids show the summer sun.
  function seasonCss(id, cssPx) { return cellCss(Util.has(SEASON, id) ? SEASON[id] : SEASON.summer, size(cssPx, 16)); }

  // Empty equipment-slot glyph (a grey item silhouette) for a 32-css cell.
  function slotCss(slot) { return cellCss(Util.has(SLOT, slot) ? SLOT[slot] : MISC_CELL, CSS_CELL); }

  // A 16x16 art-px canvas of one cell (cached).
  function cellCanvas(cell) {
    if (!Util.has(cellCv, cell)) {
      cellCv[cell] = canvas(CELL, CELL);
      paintRows(cellCv[cell].getContext("2d"), cells[cell].rows, 0, 0, 1, cells[cell].pal, false);
    }
    return cellCv[cell];
  }

  function blit(ctx, cv, x, y, s) {
    var prev = ctx.imageSmoothingEnabled;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(cv, Math.round(x), Math.round(y), CELL * s, CELL * s);
    ctx.imageSmoothingEnabled = prev;
  }

  // Item icon at (x, y), scale px per art px; qty picks the coin pile.
  function paint(ctx, itemId, x, y, scale, qty) { blit(ctx, cellCanvas(cellOf(itemId, qty)), x, y, size(scale, 1)); }

  function paintSkill(ctx, skillId, x, y, scale) {
    blit(ctx, cellCanvas(Util.has(SKILL, skillId) ? SKILL[skillId] : SKILL.total), x, y, size(scale, 1));
  }

  // The 16x16 icon canvas of an item (Render: ground items and their hover outline).
  function itemCanvas(itemId, qty) { return cellCanvas(cellOf(itemId, qty)); }

  return {
    get k() { return api.k; },
    SHAPES: SHAPES, init: init, url: url, css: css, paint: paint, skillCss: skillCss, tabCss: tabCss, seasonCss: seasonCss,
    mapGlyph: mapGlyph, slotCss: slotCss, paintGlyph: paintGlyph, paintSkill: paintSkill, itemCanvas: itemCanvas,
    lib: { grid: grid, stamp: stamp, finish: finish, paintRows: paintRows, ramp: ramp, mix: mix, OUTLINE: OUTLINE }
  };
})();
// ==== src/ui/sprites.js ====
// ----------------------------------------------------------------
// --------------- Sprites: procedural pixel sprites --------------
// ----------------------------------------------------------------
// World sprites (DESIGN.md 18.5): the paper-doll player and humanoids, monsters, trees, rocks, fishing
// spots, stations, quest objects and decor. Built from integer colour grids, outlined in #1b140d with
// light from the top-left, painted once into small art-px canvases and cached. Masks are "|"-joined
// rows: b/a are auto-shaded (c1/c2), other letters are FIXED colours, 1/2/3 cycle a glow per frame.
// Sprite = { cv, ax, ay, w, h, box }: (ax, ay) = the tile's bottom-centre, box = opaque bounds.
const Sprites = (function () {
  "use strict";

  var L = Icons.lib;
  var OUT = L.OUTLINE;
  var SKIN = ["#f0c8a0", "#d9a77a", "#a8734a", "#6e4a2e"];
  // Character creation palettes; index 0 is the original look and the sizes match Rules.LOOK.
  var LOOK_PAL = {
    skin: ["#f0c8a0", "#e2b48a", "#d9a77a", "#a8734a", "#8a5a36", "#6e4a2e"],
    hairCol: ["#5a3b22", "#2a1d14", "#c9a050", "#a0502a", "#8c8c8c", "#e6dcc8", "#6e2626", "#3d5f9e"],
    top: ["#3a5fa0", "#a03a3a", "#3a8a4a", "#8a6a2a", "#6a3a8a", "#c8bca4", "#363636", "#b8682a"],
    legs: ["#6a4a2a", "#3a3a3a", "#2a3a6a", "#4a5a2a", "#7a6a5a", "#5a2a2a"]
  };
  var HAIR_STYLES = ["Short", "Long", "Spiky", "Bald", "Ponytail"];
  var GLOW = ["#e08020", "#ffb050", "#ffe070"];
  var DX = 5, DY = 5;   // paper-doll frame offset inside its canvas (room for tools)
  var HUMANOID = { human: 1, guard: 1, robed: 1, smith: 1 };
  var FIXED = {
    k: OUT, e: "#f0ece0", r: "#c02838", y: "#e8c040", g: "#ffb050", G: "#ffe070", f: "#e08020", F: "#b8433a",
    Y: "#fff4c0", p: "#e89a8a", t: "#e8e0c8", i: "#6d6a66", j: "#9a9792", I: "#4a4846", n: "#5a3b22", N: "#3f2915",
    m: "#7a5333", u: "#7a5532", U: "#5a3c22", v: "#9a7048", x: "#7e7b73", X: "#5b5852", z: "#9d9a90", q: "#cdb67e",
    Q: "#a9925e", c: "#8a2a2a", C: "#3a5fa0", A: "#23446d", B: "#2f5f8f", D: "#5089bb", E: "#b4d0e6", K: "#2a2522",
    P: "#6b6660", R: "#4e4a45", w: "#ffffff", Z: "#e8fff8"
  };
  var cache = {}, count = 0, missing = {};

  function canvas(w, h) {
    var cv = document.createElement("canvas");
    cv.width = Math.max(1, w);
    cv.height = Math.max(1, h);
    return cv;
  }

  function remember(key, fn) {
    if (Util.has(cache, key)) return cache[key];
    if (count >= 4000) flush();
    count++;
    return (cache[key] = fn());
  }

  function flush() { cache = {}; count = 0; }

  function rows(str) { return str.split("|"); }

  // Mask palette: b/h/s from c1, a/l/d from c2, 1/2/3 = the glow cycle at frame f, plus FIXED.
  function pal(c1, c2, f, extra) {
    var p = {}, k;
    for (k in FIXED) if (Util.has(FIXED, k)) p[k] = FIXED[k];
    var r = L.ramp(c1 || "#888888"), q = L.ramp(c2 || r[0]);
    p.o = OUT; p.b = c1 || "#888888"; p.s = r[0]; p.h = r[1]; p.a = c2 || r[0]; p.d = q[0]; p.l = q[1];
    for (var i = 0; i < 3; i++) p[i + 1] = GLOW[((f | 0) + i) % 3];
    if (extra) for (k in extra) if (Util.has(extra, k)) p[k] = extra[k];
    return p;
  }

  function hash(n) {
    var x = Math.imul((n | 0) ^ 0x5bd1e995, 0x165667b1) + 668265263;
    x = Math.imul(x ^ (x >>> 13), 1274126177);
    return (x ^ (x >>> 16)) >>> 0;
  }

  // ----------------------------------------------------------------
  // ------------------------- Colour grids -------------------------
  // ----------------------------------------------------------------

  function cgrid(w, h) {
    var c = new Array(w * h);
    for (var i = 0; i < c.length; i++) c[i] = null;
    return { w: w, h: h, c: c };
  }

  function cset(g, x, y, col) {
    if (col && x >= 0 && y >= 0 && x < g.w && y < g.h) g.c[y * g.w + x] = col;
  }

  function crect(g, x, y, w, h, col) {
    for (var j = 0; j < h; j++) for (var i = 0; i < w; i++) cset(g, x + i, y + j, col);
  }

  // Processed mask rows -> colours at (ox, oy).
  function crows(g, rs, p, ox, oy) {
    for (var j = 0; j < rs.length; j++) {
      for (var i = 0; i < rs[j].length; i++) {
        var ch = rs[j].charAt(i);
        if (ch !== "." && Util.has(p, ch)) cset(g, ox + i, oy + j, p[ch]);
      }
    }
  }

  // Auto-outline: every empty cell beside a filled one.
  function coutline(g) {
    var s = g.c.slice(), w = g.w;
    for (var i = 0; i < s.length; i++) {
      if (s[i]) continue;
      var x = i % w;
      if ((i >= w && s[i - w]) || (i + w < s.length && s[i + w]) || (x > 0 && s[i - 1]) || (x < w - 1 && s[i + 1])) {
        g.c[i] = OUT;
      }
    }
  }

  function cpaint(ctx, g, s, flip) {
    for (var y = 0; y < g.h; y++) {
      for (var x = 0, k; x < g.w; x = k) {
        var col = g.c[y * g.w + x];
        for (k = x + 1; k < g.w && g.c[y * g.w + k] === col;) k++;
        if (!col) continue;
        ctx.fillStyle = col;
        ctx.fillRect((flip ? g.w - k : x) * s, y * s, (k - x) * s, s);
      }
    }
  }

  function cbox(g, flip) {
    var x0 = g.w, y0 = g.h, x1 = -1, y1 = -1;
    for (var i = 0; i < g.c.length; i++) {
      if (!g.c[i]) continue;
      var x = i % g.w, y = (i - x) / g.w;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    return x1 < 0 ? [0, 0, 1, 1] : [flip ? g.w - 1 - x1 : x0, y0, x1 - x0 + 1, y1 - y0 + 1];
  }

  // Span-filled ellipse in the rect (x, y, w, h), straight onto a canvas (shadows).
  function spanEllipse(ctx, x, y, w, h, s, col) {
    ctx.fillStyle = col;
    for (var j = 0; j < h; j++) {
      var v = (j + 0.5 - h / 2) / (h / 2);
      var dx = Math.round((w / 2) * Math.sqrt(Math.max(0, 1 - v * v)));
      if (dx > 0) ctx.fillRect((x + w / 2 - dx) * s, (y + j) * s, dx * 2 * s, s);
    }
  }

  // Sprite from a colour grid. o: { shadow: [x, y, w, h], shade, scale, flip, outline }.
  function toSprite(g, ax, ay, o) {
    var opt = o || {}, s = opt.scale || 1, flip = !!opt.flip, sh = opt.shadow;
    if (opt.outline !== false) coutline(g);
    var cv = canvas(g.w * s, g.h * s), ctx = cv.getContext("2d");
    if (sh) spanEllipse(ctx, flip ? g.w - sh[0] - sh[2] : sh[0], sh[1], sh[2], sh[3], s, opt.shade || "rgba(0,0,0,0.3)");
    cpaint(ctx, g, s, flip);
    var b = cbox(g, flip);
    return { cv: cv, ax: (flip ? g.w - ax : ax) * s, ay: ay * s, w: cv.width, h: cv.height,
      box: [b[0] * s, b[1] * s, b[2] * s, b[3] * s] };
  }

  // Raw mask rows (b/a auto-shaded and outlined by finish) -> colour grid, padded by 1 for the outline.
  function maskGrid(rs, p) {
    var w = 0;
    rs.forEach(function (r) { w = Math.max(w, r.length); });
    var mg = L.grid(w + 2, rs.length + 2);
    L.stamp(mg, 1, 1, rs);
    var g = cgrid(mg.w, mg.h);
    crows(g, L.finish(mg, true), p, 0, 0);
    return g;
  }

  // Mask sprite standing on its tile; lift = px between the sprite bottom and the tile bottom.
  function maskSprite(m, p, lift, shadow) {
    var g = maskGrid(rows(m), p);
    return toSprite(g, Math.round(g.w / 2), g.h + (lift || 0),
      { outline: false, shadow: shadow === false ? null : [1, g.h - 4, g.w - 2, 3] });
  }

  // ----------------------------------------------------------------
  // ------------------------ Held tool masks -----------------------
  // ----------------------------------------------------------------

  // Upright (head at the top; the grip is the bottom row's handle). b/s/h = tier, a = handle.
  var TOOL = {
    sword: ".h.|.h.|.h.|.h.|.h.|.h.|.b.|sbs|.a.|.a.",   // a bright blade: it must read against a same-tier body
    axe: "..hb|.abs|.abs|.a..|.a..|.a..|.a..|.a..|.a..|.a..",
    pickaxe: ".hbs.|h.a.s|..a..|..a..|..a..|..a..|..a..|..a..|..a..",
    hammer: "hbbs|bbss|.a..|.a..|.a..|.a..|.a..|.a..",
    rod: ".b|.b|.b|.b|.b|.b|.b|.b|bb|bb",
    harpoon: "h.h|.b.|hbs|.a.|.a.|.a.|.a.|.a.|.a.|.a.|.a.",
    net: ".aaa.|abebo|aebea|.aaa.|..a..|..a..|..a..|..a..|..a..",
    spear: ".j.|.j.|jjj|.n.|.n.|.n.|.n.|.n.|.n.|.n.|.n.|.n.|.n.",
    dagger: ".h.|.h.|.h.|sbs|.a.",
    mace: "h.s|hbs|hbs|.s.|.a.|.a.|.a.|.a.",
    cleaver: "hhhb|hhhb|hhbs|hbs.|.a..|.a..|.a..",
    // Two-handed: a 2-wide blade, a 4-wide guard, a long grip and a pommel (12 rows).
    greatsword: ".h..|.hh.|.hh.|.hh.|.hh.|.hh.|.hh.|.hh.|sbbs|.a..|.a..|.b.."
  };
  var TOOL_SHAPE = { sword: 1, axe: 1, pickaxe: 1, hammer: 1, rod: 1, harpoon: 1, net: 1, dagger: 1, mace: 1, cleaver: 1,
    greatsword: 1 };
  var TWO_HANDED = { greatsword: 1 };

  // Turns an upright mask: "cw" points it right, "down" points it down.
  function rotate(rs, how) {
    if (how !== "cw" && how !== "down") return rs;
    var h = rs.length, w = 0, out = [];
    rs.forEach(function (r) { w = Math.max(w, r.length); });
    function at(cx, cy) { return rs[cy].charAt(cx) || "."; }
    for (var y = 0; y < (how === "cw" ? w : h); y++) {
      out.push("");
      for (var x = 0; x < (how === "cw" ? h : w); x++) out[y] += how === "cw" ? at(y, h - 1 - x) : at(w - 1 - x, h - 1 - y);
    }
    return out;
  }

  // Places a tool so its grip lands on (hx, hy); returns the tool-head cell (for particles).
  function placeTool(g, kind, cols, hx, hy, how) {
    var rs = rows(TOOL[kind]), h = rs.length, w = 0;
    rs.forEach(function (r) { w = Math.max(w, r.length); });
    var last = rs[h - 1], gc = Math.max(last.indexOf("a"), last.indexOf("n"), last.indexOf("b"));
    var x0 = hx - gc, y0 = hy - (h - 1), head = [hx, y0];
    if (how === "cw") { x0 = hx; y0 = hy - gc; head = [hx + h - 1, hy]; }
    if (how === "down") { x0 = hx - (w - 1 - gc); y0 = hy; head = [hx, hy + h - 1]; }
    var t = L.ramp(cols.c1);
    var p = { b: cols.c1, s: t[0], h: t[1], a: cols.c2 || "#7a5532", e: "#d8d0b8", o: OUT, j: FIXED.j, n: FIXED.u };
    crows(g, rotate(rs, how), p, x0, y0);
    return head;
  }

  // ----------------------------------------------------------------
  // --------------------------- Paper doll -------------------------
  // ----------------------------------------------------------------

  function item(id) {
    var ic = typeof id === "string" && Util.has(Data.items, id) ? Data.items[id].icon : null;
    return Array.isArray(ic) ? { shape: ic[0], c1: ic[1], c2: ic[2] } : null;
  }

  // Look of a humanoid: colours per part plus held items, from equipment or NPC draw data.
  function lookFromEq(eq, look) {
    var k = look || {};
    var pick = function (part) { var a = LOOK_PAL[part], i = k[part]; return a[i >= 0 && i < a.length ? i : 0]; };
    var e = eq || {}, lk = { skin: pick("skin"), hair: pick("hairCol"), torso: pick("top"), legs: pick("legs"),
      feet: "#3f2915", hairStyle: k.hair > 0 && k.hair < HAIR_STYLES.length ? k.hair : 0 };
    var body = item(e.body), legs = item(e.legs), feet = item(e.feet), hands = item(e.hands), cape = item(e.cape);
    var head = item(e.head), neck = item(e.neck), wp = item(e.weapon);
    if (body) { lk.torso = body.c1; lk.metalBody = body.shape === "breastplate"; }
    if (legs) { lk.legs = legs.c1; lk.metalLegs = legs.shape === "greaves"; }
    if (feet) lk.feet = feet.c1;
    if (hands) lk.hands = hands.c1;
    if (cape) lk.cape = [cape.c1, cape.c2 || cape.c1];
    if (head) lk.helm = head.c1;
    if (neck) lk.neck = [neck.c1, neck.c2 || neck.c1];
    lk.shield = item(e.shield);
    if (wp && Util.has(TOOL_SHAPE, wp.shape)) lk.tool = { kind: wp.shape, cols: wp };
    lk.twoHand = !!(wp && Util.has(TWO_HANDED, wp.shape));
    return lk;
  }

  // NPC humanoids: c1 torso, c2 legs/trim, c3 accessory colour; skin by the id's char-code sum.
  function lookFromNpc(id, d) {
    var dr = d.draw, lk = lookFromEq(null), n = 0;
    for (var i = 0; i < id.length; i++) n += id.charCodeAt(i);
    lk.skin = SKIN[n % 4];
    lk.hair = ["#5a3b22", "#3f2915", "#8a6a3a"][id.length % 3];
    lk.torso = dr[1] || lk.torso;
    lk.legs = dr[2] || lk.legs;
    lk.acc = dr[4] || null;
    lk.accCol = dr[3] || "#d8d0b8";
    if (lk.acc === "chain") lk.neck = [lk.accCol, lk.accCol];   // drawn like a worn amulet
    if (dr[0] === "guard") {
      lk.helm = "#a3abb0"; lk.tabard = dr[1]; lk.torso = "#727a80"; lk.arms = "#a3abb0"; lk.metalLegs = true;
      lk.tool = { kind: "spear", cols: { c1: "#9a9792", c2: "#7a5532" } };
    } else if (dr[0] === "robed") {
      lk.robe = true; lk.trim = dr[2] || "#e8c040"; lk.legs = dr[1];
    } else if (dr[0] === "smith") {
      lk.arms = lk.skin;
    }
    if (d.combat && dr[0] === "human") lk.tool = { kind: "sword", cols: { c1: "#6d6a66", c2: "#5a3c22" } };
    return lk;
  }

  var PARTICLE = { chop: "#a5844f", mine: "#ffe070", smith: "#ffe070", smelt: "#ffe070", fish: "#b4d0e6",
    cook: "#9a9a9a", fire: "#9a9a9a", craft: "#ffe070" };

  // frame & 7: 0 stand, 1/2 walk, 3/4 action raise/strike, 5 blink; block/eat/cast pick their own pose.
  function poseOf(frame, anim) {
    var f = frame & 7;
    if (f === 1 || f === 2) return f === 1 ? "walkA" : "walkB";
    if (anim === "block" || anim === "eat" || anim === "cast") return anim;
    return f === 3 ? "raise" : f === 4 ? "strike" : "stand";
  }

  // The 16x24 frame (DESIGN.md 18.5) in a grid at (DX, DY), with p.R / p.B (shaded) rect helpers.
  function doll(look, view, frame, anim) {
    var lk = {}, k;
    for (k in look) if (Util.has(look, k)) lk[k] = look[k];
    if (!lk.arms) lk.arms = L.ramp(lk.torso)[0];
    var g = cgrid(26, 29), pose = poseOf(frame, anim);
    var o = { x: DX, y: DY + (pose === "walkA" || pose === "walkB" ? -1 : 0) };
    var p = { g: g, O: o, lk: lk, pose: pose, blink: (frame & 7) === 5, anim: anim,
      swing: pose === "walkA" ? 1 : pose === "walkB" ? -1 : 0, hand: lk.hands || lk.skin };
    p.R = function (x, y, w, h, c) { crect(g, o.x + x, o.y + y, w, h, c); };
    p.B = function (x, y, w, h, c) {
      var t = L.ramp(c);
      p.R(x, y, w, h, c);
      if (w > 2) { p.R(x, y, 1, h, t[1]); p.R(x + w - 1, y, 1, h, t[0]); }
    };
    p.tool = function (hx, hy, how) {
      return lk.tool ? placeTool(g, lk.tool.kind, lk.tool.cols, o.x + hx, o.y + hy, how) : null;
    };
    if (view === "back") dollBack(p);
    else if (view === "side") dollSide(p);
    else dollFront(p);
    return g;
  }

  function legs(p, xs) {
    var lk = p.lk, lift = p.pose === "walkA" ? 0 : p.pose === "walkB" ? 1 : -1;
    xs.forEach(function (x, i) {
      var up = lift === i ? 1 : 0;
      p.B(x, 15, 3, 6 - up, lk.legs);
      if (lk.metalLegs) p.R(x, 17 - up, 3, 1, L.ramp(lk.legs)[1]);
      p.R(x, 21 - up, 3, 1, lk.feet);
    });
  }

  // Legs and torso, or a robe down to y 21.
  function lower(p, x, w, xs) {
    var lk = p.lk;
    if (!lk.robe) {
      legs(p, xs);
      p.B(x, 8, w, 7, lk.torso);
      p.R(x, 14, w, 1, L.ramp(lk.torso)[0]);
      if (lk.metalBody) {   // plate: shaded flanks and a shoulder seam, so it does not merge into helm and greaves
        var ts = L.ramp(lk.torso)[0];
        p.R(x + w - 2, 9, 1, 5, ts); p.R(x, 8, w, 1, ts); p.R(x + 1, 9, 1, 5, L.ramp(lk.torso)[1]);
      }
      return;
    }
    p.B(x, 8, w, 13, lk.torso);
    p.R(x - 1, 18, w + 2, 3, lk.torso);
    p.R(x - 1, 20, w + 2, 1, lk.trim);
    p.R(x, 14, w, 1, lk.trim);
  }

  function headwear(p, view) {
    var lk = p.lk, c = lk.accCol;
    if (lk.helm) {
      var t = L.ramp(lk.helm);
      p.R(4, 1, 8, 7, lk.helm); p.R(4, 1, 1, 7, t[1]); p.R(11, 1, 1, 7, t[0]); p.R(5, 1, 6, 1, t[1]);
      p.R(5, 2, 2, 1, t[1]); p.R(4, 7, 8, 1, t[0]);   // top-left gleam; a darker rim parts the helm from the body
      if (view === "front") { p.R(5, 4, 6, 1, OUT); p.R(7, 5, 2, 2, OUT); p.R(7, 5, 2, 1, lk.skin); }   // T-visor
      if (view === "side") { p.R(8, 4, 3, 1, OUT); p.R(10, 5, 1, 1, lk.skin); }
    }
    if (lk.acc === "hood") {
      p.R(4, 1, 8, view === "back" ? 7 : 4, c); p.R(4, 5, 1, 3, c); p.R(11, 5, 1, 3, c);
    } else if (lk.acc === "cook_hat") {
      p.R(4, 0, 8, 2, c); p.R(5, -2, 6, 2, c);
    } else if (lk.acc === "straw_hat") {
      p.R(3, 1, 10, 2, c); p.R(5, 0, 6, 1, c); p.R(3, 2, 10, 1, L.ramp(c)[0]);
    } else if (lk.acc === "plume") {
      p.R(9, -1, 2, 3, c);
    }
  }

  // Hair by style: 0 short, 1 long, 2 spiky, 3 bald, 4 ponytail (NPC looks have no style: short).
  function hair(p, view) {
    var lk = p.lk, h = lk.hair, st = lk.hairStyle | 0;
    if (st === 3) {
      if (view === "back") { p.R(5, 1, 6, 7, lk.skin); p.R(5, 1, 6, 1, L.ramp(lk.skin)[0]); }
      else p.R(5, 1, 6, 1, lk.skin);
      return;
    }
    if (view === "back") {
      p.R(5, 1, 6, st === 1 ? 9 : 7, h);
      if (st === 4) p.R(7, 8, 2, 4, h);
    } else if (view === "side") {
      p.R(5, 1, 6, st === 2 ? 1 : 2, h); p.R(5, 3, 2, st === 1 ? 5 : 3, h);
      if (st === 2) p.R(5, 2, 2, 1, h);
      if (st === 4) p.R(4, 4, 1, 5, h);
    } else {
      p.R(5, 1, 6, st === 2 ? 1 : 2, h);
      p.R(5, 3, 1, st === 1 ? 5 : 2, h); p.R(10, 3, 1, st === 1 ? 5 : 2, h);
      if (st === 2) { p.R(5, 2, 1, 1, h); p.R(10, 2, 1, 1, h); }
    }
    if (st === 2) { p.R(5, 0, 1, 1, h); p.R(7, 0, 1, 1, h); p.R(9, 0, 1, 1, h); }
  }

  function face(p, back) {
    var lk = p.lk, shade = L.ramp(lk.skin)[0];
    if (back) hair(p, "back");
    else {
      p.R(5, 2, 6, 6, lk.skin); p.R(5, 7, 6, 1, shade);
      p.R(6, 5, 1, 1, p.blink ? shade : OUT); p.R(9, 5, 1, 1, p.blink ? shade : OUT);
      hair(p, "front");
    }
    headwear(p, back ? "back" : "front");
  }

  // A shield with a dark rim (so a same-tier breastplate behind it does not swallow it) and a bright boss.
  function shieldAt(p, x, y, w, h) {
    var sh = p.lk.shield;
    if (!sh) return;
    var t = L.ramp(sh.c1);
    p.R(x, y, w, h, sh.c1); p.R(x, y, 1, h, t[1]); p.R(x + w - 1, y, 1, h, t[0]);
    p.R(x + 1, y + h, Math.max(1, w - 2), 1, t[0]);
    if (w > 2) {
      p.R(x - 1, y, 1, h, OUT); p.R(x + w, y, 1, h, OUT); p.R(x, y + h, 1, 1, OUT); p.R(x + w - 1, y + h, 1, 1, OUT);
      p.R(x + 1, y + h + 1, w - 2, 1, OUT);
    }
    p.R(x + Math.floor(w / 2) - (w > 3 ? 1 : 0), y + Math.floor(h / 2) - 1, w > 3 ? 2 : 1, 2, sh.c2 || t[1]);
  }

  // A 1-px arm of h rows with the hand below it (or above it when raised).
  function arm(p, x, y, h, raised) {
    p.R(x, y, 1, h, p.lk.arms);
    p.R(x, raised ? y - 1 : y + h, 1, 1, p.hand);
  }

  // Work particles at the tool head on strike frames; cast sparkles.
  function sparks(p, at) {
    if (at && p.pose === "strike" && Util.has(PARTICLE, p.anim)) {
      cset(p.g, at[0] - 1, at[1] - 2, PARTICLE[p.anim]);
      cset(p.g, at[0] + 2, at[1] - 1, PARTICLE[p.anim]);
    }
    if (p.pose === "cast") [[2, 1], [13, 1], [7, -1]].forEach(function (c) { cset(p.g, p.O.x + c[0], p.O.y + c[1], "#ffe070"); });
  }

  function cape(p) {
    var cp = p.lk.cape;
    if (cp) { p.B(3, 8, 10, 11, cp[0]); p.R(3, 18, 10, 1, cp[1]); }
  }

  // Front: the right hand (tool) is on screen left, the shield on screen right.
  function dollFront(p) {
    var lk = p.lk, pose = p.pose, sw = p.swing, at = null;
    cape(p);
    lower(p, 4, 8, [5, 8]);
    if (lk.metalBody) p.R(7, 9, 2, 4, L.ramp(lk.torso)[1]);
    if (lk.tabard) { p.R(6, 8, 4, 8, lk.tabard); p.R(6, 15, 4, 1, L.ramp(lk.tabard)[0]); }
    if (lk.acc === "apron") p.R(5, 10, 6, 6, lk.accCol);
    if (lk.neck) { p.R(6, 9, 1, 1, lk.neck[0]); p.R(9, 9, 1, 1, lk.neck[0]); p.R(7, 10, 2, 1, lk.neck[1]); }
    if (lk.twoHand && pose !== "eat" && pose !== "cast") {
      at = twoHandFront(p);
      face(p, false);
      sparks(p, at);
      return;
    }
    if (pose === "raise" || pose === "cast") {
      arm(p, 3, 4, 6, true);
      if (pose === "raise") at = p.tool(2, 4, "up");
    } else if (pose === "strike") {
      p.R(3, 9, 1, 4, lk.arms); p.R(4, 12, 2, 1, lk.arms); p.R(6, 12, 1, 1, p.hand);
      at = p.tool(6, 12, "down") || [p.O.x + 6, p.O.y + 13];
    } else if (pose === "eat") {
      p.R(3, 9, 1, 2, lk.arms); p.R(4, 7, 2, 2, lk.arms); p.R(6, 6, 1, 1, p.hand);
    } else {
      arm(p, 3, 9 + sw, 5, false);
      at = p.tool(2, 14 + sw, "up");
    }
    if (pose === "cast") arm(p, 12, 4, 6, true);
    else arm(p, 12, 9 - sw, 5, false);
    if (pose === "block") shieldAt(p, 6, 8, 5, 6);
    else shieldAt(p, 11, 10 - sw, 4, 6);
    face(p, false);
    sparks(p, at);
  }

  // Two-handed weapons, front view: at rest the blade stands point-down before the body with both hands on the
  // hilt; raised, it rises over the right shoulder; the strike sweeps it level across the waist.
  function twoHandFront(p) {
    var lk = p.lk, pose = p.pose, at;
    if (pose === "raise") {
      arm(p, 3, 7, 3, true); arm(p, 12, 9, 5, false);
      return p.tool(3, 6, "up");
    }
    if (pose === "strike") {
      p.R(3, 9, 1, 3, lk.arms); p.R(12, 9, 1, 2, lk.arms); p.R(7, 11, 5, 1, lk.arms);
      at = p.tool(3, 12, "cw");
      p.R(4, 12, 1, 1, p.hand); p.R(6, 12, 1, 1, p.hand);
      return at;
    }
    p.R(3, 9, 1, 2, lk.arms); p.R(4, 11, 3, 1, lk.arms); p.R(12, 9, 1, 2, lk.arms); p.R(10, 11, 2, 1, lk.arms);
    at = p.tool(8, 10, "down");
    p.R(7, 11, 1, 1, p.hand); p.R(9, 11, 1, 1, p.hand);
    return at;
  }

  // Back: held items are in front of the character, so behind the body from this side.
  function dollBack(p) {
    var lk = p.lk, pose = p.pose, sw = p.swing, at = null;
    if (pose === "stand" || pose === "walkA" || pose === "walkB") p.tool(13, 14 - sw, "up");
    if (pose !== "block") shieldAt(p, 1, 10 + sw, 4, 6);
    lower(p, 4, 8, [5, 8]);
    if (lk.tabard) p.R(6, 8, 4, 8, lk.tabard);
    arm(p, 3, 9 + sw, 5, false);
    if (pose === "raise" || pose === "cast") {
      arm(p, 12, 4, 6, true);
      if (pose === "raise") at = p.tool(12, 4, "up");
    } else if (pose === "strike") {
      p.R(11, 6, 1, 4, lk.arms); p.R(10, 5, 1, 1, p.hand);
      at = p.tool(10, 6, "up");
    } else {
      arm(p, 12, 9 - sw, 5, false);
    }
    face(p, true);
    cape(p);
    if (pose === "block") shieldAt(p, 5, 8, 6, 6);
    sparks(p, at);
  }

  // Side view facing right (left = mirror). Torso 6 px wide.
  function dollSide(p) {
    var lk = p.lk, pose = p.pose, sw = p.swing, at = null;
    if (lk.cape) p.B(3, 8, 3, 11, lk.cape[0]);
    if (lk.robe) lower(p, 5, 6, []);
    else {
      var a = pose === "walkA" ? 2 : 0;
      p.B(7 - a, 15, 2, 6, L.ramp(lk.legs)[0]); p.R(7 - a, 21, 3, 1, L.ramp(lk.feet)[0]);
      p.B(7 + a, 15, 2, 6, lk.legs); p.R(7 + a, 21, 3, 1, lk.feet);
      p.B(5, 8, 6, 7, lk.torso); p.R(5, 14, 6, 1, L.ramp(lk.torso)[0]);
    }
    if (lk.tabard) p.R(7, 8, 4, 8, lk.tabard);
    if (lk.acc === "apron") p.R(9, 10, 2, 6, lk.accCol);
    if (pose !== "block") shieldAt(p, 10, 9, 2, 6);
    p.R(5, 2, 6, 6, lk.skin); p.R(11, 5, 1, 1, lk.skin);
    hair(p, "side");
    p.R(9, 5, 1, 1, p.blink ? L.ramp(lk.skin)[0] : OUT);
    headwear(p, "side");
    if (lk.twoHand && pose !== "eat" && pose !== "cast" && pose !== "block") {
      sparks(p, twoHandSide(p));
      return;
    }
    if (pose === "raise" || pose === "cast") {
      p.R(7, 4, 2, 5, lk.arms); p.R(7, 3, 2, 1, p.hand);
      if (pose === "raise") at = p.tool(7, 4, "up");
    } else if (pose === "strike") {
      p.R(8, 10, 4, 2, lk.arms); p.R(12, 10, 1, 2, p.hand);
      at = p.tool(12, 11, "cw") || [p.O.x + 13, p.O.y + 11];
    } else if (pose === "eat") {
      p.R(8, 8, 2, 3, lk.arms); p.R(10, 6, 1, 2, p.hand);
    } else if (pose === "block") {
      p.R(8, 9, 3, 2, lk.arms); shieldAt(p, 11, 7, 2, 7);
    } else {
      p.R(7 + sw, 9, 2, 5, lk.arms); p.R(7 + sw, 14, 2, 1, p.hand);
      at = p.tool(8 + sw, 14, "up");
    }
    sparks(p, at);
  }

  // Two-handed weapons, side view (facing right): point-down before the legs at rest, high over the head when
  // raised, thrust level ahead on the strike. Both hands sit on the grip.
  function twoHandSide(p) {
    var lk = p.lk, pose = p.pose, at;
    if (pose === "raise") {
      p.R(7, 5, 2, 4, lk.arms);
      at = p.tool(7, 6, "up");
      p.R(7, 4, 2, 1, p.hand);
      return at;
    }
    if (pose === "strike") {
      p.R(8, 10, 2, 2, lk.arms);
      at = p.tool(9, 11, "cw");
      p.R(10, 11, 2, 1, p.hand);
      return at;
    }
    p.R(8, 9, 2, 2, lk.arms); p.R(9, 11, 1, 1, lk.arms);
    at = p.tool(11, 10, "down");
    p.R(10, 11, 1, 2, p.hand);
    return at;
  }

  // face 0 = back, 4 = front, 1-3 = right side, 5-7 = left side (a mirror).
  function viewOf(face) {
    var f = face | 0;
    return f === 0 ? { view: "back", flip: false } : f === 4 ? { view: "front", flip: false } : { view: "side", flip: f >= 5 };
  }

  function dollSprite(lk, face, frame, anim, scale) {
    var v = viewOf(face);
    var sp = toSprite(doll(lk, v.view, frame, anim), DX + 8, DY + 24,
      { flip: v.flip, scale: scale || 1, shadow: [DX + 4, DY + 22, 8, 2], shade: "rgba(0,0,0,0.35)" });
    return frame & 8 ? flashOf(sp) : sp;
  }

  function eqKey(eq) {
    return eq ? [eq.head, eq.cape, eq.neck, eq.weapon, eq.body, eq.shield, eq.legs, eq.hands, eq.feet].join(",") : "";
  }

  // frame: 0 stand, 1/2 walk, 3/4 action raise/strike, 5 blink; +8 = the white hit flash.
  function lookKey(look) {
    var k = look || {};
    return [k.skin | 0, k.hair | 0, k.hairCol | 0, k.top | 0, k.legs | 0].join(".");
  }

  function player(eq, face, frame, anim, look) {
    var key = "p|" + eqKey(eq) + "|" + lookKey(look) + "|" + (face | 0) + "|" + (frame | 0) + "|" + (anim || "");
    return remember(key, function () { return dollSprite(lookFromEq(eq, look), face, frame | 0, anim); });
  }

  // ----------------------------------------------------------------
  // ---------------------------- Monsters --------------------------
  // ----------------------------------------------------------------

  // Facing right: [first leg row, mask]. Walk splits the legs front/back.
  var MONSTERS = {
    chicken: [7, "....aa..|...bbbb.|...bkbby|bb.bbbba|bbbbbbb.|.bbbbbb.|..bbbb..|..y..y.."],
    cow: [9, "...............t.t|..............bbbb|.bbbbbbbbbbbbbbkbb|bbbbaaabbbbbbbbbbb|b.baaaabbbbaabbbpp|" +
      "b.bbaabbbbbaaabbpp|a.bbbbbbbbbbbbb...|..bbbbbbbbbbbbb...|..bbbbppbbbbbbb...|..bb.bb....bb.bb..|" +
      "..bb.bb....bb.bb..|..kk.kk....kk.kk.."],
    goblin: [12, ".........j.|........jjj|...bbbb..n.|b.bbbbbb.n.|bbbkbbkbbn.|.bbbbbbb.n.|..brrrb..n.|..aaaaa.bn.|" +
      ".baaaaaabn.|.b.aaaa..n.|...aaaa..n.|...a..a..n.|...b..b..n.|..bb..bb.n."],
    crab: [6, "bb.........bb|bbb.......bbb|.bb.k...k.bb.|..bbbbbbbbb..|.bbbaaaaabbb.|..bbbbbbbbb..|.a.a.....a.a.|" +
      "a.a.......a.a"],
    spider: [4, "..b.b...b.b..|.b.bbbbbbb.b.|b.bbaabbbrbb.b|.bbbbabbbbbbb.|b.b.bbbbb.b.b.|b.b.......b.b."],
    skeleton: [12, "...bbbb...|..bbbbbb..|..bkbbkb..|..bbbbbb..|...b.b.b..|....bb....|.bb.bbbb.j|b...bab..j|" +
      "b...bbb..j|b...bab.bj|b....b...i|....bbb...|....b.b...|....b.b...|....b.b...|...bb.bb.."],
    wolf: [7, ".............b....|............bbb...|a...........bbbbb.|aa..aaaaaaaabbkbbb|.aaabbbbbbbbbbbbbk|" +
      "..bbbbbbbbbbbbbe..|..bbbbbbbbbbbbb...|..bb.bb...bb.bb...|..bb.bb...bb.bb...|..kk.kk...kk.kk..."],
    ogre: [17, "......bbbbb.......|.....bbbbbbb......|.....bkbbbkb......|.....bbbbbbb......|.....btbbbtb......|" +
      "......bbbbb.......|...bbbbbbbbbbb.nn.|..bbbbbbbbbbbbbnn.|.bbbbaaaaaaabbbnn.|.bbbbaaaaaaabbbnn.|" +
      ".bb.baaaaaaab.bnn.|.bb.baaaaaaab.bnn.|.bb.bbbbbbbbb.bnn.|bbb.aaaaaaaaa.bbn.|bbb.aaaaaaaaa..nn.|" +
      "....aaaaaaaaa..nn.|....aaaa.aaaa..nn.|.....bbb.bbb......|.....bbb.bbb......|.....bbb.bbb......|" +
      ".....bbb.bbb......|....bbbb.bbbb....."],
    lurker: [6, ".........aaaa.|.bbbbbbbbaaaaa|bbbbbbbbbbaaaa|bbabbabbabbbaa|.bbbbbbbbbbbbt|..bbbbbbbbbbt.|" +
      "..b.b.b.b.b..."],
    imp: [9, ".b.....b.|.bb...bb.|..bbbbb..|..bGbGb..|..bbbbb..|a..bbb..a|aabbbbbaa|.a.bbb.a.|...bbb...|" +
      "...b.b...|..bb.bb.."],
    golem: [15, "......bbbbb.....|.....bbbbbbb....|.....bGbbbGb....|......bbabb.....|..bbbbbbbbbbbb..|" +
      ".bbbbbabbbabbbb.|bbbbbbbaabbbbbbb|bbbb.baabbab.bbb|bbbb.bbbabbb.bbb|bab..bbbbbbb..ba|bbb..babbbbb..bb|" +
      ".a...bbbabbb...a|.....bbbbbbb....|.....bbb.bbb....|.....bbb.bbb....|....bbbb.bbbb...|....aaaa.aaaa..."],
    // Backswept horns, an open glowing jaw, a raised membrane wing (F/g struts), a glowing belly and a curled tail.
    wyrm: [17, "......tb......t...t.....|.......bb......tt..t....|......Fgbb.......tbbb...|.....Fggbb......bbbGbbb.|" +
      "...FggggFbb.....bbbbbbbb|..FgFFggFbb......bbbbtbt|.FgFFgFgFFbb.....bbbfGGf|.gFFFgFgFFbb.....bbbbtb.|" +
      "...FgFFgFFFbb...bbbb....|....g.FgFFFbb..bbbb.....|.......gbbbbbbbbb.......|.......bbbbbbbbbbbb.....|" +
      "......bbbbgbbbbbgbbb....|.....bbbbbbbbgbbbbbb....|...bbbbbbbbbbbbbbbbb....|.bbbb.bbaaaaaaaaabb.....|" +
      "bbb....bbaaaaaaabb......|b..a...bbbb....bbb......|bbbaa..bbb.....bbb......|......bbbbbt...bbbbt...."]
  };
  var SIDE_ONLY = { chicken: 1, cow: 1, crab: 1, spider: 1, wolf: 1, lurker: 1, wyrm: 1 };

  // Walk splits the legs; attack lunges 2 px forward. anim "cast" on a wyrm = the breath telegraph.
  function monster(kind, d, face, frame, anim, mask) {
    var m = mask || MONSTERS[kind], f = frame & 7, glow = kind === "wyrm" && anim === "cast";
    var base = maskGrid(rows(m[1]), pal(d.draw[1], d.draw[2], 0, glow ? { G: "#ffffff", t: "#ffe070" } : null));
    var g = cgrid(base.w + 4, base.h + 1), dy = f === 1 || f === 2 ? 0 : 1, dx = f === 4 ? 3 : 1;
    for (var i = 0; i < base.c.length; i++) {
      if (!base.c[i]) continue;
      var x = i % base.w, y = (i - x) / base.w;
      var sx = y > m[0] && (f === 1 || f === 2) ? (x < base.w / 2 ? 1 : -1) * (f === 1 ? 1 : -1) : 0;
      cset(g, x + dx + sx, y + dy, base.c[i]);
    }
    if (glow) for (var k = 0; k < 4; k++) cset(g, g.w - 3 + (k % 2), 6 + k, GLOW[1 + (k % 2)]);
    var sp = toSprite(g, Math.round(g.w / 2), g.h - 1, { outline: false, flip: viewOf(face).flip,
      scale: d.scale === 2 ? 2 : 1, shadow: [2, g.h - 3, g.w - 4, 3] });
    return frame & 8 ? flashOf(sp) : sp;
  }

  // frame: 0 idle, 1/2 walk, 3/4 attack wind-up/strike, 5 blink; +8 = the white hit flash.
  function npc(npcId, face, frame, anim) {
    if (typeof npcId !== "string" || !Util.has(Data.npcs, npcId)) return blank();
    var d = Data.npcs[npcId], kind = Array.isArray(d.draw) ? d.draw[0] : "";
    return remember("n|" + npcId + "|" + (face | 0) + "|" + (frame | 0) + "|" + (anim || ""), function () {
      if (Util.has(HUMANOID, kind)) return dollSprite(lookFromNpc(npcId, d), face, frame | 0, anim, d.scale === 2 ? 2 : 1);
      if (Util.has(MONSTERS, kind)) return monster(kind, d, face, frame | 0, anim);
      missing[kind] = 1;
      return blank();
    });
  }

  // A monster mask at two-thirds size for a pet: a cell fills when half its source block is filled, and
  // keeps a feature (an eye, a glow) over the body colours, else the block's commonest colour.
  function miniMask(m) {
    var src = rows(m[1]), w = 0, out = [];
    src.forEach(function (r) { w = Math.max(w, r.length); });
    var mw = Math.ceil(w * 2 / 3), mh = Math.ceil(src.length * 2 / 3);
    for (var j = 0; j < mh; j++) {
      var line = "";
      for (var i = 0; i < mw; i++) {
        var x0 = Math.floor(i * 1.5), x1 = Math.max(x0 + 1, Math.floor((i + 1) * 1.5));
        var y0 = Math.floor(j * 1.5), y1 = Math.max(y0 + 1, Math.floor((j + 1) * 1.5));
        var n = 0, feat = "", best = "", tally = {};
        for (var y = y0; y < y1; y++) {
          for (var x = x0; x < x1; x++) {
            var ch = (src[y] || "").charAt(x) || ".";
            n++;
            if (ch === ".") continue;
            tally[ch] = (tally[ch] || 0) + 1;
            if (!feat && ch !== "a" && ch !== "b") feat = ch;
            if (!best || tally[ch] > tally[best]) best = ch;
          }
        }
        var filled = 0;
        Object.keys(tally).forEach(function (k) { filled += tally[k]; });
        line += filled * 2 >= n ? feat || best : ".";
      }
      out.push(line);
    }
    return [Math.floor(m[0] * 2 / 3), out.join("|")];
  }

  // A summoned pet in its growth stage (0 young, 1 adult, 2 mythic): the young form is its kind's monster at
  // two-thirds size, the adult full size in its own colours, the mythic form full size with its edge in
  // its detail colour (a glow).
  function pet(petId, face, frame, stage) {
    var d = typeof petId === "string" && Data.pets && Util.has(Data.pets, petId) ? Data.pets[petId] : null;
    if (!d) return blank();
    var st = Math.max(0, Math.min(2, stage | 0)), g = st > 0 && Array.isArray(d.grows) ? d.grows[st - 1] : null;
    var form = g && Array.isArray(g.draw) ? g : d, kind = Array.isArray(form.draw) ? form.draw[0] : "";
    if (!Util.has(MONSTERS, kind)) {
      missing[kind] = 1;
      return blank();
    }
    return remember("p|" + petId + "|" + st + "|" + (face | 0) + "|" + (frame | 0), function () {
      var sp = monster(kind, form, face, frame | 0, null, st > 0 ? null : miniMask(MONSTERS[kind]));
      return st >= 2 ? outline(sp, form.draw[2] || "#ffe9a0") : sp;
    });
  }

  // ----------------------------------------------------------------
  // ----------------------------- Trees ----------------------------
  // ----------------------------------------------------------------

  var FOLIAGE = {
    tree: ["#3f6d2a", "#2d5120", "#5d903a"], oak: ["#4b6b24", "#34501a", "#6c8f33"],
    willow: ["#7f9a3f", "#5f7a2e", "#a8bf5a"], maple: ["#b5532a", "#8a3a1e", "#e07a3a"],
    yew: ["#2b4a33", "#1d3524", "#3f6a48"], ironbark: ["#3f8f8a", "#2a6662", "#79cfc6"],
    amber: ["#d0902a", "#9a6018", "#f0c050"]
  };
  // [w, h, lobes [cx, cy, r], trunk [x, y, w, h]]
  var TREE = {
    tree: [22, 30, [[11, 10, 7], [6, 14, 6], [15, 14, 6]], [9, 19, 4, 9]],
    oak: [28, 32, [[14, 9, 7], [7, 13, 6], [21, 13, 6], [14, 15, 7]], [12, 21, 5, 9]],
    willow: [26, 32, [[13, 9, 7], [7, 12, 5], [19, 12, 5]], [11, 18, 4, 12]],
    maple: [22, 30, [[11, 10, 7], [6, 14, 5], [16, 14, 5]], [9, 19, 4, 9]],
    ironbark: [22, 30, [[11, 9, 7], [6, 13, 6], [16, 13, 6]], [9, 18, 4, 10]],
    amber: [26, 32, [[13, 9, 7], [7, 13, 6], [19, 13, 6], [13, 15, 6]], [11, 20, 4, 10]]
  };
  var BARK = ["#5a3b22", "#3f2915", "#7a5333"];

  // ----------------------------------------------------------------
  // ---------------------------- Seasons ---------------------------
  // ----------------------------------------------------------------
  // Render sets the season (Engine.view.season id) every frame; object sprites are cached per season.
  // Spring freshens the leaves and dots canopies with blossom, autumn turns them (a palette per tree seed),
  // winter frosts them and lays snow along the top edge of outdoor objects.
  var SEASON_IDS = { spring: 1, summer: 1, autumn: 1, winter: 1 };
  var SNOW = ["#f4f8fb", "#d6e2ea"];
  var FOL_SEASON = {
    spring: { tree: [["#4a8a2e", "#356a22", "#74b048"]], oak: [["#58842a", "#3e641e", "#82ac40"]],
      willow: [["#8fb048", "#6c8c34", "#bcd468"]] },
    autumn: { tree: [["#c8702a", "#9a4c1c", "#eca048"], ["#c89a2a", "#98701a", "#ecc456"], ["#b4442a", "#86301c", "#dc6a40"]],
      oak: [["#a8702a", "#7c501c", "#cc9640"], ["#9a5a26", "#70401a", "#c47c3a"]], willow: [["#b8a83a", "#8c8028", "#dccc62"]],
      maple: [["#a8301e", "#781e14", "#d84e30"]], amber: [["#d8702a", "#a04c18", "#f8a848"]] },
    winter: { tree: [["#4f6452", "#36463a", SNOW[1]]], oak: [["#56604a", "#3c4434", SNOW[1]]],
      willow: [["#68745a", "#4a5440", SNOW[1]]], maple: [["#6a5048", "#4a3832", SNOW[1]]], yew: [["#2b4a33", "#1d3524", SNOW[1]]],
      amber: [["#9a7040", "#6a4a28", SNOW[1]]] }
  };
  var BLOOM = { tree: 1, oak: 1, maple: 1 };
  var NO_SNOW = { fire: 1, torch: 1, fish_spot: 1, shrine: 1 };
  var FLOWER_COLS = {
    spring: ["#f4a8c0", "#ffffff", "#e8c040", "#b890e0", "#f07890"],
    autumn: ["#c8502a", "#e8a030", "#a0522d", "#d8b040", "#e07040"]
  };
  var season = "summer";

  function setSeason(id) { season = typeof id === "string" && Util.has(SEASON_IDS, id) ? id : "summer"; }

  // [base, dark, light] of a foliage kind this season; seed picks among a season's palettes.
  function foliage(kind, seed) {
    var by = Util.has(FOL_SEASON, season) ? FOL_SEASON[season] : null;
    if (!by || !Util.has(by, kind)) return FOLIAGE[kind];
    return by[kind][(seed | 0) % by[kind].length];
  }

  // Spring blossom [shade, bright] for a tree seed: pink on odd seeds, white on even ones.
  function bloomOf(kind, seed) {
    if (season !== "spring" || !Util.has(BLOOM, kind)) return null;
    return seed & 1 ? ["#e890b0", "#fbd0de"] : ["#f0d4de", "#fff6f8"];
  }

  // Winter: snow on the top edge of a sprite (the first solid pixel of each column, under its outline), two
  // deep in places when thick. Read once per cached sprite; painted with integer fillRects.
  function snowCap(sp, thick) {
    var w = sp.cv.width, h = sp.cv.height, cx = sp.cv.getContext("2d"), d = cx.getImageData(0, 0, w, h).data;
    function solid(x, y) {
      var i = (y * w + x) * 4;
      return y < h && d[i + 3] === 255 && !(d[i] === 0x1b && d[i + 1] === 0x14 && d[i + 2] === 0x0d);
    }
    for (var x = 0; x < w; x++) {
      var y = 0;
      while (y < h && d[(y * w + x) * 4 + 3] < 255) y++;
      if (y < h && !solid(x, y)) y++;
      if (!solid(x, y)) continue;
      cx.fillStyle = SNOW[0];
      cx.fillRect(x, y, 1, 1);
      if (thick && solid(x, y + 1) && hash(x * 13 + w) % 3) { cx.fillStyle = SNOW[1]; cx.fillRect(x, y + 1, 1, 1); }
    }
    return sp;
  }

  // Lobes lit from the top-left (seed & 1 shifts the light) with seeded leaf clumps and, in spring, blossom.
  function canopy(g, lobes, fol, seed, bloom) {
    var owner = new Array(g.w * g.h);
    lobes.forEach(function (lb, li) {
      for (var y = Math.floor(lb[1] - lb[2]); y <= lb[1] + lb[2]; y++) {
        for (var x = Math.floor(lb[0] - lb[2]); x <= lb[0] + lb[2]; x++) {
          var dx = x + 0.5 - lb[0], dy = y + 0.5 - lb[1];
          if (dx * dx + dy * dy <= lb[2] * lb[2] && x >= 0 && y >= 0 && x < g.w && y < g.h) owner[y * g.w + x] = li + 1;
        }
      }
    });
    for (var i = 0; i < owner.length; i++) {
      if (!owner[i]) continue;
      var lb = lobes[owner[i] - 1], x = i % g.w, y = (i - x) / g.w;
      var u = (x + 0.5 - lb[0]) / lb[2], v = (y + 0.5 - lb[1]) / lb[2];
      var lit = -((seed & 1) ? v - u * 0.6 : u + v);
      var col = lit > 0.55 ? fol[2] : lit < -0.45 ? fol[1] : fol[0];
      var hs = hash(seed * 977 + i) % 11;
      if (hs === 0) col = col === fol[1] ? fol[0] : fol[1];
      else if (hs === 1 && lit > 0) col = fol[2];
      if (bloom && hash(seed * 389 + i) % 10 === 0) col = lit > 0.2 ? bloom[1] : bloom[0];
      g.c[i] = col;
    }
  }

  function trunk(g, x, y, w, h) {
    crect(g, x, y, w, h, BARK[0]); crect(g, x, y, 1, h, BARK[2]); crect(g, x + w - 1, y, 1, h, BARK[1]);
    cset(g, x - 1, y + h - 1, BARK[0]); cset(g, x + w, y + h - 1, BARK[1]);
  }

  // frame 100..102 = the three grow stages after a respawn; seed (0..3) varies the size and light.
  function tree(kind, seed, frame) {
    var grow = frame >= 100 && frame <= 102 ? [0.35, 0.6, 0.85][frame - 100] : 1, fol = foliage(kind, seed), g, ax, ay;
    if (kind === "yew") {
      g = cgrid(20, 34);
      trunk(g, 9, 26, 3, 5);
      [[3, 10, 4], [9, 17, 6], [15, 25, 8]].forEach(function (t, i) {
        var top = Math.round(t[0] + (1 - grow) * 14);
        for (var y = top; y <= t[1] + 1; y++) {
          var half = Math.round(((y - top) / Math.max(1, t[1] - top)) * t[2] * grow);
          for (var x = 10 - half; x <= 10 + half; x++) {
            var col = x < 10 - half / 3 ? fol[2] : x > 10 + half / 2 ? fol[1] : fol[0];
            cset(g, x, y, hash(seed * 31 + x * 7 + y * 13 + i) % 9 === 0 ? fol[1] : col);
          }
        }
      });
      ax = 10; ay = 32;
    } else {
      var sp = TREE[kind], tr = sp[3], big = seed === 1 ? 1 : seed === 2 ? -1 : 0;
      g = cgrid(sp[0], sp[1]);
      var tTop = Math.round(tr[1] + (1 - grow) * (tr[3] - 2));
      trunk(g, tr[0], tTop, tr[2], tr[1] + tr[3] - tTop);
      canopy(g, sp[2].map(function (lb, i) {
        return [lb[0], lb[1] + (1 - grow) * (tr[1] + tr[3] - lb[1] - 2), (lb[2] + (i ? 0 : big)) * grow];
      }), fol, seed, bloomOf(kind, seed));
      if (kind === "willow" && grow === 1) strands(g, fol, frame & 1, seed);
      if (kind === "ironbark" && grow === 1) {
        var spots = [[8, 6], [14, 10], [9, 14], [16, 7], [5, 12], [12, 4]];
        for (var s = 0; s < 3; s++) {
          var q = spots[(s * 2 + (frame % 3) + seed) % 6];
          cset(g, q[0], q[1], FIXED.Z);
        }
      }
      ax = Math.floor(sp[0] / 2); ay = tr[1] + tr[3] + 1;
    }
    return toSprite(g, ax, ay, { shadow: [ax - 6, ay - 3, 12, 3] });
  }

  // Willow strands hang from the canopy edge; the lower half sways 1 px on odd frames.
  function strands(g, fol, sway, seed) {
    for (var x = 3; x < g.w - 3; x += 2) {
      var top = -1;
      for (var y = 0; y < g.h; y++) if (g.c[y * g.w + x]) top = y;
      if (top < 8) continue;
      var len = 3 + (hash(seed + x) % 5);
      for (var k = 1; k <= len; k++) cset(g, x + (sway && k > len / 2 ? 1 : 0), top + k, k % 2 ? fol[1] : fol[0]);
    }
  }

  function stump() {
    var g = cgrid(12, 9);
    trunk(g, 2, 3, 8, 4);
    crect(g, 2, 2, 8, 2, "#a5844f"); crect(g, 3, 1, 6, 1, "#a5844f"); crect(g, 4, 2, 4, 1, "#8b6b3e");
    return toSprite(g, 6, 8, { shadow: [1, 5, 10, 3] });
  }

  // ----------------------------------------------------------------
  // ---------------------- Rocks and fishing -----------------------
  // ----------------------------------------------------------------

  var ROCKS = [
    "......bbbbbb......|....bbbbbbbbbb....|...bbbbbbbbbbbbb..|..bbbbbbbbbbbbbbb.|.bbbbbbbbbbbbbbbbb|" +
    ".bbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbbb|.bbbbbbbbbbbbbbbb.|..bbbbbbbbbbbbbb..",
    ".......bbbbb......|...bbbbbbbbbbb....|..bbbbbbbbbbbbbb..|.bbbbbbbbbbbbbbbb.|.bbbbbbbbbbbbbbbbb|" +
    "bbbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbbb.|.bbbbbbbbbbbbbbbb.|...bbbbbbbbbbbbb.."
  ];
  var VEINS = [[4, 3, 2, 2], [10, 2, 2, 1], [13, 5, 2, 2], [6, 6, 2, 1], [9, 7, 2, 2], [3, 7, 1, 2], [12, 8, 2, 1]];

  // A 3-tone boulder with 4-6 vein patches and a glint (no veins and 10% darker when empty);
  // frame 200 = the respawn glint.
  function rock(cols, empty, seed, frame) {
    var dk = empty ? "#524f4a" : "#5b5852";
    var g = maskGrid(rows(ROCKS[seed & 1]), pal(empty ? L.mix("#7e7b73", "#000000", 0.1) : "#7e7b73"));
    if (seed & 2) {
      var f = cgrid(g.w, g.h);
      g.c.forEach(function (c, i) { if (c) cset(f, g.w - 1 - (i % g.w), Math.floor(i / g.w), c); });
      g = f;
    }
    crect(g, 6, 7, 6, 1, dk); cset(g, 12, 6, dk); cset(g, 5, 8, dk);
    if (!empty && cols.length) {
      for (var k = 0; k < 4 + (seed % 3); k++) {
        var sp = VEINS[(k * 2 + seed) % VEINS.length], c = cols[k % cols.length];
        crect(g, sp[0] + 1, sp[1] + 1, sp[2], sp[3], c);
        cset(g, sp[0] + 1, sp[1] + 1, L.ramp(c)[1]);
      }
      cset(g, VEINS[seed][0] + 2, VEINS[seed][1] + 1, frame === 200 ? "#ffffff" : "#f0ece0");
      if (frame === 200) [[4, 2], [15, 4], [9, 1]].forEach(function (q) { cset(g, q[0], q[1], "#ffffff"); });
    }
    return toSprite(g, 10, 14, { outline: false, shadow: [2, 10, 16, 3] });
  }

  // Disturbed water with two rings growing r 2->6 (8 frames of 100 ms, the second 400 ms behind)
  // and bubbles; harpoon and deep spots grow r 3->8 and splash.
  function fishSpot(big, frame) {
    var g = cgrid(22, 14), f = frame & 7, rx = big ? 9 : 7.5, ry = big ? 5 : 4.2;
    for (var i = 0; i < g.c.length; i++) {
      var u = ((i % 22) + 0.5 - 11) / rx, v = (Math.floor(i / 22) + 0.5 - 7) / ry;
      if (u * u + v * v <= 1) g.c[i] = u * u + v * v < 0.35 ? "#5089bb" : "#3f74a6";
    }
    [f, (f + 4) & 7].forEach(function (ph) {
      var r = (big ? 3 : 2) + Math.round((ph / 7) * (big ? 5 : 4));
      ring(g, 11, 7, r, Math.max(1, Math.round(r * 0.55)), ph < 3 ? "#ffffff" : ph < 6 ? FIXED.E : "#8fb6d8");
    });
    var bub = [[9, 6], [13, 7], [11, 5], [12, 8]];
    crect(g, bub[f % 4][0], bub[f % 4][1], 2, 1, "#ffffff");
    cset(g, bub[(f + 2) % 4][0] - 1, bub[(f + 2) % 4][1], FIXED.E);
    cset(g, bub[(f + 1) % 4][0] + 1, bub[(f + 1) % 4][1] - 1, "#ffffff");
    if (big && f % 4 && f % 4 !== 3) {
      cset(g, 10, 3 - (f & 1), "#ffffff"); cset(g, 12, 2 + (f & 1), "#ffffff"); cset(g, 14, 4, FIXED.E); cset(g, 8, 4, FIXED.E);
    }
    return toSprite(g, 11, 15, { outline: false });
  }

  function ring(g, cx, cy, rx, ry, col) {
    for (var y = -ry; y <= ry; y++) {
      var dx = Math.round(rx * Math.sqrt(Math.max(0, 1 - (y / ry) * (y / ry))));
      if (Math.abs(y) === ry) crect(g, cx - dx, cy + y, dx * 2 + 1, 1, col);
      else { cset(g, cx - dx, cy + y, col); cset(g, cx + dx, cy + y, col); }
    }
  }

  // ----------------------------------------------------------------
  // ------------------ Stations, quest objects, decor --------------
  // ----------------------------------------------------------------

  // kind -> [c1, c2, mask, lift (px above the tile bottom), shadow (false = none)]
  var OBJ = {
    bank_booth: ["#7a5532", "#9a9792", ".iiiiiiiiiiiiii.|.i.i.i.i.i.i.ii.|.i.i.i.i.i.i.ii.|.i.i.i.i.i.i.ii.|" +
      "bbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbb|bUUUUUUUUUUUUUUb|bbbbbbbbbbbbbbbb|bbbbbbbyybbbbbbb|bbbbbbbbbbbbbbbb|" +
      "bbbbbbbbbbbbbbbb|UUUUUUUUUUUUUUUU", 0],
    anvil: ["#6d6a66", "#5a3b22", "bbbbbbbbbbbbb.|.bbbbbbbbbbbbb|....bbbbbbb...|.....bbbbb....|.....bbbbb....|" +
      "...aaaaaaaa...|..aaaaaaaaaa..|..aaaaaaaaaa..", 1],
    gravestone: ["#7e7b73", "#5a8532", "...bbbb...|..bbbbbb..|.bbbbbbbb.|.bbbXXbbb.|.bbXXXXbb.|.bbbXXbbb.|" +
      ".bbbXXbbb.|.bbbbbbbb.|.bbbbbbbb.|aaaaaaaaaa", 1],
    counter: ["#7a5532", "#5a3c22", "bbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbb|UUUUUUUUUUUUUUUU|aaaaaaaaaaaaaaaa|" +
      "aaaUaaaaaaaaUaaa|aaaUaaaaaaaaUaaa|aaaUaaaaaaaaUaaa|aaaaaaaaaaaaaaaa", 1],
    table: ["#7a5532", "#5a3c22", "......tt........|bbbbbbttbbbbbbbb|bbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbb|" +
      "UUUUUUUUUUUUUUUU|.aa..........aa.|.aa..........aa.|.aa..........aa.", 1],
    crate: ["#9a7048", "#5a3c22", "bbbbbbbbbbbb|baaaaaaaaaab|bbbbbbbbbbbb|bab......bab|ba.b....b.ab|ba..b..b..ab|" +
      "ba...bb...ab|ba..b..b..ab|ba.b....b.ab|bab......bab|bbbbbbbbbbbb", 1],
    barrel: ["#7a5532", "#6d6a66", "..bbbbbb..|.bUUUUUUb.|.aaaaaaaa.|bbbbbbbbbb|bbbbbbbbbb|aaaaaaaaaa|bbbbbbbbbb|" +
      "bbbbbbbbbb|.aaaaaaaa.|.bbbbbbbb.", 1],
    sign: ["#7a5532", "#e3d0a0", ".....bb.....|aaaaaaaaaaa.|akkakkkaakaa|aaaaaaaaaaa.|.....bb.....|.aaaaaaaaaaa|" +
      "aakakkakkaka|.aaaaaaaaaaa|.....bb.....|.....bb.....|.....bb.....|.....bb.....|....bbbb....", 1],
    statue: ["#9d9a90", "#7e7b73", "....bbb.....|...bbbbb....|...bbbbb....|....bbb.....|..bbbbbbb...|.bbbbbbbbb..|" +
      ".b.bbbbb.b..|.b.bbbbb.b..|...bbbbb.b..|...bbbbb....|...bb.bb....|...bb.bb....|...bb.bb....|..bbb.bbb...|" +
      "aaaaaaaaaaa.|aaaaaaaaaaa.|aaaaaaaaaaa.|aaaaaaaaaaa.", 1],
    rubble: ["#7e7b73", "#5b5852", "...bb.......|..bbbb..bb..|.bbaab.bbbb.|bbbbaa.abbb.|..aa.bbb.aa.", 3],
    tent: ["#a5844f", "#7a5532", ".........n.........|........bbs........|.......bbbss.......|......bbbbsss......|" +
      ".....bbbbbssss.....|....bbbbbbsssss....|...bbbbbbkkssss....|...bbbbbkkkksss....|..bbbbbbkkkkssss...|" +
      "..bbbbbkkkkkksss...|.bbbbbbkkkkkkssss..|.bbbbbbkkkkkksssss.|aaaaaaakkkkkkaaaaaa", 1],
    boat: ["#7a5532", "#5a3c22", "bbbbbbbbbbbbbbbbbbbb|baaaaaaaaaaaaaaaaaab|bauuuuuuuuuuuuuuuuab|.bbbbbbbbbbbbbbbbbb.|" +
      "..aaaaaaaaaaaaaaaa..|...aaaaaaaaaaaaaa...", 2, false],
    stalagmite: ["#5b5852", "#4a4440", "....b....|....b....|...bb....|...bbb...|...bbb...|..bbbbb..|..bbbab..|" +
      "..bbbbb..|.bbbabbb.|.bbbbbbb.|bbbabbbbb|aaaaaaaaa", 1],
    well: ["#7e7b73", "#7a5532", ".aaaaaaaaaaaaa..|aaaaaaaaaaaaaaa.|.a.....i.....a..|.a.....i.....a..|.a....jjj....a..|" +
      ".a...........a..|..bbbbbbbbbbb...|.bbBBBBBBBBBbb..|bbBAAAAAAAAABbb.|bbbBBBBBBBBBbbb.|bbbbbbbbbbbbbbb.|" +
      "bxbbbxbbbbxbbbb.|.bbbbbbbbbbbbb..", 1],
    ladder_up: ["#7a5532", "#9a7048", "b......b|baaaaaab|b......b|b......b|baaaaaab|b......b|b......b|baaaaaab|" +
      "b......b|b......b|baaaaaab|b......b|b......b|baaaaaab|b......b|b......b", 0],
    ladder_down: ["#7e7b73", "#7a5532", "..bbbbbbbbbbbb..|.bbkkkkkkkkkkbb.|bbkkaKKKKKKakkbb|bbkkaaaaaaaakkbb|" +
      "bbkkaKKKKKKakkbb|bbkkaaaaaaaakkbb|bbkkaKKKKKKakkbb|.bbkkkkkkkkkkbb.|..bbbbbbbbbbbb..", 3, false],
    gate: ["#4a4846", "#7e7b73", "aa............aa|aabbbbbbbbbbbbaa|aab.b.b.b.b.b.aa|aab.b.b.b.b.b.aa|aab.b.b.b.b.b.aa|" +
      "aabbbbbbbbbbbbaa|aab.b.b.b.b.b.aa|aab.b.b.b.b.b.aa|aab.b.byyb.b.baa|aab.b.b.b.b.b.aa|aabbbbbbbbbbbbaa|" +
      "aab.b.b.b.b.b.aa|aab.b.b.b.b.b.aa|aab.b.b.b.b.b.aa|aabbbbbbbbbbbbaa|aaaaaaaaaaaaaaaa", 0, false],
    door: ["#5a3c22", "#5b5852", "aaaaaaaaaaaaaaaa|aaaa........aaaa|aa..bbbbbbbb..aa|aa.bbbbbbbbbb.aa|aa.bbbbbbbbbb.aa|" +
      "aa.iiiiiiiiii.aa|aa.bbbbbbbbbb.aa|aa.bbbbbbbbbb.aa|aa.bbbbbbbjbb.aa|aa.bbbbbbbbbb.aa|aa.iiiiiiiiii.aa|" +
      "aa.bbbbbbbbbb.aa|aa.bbbbbbbbbb.aa|aa.bbbbbbbbbb.aa|aa.bbbbbbbbbb.aa|aaaaaaaaaaaaaaaa", 0, false],
    bush: ["#3f6d2a", "#2d5120", "....bbbbb.....|..bbbbbbbbbb..|.bbbbbbbbbbbb.|bbbbbbbbbbbbbb|bbbbbbbbbbbbbb|" +
      "abbbbbbbbbbbba|.aaaaaaaaaaaa.", 1],
    furnace: ["#7e7b73", "#5b5852", ".....aaaaaa.....|.....aaaaaa.....|.....aaaaaa.....|..bbbbbbbbbbbb..|" +
      ".bbbbbbbbbbbbbb.|bbbbbbbbbbbbbbbb|bbXbbbbXbbbbXbbb|bbbbbbbbbbbbbbbb|bbbbXbbbbXbbbbbb|bbbbbkkkkkkbbbbb|" +
      "bbbbk111111kbbbb|bbbk12222221kbbb|bbbk12333321kbbb|bbbk123YY321kbbb|bbbk123YY321kbbb|bbbk12333321kbbb|" +
      "bbbkkkkkkkkkkbbb|bbXbbbbbbbbbbXbb|bbbbbbbbbbbbbbbb|.bbbbbbbbbbbbbb.", 1],
    range: ["#4a4846", "#6d6a66", "............jj..|............ij..|..aaaaaa....ij..|..ajjjja....ij..|" +
      "..aaaaaa....ij..|bbbbbbbbbbbbbbbb|bbbbbbbbbbbbbbbb|bjjjjjjjjjjjjjjb|bkkkkkkkkkkkkkkb|bk111111111111kb|" +
      "bk122222222221kb|bk123333333321kb|bk111111111111kb|bkkkkkkkkkkkkkkb|bbbbbbbbbbbbbbbb|.bb..........bb.", 1],
    shrine: ["#9d9a90", "#7e7b73", ".....3......|....232.....|....121.....|...bbbbbb...|..bbbbbbbb..|...bbbbbb...|" +
      "...bb11bb...|...bb12bb...|...bb11bb...|...bbbbbb...|...bbbbbb...|..bbbbbbbb..|.aaaaaaaaaa.|aaaaaaaaaaaa", 1],
    torch: ["#5a3b22", "#6d6a66", "..3..|.232.|.121.|.111.|aaaaa|.bm..|.bm..|.bm..|.bm..|.bm..|.bm..|.bm..", 1],
    banner: ["#8a2a2a", "#e8c040", "mn........|mnbbbbbb..|mnbbbbbb..|mnbbttbb..|mnbbttbb..|mnbbbtbb..|mnbbbbbb..|" +
      "mnbaaaab..|mnbbbbbb..|mnbbbbbb..|mnbb..bb..|mnb....b..|mn........|mn........|mn........|mn........|" +
      "mn........|mn........|NNNN......", 0],
    banner_alt: ["#2b2118", "#4a3a2a", ".P........|kb........|kbkk......|kb.k......|kb........|kb........|" +
      "kb........|kb........|kb........|kb........|kb........|kb........|kb........|kb........|kb........|" +
      "kb........|kb........|kb........|kkkk......", 0],
    // A log-filled brazier bowl on splayed tripod legs; lit, fire() stacks the flames over the logs.
    beacon: ["#4a4846", "#6b6660", "....v..u..v...|...uvu.uu.uv..|..KuUKuUKuUK..|.aaaaaaaaaaaa.|.bbbbbbbbbbbb.|" +
      "..bbbbbbbbbb..|...bbbbbbbb...|.....bbbb.....|....b.bb.b....|...b..bb..b...|..b...bb...b..|.bb..bbbb..bb.", 1]
  };
  var FLAMES = [
    "....g.....|...gfg....|..gfYfg.g.|..fYYfgfg.|.gfYYYfff.|.fYYGYYff.|gfYGGGYffg|fFfYGYfFff",
    ".....g....|..g.gfg...|..fgfYfg..|.gfYYYffg.|.ffYGYYfg.|gfYYGGYff.|fYYGGGYfFg|fFfYGYffFf",
    "...g......|...gf..g..|..gfYg.fg.|..fYYfgfg.|gffYGYYff.|.fYYGGYfFg|gfYGGGYYff|fFffYGfFff"
  ];

  // A fire (crossed logs) or a lit beacon (the brazier) under a 3-frame flame with an ember spark.
  function fire(frame, beacon) {
    var g;
    if (beacon) {
      var bowl = maskGrid(rows(OBJ.beacon[2]), pal(OBJ.beacon[0], OBJ.beacon[1]));
      g = cgrid(bowl.w, bowl.h + 7);
      bowl.c.forEach(function (c, i) { if (c) cset(g, i % bowl.w, Math.floor(i / bowl.w) + 7, c); });
    } else {
      g = cgrid(14, 16);
      crect(g, 1, 13, 12, 2, "#4e4a45"); crect(g, 3, 14, 8, 1, "#6b6660");
      crect(g, 2, 12, 10, 2, BARK[0]); crect(g, 2, 12, 10, 1, BARK[2]); crect(g, 3, 11, 2, 1, BARK[1]); crect(g, 9, 11, 2, 1, BARK[1]);
    }
    crows(g, rows(FLAMES[frame % 3]), FIXED, beacon ? 3 : 2, beacon ? 1 : 4);
    var e = [[3, 2], [10, 1], [6, 0], [8, 3]][frame % 4];
    cset(g, e[0] + (beacon ? 1 : 0), e[1], FIXED.g);
    return toSprite(g, Math.floor(g.w / 2), beacon ? g.h + 1 : g.h - 1, { shadow: [1, g.h - 4, g.w - 2, 3] });
  }

  // A flower patch; spring has more of it, autumn turns it warm.
  function flowers(seed) {
    var g = cgrid(16, 10), cols = Util.has(FLOWER_COLS, season) ? FLOWER_COLS[season] : ["#e04848", "#e8c040", "#f0ece0", "#8a6ad0", "#e08020"];
    for (var i = 0; i < (season === "spring" ? 8 : 6); i++) {
      var h = hash(seed * 7 + i), x = 1 + (h % 13), y = 2 + ((h >> 5) % 5), c = cols[(h >> 9) % 5];
      crect(g, x, y + 2, 1, 2, "#2d5120"); cset(g, x - 1, y + 3, "#46692a");
      crect(g, x - 1, y, 3, 1, c); crect(g, x, y - 1, 1, 3, c); cset(g, x, y, "#ffe070");
    }
    return toSprite(g, 8, 13, { outline: false });
  }

  // Ripe gold most of the year; young and green in spring.
  function wheat(seed, frame) {
    var g = cgrid(18, 14), c = season === "spring" ? ["#6a9a3a", "#9ac85a", "#c4e084"] : ["#a9925e", "#e3c060", "#f0d890"];
    for (var x = 1; x < 17; x += 2) {
      var top = 1 + (hash(seed * 5 + x) % 3), sway = frame & 1 && x % 4 === 1 ? 1 : 0;
      crect(g, x, top + 3, 1, 10 - top, c[0]); crect(g, x + sway, top, 1, 3, c[1]); cset(g, x + sway, top, c[2]);
    }
    return toSprite(g, 9, 15, { outline: false });
  }

  // ----------------------------------------------------------------
  // ------------------------- Object entry -------------------------
  // ----------------------------------------------------------------

  // variant "alt" uses def.alt.draw when present, else the kind's own alt state (banner, beacon).
  // frame: ambient step (0..); 100..102 tree grow; 200 rock glint. seed & 3 picks the variant.
  function obj(objId, variant, seed, frame) {
    if (typeof objId !== "string" || !Util.has(Data.objects, objId)) return blank();
    var def = Data.objects[objId], alt = variant === "alt";
    var dr = alt && def.alt && Array.isArray(def.alt.draw) ? def.alt.draw : def.draw;
    if (!Array.isArray(dr)) return blank();
    var f = frame | 0, sd = (seed | 0) & 3, snow = season === "winter" && !Util.has(NO_SNOW, dr[0]) && !(alt && dr[0] === "beacon");
    return remember("o|" + season + "|" + objId + "|" + (alt ? 1 : 0) + "|" + sd + "|" + f, function () {
      var sp = objSprite(dr, objId, alt, sd, f);
      return snow ? snowCap(sp, Util.has(FOLIAGE, dr[0]) || dr[0] === "rock" || dr[0] === "rock_empty") : sp;
    });
  }

  function objSprite(dr, objId, alt, seed, f) {
    var kind = dr[0];
    if (Util.has(FOLIAGE, kind)) return tree(kind, seed, f);
    if (kind === "stump") return stump();
    if (kind === "rock" || kind === "rock_empty") {
      return rock(dr.slice(1).filter(function (c) { return typeof c === "string"; }), kind === "rock_empty", seed, f);
    }
    if (kind === "fish_spot") return fishSpot(objId === "spot_harpoon" || objId === "spot_deep" || objId === "spot_storm", f);
    if (kind === "fire" || (kind === "beacon" && alt)) return fire(f, kind === "beacon");
    if (kind === "flowers") return flowers(seed);
    if (kind === "wheat") return wheat(seed, f);
    var o = OBJ[kind === "banner" && alt ? "banner_alt" : kind];
    if (!o) {
      missing[kind] = 1;
      return blank();
    }
    if (kind === "bush") return bush(o, seed, f);
    return maskSprite(o[2], pal(o[0], o[1], f), o[3], o[4]);
  }

  // Autumn bushes: turning olive and ochre leaves, flecked red, orange or gold (a palette per seed).
  var AUTUMN_BUSH = [["#7a7a2e", "#585a20", "#d8603a"], ["#8a7430", "#635220", "#eca048"], ["#6e7430", "#4e5422", "#ecc456"]];

  // A bush in the season's tree colours, flecked with light leaves (blossom in spring, warm leaves in autumn).
  function bush(o, seed, f) {
    var fol = season === "autumn" ? AUTUMN_BUSH[(seed | 0) % 3] : foliage("tree", seed), bloom = bloomOf("tree", seed);
    var sp = maskSprite(o[2], pal(fol[0], fol[1], f), o[3], o[4]), cx = sp.cv.getContext("2d");
    for (var i = 0; i < (season === "autumn" ? 7 : 4); i++) {
      cx.fillStyle = bloom ? bloom[i & 1] : fol[2];
      cx.fillRect(3 + (hash(seed * 13 + i) % 10), 3 + (hash(seed * 7 + i) % 3), 1, 1);
    }
    return sp;
  }

  // Animated draw kinds: [frames, ms per frame] (Render picks the ambient frame).
  var ANIM = { fire: [3, 200], furnace: [3, 300], range: [3, 300], shrine: [3, 400], torch: [3, 200],
    fish_spot: [8, 100], willow: [2, 600], ironbark: [3, 400], wheat: [2, 900], beacon: [3, 200] };

  // ----------------------------------------------------------------
  // ----------------------- Outline and flash ----------------------
  // ----------------------------------------------------------------

  function blank() { return { cv: canvas(1, 1), ax: 0, ay: 0, w: 1, h: 1, box: [0, 0, 1, 1] }; }

  // fn(data, i, edge) on a copy; edge = an opaque pixel with a non-opaque 4-neighbour. clear: drop every
  // non-opaque pixel (the shadow) from the copy.
  function recolour(sp, fn, clear) {
    var cv = canvas(sp.w, sp.h), ctx = cv.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(sp.cv, 0, 0);
    var img = ctx.getImageData(0, 0, sp.w, sp.h), d = img.data, src = new Uint8ClampedArray(d), w = sp.w;
    function solid(x, y) { return x >= 0 && y >= 0 && x < w && y < sp.h && src[(y * w + x) * 4 + 3] === 255; }
    for (var y = 0; y < sp.h; y++) {
      for (var x = 0; x < w; x++) {
        var i = (y * w + x) * 4;
        if (src[i + 3] === 255) fn(d, i, !solid(x - 1, y) || !solid(x + 1, y) || !solid(x, y - 1) || !solid(x, y + 1));
        else if (clear) d[i + 3] = 0;
      }
    }
    ctx.putImageData(img, 0, 0);
    return { cv: cv, ax: sp.ax, ay: sp.ay, w: sp.w, h: sp.h, box: sp.box };
  }

  // 1 art px recoloured silhouette edge (the hover outline), cached on the sprite.
  function outline(sprite, color) {
    if (!sprite || !sprite.cv) return sprite;
    sprite._ol = sprite._ol || {};
    if (!Util.has(sprite._ol, color)) {
      var n = parseInt(String(color).slice(1, 7), 16) || 0;
      sprite._ol[color] = recolour(sprite, function (d, i, edge) {
        if (edge) { d[i] = (n >> 16) & 255; d[i + 1] = (n >> 8) & 255; d[i + 2] = n & 255; }
      });
    }
    return sprite._ol[color];
  }

  // The 1 art px edge alone, the rest transparent: drawn over whatever covers the sprite (18.2 occlusion).
  function edge(sprite, color) {
    if (!sprite || !sprite.cv) return sprite;
    sprite._eg = sprite._eg || {};
    if (!Util.has(sprite._eg, color)) {
      var n = parseInt(String(color).slice(1, 7), 16) || 0;
      sprite._eg[color] = recolour(sprite, function (d, i, e) {
        if (e) { d[i] = (n >> 16) & 255; d[i + 1] = (n >> 8) & 255; d[i + 2] = n & 255; } else d[i + 3] = 0;
      }, true);
    }
    return sprite._eg[color];
  }

  function flashOf(sprite) {
    return recolour(sprite, function (d, i) { d[i] = d[i + 1] = d[i + 2] = 255; });
  }

  // Draw kinds that fell back to a blank sprite (should stay empty).
  function fallbacks() { return Object.keys(missing); }

  return {
    player: player, npc: npc, pet: pet, obj: obj, outline: outline, edge: edge, flush: flush, fallbacks: fallbacks, ANIM: ANIM,
    setSeason: setSeason,
    SIDE_ONLY: SIDE_ONLY, HUMANOID: HUMANOID, DOLL: { x: DX, y: DY },
    LOOK_PAL: LOOK_PAL, HAIR_STYLES: HAIR_STYLES
  };
})();
// ==== src/ui/render.js ====
// ----------------------------------------------------------------
// ---------------- Render: world view and minimap ----------------
// ----------------------------------------------------------------
// Draws the world (DESIGN.md 18.2): terrain baked per 32x32-tile chunk, then decals, ground items and
// a y-sorted pass of objects, NPCs, the player and occluding walls into a low-res art-px buffer that is
// blitted at the integer scale S; then device-resolution overlays (hitsplats, HP bars, XP drops, click
// crosses, overheads) and the minimap. Reads state only (I1); objects come from Engine.objectAt.
const Render = (function () {
  "use strict";

  var T = 16, CHUNK = 32, MAX_BACK = 4200000, AMB_MS = 1000 / 15, LIGHT_R = 80;
  var MS = { splat: 1200, bar: 6000, xp: 1600, cross: 400, fw: 1400, over: 3000, land: 300, flash: 100, ghost: 450,
    fade: 300, ease: 200 };
  var SPLAT_AT = [[0, 0], [0, -14], [-12, 8], [12, 8]];
  var SPLAT = "...oooo...|.oobbbboo.|obbbbbbbbo|obbbbbbbbo|obbbbbbbbo|obbbbbbbbo|obbbbbbbbo|.oobbbboo.|...oooo...";
  var ARROW = ["ooooooo", "oyyyyyo", "oyyyyyo", "ooyyyoo", ".oyyyo.", ".ooyoo.", "..oyo..", "..ooo..", "...o..."];
  var FONT = "Verdana,Geneva,Tahoma,Arial,sans-serif";
  var HOVER = { npc: "#ffff00", obj: "#00ffff", grave: "#00ffff", ground: "#ff9040" };
  var SPLAT_COL = { hit: "#b81818", miss: "#2b55b0", heal: "#2c9c3c", pet: "#c47412" };
  var FLOORS = { wood_floor: 1, stone_floor: 1 }, WATER = { water: 1, deep_water: 1 };
  var FOLIAGE = { tree: 1, oak: 1, willow: 1, maple: 1, yew: 1, ironbark: 1, amber: 1 };
  var EMIT = { fire: 1, torch: 1, furnace: 1, beacon: 1, range: 1, shrine: 1 };
  var CONT = { chop: 1, mine: 1, fish: 1, smith: 1, smelt: 1, cook: 1, craft: 1, fire: 1 };
  var ANIM_TOOL = { chop: "axe", mine: "pickaxe", smith: "hammer" };
  var DIRS = [[0, -1], [1, 0], [0, 1], [-1, 0]];
  // Terrain colours [base, dark, light] (18.4) and blend priority (higher spills into lower).
  var TC = {
    grass: ["#5a8532", "#46692a", "#74a047"], grass_dark: ["#46692a", "#3a5a22", "#5a8532"],
    dirt: ["#8b6b3e", "#6c512d", "#a5844f"], path: ["#a5844f", "#8b6b3e", "#b8986a"],
    sand: ["#cdb67e", "#a9925e", "#e3d0a0"], water: ["#2f5f8f", "#23446d", "#5089bb"],
    deep_water: ["#23446d", "#1c3a60", "#2f5f8f"], wood_floor: ["#7a5532", "#5a3c22", "#8f6a42"],
    stone_floor: ["#7e7b73", "#5b5852", "#9d9a90"], ash: ["#6b6660", "#4e4a45", "#7d7871"],
    swamp: ["#4f5f3a", "#3a4a2c", "#66784c"], bog: ["#2b3f3a", "#20302c", "#3e5650"],
    wall: ["#8d8577", "#6a6458", "#b6ad9c"],
    fence: ["#7a5532", "#5a3c22", "#9a7048"], bridge: ["#7a5532", "#5a3c22", "#9a7048"],
    cave_floor: ["#4a4440", "#3a3532", "#5a524c"], cave_wall: ["#2a2522", "#1c1816", "#3a3430"],
    lava: ["#b8433a", "#8a2a24", "#ffb050"]
  };
  // Bog (swamp pools) is still water but not WATER: no foam or shore, and the swamp spills a ragged fringe into it.
  var PRIO = { deep_water: 0, water: 1, lava: 1, bog: 2, swamp: 3, sand: 4, cave_floor: 4, ash: 4, dirt: 5, path: 6,
    grass_dark: 7, grass: 8 };
  // ----------------------------------------------------------------
  // ------------- Seasons: terrain colours per season --------------
  // ----------------------------------------------------------------
  // Summer is TC. Spring greens are fresher, autumn's yellower with fallen leaves, winter's grass lies
  // under snow and paths are dusted. Chunks and the minimap image are baked per season.
  var SEASON_TC = {
    spring: { grass: ["#5f9436", "#4a7a2a", "#80b24e"], grass_dark: ["#4a7a2c", "#3a6224", "#5f9436"] },
    autumn: { grass: ["#6f8634", "#586a2a", "#8a9c48"], grass_dark: ["#57692a", "#475622", "#6f8634"] },
    winter: { grass: ["#e2eaef", "#c6d4de", "#f6fafc"], grass_dark: ["#d4dee5", "#b8c8d3", "#e8eff4"],
      swamp: ["#78887a", "#5c6c5e", "#a2b0a4"], dirt: ["#94806a", "#76644e", "#b2a490"],
      path: ["#b0a28c", "#948670", "#c8bea8"], water: ["#2c5a88", "#21456e", "#5a8cba"] }
  };
  var SNOW = ["#f4f8fb", "#e2eaef", "#c6d4de"];
  var LEAVES = ["#d8702a", "#c89a2a", "#b4442a", "#e8a040"];
  var BLOSSOM = ["#f4a8c0", "#ffffff", "#e8c040", "#fbd0de"];
  var MM_TREE = { spring: "#356a22", summer: "#2d5120", autumn: "#9a5a20", winter: "#5a6a5c" };
  var tcMemo = {};

  var cv = null, ctx = null, mm = null, mctx = null, buf = null, bctx = null, dark = null, dctx = null, lightCv = null;
  var dpr = 1, S = 2, target = 32, cssW = 0, cssH = 0, backW = 0, backH = 0, mmDiam = 100, mmPx = 2;
  var rect = null, rectAt = 0, orbsBottom = 0, layoutVer = 0;
  var inset = { cur: 0, from: 0, to: 0, at: -1e9 }, opts = { xpDrops: 1, fireworks: 1, hints: 1, motion: 0 };
  var motion = { at: -1e9, v: false };
  var fr = { bx0: 0, by0: 0, offX: 0, offY: 0, camX: 0, camY: 0 }, camMap = null, curMap = null;
  var chunks = {}, mmImg = {}, glyphCache = {}, splatCv = {}, hits = [], ents = {}, drawnNpc = {}, errSeen = {};
  var lastSig = "", lastBusy = false, lastState = null, serial = 0, overVer = 0, ambientSeen = false;
  var splats = [], bars = {}, xps = [], crosses = [], fireworks = [], overheads = {}, breaths = [], flashes = {};
  var ghosts = [], hoverRef = null, hoverMode = "normal", lastH = {}, petPos = null;
  var seenObj = {}, respawnAt = {}, spots = {}, spotGhosts = [], spotFadeUntil = 0, lavaTiles = [];
  var objEpoch = "", objCache = {}, extraTiles = {}, hintCache = { key: "", v: null }, lastAlpha = 1, xpCarry = {};
  var chevrons = {}, hatchCv = null;
  var season = "summer", tc = TC, chunkSeason = {};

  function now() { return typeof performance !== "undefined" ? performance.now() : 0; }

  function canvas(w, h) {
    var c = document.createElement("canvas");
    c.width = Math.max(1, w);
    c.height = Math.max(1, h);
    return c;
  }

  function hash(a, b, c) {
    var x = Math.imul((a | 0) ^ 0x27d4eb2d, 0x165667b1) ^ Math.imul((b | 0) + 0x61c88647, 0x27d4eb2f) ^ (c | 0);
    x = Math.imul(x ^ (x >>> 15), 0x2c1b3c6d);
    x = Math.imul(x ^ (x >>> 12), 0x297a2d39);
    return (x ^ (x >>> 15)) >>> 0;
  }

  function keys(o) { return Object.keys(o); }

  // ----------------------------------------------------------------
  // -------------------------- Setup / size ------------------------
  // ----------------------------------------------------------------

  function init(gameCanvas, minimapCanvas) {
    cv = gameCanvas || null;
    mm = minimapCanvas || null;
    ctx = cv ? cv.getContext("2d") : null;
    mctx = mm ? mm.getContext("2d") : null;
    buf = canvas(1, 1);
    bctx = buf.getContext("2d");
    dark = canvas(1, 1);
    dctx = dark.getContext("2d");
    lastSig = "";
  }

  // Backing = floor(view * dpr) device px (<= 4.2 MP); css size = backing / dpr (dpr capped at 2).
  function resize(sizes) {
    if (!sizes || !sizes.view) return;
    dpr = Math.min(typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1, 2);
    cssW = Math.max(0, sizes.view.w | 0);
    cssH = Math.max(0, sizes.view.h | 0);
    var w = Math.floor(cssW * dpr), h = Math.floor(cssH * dpr), capped = w * h > MAX_BACK;
    if (capped) {
      var f = Math.sqrt(MAX_BACK / (w * h));
      w = Math.floor(w * f);
      h = Math.floor(h * f);
    }
    backW = Math.max(1, w);
    backH = Math.max(1, h);
    // Assigning a canvas size clears it: only on a real change, and the frame is repainted below, so a drag of
    // the panel splitter never shows a blank view or minimap.
    if (cv) {
      if (cv.width !== backW) cv.width = backW;
      if (cv.height !== backH) cv.height = backH;
      cv.style.width = (capped ? cssW : backW / dpr) + "px";
      cv.style.height = (capped ? cssH : backH / dpr) + "px";
    }
    mmDiam = sizes.mmDiam > 0 ? sizes.mmDiam : 100;
    mmPx = sizes.mmPx > 0 ? sizes.mmPx : 2;
    if (mm) {
      var md = Math.max(1, Math.floor(mmDiam * dpr));
      if (mm.width !== md || mm.height !== md) mm.width = mm.height = md;
      mm.style.width = mm.style.height = mmDiam + "px";
    }
    sizeBuffers();
    setZoom(target);
    rect = null;
    layoutVer++;
    if (lastState) draw(lastState, lastAlpha, now());
  }

  function sizeBuffers() {
    if (!buf) return;
    dark.width = buf.width = Math.ceil(backW / S) + 2;
    dark.height = buf.height = Math.ceil(backH / S) + 2;
    [ctx, mctx, bctx, dctx].forEach(function (c) { if (c) c.imageSmoothingEnabled = false; });
    lastSig = "";
  }

  // Integer scales S whose css tile 16*S/dpr lies in 22..64.
  function scales() {
    var out = [];
    for (var s = 1; s <= 16; s++) if ((T * s) / dpr >= 22 - 1e-9 && (T * s) / dpr <= 64 + 1e-9) out.push(s);
    return out.length ? out : [Math.max(1, Math.round((32 * dpr) / T))];
  }

  function applyScale(s) {
    if (s !== S) {
      S = s;
      sizeBuffers();
    }
    return (T * S) / dpr;
  }

  // The scale closest to the css tile target (ties go to the larger tile).
  function setZoom(cssTile) {
    target = typeof cssTile === "number" && isFinite(cssTile) ? Math.max(22, Math.min(64, cssTile)) : 32;
    var best = 0;
    scales().forEach(function (s) {
      if (!best || Math.abs((T * s) / dpr - target) <= Math.abs((T * best) / dpr - target) + 1e-9) best = s;
    });
    return applyScale(best);
  }

  // -1 / +1 step through the allowed scales; 0 resets to the default 32 css tile.
  function zoomStep(dir) {
    if (dir === 0) return setZoom(32);
    var list = scales(), i = Math.max(0, list.indexOf(S));
    var j = Math.max(0, Math.min(list.length - 1, i + (dir > 0 ? 1 : -1)));
    target = (T * list[j]) / dpr;
    return applyScale(list[j]);
  }

  // bottom: open sheet height (the camera centres above it, 200 ms ease); orbsBottom: XP drop anchor.
  function setInsets(o) {
    if (!o) return;
    var b = Math.max(0, Number(o.bottom) || 0);
    if (typeof o.orbsBottom === "number" && isFinite(o.orbsBottom)) orbsBottom = o.orbsBottom;
    if (b !== inset.to) {
      inset.from = inset.cur;
      inset.to = b;
      inset.at = now();
    }
    lastSig = "";
  }

  // Render-only prefs from the Options tab: { xpDrops, fireworks, hints, motion: 0 auto | 1 on | 2 off }.
  function setOpts(o) {
    if (!o) return;
    ["xpDrops", "fireworks", "hints", "motion"].forEach(function (k) { if (typeof o[k] === "number") opts[k] = o[k]; });
    lastSig = "";
  }

  function reduced() {
    if (opts.motion) return opts.motion === 1;
    var t = now();
    if (t - motion.at > 1000) {
      motion.at = t;
      try { motion.v = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) {
        motion.v = false;
      }
    }
    return motion.v;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Terrain ---------------------------
  // ----------------------------------------------------------------

  function mapOf(id) { return typeof id === "string" && Util.has(World.maps, id) ? World.maps[id] : null; }

  // The season shown on map m: Engine.view.season outdoors, always summer (the base look) underground.
  function seasonOf(state, m) {
    if (m.dark || !Engine.view || typeof Engine.view.season !== "function") return "summer";
    var v = Engine.view.season(state), id = v && v.id;
    return typeof id === "string" && (id === "summer" || Util.has(SEASON_TC, id)) ? id : "summer";
  }

  // Terrain colours of a season: TC with the season's overrides.
  function tcOf(id) {
    if (!Util.has(SEASON_TC, id)) return TC;
    if (!Util.has(tcMemo, id)) {
      var out = {};
      keys(TC).forEach(function (k) { out[k] = Util.has(SEASON_TC[id], k) ? SEASON_TC[id][k] : TC[k]; });
      tcMemo[id] = out;
    }
    return tcMemo[id];
  }

  function nearTree(m, x, y) {
    for (var dy = -1; dy <= 1; dy++) {
      for (var dx = -1; dx <= 1; dx++) {
        var xx = x + dx, yy = y + dy, o = xx >= 0 && yy >= 0 && xx < m.w && yy < m.h ? m.sobj[xx + yy * m.w] : null;
        var d = o && Util.has(Data.objects, o) ? Data.objects[o].draw : null;
        if (Array.isArray(d) && FOLIAGE[d[0]]) return true;
      }
    }
    return false;
  }

  // Seasonal touches on a ground tile: blossom specks, fallen leaves (more under trees), snow tufts, dusted paths.
  function seasonTile(c, m, t, x, y, px, py, h) {
    var grass = t === "grass" || t === "grass_dark";
    if (season === "spring" && grass && (h & 15) < 2) dots(c, px, py, h + 5, 1 + (h & 1), BLOSSOM[(h >>> 5) & 3], 1, 1);
    if (season === "autumn" && grass) {
      var n = nearTree(m, x, y) ? 3 + (h & 1) : (h & 3) === 0 ? 1 : 0;
      for (var i = 0; i < n; i++) dots(c, px, py, h + 11 + i, 1, LEAVES[(h >>> (3 + i * 2)) & 3], 1 + ((h >>> (9 + i)) & 1), 1);
    }
    if (season !== "winter") return;
    if (grass && (h & 7) === 0) dots(c, px, py, h + 3, 1, "#7d8f6c", 1, 2);
    if (t === "dirt" || t === "path" || t === "sand" || t === "ash") {
      dots(c, px, py, h + 17, (h >>> 8) & 3, SNOW[2], 3, 1);
      dots(c, px, py, h + 13, (h >>> 10) & 1, SNOW[1], 2, 1);
    }
  }

  function tid(m, x, y) { return x < 0 || y < 0 || x >= m.w || y >= m.h ? null : m.tIds[m.terr[x + y * m.w]]; }

  function isTall(t) { return t === "wall" || t === "cave_wall" || t === "fence"; }

  function voidCol(m) { return m && m.dark ? "#0e0b09" : "#23446d"; }

  function fill(c, col, x, y, w, h) {
    c.fillStyle = col;
    c.fillRect(x, y, w, h);
  }

  function dots(c, px, py, h, n, col, w, hh) {
    c.fillStyle = col;
    for (var i = 0; i < n; i++) {
      var r = hash(h, i, 7);
      c.fillRect(px + (r & 15), py + ((r >>> 4) & 15), w, hh);
    }
  }

  // One 16x16 ground tile with seeded variation.
  function paintTile(c, m, t, x, y, px, py) {
    var col = tc[t], h = hash(x, y, 11), k;
    if (!col) return fill(c, voidCol(m), px, py, T, T);
    fill(c, col[0], px, py, T, T);
    if (t === "grass" || t === "grass_dark") {
      if (season === "winter") dots(c, px, py, h, 4, col[1], 2, 1);   // soft drifts, not grass blades
      else dots(c, px, py, h, 7, col[1], 1, 2);
      dots(c, px, py, h + 1, 3, col[2], 1, 1);
      if ((h & 31) === 0 && season !== "winter") dots(c, px, py, h + 2, 1, h & 64 ? "#e8c040" : "#f0ece0", 1, 1);
    } else if (t === "wood_floor") {
      for (k = 0; k < 4; k++) {
        fill(c, col[1], px, py + k * 4 + 3, T, 1);
        c.fillRect(px + ((k * 5 + x * 3 + y) & 15), py + k * 4, 1, 3);
        fill(c, col[2], px, py + k * 4, T, 1);
      }
    } else if (t === "stone_floor") {
      fill(c, col[1], px, py + 7, T, 1);
      c.fillRect(px, py + 15, T, 1);
      c.fillRect(px + ((x * 5 + y * 3) & 7) + 3, py, 1, 7);
      c.fillRect(px + ((x * 3 + y * 7) & 7) + 4, py + 8, 1, 7);
      fill(c, col[2], px + 1, py, 5, 1);
      c.fillRect(px + 9, py + 8, 4, 1);
    } else if (t === "bridge") {
      var across = WATER[tid(m, x, y - 1)] || WATER[tid(m, x, y + 1)];
      for (k = 0; k < T; k += 2) {
        fill(c, col[k & 2 ? 1 : 2], across ? px + k + 1 : px, across ? py : py + k + 1, across ? 1 : T, across ? T : 1);
      }
      c.fillStyle = "#3f2915";
      if (across && WATER[tid(m, x, y - 1)]) c.fillRect(px, py, T, 2);
      if (across && WATER[tid(m, x, y + 1)]) c.fillRect(px, py + 14, T, 2);
      if (!across && WATER[tid(m, x - 1, y)]) c.fillRect(px, py, 2, T);
      if (!across && WATER[tid(m, x + 1, y)]) c.fillRect(px + 14, py, 2, T);
    } else if (t === "lava") {
      lavaCrust(c, x, y, px, py);
    } else if (WATER[t]) {
      dots(c, px, py, h, 3, col[1], 3, 1);
      dots(c, px, py, h + 9, 1, col[2], 2, 1);
    } else if (t === "bog") {
      dots(c, px, py, h, 3, col[1], 3, 1);
      dots(c, px, py, h + 5, 2, "#5f7a2e", 2, 1);
      dots(c, px, py, h + 7, 2, col[2], 1, 1);
    } else if (t === "swamp") {
      dots(c, px, py, h, 3, col[1], 3, 2);
      dots(c, px, py, h + 4, 3, col[2], 1, 2);
      if ((h & 7) === 0) dots(c, px, py, h + 6, 1, "#3a4a3c", 4, 2);
    } else {
      dots(c, px, py, h, 6, col[1], 1, 1);
      dots(c, px, py, h + 1, 4, col[2], 1, 1);
      if (t === "path") dots(c, px, py, h + 2, 1, "#9d9a90", 2, 1);
      if (t === "cave_floor" && (h & 3) === 0) dots(c, px, py, h + 2, 1, "#6a625a", 2, 1);
    }
    if (season !== "summer") seasonTile(c, m, t, x, y, px, py, h);
  }

  // Lava: a dark crust split by glowing cracks. The cracks are the edges of a Voronoi cell pattern in world px
  // (cells ~10 px), so they run on across tile borders and a lone tile reads as a crack in molten rock.
  function lavaCrust(c, x, y, px, py) {
    fill(c, "#4a1a12", px, py, T, T);
    for (var ly = 0; ly < T; ly++) {
      for (var lx = 0; lx < T; lx++) {
        var wx = x * T + lx, wy = y * T + ly, gx = Math.floor(wx / 10), gy = Math.floor(wy / 10), d1 = 1e9, d2 = 1e9;
        for (var j = -1; j <= 1; j++) {
          for (var i = -1; i <= 1; i++) {
            var fh = hash(gx + i, gy + j, 77), fx = (gx + i) * 10 + (fh % 10), fy = (gy + j) * 10 + ((fh >>> 8) % 10);
            var dd = (fx - wx) * (fx - wx) + (fy - wy) * (fy - wy);
            if (dd < d1) { d2 = d1; d1 = dd; } else if (dd < d2) d2 = dd;
          }
        }
        var e = Math.sqrt(d2) - Math.sqrt(d1);
        if (e < 0.9) fill(c, (hash(wx, wy, 3) & 3) === 0 ? "#ffe070" : "#ffb050", px + lx, py + ly, 1, 1);
        else if (e < 1.9) fill(c, "#d8501a", px + lx, py + ly, 1, 1);
        else if (e < 2.8) fill(c, "#7a2616", px + lx, py + ly, 1, 1);
      }
    }
  }

  // Ragged edges: higher-priority ground spills 1-2 px into its neighbour; shores get foam. Between two
  // natural grounds (SOFT) the fringe is deep and speckled (1-5 px plus loose tufts), so the map's
  // tile-sized patches of grass, dirt, ash and swamp read as organic shapes instead of blocks.
  var SOFT = { grass: 1, grass_dark: 1, dirt: 1, ash: 1, swamp: 1, bog: 1 };
  function blendTile(c, m, x, y, px, py) {
    var t = tid(m, x, y);
    for (var d = 0; d < 4; d++) {
      var n = tid(m, x + DIRS[d][0], y + DIRS[d][1]);
      if (!n || n === t) continue;
      if (n === "lava" && tc[t] && !isTall(t)) lavaGlow(c, t, x, y, d, px, py);
      var foam = WATER[t] && !WATER[n] && n !== "void" && n !== "bridge";
      if (!foam && !(Util.has(PRIO, t) && Util.has(PRIO, n) && PRIO[n] > PRIO[t])) continue;
      var hz = d === 0 || d === 2, soft = !foam && Util.has(SOFT, t) && Util.has(SOFT, n), ice = foam && season === "winter";
      for (var i = 0; i < T; i++) {
        var r = hash(x * 31 + i, y * 17 + d, 3);
        var depth = ice ? 1 + (r & 1) + ((r >>> 3) & 1) : foam ? 1 : soft ? 1 + (r & 3) + ((r >>> 2) & 1) : 1 + ((r & 3) === 0 ? 1 : 0);
        if (foam && !ice && (r & 3) === 0) continue;
        var ex = d === 1 ? px + T - depth : d === 3 ? px : px + i, ey = d === 0 ? py : d === 2 ? py + T - depth : py + i;
        fill(c, ice ? SNOW[1] : foam ? "#b4d0e6" : tc[n][0], ex, ey, hz ? 1 : depth, hz ? depth : 1);
        if (foam && (r & 12) === 0) {
          fill(c, "#5089bb", d === 1 ? ex - 1 : d === 3 ? ex + 1 : ex, d === 0 ? ey + 1 : d === 2 ? ey - 1 : ey, 1, 1);
        }
        if (soft && ((r >>> 4) & 3) === 0) {   // a loose tuft 1-3 px past the fringe
          var k = depth + 1 + ((r >>> 6) & 1) + ((r >>> 7) & 1);
          fill(c, tc[n][0], d === 1 ? px + T - 1 - k : d === 3 ? px + k : px + i, d === 0 ? py + k : d === 2 ? py + T - 1 - k : py + i, 1, 1);
        }
      }
    }
  }

  // Ground beside lava catches its light: a broken 1 px #ff6a00-tinted rim along the shared edge.
  function lavaGlow(c, t, x, y, d, px, py) {
    var col = Icons.lib.mix(tc[t][0], "#ff6a00", 0.45);
    for (var i = 0; i < T; i++) {
      if ((hash(x * 31 + i, y * 17 + d, 9) & 3) === 0) continue;
      fill(c, col, d === 1 ? px + T - 1 : d === 3 ? px : px + i, d === 0 ? py : d === 2 ? py + T - 1 : py + i, 1, 1);
    }
  }

  // Wall height: 4 px for the south wall of a building (a floor to its north, or its corner), else 12.
  function tallH(m, x, y) {
    var t = tid(m, x, y);
    if (t === "fence") return 7;
    if (t !== "wall") return 12;
    if (FLOORS[tid(m, x, y - 1)]) return 4;
    if (tid(m, x, y - 1) === "wall") {
      for (var dx = -1; dx <= 1; dx += 2) if (tid(m, x + dx, y) === "wall" && FLOORS[tid(m, x + dx, y - 1)]) return 4;
    }
    return 12;
  }

  // A raised wall or cave wall on tile (x, y), tile top-left (px, py): a top surface lifted by its height,
  // a south face (bricks every 4 px under a 2 px cap) and, when baking, a 2 px shadow to the SE.
  function drawTall(c, m, x, y, px, py, shadow) {
    var t = tid(m, x, y);
    if (t === "fence") return drawFence(c, m, x, y, px, py);
    var H = tallH(m, x, y), below = tid(m, x, y + 1), cave = t === "cave_wall", col = tc[t], h = hash(x, y, 5);
    var snow = season === "winter" && !cave;
    var faceEnd = isTall(below) && below !== "fence" ? T - Math.min(H, tallH(m, x, y + 1)) : T;
    var top = py - H, edge = cave ? "#14100e" : "#4a4743";
    var openW = !isTall(tid(m, x - 1, y)), openE = !isTall(tid(m, x + 1, y));
    if (cave) {
      fill(c, col[0], px, top, T, T);
      dots(c, px, top, h, 6, col[1], 2, 1);
      dots(c, px, top, h + 1, 4, "#3a3430", 1, 1);
    } else {
      var sh = (y & 1) * 8;
      fill(c, snow ? SNOW[1] : "#7e7b73", px, top, T, T);
      fill(c, snow ? SNOW[2] : "#6a6760", px, top + 7, T, 1);
      c.fillRect(px + ((sh + 3) & 15), top, 1, 7);
      c.fillRect(px + ((sh + 11) & 15), top + 8, 1, 7);
      fill(c, snow ? SNOW[0] : "#8f8b82", px, top + 8, T, 1);
      c.fillRect(px, top, T, 1);
    }
    c.fillStyle = edge;
    if (!isTall(tid(m, x, y - 1))) c.fillRect(px, top, T, 1);
    if (openW) c.fillRect(px, top, 1, T);
    if (openE) c.fillRect(px + T - 1, top, 1, T);
    if (faceEnd > T - H) {
      var fy = py + T - H, fh = faceEnd - (T - H);
      fill(c, cave ? col[2] : col[0], px, fy, T, fh);
      if (cave) {
        dots(c, px, fy, h + 2, 5, col[1], 1, 2);
        dots(c, px, fy, h + 3, 3, "#4a4440", 2, 1);
        fill(c, "#4a4440", px, fy, T, 1);
      } else {
        fill(c, snow ? SNOW[0] : col[2], px, fy, T, 2);
        if (snow) dots(c, px, fy + 2, h + 4, 5, SNOW[1], 1, 1 + (h & 1));
        c.fillStyle = col[1];
        for (var by = fy + 5; by < fy + fh; by += 4) {
          c.fillRect(px, by, T, 1);
          for (var bx = (((by - fy) >> 2) & 1 ? 4 : 0) + 1; bx < T; bx += 8) c.fillRect(px + bx, by - 3, 1, 3);
        }
      }
      c.fillStyle = edge;
      if (openW) c.fillRect(px, fy, 1, fh);
      if (openE) c.fillRect(px + T - 1, fy, 1, fh);
      fill(c, "rgba(0,0,0,0.35)", px, py + faceEnd - 1, T, 1);
    }
    if (shadow) {
      c.fillStyle = "rgba(0,0,0,0.3)";
      if (openE) c.fillRect(px + T, py + T - H + 2, 2, H);
      if (!isTall(below)) c.fillRect(px + 2, py + T, T, 2);
    }
  }

  // A post at the tile centre with rails to each fence neighbour (W/E rails, N links): runs and
  // diagonal steps both read as one fence.
  function drawFence(c, m, x, y, px, py) {
    var col = tc.fence, gy = py + 12, top = season === "winter" ? SNOW[0] : col[2];
    function rail(rx) {
      fill(c, col[0], rx, gy - 6, 8, 2);
      c.fillRect(rx, gy - 3, 8, 2);
      fill(c, top, rx, gy - 6, 8, 1);
      c.fillRect(rx, gy - 3, 8, 1);
    }
    if (tid(m, x - 1, y) === "fence") rail(px);
    if (tid(m, x + 1, y) === "fence") rail(px + 8);
    if (tid(m, x, y - 1) === "fence") {
      fill(c, col[0], px + 7, py - 3, 2, 8);
      fill(c, col[2], px + 7, py - 3, 1, 8);
    }
    fill(c, "rgba(0,0,0,0.25)", px + 9, gy - 1, 2, 2);
    fill(c, col[1], px + 7, gy - 8, 2, 9);
    fill(c, col[2], px + 7, gy - 8, 1, 9);
    fill(c, "#1b140d", px + 7, gy - 9, 2, 1);
    if (season === "winter") fill(c, SNOW[0], px + 7, gy - 8, 2, 1);
  }

  // The walkable ground under a fence (its first walkable neighbour).
  function underFence(m, x, y) {
    for (var d = 0; d < 4; d++) {
      var n = tid(m, x + DIRS[d][0], y + DIRS[d][1]);
      if (n && n !== "fence" && Data.terrain[n] && Data.terrain[n].walk) return n;
    }
    return "grass";
  }

  // Ground, then edge blends, then raised walls in y order (including the row below for overhangs).
  function bakeChunk(m, cx, cy) {
    var c = canvas(CHUNK * T, CHUNK * T), g = c.getContext("2d"), x0 = cx * CHUNK, y0 = cy * CHUNK, x, y, t;
    for (y = 0; y < CHUNK; y++) {
      for (x = 0; x < CHUNK; x++) {
        t = tid(m, x0 + x, y0 + y);
        if (t !== null) paintTile(g, m, t === "fence" ? underFence(m, x0 + x, y0 + y) : t, x0 + x, y0 + y, x * T, y * T);
      }
    }
    for (y = 0; y < CHUNK; y++) {
      for (x = 0; x < CHUNK; x++) if (tid(m, x0 + x, y0 + y) !== null) blendTile(g, m, x0 + x, y0 + y, x * T, y * T);
    }
    for (y = -1; y <= CHUNK; y++) {
      for (x = -1; x <= CHUNK; x++) if (isTall(tid(m, x0 + x, y0 + y))) drawTall(g, m, x0 + x, y0 + y, x * T, y * T, true);
    }
    return c;
  }

  // Chunks of the season on screen; a season change drops that map's old chunks (one season held per map).
  function chunk(m, cx, cy) {
    if (chunkSeason[m.id] !== season) {
      keys(chunks).forEach(function (k) { if (k.indexOf(m.id + ":") === 0) delete chunks[k]; });
      chunkSeason[m.id] = season;
    }
    var key = m.id + ":" + cx + "," + cy;
    tc = tcOf(season);
    if (!Util.has(chunks, key)) chunks[key] = bakeChunk(m, cx, cy);
    return chunks[key];
  }

  // ----------------------------------------------------------------
  // ------------------------- Scene gathering ----------------------
  // ----------------------------------------------------------------

  function lerp(a, b, t) { return a + (b - a) * t; }

  // Interpolated tile position (the player goes through mx,my on 2-step ticks); teleports snap.
  function entPos(e, a, mid) {
    var px = typeof e.px === "number" ? e.px : e.x, py = typeof e.py === "number" ? e.py : e.y;
    if (Math.max(Math.abs(e.x - px), Math.abs(e.y - py)) > 2) return { x: e.x, y: e.y, moving: false };
    var moving = (px !== e.x || py !== e.y) && a < 1;
    var mx = mid && typeof e.mx === "number" ? e.mx : e.x, my = mid && typeof e.my === "number" ? e.my : e.y;
    if ((mx !== e.x || my !== e.y) && (mx !== px || my !== py)) {
      return a < 0.5 ? { x: lerp(px, mx, a * 2), y: lerp(py, my, a * 2), moving: moving } :
        { x: lerp(mx, e.x, a * 2 - 1), y: lerp(my, e.y, a * 2 - 1), moving: moving };
    }
    return { x: lerp(px, e.x, a), y: lerp(py, e.y, a), moving: moving };
  }

  // Tiles that may hold an object this epoch besides static ones: overrides and active fishing spots.
  function overrideTiles(state, map) {
    var out = {}, pre = map + ":";
    keys(state.objs || {}).forEach(function (k) {
      if (k.lastIndexOf(pre, 0) !== 0) return;
      var xy = k.slice(pre.length).split(",");
      out[+xy[0] + +xy[1] * 1024] = 1;
    });
    fishTiles(state, map, function (t) { out[t[0] + t[1] * 1024] = 1; });
    return out;
  }

  function fishTiles(state, map, fn) {
    keys(state.fish || {}).forEach(function (gid) {
      var g = Util.has(World.FISH, gid) ? World.FISH[gid] : null;
      if (g && g.map === map) (state.fish[gid].at || []).forEach(function (i) { if (g.tiles[i]) fn(g.tiles[i], g.obj); });
    });
  }

  // Respawn animations: a depleted node turning back into its base (tree grow 3 x 150 ms, rock glint).
  function respawnFrame(key, o, t, rock) {
    var prev = seenObj[key];
    seenObj[key] = o.id;
    if (prev && prev !== o.id && (prev === "stump" || prev === "rock_empty")) respawnAt[key] = t;
    if (!Util.has(respawnAt, key)) return -1;
    var age = t - respawnAt[key];
    if (age < (rock ? 300 : 450)) return rock ? 200 : 100 + Math.floor(age / 150);
    delete respawnAt[key];
    return -1;
  }

  // ----------------------------------------------------------------
  // ------------------------------ Draw ----------------------------
  // ----------------------------------------------------------------

  function eqKey(eq) {
    return eq ? [eq.head, eq.cape, eq.neck, eq.weapon, eq.body, eq.shield, eq.legs, eq.hands, eq.feet].join(",") : "";
  }

  function easeInset(t) {
    if (reduced() || inset.at < 0) { inset.cur = inset.to; return false; }
    var k = Math.min(1, (t - inset.at) / MS.ease);
    inset.cur = inset.from + (inset.to - inset.from) * (1 - (1 - k) * (1 - k));
    return k < 1;
  }

  function liveCount() {
    return splats.length + xps.length + crosses.length + fireworks.length + breaths.length + ghosts.length + spotGhosts.length;
  }

  function prune(t) {
    var n = liveCount();
    function live(ms) { return function (s) { return t - s.t < ms; }; }
    splats = splats.filter(live(MS.splat));
    xps = xps.filter(live(MS.xp));
    crosses = crosses.filter(live(MS.cross));
    fireworks = fireworks.filter(live(MS.fw));
    ghosts = ghosts.filter(live(MS.ghost));
    spotGhosts = spotGhosts.filter(live(MS.fade));
    breaths = breaths.filter(function (b) { return b.landT === null || t - b.landT < MS.land; });
    keys(overheads).forEach(function (k) { if (t - overheads[k].t >= MS.over) { delete overheads[k]; overVer++; } });
    keys(bars).forEach(function (k) { if (t - bars[k] >= MS.bar) { delete bars[k]; overVer++; } });
    keys(flashes).forEach(function (k) { if (flashes[k] <= t) { delete flashes[k]; overVer++; } });
    keys(respawnAt).forEach(function (k) { if (t - respawnAt[k] > 1000) delete respawnAt[k]; });
    if (n !== liveCount()) overVer++;
  }

  function hintTarget(state) {
    if (!opts.hints) return null;
    var key = serial + ":" + state.tick + ":" + state.player.map;
    if (hintCache.key !== key) {
      hintCache.key = key;
      try { hintCache.v = Engine.view.hint(state); } catch (e) { hintCache.v = null; }
    }
    var h = hintCache.v;
    return h && h.map === state.player.map ? h : null;
  }

  function camera(pos, m) {
    var insetDev = inset.cur * (backW / Math.max(1, cssW));
    var x = Math.round((pos.x * T + T / 2) * S - backW / 2);
    var y = Math.round((pos.y * T + T / 2) * S - (backH - insetDev) / 2);
    var mw = m.w * T * S, mh = m.h * T * S;
    x = mw <= backW ? Math.round((mw - backW) / 2) : Math.max(0, Math.min(mw - backW, x));
    y = mh <= backH - insetDev ? Math.round((mh - backH + insetDev) / 2) : Math.max(0, Math.min(mh - backH + insetDev, y));
    fr.camX = x; fr.camY = y;
    fr.bx0 = Math.floor(x / S); fr.by0 = Math.floor(y / S);
    fr.offX = x - fr.bx0 * S; fr.offY = y - fr.by0 * S;
  }

  // Skips the frame when its signature is unchanged; returns busy (walking, easing, overlays animating).
  // A fault is reported once per message and never breaks the caller's frame loop.
  function draw(state, alpha, nowMs) {
    try {
      return drawFrame(state, alpha, nowMs);
    } catch (e) {
      var msg = String(e && e.message ? e.message : e);
      if (!Util.has(errSeen, msg) && typeof console !== "undefined") console.error("Render: " + msg);
      errSeen[msg] = 1;
      lastSig = "";
      return false;
    }
  }

  function drawFrame(state, alpha, nowMs) {
    if (!ctx || !state || !state.player || backW < 2) return false;
    var p = state.player, m = mapOf(p.map);
    if (!m) return false;
    var t = typeof nowMs === "number" ? nowMs : now();
    var a = typeof alpha === "number" && isFinite(alpha) ? Math.max(0, Math.min(1, alpha)) : 1;
    lastAlpha = a;
    if (state !== lastState || camMap !== p.map) {
      if (state !== lastState) serial++;
      lastState = state;
      camMap = p.map;
      resetTracking();
    }
    season = seasonOf(state, m);
    Sprites.setSeason(season);
    var easing = easeInset(t);
    prune(t);
    var pos = entPos(p, a, true);
    camera(pos, m);
    var hint = hintTarget(state), moving = pos.moving || npcMoving(state, a) || petMoving(a);
    var animOn = splats.length || xps.length || crosses.length || fireworks.length || breaths.length || ghosts.length ||
      spotGhosts.length || keys(respawnAt).length || keys(flashes).length || spotFadeUntil > t || animWindow(state, a);
    var path = p.path && p.path.length ? p.path[p.path.length - 1].join(",") : "";
    var sig = [serial, state.tick, p.map, fr.camX, fr.camY, moving ? Math.floor(a * 30) : -1, hoverRef, hoverMode,
      overVer, animOn ? Math.floor(t / 16) : -1, ambientSeen ? Math.floor(t / AMB_MS) : -1, state.objVer, state.gid,
      (state.ground || []).length, eqKey(p.eq), p.anim, p.animAt, p.face, path, backW, backH, S, layoutVer,
      Math.round(inset.cur), hint ? hint.x + "," + hint.y : "", state.grave ? state.grave.items.length : 0, season,
      p.pet, p.petAt].join("|");
    if (sig === lastSig) return lastBusy;
    lastSig = sig;
    lastBusy = !!(moving || easing || animOn);
    world(state, m, pos, a, t, hint);
    overlays(state, t);
    minimap(state, m, pos, hint);
    return lastBusy;
  }

  // One-shot anims (attack swing, eat, block) need frames inside their first 300 ms.
  function animWindow(state, a) {
    if (a * 600 >= 320) return false;
    if (state.player.animAt === state.tick && state.player.anim) return true;
    if (state.player.pet && state.player.petAt === state.tick) return true;
    return state.npcs.some(function (n) { return n.map === state.player.map && n.animAt === state.tick && n.anim; });
  }

  function petMoving(a) {
    return !!petPos && a < 1 && (petPos.px !== petPos.x || petPos.py !== petPos.y);
  }

  function npcMoving(state, a) {
    return a < 1 && state.npcs.some(function (n) {
      return n.map === state.player.map && n.on && n.hp > 0 && (n.px !== n.x || n.py !== n.y);
    });
  }

  function resetTracking() {
    seenObj = {}; respawnAt = {}; spots = {}; spotGhosts = []; ghosts = []; drawnNpc = {};
    objEpoch = ""; hintCache.key = ""; lastSig = "";
  }

  function world(state, m, pos, a, t, hint) {
    var bw = buf.width, bh = buf.height, bx0 = fr.bx0, by0 = fr.by0, span = CHUNK * T;
    fill(bctx, voidCol(m), 0, 0, bw, bh);
    var cy1 = Math.min(Math.ceil(m.h / CHUNK) - 1, Math.floor((by0 + bh) / span));
    var cx1 = Math.min(Math.ceil(m.w / CHUNK) - 1, Math.floor((bx0 + bw) / span));
    for (var cy = Math.max(0, Math.floor(by0 / span)); cy <= cy1; cy++) {
      for (var cx = Math.max(0, Math.floor(bx0 / span)); cx <= cx1; cx++) {
        bctx.drawImage(chunk(m, cx, cy), cx * span - bx0, cy * span - by0);
      }
    }
    var tx0 = Math.max(0, Math.floor(bx0 / T) - 2), ty0 = Math.max(0, Math.floor(by0 / T) - 1);
    var tx1 = Math.min(m.w - 1, Math.floor((bx0 + bw) / T) + 2), ty1 = Math.min(m.h - 1, Math.floor((by0 + bh) / T) + 3);
    ambientSeen = false;
    shimmer(state, m, tx0, ty0, tx1, Math.min(m.h - 1, ty1 - 2), t);
    breathDecals(state, t);
    hits = [];
    ents = {};
    curMap = m;
    var list = [];
    groundItems(state, m);
    objects(state, m, tx0, ty0, tx1, ty1, t, list);
    npcs(state, a, t, list);
    playerEnt(state, pos, a, t, list);
    petEnt(state, a, t, list);
    var flag = flagEnt(state);
    if (flag) list.push(flag);
    occluders(m, list);
    fadeCanopies(state, m, list);
    list.sort(function (p, q) { return p.by - q.by || p.layer - q.layer || p.bx - q.bx; });
    list.forEach(drawEnt);
    silhouette(state, list);
    breathEdges(state, t);
    if (m.dark) darkness(pos, list, t);
    fireworksDraw(pos, t);
    hintArrow(hint, list, t, pos);
    ctx.drawImage(buf, 0, 0, bw, bh, -fr.offX, -fr.offY, bw * S, bh * S);
  }

  // Water shimmer: 1-2 highlight px per visible water tile, phase (x + y + tick) mod 4; lava glints; a slow
  // bubble now and then on bog (stagnant water does not sparkle).
  function shimmer(state, m, tx0, ty0, tx1, ty1, t) {
    var amb = Math.floor(t / 600);
    lavaTiles = [];
    for (var y = ty0; y <= ty1; y++) {
      for (var x = tx0; x <= tx1; x++) {
        var tt = tid(m, x, y);
        if (!WATER[tt] && tt !== "lava" && tt !== "bog") continue;
        ambientSeen = true;
        var h = hash(x, y, 21), px = x * T - fr.bx0, py = y * T - fr.by0;
        if (tt === "bog") {
          if (((h >>> 2) + amb) % 5 === 0) fill(bctx, "#4f6450", px + ((h >>> 5) & 11) + 2, py + ((h >>> 9) & 11) + 2, 1, 1);
          continue;
        }
        if (tt === "lava") {
          lavaTiles.push([x, y]);
          fill(bctx, (h + amb) & 1 ? "#ffb050" : "#e08020", px + ((h >>> 3) & 13) + 1, py + ((h >>> 8) & 13) + 1, 2, 1);
          continue;
        }
        var ph = (x + y + state.tick) & 3, sx = ((h >>> (ph * 4)) & 11) + 2, sy = ((h >>> (ph * 4 + 8)) & 11) + 2;
        fill(bctx, tt === "water" ? "#5089bb" : "#2f5f8f", px + sx, py + sy, 2, 1);
        if (h & 1) bctx.fillRect(px + ((sx + 7) & 13) + 1, py + ((sy + 5) & 13) + 1, 1, 1);
      }
    }
  }

  // Diagonal #ff3a00 hatch for the breath telegraph, 6 art px apart; drawn with a scrolling source offset.
  function hatch() {
    if (hatchCv) return hatchCv;
    hatchCv = canvas(3 * T + 6, 3 * T);
    var c = hatchCv.getContext("2d");
    c.fillStyle = "#ff3a00";
    for (var y = 0; y < 3 * T; y++) for (var x = 0; x < 3 * T + 6; x++) if ((x + y) % 6 === 0) c.fillRect(x, y, 1, 1);
    return hatchCv;
  }

  // Breath telegraph under the sprites: 3x3 tiles of #ff6a00, alpha pulsing 0.45-0.7, with a diagonal hatch
  // scrolling 1 art px per 100 ms; when it lands, a 300 ms #ffe070 flash.
  function breathDecals(state, t) {
    breaths.forEach(function (b) {
      if (b.map !== state.player.map) return;
      if (b.landT === null && state.tick >= b.land) b.landT = t;
      var landed = b.landT !== null, x = (b.cx - 1) * T - fr.bx0, y = (b.cy - 1) * T - fr.by0;
      bctx.globalAlpha = landed ? Math.max(0, 0.75 * (1 - (t - b.landT) / MS.land)) : 0.575 + 0.125 * Math.sin(t / 110);
      fill(bctx, landed ? "#ffe070" : "#ff6a00", x, y, 3 * T, 3 * T);
      if (!landed) {
        bctx.globalAlpha = 0.6;
        bctx.drawImage(hatch(), reduced() ? 0 : Math.floor(t / 100) % 6, 0, 3 * T, 3 * T, x, y, 3 * T, 3 * T);
      }
      bctx.globalAlpha = 1;
    });
  }

  // Above the sprites (so the wyrm and the player never hide it): a pulsing 1 art px #ffe070 border round each
  // un-landed telegraph, and embers rising inside it.
  function breathEdges(state, t) {
    breaths.forEach(function (b) {
      if (b.map !== state.player.map || b.landT !== null) return;
      var x = (b.cx - 1) * T - fr.bx0, y = (b.cy - 1) * T - fr.by0, n = 3 * T;
      bctx.globalAlpha = 0.6 + 0.4 * Math.sin(t / 110);
      fill(bctx, "#ffe070", x, y, n, 1);
      bctx.fillRect(x, y + n - 1, n, 1);
      bctx.fillRect(x, y + 1, 1, n - 2);
      bctx.fillRect(x + n - 1, y + 1, 1, n - 2);
      bctx.globalAlpha = 1;
      var rise = reduced() ? 0 : Math.floor(t / 100) % 12;
      for (var i = 0; i < 12; i++) {
        var h = hash(b.cx * 13 + i, b.cy, 5), ey = ((h >>> 8) % 44) + 2 - rise;
        if (ey < 2) ey += 44;
        fill(bctx, i % 3 ? "#ffb050" : "#ffe070", x + (h % 44) + 2, y + ey, 1, 1);
      }
    });
  }

  function addHit(ref, kind, sp, wx, wy, by) {
    var b = sp.box || [0, 0, sp.w, sp.h];
    hits.push({ ref: ref, kind: kind, x0: wx + b[0], y0: wy + b[1], x1: wx + b[0] + b[2], y1: wy + b[1] + b[3], by: by,
      bx: wx + sp.ax });
  }

  // Ground items: the item mask at the tile centre; a tile's top 3 entries (or a pile) at 2 px offsets.
  function groundItems(state, m) {
    var byTile = {};
    (state.ground || []).forEach(function (g) {
      if (g.map !== m.id) return;
      (byTile[g.x + "," + g.y] = byTile[g.x + "," + g.y] || []).push(g);
    });
    keys(byTile).forEach(function (k) {
      var shown = byTile[k].slice(-3), g0 = shown[0];
      if (shown.length === 1 && g0.qty > 1 && !(Data.items[g0.id] && Data.items[g0.id].stack)) {
        shown = [g0, g0, g0].slice(0, Math.min(3, g0.qty));
      }
      shown.forEach(function (g, i) {
        var wx = g.x * T + i * 2, wy = g.y * T - i * 2, x = wx - fr.bx0, y = wy - fr.by0;
        var icon = Icons.itemCanvas(g.id, g.qty), hov = hoverRef === "ground:" + g.gid;
        bctx.globalAlpha = 0.3;
        fill(bctx, "#000000", x + 4, y + 13, 9, 1);
        bctx.globalAlpha = hov && hoverMode === "use" ? 0.5 : 1;
        bctx.drawImage(icon, x, y);
        if (hov) {
          icon._sp = icon._sp || { cv: icon, ax: 8, ay: 16, w: 16, h: 16, box: [0, 0, 16, 16] };
          bctx.drawImage(Sprites.outline(icon._sp, HOVER.ground).cv, x, y);
        }
        bctx.globalAlpha = 1;
        if (i === shown.length - 1) hits.push({ ref: "ground:" + g.gid, kind: "ground", x0: wx + 1, y0: wy + 1, x1: wx + 15,
          y1: wy + 15, by: g.y * T + 15, bx: wx + 8, flat: 1 });
      });
    });
  }

  function objects(state, m, tx0, ty0, tx1, ty1, t, list) {
    var epoch = serial + "|" + state.tick + "|" + state.objVer + "|" + m.id;
    if (epoch !== objEpoch) {
      objEpoch = epoch;
      objCache = {};
      extraTiles = overrideTiles(state, m.id);
      trackSpots(state, m, t);
    }
    for (var y = ty0; y <= ty1; y++) {
      for (var x = tx0; x <= tx1; x++) {
        var k = x + y * 1024;
        if (!m.sobj[x + y * m.w] && !Util.has(extraTiles, k)) continue;
        if (!Util.has(objCache, k)) objCache[k] = Engine.objectAt(state, m.id, x, y);
        if (objCache[k]) objEnt(objCache[k], x, y, t, list, 1, false);
      }
    }
    spotGhosts.forEach(function (gh) {
      if (gh.map === m.id) objEnt(gh.o, gh.x, gh.y, t, list, 1 - (t - gh.t) / MS.fade, true);
    });
    var gr = state.grave;
    if (gr && gr.map === m.id && Util.has(Data.objects, "gravestone")) {
      var sp = Sprites.obj("gravestone", "base", hash(gr.x, gr.y, 1), 0);
      list.push({ sp: sp, x: gr.x * T + 8 - sp.ax, y: gr.y * T + 16 - sp.ay, by: gr.y * T + 16, bx: gr.x * T, layer: 0,
        ref: "grave:0", kind: "grave", tile: [gr.x, gr.y] });
    }
  }

  // Fishing spots that moved fade out over 300 ms, then the new tile fades in.
  function trackSpots(state, m, t) {
    var cur = {}, next = {}, had = keys(spots).length > 0;
    fishTiles(state, m.id, function (tl, o) { cur[tl[0] + "," + tl[1]] = { x: tl[0], y: tl[1], obj: o }; });
    keys(spots).forEach(function (k) {
      var s = spots[k];
      if (!Util.has(cur, k)) {
        spotGhosts.push({ o: { id: s.obj, def: Data.objects[s.obj], alt: false }, x: s.x, y: s.y, t: t, map: m.id });
      }
    });
    keys(cur).forEach(function (k) {
      next[k] = Util.has(spots, k) ? spots[k] : { x: cur[k].x, y: cur[k].y, obj: cur[k].obj, t: had ? t + MS.fade : -1e9 };
      spotFadeUntil = Math.max(spotFadeUntil, next[k].t + MS.fade);
    });
    spots = next;
  }

  function objEnt(o, x, y, t, list, alpha, ghost) {
    var def = o.def || Data.objects[o.id];
    if (!def) return;
    var dr = o.alt && def.alt && Array.isArray(def.alt.draw) ? def.alt.draw : def.draw;
    var kind = Array.isArray(dr) ? dr[0] : "", seed = hash(x, y, 9), key = x + "," + y, f = 0, a = alpha;
    var anim = Sprites.ANIM[kind];
    if (anim) {
      f = Math.floor((t + (kind === "beacon" ? 0 : (seed % 7) * 97)) / anim[1]) % anim[0];
      ambientSeen = true;
    }
    if (!ghost) {
      var rf = respawnFrame(key, o, t, kind === "rock");
      if (rf >= 0 && (kind === "rock" || FOLIAGE[kind])) f = rf;
      if (kind === "fish_spot" && Util.has(spots, key)) a = Math.max(0, Math.min(1, (t - spots[key].t) / MS.fade));
    }
    if (a <= 0) return;
    var sp = Sprites.obj(o.id, o.alt ? "alt" : "base", seed, f);
    list.push({ sp: sp, x: x * T + 8 - sp.ax, y: y * T + 16 - sp.ay, by: y * T + 16, bx: x * T, layer: 0, alpha: a,
      ref: ghost ? null : "obj:" + x + "," + y, kind: "obj", tile: [x, y], tall: sp.ay - sp.box[1] > 20,
      canopy: !!FOLIAGE[kind], emit: EMIT[kind] && (kind !== "beacon" || o.alt) ? 1 : 0 });
  }

  function npcFrame(state, n, pos, a, t) {
    var f = 0, anim = null;
    if (pos.moving) f = 1 + (Math.floor(t / 150) & 1);
    else if (n.anim && n.animAt === state.tick && a * 600 < 300) {
      f = n.anim === "attack" ? 4 : 0;
      anim = n.anim;
    } else if ((t + n.uid * 997) % 4000 < 140) f = 5;
    if (n.spec && n.spec.land > state.tick) anim = "cast";
    if (Util.has(flashes, n.uid) && flashes[n.uid] > t) f |= 8;
    return { f: f, anim: anim };
  }

  function npcs(state, a, t, list) {
    var map = state.player.map;
    drawnNpc = {};
    state.npcs.forEach(function (n) {
      if (!n || n.map !== map || !n.on || !(n.hp > 0) || !Util.has(Data.npcs, n.id)) return;
      var d = Data.npcs[n.id], pos = entPos(n, a, false), fm = npcFrame(state, n, pos, a, t), face = n.face | 0;
      var fx = typeof n.px === "number" ? n.px : n.x, fy = typeof n.py === "number" ? n.py : n.y;
      if (Util.has(Sprites.SIDE_ONLY, Array.isArray(d.draw) ? d.draw[0] : "")) {
        if (face >= 1 && face <= 3) lastH[n.uid] = 2;
        else if (face >= 5) lastH[n.uid] = 6;
        face = Util.has(lastH, n.uid) ? lastH[n.uid] : 6;
      }
      var sp = Sprites.npc(n.id, face, fm.f, fm.anim), wx = pos.x * T + 8 - sp.ax, wy = pos.y * T + 16 - sp.ay;
      list.push({ sp: sp, x: wx, y: wy, by: pos.y * T + 16, bx: pos.x * T, layer: 1, ref: "npc:" + n.uid, kind: "npc",
        tile: [Math.round(pos.x), Math.round(pos.y)], at: [n.x, n.y], big: d.scale === 2, uid: n.uid,
        from: Math.max(Math.abs(fx - n.x), Math.abs(fy - n.y)) <= 1 ? [fx, fy] : null,   // a step, not a respawn
        doll: Util.has(Sprites.HUMANOID, d.draw[0]) ? (d.scale === 2 ? 2 : 1) : 0 });
      drawnNpc[n.uid] = { sp: sp, x: wx, y: wy, by: pos.y * T + 16, map: map };
    });
    ghosts.forEach(function (gh) {
      if (gh.map === map) {
        list.push({ sp: gh.sp, x: gh.x, y: gh.y + Math.floor((t - gh.t) / 90), by: gh.by, bx: gh.x, layer: 1,
          alpha: Math.max(0, 1 - (t - gh.t) / MS.ghost), kind: "ghost" });
      }
    });
  }

  // The tool the player visibly works with: the best of its kind in the pack or hand.
  function heldTool(p) {
    var cat = Util.has(ANIM_TOOL, p.anim) ? ANIM_TOOL[p.anim] : null, best = null, bestMult = -1;
    if (p.anim === "fish" && p.act && p.act.k === "gather" && Util.has(Data.objects, p.act.base)) {
      var op = (Data.objects[p.act.base].ops || []).filter(function (o) { return o.id === p.act.op; })[0];
      cat = op ? op.tool : null;
    }
    if (!cat) return null;
    (p.inv || []).map(function (s) { return s ? s.id : null; }).concat([p.eq.weapon]).forEach(function (id) {
      var it = id && Util.has(Data.items, id) ? Data.items[id] : null;
      var mult = it && it.tool && it.tool.cat === cat ? (typeof it.tool.mult === "number" ? it.tool.mult : 1) : -1;
      if (mult > bestMult) { best = id; bestMult = mult; }
    });
    return best;
  }

  // Walk frames while moving; action A/B per tick while a continuous anim runs; one-shots for 300 ms.
  function playerEnt(state, pos, a, t, list) {
    var p = state.player, f = 0, anim = p.anim || null, act = p.act ? p.act.k : null;
    if (pos.moving) { f = 1 + (Math.floor(t / 150) & 1); anim = null; }
    else if (anim && CONT[anim] && act) f = state.tick & 1 ? 3 : 4;
    else if (act === "cast") anim = "cast";
    else if (anim && !CONT[anim] && anim !== "cast" && p.animAt === state.tick && a * 600 < 300) {
      f = anim === "attack" ? 4 : 0;
    }
    else {
      anim = null;
      if ((t + 333) % 4000 < 140) f = 5;
    }
    if (Util.has(flashes, 0) && flashes[0] > t) f |= 8;
    var eq = p.eq || {}, tool = anim ? heldTool(p) : null;
    if (tool) {
      eq = JSON.parse(JSON.stringify(eq));
      eq.weapon = tool;
    }
    var sp = Sprites.player(eq, p.face | 0, f, anim, p.look);
    list.push({ sp: sp, x: pos.x * T + 8 - sp.ax, y: pos.y * T + 16 - sp.ay, by: pos.y * T + 16, bx: pos.x * T, layer: 1,
      kind: "player", tile: [Math.round(pos.x), Math.round(pos.y)], doll: 1 });
  }

  // The summoned pet is drawn render-side only (the engine gives a pet no tile); its hit rect carries the ref
  // "pet:0", which only the UI's right-click menu reads. A free side for it: behind the player first, then
  // round to the front. Diagonally behind comes first, so a player facing the camera doesn't hide it.
  var PET_DX = [0, 1, 1, 1, 0, -1, -1, -1], PET_DY = [-1, -1, 0, 1, 1, 1, 0, -1];

  function petSide(state, p, x, y) {
    var f = (p.face | 0) + 4;
    var order = [-1, 1, -2, 2, 0, -3, 3, 4];
    for (var i = 0; i < order.length; i++) {
      var k = ((f + order[i]) % 8 + 8) % 8, nx = p.x + PET_DX[k], ny = p.y + PET_DY[k];
      if (!World.blocked(state, p.map, nx, ny)) return [nx, ny];
    }
    return [x, y];
  }

  // The foe the pet stands beside: the player's fight act on a living NPC on this map that the player can
  // swing at (cardinally adjacent), the same test the engine's pet strike uses. Null otherwise.
  function petFoeOf(state, p) {
    var n = p.act && p.act.k === "fight" && p.act.uid >= 1 ? state.npcs[p.act.uid - 1] : null;
    return n && n.on && n.hp > 0 && n.map === p.map && World.adjacent(p.x, p.y, n.x, n.y, "nsew") ? n : null;
  }

  // A tile the pet may stand on in a fight: open, not the player's or a living NPC's, outside a pending breath.
  function petFree(state, p, x, y) {
    if ((x === p.x && y === p.y) || World.blocked(state, p.map, x, y)) return false;
    for (var i = 0; i < state.npcs.length; i++) {
      var n = state.npcs[i];
      if (!n || !n.on || !(n.hp > 0) || n.map !== p.map) continue;
      if (n.x === x && n.y === y) return false;
      if (n.spec && n.spec.land > state.tick && Util.dist(x, y, n.spec.cx, n.spec.cy) <= 1) return false;
    }
    return true;
  }

  // The flank: a free tile touching the foe, across from the player before next to them, so the player, the foe
  // and the pet all stay in view: beside a normal foe (left or right) before above or below; in front of a big
  // (scale 2) foe, whose sprite covers the tiles beside and behind it. The pet keeps its tile when that scores as
  // well as the best (no hopping between equal tiles). Null when no tile is free.
  function petFlank(state, p, n, q) {
    var big = Util.has(Data.npcs, n.id) && Data.npcs[n.id].scale === 2;
    var score = function (x, y) {
      var row = big ? (y > n.y ? 0 : y === n.y ? 3 : 6) : (y === n.y ? 0 : x === n.x ? 4 : 2);
      return row - 2 * Util.dist(x, y, p.x, p.y);
    };
    var best = null, bs = 1e9;
    for (var k = 0; k < 8; k++) {
      var x = n.x + PET_DX[k], y = n.y + PET_DY[k];
      if (!petFree(state, p, x, y)) continue;
      if (score(x, y) < bs) { bs = score(x, y); best = [x, y]; }
    }
    if (best && q && Util.dist(q.x, q.y, n.x, n.y) === 1 && petFree(state, p, q.x, q.y) && score(q.x, q.y) <= bs) return [q.x, q.y];
    return best;
  }

  // One step (8-way) toward (tx, ty), never onto the player's or an NPC's tile; straighter steps win ties.
  function petStep(state, p, x, y, tx, ty) {
    var best = null, bd = Util.dist(x, y, tx, ty) + 0.5;
    for (var k = 0; k < 8; k++) {
      var nx = x + PET_DX[k], ny = y + PET_DY[k];
      if (!(nx === tx && ny === ty) && !petFree(state, p, nx, ny)) continue;
      var dd = Util.dist(nx, ny, tx, ty) + 0.01 * (Math.abs(nx - tx) + Math.abs(ny - ty));
      if (dd < bd) { bd = dd; best = [nx, ny]; }
    }
    return best;
  }

  // The pet walks the player's own path one step behind, at the player's pace: a walking tick it steps onto
  // the tile the player left; a running tick (two steps) it goes through that tile to the player's first
  // step, in the same two halves as the player. Standing still, it closes up to a free side. In a fight (the
  // player beside their foe) it goes to the foe's flank instead, up to two steps a tick, and faces it; the
  // tick the player clicks away it is back to following. It snaps beside the player only after a teleport,
  // a map change, a summon, or when it is more than 3 tiles from where the player started the tick.
  function petEnt(state, a, t, list) {
    var p = state.player;
    var d = p.pet && Data.pets && Util.has(Data.pets, p.pet) && p.pets && Util.has(p.pets, p.pet) ? Data.pets[p.pet] : null;
    if (!d || !(p.hp > 0)) { petPos = null; return; }
    var stage = Rules.petStage(Rules.petLevel(p.pets[p.pet])), g = stage > 0 && Array.isArray(d.grows) ? d.grows[stage - 1] : null;
    var kind = g && Array.isArray(g.draw) ? g.draw[0] : Array.isArray(d.draw) ? d.draw[0] : "";
    var q = petPos;
    var jumped = Util.dist(p.px, p.py, p.x, p.y) > 2;
    if (!q || q.map !== p.map || q.id !== p.pet || jumped || Util.dist(q.x, q.y, p.px, p.py) > 3) {
      var at = petSide(state, p, p.x, p.y);
      q = petPos = { id: p.pet, map: p.map, x: at[0], y: at[1], px: at[0], py: at[1], mx: null, my: null,
        tick: state.tick, face: p.face | 0, h: 6 };
    }
    if (q.tick !== state.tick) {
      q.px = q.x;
      q.py = q.y;
      q.mx = q.my = null;
      q.tick = state.tick;
      var moved = p.px !== p.x || p.py !== p.y;
      var two = moved && (p.mx !== p.x || p.my !== p.y) && (p.mx !== p.px || p.my !== p.py);
      var foe = petFoeOf(state, p), flank = foe ? petFlank(state, p, foe, q) : null;
      if (flank) {
        var s1 = flank[0] === q.x && flank[1] === q.y ? null : petStep(state, p, q.x, q.y, flank[0], flank[1]);
        var s2 = s1 && !(s1[0] === flank[0] && s1[1] === flank[1]) ? petStep(state, p, s1[0], s1[1], flank[0], flank[1]) : null;
        if (s1 && s2) {
          q.mx = s1[0];
          q.my = s1[1];
          q.x = s2[0];
          q.y = s2[1];
        } else if (s1) {
          q.x = s1[0];
          q.y = s1[1];
        }
      } else if (two) {
        q.mx = p.px;
        q.my = p.py;
        q.x = p.mx;
        q.y = p.my;
      } else if (moved) {
        q.x = p.px;
        q.y = p.py;
      } else if (Util.dist(q.x, q.y, p.x, p.y) > 1) {
        var sx = q.x + Math.sign(p.x - q.x), sy = q.y + Math.sign(p.y - q.y);
        if (!(sx === p.x && sy === p.y) && !World.blocked(state, p.map, sx, sy)) { q.x = sx; q.y = sy; }
        else if (!World.blocked(state, p.map, q.x + Math.sign(p.x - q.x), q.y)) q.x += Math.sign(p.x - q.x);
        else if (!World.blocked(state, p.map, q.x, q.y + Math.sign(p.y - q.y))) q.y += Math.sign(p.y - q.y);
      }
      if (!flank && q.x === p.x && q.y === p.y) {
        var sd = petSide(state, p, q.x, q.y);
        q.x = sd[0];
        q.y = sd[1];
      }
      var fx = q.mx !== null ? q.mx : q.px, fy = q.my !== null ? q.my : q.py;
      if (q.x !== fx || q.y !== fy) q.face = Util.dirIndex(q.x - fx, q.y - fy);
      if ((flank && q.x === flank[0] && q.y === flank[1]) || (foe && p.petAt === state.tick)) {
        q.face = Util.dirIndex(foe.x - q.x, foe.y - q.y);
      }
    }
    var moving = (q.px !== q.x || q.py !== q.y) && a < 1;
    var x = q.x, y = q.y, f = 0, face = q.face;
    if (moving && q.mx !== null) {
      x = a < 0.5 ? lerp(q.px, q.mx, a * 2) : lerp(q.mx, q.x, a * 2 - 1);
      y = a < 0.5 ? lerp(q.py, q.my, a * 2) : lerp(q.my, q.y, a * 2 - 1);
    } else if (moving) {
      x = lerp(q.px, q.x, a);
      y = lerp(q.py, q.y, a);
    }
    if (moving) f = 1 + (Math.floor(t / 150) & 1);
    else if (p.petAt === state.tick && a * 600 < 300) f = 4;
    else if ((t + 571) % 4000 < 140) f = 5;
    if (Util.has(Sprites.SIDE_ONLY, kind)) {
      if (face >= 1 && face <= 3) q.h = 2;
      else if (face >= 5) q.h = 6;
      face = q.h;
    }
    var sp = Sprites.pet(p.pet, face, f, stage);
    list.push({ sp: sp, x: x * T + 8 - sp.ax, y: y * T + 16 - sp.ay, by: y * T + 16, bx: x * T, layer: 1, kind: "pet",
      ref: "pet:0" });
  }

  // The destination a click set (walk or goto) until arrival; fight chases re-path every tick and show none.
  function flagAt(p) {
    var a = p.act, path = p.path;
    return path && path.length && a && (a.k === "walk" || a.k === "goto") ? path[path.length - 1] : null;
  }

  // The red flag on the walk destination (until arrival).
  function flagEnt(state) {
    var d = flagAt(state.player);
    if (!d) return null;
    return { flag: 1, x: d[0] * T + 7, y: d[1] * T + 6, by: d[1] * T + 14, bx: d[0] * T, layer: 0 };
  }

  // Walls and fences in the row below an entity are redrawn after it (it stands behind them).
  function occluders(m, list) {
    var seen = {};
    list.slice().forEach(function (e) {
      if (!e.tile || !(e.kind === "player" || e.kind === "npc" || e.tall)) return;
      for (var x = e.tile[0] - 1; x <= e.tile[0] + 1; x++) {
        var y = e.tile[1] + 1, k = x + "," + y;
        if (Util.has(seen, k) || !isTall(tid(m, x, y))) continue;
        seen[k] = 1;
        var H = tallH(m, x, y);
        list.push({ wall: 1, tx: x, ty: y, by: y * T + 16, bx: x * T, layer: 0, x: x * T, y: y * T - H,
          sp: { w: T, h: T + H } });
      }
    });
  }

  // A canopy that hides an NPC, a fire or other light, the gravestone or a ground item behind it (north of its
  // trunk) is drawn at 45%, so a fire lit on a tree's north side or a goblin wandering behind it stays visible.
  function fadeCanopies(state, m, list) {
    var behind = list.filter(function (e) { return e.kind === "npc" || e.kind === "grave" || e.emit; }).map(function (e) {
      return { by: e.by, box: boxOf(e) };
    });
    (state.ground || []).forEach(function (g) {
      if (g.map === m.id) behind.push({ by: g.y * T + 16, box: [g.x * T + 2, g.y * T + 2, g.x * T + 14, g.y * T + 14] });
    });
    list.forEach(function (c) {
      if (!c.canopy) return;
      var cb = boxOf(c);
      if (behind.some(function (e) { return e.by < c.by && e.box && overlap(e.box, cb) > 0.3; })) {
        c.alpha = Math.min(typeof c.alpha === "number" ? c.alpha : 1, 0.45);
      }
    });
  }

  function drawEnt(e) {
    if (e.wall) return drawTall(bctx, curMap, e.tx, e.ty, e.tx * T - fr.bx0, e.ty * T - fr.by0, false);
    var x = Math.round(e.x) - fr.bx0, y = Math.round(e.y) - fr.by0;
    if (e.flag) {
      fill(bctx, "#1b140d", x, y, 1, 9);
      bctx.fillRect(x + 1, y - 1, 5, 5);
      fill(bctx, "#e02020", x + 1, y, 4, 3);
      fill(bctx, "#ff6060", x + 1, y, 4, 1);
      return;
    }
    var sp = e.sp;
    if (e.alpha !== undefined && e.alpha < 1) bctx.globalAlpha = e.alpha;
    bctx.drawImage(sp.cv, x, y);
    if (e.ref && e.ref === hoverRef) {
      if (hoverMode === "use") bctx.globalAlpha = 0.5;
      bctx.drawImage(Sprites.outline(sp, HOVER[e.kind] || HOVER.obj).cv, x, y);
    }
    bctx.globalAlpha = 1;
    if (e.ref) addHit(e.ref, e.kind, sp, Math.round(e.x), Math.round(e.y), e.by);
    if (e.ref && e.canopy) hits[hits.length - 1].canopy = 1;
    // A small NPC is hit anywhere on the tile it is leaving or entering: a click aimed a moment ago still lands.
    if (e.ref && e.kind === "npc" && !e.big && e.from) {
      var hh = hits[hits.length - 1];
      [e.at, e.from].forEach(function (tl) {
        hh.x0 = Math.min(hh.x0, tl[0] * T + 2); hh.x1 = Math.max(hh.x1, tl[0] * T + T - 2);
        hh.y0 = Math.min(hh.y0, tl[1] * T + 2); hh.y1 = Math.max(hh.y1, tl[1] * T + T);
      });
    }
    if (e.kind === "player" || e.kind === "npc") {
      // humanoids anchor on the head, not on a raised tool
      var top = Math.round(e.y) + (e.doll ? Sprites.DOLL.y * e.doll : sp.box[1]);
      ents[e.kind === "player" ? 0 : e.uid] = { x: Math.round(e.x) + sp.ax, top: top, by: e.by,
        chest: top + (e.doll ? 11 * e.doll : Math.round(sp.box[3] * 0.42)) };
    }
  }

  // An entity's opaque bounds in world art px: [x0, y0, x1, y1] (null for the flag).
  function boxOf(e) {
    if (!e.sp) return null;
    var b = e.wall ? [0, 0, e.sp.w, e.sp.h] : e.sp.box, x0 = Math.round(e.x) + b[0], y0 = Math.round(e.y) + b[1];
    return [x0, y0, x0 + b[2], y0 + b[3]];
  }

  // Overlap of two boxes as a share of a's area.
  function overlap(a, b) {
    var w = Math.min(a[2], b[2]) - Math.max(a[0], b[0]), h = Math.min(a[3], b[3]) - Math.max(a[1], b[1]);
    return w > 0 && h > 0 ? (w * h) / Math.max(1, (a[2] - a[0]) * (a[3] - a[1])) : 0;
  }

  // The first entity drawn after list[i] that covers more than `min` of it and passes ok (any when ok is null).
  function coveredBy(list, i, ok, min) {
    var a = boxOf(list[i]);
    for (var j = i + 1; a && j < list.length; j++) {
      var e = list[j], b = e.kind === "ghost" ? null : boxOf(e);
      if (b && (!ok || ok(e)) && overlap(a, b) > min) return e;
    }
    return null;
  }

  function redraw(e, alpha, edgeCol) {
    var x = Math.round(e.x) - fr.bx0, y = Math.round(e.y) - fr.by0;
    bctx.globalAlpha = alpha;
    bctx.drawImage(e.sp.cv, x, y);
    bctx.globalAlpha = 1;
    if (edgeCol) bctx.drawImage(Sprites.edge(e.sp, edgeCol).cv, x, y);
  }

  // Covered sprites stay findable: the player behind a canopy, wall, tall object or boss drawn after it gets a
  // 35% silhouette on top (and a white edge inside a boss); the current foe hidden behind anything drawn after
  // it (the player included) is redrawn at 45% with a yellow edge.
  function silhouette(state, list) {
    var p = state.player, foe = p.foe || (p.act && p.act.k === "fight" ? p.act.uid : 0);
    list.forEach(function (e, i) {
      if (e.kind === "player") {
        var by = coveredBy(list, i, function (o) { return o.wall || o.canopy || o.big || o.tall; }, 0);
        if (by) redraw(e, 0.35, coveredBy(list, i, function (o) { return o.big; }, 0) ? "#ffffff" : null);
      } else if (foe && e.kind === "npc" && e.uid === foe && coveredBy(list, i, null, 0.25)) {
        redraw(e, 0.45, "#ffff00");
      }
    });
  }

  // Dark maps: 35% darker outside a 5-tile light around the player; fires, torches and lava glow.
  function darkness(pos, list, t) {
    if (!lightCv) {
      lightCv = canvas(LIGHT_R * 2, LIGHT_R * 2);
      var c = lightCv.getContext("2d");
      for (var i = 0; i < LIGHT_R * LIGHT_R * 4; i++) {
        var x = i % (LIGHT_R * 2), y = Math.floor(i / (LIGHT_R * 2));
        var d = Math.sqrt((x + 0.5 - LIGHT_R) * (x + 0.5 - LIGHT_R) + (y + 0.5 - LIGHT_R) * (y + 0.5 - LIGHT_R)) / LIGHT_R;
        if (d < 1) fill(c, "rgba(0,0,0," + (d < 0.72 ? 1 : d < 0.86 ? 0.66 : 0.33) + ")", x, y, 1, 1);
      }
    }
    dctx.globalCompositeOperation = "source-over";
    dctx.clearRect(0, 0, dark.width, dark.height);
    fill(dctx, "rgba(0,0,0,0.35)", 0, 0, dark.width, dark.height);
    dctx.globalCompositeOperation = "destination-out";
    dctx.drawImage(lightCv, Math.round(pos.x * T + 8) - fr.bx0 - LIGHT_R, Math.round(pos.y * T + 4) - fr.by0 - LIGHT_R);
    dctx.fillStyle = "rgba(0,0,0,0.85)";
    lavaTiles.forEach(function (lt) { dctx.fillRect(lt[0] * T - fr.bx0, lt[1] * T - fr.by0, T, T); });
    list.forEach(function (e) {
      if (!e.emit) return;
      var r = LIGHT_R / 2, fl = (Math.floor(t / 200) + e.bx) & 1;
      dctx.drawImage(lightCv, e.bx + 8 - fr.bx0 - r - fl, e.by - 10 - fr.by0 - r - fl, r * 2 + fl * 2, r * 2 + fl * 2);
    });
    dctx.globalCompositeOperation = "source-over";
    bctx.drawImage(dark, 0, 0);
  }

  // 28 particles, 2x2 art px, skill colour + white, bursting from the player's head for 1.4 s.
  function fireworksDraw(pos, t) {
    var hx = pos.x * T + 8 - fr.bx0, hy = pos.y * T - 6 - fr.by0;
    fireworks.forEach(function (fw) {
      var k = (t - fw.t) / MS.fw;
      bctx.globalAlpha = k > 0.7 ? Math.max(0, (1 - k) / 0.3) : 1;
      for (var i = 0; i < 28; i++) {
        var ang = (i / 28) * Math.PI * 2 + fw.spin, dist = (18 + (hash(i, fw.seed, 3) % 14)) * (1 - (1 - k) * (1 - k));
        var x = Math.round(hx + Math.cos(ang) * dist), y = Math.round(hy + Math.sin(ang) * dist * 0.8 + k * k * 10);
        fill(bctx, i % 3 ? fw.col : "#ffffff", x, y, 2, 2);
      }
    });
    bctx.globalAlpha = 1;
  }

  // Yellow 7x9 arrow bobbing 2 art px over the hint target (an NPC: over its drawn sprite, so it follows a walk),
  // lifted above the player's head when the player stands in its way. When that arrow would not be fully in view,
  // a chevron instead: on the line from the player toward the target, at the view edge (inset 12 art px) but at
  // most 4.5 tiles out.
  function hintArrow(hint, list, t, pos) {
    if (!hint) return;
    var top = hint.y * T - 4, cx = hint.x * T + 8, cy = hint.y * T + 8;
    list.forEach(function (e) {
      var at = e.at || e.tile;
      if (!at || at[0] !== hint.x || at[1] !== hint.y || (e.kind !== "npc" && e.kind !== "obj")) return;
      if (e.kind === "obj") { top = Math.min(top, e.y + e.sp.box[1] - 3); return; }
      cx = Math.round(e.x + e.sp.ax);                          // a walking NPC: follow the drawn sprite
      cy = e.by - 8;
      top = Math.min(e.by - 20, e.y + e.sp.box[1] - 3);
    });
    ambientSeen = true;
    var bob = reduced() ? 0 : Math.round(1 + Math.sin(t / 260));
    var vx0 = fr.camX / S, vy0 = fr.camY / S, vw = backW / S, vh = (backH - inset.cur * (backW / Math.max(1, cssW))) / S;
    // Off-screen = the arrow itself would not be fully in view (a target cut by the bottom edge keeps its arrow).
    if (cx < vx0 + 4 || cx > vx0 + vw - 4 || top - 13 < vy0 || top - 1 > vy0 + vh) {
      return edgeArrow(pos, cx, cy, [vx0, vy0, vw, vh], bob);
    }
    list.forEach(function (e) {
      if (e.kind !== "player") return;
      var l = Math.round(e.x) + e.sp.box[0], st = Math.round(e.y) + e.sp.box[1];
      if (l < cx + 4 && l + e.sp.box[2] > cx - 4 && st <= top - 1 && e.by >= top - 13) top = st - 3;
    });
    var x = cx - 4 - fr.bx0, y = Math.round(top) - 10 - bob - fr.by0;
    ARROW.forEach(function (row, r) {
      for (var c = 0; c < 7; c++) {
        if (row.charAt(c) !== ".") fill(bctx, row.charAt(c) === "o" ? "#1b140d" : r < 3 ? "#fff07a" : "#ffd200", x + c, y + r, 1, 1);
      }
    });
  }

  // The off-screen hint chevron (see hintArrow); view = [x0, y0, w, h] in world art px.
  function edgeArrow(pos, tx, ty, view, bob) {
    var px = pos.x * T + 8, py = pos.y * T + 8, dx = tx - px, dy = ty - py, len = Math.sqrt(dx * dx + dy * dy);
    if (len < 1) return;
    dx /= len; dy /= len;
    var x0 = view[0] + 12, y0 = view[1] + 12, x1 = view[0] + view[2] - 12, y1 = view[1] + view[3] - 12, k = 72;
    if (dx > 0) k = Math.min(k, (x1 - px) / dx); else if (dx < 0) k = Math.min(k, (x0 - px) / dx);
    if (dy > 0) k = Math.min(k, (y1 - py) / dy); else if (dy < 0) k = Math.min(k, (y0 - py) / dy);
    k = Math.max(20, k) + bob;
    var ch = chevron(Math.atan2(dy, dx), 1);
    bctx.drawImage(ch, Math.round(px + dx * k - ch.width / 2) - fr.bx0, Math.round(py + dy * k - ch.height / 2) - fr.by0);
  }

  // A hint chevron pointing along angle `ang` (radians; snapped to 16 steps), `size` 1 for the view or 0.6 for
  // the minimap ring: a #ffd200 triangle with a #fff07a back, outlined #1b140d. Cached per step and size.
  function chevron(ang, size) {
    var idx = ((Math.round(ang / (Math.PI / 8)) % 16) + 16) % 16, key = idx + ":" + size;
    if (Util.has(chevrons, key)) return chevrons[key];
    var N = 15, a = (idx * Math.PI) / 8, ca = Math.cos(a), sa = Math.sin(a), cells = [], x, y;
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var qx = x + 0.5 - N / 2, qy = y + 0.5 - N / 2, u = (qx * ca + qy * sa) / size, v = (qy * ca - qx * sa) / size;
        cells.push(u >= -3.5 && u <= 4.5 && Math.abs(v) <= (4.5 - u) * 0.62 ? (u < -1.5 ? "#fff07a" : "#ffd200") : null);
      }
    }
    var c = canvas(N, N), g = c.getContext("2d");
    for (y = 0; y < N; y++) {
      for (x = 0; x < N; x++) {
        var col = cells[y * N + x];
        if (!col && ((x > 0 && cells[y * N + x - 1]) || (x < N - 1 && cells[y * N + x + 1]) ||
          (y > 0 && cells[(y - 1) * N + x]) || (y < N - 1 && cells[(y + 1) * N + x]))) col = "#1b140d";
        if (col) fill(g, col, x, y, 1, 1);
      }
    }
    return (chevrons[key] = c);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Overlays --------------------------
  // ----------------------------------------------------------------

  function dev(v) { return v * (backW / Math.max(1, cssW)); }

  // Entity anchors in device px on the main canvas.
  function entDev(on) {
    if (!Util.has(ents, on)) return null;
    var e = ents[on];
    return { x: (e.x - fr.bx0) * S - fr.offX, top: (e.top - fr.by0) * S - fr.offY, chest: (e.chest - fr.by0) * S - fr.offY,
      by: e.by };
  }

  // An NPC's overlay anchor; one standing just north of the player is lifted until its chest is 24 css above the
  // player's head, so its bar and splats sit above the player's bar instead of on the player's face.
  function anchorOf(on, pd) {
    var d = entDev(on);
    if (!d || !pd || +on === 0 || !(d.by < pd.by) || Math.abs(d.x - pd.x) >= dev(12)) return d;
    var lift = d.chest - (pd.top - dev(24));
    if (lift > 0) { d.top -= lift; d.chest -= lift; }
    return d;
  }

  // Bold text with a #000 shadow at (1, 1), drawn twice (no shadowBlur).
  function text(str, x, y, px, col, align) {
    var sh = Math.max(1, Math.round(dev(1)));
    ctx.font = "bold " + Math.round(dev(px)) + "px " + FONT;
    ctx.textAlign = align || "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#000000";
    ctx.fillText(str, Math.round(x) + sh, Math.round(y) + sh);
    ctx.fillStyle = col;
    ctx.fillText(str, Math.round(x), Math.round(y));
  }

  // The 20x18 css hitsplat burst for a kind, rendered once per device scale.
  function splatImg(kind) {
    var key = kind + ":" + backW + ":" + cssW;
    if (Util.has(splatCv, key)) return splatCv[key];
    var u = dev(2), c = canvas(Math.ceil(u * 10), Math.ceil(u * 9)), g = c.getContext("2d");
    var col = SPLAT_COL[kind], hi = Icons.lib.mix(col, "#ffffff", 0.3);
    SPLAT.split("|").forEach(function (row, r) {
      for (var k = 0; k < 10; k++) {
        var ch = row.charAt(k);
        if (ch !== ".") fill(g, ch === "o" ? "#1b140d" : r < 3 && k < 5 ? hi : col, Math.round(k * u), Math.round(r * u), Math.ceil(u), Math.ceil(u));
      }
    });
    return (splatCv[key] = c);
  }

  function overlays(state, t) {
    var pd = entDev(0);
    keys(bars).forEach(function (on) {
      var d = anchorOf(on, pd), hp = barHp(state, +on);
      if (!d || !hp) return;
      var w = Math.round(dev(30)), h = Math.round(dev(5)), x = Math.round(d.x - w / 2), y = Math.round(d.top - dev(8) - h);
      fill(ctx, "#000000", x - 1, y - 1, w + 2, h + 2);
      fill(ctx, "#c00000", x, y, w, h);
      fill(ctx, "#00c000", x, y, Math.round(w * Math.max(0, Math.min(1, hp[0] / hp[1]))), h);
    });
    splats.forEach(function (s) {
      var d = anchorOf(s.on, pd);
      if (!d) return;
      var img = splatImg(s.kind), x = d.x + dev(SPLAT_AT[s.slot][0]), y = d.chest + dev(SPLAT_AT[s.slot][1]);
      ctx.drawImage(img, Math.round(x - img.width / 2), Math.round(y - img.height / 2));
      text(String(s.dmg), x, y + dev(0.5), 11, "#ffffff");
    });
    keys(overheads).forEach(function (uid) {
      var d = anchorOf(uid, pd);
      if (d) text(overheads[uid].text, d.x, d.top - dev(10), 12, "#ffff00");
    });
    crosses.forEach(crossDraw.bind(null, t));
    xpDrops(t);
  }

  // Click cross: 9 css, shrinking over 400 ms; yellow for walk, red for an action.
  function crossDraw(t, c) {
    var half = Math.floor([9, 7, 5, 3][Math.min(3, Math.floor((t - c.t) / 100))] / 2), u = Math.max(1, Math.round(dev(1)));
    var cx = Math.round(dev(c.x)), cy = Math.round(dev(c.y)), i;
    for (i = -half; i <= half; i++) {
      fill(ctx, "#000000", cx + i * u - u, cy + i * u, u * 3, u);
      ctx.fillRect(cx + i * u - u, cy - i * u, u * 3, u);
    }
    ctx.fillStyle = c.kind === "act" ? "#ff2020" : "#ffff00";
    for (i = -half; i <= half; i++) {
      ctx.fillRect(cx + i * u, cy + i * u, u, u);
      ctx.fillRect(cx + i * u, cy - i * u, u, u);
    }
  }

  function barHp(state, on) {
    if (on === 0) {
      var p = state.player;
      return [p.hp, Math.max(1, Rules.levelForXp(((p.xp10 && p.xp10.hitpoints) || 0) / 10))];
    }
    var n = state.npcs[on - 1], c = n && Util.has(Data.npcs, n.id) ? Data.npcs[n.id].combat : null;
    return n && n.on && n.hp > 0 && c ? [n.hp, c.hp] : null;
  }

  // XP drops: right 12, rising 64 css from orbsBottom + 72 over 1.6 s, fading in the last 0.5 s. Rested
  // (doubled, 10.14) drops are gold.
  function xpDrops(t) {
    xps.forEach(function (d) {
      var k = (t - d.t) / MS.xp, y = dev(orbsBottom + 72 - 64 * k), right = backW - dev(12), g = dev(16);
      var label = "+" + Util.fmtInt(d.amt);
      ctx.globalAlpha = Math.max(0, Math.min(1, ((1 - k) * MS.xp) / 500));
      text(label, right, y, 13, d.rested ? "#f3cf6a" : "#ffffff", "right");
      var x = right - ctx.measureText(label).width - dev(4);
      for (var i = d.skills.length - 1; i >= 0; i--) {
        x -= g;
        Icons.paintSkill(ctx, d.skills[i], x, y - g / 2, g / 16);
        x -= dev(1);
      }
      ctx.globalAlpha = 1;
    });
  }

  // ----------------------------------------------------------------
  // ---------------------------- Minimap ---------------------------
  // ----------------------------------------------------------------

  // One px per tile: terrain base colours, trees, rocks and walls.
  function mmImage(m) {
    var mk = m.id + ":" + season;
    if (Util.has(mmImg, mk)) return mmImg[mk];
    keys(mmImg).forEach(function (k) { if (k.indexOf(m.id + ":") === 0) delete mmImg[k]; });
    tc = tcOf(season);
    var c = canvas(m.w, m.h), g = c.getContext("2d");
    for (var i = 0; i < m.w * m.h; i++) {
      var x = i % m.w, y = Math.floor(i / m.w), t = tid(m, x, y), o = m.sobj[i];
      var od = o && Util.has(Data.objects, o) ? Data.objects[o] : null, k = od && Array.isArray(od.draw) ? od.draw[0] : "";
      var col = t === "wall" ? "#d8d0c0" : t === "fence" ? "#9a7048" : tc[t] ? tc[t][0] : voidCol(m);
      if (FOLIAGE[k]) col = k === "yew" || k === "ironbark" ? "#2d5120" : k === "amber" ? "#b8742a" : MM_TREE[season];
      else if (k === "rock") col = season === "winter" ? "#c8d0d4" : "#9d9a90";
      else if (od && od.block !== false) col = Icons.lib.mix(col, "#d8d0c0", 0.35);
      else if ((hash(x, y, 2) & 7) === 0 && (t === "grass" || t === "grass_dark")) col = Icons.lib.mix(col, "#000000", 0.08);
      fill(g, col, x, y, 1, 1);
    }
    return (mmImg[mk] = c);
  }

  // Glyph spots per map (objects, fishing groups and NPC spawns with mapIcon). A glyph within 8 tiles of
  // one of the same kind is merged into it, so a wood or a mine shows one icon, not a cluster.
  function glyphs(m) {
    if (Util.has(glyphCache, m.id)) return glyphCache[m.id];
    var out = [];
    function add(kind, x, y) {
      for (var i = 0; i < out.length; i++) {
        if (out[i][0] === kind && Math.max(Math.abs(out[i][1] - x), Math.abs(out[i][2] - y)) <= 8) return;
      }
      if (Icons.mapGlyph(kind).length) out.push([kind, x, y]);
    }
    keys(m.nodes).forEach(function (o) {
      var d = Util.has(Data.objects, o) ? Data.objects[o] : null;
      if (d && d.mapIcon) m.nodes[o].forEach(function (p) { add(d.mapIcon, p[0], p[1]); });
    });
    keys(World.FISH).forEach(function (g) {
      var f = World.FISH[g], d = Data.objects[f.obj], sx = 0, sy = 0;
      if (f.map !== m.id || !d || !d.mapIcon || !f.tiles.length) return;
      f.tiles.forEach(function (tl) { sx += tl[0]; sy += tl[1]; });
      add(d.mapIcon, Math.round(sx / f.tiles.length), Math.round(sy / f.tiles.length));
    });
    World.SPAWNS.forEach(function (sp) {
      var d = Data.npcs[sp.id];
      if (sp.map === m.id && d && d.mapIcon) add(d.mapIcon, sp.x, sp.y);
    });
    return (glyphCache[m.id] = out);
  }

  // Circle of mmDiam css at mmPx css per tile, centred on the player; ring 2 px #2a231b + 1 px #6a5a44.
  function minimap(state, m, pos, hint) {
    if (!mctx || mm.width < 4) return;
    var W = mm.width, r = W / 2, u = W / Math.max(1, mmDiam), tp = mmPx * u, ox = r - (pos.x + 0.5) * tp, oy = r - (pos.y + 0.5) * tp;
    function dot(x, y, col) {
      var dx = Math.round(ox + (x + 0.5) * tp - 1.5 * u), dy = Math.round(oy + (y + 0.5) * tp - 1.5 * u);
      fill(mctx, "#000000", dx + 1, dy + 1, 3 * u, 3 * u);
      fill(mctx, col, dx, dy, 3 * u, 3 * u);
    }
    mctx.clearRect(0, 0, W, W);
    mctx.save();
    mctx.beginPath();
    mctx.arc(r, r, r - u, 0, Math.PI * 2);
    mctx.clip();
    fill(mctx, voidCol(m), 0, 0, W, W);
    mctx.imageSmoothingEnabled = false;
    mctx.drawImage(mmImage(m), Math.round(ox), Math.round(oy), m.w * tp, m.h * tp);
    // Dots first: a keeper standing on its own shop or bank glyph must not cover it.
    (state.ground || []).forEach(function (g) { if (g.map === m.id) dot(g.x, g.y, "#ff3030"); });
    state.npcs.forEach(function (n) { if (n.map === m.id && n.on && n.hp > 0) dot(n.x, n.y, "#ffff00"); });
    glyphs(m).forEach(function (gl) {
      var gx = Math.round(ox + (gl[1] + 0.5) * tp - 3.5 * u), gy = Math.round(oy + (gl[2] + 0.5) * tp - 3.5 * u);
      if (gx > -8 * u && gy > -8 * u && gx < W && gy < W) Icons.paintGlyph(mctx, gl[0], gx, gy, u);
    });
    var d = flagAt(state.player);
    if (d) {
      var fx = Math.round(ox + (d[0] + 0.5) * tp), fy = Math.round(oy + (d[1] + 0.5) * tp);
      fill(mctx, "#1b140d", fx, fy - 5 * u, u, 6 * u);
      fill(mctx, "#e02020", fx + u, fy - 5 * u, 3 * u, 2 * u);
    }
    fill(mctx, "#000000", Math.round(r - 1.5 * u) + 1, Math.round(r - 1.5 * u) + 1, 3 * u, 3 * u);
    fill(mctx, "#ffffff", Math.round(r - 1.5 * u), Math.round(r - 1.5 * u), 3 * u, 3 * u);
    var gv = state.grave ? Engine.view.grave(state) : null, gp = gv && gv.pin;
    if (gp) mmPin(ox + (gp[0] + 0.5) * tp, oy + (gp[1] + 0.5) * tp, r, u, "#c8c8c8", "#f4f4f4");
    if (hint) mmHint(ox + (hint.x + 0.5) * tp, oy + (hint.y + 0.5) * tp, r, u);
    mctx.restore();
    [[2, "#2a231b", r - u], [1, "#6a5a44", r - 2.5 * u]].forEach(function (ring) {
      mctx.lineWidth = ring[0] * u;
      mctx.strokeStyle = ring[1];
      mctx.beginPath();
      mctx.arc(r, r, ring[2], 0, Math.PI * 2);
      mctx.stroke();
    });
  }

  // The hint on the minimap: the yellow 7x9 arrow with its tip just above the target (so a glyph there stays
  // visible), bobbing 1 css px; when it would not fit inside the ring, a chevron on the ring pointing out to it.
  function mmHint(hx, hy, r, u) {
    var dx = hx - r, dy = hy - r, d = Math.sqrt(dx * dx + dy * dy), ty = hy - 12 * u;
    if (d <= r - 7 * u && Math.sqrt(dx * dx + (ty - r) * (ty - r)) <= r - 3 * u) {
      var x = Math.round(hx - 3.5 * u), y = Math.round(ty - (reduced() ? 0 : Math.round(0.5 + 0.5 * Math.sin(now() / 260))) * u);
      ARROW.forEach(function (row, rr) {
        for (var c = 0; c < 7; c++) {
          var ch = row.charAt(c);
          if (ch !== ".") fill(mctx, ch === "o" ? "#1b140d" : rr < 3 ? "#fff07a" : "#ffd200", x + Math.round(c * u), y + Math.round(rr * u), Math.ceil(u), Math.ceil(u));
        }
      });
      return;
    }
    var lim = r - 6 * u, ch2 = chevron(Math.atan2(dy, dx), 0.6), sz = ch2.width * u;
    mctx.drawImage(ch2, Math.round(r + (dx / d) * lim - sz / 2), Math.round(r + (dy / d) * lim - sz / 2), Math.round(sz), Math.round(sz));
  }

  // A minimap marker (your gravestone, or the ladder toward it), pinned to the ring when it is off the map.
  function mmPin(hx, hy, r, u, col, hi) {
    var dx = hx - r, dy = hy - r, d = Math.sqrt(dx * dx + dy * dy), lim = r - 7 * u, s = Math.round(u);
    if (d > lim) { hx = r + (dx / d) * lim; hy = r + (dy / d) * lim; }
    var x = Math.round(hx), y = Math.round(hy);
    fill(mctx, "#1b140d", x - 3 * s, y - 3 * s, 7 * s, 7 * s);
    fill(mctx, col, x - 2 * s, y - 2 * s, 5 * s, 5 * s);
    fill(mctx, hi, x - 2 * s, y - 2 * s, 5 * s, s);
  }

  // The world map window (the globe by the minimap): the current map at a whole number of device px per tile.
  // view.z 1 fits the whole map into w x h css; z 2..4 multiplies that scale and shows a w x h window centred on
  // (view.cx, view.cy) in tiles, clamped to the map. Region names (towns above their walls), glyphs, the hint arrow
  // and you (white). Redrawn on a change; returns { tp, ox, oy } in device px for the UI's drag and wheel.
  function worldMap(cv, w, h, view) {
    var st = lastState, m = st && st.player ? mapOf(st.player.map) : null;
    if (!cv || !m || w < 8 || h < 8) return null;
    var p = st.player, hint = hintTarget(st), u = Math.max(1, Math.round(dpr));
    var z = view && view.z > 1 ? Math.min(4, Math.floor(view.z)) : 1;
    var fit = Math.max(1, Math.floor(Math.min((w * dpr) / m.w, (h * dpr) / m.h))), tp = fit * z;
    var W = z === 1 ? m.w * tp : Math.floor(w * dpr), H = z === 1 ? m.h * tp : Math.floor(h * dpr);
    var cx = view && typeof view.cx === "number" ? view.cx : p.x + 0.5, cy = view && typeof view.cy === "number" ? view.cy : p.y + 0.5;
    function clampO(c, size, full) { return full <= size ? Math.round((full - size) / 2) : Math.max(0, Math.min(full - size, Math.round(c * tp - size / 2))); }
    var ox = z === 1 ? 0 : clampO(cx, W, m.w * tp), oy = z === 1 ? 0 : clampO(cy, H, m.h * tp);
    var sig = [m.id, season, W, H, tp, ox, oy, p.x, p.y, hint ? hint.x + "," + hint.y : ""].join("|");
    cv._view = { tp: tp, ox: ox, oy: oy, dpr: dpr, w: m.w, h: m.h, z: z };
    if (cv._sig === sig) return cv._view;
    cv._sig = sig;
    cv.width = W;
    cv.height = H;
    cv.style.width = W / dpr + "px";
    cv.style.height = H / dpr + "px";
    var g = cv.getContext("2d");
    g.imageSmoothingEnabled = false;
    fill(g, voidCol(m), 0, 0, W, H);
    g.drawImage(mmImage(m), -ox, -oy, m.w * tp, m.h * tp);
    g.font = "bold " + 11 * u + "px " + FONT;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.lineJoin = "round";
    g.lineWidth = 3 * u;
    // Towns first; a name that would overlap one already drawn is left out, and names stay inside the frame.
    var boxes = [], list = (Data.regions || []).filter(function (rg) { return rg.map === m.id && rg.rect; });
    list.sort(function (a, b) { return (b.town ? 1 : 0) - (a.town ? 1 : 0); });
    list.forEach(function (rg) {
      var tw = g.measureText(rg.name).width + 4 * u, th = 13 * u;
      var lx = ((rg.rect[0] + rg.rect[2] + 1) / 2) * tp - ox, ly = (rg.town ? rg.rect[1] * tp - 7 * u : ((rg.rect[1] + rg.rect[3] + 1) / 2) * tp) - oy;
      if (lx + tw / 2 < 0 || lx - tw / 2 > W || ly + th / 2 < 0 || ly - th / 2 > H) return;
      lx = Math.max(tw / 2, Math.min(W - tw / 2, lx));
      ly = Math.max(th / 2, Math.min(H - th / 2, ly));
      var bx = [lx - tw / 2, ly - th / 2, lx + tw / 2, ly + th / 2];
      if (boxes.some(function (o) { return bx[0] < o[2] && o[0] < bx[2] && bx[1] < o[3] && o[1] < bx[3]; })) return;
      boxes.push(bx);
      g.strokeStyle = "#1b140d";
      g.strokeText(rg.name, lx, ly);
      g.fillStyle = rg.town ? "#ffffff" : "#ffb000";
      g.fillText(rg.name, lx, ly);
    });
    glyphs(m).forEach(function (gl) {
      Icons.paintGlyph(g, gl[0], Math.round((gl[1] + 0.5) * tp - 3.5 * u) - ox, Math.round((gl[2] + 0.5) * tp - 3.5 * u) - oy, u);
    });
    if (hint) {
      var ax = Math.round((hint.x + 0.5) * tp - 3.5 * u) - ox, ay = Math.round((hint.y + 0.5) * tp - 10 * u) - oy;
      ARROW.forEach(function (row, rr) {
        for (var c = 0; c < 7; c++) {
          var ch = row.charAt(c);
          if (ch !== ".") fill(g, ch === "o" ? "#1b140d" : rr < 3 ? "#fff07a" : "#ffd200", ax + c * u, ay + rr * u, u, u);
        }
      });
    }
    var px = Math.round((p.x + 0.5) * tp) - ox, py = Math.round((p.y + 0.5) * tp) - oy;
    fill(g, "#000000", px - 3 * u, py - 3 * u, 6 * u, 6 * u);
    fill(g, "#ffffff", px - 2 * u, py - 2 * u, 4 * u, 4 * u);
    return cv._view;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Events ----------------------------
  // ----------------------------------------------------------------

  // Up to 4 splats per target at once; a fifth replaces the oldest.
  function addSplat(on, val, kind, t) {
    var used = splats.filter(function (s) { return s.on === on; }), slot = -1;
    for (var i = 0; i < 4 && slot < 0; i++) if (!used.some(function (s) { return s.slot === i; })) slot = i;
    if (slot < 0) {
      var old = used.sort(function (p, q) { return p.t - q.t; })[0];
      splats.splice(splats.indexOf(old), 1);
      slot = old.slot;
    }
    splats.push({ on: on, dmg: val, kind: kind, t: t, slot: slot });
  }

  function firework(col, t) {
    if (opts.fireworks) fireworks.push({ t: t, col: col, seed: fireworks.length + Math.floor(t), spin: (t % 628) / 100 });
  }

  // Hitsplats, HP bars, XP drops (grouped per call), fireworks, breath telegraphs, overheads, tp snaps.
  function onEvents(state, events, nowMs) {
    if (!Array.isArray(events) || !events.length) return;
    var t = typeof nowMs === "number" ? nowMs : now(), xp = {}, order = [], rested = false;
    events.forEach(function (ev) {
      if (!ev || typeof ev !== "object") return;
      var on = ev.on | 0;
      if (ev.type === "hit") {
        addSplat(on, ev.miss ? 0 : ev.dmg | 0, ev.miss ? "miss" : ev.pet ? "pet" : "hit", t);
        bars[on] = t;
        if (!ev.miss && ev.dmg > 0) flashes[on] = t + MS.flash;
      } else if (ev.type === "heal") {
        addSplat(on, ev.amt | 0, "heal", t);
        bars[on] = t;
      } else if (ev.type === "death") {
        var dn = on > 0 && Util.has(drawnNpc, on) ? drawnNpc[on] : null;
        if (dn) ghosts.push({ sp: dn.sp, x: dn.x, y: dn.y, by: dn.by, t: t, map: dn.map });
        delete bars[on];
      } else if (ev.type === "xp" && ev.amt > 0 && typeof ev.skill === "string") {
        if (!Util.has(xp, ev.skill)) { xp[ev.skill] = 0; order.push(ev.skill); }
        xp[ev.skill] += ev.amt;
        if (ev.rested) rested = true;
      } else if (ev.type === "level") {
        var sk = (Data.skills || []).filter(function (k) { return k.id === ev.skill; })[0];
        firework(ev.lvl >= 99 || !sk ? "#ffd24a" : sk.color, t);
      } else if (ev.type === "questDone" || ev.type === "rare" || ev.type === "pet" || ev.type === "petGrow") {
        firework("#ffd24a", t);
      } else if (ev.type === "recall") {
        firework("#b4d0e6", t);
      } else if (ev.type === "breath") {
        breaths.push({ cx: ev.cx, cy: ev.cy, land: ev.land, landT: null,
          map: state && state.player ? state.player.map : null });
      } else if (ev.type === "overhead") {
        overheads[ev.uid] = { text: String(ev.text || ""), t: t };
      } else if (ev.type === "tp") {
        // The player's splats, HP bar and hit flash belong where they were: don't carry them along.
        camMap = null;
        breaths = [];
        splats = splats.filter(function (s) { return s.on !== 0; });
        delete bars[0];
        delete flashes[0];
      }
    });
    // Whole numbers only: each skill's fraction carries into its next drop, so the running total stays exact.
    if (order.length && opts.xpDrops) {
      var whole = order.reduce(function (s, k) {
        var v = xp[k] + (xpCarry[k] || 0), w = Math.floor(v + 1e-6);
        xpCarry[k] = Math.max(0, v - w);
        return s + w;
      }, 0);
      if (whole > 0) xps.push({ skills: order, amt: whole, t: t, rested: rested });
    }
    overVer++;
    lastSig = "";
  }

  // ----------------------------------------------------------------
  // ------------------------ Picking, coords -----------------------
  // ----------------------------------------------------------------

  function clientRect() {
    var t = now();
    if (!rect || t - rectAt > 250) {
      rect = cv ? cv.getBoundingClientRect() : null;
      rectAt = t;
    }
    return rect;
  }

  // Every hit entity under the cursor (sprite bounds + 2 css px, front-most first), then the ground items on the
  // tile under it, then trees hit only by their canopy over another tile (the one north of the trunk): a fire or
  // loot there is clicked, not the tree. null outside the map.
  function pick(clientX, clientY) {
    var st = lastState, rc = clientRect(), m = st && st.player ? mapOf(st.player.map) : null;
    if (!m || !rc || rc.width <= 0 || rc.height <= 0) return null;
    var wx = ((clientX - rc.left) * (backW / rc.width) + fr.camX) / S;
    var wy = ((clientY - rc.top) * (backH / rc.height) + fr.camY) / S;
    var tx = Math.floor(wx / T), ty = Math.floor(wy / T), pad = dev(2) / S, refs = [], far = [];
    if (tx < 0 || ty < 0 || tx >= m.w || ty >= m.h) return null;
    function add(ref) { if (refs.indexOf(ref) < 0) refs.push(ref); }
    hits.filter(function (h) { return !h.flat && wx >= h.x0 - pad && wx < h.x1 + pad && wy >= h.y0 - pad && wy < h.y1 + pad; })
      .sort(function (a, b) { return b.by - a.by || b.bx - a.bx; })
      .forEach(function (h) {
        var own = Math.floor(h.bx / T) === tx && Math.floor((h.by - 1) / T) === ty;
        if (h.canopy && !own) far.push(h.ref);
        else add(h.ref);
      });
    for (var i = (st.ground || []).length - 1; i >= 0; i--) {
      var g = st.ground[i];
      if (g.map === m.id && g.x === tx && g.y === ty) add("ground:" + g.gid);
    }
    far.forEach(add);
    return { x: tx, y: ty, refs: refs };
  }

  function minimapPick(clientX, clientY) {
    var st = lastState, rc = mm ? mm.getBoundingClientRect() : null, m = st && st.player ? mapOf(st.player.map) : null;
    if (!m || !rc || rc.width <= 0) return null;
    var r = rc.width / 2, dx = clientX - rc.left - r, dy = clientY - rc.top - r;
    if (dx * dx + dy * dy > r * r) return null;
    var pos = entPos(st.player, 1, true), x = Math.floor(pos.x + 0.5 + dx / mmPx), y = Math.floor(pos.y + 0.5 + dy / mmPx);
    return x < 0 || y < 0 || x >= m.w || y >= m.h ? null : { x: x, y: y };
  }

  function worldToClient(wx, wy) {
    var rc = clientRect();
    if (!rc || backW < 1) return { x: 0, y: 0 };
    return { x: rc.left + (wx * S - fr.camX) * (rc.width / backW), y: rc.top + (wy * S - fr.camY) * (rc.height / backH) };
  }

  function tileToClient(x, y) { return worldToClient(x * T + T / 2, y * T + T / 2); }

  // The centre of a ref's hit rect (tile centre for tile/obj/ground refs not drawn this frame).
  function refToClient(ref) {
    var h = hits.filter(function (e) { return e.ref === ref; })[0], r = Util.parseRef(ref), st = lastState;
    if (h) return worldToClient((h.x0 + h.x1) / 2, (h.y0 + h.y1) / 2);
    if (r && (r.t === "tile" || r.t === "obj")) return tileToClient(r.x, r.y);
    var g = r && r.t === "ground" && st ? (st.ground || []).filter(function (e) { return e.gid === r.n; })[0] : null;
    return g ? tileToClient(g.x, g.y) : null;
  }

  function marker(clientX, clientY, kind) {
    var rc = clientRect();
    if (!rc || rc.width <= 0) return;
    crosses.push({ x: (clientX - rc.left) * (cssW / rc.width), y: (clientY - rc.top) * (cssH / rc.height),
      kind: kind === "act" ? "act" : "walk", t: now() });
    overVer++;
    lastSig = "";
  }

  // Hover outline target. In use mode it draws at 50% alpha; pass the slot to keep only valid targets.
  function hover(ref, mode, slot) {
    var r = typeof ref === "string" ? ref : null, md = mode === "use" ? "use" : "normal";
    if (r && md === "use" && typeof slot === "number" && slot >= 0 && lastState) {
      try { if (!Engine.canUse(lastState, slot, r)) r = null; } catch (e) { r = null; }
    }
    if (r !== hoverRef || md !== hoverMode) lastSig = "";
    hoverRef = r;
    hoverMode = md;
  }

  // ----------------------------------------------------------------
  // ---------------------------- Portrait --------------------------
  // ----------------------------------------------------------------

  // Head crop (art x4, y0, w8, h8 of the 16x24 frame) x6 = 48x48 css; monsters fit whole.
  function portrait(who) {
    var k = Math.max(1, Math.round(dpr)), out = canvas(48 * k, 48 * k), g = out.getContext("2d");
    out.style.width = out.style.height = "48px";
    out.style.imageRendering = "pixelated";
    g.imageSmoothingEnabled = false;
    var d = typeof who === "string" && Util.has(Data.npcs, who) ? Data.npcs[who] : null;
    if (!d && who !== null && who !== undefined) return out;
    var sp = d ? Sprites.npc(who, 4, 0, null) :
      Sprites.player(lastState && lastState.player ? lastState.player.eq : {}, 4, 0, null, lastState && lastState.player ? lastState.player.look : null);
    if (!d || Util.has(Sprites.HUMANOID, d.draw[0])) {
      var sc = d && d.scale === 2 ? 2 : 1;
      g.drawImage(sp.cv, (Sprites.DOLL.x + 4) * sc, Sprites.DOLL.y * sc, 8 * sc, 8 * sc, 0, 0, 48 * k, 48 * k);
      return out;
    }
    var b = sp.box, f = Math.max(1, Math.floor((48 * k) / Math.max(b[2], b[3])));
    g.drawImage(sp.cv, b[0], b[1], b[2], b[3], Math.floor((48 * k - b[2] * f) / 2), Math.floor((48 * k - b[3] * f) / 2),
      b[2] * f, b[3] * f);
    return out;
  }

  function reset() {
    splats = []; bars = {}; xps = []; crosses = []; fireworks = []; overheads = {}; breaths = []; flashes = {}; lastH = {};
    petPos = null;
    xpCarry = {};
    hoverRef = null; hoverMode = "normal"; camMap = null; lastState = null;
    resetTracking();
  }

  return {
    init: init, resize: resize, setZoom: setZoom, zoomStep: zoomStep, setInsets: setInsets, setOpts: setOpts,
    draw: draw, onEvents: onEvents, pick: pick, minimapPick: minimapPick, worldMap: worldMap, tileToClient: tileToClient,
    refToClient: refToClient, marker: marker, hover: hover, portrait: portrait, reset: reset,
    fallbacks: function () { return Sprites.fallbacks(); }
  };
})();
// ==== src/ui/music.js ====
// ----------------------------------------------------------------
// ----------------------------- Music ----------------------------
// ----------------------------------------------------------------
// Original looping tunes in a small Web Audio synth (no audio files): lute, harp, flute, reed, brass, bass,
// pad and a tabor kit. The track follows where the player is (town, wilds, dark places, the Deeps, a boss
// fight) and crossfades on a change. Audio starts on the first click or key (autoplay rules), pauses when the
// page is hidden or stops drawing (a docked panel on another OrcaSlicer tab), and obeys the Music options.
// Short cues for the big moments (level-up, mastery, rare drop, quest complete, rested) use the same voices
// on their own bus, so they play with Music off too; the Sound effects option silences them.
const Music = (function () {
  "use strict";

  var LOOKAHEAD = 0.25, STEP_MS = 50, FADE = 1.4, STALL_MS = 1500, LEVEL = 0.22, SFX_LEVEL = 0.26;

  // Chord voicings: [bass, arp/pad tones...].
  var CH = {
    D: ["D3", "D4", "A4", "D5"], G: ["G2", "G3", "D4", "G4"], A: ["A2", "A3", "E4", "A4"], Bm: ["B2", "B3", "F#4", "B4"],
    Am: ["A2", "A3", "E4", "C5"], Em: ["E2", "E3", "B3", "G4"], F: ["F2", "F3", "C4", "A4"], Dm: ["D2", "D3", "A3", "F4"],
    Bb: ["Bb1", "Bb2", "F3", "D4"], Gm: ["G1", "G2", "D3", "Bb3"], Cm: ["C2", "C3", "G3", "Eb4"], Ab: ["Ab1", "Ab2", "Eb3", "C4"],
    G7: ["G1", "G2", "D3", "B3"], A7: ["A1", "A2", "E3", "C#4"]
  };

  // Notation helpers: "F#5:2 r:1 D4+A4:3" (note:beats, r = rest, + = chord).
  function rep(s, n) { var o = []; for (var i = 0; i < n; i++) o.push(s); return o.join(" "); }
  function arp(chords, order, beat) {
    return chords.map(function (c) { return order.map(function (i) { return CH[c][i] + ":" + beat; }).join(" "); }).join(" ");
  }
  function roots(chords, beats) { return chords.map(function (c) { return CH[c][0] + ":" + beats; }).join(" "); }
  function pads(chords, beats) { return chords.map(function (c) { return CH[c].slice(1).join("+") + ":" + beats; }).join(" "); }

  var JIG = ["D", "G", "D", "A", "D", "G", "A", "D", "G", "D", "A", "D", "G", "D", "A", "D"];
  var BOUNCE = { D: "D3:3 A2:3", G: "G2:3 D3:3", A: "A2:3 E3:3" };
  var WILD = ["Am", "D", "Am", "G", "Am", "D", "Em", "Am", "D", "D", "Am", "G", "Am", "D", "G", "Am"];
  var DARK = ["Em", "F", "Em", "D", "Em", "F", "Em", "Em"];
  var CAVE = ["Dm", "Dm", "Bb", "Bb", "Gm", "Gm", "A7", "A7"];
  var BOSS = ["Cm", "Cm", "Ab", "G7", "Cm", "Cm", "Ab", "G7"];
  var OST = {
    Cm: "C3 C3 G2 C3 Eb3 C3 G2 Bb2", Ab: "Ab2 Ab2 Eb2 Ab2 C3 Ab2 Eb2 G2", G7: "G2 G2 D2 G2 B2 G2 D2 F2"
  };

  var TRACKS = {
    // "Hearth and Harvest": a bright 6/8 market jig in D major (a beat here is one eighth note).
    town: { bpm: 208, parts: [
      ["pipe", 0.42, "A4:2 D5:1 F#5:2 D5:1 G5:2 F#5:1 E5:2 D5:1 F#5:2 A5:1 A5:2 F#5:1 E5:3 C#5:2 A4:1 " +
        "A4:2 D5:1 F#5:2 A5:1 B5:2 A5:1 G5:2 B5:1 A5:2 G5:1 F#5:1 E5:1 C#5:1 D5:4 r:2 " +
        "B5:2 G5:1 D5:2 G5:1 A5:2 F#5:1 D5:2 F#5:1 E5:2 F#5:1 G5:2 E5:1 F#5:2 E5:1 D5:3 " +
        "G5:1 A5:1 B5:1 D6:2 B5:1 A5:2 F#5:1 D5:2 F#5:1 E5:1 F#5:1 G5:1 E5:2 C#5:1 D5:3 D6:2 r:1"],
      ["lute", 0.3, arp(JIG, [1, 2, 3, 3, 2, 1], 1)],
      ["bass", 0.45, JIG.map(function (c) { return BOUNCE[c]; }).join(" ")],
      ["bell", 0.16, JIG.map(function (c) { return CH[c][3].replace(/\d$/, function (o) { return String(+o + 1); }) + ":6"; }).join(" ")],
      ["drum", 0.26, rep("K:1 H:1 H:1 K:1 H:1 S:1", 16)]] },
    // "Over the Pinewood": an open Dorian walk for forests, farms and rivers.
    wild: { bpm: 80, parts: [
      ["flute", 0.48, "E5:2 D5:1 C5:1 D5:2 F#5:2 E5:1 C5:1 A4:2 B4:2 G4:2 A4:1 C5:1 E5:1 G5:1 F#5:2 E5:1 D5:1 " +
        "E5:1 D5:1 B4:2 A4:4 r:2 A5:1 G5:1 F#5:2 D5:2 E5:3 C5:1 B4:2 D5:2 C5:1 B4:1 A4:1 G4:1 A4:2 F#4:2 " +
        "G4:1 A4:1 B4:2 A4:4"],
      ["harp", 0.4, arp(WILD, [1, 2, 3, 2], 1)],
      ["bass", 0.45, roots(WILD, 4)]] },
    // "Gnarled Hollow": a low Phrygian reed over a tabor, for the swamp, goblin camp and ash.
    dark: { bpm: 72, parts: [
      ["reed", 0.42, "E4:3 F4:1 G4:2 F4:1 E4:1 D4:2 E4:2 D4:4 B4:2 A4:1 G4:1 A4:2 G4:1 F4:1 G4:1 F4:1 E4:2 E4:4"],
      ["pad", 0.22, pads(DARK, 4)],
      ["bass", 0.5, roots(DARK, 4)],
      ["drum", 0.42, rep("K:1 r:1 K:0.5 K:0.5 S:1", 8)]] },
    // "Embers in the Deep": slow harp drops over a cold pad, with an echo.
    cave: { bpm: 56, echo: true, parts: [
      ["harp", 0.42, "A5:2 r:1 F5:1 E5:2 r:2 D5:3 r:1 r:4 C5:1 D5:1 F5:2 E5:2 r:2 G5:2 r:1 F5:1 E5:4"],
      ["pad", 0.26, pads(CAVE, 4)],
      ["bass", 0.4, roots(CAVE, 4)]] },
    // "The Wyrm Wakes": driving C minor for boss fights.
    boss: { bpm: 132, parts: [
      ["brass", 0.34, "C5:1 Eb5:1 G5:2 F5:1 Eb5:1 D5:2 Eb5:1 D5:1 C5:1 Bb4:1 B4:2 G4:2 " +
        "C5:0.5 C5:0.5 Eb5:1 G5:1 C6:1 Bb5:1 G5:1 Eb5:2 F5:1 Eb5:1 D5:1 C5:1 D5:2 B4:2"],
      ["bass", 0.5, BOSS.map(function (c) { return OST[c].split(" ").map(function (n) { return n + ":0.5"; }).join(" "); }).join(" ")],
      ["drum", 0.42, rep("K:0.5 H:0.5 S:0.5 H:0.5 K:0.5 K:0.5 S:0.5 H:0.5", 8)]] }
  };

  var SEMI = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

  function midi(n) {
    var m = /^([A-G])(#|b)?(\d)$/.exec(n);
    if (!m) return -1;
    return SEMI[m[1]] + (m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0) + (parseInt(m[3], 10) + 1) * 12;
  }

  // A track's parts flattened into one beat-sorted event list.
  function compile(t) {
    var ev = [], len = 0;
    t.parts.forEach(function (part) {
      var b = 0;
      part[2].trim().split(/\s+/).forEach(function (tok) {
        var p = tok.split(":"), d = parseFloat(p[1]) || 1;
        if (p[0] !== "r") p[0].split("+").forEach(function (n) { ev.push({ b: b, d: d, n: n, m: midi(n), inst: part[0], v: part[1] }); });
        b += d;
      });
      len = Math.max(len, b);
    });
    ev.sort(function (a, c) { return a.b - c.b; });
    return { bpm: t.bpm, echo: !!t.echo, ev: ev, len: len };
  }

  var COMPILED = {};
  Object.keys(TRACKS).forEach(function (k) { COMPILED[k] = compile(TRACKS[k]); });

  // Cues in D major, like the town jig: [start s, voice, note, level, length s].
  var CUES = {
    level: [[0, "pipe", "D5", 0.5, 0.1], [0.09, "pipe", "F#5", 0.5, 0.1], [0.18, "pipe", "A5", 0.5, 0.1],
      [0.27, "pipe", "D6", 0.55, 0.45], [0.27, "bell", "D6", 0.4, 1], [0.27, "harp", "A4", 0.35, 0.6], [0.27, "harp", "F#4", 0.3, 0.6]],
    mastery: [[0, "brass", "A4", 0.5, 0.14], [0.16, "brass", "D5", 0.5, 0.14], [0.32, "brass", "F#5", 0.5, 0.14],
      [0.48, "brass", "A5", 0.55, 0.9], [0.48, "brass", "D5", 0.4, 0.9], [0.48, "bell", "D6", 0.45, 1], [0.8, "bell", "A6", 0.35, 1],
      [1.1, "bell", "D7", 0.3, 1]],
    rare: [[0, "bell", "A5", 0.4, 1], [0.06, "bell", "D6", 0.4, 1], [0.12, "bell", "F#6", 0.4, 1], [0.18, "bell", "A6", 0.4, 1],
      [0.24, "bell", "D7", 0.45, 1], [0.24, "harp", "D4", 0.4, 0.8], [0.24, "harp", "A4", 0.3, 0.8]],
    quest: [[0, "brass", "D5", 0.5, 0.12], [0.13, "brass", "D5", 0.5, 0.12], [0.26, "brass", "D5", 0.5, 0.12],
      [0.39, "brass", "A5", 0.55, 0.7], [0.39, "brass", "F#5", 0.45, 0.7], [0.39, "bass", "D3", 0.6, 0.7], [0.39, "bell", "D6", 0.35, 1],
      [1.1, "brass", "G5", 0.5, 0.18], [1.3, "brass", "A5", 0.55, 0.9], [1.3, "brass", "D5", 0.4, 0.9], [1.3, "bass", "D3", 0.6, 0.9],
      [1.3, "bell", "A6", 0.3, 1]],
    rested: [[0, "harp", "D4", 0.3, 0.6], [0.12, "harp", "F#4", 0.3, 0.6], [0.24, "harp", "A4", 0.3, 0.6], [0.36, "harp", "D5", 0.35, 0.9],
      [0.36, "bell", "A5", 0.2, 1]]
  };

  // ----------------------------------------------------------------
  // ---------------------------- Synth -----------------------------
  // ----------------------------------------------------------------

  var ac = null, master = null, noise = null, echo = null, sfxBus = null;
  var cur = null;   // { name, t, g, t0, ei }
  var on = true, vol = 0.5, want = "", lastSeen = 0, timer = 0, unlocked = false;
  var sfxOn = true, sfxUntil = 0, lastCue = "";   // sfxUntil: wall ms the latest cue rings until

  function hz(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  function env(g, when, peak, attack, hold, release) {
    g.gain.setValueAtTime(0.0001, when);
    g.gain.linearRampToValueAtTime(peak, when + attack);
    if (hold > 0) g.gain.setValueAtTime(peak, when + attack + hold);
    g.gain.exponentialRampToValueAtTime(0.0001, when + attack + Math.max(0, hold) + release);
    return when + attack + Math.max(0, hold) + release + 0.05;
  }

  function osc(type, f, when, end, out, detune) {
    var o = ac.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f, when);
    if (detune) o.detune.setValueAtTime(detune, when);
    o.connect(out);
    o.start(when);
    o.stop(end);
    return o;
  }

  function voice(out, v, filterHz) {
    var g = ac.createGain();
    if (filterHz) {
      var f = ac.createBiquadFilter();
      f.type = "lowpass";
      f.frequency.value = filterHz;
      g.connect(f);
      f.connect(out);
    } else g.connect(out);
    g.gain.value = 0;
    return g;
  }

  function hit(out, when, kind, v) {
    if (kind === "K") {
      var g = voice(out), o = ac.createOscillator();
      o.type = "sine";
      o.frequency.setValueAtTime(130, when);
      o.frequency.exponentialRampToValueAtTime(48, when + 0.14);
      o.connect(g);
      o.start(when);
      o.stop(env(g, when, v, 0.004, 0, 0.18));
      return;
    }
    var src = ac.createBufferSource(), f = ac.createBiquadFilter(), n = voice(out);
    src.buffer = noise;
    f.type = kind === "H" ? "highpass" : "bandpass";
    f.frequency.value = kind === "H" ? 7000 : 1800;
    src.connect(f);
    f.connect(n);
    src.start(when);
    src.stop(env(n, when, kind === "H" ? v * 0.35 : v * 0.7, 0.002, 0, kind === "H" ? 0.04 : 0.13));
  }

  function play(e, when, spb, out) {
    var v = e.v, dur = e.d * spb;
    if (e.inst === "drum") { hit(out, when, e.n, v); return; }
    if (e.m < 0) return;
    var f = hz(e.m), g, end;
    if (e.inst === "lute" || e.inst === "harp") {
      g = voice(out, v, e.inst === "harp" ? 3200 : 2400);
      end = env(g, when, v, 0.004, 0, Math.min(1.8, Math.max(0.45, dur * (e.inst === "harp" ? 2 : 1.3))));
      osc("triangle", f, when, end, g);
      var hi = ac.createGain();
      hi.gain.value = 0.25;
      hi.connect(g);
      osc("sine", f * 2, when, end, hi);
    } else if (e.inst === "flute") {
      g = voice(out, v, 2600);
      end = env(g, when, v * 0.8, 0.05, Math.max(0, dur * 0.85 - 0.05), 0.14);
      var fl = osc("sine", f, when, end, g), lfo = ac.createOscillator(), dep = ac.createGain();
      lfo.frequency.value = 5.4;
      dep.gain.value = f * 0.006;
      lfo.connect(dep);
      dep.connect(fl.frequency);
      lfo.start(when);
      lfo.stop(end);
    } else if (e.inst === "pipe") {
      // A tin whistle: triangle plus a touch of square, quick and a little detached, vibrato only on long notes.
      g = voice(out, v, 3600);
      end = env(g, when, v * 0.75, 0.012, Math.max(0, dur * 0.7 - 0.012), 0.07);
      var pw = osc("triangle", f, when, end, g), sq = ac.createGain();
      sq.gain.value = 0.16;
      sq.connect(g);
      osc("square", f, when, end, sq);
      if (dur > 0.5) {
        var vib = ac.createOscillator(), vd = ac.createGain();
        vib.frequency.value = 6;
        vd.gain.setValueAtTime(0, when);
        vd.gain.linearRampToValueAtTime(f * 0.004, when + 0.25);
        vib.connect(vd);
        vd.connect(pw.frequency);
        vib.start(when);
        vib.stop(end);
      }
    } else if (e.inst === "bell") {
      g = voice(out, v);
      end = env(g, when, v, 0.003, 0, 1.1);
      osc("sine", f, when, end, g);
      var ov = ac.createGain();
      ov.gain.value = 0.3;
      ov.connect(g);
      osc("sine", f * 2.76, when, end, ov);
    } else if (e.inst === "reed") {
      g = voice(out, v, 1400);
      end = env(g, when, v * 0.7, 0.04, Math.max(0, dur * 0.8 - 0.04), 0.18);
      osc("square", f, when, end, g, -4);
      osc("triangle", f, when, end, g, 4);
    } else if (e.inst === "brass") {
      g = voice(out, v, 1900);
      end = env(g, when, v * 0.6, 0.02, Math.max(0, dur * 0.75 - 0.02), 0.1);
      osc("sawtooth", f, when, end, g, -6);
      osc("sawtooth", f, when, end, g, 6);
    } else if (e.inst === "bass") {
      g = voice(out, v, 900);
      end = env(g, when, v, 0.006, 0, Math.max(0.25, dur * 0.7));
      osc("triangle", f, when, end, g);
    } else if (e.inst === "pad") {
      g = voice(out, v, 800);
      end = env(g, when, v * 0.5, Math.min(0.6, dur * 0.3), Math.max(0, dur * 0.6), 0.7);
      osc("sawtooth", f, when, end, g, -7);
      osc("sawtooth", f, when, end, g, 7);
    }
  }

  // ----------------------------------------------------------------
  // -------------------------- Scheduler ---------------------------
  // ----------------------------------------------------------------

  function build() {
    if (ac) return true;
    var C = window.AudioContext || window.webkitAudioContext;
    if (!C) return false;
    try { ac = new C(); } catch (err) { ac = null; return false; }
    master = ac.createGain();
    master.gain.value = on ? vol * LEVEL : 0;
    master.connect(ac.destination);
    sfxBus = ac.createGain();
    sfxBus.gain.value = sfxOn ? vol * SFX_LEVEL : 0;
    sfxBus.connect(ac.destination);
    echo = ac.createDelay(1);
    echo.delayTime.value = 0.36;
    var fb = ac.createGain();
    fb.gain.value = 0.32;
    echo.connect(fb);
    fb.connect(echo);
    echo.connect(master);
    noise = ac.createBuffer(1, Math.floor(ac.sampleRate * 0.25), ac.sampleRate);
    var d = noise.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    timer = setInterval(tick, STEP_MS);
    return true;
  }

  function start(name) {
    var now = ac.currentTime;
    if (cur) {
      var old = cur.g;
      old.gain.cancelScheduledValues(now);
      old.gain.setValueAtTime(old.gain.value, now);
      old.gain.linearRampToValueAtTime(0.0001, now + FADE);
      setTimeout(function () { old.disconnect(); }, (FADE + 2) * 1000);
    }
    cur = null;
    if (!name || !Util.has(COMPILED, name)) return;
    var g = ac.createGain();
    g.gain.setValueAtTime(0.0001, now);
    g.gain.linearRampToValueAtTime(1, now + FADE);
    g.connect(master);
    if (COMPILED[name].echo) {
      var send = ac.createGain();
      send.gain.value = 0.35;
      g.connect(send);
      send.connect(echo);
    }
    cur = { name: name, t: COMPILED[name], g: g, t0: now + 0.1, ei: 0 };
  }

  function tick() {
    if (!ac) return;
    var stalled = Date.now() - lastSeen > STALL_MS;
    // With Music off the context runs only while a cue rings.
    if ((stalled || document.hidden || (!on && Date.now() > sfxUntil)) && ac.state === "running") ac.suspend();
    if (ac.state !== "running" || !cur || !cur.t.ev.length) return;
    var spb = 60 / cur.t.bpm, horizon = ac.currentTime + LOOKAHEAD;
    for (var guard = 0; guard < 512; guard++) {
      var e = cur.t.ev[cur.ei], when = cur.t0 + e.b * spb;
      if (when > horizon) break;
      if (when >= ac.currentTime - 0.05) play(e, when, spb, cur.g);
      cur.ei++;
      if (cur.ei >= cur.t.ev.length) {
        cur.ei = 0;
        cur.t0 += cur.t.len * spb;
      }
    }
    // A long suspend leaves the loop behind the clock: rejoin at the next bar instead of racing to catch up.
    if (cur.t0 + cur.t.len * spb < ac.currentTime) { cur.t0 = ac.currentTime + 0.1; cur.ei = 0; }
  }

  // First click or key: browsers only allow audio after a gesture.
  function unlock() {
    unlocked = true;
    if (!on && !sfxOn) return;
    if (build() && on && ac.state !== "running" && !document.hidden) ac.resume();
  }

  // One cue (CUES key) on the effects bus, after the first gesture and while the page is shown and drawing.
  // Returns whether it was scheduled.
  function sfx(kind) {
    var cue = Util.has(CUES, kind) ? CUES[kind] : null;
    if (!cue || !sfxOn || !unlocked || document.hidden || Date.now() - lastSeen > STALL_MS || !build()) return false;
    if (ac.state !== "running") ac.resume();
    var t0 = ac.currentTime + 0.06, end = t0;
    cue.forEach(function (n) {
      play({ inst: n[1], m: midi(n[2]), v: n[3], d: n[4] }, t0 + n[0], 1, sfxBus);
      end = Math.max(end, t0 + n[0] + n[4] + 1.2);
    });
    sfxUntil = Date.now() + Math.ceil((end - ac.currentTime) * 1000);
    lastCue = kind;
    return true;
  }

  // ----------------------------------------------------------------
  // -------------------------- Track pick --------------------------
  // ----------------------------------------------------------------

  function inRect(r, x, y) { return Array.isArray(r) && x >= r[0] && y >= r[1] && x <= r[2] && y <= r[3]; }

  function trackFor(s) {
    var p = s.player;
    var foe = null;
    for (var i = 0; i < s.npcs.length && p.foe; i++) if (s.npcs[i].uid === p.foe) foe = s.npcs[i];
    var def = foe && Util.has(Data.npcs, foe.id) ? Data.npcs[foe.id] : null;
    if (def && def.combat && def.combat.boss && p.combatUntil > s.tick) return "boss";
    if (p.map !== "overworld") return "cave";
    var list = Array.isArray(Data.regions) ? Data.regions : [];
    for (var j = 0; j < list.length; j++) {
      var r = list[j];
      if (r && r.map === p.map && inRect(r.rect, p.x, p.y)) return r.town ? "town" : r.danger ? "dark" : "wild";
    }
    return "wild";
  }

  // Called every UI frame with the live state and the sound prefs (on: 0/1, vol: 25..100, effects: 0/1).
  function update(s, enabled, volume, effects) {
    lastSeen = Date.now();
    on = !!enabled;
    sfxOn = effects === undefined || !!effects;
    vol = Math.max(0, Math.min(1, (volume || 50) / 100));
    want = on && s && s.player && s.player.name ? trackFor(s) : "";
    if (!ac) return;
    master.gain.setTargetAtTime(on ? vol * LEVEL : 0, ac.currentTime, 0.1);
    sfxBus.gain.setTargetAtTime(sfxOn ? vol * SFX_LEVEL : 0, ac.currentTime, 0.05);
    if (on && unlocked && ac.state === "suspended" && !document.hidden) ac.resume();
    if ((cur ? cur.name : "") !== want) start(want);
  }

  function init() {
    document.addEventListener("pointerdown", unlock, true);
    document.addEventListener("keydown", unlock, true);
  }

  return { init: init, update: update, sfx: sfx, TRACKS: Object.keys(TRACKS), CUES: Object.keys(CUES),
    current: function () { return cur ? cur.name : ""; }, state: function () { return ac ? ac.state : "none"; },
    lastCue: function () { return lastCue; } };
})();
// ==== src/ui/ui.js ====
// ----------------------------------------------------------------
// ------------------ UI: DOM chrome, panes, windows --------------
// ----------------------------------------------------------------
// Builds and syncs every DOM surface of DESIGN.md 19: layout, status strip, minimap block, side tabs and
// panes, chat, windows, sheets, banner, toasts, veil and the chrome modal. State is read-only here: every
// change goes through ctx.act(Engine.*). Panels are built once and patched by signature, so a button
// under the cursor is never replaced between press and release.
const UI = (function () {
  "use strict";

  var TABS = ["combat", "skills", "quests", "inventory", "equipment", "options"];
  var TAB_NAMES = { combat: "Combat", skills: "Skills", quests: "Quests", inventory: "Inventory",
    equipment: "Equipment", options: "Options" };
  var X_SVG = '<svg viewBox="0 0 12 12"><path d="M2 2l8 8M10 2l-8 8"/></svg>';
  var FILTERS = ["all", "game", "skill", "loot", "fight"];
  var MSG_CS = ["game", "warn", "skill", "loot", "fight", "quest", "examine", "npc"];
  var FILTER_OF = { game: "game", npc: "game", quest: "game", warn: "game", examine: "game", skill: "skill",
    loot: "loot", fight: "fight" };
  var FILTER_LABEL = { game: "game", skill: "skill", loot: "loot", fight: "fight" };
  var DEFAULTS = { zoom: 32, tab: "inventory", fps: 30, shiftDrop: 1, atk: 0, xpDrops: 1, fireworks: 1, hints: 1,
    motion: 0, chatOverlay: 1, chatFilter: "all", bankQty: 1, makeQty: -1, shopQty: 1, tipFull: 0,
    music: 1, musicVol: 50, sfx: 1, ui: 1 };
  var CHAT_MAX = 200;
  var CHAT_SAVE = 30;
  var QTY_MAX = 2147483647;
  var EQ_SLOTS = ["head", "cape", "neck", "weapon", "body", "shield", "legs", "hands", "feet", "ring"];
  var EQ_NAMES = { head: "Head", cape: "Cape", neck: "Neck", weapon: "Weapon", body: "Body", shield: "Shield",
    legs: "Legs", hands: "Hands", feet: "Feet", ring: "Ring" };
  var ASK_FULL = "Pack full. Keep going while you're away?";
  var TIP_FULL = "Full packs are now dropped. Change it in Options → When full.";
  var GATHER = ["woodcutting", "mining", "fishing"];
  var TIP_COURIER = "Unlocks with The River Courier (Bram, Willowmere)";
  var FULL3 = [["stop", "Stop"], ["drop", "Drop"], ["courier", "Courier"]];
  var OPTIONS = [
    { k: "dock", label: "Panel", seg: [["right", "Docked"], ["window", "Separate window"]],
      note: "Drag the panel's title bar to move or float it; OrcaSlicer remembers where. Separate window applies next time you open Orcadia." },
    { k: "ui", label: "Interface size", seg: [["0", "Small"], ["1", "Standard"], ["2", "Large"], ["3", "Extra large"]],
      note: "The side panel and windows: icons, slots and text." },
    { k: "music", label: "Music" },
    { k: "sfx", label: "Sound effects" },
    { k: "musicVol", label: "Volume", seg: [["25", "Quiet"], ["50", "Medium"], ["75", "Loud"], ["100", "Full"]] },
    { k: "afk.cont", label: "Auto-continue" },
    { k: "afk.loot", label: "Auto-loot" },
    { k: "full.woodcutting", label: "When full: Woodcutting", seg: FULL3 },
    { k: "full.mining", label: "When full: Mining", seg: FULL3 },
    { k: "full.fishing", label: "When full: Fishing", seg: FULL3 },
    { k: "full.combat", label: "When full: Combat loot", seg: [["stop", "Stop"], ["courier", "Courier"]] },
    { k: "fps", label: "Frame rate", seg: [["60", "Smooth"], ["30", "Light"]] },
    { k: "shiftDrop", label: "Shift-click drop" },
    { k: "atk", label: "Attack option", seg: [["0", "Depends on level"], ["1", "Left-click"], ["2", "Right-click only"]] },
    { k: "xpDrops", label: "XP drops" },
    { k: "fireworks", label: "Level-up fireworks" },
    { k: "hints", label: "Quest hint arrows" },
    { k: "chatOverlay", label: "Chat overlay (compact layout)" },
    { k: "motion", label: "Reduce motion", seg: [["0", "Auto"], ["1", "On"], ["2", "Off"]] }
  ];

  var ctx = null;
  var prefs = copy(DEFAULTS);
  var dock = "right";
  var L = "";
  var sz = null;
  var tabPx = 0;             // css px the tab glyphs were last built at
  var lines = [];            // chat: { c, text, n, at, el }
  var sigs = {};             // last rendered signature per surface
  var uiWin = null;          // UI-only window: { kind: journal|guide|away|questdone, ... }
  var winFresh = true;       // the next frame() is a newly opened window: its body starts scrolled to the top
  var prompt = null;         // amount prompt: { done(n) }
  var lastRid = null;        // Make-X: the last product made (Space repeats it)
  var prevTab = null;        // tab to restore after a bank or shop closes
  var paneOpen = false;      // layout C: the pane sheet is open
  var sheetH = 0;
  var bannerUntil = 0;
  var toastQ = [];
  var toastUntil = 0;
  var toastCur = null;
  var flashUntil = {};
  var death = null;          // { at } while the death veil shows
  var doneQ = [];            // quest-complete windows waiting for the dialogue (or store) to close
  var veilKind = "";
  var flashPrice = { i: -1, until: 0 };
  var modalTimer = 0;
  var tipTimer = 0;
  var lastGather = null;     // { ref, op, base }: the gather a pack-full stop ended (else the latest seen); Drop resumes it
  var layoutQueued = false;
  var els = {};

  // ----------------------------------------------------------------
  // --------------------------- Helpers ----------------------------
  // ----------------------------------------------------------------

  function copy(o) { return JSON.parse(JSON.stringify(o)); }
  function $(id) { return els[id] || (els[id] = document.getElementById(id)); }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;"; });
  }
  function itemDef(id) { return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id] : null; }
  function itemName(id) { var d = itemDef(id); return d ? d.name : ""; }
  function skillDef(id) {
    var list = Array.isArray(Data.skills) ? Data.skills : [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function skillName(id) { var d = skillDef(id); return d ? d.name : String(id); }
  function skillColor(id) { var d = skillDef(id); return d && d.color ? d.color : "#37c871"; }
  function state() { return ctx.state(); }
  function act(fn) { return ctx.act(fn); }

  function ico(id, qty) {
    return '<i class="ico" style="' + esc(Icons.css(id, qty)) + '"></i>';
  }
  function qtyTag(id, qty) {
    var d = itemDef(id);
    if (!d || (!d.stack && qty <= 1)) return "";
    return '<b class="q q-' + Util.qtyClass(qty) + '">' + Util.fmtQty(qty) + "</b>";
  }
  function skillIco(id, px) {
    return '<i class="ico" style="width:' + px + "px;height:" + px + "px;" + esc(Icons.skillCss(id, px)) + '"></i>';
  }
  function setHtml(el, key, sig, html) {
    if (sigs[key] === sig) return false;
    sigs[key] = sig;
    el.innerHTML = html;
    return true;
  }
  function toggle(el, cls, on) { if (el.classList.contains(cls) !== !!on) el.classList.toggle(cls, !!on); }
  function text(el, t) { if (el.textContent !== t) el.textContent = t; }
  function setAttr(el, k, v) { if (el.getAttribute(k) !== v) el.setAttribute(k, v); }
  function setDisabled(el, on) { if (el.disabled !== !!on) el.disabled = !!on; }

  // ----------------------------------------------------------------
  // ---------------------- Perk points (views) ---------------------
  // ----------------------------------------------------------------
  // Every perk surface feature-detects the engine's perk API, so the page still runs on an engine without it.
  var perkMemo = { sig: null, free: {} };
  function perksOn() {
    return typeof Engine.view.perks === "function" && typeof Engine.view.perkFree === "function" &&
      typeof Engine.perkUp === "function" && typeof Engine.perkReset === "function";
  }
  // { skillId: free points }, recomputed only when levels or ranks change.
  function perkFree(s) {
    if (!perksOn()) return {};
    var sig = JSON.stringify([s.player.xp10, s.player.perks || null]);
    if (perkMemo.sig !== sig) { perkMemo.sig = sig; perkMemo.free = Engine.view.perkFree(s) || {}; }
    return perkMemo.free;
  }
  function freeTotal(s) {
    var f = perkFree(s);
    return Object.keys(f).reduce(function (n, k) { return n + (f[k] > 0 ? f[k] : 0); }, 0);
  }
  function pointsText(n) { return n + (n === 1 ? " perk point" : " perk points"); }
  // "2 perk points to spend", else when the next one comes (a point every 5 levels, the last at 95).
  function perkLine(v) {
    if (v.free > 0) return pointsText(v.free) + " to spend";
    return v.level >= 95 ? "Every perk point earned" : "Next point at level " + (Math.floor(v.level / 5) + 1) * 5;
  }
  function packCoins(s) {
    return s.player.inv.reduce(function (n, it) { return n + (it && it.id === "coins" ? it.qty : 0); }, 0);
  }

  // Keeps box at n cells; a cell is rewritten only when its signature changed. labelOf names the icon-only
  // cell for screen readers (role button: Input handles its clicks).
  function syncCells(box, n, cls, attr, sigOf, htmlOf, labelOf) {
    while (box.children.length > n) box.removeChild(box.lastChild);
    while (box.children.length < n) {
      var c = document.createElement("div");
      c.className = cls;
      c.setAttribute(attr, String(box.children.length));
      c.setAttribute("role", "button");
      box.appendChild(c);
    }
    for (var i = 0; i < n; i++) {
      var cell = box.children[i];
      var sig = sigOf(i);
      if (cell._sig !== sig) {
        cell._sig = sig;
        cell.innerHTML = htmlOf(i);
        cell.setAttribute("aria-label", labelOf(i));
      }
    }
  }

  // "Coins ×50", "Logs", or "Empty slot".
  function slotLabel(id, qty) {
    if (!itemDef(id)) return "Empty slot";
    return itemName(id) + (qty > 1 ? " ×" + Util.fmtInt(qty) : "");
  }

  // "1", "5", "All", "All-but-1", or a typed count.
  function qtyLabel(n) { return n === -1 ? "All" : n === -2 ? "All-but-1" : Util.fmtInt(n); }

  // ----------------------------------------------------------------
  // ---------------------------- Prefs -----------------------------
  // ----------------------------------------------------------------

  function oneOf(list) { return function (v) { return list.indexOf(v) >= 0 ? v : null; }; }
  function count(v) { return v === -1 || (typeof v === "number" && v >= 1 && v <= QTY_MAX && Math.floor(v) === v) ? v : null; }
  var PREF_RULES = {
    zoom: function (v) { return typeof v === "number" && v >= 22 && v <= 64 ? Math.round(v) : null; },
    tab: oneOf(TABS), fps: oneOf([30, 60]), shiftDrop: oneOf([0, 1]), atk: oneOf([0, 1, 2]), xpDrops: oneOf([0, 1]),
    fireworks: oneOf([0, 1]), hints: oneOf([0, 1]), motion: oneOf([0, 1, 2]), chatOverlay: oneOf([0, 1]),
    chatFilter: oneOf(FILTERS), bankQty: count, makeQty: count, shopQty: oneOf([1, 5, 10, 50]), tipFull: oneOf([0, 1]),
    music: oneOf([0, 1]), musicVol: oneOf([25, 50, 75, 100]), sfx: oneOf([0, 1]), ui: oneOf([0, 1, 2, 3])
  };

  function setPrefs(obj) {
    var o = obj && typeof obj === "object" ? obj : {};
    var out = {};
    Object.keys(DEFAULTS).forEach(function (k) {
      var v = Util.has(o, k) ? PREF_RULES[k](o[k]) : null;
      out[k] = v === null ? DEFAULTS[k] : v;
    });
    prefs = out;
    applyPrefs();
  }

  function getPrefs() { return copy(prefs); }

  function reducedMotion() {
    if (prefs.motion === 1) return true;
    if (prefs.motion === 2) return false;
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // Interface size: the zoom of the side column's contents and of windows (Layout sizes the column for it).
  function uiScale() { return Layout.SCALES[prefs.ui] || 1; }

  function applyPrefs() {
    prefs.zoom = Render.setZoom(prefs.zoom) || prefs.zoom;
    if (sz && sz.scale !== uiScale()) {
      applyLayout();
      Object.keys(sigs).forEach(function (k) { sigs[k] = null; });
      $("pane").querySelectorAll(".cb-pets").forEach(function (b) { b._shape = null; });
    }
    // Render-only toggles (hint arrows, motion) have no 18.1 call; Render offers setOpts.
    if (typeof Render.setOpts === "function") {
      Render.setOpts({ hints: prefs.hints, xpDrops: prefs.xpDrops, fireworks: prefs.fireworks, motion: prefs.motion });
    }
    document.body.setAttribute("data-motion", reducedMotion() ? "reduce" : "");
    setFilter(prefs.chatFilter);
    toggle($("app"), "chat-off", !prefs.chatOverlay);
    selectTab(prefs.tab, true);
    sigs["pane:options"] = null;
    // At once, not at the next draw: a cue in the very next event batch must hear a new Sound effects choice.
    if (ctx) Music.update(state(), prefs.music, prefs.musicVol, prefs.sfx);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Theme -----------------------------
  // ----------------------------------------------------------------

  // data-orca-theme decides; the luminance of --orca-bg is a harness-only fallback.
  function applyTheme() {
    var a = document.documentElement.getAttribute("data-orca-theme");
    var light = a === "light";
    if (a !== "light" && a !== "dark") {
      var bg = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g) || [0, 0, 0];
      light = (0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2]) / 255 > 0.5;
    }
    document.body.setAttribute("data-theme", light ? "light" : "dark");
  }

  function watchTheme() {
    applyTheme();
    if (!window.MutationObserver) return;
    var mo = new MutationObserver(applyTheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-orca-theme"] });
    var vars = document.getElementById("orca-host-theme-vars");
    if (vars) mo.observe(vars, { childList: true, characterData: true, subtree: true });
  }

  // ----------------------------------------------------------------
  // ---------------------------- Layout ----------------------------
  // ----------------------------------------------------------------

  function queueLayout() {
    if (layoutQueued) return;
    layoutQueued = true;
    requestAnimationFrame(function () { layoutQueued = false; applyLayout(); });
  }

  function cssVar(name, v) { $("app").style.setProperty(name, v); }

  function applyLayout() {
    var app = $("app");
    var w = app.clientWidth;
    var h = app.clientHeight;
    var next = Layout.layoutFor(w, h, L || null, uiScale());
    var z = Layout.sizes(next, w, h, uiScale());
    var changed = next !== L;
    L = next;
    sz = z;
    app.setAttribute("data-layout", L);
    cssVar("--bottom", z.bottom + "px");
    cssVar("--side", z.side + "px");
    cssVar("--sw", z.slot.w + "px");
    cssVar("--sh", z.slot.h + "px");
    cssVar("--mm", z.mmDiam + "px");
    cssVar("--cf", z.chatFont + "px");
    cssVar("--cl", z.chatLine + "px");
    cssVar("--ui", String(z.scale));
    cssVar("--tabs", z.tabs + "px");
    cssVar("--tab-ico", z.tabIco + "px");
    if (tabPx !== z.tabIco) buildTabs(z.tabIco);
    cssVar("--pane-c", Math.max(160, Math.min(Math.round(264 * z.scale), z.view.h - 110)) + "px");
    cssVar("--pane-cs", Math.max(140, Math.min(Math.round(264 * z.scale), z.view.h - 232)) + "px");
    cssVar("--mmr", z.mmDiam + 16 + "px");
    // The minimap block sits at the view's top-right (8, 8); the hover line stops short of it.
    var mm = $("mm");
    mm.style.left = z.view.w - 8 - z.mmDiam + "px";
    mm.style.top = "34px";
    $("hover").style.maxWidth = Math.max(40, z.view.w - z.mmDiam - 24) + "px";
    if (changed) {
      paneOpen = false;
      syncPaneOpen();
      $("chatlog").scrollTop = $("chatlog").scrollHeight;
    }
    Render.resize(z);
    insets();
    askHeight();
    return L;
  }

  // What covers the view's bottom: the open sheet, or in layout C the open pane (shorter beside a bank or shop).
  function bottomInset() {
    var store = $("app").classList.contains("store");
    var pc = L === "C" && paneOpen ? parseInt($("app").style.getPropertyValue(store ? "--pane-cs" : "--pane-c"), 10) || 264 : 0;
    return Math.max(pc, sheetH);
  }

  // The camera centres the player above it; the level-up toast sits above it.
  function insets() {
    var ob = 8 + (sz ? sz.mmDiam : 84) + 64;
    var b = bottomInset();
    Render.setInsets({ bottom: b, orbsBottom: ob });
    cssVar("--toast-b", b + "px");
  }

  // ----------------------------------------------------------------
  // ----------------------------- Tabs -----------------------------
  // ----------------------------------------------------------------

  // Tab glyphs are drawn at the Layout's tabIco css px (the tab row is not zoomed), so a size change rebuilds them.
  function buildTabs(px) {
    var bs = $("tabs").children;
    tabPx = px || 24;
    for (var i = 0; i < bs.length; i++) {
      var id = bs[i].getAttribute("data-tab");
      bs[i].setAttribute("data-tip", TAB_NAMES[id]);
      bs[i].setAttribute("aria-label", TAB_NAMES[id]);
      bs[i].innerHTML = '<i class="ico" style="' + esc(Icons.tabCss(id, tabPx)) + '"></i>';
    }
  }

  function selectTab(id, quiet) {
    if (TABS.indexOf(id) < 0) return;
    prefs.tab = id;
    var bs = $("tabs").children;
    for (var i = 0; i < bs.length; i++) toggle(bs[i], "on", bs[i].getAttribute("data-tab") === id && (L !== "C" || paneOpen));
    var ss = $("pane").children;
    for (var k = 0; k < ss.length; k++) toggle(ss[k], "on", ss[k].getAttribute("data-pane") === id);
    if (!quiet) sigs["pane:" + id] = null;
  }

  function clickTab(id) {
    if (L === "C") paneOpen = !(paneOpen && prefs.tab === id);
    selectTab(id);
    syncPaneOpen();
  }

  function syncPaneOpen() {
    toggle($("app"), "pane-open", L === "C" && paneOpen);
    selectTab(prefs.tab, true);
    winBottom();
  }

  // A window ends above an open sheet, and in layout C above the open pane. T: 6 px higher, clear of the
  // scroll's roll that lies 11 px into the view bottom.
  function winBottom() {
    cssVar("--win-b", bottomInset() + (L === "T" ? 10 : 4) + "px");
    insets();
  }

  // Bank and shop force the Inventory tab; the previous tab returns afterwards.
  function syncIfaceTab(s) {
    var f = s.player.iface;
    var store = !!f && (f.t === "bank" || f.t === "shop");
    toggle($("app"), "store", store);
    if (store && prevTab === null) {
      prevTab = { tab: prefs.tab, open: paneOpen };
      if (L === "C") paneOpen = true;
      selectTab("inventory");
      syncPaneOpen();
    } else if (!store && prevTab !== null) {
      var p = prevTab;
      prevTab = null;
      if (L === "C") paneOpen = p.open;
      selectTab(p.tab);
      syncPaneOpen();
    }
  }

  // ----------------------------------------------------------------
  // ------------------------- Status strip -------------------------
  // ----------------------------------------------------------------

  function skillPct(s, id) {
    var xp = Util.has(s.player.xp10, id) ? s.player.xp10[id] / 10 : 0;
    var lvl = Rules.levelForXp(xp);
    if (lvl >= 99) return 100;
    var lo = Rules.xpForLevel(lvl);
    return Math.max(0, Math.min(100, (xp - lo) * 100 / (Rules.xpForLevel(lvl + 1) - lo)));
  }

  function syncStatus(s, st) {
    var d = st.doing;
    var stopped = !!st.stop && !s.player.act && d.dot !== "dead";
    var t = sz && sz.tooSmall ? "Panel too small: drag it larger" : stopped ? "Idle: " + st.stop : d.text;
    text($("st-text"), t);
    var dot = stopped ? "stop" : d.dot;
    if ($("st-dot").getAttribute("data-dot") !== dot) $("st-dot").setAttribute("data-dot", dot);
    toggle($("status"), "stop", stopped);
    text($("st-packn"), st.pack + "/28");
    toggle($("st-pack"), "full", st.pack >= 28);
    syncGoalChip(s, st, stopped);
    syncGraveChip(s);
    syncRestedChip(st);
    syncSeasonChip(s);
    var fill = $("st-fill");
    var w = d.skill ? skillPct(s, d.skill).toFixed(1) + "%" : "0%";
    if (fill.style.width !== w) fill.style.width = w;
    var col = d.skill ? skillColor(d.skill) : "";
    if (fill._col !== col) { fill._col = col; fill.style.background = col; }
    var bs = $("tabs").children;
    var free = freeTotal(s);
    for (var i = 0; i < bs.length; i++) {
      var tab = bs[i].getAttribute("data-tab");
      if (tab === "inventory") toggle(bs[i], "badge", st.pack >= 28 || st.stop !== null);
      if (tab === "skills") {
        toggle(bs[i], "badge", free > 0);
        setAttr(bs[i], "data-tip", free > 0 ? "Skills · " + pointsText(free) + " to spend" : TAB_NAMES.skills);
      }
    }
  }

  // "Grave 9:41" while a gravestone stands (its pin is on the minimap); the tip names where.
  function syncGraveChip(s) {
    var el = $("st-grave"), g = Engine.view.grave(s);
    if (el.hidden !== !g) el.hidden = !g;
    if (!g) return;
    text(el, "Grave " + Util.fmtDur(g.ticksLeft));
    var tip = "Your gravestone waits in " + graveWhere(g) + ". The grey pin on the minimap leads to it.";
    if (el.getAttribute("data-tip") !== tip) el.setAttribute("data-tip", tip);
  }

  // ----------------------------------------------------------------
  // ------------------------- Season chip --------------------------
  // ----------------------------------------------------------------
  // "Autumn · 42m" (minutes until the next season) with the season's glyph; the tip says what it changes.
  // Hidden while the engine has no season data.
  function seasonDef(id) {
    return (Array.isArray(Data.seasons) ? Data.seasons : []).filter(function (d) { return d && d.id === id; })[0] || null;
  }

  function syncSeasonChip(s) {
    var el = $("st-season"), v = typeof Engine.view.season === "function" ? Engine.view.season(s) : null;
    if (el.hidden !== !v) el.hidden = !v;
    if (!v) return;
    var mins = Math.max(1, Math.ceil(v.ticksLeft / 100)), list = Array.isArray(Data.seasons) ? Data.seasons : [];
    var next = list[(list.indexOf(seasonDef(v.id)) + 1) % Math.max(1, list.length)];
    text(el.lastChild, v.name + " · " + mins + "m");
    if (el._id !== v.id) { el._id = v.id; el.firstChild.setAttribute("style", Icons.seasonCss(v.id, 16)); }
    var tip = v.name + ": " + v.effect + " " + (next ? next.name + " comes in " + mins + " min." : "");
    if (el.getAttribute("data-tip") !== tip) el.setAttribute("data-tip", tip);
  }

  // The banner when a season turns: its glyph, "Autumn arrives." and what it changes.
  function seasonBanner(id) {
    var d = seasonDef(id);
    if (!d) return;
    banner(d.name + " arrives. " + d.effect, "season");
    $("banner").firstChild.insertAdjacentHTML("afterbegin", '<i class="ico" style="' + esc(Icons.seasonCss(d.id, 16)) + '"></i>');
  }

  // ----------------------------------------------------------------
  // -------------------------- Goal chip ---------------------------
  // ----------------------------------------------------------------
  // "· 12m to Willow tree" after the doing text (10.15): the next milestone of the skill being trained and,
  // once RATE_MIN ticks are measured, the time to it at the current pace. The pace is the tracked skill's
  // gains over the last RATE_WINDOW ticks of game time; a catch-up (whose gains the UI never sees) restarts
  // it through resync, and so does a whole window without a gain.
  var RATE_WINDOW = 1000;
  var RATE_MIN = 100;
  var trk = { skill: null, since: 0, gains: [] };   // gains: [tick, xp]
  var goalMemo = {};                                 // skill -> { x: xp10, g: view.goal }

  function goalOf(s, k) {
    var x = Util.has(s.player.xp10, k) ? s.player.xp10[k] : 0;
    if (!goalMemo[k] || goalMemo[k].x !== x) goalMemo[k] = { x: x, g: Engine.view.goal(s, k) };
    return goalMemo[k].g;
  }

  // The skill the activity trains: gathering and making name it; a fight trains its style's skill
  // (Controlled: the one closest to its goal).
  function goalSkill(s, d) {
    if (d.skill) return d.skill;
    if (d.dot !== "fight") return null;
    var best = null;
    Rules.style(s.player.style).xp.forEach(function (k) {
      var g = goalOf(s, k);
      if (g && (!best || g.need < best.need)) best = g;
    });
    return best ? best.skill : null;
  }

  function trackSkill(skill, tick) {
    if (skill && skill !== trk.skill) trk = { skill: skill, since: tick, gains: [] };
    var lastAt = trk.gains.length ? trk.gains[trk.gains.length - 1][0] : trk.since;
    if (tick - lastAt > RATE_WINDOW) trk = { skill: trk.skill, since: tick, gains: [] };
    while (trk.gains.length && trk.gains[0][0] < tick - RATE_WINDOW) trk.gains.shift();
  }

  // XP per tick of the tracked skill, or 0 until RATE_MIN ticks are measured.
  function xpRate(tick) {
    var from = Math.max(trk.since, tick - RATE_WINDOW);
    if (tick - from < RATE_MIN) return 0;
    var sum = 0;
    for (var i = 0; i < trk.gains.length; i++) if (trk.gains[i][0] >= from) sum += trk.gains[i][1];
    return sum / (tick - from);
  }

  // "12m", "1h 5m" (short, for the chip) or "12 min", "1 h 5 min" (long, for tips), rounded up to a minute.
  function etaText(ticks, long) {
    var m = Math.max(1, Math.ceil(ticks / 100));
    var h = Math.floor(m / 60);
    if (long) return h ? h + " h" + (m % 60 ? " " + (m % 60) + " min" : "") : m + " min";
    return h ? h + "h " + (m % 60) + "m" : m + "m";
  }

  function goalWhat(g) {
    return g.names.length ? g.names[0] : g.perk ? "a perk point" : g.mastery ? skillName(g.skill) + " 99" : "level " + g.at;
  }

  // "Woodcutting 30: Willow tree and a perk point. 1,240 XP to go at 37,400 XP/h: about 12 min."
  function goalTip(g, perTick) {
    var n = g.names, list = n.length > 3 ? n.slice(0, 3).join(", ") + " and " + (n.length - 3) + " more" : n.join(", ");
    var parts = [];
    if (list) parts.push(list);
    if (g.perk) parts.push("a perk point");
    if (g.mastery) parts.push("mastery");
    var head = skillName(g.skill) + " " + g.at + (parts.length ? ": " + parts.join(" and ") : "") + ". ";
    var pace = perTick > 0 ? " at " + Util.fmtInt(Math.round(perTick * 6000)) + " XP/h: about " + etaText(g.need / perTick, true) + "."
      : ". Keep at it a minute to see your XP/h.";
    return head + Util.fmtInt(g.need) + " XP to go" + pace;
  }

  function syncGoalChip(s, st, stopped) {
    var el = $("st-goal");
    var skill = sz && sz.tooSmall || stopped ? null : goalSkill(s, st.doing);
    trackSkill(skill, s.tick);
    var g = skill ? goalOf(s, skill) : null;
    var perTick = g ? xpRate(s.tick) : 0;
    text(el, g ? "· " + (perTick > 0 ? etaText(g.need / perTick) : Util.fmtInt(g.need) + " XP") + " to " + goalWhat(g) : "");
    // An empty spacer while there is no goal: no tip to show over it.
    if (g) setAttr(el, "data-tip", goalTip(g, perTick));
    else if (el.hasAttribute("data-tip")) el.removeAttribute("data-tip");
  }

  // An XP drop of the tracked skill feeds the pace.
  function trackXp(e, tick) {
    if (e.skill === trk.skill && e.amt > 0) trk.gains.push([tick, e.amt]);
  }

  // "Rested 54m" while the pool lasts (10.14).
  function syncRestedChip(st) {
    var el = $("st-rested");
    if (el.hidden !== !(st.rested > 0)) el.hidden = !(st.rested > 0);
    if (!(st.rested > 0)) return;
    text(el, "Rested " + etaText(st.rested));
    setAttr(el, "data-tip", "Rested: your next " + etaText(st.rested, true) + " of gathering, making and fighting earn double XP. " +
      "Time away past the catch-up limit rests you (10 min away for each minute, up to 1 h).");
  }

  function syncOrbs(st) {
    var hp = $("orb-hp");
    text(hp.lastChild, String(st.hp));
    var p = Math.round(100 * st.hp / Math.max(1, st.maxHp)) + "%";
    if (hp._p !== p) { hp._p = p; hp.style.setProperty("--p", p); }
    toggle(hp, "low", st.hp * 4 <= st.maxHp);
    var tip = "Vitality " + st.hp + "/" + st.maxHp;
    if (hp._tip !== tip) { hp._tip = tip; hp.setAttribute("data-tip", tip); hp.setAttribute("aria-label", tip); }
    var run = $("orb-run");
    toggle(run, "on", !!st.run);
    if (run.getAttribute("aria-pressed") !== String(!!st.run)) run.setAttribute("aria-pressed", String(!!st.run));
  }

  function notSaving(on) { $("st-nosave").hidden = !on; }

  // ----------------------------------------------------------------
  // ----------------------------- Chat -----------------------------
  // ----------------------------------------------------------------

  function lineText(ln) { return ln.n > 1 ? ln.text + " (×" + ln.n + ")" : ln.text; }

  function drawLine(ln) {
    var el = ln.el;
    if (!el) {
      el = ln.el = document.createElement("div");
      el.className = "ln c-" + ln.c + " f-" + FILTER_OF[ln.c];
    }
    el.textContent = ln.text;
    if (ln.n > 1) {
      var x = document.createElement("span");
      x.className = "x";
      x.textContent = " (×" + ln.n + ")";
      el.appendChild(x);
    }
  }

  function atBottom() {
    var log = $("chatlog");
    return log.scrollTop + log.clientHeight >= log.scrollHeight - 4;
  }

  function addLine(textIn, c, at) {
    var t = String(textIn).slice(0, 400);
    if (!t) return;
    var cc = MSG_CS.indexOf(c) >= 0 ? c : "game";
    var log = $("chatlog");
    var pinned = atBottom();
    var last = lines.length ? lines[lines.length - 1] : null;
    if (at && last && last.text === t && last.c === cc) {
      last.n++;
      last.at = at;
      drawLine(last);
    } else {
      var ln = { c: cc, text: t, n: 1, at: at, el: null };
      drawLine(ln);
      lines.push(ln);
      log.appendChild(ln.el);
      while (lines.length > CHAT_MAX) {
        var old = lines.shift();
        if (old.el && old.el.parentNode) old.el.parentNode.removeChild(old.el);
      }
    }
    if (pinned || L === "C") log.scrollTop = log.scrollHeight;
    else if (FILTER_OF[cc] === prefs.chatFilter || prefs.chatFilter === "all") $("newmsgs").hidden = false;
    syncEmpty();
  }

  // A filter with nothing to show says so (with a way back), instead of a blank log.
  function syncEmpty() {
    var f = prefs.chatFilter;
    var none = Util.has(FILTER_LABEL, f) && !$("chatlog").querySelector(".f-" + f);
    $("chatempty").hidden = !none;
    if (none) $("chatempty-t").textContent = "No " + FILTER_LABEL[f] + " messages yet.";
  }

  function chatLine(t, c) { addLine(t, c, Date.now()); }

  function chat() {
    return lines.slice(-CHAT_SAVE).map(function (l) { return [l.c, lineText(l)]; });
  }

  function setChat(arr) {
    clearChat();
    if (!Array.isArray(arr)) return;
    arr.slice(-CHAT_SAVE).forEach(function (e) {
      if (Array.isArray(e) && typeof e[1] === "string" && MSG_CS.indexOf(e[0]) >= 0) addLine(e[1], e[0], 0);
    });
    $("chatlog").scrollTop = $("chatlog").scrollHeight;
  }

  function clearChat() {
    lines = [];
    $("chatlog").innerHTML = "";
    $("newmsgs").hidden = true;
    syncEmpty();
  }

  function setFilter(f) {
    if (FILTERS.indexOf(f) < 0 || $("chatlog").getAttribute("data-filter") === f) return;
    prefs.chatFilter = f;
    $("chatlog").setAttribute("data-filter", f);
    var bs = $("chatfilters").children;
    for (var i = 0; i < bs.length; i++) toggle(bs[i], "on", bs[i].getAttribute("data-filter") === f);
    $("chatlog").scrollTop = $("chatlog").scrollHeight;
    $("newmsgs").hidden = true;
    syncEmpty();
  }

  // ----------------------------------------------------------------
  // ------------------------- Side panes ---------------------------
  // ----------------------------------------------------------------

  function syncPane(s, st) {
    if (L === "C" && !paneOpen) return;
    var t = prefs.tab;
    if (t === "combat") syncCombat(s);
    else if (t === "skills") syncSkills(s);
    else if (t === "quests") syncQuests(s);
    else if (t === "inventory") syncInv(s);
    else if (t === "equipment") syncEquip(s);
    else syncOptions(s);
  }

  function pane(id) { return $("pane").querySelector('[data-pane="' + id + '"]'); }

  // Combat: built once, then patched.
  function buildCombat() {
    var styles = Rules.STYLES.map(function (st) {
      return '<button data-act="style" data-v="' + st.id + '">' + esc(st.name) + "<span></span></button>";
    }).join("");
    var eats = [[0, "Off"], [30, "30%"], [50, "50%"], [70, "70%"]].map(function (e) {
      return '<button data-act="eat" data-v="' + e[0] + '">' + e[1] + "</button>";
    }).join("");
    pane("combat").innerHTML = '<div class="cb-w"><span class="cb-i"></span><div><b class="cb-n"></b><span class="cb-c"></span></div></div>' +
      '<div class="cb-lvl"></div><div class="cb-st">' + styles + "</div>" +
      '<button class="tgl" data-act="ret">Auto-retaliate<i class="sw"></i></button>' +
      '<div class="cb-eatrow"><span>Auto-eat</span><div class="seg cb-eat">' + eats + "</div></div>" +
      '<button class="btn cb-rc" data-act="recall"></button>' +
      '<div class="cb-ph"><b>Pets</b><span></span></div><div class="cb-pets"></div>';
  }

  function weaponKind(id) {
    var d = itemDef(id);
    if (!d) return "Fists · Speed 4";
    // A two-hander says so instead of its kind (the name already says greatsword), so the line fits the side pane.
    var k = d.equip && d.equip.twoHanded ? "two-handed" : d.icon && d.icon[0] ? String(d.icon[0]) : "weapon";
    return k.charAt(0).toUpperCase() + k.slice(1) + " · Speed " + (d.equip && d.equip.speed ? d.equip.speed : 4);
  }

  function syncCombat(s) {
    var p = pane("combat");
    if (!p.firstChild) buildCombat();
    syncPets(p, s);
    var v = Engine.view.combat(s);
    var sig = JSON.stringify([v.weapon, v.cmb, v.styles, v.afk.ret, v.afk.eat, Math.ceil(v.recall / 10)]);
    if (sigs["pane:combat"] === sig) return;
    sigs["pane:combat"] = sig;
    p.querySelector(".cb-i").innerHTML = v.weapon ? ico(v.weapon, 1) : "";
    text(p.querySelector(".cb-n"), v.weapon ? itemName(v.weapon) : "Unarmed");
    text(p.querySelector(".cb-c"), weaponKind(v.weapon));
    text(p.querySelector(".cb-lvl"), "Combat level " + v.cmb);
    var bs = p.querySelectorAll(".cb-st button");
    for (var i = 0; i < bs.length; i++) {
      var st = v.styles[i];
      if (!st) continue;
      toggle(bs[i], "on", st.on);
      text(bs[i].lastChild, (st.xp.length > 1 ? "Shared" : st.xp[0]) + " XP");
    }
    toggle(p.querySelector(".tgl"), "on", v.afk.ret);
    var es = p.querySelectorAll(".cb-eat button");
    for (var k = 0; k < es.length; k++) toggle(es[k], "on", +es[k].getAttribute("data-v") === v.afk.eat);
    var rc = p.querySelector(".cb-rc");
    text(rc, "Hearth recall · " + (v.recall > 0 ? Util.fmtDur(v.recall) : "Ready"));
    toggle(rc, "ready", v.recall <= 0);
  }

  // Pets: owned ones with level, XP bar, perk and Summon/Dismiss; the rest as locked rows naming their source.
  // Rows are rebuilt only when a pet is found, summoned or levels; XP bars patch in place (a press survives).
  function syncPets(p, s) {
    var v = Engine.view.pets(s);
    var sig = JSON.stringify(v);
    if (sigs["pane:pets"] === sig) return;
    sigs["pane:pets"] = sig;
    text(p.querySelector(".cb-ph span"), v.owned + " / " + v.list.length);
    var box = p.querySelector(".cb-pets");
    var shape = JSON.stringify(v.list.map(function (e) { return [e.id, e.owned, e.on, e.lvl, e.name]; }));
    if (box._shape !== shape) {
      box._shape = shape;
      box.innerHTML = v.list.map(function (e) {
        if (!e.owned) {
          return '<div class="pet lock"><i class="pet-q">?</i><div><b>Unknown pet</b><span>From ' + esc(e.from) +
            "</span></div></div>";
        }
        return '<div class="pet' + (e.on ? " on" : "") + '" data-act="petinfo" data-v="' + esc(e.id) + '"><canvas data-pet="' +
          esc(e.id) + '" data-stage="' + e.stage + '"></canvas><div><b>' + esc(e.name) + "</b><span>Lv " + e.lvl + " " +
          esc(e.stageName) + " · " + esc(e.perkName) +
          '</span><i class="pet-bar"><i></i></i></div><button data-act="pet" data-v="' + esc(e.id) + '">' +
          (e.on ? "Dismiss" : "Summon") + "</button></div>";
      }).join("");
      var cvs = box.querySelectorAll("canvas[data-pet]");
      for (var i = 0; i < cvs.length; i++) petIcon(cvs[i], cvs[i].getAttribute("data-pet"), +cvs[i].getAttribute("data-stage"));
    }
    v.list.forEach(function (e, k) {
      var row = box.children[k];
      if (!e.owned || !row) return;
      var lo = Rules.petXpFor(e.lvl);
      var pct = e.next === null ? 100 : Math.floor(100 * (e.xp - lo) / (e.next - lo));
      row.querySelector(".pet-bar i").style.width = pct + "%";
      row.setAttribute("data-tip", e.perkName + ": " + e.perkDesc + " · " + (e.next === null ? "Max level" :
        Util.fmtInt(e.xp) + " / " + Util.fmtInt(e.next) + " XP") + " · Click for its dex page");
    });
  }

  // The pet's side view, scaled by a whole step to fit 36x28 css px crisply.
  function petIcon(cv, id, stage) {
    var sp = Sprites.pet(id, 2, 0, stage);
    var d = Math.max(1, Math.ceil(window.devicePixelRatio || 1));
    var k = Math.max(1, Math.min(Math.floor(36 / sp.w), Math.floor(28 / sp.h)));
    cv.width = 36 * d;
    cv.height = 28 * d;
    cv.style.width = "36px";
    cv.style.height = "28px";
    var g = cv.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.drawImage(sp.cv, 0, 0, sp.w, sp.h, Math.floor((36 - sp.w * k) / 2) * d, Math.floor((28 - sp.h * k) / 2) * d,
      sp.w * k * d, sp.h * k * d);
  }

  // Built once per skill list, then patched in place: a box under the cursor is never replaced (a click
  // across an XP gain still lands). Each box shows its level; Vitality shows current/max.
  function syncSkills(s) {
    var p = pane("skills");
    var now = Date.now();
    var free = perkFree(s);
    var sig = JSON.stringify([s.player.xp10, s.player.hp, free, Object.keys(flashUntil).filter(function (k) { return flashUntil[k] > now; })]);
    if (sigs["pane:skills"] === sig) return;
    sigs["pane:skills"] = sig;
    var v = Engine.view.skills(s);
    var ids = v.list.map(function (k) { return k.id; }).join(",");
    var grid = p.firstChild;
    if (!grid || grid._ids !== ids) {
      p.innerHTML = '<div class="sk-grid">' + v.list.map(function (k) {
        return '<div class="sk' + (k.id === "hitpoints" ? " hp" : "") + '" data-act="guide" data-v="' + esc(k.id) + '">' + skillIco(k.id, 16) +
          '<span></span><div class="bar"><i style="background:' + skillColor(k.id) + '"></i></div></div>';
      }).join("") + '<div class="sk total"><span></span></div></div>';
      grid = p.firstChild;
      grid._ids = ids;
    }
    var boxes = grid.children;
    v.list.forEach(function (k, i) {
      var el = boxes[i];
      var hp = k.id === "hitpoints";
      var pts = free[k.id] > 0 ? free[k.id] : 0;
      var tip = k.name + ": XP " + Util.fmtInt(k.xp) + (k.next === null ? "" : " · Next level " + Util.fmtInt(k.next) +
        " · Remaining " + Util.fmtInt(Math.ceil(k.next - k.xp))) + (pts ? " · " + pointsText(pts) + " to spend" : "");
      text(el.querySelector("span"), hp ? s.player.hp + "/" + k.lvl : String(k.lvl));
      toggle(el, "lo", hp && s.player.hp < k.lvl);
      toggle(el, "pts", pts > 0);
      toggle(el, "flash", flashUntil[k.id] > now);
      var bar = el.querySelector(".bar i");
      if (bar.style.width !== k.pct + "%") bar.style.width = k.pct + "%";
      if (el.getAttribute("data-tip") !== tip) el.setAttribute("data-tip", tip);
    });
    var tot = boxes[v.list.length];
    var ts = tot.querySelector("span");
    if (ts._v !== v.total) { ts._v = v.total; ts.innerHTML = "Total<br>" + v.total; }
    tot.setAttribute("data-tip", "Total XP " + Util.fmtInt(v.totalXp));
  }

  function syncQuests(s) {
    var sig = JSON.stringify(s.player.quests);
    if (sigs["pane:quests"] === sig) return;
    var v = Engine.view.quests(s);
    var html = '<div class="qh">Quest points ' + v.qp + " · " + v.done + "/" + v.total + " complete</div>" +
      v.list.map(function (q) {
        return '<button class="qr qs-' + q.state + '" data-act="journal" data-v="' + q.id + '">' + esc(q.name) + "</button>";
      }).join("");
    setHtml(pane("quests"), "pane:quests", sig, html);
  }

  function syncInv(s) {
    var inv = s.player.inv;
    syncCells($("inv"), 28, "slot", "data-slot", function (i) {
      var e = inv[i];
      return e ? e.id + ":" + e.qty + (e.note ? ":n" : "") : "";
    }, function (i) {
      var e = inv[i];
      if (e && e.note) return '<span class="note">' + ico(e.id, 1) + "</span>" + qtyTag(e.id, e.qty);
      return e ? ico(e.id, e.qty) + qtyTag(e.id, e.qty) : "";
    }, function (i) {
      return inv[i] ? slotLabel(inv[i].id, inv[i].qty) + (inv[i].note ? " (noted)" : "") : "Empty slot";
    });
    var cells = $("inv").children;
    for (var i = 0; i < 28; i++) toggle(cells[i], "has", !!inv[i]);
  }

  // Empty slot glyph at 30%: Icons' slot silhouette, else the first item that fits the slot.
  function slotGlyph(slot) {
    if (typeof Icons.slotCss === "function") return '<i class="ico ghost" style="' + esc(Icons.slotCss(slot)) + '"></i>';
    var ids = Object.keys(Data.items || {});
    for (var i = 0; i < ids.length; i++) {
      var d = Data.items[ids[i]];
      if (d.equip && d.equip.slot === slot) return '<span class="ghost">' + ico(ids[i], 1) + "</span>";
    }
    return "";
  }

  function syncEquip(s) {
    var box = $("equip");
    if (box.children.length !== EQ_SLOTS.length) {
      box.innerHTML = EQ_SLOTS.map(function (k) {
        return '<div class="eq" role="button" data-eq="' + k + '" style="grid-area:' + k + '"></div>';
      }).join("");
    }
    var v = Engine.view.equipment(s);
    for (var i = 0; i < EQ_SLOTS.length; i++) {
      var k = EQ_SLOTS[i];
      var id = v.slots[k];
      var cell = box.children[i];
      var sig = id || "";
      if (cell._sig === sig) continue;
      cell._sig = sig;
      cell.innerHTML = id ? ico(id, 1) : slotGlyph(k);
      cell.setAttribute("data-tip", id ? itemName(id) : EQ_NAMES[k]);
      cell.setAttribute("aria-label", id ? EQ_NAMES[k] + ": " + itemName(id) : EQ_NAMES[k] + ": Empty slot");
      toggle(cell, "has", !!id);
    }
    var sign = function (n) { return (n >= 0 ? "+" : "") + n; };
    var eqs = "Att " + sign(v.att) + " · Str " + sign(v.str) + " · Def " + sign(v.def) + "<br>Max hit " + v.maxHit;
    if ($("eqstats").innerHTML !== eqs) $("eqstats").innerHTML = eqs;
  }

  // Options: built once from OPTIONS, then patched.
  function buildOptions() {
    pane("options").innerHTML = OPTIONS.map(function (o) {
      if (!o.seg) return '<div class="opt"><button class="tgl" data-act="opt" data-k="' + o.k + '">' + esc(o.label) + '<i class="sw"></i></button></div>';
      return '<div class="opt"><span class="lbl">' + esc(o.label) + '</span><div class="seg">' + o.seg.map(function (e) {
        return '<button data-act="opt" data-k="' + o.k + '" data-v="' + e[0] + '">' + esc(e[1]) + "</button>";
      }).join("") + "</div>" + (o.note ? '<p class="opt-note">' + esc(o.note) + "</p>" : "") + "</div>";
    }).join("") + '<div class="opt"><span class="lbl">Zoom</span><button class="btn" data-act="zoom">Reset zoom</button></div>' +
      '<div class="opt"><button class="btn quiet" data-act="delete">Delete character…</button></div>';
  }

  // Current value of an option key, as the string its buttons carry.
  function optValue(k, afk) {
    if (k === "dock") return dock === "window" ? "window" : "right";
    if (k.indexOf("afk.") === 0) return afk[k.slice(4)] ? "1" : "0";
    if (k.indexOf("full.") === 0) return afk.full[k.slice(5)];
    return String(prefs[k]);
  }

  function syncOptions(s) {
    var p = pane("options");
    if (!p.firstChild) buildOptions();
    var v = Engine.view.combat(s);
    var sig = JSON.stringify([prefs, dock, v.afk, v.courier]);
    if (sigs["pane:options"] === sig) return;
    sigs["pane:options"] = sig;
    var bs = p.querySelectorAll("[data-k]");
    for (var i = 0; i < bs.length; i++) {
      var b = bs[i];
      var k = b.getAttribute("data-k");
      var cur = optValue(k, v.afk);
      if (b.classList.contains("tgl")) toggle(b, "on", cur === "1");
      else toggle(b, "on", b.getAttribute("data-v") === cur);
      if (k.indexOf("full.") === 0 && b.getAttribute("data-v") === "courier") {
        toggle(b, "lock", !v.courier);
        if (v.courier) b.removeAttribute("data-tip");
        else b.setAttribute("data-tip", TIP_COURIER);
      }
    }
  }

  function setOption(k, v) {
    if (k === "dock") {
      setDock(v);
      ctx.postDock(dock);
      return;
    }
    if (k.indexOf("afk.") === 0) {
      var a = {};
      a[k.slice(4)] = !Engine.view.combat(state()).afk[k.slice(4)];
      act(function (s) { return Engine.setAfk(s, a); });
      return;
    }
    if (k.indexOf("full.") === 0) {
      if (v === "courier" && !Engine.view.combat(state()).courier) { banner(TIP_COURIER, "info"); return; }
      var f = {};
      f[k.slice(5)] = v;
      act(function (s) { return Engine.setAfk(s, { full: f }); });
      return;
    }
    var n = v === null ? (prefs[k] ? 0 : 1) : parseInt(v, 10);
    var patch = getPrefs();
    patch[k] = n;
    setPrefs(patch);
    ctx.persist();
  }

  function setDock(d) {
    dock = d === "window" ? "window" : "right";
    sigs["pane:options"] = null;
  }

  // ----------------------------------------------------------------
  // --------------------------- Windows ----------------------------
  // ----------------------------------------------------------------

  function winKind(s) {
    var f = s.player.iface;
    if (f && (f.t === "bank" || f.t === "shop")) return f.t;
    return uiWin ? uiWin.kind : "";
  }

  // Fills the window. The header (and its close button) and the body element are built once per open window
  // and kept across rebuilds, so a press on X survives a content change and the body keeps its scroll.
  function frame(title, sub, body, foot, parch) {
    var w = $("win");
    toggle(w, "parch", !!parch);
    var wb = w.querySelector(".wb");
    if (!wb) {
      w.innerHTML = '<div class="wh"><span class="wt"></span><span class="ws"></span><button class="wx" data-act="close" data-tip="Close" aria-label="Close">' +
        X_SVG + '</button></div><div class="wb"></div><div class="wf"></div>';
      wb = w.querySelector(".wb");
    }
    var ws = w.querySelector(".ws");
    var wf = w.querySelector(".wf");
    text(w.querySelector(".wt"), title);
    ws._sig = null;
    ws.innerHTML = sub || "";
    wb.innerHTML = body;
    wf.innerHTML = foot || "";
    wf.hidden = !foot;
    if (winFresh) wb.scrollTop = 0;
    winFresh = false;
  }

  function syncWindow(s, now, st) {
    var f = s.player.iface;
    if (uiWin && f && (f.t === "bank" || f.t === "shop")) uiWin = null;
    var k = winKind(s);
    var w = $("win");
    if (!k) {
      if (!w.hidden) { w.hidden = true; w.innerHTML = ""; w.setAttribute("data-kind", ""); sigs.win = null; winFresh = true; }
      return;
    }
    if (w.getAttribute("data-kind") !== k) { w.setAttribute("data-kind", k); sigs.win = null; winFresh = true; }
    w.hidden = false;
    if (k === "bank") syncBank(s);
    else if (k === "shop") syncShop(s, now);
    else {
      var sig = uiSig(s, k, st);
      if (sigs.win !== sig) {
        sigs.win = sig;
        if (k === "journal") buildJournal(s);
        else if (k === "guide") buildGuide(s);
        else if (k === "away") buildAway(s);
        else if (k === "map") buildMap();
        else if (k === "pet") buildPet(s);
        else buildQuestDone(s);
      }
      if (k === "map") {
        var wb = w.querySelector(".wb");
        Render.worldMap(wb.querySelector("canvas"), wb.clientWidth - 20, wb.clientHeight - 14, uiWin);
      }
      var xp = uiWin && k === "guide" && Util.has(s.player.xp10, uiWin.skill) ? s.player.xp10[uiWin.skill] : 0;
      if (uiWin && k === "guide" && uiWin.xp !== xp) {
        uiWin.xp = xp;
        text($("win").querySelector(".ws"), guideSub(Engine.view.guide(s, uiWin.skill)));
      }
      if (uiWin && k === "guide") syncPerks(s);
    }
  }

  // The world map window: the canvas plus zoom buttons; wheel zooms at the pointer and a drag pans (zoomed in).
  function buildMap() {
    frame("World map", "", "<canvas></canvas>",
      '<button class="gb" data-act="mapz" data-v="-1" aria-label="Zoom out" data-tip="Zoom out">\u2212</button>' +
      '<button class="gb" data-act="mapz" data-v="1" aria-label="Zoom in" data-tip="Zoom in">+</button>' +
      '<button class="gb" data-act="mapc">Centre on me</button><span class="sp"></span>' +
      '<span class="lb">Wheel to zoom, drag to look around</span>', true);
    var cv = $("win").querySelector(".wb canvas"), drag = null;
    function tileAt(ev) {
      var v = cv._view, r = cv.getBoundingClientRect();
      if (!v || !r.width) return null;
      return { x: ((ev.clientX - r.left) * v.dpr + v.ox) / v.tp, y: ((ev.clientY - r.top) * v.dpr + v.oy) / v.tp };
    }
    cv.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      mapZoom(ev.deltaY < 0 ? 1 : -1, ev.deltaY < 0 ? tileAt(ev) : null);
    }, { passive: false });
    cv.addEventListener("pointerdown", function (ev) {
      var v = cv._view;
      if (!v || v.z <= 1 || !uiWin || uiWin.kind !== "map") return;
      drag = { id: ev.pointerId, x: ev.clientX, y: ev.clientY, cx: (v.ox + cv.width / 2) / v.tp, cy: (v.oy + cv.height / 2) / v.tp };
      try { cv.setPointerCapture(ev.pointerId); } catch (e) { /* capture is optional */ }
    });
    cv.addEventListener("pointermove", function (ev) {
      if (!drag || ev.pointerId !== drag.id || !uiWin || uiWin.kind !== "map") return;
      var v = cv._view, k = v.dpr / v.tp, hw = cv.width / 2 / v.tp, hh = cv.height / 2 / v.tp;
      uiWin.cx = Math.max(hw, Math.min(v.w - hw, drag.cx - (ev.clientX - drag.x) * k));
      uiWin.cy = Math.max(hh, Math.min(v.h - hh, drag.cy - (ev.clientY - drag.y) * k));
    });
    function end() { drag = null; }
    cv.addEventListener("pointerup", end);
    cv.addEventListener("pointercancel", end);
  }

  // Zoom 1 (whole map) .. 4. Zooming in from the whole map centres on `at` (the tile under the wheel) or on you.
  function mapZoom(d, at) {
    if (!uiWin || uiWin.kind !== "map") return;
    var z0 = uiWin.z || 1, z = Math.max(1, Math.min(4, z0 + d));
    if (z === z0) return;
    if (at) { uiWin.cx = at.x; uiWin.cy = at.y; } else if (z0 === 1) { uiWin.cx = null; uiWin.cy = null; }
    uiWin.z = z;
  }

  // The pet dex: portrait, forms (later ones unnamed until reached), level, stats, records and dex facts (one per
  // stage reached). Rebuilt on a hit, a level, summon/dismiss or a minute together.
  function buildPet(s) {
    var v = Engine.view.pet(s, uiWin.id);
    if (!v) { uiWin = null; return; }
    var row = function (k, val) { return "<dt>" + esc(k) + "</dt><dd>" + esc(val) + "</dd>"; };
    var forms = v.forms.map(function (f) {
      return '<i class="' + (f.stage === v.stage ? "on" : f.reached ? "" : "lock") + '">' + esc(f.stageName) + " · " +
        esc(f.reached ? f.name : "? at Lv " + f.lvl) + "</i>";
    }).join("");
    var pct = v.next === null ? 100 : Math.floor(100 * (v.xp - v.prev) / (v.next - v.prev));
    var r = v.rec, x = v.dex;
    var body = '<div class="pd"><div class="pd-top"><canvas class="pd-pic"></canvas><div class="pd-id"><b>' + esc(v.name) +
      "</b><span>" + esc(x.kind) + " · " + esc(v.stageName) + '</span><div class="pd-forms">' + forms + "</div></div></div>" +
      '<div class="pd-xp"><b>Level ' + v.lvl + '</b><i class="pd-bar"><i style="width:' + pct + '%"></i></i><span>' +
      (v.next === null ? "Max level" : Util.fmtInt(v.xp) + " / " + Util.fmtInt(v.next) + " XP") + "</span></div>" +
      '<h4>Stats</h4><dl class="pd-dl">' + row("Attack", String(v.att)) + row("Max hit", String(v.maxHit)) +
      row("Attacks", "every " + (v.speed * Rules.TICK_MS / 1000).toFixed(1) + " s") + row("Perk", v.perkName) + "</dl>" +
      '<p class="pd-note">' + esc(v.perkDesc) + " Fights only; it never helps with skilling.</p>" +
      '<h4>Records</h4><dl class="pd-dl">' + row("Damage dealt", Util.fmtInt(r.dmg)) + row("Foes defeated", Util.fmtInt(r.kills)) +
      row("Biggest hit", String(r.best)) + row("Time together", Util.fmtDur(r.out)) +
      row("Found", r.kc > 0 ? v.from + " kill #" + Util.fmtInt(r.kc) : "Before records began") + "</dl>" +
      '<h4>Pet dex</h4><dl class="pd-dl">' + row("Kind", x.kind) + row("Habitat", x.habitat) + row("Size", x.size) +
      row("Weight", x.weight) + row("Likes", x.likes) + '</dl><ol class="pd-facts">' + x.facts.map(function (f) {
        return f.open ? "<li>" + esc(f.text) + "</li>" : '<li class="lock">Learn more when it grows (level ' + f.lvl + ").</li>";
      }).join("") + "</ol></div>";
    var foot = '<button class="gb" data-act="pet" data-v="' + esc(v.id) + '">' + (v.on ? "Dismiss" : "Summon") + "</button>" +
      '<span class="sp"></span><span class="lb">' + esc(v.examine) + "</span>";
    frame("Pet dex", esc("Lv " + v.lvl + " · " + v.stageName), body, foot, true);
    var cv = $("win").querySelector(".pd-pic"), sp = Sprites.pet(v.id, 2, 0, v.stage);
    var d = Math.max(1, Math.ceil(window.devicePixelRatio || 1));
    var k = Math.max(1, Math.min(Math.floor(92 / sp.w), Math.floor(76 / sp.h)));
    cv.width = 96 * d;
    cv.height = 80 * d;
    var g = cv.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.drawImage(sp.cv, 0, 0, sp.w, sp.h, Math.floor((96 - sp.w * k) / 2) * d, Math.floor((80 - sp.h * k) / 2 + 4) * d,
      sp.w * k * d, sp.h * k * d);
  }

  // UI-only windows rebuild when what they show changes: a quest stage or kill count, a level (journal
  // requirements), the skill's level (the guide; its XP subtitle is patched in syncWindow).
  function uiSig(s, k, st) {
    if (k === "journal") return k + ":" + uiWin.id + ":" + st.total + ":" + JSON.stringify([s.player.quests, s.player.qc]);
    if (k === "guide") return k + ":" + uiWin.skill + ":" + (Util.has(s.player.xp10, uiWin.skill) ? Rules.levelForXp(s.player.xp10[uiWin.skill] / 10) : 1);
    if (k === "map") return k + ":" + s.player.map;
    if (k === "pet") {
      var pv = Engine.view.pet(s, uiWin.id);
      return pv ? k + ":" + JSON.stringify([pv.id, pv.xp, pv.on, pv.rec.dmg, pv.rec.kills, pv.rec.best, Math.floor(pv.rec.out / 100)]) : k;
    }
    return k;
  }

  // Marks the chosen Qty button in box; X shows a typed count while it is the choice.
  function patchQty(box, act0, cur, list, x) {
    if (!box) return;
    var custom = cur > 0 && list.indexOf(cur) < 0;
    var bs = box.querySelectorAll('[data-act="' + act0 + '"]');
    for (var i = 0; i < bs.length; i++) toggle(bs[i], "on", +bs[i].getAttribute("data-v") === cur);
    var xb = x ? box.querySelector('[data-act="' + x + '"]') : null;
    if (xb) {
      toggle(xb, "on", custom);
      text(xb, custom ? Util.fmtQty(cur) : "X");
    }
  }

  // Qty [1][5][10][X][All]: X sits before All and shows a typed count while it is the choice.
  function qtyButtons(act0, cur, list, x) {
    var custom = cur > 0 && list.indexOf(cur) < 0;
    var xb = x ? '<button class="gb' + (custom ? " on" : "") + '" data-act="' + x + '">' + (custom ? Util.fmtQty(cur) : "X") + "</button>" : "";
    return '<span class="lb">Qty</span>' + list.map(function (n) {
      return (n === -1 ? xb : "") + '<button class="gb' + (n === cur ? " on" : "") + '" data-act="' + act0 + '" data-v="' + n + '">' + qtyLabel(n) + "</button>";
    }).join("") + (list.indexOf(-1) < 0 ? xb : "");
  }

  function syncBank(s) {
    var v = Engine.view.bank(s);
    var winW = sz.view.w - 8;
    var head = L + ":" + sz.view.w;
    if (sigs.win !== "bank:" + head) {
      sigs.win = "bank:" + head;
      frame("Bank of Brackenford", "", '<p class="mt empty">Nothing here yet. Click items in your pack to deposit them.</p><div class="grid"></div>', qtyButtons("bankqty", prefs.bankQty, [1, 5, 10, -1], "bankx") +
        '<span class="as"><span class="lb">As</span><button class="gb" data-act="banknote" data-v="0" data-tip="Withdraw items">Item</button>' +
        '<button class="gb" data-act="banknote" data-v="1" data-tip="Withdraw a stack of notes in one slot; swap them back at the bank">Note</button></span>' +
        '<span class="dep"><button class="gb" data-act="deppack">Deposit pack</button><button class="gb" data-act="depworn">Deposit worn</button></span>');
      var g = $("win").querySelector(".grid");
      g.style.setProperty("--bc", String(Math.max(6, Math.min(10, Math.floor((winW - 16) / (44 * uiScale()))))));
    }
    patchQty($("win").querySelector(".wf"), "bankqty", prefs.bankQty, [1, 5, 10, -1], "bankx");
    var nb = $("win").querySelectorAll('[data-act="banknote"]');
    for (var i = 0; i < nb.length; i++) toggle(nb[i], "on", (nb[i].getAttribute("data-v") === "1") === v.note);
    $("win").querySelector(".empty").hidden = v.rows.length > 0;
    text($("win").querySelector(".ws"), Util.fmtInt(v.used) + (v.used === 1 ? " item" : " items"));
    syncCells($("win").querySelector(".grid"), v.rows.length, "cell", "data-bank", function (i) {
      return v.rows[i].id + ":" + v.rows[i].qty;
    }, function (i) {
      return ico(v.rows[i].id, v.rows[i].qty) + '<b class="q q-' + Util.qtyClass(v.rows[i].qty) + '">' + Util.fmtQty(v.rows[i].qty) + "</b>";
    }, function (i) {
      return slotLabel(v.rows[i].id, v.rows[i].qty);
    });
  }

  function syncShop(s, now) {
    var v = Engine.view.shop(s);
    if (!v) return;
    if (sigs.win !== "shop:" + v.id) {
      sigs.win = "shop:" + v.id;
      frame(v.name, "", '<div class="shop"></div>', qtyButtons("shopqty", prefs.shopQty, [1, 5, 10, 50], null));
    }
    patchQty($("win").querySelector(".wf"), "shopqty", prefs.shopQty, [1, 5, 10, 50], null);
    var coins = '<span class="i16">' + ico("coins", v.coins) + "</span> " + Util.fmtInt(v.coins);
    var ws = $("win").querySelector(".ws");
    if (ws._sig !== coins) { ws._sig = coins; ws.innerHTML = coins; }
    var flashing = flashPrice.until > now ? flashPrice.i : -1;
    syncCells($("win").querySelector(".shop"), v.rows.length, "sc", "data-shop", function (i) {
      var r = v.rows[i];
      return [r.id, r.stock, r.price, prefs.shopQty, flashing === i ? 1 : 0].join(":");
    }, function (i) {
      var r = v.rows[i];
      return ico(r.id, 1) + '<b class="q q-' + Util.qtyClass(r.stock) + '">' + Util.fmtQty(r.stock) + '</b><span class="pr' +
        (flashing === i ? " no" : "") + '">' + Util.fmtQty(r.price) + "</span>";
    }, function (i) {
      var r = v.rows[i];
      return itemName(r.id) + ", " + (r.stock > 0 ? Util.fmtInt(r.stock) + " in stock" : "sold out") + ", " + Util.fmtInt(r.price) + " coins";
    });
    var cells = $("win").querySelector(".shop").children;
    for (var i = 0; i < cells.length && i < v.rows.length; i++) {
      var r = v.rows[i];
      toggle(cells[i], "out", r.stock <= 0);
      var n = Math.min(prefs.shopQty, r.stock);
      var hv = r.stock <= 0 ? itemName(r.id) + ": sold out" : "Buy " + n + " " + itemName(r.id) + " (" + Util.fmtInt(r.price * n) + " coins)";
      if (cells[i].getAttribute("data-hover") !== hv) cells[i].setAttribute("data-hover", hv);
    }
  }

  function shopFlash(i) {
    flashPrice = { i: i, until: Date.now() + 300 };
  }

  // NPC names in the current journal step.
  function markNames(t) {
    var out = esc(t);
    Object.keys(Data.npcs || {}).forEach(function (id) {
      var n = Data.npcs[id].name;
      if (typeof n === "string" && n.length >= 3 && out.indexOf(n) >= 0) out = out.split(esc(n)).join('<span class="nm">' + esc(n) + "</span>");
    });
    return out;
  }

  function rewardRows(q) {
    var r = q.rewards || {};
    var rows = (r.items || []).map(function (e) {
      return '<div class="rw">' + ico(e[0], e[1]) + "<span>" + (e[1] > 1 ? Util.fmtInt(e[1]) + " × " : "") + esc(itemName(e[0])) + "</span></div>";
    }).concat((r.xp || []).map(function (e) {
      return '<div class="rw">' + skillIco(e[0], 32) + "<span>" + Util.fmtInt(e[1]) + " " + esc(skillName(e[0])) + " XP</span></div>";
    })).concat((r.lines || []).map(function (t) { return '<div class="rw"><span>' + esc(t) + "</span></div>"; }));
    return rows.join("");
  }

  function buildJournal(s) {
    var id = uiWin.id;
    var q = Util.has(Data.quests, id) ? Data.quests[id] : null;
    if (!q) { uiWin = null; return; }
    var v = Engine.view.quests(s).list.filter(function (e) { return e.id === id; })[0];
    var steps = v ? v.lines : [];
    var cur = -1;
    for (var i = 0; i < steps.length; i++) if (!steps[i].done) cur = i;
    var body = steps.map(function (st, i) {
      return '<p class="ln2' + (st.done ? " strike" : "") + '">' + (i === cur ? markNames(st.text) : esc(st.text)) + "</p>";
    }).join("");
    if (v && v.state === "todo") {
      var met = v.reqs || [];
      var reqs = (q.reqText || []).map(function (t, i) {
        var c = (q.reqs || [])[i];
        var lvl = c && typeof c.lvl === "string" && typeof c.gte === "number" && met[i] === false ?
          Rules.levelForXp((Util.has(s.player.xp10, c.lvl) ? s.player.xp10[c.lvl] : 0) / 10) : 0;
        return '<p class="ln2' + (met[i] ? " strike" : "") + '">' + esc(t) + (lvl ? " (you: " + lvl + ")" : "") + "</p>";
      }).join("");
      if (reqs) body += '<div class="sec">Requirements</div>' + reqs;
      if (q.recCmb) body += '<p class="ln2">Recommended combat level ' + q.recCmb + "</p>";
    }
    if (v && v.state === "done") body += '<div class="sec">Rewards</div>' + rewardRows(q);
    frame(q.name, "", body, "", true);
  }

  function guideSub(g) {
    if (!g) return "";
    return g.next === null ? Util.fmtInt(g.xp) + " XP" : g.pct + "% to " + (g.lvl + 1) + " · " + Util.fmtInt(Math.ceil(g.next - g.xp)) + " XP left";
  }

  // The perks block sits on top. Opens at the top while the skill has a point to spend, else scrolled to the
  // first locked row; a level-up rebuild keeps the reader's scroll.
  function buildGuide(s) {
    var fresh = winFresh;
    var g = Engine.view.guide(s, uiWin.skill);
    if (!g) { uiWin = null; return; }
    var name = skillName(g.id);
    var sub = guideSub(g);
    var pv = perksOn() ? Engine.view.perks(s, g.id) : null;
    var first = -1;
    var rows = g.rows.map(function (r, i) {
      if (!r.ok && first < 0) first = i;
      return '<div class="gr' + (r.ok ? "" : " lock") + '"><span class="lv">' + r.lvl + "</span>" + (r.icon ? ico(r.icon, 1) : '<i class="ico"></i>') +
        "<div><span>" + esc(r.name) + '</span><span class="nt">' + esc(r.note) + "</span></div></div>";
    }).join("");
    var list = rows || '<p class="mt">Every level of ' + esc(name) + " makes you tougher in a fight.</p>";
    frame(name + " " + g.lvl, esc(sub), pv && pv.perks && pv.perks.length ? perksHtml(pv) + '<div class="sec">Unlocks</div>' + list : list, "");
    syncPerks(s);
    if (first > 0 && fresh && !(pv && pv.free > 0)) {
      var wb = $("win").querySelector(".wb");
      var row = wb.querySelectorAll(".gr")[first];
      wb.scrollTop = Math.max(0, row.getBoundingClientRect().top - wb.getBoundingClientRect().top - 40);
    }
  }

  // ----------------------------------------------------------------
  // ------------------------- Guide: perks -------------------------
  // ----------------------------------------------------------------
  // Built with the guide, then patched in place each frame (text, pips, disabled), so a press on + or Reset
  // is never replaced under the mouse and the body keeps its scroll.
  function perksHtml(v) {
    return '<div class="perks"><div class="pkh"><b>Perks</b><span class="pkf"></span>' +
      '<button class="pkr" data-act="perkask" data-v="' + esc(v.skill) + '"></button></div>' + v.perks.map(function (k) {
      var pips = "";
      for (var i = 0; i < k.max; i++) pips += "<i></i>";
      return '<div class="pk" data-perk="' + esc(k.id) + '"><div class="pkt"><b>' + esc(k.name) + "</b><span>" + esc(k.desc) +
        '</span></div><span class="pips" role="img">' + pips + '</span><button class="pkb" data-act="perkup" data-v="' + esc(k.id) +
        '" aria-label="Raise ' + esc(k.name) + '">+</button></div>';
    }).join("") + "</div>";
  }

  function syncPerks(s) {
    var box = $("win").querySelector(".perks");
    if (!box || !uiWin || !perksOn()) return;
    var v = Engine.view.perks(s, uiWin.skill);
    if (!v) return;
    var coins = packCoins(s);
    var sig = JSON.stringify([v, coins >= v.resetCost]);
    if (box._sig === sig) return;
    box._sig = sig;
    text(box.querySelector(".pkf"), perkLine(v));
    toggle(box, "has", v.free > 0);
    var r = box.querySelector(".pkr");
    text(r, v.spent > 0 ? "Reset (" + Util.fmtInt(v.resetCost) + " coins)" : "Reset");
    setDisabled(r, !(v.spent > 0));
    toggle(r, "no", v.spent > 0 && coins < v.resetCost);
    setAttr(r, "data-tip", v.spent > 0 ? "Refund " + pointsText(v.spent) + " for " + Util.fmtInt(v.resetCost) + " coins" : "No points spent yet");
    v.perks.forEach(function (k) {
      var row = box.querySelector('[data-perk="' + k.id + '"]');
      if (!row) return;
      var pips = row.querySelector(".pips");
      for (var i = 0; i < pips.children.length; i++) toggle(pips.children[i], "on", i < k.rank);
      setAttr(pips, "aria-label", "Rank " + k.rank + " of " + k.max);
      setAttr(pips, "data-tip", "Rank " + k.rank + " of " + k.max);
      toggle(row, "maxed", k.rank >= k.max);
      var b = row.querySelector(".pkb");
      setDisabled(b, v.free <= 0 || k.rank >= k.max);
      setAttr(b, "data-tip", k.rank >= k.max ? "Fully ranked" : v.free > 0 ? "Spend a point: rank " + (k.rank + 1) + " of " + k.max : perkLine(v));
    });
  }

  // Reset asks first (the chrome modal): every rank in the skill comes back for coins from the pack.
  function openPerkReset(skill) {
    var v = perksOn() ? Engine.view.perks(state(), skill) : null;
    if (!v || !(v.spent > 0)) return;
    var cost = Util.fmtInt(v.resetCost);
    $("modal").innerHTML = '<div class="md"><b>Reset ' + esc(skillName(skill)) + " perks?</b><p>" +
      (v.spent === 1 ? "Your perk point comes" : "All " + v.spent + " perk points come") + " back to spend again. It costs " + cost +
      ' coins from your pack.</p><div class="mdb"><button data-act="mdno">Cancel</button><button class="ok" data-act="pkyes" data-v="' +
      esc(skill) + '">Reset (' + cost + " coins)</button></div></div>";
    $("modal").hidden = false;
  }

  function perkReset(skill) {
    closeModal();
    var v = perksOn() ? Engine.view.perks(state(), skill) : null;
    if (!v) return;
    if (!act(function (s) { return Engine.perkReset(s, skill); }) && packCoins(state()) < v.resetCost) {
      banner("You need " + Util.fmtInt(v.resetCost) + " coins to reset these perks.", "warn");
    }
  }

  function grid(items) {
    return '<div class="ig">' + items.map(function (e) {
      return '<div class="cell" data-tip="' + esc(itemName(e[0])) + '">' + ico(e[0], e[1]) + '<b class="q q-' + Util.qtyClass(e[1]) + '">' + Util.fmtQty(e[1]) + "</b></div>";
    }).join("") + "</div>";
  }

  // The region (else map) name of a grave view.
  function graveWhere(g) {
    var rs = Array.isArray(Data.regions) ? Data.regions : [];
    for (var i = 0; i < rs.length; i++) {
      if (rs[i].map === g.map && Util.inRect(rs[i].rect, g.x, g.y)) return rs[i].name;
    }
    return Util.has(Data.maps, g.map) ? Data.maps[g.map].name : "";
  }

  function graveLine(s) {
    var g = Engine.view.grave(s);
    if (!g) return "";
    return '<p class="ln2">Your gravestone waits in ' + esc(graveWhere(g)) + " (" + Util.fmtDur(g.ticksLeft) + " left).</p>";
  }

  // A save's local wall time: "today 09:30", "yesterday 21:05" or "Tue, Oct 14 09:30".
  function whenText(ms) {
    var d = new Date(ms), now = new Date();
    var at = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (ms >= new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) return "today " + at;
    if (ms >= new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).getTime()) return "yesterday " + at;
    return d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) + " " + at;
  }

  function buildAway(s) {
    var m = uiWin.sum;
    var stopped = m.stop ? " — stopped: " + esc(m.stop) + (m.stopAt > 0 ? " (after " + esc(Util.fmtDur(m.stopAt)) + ")" : "") : "";
    var body = '<p class="ln2">' + esc(m.doing) + stopped + "</p>";
    var xs = Object.keys(m.xp).filter(function (k) { return m.xp[k] > 0; });
    body += xs.map(function (k) {
      var pts = Util.has(m.levels, k) && perksOn() ? Math.floor(m.levels[k][1] / 5) - Math.floor(m.levels[k][0] / 5) : 0;
      var lv = Util.has(m.levels, k) ? '<span class="mt">' + m.levels[k][0] + " → " + m.levels[k][1] + "</span>" +
        (pts > 0 ? '<span class="pkn">+' + pointsText(pts) + "</span>" : "") : "";
      return '<div class="rw">' + skillIco(k, 16) + "<span>" + esc(skillName(k)) + " +" + Util.fmtInt(m.xp[k]) + " XP</span>" + lv + "</div>";
    }).join("");
    var gained = [];
    var used = [];
    Object.keys(m.items).forEach(function (id) {
      if (!itemDef(id)) return;
      if (m.items[id] > 0) gained.push([id, m.items[id]]);
      else if (!Util.has(m.dropped || {}, id)) used.push([id, -m.items[id]]);   // dropped yields are counted there
    });
    var cour = Object.keys(m.couriered).filter(itemDef).map(function (id) { return [id, m.couriered[id]]; });
    var drop = Object.keys(m.dropped || {}).filter(itemDef).map(function (id) { return [id, m.dropped[id]]; });
    if (gained.length) body += '<div class="sec">Gained</div>' + grid(gained);
    if (cour.length) body += '<div class="sec">Couriered</div>' + grid(cour);
    if (drop.length) body += '<div class="sec">Dropped (pack full)</div>' + grid(drop);
    if (used.length) body += '<div class="sec">Used</div>' + grid(used);
    var kills = Object.keys(m.kills).filter(function (id) { return Util.has(Data.npcs, id); }).map(function (id) {
      return esc(Data.npcs[id].name) + " ×" + Util.fmtInt(m.kills[id]);
    });
    if (kills.length) body += '<div class="sec">Kills</div><p class="ln2">' + kills.join(" · ") + "</p>";
    if (m.recalls > 0) body += '<p class="ln2">Recalled ' + m.recalls + (m.recalls === 1 ? " time" : " times") + "</p>";
    if (m.notes && m.notes.length) {
      body += '<div class="sec">Quests</div>' + m.notes.map(function (t) { return '<p class="ln2">' + esc(t) + "</p>"; }).join("");
    }
    if (m.paused) body += '<p class="ln2">' + esc(m.paused) + "</p>";
    if (m.rested > 0) {
      body += '<div class="sec">Rested</div><p class="ln2">The time past the catch-up limit rested you: +' + esc(etaText(m.rested, true)) +
        " of double XP from gathering, making and fighting.</p>";
    }
    body += graveLine(s);
    // After a load, when the save was written: a second OrcaSlicer window restores an older one.
    var cap = m.capped ? (uiWin.cap >= 24000 ? "counted up to 4 h" : "counted up to 1 h") : "";
    if (m.savedAt > 0) body += '<p class="ln2 mt">Last saved ' + esc(whenText(m.savedAt)) + (cap ? " · " + cap : "") + "</p>";
    else if (cap) body += '<p class="ln2 mt">(' + cap + ")</p>";
    frame("While you were away", esc(Util.fmtDur(m.ticks)), body, '<span class="sp"></span><button class="gb" data-act="close">Continue</button>');
  }

  function buildQuestDone(s) {
    var q = Util.has(Data.quests, uiWin.id) ? Data.quests[uiWin.id] : null;
    if (!q) { uiWin = null; return; }
    var body = '<p class="ctr" style="font-weight:bold;font-size:14px">' + esc(q.name) + "</p>" + rewardRows(q) +
      '<p class="ln2">Quest points: ' + Engine.view.quests(s).qp + "</p>";
    frame("Quest complete!", "", body, '<span class="sp"></span><button class="gb" data-act="close">Continue</button>');
  }

  function openWin(w) {
    uiWin = w;
    sigs.win = null;
    winFresh = true;
  }

  // The quest-complete window waits until the closing line of the dialogue (or a store it opened) is gone.
  function questDone(s) {
    var f = s.player.iface;
    if (!doneQ.length || (f && (f.t === "dialogue" || f.t === "bank" || f.t === "shop"))) return;
    openWin({ kind: "questdone", id: doneQ.shift() });
  }

  // ----------------------------------------------------------------
  // ---------------------------- Sheets ----------------------------
  // ----------------------------------------------------------------

  function syncSheet(s) {
    var f = s.player.iface;
    var sh = $("sheet");
    var kind = prompt ? "amount" : f && (f.t === "dialogue" || f.t === "make") ? f.t : "";
    var sig = "";
    if (kind === "dialogue") sig = JSON.stringify(Engine.view.dialogue(s));
    else if (kind === "make") sig = JSON.stringify([Engine.view.make(s), L, sz.view.w]);
    else if (kind === "amount") sig = "amount";
    if (kind === "make") patchQty(sh.querySelector(".row"), "makeqty", prefs.makeQty, [1, 5, 10, -1], "makex");
    if (sigs.sheet === kind + sig) return;
    sigs.sheet = kind + sig;
    sh.setAttribute("data-kind", kind);
    toggle($("app"), "sheet-open", !!kind);
    if (kind && L === "C" && paneOpen && prevTab === null) {
      paneOpen = false;
      syncPaneOpen();
    }
    if (!kind) {
      sh.hidden = true;
      sh.innerHTML = "";
    } else {
      sh.hidden = false;
      if (kind === "dialogue") buildDialogue(s);
      else if (kind === "make") buildMake(s);
      else buildAmount();
    }
    var h = kind ? sh.offsetHeight : 0;
    if (h !== sheetH) {
      sheetH = h;
      cssVar("--sheet-h", h + "px");
      winBottom();
    }
  }

  function buildDialogue(s) {
    var v = Engine.view.dialogue(s);
    var sh = $("sheet");
    if (!v) { sh.innerHTML = ""; return; }
    var body = (v.name ? '<div class="dn">' + esc(v.name) + "</div>" : "") + '<div class="dt">' + esc(v.text) + "</div>";
    if (v.opts) {
      body += v.opts.map(function (o, i) { return '<button class="dop" data-act="dlgopt" data-v="' + i + '">' + esc(o) + "</button>"; }).join("");
    } else {
      body += '<div class="dc">Click or Space to continue</div>';
    }
    sh.innerHTML = '<div class="dlg"' + (v.opts ? "" : ' data-act="dlgnext"') + '>' + (v.who === "none" ? "" : '<div class="pf"></div>') +
      '<div class="dl">' + body + "</div></div>";
    if (v.who !== "none") {
      var cv = Render.portrait(v.who === "player" ? null : v.npc);
      if (cv) sh.querySelector(".pf").appendChild(cv);
    }
  }

  function levelLocked(s, r) {
    var xp = Util.has(s.player.xp10, r.skill) ? s.player.xp10[r.skill] / 10 : 0;
    return Rules.levelForXp(xp) < r.lvl;
  }

  function makeHover(s, r) {
    if (r.ok) return "Make " + r.name;
    if (levelLocked(s, r)) return "Needs " + skillName(r.skill) + " level " + r.lvl;
    for (var i = 0; i < r.inputs.length; i++) {
      var e = r.inputs[i];
      if (e[2] < e[1]) {
        var nm = itemName(e[0]).toLowerCase();
        return "Needs " + Util.fmtInt(e[1]) + " " + nm + (e[1] > 1 && nm.slice(-1) !== "s" ? "s" : "");
      }
    }
    return r.why || r.name;
  }

  function buildMake(s) {
    var v = Engine.view.make(s);
    var sh = $("sheet");
    if (!v) { sh.innerHTML = ""; return; }
    var cells = v.rows.map(function (r) {
      var lock = levelLocked(s, r);
      return '<div class="mk' + (lock ? " lock" : "") + '" data-act="make" data-v="' + esc(r.rid) + '" data-hover="' + esc(makeHover(s, r)) + '">' +
        (r.out ? ico(r.out, 1) : '<i class="ico"></i>') + "<span>" + esc(r.name) + "</span>" + (lock ? '<b class="lv">Lv ' + r.lvl + "</b>" : "") + "</div>";
    }).join("");
    var cols = Math.max(1, Math.min(v.rows.length, Math.floor((sz.view.w - 16) / 60)));
    sh.innerHTML = '<div class="mkt">What will you make?</div><div class="mkg" style="--mc:' + cols + '">' + cells + '</div><div class="row">' +
      qtyButtons("makeqty", prefs.makeQty, [1, 5, 10, -1], "makex") + "</div>" +
      (v.bankAvailable ? '<div class="row"><button class="gb' + (v.bankFeed ? " on" : "") +
        '" data-act="makebank" aria-pressed="' + v.bankFeed + '">Bank-fed: ' + (v.bankFeed ? "On" : "Off") +
        '</button></div><div class="mkt">' + (v.bankFeed ?
          "Uses bank materials; products go to bank. Keep tools in your pack. Stops on closing the game." :
          "Uses materials in your pack. Enable bank-fed mode for automatic storage.") + "</div>" : "");
  }

  function buildAmount() {
    $("sheet").innerHTML = '<div class="amt"><span>How many?</span><input id="amt-in" type="text" inputmode="numeric" maxlength="12" autocomplete="off" spellcheck="false">' +
      '<button class="gb" data-act="amtok">OK</button><button class="gb" data-act="amtno">Cancel</button></div>';
    var inp = document.getElementById("amt-in");
    inp.addEventListener("input", function () {
      var v = inp.value.replace(/[^0-9.kKmM]/g, "");
      if (v !== inp.value) inp.value = v;
    });
    setTimeout(function () { if (document.getElementById("amt-in") === inp) inp.focus(); }, 0);
  }

  function askAmount(done) {
    prompt = { done: done };
    sigs.sheet = null;
  }

  function confirmAmount() {
    if (!prompt) return false;
    var inp = document.getElementById("amt-in");
    var n = Util.parseQty(inp ? inp.value : "", QTY_MAX);
    var p = prompt;
    prompt = null;
    sigs.sheet = null;
    if (inp) inp.blur();
    if (n !== null) p.done(n);
    return true;
  }

  function makeNow(rid) {
    if (typeof rid !== "string") return;
    lastRid = rid;
    act(function (s) {
      var ok = Engine.make(s, rid, prefs.makeQty);
      if (ok && s.player.iface && s.player.iface.t === "make") Engine.closeInterface(s);
      return ok;
    });
  }

  // ----------------------------------------------------------------
  // ---------------------- Banner, toast, veil ---------------------
  // ----------------------------------------------------------------

  function banner(t, kind) {
    var b = $("banner");
    b.className = kind === "warn" || kind === "good" || kind === "season" ? kind : "";
    b.innerHTML = "<span>" + esc(t) + "</span>";
    b.hidden = false;
    bannerUntil = Date.now() + Math.max(3000, String(t).length * 60);
  }

  function showToast(now) {
    var t = toastQ.shift();
    toastCur = t;
    drawToast(t);
    $("toast").hidden = false;
    toastUntil = now + (toastQ.length ? 2500 : 5000);
  }

  // A perk point gets its own gold line, so a long unlock list can't cut it off.
  function drawToast(t) {
    var sub = t.unlocks.length ? "New: " + t.unlocks.join(", ") : "Level up!";
    $("toast").innerHTML = skillIco(t.skill, 32) + "<div><b>" + esc(skillName(t.skill) + " " + t.lvl) + "</b><span>" + esc(sub) + "</span>" +
      (t.perk ? "<em>New perk point!</em>" : "") + "</div>";
  }

  // A perkpoint event (it follows its level event): the chat line, and the line on that skill's newest toast.
  function perkPoint(skill, n) {
    chatLine("You earned " + (n > 1 ? n + " perk points" : "a perk point") + " in " + skillName(skill) + ".", "skill");
    var t = null;
    for (var i = toastQ.length - 1; i >= 0 && !t; i--) if (toastQ[i].skill === skill) t = toastQ[i];
    if (!t && toastCur && toastCur.skill === skill && !$("toast").hidden) t = toastCur;
    if (!t || t.perk) return;
    t.perk = true;
    if (t === toastCur) drawToast(t);
  }

  // The quest-complete window would cover the toast (its rewards level things up): toasts wait for Continue.
  function toastHeld() { return !!uiWin && uiWin.kind === "questdone"; }

  // e.from (a catch-up jump, e.g. 1 -> 4): the toast lists the unlocks of every level gained.
  function levelUp(e, now) {
    flashUntil[e.skill] = now + 2000;
    sigs["pane:skills"] = null;
    var unl = [];
    for (var l = Math.max(1, typeof e.from === "number" ? e.from + 1 : e.lvl); l <= e.lvl; l++) {
      Engine.view.unlocks(e.skill, l).forEach(function (n) { if (unl.indexOf(n) < 0) unl.push(n); });
    }
    toastQ.push({ skill: e.skill, lvl: e.lvl, unlocks: unl });
    if (toastQ.length > 6) toastQ.shift();
    if ($("toast").hidden && !toastHeld()) showToast(now);
    if (e.lvl >= 99) banner("Mastery: " + skillName(e.skill) + " 99", "good");
    // A catch-up's folded level event has no perkpoint events behind it: count the multiples of 5 crossed.
    var pts = typeof e.from === "number" && perksOn() ? Math.floor(e.lvl / 5) - Math.floor(e.from / 5) : 0;
    if (pts > 0) perkPoint(e.skill, pts);
  }

  // ----------------------------------------------------------------
  // -------------- First full pack: the Drop offer -----------------
  // ----------------------------------------------------------------
  // Shown while a gathering pack-full stop stands (no command since), every gathering skill is still on
  // Stop and the player never answered (pref tipFull). It sits under the banner line, above the toasts;
  // only its own box takes clicks. Either button answers for good.
  function askFull(s) {
    var p = s.player;
    return !prefs.tipFull && p.stop === "pack full" && !p.act && GATHER.every(function (k) { return p.afk.full[k] === "stop"; });
  }

  function syncAsk(s) {
    var p = s.player;
    var a = p.act;
    if (a && a.k === "gather" && !(lastGather && lastGather.ref === a.ref && lastGather.op === a.op)) lastGather = { ref: a.ref, op: a.op, base: a.base };
    var on = askFull(s);
    var el = $("ask");
    if (el.hidden === !on) return;
    if (on && !el.firstChild) {
      el.innerHTML = '<div class="ab" role="group" aria-label="' + esc(ASK_FULL) + '"><span>' + esc(ASK_FULL) + "</span><div>" +
        '<button class="gb on" data-act="askdrop">Drop when full</button><button class="gb" data-act="askstop">Keep stopping</button></div></div>';
    }
    el.hidden = !on;
    toggle($("app"), "asking", on);
    if (on) askHeight();
  }

  // The banner line moves below the offer while it shows.
  function askHeight() {
    if (!$("ask").hidden) cssVar("--ask-h", $("ask").offsetHeight + "px");
  }

  // Drop: every gathering skill drops from now on, and the gather that just stopped carries on. The last
  // roll may have used its node up (a stump, a spot that moved): then the nearest node of that kind.
  function answerFull(drop) {
    prefs.tipFull = 1;
    $("ask").hidden = true;
    toggle($("app"), "asking", false);
    if (drop) {
      var g = lastGather;
      act(function (s) { return Engine.setAfk(s, { full: { woodcutting: "drop", mining: "drop", fishing: "drop" } }); });
      if (g) {
        act(function (s) {
          if (Engine.act(s, g.ref, g.op)) return true;
          var near = Engine.nearest(s, "obj", g.base, Rules.RETARGET_RANGE * 2);
          return !!near && Engine.act(s, near, g.op);
        });
      }
      banner(TIP_FULL, "info");
    }
    ctx.persist();
  }

  function veil(kind, pct, t) {
    var v = $("veil");
    var k = kind === "loading" || kind === "catchup" || kind === "death" ? kind : "";
    veilKind = k;
    v.setAttribute("data-kind", k);
    if (k === "loading") {
      text($("veil-title"), "Orcadia");
      text($("veil-text"), t || "Loading…");
    } else if (k === "catchup") {
      var p = Math.max(0, Math.min(100, Math.floor(pct || 0)));
      text($("veil-title"), "Catching up… " + p + "%");
      text($("veil-text"), t || "Your adventurer kept busy while you were away.");
      $("veil-fill").style.width = p + "%";
    } else if (k === "death") {
      text($("veil-title"), "You have fallen");
      text($("veil-text"), t || "");
    }
    if (k !== "death") death = null;
  }

  // The veil's title already says it; the body keeps the consequence.
  function showDeath(t) {
    death = { at: Date.now() };
    closeUiWindows();
    veil("death", 0, String(t || "").replace(/^You have fallen\.\s*/, ""));
  }

  function dismissDeath(force) {
    if (!death || (!force && Date.now() - death.at < 800)) return !!death;
    death = null;
    veil(null);
    return true;
  }

  function timers(now) {
    if (!$("banner").hidden && now > bannerUntil) $("banner").hidden = true;
    var toast = $("toast");
    if (toastHeld()) {
      if (!toast.hidden) { toastQ.unshift(toastCur); toast.hidden = true; }
    } else if (toast.hidden ? toastQ.length > 0 : now > toastUntil) {
      if (toastQ.length) showToast(now);
      else toast.hidden = true;
    }
    if (death && now - death.at > 2400) dismissDeath(true);
  }

  // ----------------------------------------------------------------
  // ---------------------------- Modal -----------------------------
  // ----------------------------------------------------------------

  function openDelete() {
    var m = $("modal");
    m.innerHTML = '<div class="md"><b>Delete this character?</b><p>Levels, bank, gear and quests are erased. This can\'t be undone.</p>' +
      '<div class="mdb"><button data-act="mdno">Cancel</button><button class="danger" data-act="mdyes" disabled>Delete character (3)</button></div></div>';
    m.hidden = false;
    var left = 3;
    clearInterval(modalTimer);
    modalTimer = setInterval(function () {
      left--;
      var b = m.querySelector(".danger");
      if (!b) { clearInterval(modalTimer); return; }
      b.textContent = left > 0 ? "Delete character (" + left + ")" : "Delete character";
      if (left <= 0) { b.disabled = false; clearInterval(modalTimer); }
    }, 1000);
  }

  function closeModal() {
    clearInterval(modalTimer);
    $("modal").hidden = true;
    $("modal").innerHTML = "";
  }

  // ----------------------------------------------------------------
  // ------------------------- Click actions ------------------------
  // ----------------------------------------------------------------

  function closeUiWindows() {
    uiWin = null;
    sigs.win = null;
  }

  // Closes the open sheet or window (iface ones through the engine). True when something closed.
  function closeTop() {
    var s = state();
    var f = s.player.iface;
    if (uiWin && !(f && (f.t === "bank" || f.t === "shop"))) {
      closeUiWindows();
      return true;
    }
    if (f) {
      act(function (st) { Engine.closeInterface(st); return true; });
      return true;
    }
    return false;
  }

  var ACTS = {
    run: function () { var on = !state().player.run; act(function (s) { return Engine.setRun(s, on); }); },
    newmsgs: function () { $("chatlog").scrollTop = $("chatlog").scrollHeight; $("newmsgs").hidden = true; },
    close: function () { closeTop(); },
    map: function () { if (uiWin && uiWin.kind === "map") closeUiWindows(); else openWin({ kind: "map", z: 1, cx: null, cy: null }); },
    mapz: function (v) { mapZoom(+v, null); },
    mapc: function () { if (uiWin && uiWin.kind === "map") { uiWin.cx = null; uiWin.cy = null; } },
    crStep: function (v) {
      var a = String(v).split(":"), k = a[0], n = Util.has(Rules.LOOK, k) ? Rules.LOOK[k] : 0;
      if (!crLook || !n) return;
      crLook[k] = (crLook[k] + (+a[1] || 0) + n) % n;
      crDraw();
    },
    crRandom: function () {
      if (!crLook) return;
      CR_PARTS.forEach(function (p) { crLook[p[0]] = Math.floor(Math.random() * Rules.LOOK[p[0]]); });
      $("cr-name").value = pickOf(CR_A) + pickOf(CR_B);
      crDraw();
    },
    crGo: function () { crGo(); },
    style: function (v) { act(function (s) { return Engine.setStyle(s, v); }); },
    ret: function () { var on = !state().player.afk.ret; act(function (s) { return Engine.setAfk(s, { ret: on }); }); },
    eat: function (v) { act(function (s) { return Engine.setAfk(s, { eat: +v }); }); },
    recall: function () { act(function (s) { return Engine.recall(s); }); },
    guide: function (v) { openWin({ kind: "guide", skill: v }); },
    journal: function (v) { openWin({ kind: "journal", id: v }); },
    opt: function (v, el) { setOption(el.getAttribute("data-k"), el.hasAttribute("data-v") ? v : null); },
    zoom: function () { prefs.zoom = Render.setZoom(32) || 32; ctx.persist(); },
    "delete": openDelete,
    mdno: closeModal,
    mdyes: function () { closeModal(); ctx.reset(); },
    perkup: function (v) { if (perksOn()) act(function (s) { return Engine.perkUp(s, v); }); },
    perkask: function (v) { openPerkReset(v); },
    pkyes: function (v) { perkReset(v); },
    bankqty: function (v) { prefs.bankQty = +v; },
    bankx: function () { askAmount(function (n) { prefs.bankQty = n; }); },
    banknote: function (v) { act(function (s) { return Engine.setBankNote(s, v === "1"); }); },
    pet: function (v) {
      var on = state().player.pet === v;
      act(function (s) { return Engine.setPet(s, on ? null : v); });
    },
    petinfo: function (v) { openWin({ kind: "pet", id: v }); },
    deppack: function () { act(function (s) { return Engine.depositAll(s); }); },
    depworn: function () { act(function (s) { return Engine.depositWorn(s); }); },
    shopqty: function (v) { prefs.shopQty = +v; },
    make: function (v) { makeNow(v); },
    makeqty: function (v) { prefs.makeQty = +v; },
    makebank: function () {
      act(function (s) { return Engine.setMakeBankFeed(s, !s.player.iface.bankFeed); });
      sigs.sheet = null;
    },
    makex: function () { askAmount(function (n) { prefs.makeQty = n; }); },
    dlgnext: function () { act(function (s) { return Engine.dialogueContinue(s); }); },
    dlgopt: function (v) { act(function (s) { return Engine.dialogueChoose(s, +v); }); },
    askdrop: function () { answerFull(true); },
    askstop: function () { answerFull(false); },
    amtok: confirmAmount,
    amtno: function () { prompt = null; sigs.sheet = null; }
  };

  function onClick(ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest("#veil")) { if (veilKind === "death") dismissDeath(false); return; }
    if (!ctx || ctx.blocked() || t.closest("#menu")) return;
    var tab = t.closest("[data-tab]");
    if (tab) { clickTab(tab.getAttribute("data-tab")); return; }
    var f = t.closest("[data-filter]");
    if (f) { setFilter(f.getAttribute("data-filter")); return; }
    var a = t.closest("[data-act]");
    if (!a || a.disabled) return;
    var fn = ACTS[a.getAttribute("data-act")];
    if (!fn) return;
    hideTip();
    fn(a.getAttribute("data-v"), a);
    if (a.tagName === "BUTTON") a.blur();
  }

  // ----------------------------------------------------------------
  // --------------------------- Tooltips ---------------------------
  // ----------------------------------------------------------------

  function hideTip() {
    clearTimeout(tipTimer);
    $("tip").hidden = true;
  }

  function onOver(ev) {
    if (ev.pointerType && ev.pointerType !== "mouse") return;
    var el = ev.target && ev.target.closest ? ev.target.closest("[data-tip]") : null;
    hideTip();
    if (!el || (el.closest("#view") && !el.closest("#win"))) return;
    var x = ev.clientX;
    var y = ev.clientY;
    tipTimer = setTimeout(function () {
      var tip = $("tip");
      // Stone over the world and the scroll (chat, side, minimap); host colours over the status strip only.
      tip.className = el.closest("#view,#chat,#side,#mm") ? "game" : "";
      tip.textContent = el.getAttribute("data-tip");
      tip.hidden = false;
      var w = tip.offsetWidth;
      var h = tip.offsetHeight;
      tip.style.left = Math.max(4, Math.min(window.innerWidth - w - 4, x + 10)) + "px";
      tip.style.top = (y + 18 + h > window.innerHeight - 4 ? y - h - 8 : y + 18) + "px";
    }, 400);
  }

  // ----------------------------------------------------------------
  // --------------------------- Lifecycle --------------------------
  // ----------------------------------------------------------------

  function init(c) {
    ctx = c;
    watchTheme();
    buildTabs();
    buildCombat();
    buildOptions();
    document.addEventListener("click", onClick);
    Music.init();
    $("cr-name").addEventListener("input", crValid);
    $("cr-name").addEventListener("keydown", function (ev) { if (ev.key === "Enter") { ev.preventDefault(); crGo(); } });
    document.addEventListener("pointerover", onOver);
    document.addEventListener("pointerout", function (ev) { if (!ev.relatedTarget || !ev.relatedTarget.closest || !ev.relatedTarget.closest("[data-tip]")) hideTip(); });
    document.addEventListener("pointerdown", hideTip, true);
    $("chatlog").addEventListener("scroll", function () { if (atBottom()) $("newmsgs").hidden = true; });
    $("sheet").addEventListener("keydown", function (ev) {
      if (!ev.target || ev.target.id !== "amt-in") return;
      if (ev.key === "Enter") { ev.preventDefault(); confirmAmount(); }
      if (ev.key === "Escape") { ev.preventDefault(); prompt = null; sigs.sheet = null; }
    });
    if (window.ResizeObserver) new ResizeObserver(queueLayout).observe($("app"));
    else window.addEventListener("resize", queueLayout);
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-reduced-motion: reduce)");
      if (mq.addEventListener) mq.addEventListener("change", applyPrefs);
    }
    applyLayout();
    applyPrefs();
  }

  // UI timers run on Date.now(); Main's nowMs is a frame clock.
  // ----------------------------------------------------------------
  // ----------------------- Character creation ---------------------
  // ----------------------------------------------------------------

  var CR_PARTS = [["skin", "Skin"], ["hair", "Hair"], ["hairCol", "Hair colour"], ["top", "Top"], ["legs", "Legs"]];
  var CR_A = ["Al", "Bran", "Cor", "Da", "El", "Fen", "Gar", "Hal", "Ise", "Jor", "Ka", "Lor", "Mae", "Nor", "Os", "Ren", "Sel", "Tor", "Ul", "Wy"];
  var CR_B = ["dric", "wen", "ric", "mir", "sa", "ton", "lin", "dra", "vik", "na", "rok", "eth", "ira", "gan"];
  var CR_SCALE = 4;
  var crLook = null;

  function pickOf(a) { return a[Math.floor(Math.random() * a.length)]; }

  // Shown while the character has no name (a new game, or a save from before names), never while booting.
  function syncCreate(s) {
    var el = $("create");
    if (s.player.name || ctx.blocked()) {
      if (!el.hidden) { el.hidden = true; crLook = null; }
      return;
    }
    if (!el.hidden) return;
    crLook = Rules.cleanLook(s.player.look);
    el.hidden = false;
    crDraw();
    $("cr-name").focus();
  }

  function crDraw() {
    $("cr-rows").innerHTML = CR_PARTS.map(function (p) {
      var k = p[0], i = crLook[k];
      var v = k === "hair" ? esc(Sprites.HAIR_STYLES[i]) :
        '<i style="background:' + Sprites.LOOK_PAL[k][i] + '"></i>' + (i + 1) + "/" + Rules.LOOK[k];
      return "<span>" + p[1] + '</span><button data-act="crStep" data-v="' + k + ':-1" aria-label="Previous ' + p[1] +
        '">&lsaquo;</button><b>' + v + '</b><button data-act="crStep" data-v="' + k + ':1" aria-label="Next ' + p[1] + '">&rsaquo;</button>';
    }).join("");
    crDoll();
    crValid();
  }

  // The front view of the base look (no gear), scaled up crisply.
  function crDoll() {
    var sp = Sprites.player({}, 4, 0, null, crLook);
    var cv = $("cr-doll"), d = Math.max(1, Math.ceil(window.devicePixelRatio || 1)), k = CR_SCALE * d;
    cv.width = sp.w * k;
    cv.height = sp.h * k;
    cv.style.width = sp.w * CR_SCALE + "px";
    cv.style.height = sp.h * CR_SCALE + "px";
    var g = cv.getContext("2d");
    g.imageSmoothingEnabled = false;
    g.clearRect(0, 0, cv.width, cv.height);
    g.drawImage(sp.cv, 0, 0, sp.w, sp.h, 0, 0, cv.width, cv.height);
  }

  function crValid() {
    var v = $("cr-name").value, ok = !!Rules.cleanName(v);
    $("cr-go").disabled = !ok;
    $("cr-err").textContent = v.trim() && !ok ? "Use 1 to 12 letters, numbers or spaces." : "";
    return ok;
  }

  function crGo() {
    if (!crLook || !crValid()) return;
    var name = $("cr-name").value, look = crLook;
    if (act(function (s) { return Engine.setLook(s, name, look); })) {
      $("create").hidden = true;
      crLook = null;
      ctx.persist();
    }
  }

  function update() {
    if (!ctx || !sz) return;
    var now = Date.now();
    var s = state();
    syncCreate(s);
    Music.update(s, prefs.music, prefs.musicVol, prefs.sfx);
    var st = Engine.status(s);
    syncStatus(s, st);
    syncAsk(s);
    syncOrbs(st);
    syncIfaceTab(s);
    questDone(s);
    syncPane(s, st);
    syncWindow(s, now, st);
    syncSheet(s);
    timers(now);
  }

  // One sound per event batch, the biggest moment in it (19.7).
  var CUES = ["rested", "level", "rare", "mastery", "quest"];

  function cueOf(e) {
    if (e.type === "level") return e.lvl >= 99 ? "mastery" : "level";
    if (e.type === "questDone") return "quest";
    return e.type === "rare" || e.type === "rested" ? e.type : "";
  }

  function playCue(cue) {
    if (cue && prefs.sfx) Music.sfx(cue);
  }

  function onEvents(evs) {
    var now = Date.now();
    var warned = evs.some(function (e) { return e.type === "msg" && e.c === "warn"; });
    var loot = [];
    var cue = "";
    for (var i = 0; i < evs.length; i++) {
      var e = evs[i];
      var c = cueOf(e);
      if (CUES.indexOf(c) > CUES.indexOf(cue)) cue = c;
      if (e.type === "msg") { flushLoot(loot); chatLine(e.text, e.c); }
      else if (e.type === "loot") loot.push(e);
      else if (e.type === "xp") trackXp(e, state().tick);
      else if (e.type === "level") levelUp(e, now);
      else if (e.type === "perkpoint") perkPoint(e.skill, 1);
      else if (e.type === "stop") {
        if (e.ref) lastGather = { ref: e.ref, op: e.op, base: e.base };
        stopped(e.why, warned);
      }
      else if (e.type === "death" && e.on === 0) {
        showDeath(e.text);
        if (e.text) chatLine(e.text, "warn");   // the veil fades; where the grave is must stay readable
      }
      else if (e.type === "questDone") doneQ.push(e.id);
      else if (e.type === "season") seasonBanner(e.id);
      else if (e.type === "pet" && Data.pets && Util.has(Data.pets, e.id)) {
        banner("New pet: " + Data.pets[e.id].name + "! See Pets on the Combat tab.", "good");
      }
      else if (e.type === "petGrow") {
        var gv = Engine.view.pet(state(), e.id);
        if (gv && gv.forms[e.stage] && gv.forms[e.stage - 1]) {
          banner(gv.forms[e.stage - 1].name + " grew into " + gv.forms[e.stage].name + "!", "good");
        }
        sigs["pane:pets"] = null;
      }
      else if (e.type === "rested") banner("Well rested: double XP for your next " + etaText(e.total, true) + " of skilling and combat", "good");
      else if (e.type === "iface" || e.type === "quest") {
        sigs.sheet = null;
        sigs["pane:quests"] = null;
      }
    }
    flushLoot(loot);
    playCue(cue);
  }

  // Prints the batch's loot so far as one line and empties the list.
  function flushLoot(loot) {
    var got = lootText(loot);
    if (got) chatLine("Loot: " + got + ".", "loot");
    loot.length = 0;
  }

  // Auto-loot, Take and grave loot land in the pack silently; one line per batch says what came in.
  function lootText(evs) {
    var order = [];
    var qty = {};
    evs.forEach(function (e) {
      if (!itemDef(e.id) || !(e.qty > 0)) return;
      if (!Util.has(qty, e.id)) { qty[e.id] = 0; order.push(e.id); }
      qty[e.id] += e.qty;
    });
    return order.map(function (id) { return itemName(id) + (qty[id] > 1 ? " ×" + Util.fmtInt(qty[id]) : ""); }).join(", ");
  }

  // A stop: banner, plus a warn line unless the engine already said why. The first gathering pack-full
  // stop shows the Drop offer instead of the banner.
  function stopped(why, warned) {
    var t = "Stopped: " + why;
    if (!warned) chatLine(t + ".", "warn");
    if (!askFull(state())) banner(t, "warn");
  }

  function resync() {
    sigs = {};
    trk = { skill: null, since: 0, gains: [] };
    goalMemo = {};
    var cells = document.querySelectorAll("[data-slot],[data-eq],[data-bank],[data-shop]");
    for (var i = 0; i < cells.length; i++) cells[i]._sig = null;
  }

  function reset() {
    clearChat();
    closeUiWindows();
    prompt = null;
    toastQ = [];
    doneQ = [];
    flashUntil = {};
    lastRid = null;
    prevTab = null;
    $("toast").hidden = true;
    $("banner").hidden = true;
    $("ask").hidden = true;
    toggle($("app"), "asking", false);
    lastGather = null;
    if (death) dismissDeath(true);
    closeModal();
    resync();
  }

  function summary(sum, capTicks) {
    if (!sum) return;
    openWin({ kind: "away", sum: sum, cap: capTicks });
    playCue(Object.keys(sum.levels || {}).length ? "level" : "");
  }

  function sheetHeight() { return sheetH; }

  // ----------------------------------------------------------------
  // ---------------------- Keys (via Input) ------------------------
  // ----------------------------------------------------------------

  // Esc after the menu: death veil, amount prompt, sheet or window. Layout C's pane is last (paneEsc).
  function escape() {
    if (death) return dismissDeath(false);
    if (!$("modal").hidden) { closeModal(); return true; }
    if (prompt) { prompt = null; sigs.sheet = null; return true; }
    return closeTop();
  }

  function paneEsc() {
    if (L !== "C" || !paneOpen) return false;
    paneOpen = false;
    syncPaneOpen();
    return true;
  }

  // Space: continue a dialogue, repeat Make-X, close the away window.
  function space() {
    var s = state();
    var f = s.player.iface;
    if (uiWin && uiWin.kind === "away") { closeUiWindows(); return true; }
    if (prompt) return false;
    if (f && f.t === "dialogue") {
      var v = Engine.view.dialogue(s);
      if (v && !v.opts) act(function (st) { return Engine.dialogueContinue(st); });
      return true;
    }
    if (f && f.t === "make") {
      var m = Engine.view.make(s);
      if (!m || !m.rows.length) return true;
      var rid = m.rows.some(function (r) { return r.rid === lastRid; }) ? lastRid : m.rows[0].rid;
      makeNow(rid);
      return true;
    }
    return false;
  }

  // Enter: confirm the amount prompt, close the away window.
  function enter() {
    if (prompt) return confirmAmount();
    if (uiWin && uiWin.kind === "away") { closeUiWindows(); return true; }
    return false;
  }

  // A world click first closes an open sheet or window.
  function closeAll() {
    prompt = null;
    sigs.sheet = null;
    if (uiWin) closeUiWindows();
    var f = state().player.iface;
    if (f) act(function (s) { Engine.closeInterface(s); return true; });
  }

  function layout() { return L; }

  return {
    init: init, applyLayout: applyLayout, update: update, onEvents: onEvents, resync: resync, reset: reset,
    banner: banner, summary: summary, chatLine: chatLine, veil: veil, notSaving: notSaving, prefs: getPrefs,
    setPrefs: setPrefs, chat: chat, setChat: setChat, setDock: setDock, sheetHeight: sheetHeight,
    // Used by Input and Main (beyond 19.9): keys, X prompts, shop flash, world-click close, layout letter.
    escape: escape, paneEsc: paneEsc, space: space, enter: enter, closeAll: closeAll, askAmount: askAmount,
    shopFlash: shopFlash, layout: layout, qtyLabel: qtyLabel,
    openPet: function (id) { openWin({ kind: "pet", id: id }); }
  };
})();
// ==== src/ui/input.js ====
// ----------------------------------------------------------------
// ------------------- Input: pointer and keys --------------------
// ----------------------------------------------------------------
// DESIGN.md 19.4: hover line, left click, right-click menu, long press, inventory drag, use mode, wheel
// zoom and the three keys (Esc, Space, Enter). Every game change goes through ctx.act(Engine.*). While
// booting or catching up, every pointer and key command is ignored; reload/zoom/back keys are always blocked.
const Input = (function () {
  "use strict";

  var LONG_MS = 450;
  var DRAG_PX = 6;
  var DRAG_MS = 120;
  var TAP_SLOP = 8;
  var MENU_LEAVE = 12;
  var WHEEL_STEP = 50;
  var PINCH_STEP = 25;
  var WHEEL_COOLDOWN = 120;

  var ctx = null;
  var ptr = { x: 0, y: 0, el: null, shift: false };
  var useSlot = -1;
  var press = null;          // { tgt, x, y, t, id, touch, drag, long, timer }
  var ctrlPress = null;      // Ctrl+click waiting for its contextmenu
  var menu = null;           // { entries, x, y, rect, at }
  var ghost = null;
  var hoverSig = "";
  var hoverRef = "";
  var wheel = { acc: 0, at: 0 };
  var els = {};

  function $(id) { return els[id] || (els[id] = document.getElementById(id)); }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" : "&quot;"; });
  }
  function S() { return ctx.state(); }
  function blocked() { return !ctx || ctx.blocked(); }
  function itemName(id) { return typeof id === "string" && Util.has(Data.items, id) ? Data.items[id].name : ""; }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function now() { return Date.now(); }
  function isWorld(ref) { return /^(tile|obj|npc|ground|grave):/.test(ref); }
  function act(fn) { return ctx.act(fn); }

  // ----------------------------------------------------------------
  // --------------------------- Targets ----------------------------
  // ----------------------------------------------------------------

  // What a DOM element is, for clicks, menus and hover.
  function targetOf(el) {
    if (!el || !el.closest) return null;
    if (el === $("game")) return { kind: "game" };
    if (el === $("minimap")) return { kind: "mm" };
    var c = el.closest("[data-slot]");
    if (c && c.closest("#inv")) return { kind: "inv", slot: +c.getAttribute("data-slot"), el: c };
    c = el.closest("[data-eq]");
    if (c) return { kind: "eq", ref: "equip:" + c.getAttribute("data-eq") };
    c = el.closest("[data-bank]");
    if (c) return { kind: "bank", ref: "bank:" + c.getAttribute("data-bank") };
    c = el.closest("[data-shop]");
    if (c) return { kind: "shop", i: +c.getAttribute("data-shop"), ref: "shop:" + c.getAttribute("data-shop"), el: c };
    c = el.closest("[data-hover]");
    if (c) return { kind: "label", text: c.getAttribute("data-hover") };
    return null;
  }

  function menuOpt() {
    return useSlot >= 0 ? { useSlot: useSlot, atk: UI.prefs().atk } : { atk: UI.prefs().atk };
  }

  function worldEntries(x, y) {
    var pick = Render.pick(x, y);
    return pick ? Engine.menuAt(S(), pick, menuOpt()) : [];
  }

  // Inventory entries, use-mode aware.
  function invEntries(slot) {
    var s = S();
    var it = s.player.inv[slot];
    if (!it) return [];
    if (useSlot >= 0) {
      var used = s.player.inv[useSlot];
      if (useSlot === slot || !used || it.note) return [];
      return [{ label: "Use", target: itemName(used.id) + " -> " + itemName(it.id), kind: "item", ref: "inv:" + slot, op: "use", arg: useSlot }];
    }
    return Engine.options(s, "inv:" + slot);
  }

  // The summoned pet (its hit rect is "pet:0") adds Inspect and Dismiss to the right-click menu only; a left
  // click goes through it to whatever lies beneath.
  function petEntries(x, y) {
    var pick = Render.pick(x, y), s = S(), v = s.player.pet ? Engine.view.pet(s, s.player.pet) : null;
    if (!pick || pick.refs.indexOf("pet:0") < 0 || !v || useSlot >= 0) return [];
    return [{ label: "Inspect", target: v.name, kind: "pet", ref: "pet:0", op: "inspect" },
      { label: "Dismiss", target: v.name, kind: "pet", ref: "pet:0", op: "dismiss" }];
  }

  function entriesFor(tgt, x, y) {
    if (tgt.kind === "game") return petEntries(x, y).concat(worldEntries(x, y));
    if (tgt.kind === "inv") return invEntries(tgt.slot);
    if (tgt.kind === "eq" || tgt.kind === "bank" || tgt.kind === "shop") return Engine.options(S(), tgt.ref);
    return [];
  }

  // ----------------------------------------------------------------
  // ---------------------------- Actions ---------------------------
  // ----------------------------------------------------------------

  function setUse(slot) {
    if (useSlot === slot) return;
    var cells = $("inv").children;
    if (useSlot >= 0 && cells[useSlot]) cells[useSlot].classList.remove("use");
    useSlot = slot;
    if (useSlot >= 0 && cells[useSlot]) cells[useSlot].classList.add("use");
    hoverSig = "";
  }

  // Runs one MenuEntry: use without arg enters use mode, "x" asks for a number.
  function run(e, x, y) {
    if (!e) return;
    if (e.kind === "pet") {
      var id = S().player.pet;
      if (e.op === "inspect" && id) UI.openPet(id);
      else if (e.op === "dismiss") act(function (s) { return Engine.setPet(s, null); });
      return;
    }
    var r = Util.parseRef(e.ref);
    if (e.op === "use" && typeof e.arg !== "number") {
      if (r && r.t === "inv") setUse(r.n);
      return;
    }
    if (e.arg === "x") {
      UI.askAmount(function (n) { act(function (s) { return Engine.act(s, e.ref, e.op, n); }); });
      return;
    }
    var world = isWorld(e.ref) && e.op !== "examine";
    if (world) UI.closeAll();
    act(function (s) { return Engine.act(s, e.ref, e.op, e.arg); });
    if (world && typeof x === "number") Render.marker(x, y, e.op === "walk" ? "walk" : "act");
    if (useSlot >= 0) setUse(-1);
  }

  function primaryGame(x, y) {
    var es = worldEntries(x, y);
    if (es.length) run(es[0], x, y);
  }

  function minimapWalk(x, y) {
    var t = Render.minimapPick(x, y);
    if (!t) return;
    if (useSlot >= 0) setUse(-1);
    UI.closeAll();
    act(function (s) { return Engine.walkTo(s, t.x, t.y); });
  }

  function invPrimary(slot) {
    var s = S();
    if (!s.player.inv[slot]) {
      if (useSlot >= 0) setUse(-1);
      return;
    }
    if (useSlot >= 0) {
      var from = useSlot;
      setUse(-1);
      if (from !== slot) act(function (st) { return Engine.useItemOn(st, from, "inv:" + slot); });
      return;
    }
    var f = s.player.iface;
    if (f && f.t === "bank") {
      var q = UI.prefs().bankQty;
      act(function (st) { return Engine.act(st, "inv:" + slot, "deposit", q); });
      return;
    }
    run(Engine.options(s, "inv:" + slot)[0]);
  }

  function shopBuy(tgt) {
    var q = UI.prefs().shopQty;
    var ok = act(function (s) { return Engine.act(s, tgt.ref, "buy", q); });
    if (ok) return;
    var v = Engine.view.shop(S());
    var row = v ? v.rows[tgt.i] : null;
    if (row && v.coins < row.price) UI.shopFlash(tgt.i);
  }

  function primary(tgt, x, y) {
    if (tgt.kind === "game") primaryGame(x, y);
    else if (tgt.kind === "inv") invPrimary(tgt.slot);
    else if (tgt.kind === "eq") run(Engine.options(S(), tgt.ref)[0]);
    else if (tgt.kind === "bank") {
      var q = UI.prefs().bankQty;
      act(function (s) { return Engine.act(s, tgt.ref, "withdraw", q); });
    } else if (tgt.kind === "shop") shopBuy(tgt);
  }

  function shiftDrop(slot) {
    var s = S();
    var f = s.player.iface;
    if (!UI.prefs().shiftDrop || useSlot >= 0 || (f && (f.t === "bank" || f.t === "shop")) || !s.player.inv[slot]) return false;
    act(function (st) { return Engine.act(st, "inv:" + slot, "drop"); });
    return true;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Menu -----------------------------
  // ----------------------------------------------------------------

  function entryHtml(e) {
    var t = e.target ? ' <span class="k-' + esc(e.kind) + '">' + esc(e.target) + "</span>" : "";
    if (e.lvl !== undefined && e.kind === "npc") {
      var col = Rules.levelColor(e.lvl - Engine.status(S()).cmb);
      t += ' <span style="color:' + col + '">(level-' + e.lvl + ")</span>";
    }
    return esc(e.label) + t;
  }

  function appRect() { return $("app").getBoundingClientRect(); }

  function openMenu(entries, x, y) {
    if (!entries.length) return;
    closeMenu();
    var m = $("menu");
    var a = appRect();
    m.innerHTML = '<div class="mh">Options</div><div class="mb">' + entries.map(function (e, i) {
      return '<div class="mr" data-i="' + i + '">' + entryHtml(e) + "</div>";
    }).join("") + '<div class="mr" data-i="-1">Cancel</div></div>';
    m.style.width = "";
    m.style.left = "0px";
    m.style.top = "0px";
    m.style.maxWidth = Math.max(120, a.width - 8) + "px";
    m.hidden = false;
    var w = Math.max(120, Math.min(a.width - 8, m.offsetWidth + 2));
    m.style.width = w + "px";
    var h = m.offsetHeight;
    var left = clamp(x - w / 2, a.left + 4, a.right - 4 - w);
    var top = y + h <= a.bottom - 4 ? y : y - h;
    top = clamp(top, a.top + 4, Math.max(a.top + 4, a.bottom - 4 - h));
    m.style.left = Math.round(left) + "px";
    m.style.top = Math.round(top) + "px";
    menu = { entries: entries, x: x, y: y, at: now(), rect: m.getBoundingClientRect() };
    setHover("");
  }

  function closeMenu() {
    if (!menu) return false;
    menu = null;
    $("menu").hidden = true;
    $("menu").innerHTML = "";
    return true;
  }

  function pickMenu(ev) {
    var row = ev.target && ev.target.closest ? ev.target.closest(".mr") : null;
    if (!row || !menu || now() - menu.at < 250) return;
    var i = +row.getAttribute("data-i");
    var m = menu;
    closeMenu();
    if (i < 0) {
      if (useSlot >= 0) setUse(-1);
      return;
    }
    if (!blocked()) run(m.entries[i], m.x, m.y);
  }

  function openContext(tgt, x, y) {
    if (!tgt || blocked()) return;
    openMenu(entriesFor(tgt, x, y), x, y);
  }

  // Closes once the pointer is 12 px outside the menu.
  function menuLeave(x, y) {
    var r = menu.rect;
    var dx = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
    var dy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
    if (Math.max(dx, dy) > MENU_LEAVE) closeMenu();
  }

  // ----------------------------------------------------------------
  // ------------------------- Hover line ---------------------------
  // ----------------------------------------------------------------

  function setHover(html) {
    if (html === hoverSig) return;
    hoverSig = html;
    var h = $("hover");
    h.innerHTML = html;
    if (html && h.scrollWidth > h.clientWidth) {
      var more = h.querySelector(".k-more");
      if (more) more.parentNode.removeChild(more);
    }
  }

  function lineFor(e, more) {
    return entryHtml(e) + (more > 0 ? '<span class="k-more"> / ' + more + " more option" + (more === 1 ? "" : "s") + "</span>" : "");
  }

  // The hover entry list for whatever the pointer is over.
  function hoverLine(tgt) {
    if (tgt.kind === "label") return { html: esc(tgt.text || ""), ref: null };
    if (tgt.kind === "shop") return { html: esc(tgt.el.getAttribute("data-hover") || ""), ref: null };
    var s = S();
    if (tgt.kind === "inv") {
      var it = s.player.inv[tgt.slot];
      if (!it) return null;
      var f = s.player.iface;
      if (useSlot < 0 && f && f.t === "bank") {
        return { html: lineFor({ label: "Deposit-" + UI.qtyLabel(UI.prefs().bankQty), target: itemName(it.id), kind: "item" }, 0), ref: null };
      }
      if (useSlot < 0 && ptr.shift && UI.prefs().shiftDrop && !(f && f.t === "shop")) {
        var d = Data.items[it.id];
        if (d && d.cat !== "quest") return { html: lineFor({ label: "Drop", target: d.name, kind: "item" }, 0), ref: null };
      }
    }
    if (tgt.kind === "bank") {
      var b = Engine.options(s, tgt.ref);
      if (!b.length) return null;
      return { html: lineFor({ label: "Withdraw-" + UI.qtyLabel(UI.prefs().bankQty), target: b[0].target, kind: "item" }, b.length - 1), ref: null };
    }
    var es = entriesFor(tgt, ptr.x, ptr.y);
    if (!es.length) return null;
    return { html: lineFor(es[0], es.length - 1), ref: isWorld(es[0].ref) && es[0].op !== "walk" ? es[0].ref : null };
  }

  function syncHover() {
    if (ptr.el && !ptr.el.isConnected) ptr.el = document.elementFromPoint(ptr.x, ptr.y);
    var tgt = menu || (press && press.drag) ? null : targetOf(ptr.el);
    var line = tgt && tgt.kind !== "mm" ? hoverLine(tgt) : null;
    setHover(line ? line.html : "");
    var ref = line && line.ref ? line.ref : "";
    var key = ref + ":" + useSlot;
    if (key !== hoverRef) {
      hoverRef = key;
      // Use mode passes the slot so Render outlines only valid targets (Engine.canUse).
      if (useSlot >= 0) Render.hover(ref || null, "use", useSlot);
      else Render.hover(ref || null, "normal");
    }
  }

  // ----------------------------------------------------------------
  // ------------------------ Pointer events ------------------------
  // ----------------------------------------------------------------

  function onDown(ev) {
    if (!ctx) return;
    var t = ev.target;
    if (t && t.closest && t.closest("#menu")) return;
    var hadMenu = closeMenu();
    if (blocked() || ev.button !== 0) return;
    var tgt = targetOf(t);
    if (!tgt || tgt.kind === "label") return;
    if (ev.ctrlKey) {
      ctrlPress = { tgt: tgt, x: ev.clientX, y: ev.clientY };
      return;
    }
    if (hadMenu) return;
    var touch = ev.pointerType === "touch" || ev.pointerType === "pen";
    if (tgt.kind === "mm") { minimapWalk(ev.clientX, ev.clientY); return; }
    if (tgt.kind === "game" && !touch) { primaryGame(ev.clientX, ev.clientY); return; }
    if (tgt.kind === "inv" && ev.shiftKey && shiftDrop(tgt.slot)) return;
    press = { tgt: tgt, x: ev.clientX, y: ev.clientY, t: now(), id: ev.pointerId, touch: touch, drag: false, long: false, timer: 0 };
    if (touch) {
      var p = press;
      p.timer = setTimeout(function () {
        if (press !== p || p.drag) return;
        p.long = true;
        openContext(p.tgt, p.x, p.y);
      }, LONG_MS);
    }
  }

  function onMove(ev) {
    ptr.x = ev.clientX;
    ptr.y = ev.clientY;
    ptr.el = ev.target;
    ptr.shift = !!ev.shiftKey;
    if (menu) menuLeave(ev.clientX, ev.clientY);
    var p = press;
    if (!p || ev.pointerId !== p.id) return;
    var d = Math.max(Math.abs(ev.clientX - p.x), Math.abs(ev.clientY - p.y));
    if (p.touch && d > TAP_SLOP) clearTimeout(p.timer);
    if (p.tgt.kind === "inv" && !p.drag && !p.long && d >= DRAG_PX && now() - p.t >= DRAG_MS && S().player.inv[p.tgt.slot]) {
      startDrag(ev, p);
    }
    if (p.drag && ghost) {
      ghost.style.left = ev.clientX - 16 + "px";
      ghost.style.top = ev.clientY - 16 + "px";
    }
  }

  function onUp(ev) {
    if (ctrlPress) {
      var c = ctrlPress;
      ctrlPress = null;
      if (!menu) openContext(c.tgt, c.x, c.y);
      return;
    }
    var p = press;
    if (!p || ev.pointerId !== p.id) return;
    press = null;
    clearTimeout(p.timer);
    if (p.drag) { endDrag(ev, p); return; }
    if (p.long || blocked()) return;
    var moved = Math.max(Math.abs(ev.clientX - p.x), Math.abs(ev.clientY - p.y));
    if (p.touch && moved > TAP_SLOP) return;
    // A quick flick that stopped before the drag timer: released over another target, it was never a click.
    if (!p.touch && moved >= DRAG_PX && !sameTarget(targetOf(document.elementFromPoint(ev.clientX, ev.clientY)), p.tgt)) {
      if (p.tgt.kind === "inv" && S().player.inv[p.tgt.slot]) endDrag(ev, p);
      return;
    }
    primary(p.tgt, p.x, p.y);
  }

  function sameTarget(a, b) {
    return !!a && !!b && a.kind === b.kind && a.slot === b.slot && a.ref === b.ref;
  }

  function cancelPress() {
    if (!press) return;
    clearTimeout(press.timer);
    if (press.drag) endDrag(null, press);
    press = null;
  }

  function onContext(ev) {
    ev.preventDefault();
    ctrlPress = null;
    if (!ctx || blocked()) return;
    if (press) cancelPress();
    var tgt = targetOf(ev.target);
    if (tgt && tgt.kind !== "mm" && tgt.kind !== "label") openContext(tgt, ev.clientX, ev.clientY);
  }

  // ----------------------------------------------------------------
  // ------------------------ Inventory drag ------------------------
  // ----------------------------------------------------------------

  function startDrag(ev, p) {
    p.drag = true;
    if (useSlot >= 0) setUse(-1);
    clearTimeout(p.timer);
    try { p.tgt.el.setPointerCapture(ev.pointerId); } catch (e) { /* the pointer may already be gone */ }
    p.tgt.el.classList.add("drag");
    ghost = document.createElement("div");
    ghost.id = "ghost";
    var ic = p.tgt.el.querySelector(".ico");
    if (ic) ghost.appendChild(ic.cloneNode(true));
    ghost.style.left = ev.clientX - 16 + "px";
    ghost.style.top = ev.clientY - 16 + "px";
    document.body.appendChild(ghost);
    setHover("");
  }

  function endDrag(ev, p) {
    p.tgt.el.classList.remove("drag");
    if (ghost && ghost.parentNode) ghost.parentNode.removeChild(ghost);
    ghost = null;
    if (!ev || blocked()) return;
    var under = document.elementFromPoint(ev.clientX, ev.clientY);
    var cell = under && under.closest ? under.closest("[data-slot]") : null;
    if (!cell || !cell.closest("#inv")) return;
    var from = p.tgt.slot;
    var to = +cell.getAttribute("data-slot");
    if (from === to) return;
    if (useSlot >= 0) setUse(-1);
    act(function (s) { return Engine.moveItem(s, from, to); });
  }

  // ----------------------------------------------------------------
  // --------------------------- Wheel ------------------------------
  // ----------------------------------------------------------------

  function zoom(dir) {
    var applied = Render.zoomStep(dir);
    var p = UI.prefs();
    if (typeof applied === "number" && applied !== p.zoom) {
      p.zoom = applied;
      UI.setPrefs(p);
    }
  }

  function chatOverlayHit(x, y) {
    if (UI.layout() !== "C") return false;
    var c = $("chat");
    if (c.offsetParent === null) return false;
    var r = c.getBoundingClientRect();
    return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  }

  function onWheel(ev) {
    closeMenu();
    var onGame = ev.target === $("game");
    if (ev.ctrlKey) ev.preventDefault();
    if (!onGame || !ctx) return;
    if (!ev.ctrlKey) ev.preventDefault();
    if (blocked()) return;
    var dy = ev.deltaY * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? 400 : 1);
    if (!ev.ctrlKey && chatOverlayHit(ev.clientX, ev.clientY)) {
      $("chatlog").scrollTop += dy;
      return;
    }
    var t = now();
    var step = ev.ctrlKey ? PINCH_STEP : WHEEL_STEP;
    if (!ev.ctrlKey && t - wheel.at < WHEEL_COOLDOWN) { wheel.acc = 0; return; }
    if ((wheel.acc > 0) !== (dy > 0)) wheel.acc = 0;
    wheel.acc += dy;
    if (Math.abs(wheel.acc) < step) return;
    zoom(wheel.acc > 0 ? -1 : 1);
    wheel.acc = 0;
    wheel.at = t;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Keys -----------------------------
  // ----------------------------------------------------------------

  // Capture phase, preventDefault only: these would reload, zoom or navigate the webview away.
  function blockKeys(ev) {
    var k = ev.key;
    var mod = ev.ctrlKey || ev.metaKey;
    if (k === "F5" || k === "BrowserBack" || k === "BrowserForward" ||
      (mod && (k === "r" || k === "R" || k === "=" || k === "+" || k === "-" || k === "0")) ||
      (ev.altKey && (k === "ArrowLeft" || k === "ArrowRight"))) ev.preventDefault();
  }

  function typing() {
    var a = document.activeElement;
    return !!a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable);
  }

  function onKey(ev) {
    if (ev.ctrlKey || ev.metaKey || ev.altKey || typing() || !ctx) return;
    var k = ev.key;
    if (k !== "Escape" && k !== " " && k !== "Enter") return;
    ev.preventDefault();
    if (blocked()) return;
    if (k === "Escape") escape();
    else if (k === " ") UI.space();
    else UI.enter();
  }

  // Esc order: menu, drag, then UI (amount, sheet or window), use mode, layout C's pane.
  function escape() {
    if (closeMenu()) return;
    if (press && press.drag) { cancelPress(); return; }
    if (UI.escape()) return;
    if (useSlot >= 0) { setUse(-1); return; }
    UI.paneEsc();
  }

  // ----------------------------------------------------------------
  // --------------------------- Lifecycle --------------------------
  // ----------------------------------------------------------------

  function init(c) {
    ctx = c;
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", cancelPress);
    document.addEventListener("contextmenu", onContext);
    document.addEventListener("wheel", onWheel, { passive: false });
    document.addEventListener("dragover", function (ev) { ev.preventDefault(); if (ev.dataTransfer) ev.dataTransfer.dropEffect = "none"; });
    document.addEventListener("drop", function (ev) { ev.preventDefault(); });
    document.addEventListener("gesturestart", function (ev) { ev.preventDefault(); });
    document.addEventListener("gesturechange", function (ev) { ev.preventDefault(); });
    document.addEventListener("keydown", onKey);
    window.addEventListener("keydown", blockKeys, true);
    window.addEventListener("mousedown", function (ev) { if (ev.button === 1 || ev.button === 3 || ev.button === 4) ev.preventDefault(); });
    window.addEventListener("mouseup", function (ev) { if (ev.button === 1 || ev.button === 3 || ev.button === 4) ev.preventDefault(); });
    window.addEventListener("blur", function () { closeMenu(); cancelPress(); });
    window.addEventListener("resize", function () { closeMenu(); });
    document.addEventListener("mouseout", function (ev) { if (!ev.relatedTarget) ptr.el = null; });
    $("game").addEventListener("pointerleave", function () { if (ptr.el === $("game")) ptr.el = null; });
    $("menu").addEventListener("click", pickMenu);
  }

  function update(nowMs) {
    if (!ctx) return;
    var s = S();
    var f = s.player.iface;
    if (useSlot >= 0 && (!s.player.inv[useSlot] || (f && (f.t === "bank" || f.t === "shop")))) setUse(-1);
    if (useSlot >= 0 && $("inv").children[useSlot] && !$("inv").children[useSlot].classList.contains("use")) {
      $("inv").children[useSlot].classList.add("use");
    }
    if (blocked()) {
      setHover("");
      return;
    }
    syncHover();
  }

  function getUseSlot() { return useSlot; }
  function getMenu() { return menu ? menu.entries.slice() : null; }

  return {
    init: init, update: update, closeMenu: closeMenu, useSlot: getUseSlot, menu: getMenu
  };
})();
// ==== src/ui/main.js ====
// ----------------------------------------------------------------
// --------------- Main: boot, loop, persistence, bridge ----------
// ----------------------------------------------------------------
// DESIGN.md 20: fixed 600 ms ticks from accumulated frame time, rAF drawing throttled to the fps pref,
// sliced catch-up after a gap or a load, the save envelope, and the hello/state/save/dock/reset bridge
// (localStorage when there is no bridge). Nothing but hello is posted before the first state arrives.
(function () {
  "use strict";

  var TICK_MS = 600;
  var MAX_FRAME_TICKS = 3;
  var CATCHUP_AFTER_MS = 1500;
  var CATCHUP_SLICE = 100;
  var CATCHUP_BUDGET_MS = 24;
  var CATCHUP_VEIL_TICKS = 1000;
  var CAP_HIDDEN = 24000;
  var CAP_CLOSED = 6000;
  var SUMMARY_MIN_TICKS = 100;
  var RESUME_SUMMARY_MIN_TICKS = 1000;
  var CHATLINE_MIN_TICKS = 3;
  var PERSIST_EVERY_MS = 30000;
  var SAVE_DEBOUNCE_MS = 1000;
  var HELLO_EVERY_MS = 500;
  var HELLO_TRIES = 20;
  var HELLO_SLOW_MS = 5000;
  var BOOT_WAIT_MS = 2500;
  var SAVE_BUDGET = 90000;
  var STORE_KEY = "orcadia-save";
  var BAD_KEY = "orcadia-save-bad";
  var BAD_SAVE = "Your save could not be read, so a new character started. The old save is kept as save_bad.";
  var IDLE_FPS = 15;

  var bridge = window.orca && typeof window.orca.postMessage === "function" &&
    typeof window.orca.onMessage === "function" ? window.orca : null;
  var state = Engine.createState(Date.now() >>> 0);
  var tickMs = TICK_MS;
  var booting = true;
  var remoteSeen = false;
  var hellos = 0;
  var helloTimer = 0;
  var job = null;            // catch-up: { left, total, cap, capped, kind: "load"|"hidden", sum }
  var last = 0;
  var lastWall = Date.now();
  var acc = 0;
  var drawAt = -1e9;
  var dirty = true;
  var busy = false;
  var dpr = window.devicePixelRatio || 1;
  var saveTimer = 0;
  var persistAt = Date.now();
  var persistTick = -1;
  var tooBig = false;
  var storeFailed = false;

  var ctx = {
    state: function () { return state; },
    act: function (fn) {
      if (booting || job) return false;
      var r = fn(state);
      dirty = true;
      return r;
    },
    persist: function () { persist(); },
    postDock: function (dock) { if (bridge && remoteSeen) bridge.postMessage({ command: "dock", dock: dock }); },
    reset: function () {
      swap(Engine.createState(Date.now() >>> 0));
      UI.reset();
      persist();
    },
    blocked: function () { return booting || !!job; }
  };

  // ----------------------------------------------------------------
  // ------------------------- Persistence --------------------------
  // ----------------------------------------------------------------

  // Wall time the simulation stands at: the last frame that advanced it, less frame leftovers and owed
  // catch-up ticks. While rAF is stalled (hidden dock) it stays put, so a pagehide save still owes that time.
  function simWall() {
    return lastWall - acc - (job ? job.left * TICK_MS : 0);
  }

  function envelope() {
    return JSON.stringify({ v: 1, t: simWall(), game: Engine.serialize(state), ui: UI.prefs(), chat: UI.chat() });
  }

  function chip() {
    UI.notSaving(tooBig || (bridge ? !remoteSeen : storeFailed));
  }

  function persist() {
    clearTimeout(saveTimer);
    saveTimer = 0;
    if (bridge && !remoteSeen) return;
    persistTick = state.tick;
    persistAt = Date.now();
    var text = "";
    try { text = envelope(); } catch (e) { text = ""; }
    tooBig = !text || text.length > SAVE_BUDGET;
    if (!tooBig) {
      if (bridge) bridge.postMessage({ command: "save", save: text });
      else {
        try { localStorage.setItem(STORE_KEY, text); storeFailed = false; } catch (e) { storeFailed = true; }
      }
    }
    chip();
  }

  function persistSoon() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persist, SAVE_DEBOUNCE_MS);
  }

  // A stored envelope string -> the envelope, or null.
  function parseEnv(text) {
    if (typeof text !== "string" || !text) return null;
    var o = null;
    try { o = JSON.parse(text); } catch (e) { return null; }
    return o && typeof o === "object" && !Array.isArray(o) && o.game && typeof o.game === "object" ? o : null;
  }

  // ----------------------------------------------------------------
  // ------------------------- State swaps --------------------------
  // ----------------------------------------------------------------

  // Cancels any catch-up, drops the old state's events and restarts the frame clock.
  function swap(next) {
    if (job) {
      job = null;
      UI.veil(null);
    }
    Engine.drainEvents(state);
    state = next;
    last = performance.now();
    lastWall = Date.now();
    acc = 0;
    dirty = true;
    Input.closeMenu();
    Render.reset();
    UI.resync();
  }

  function loadEnv(env, late) {
    swap(Engine.deserialize(env.game, Date.now() >>> 0));
    UI.setPrefs(env.ui);
    UI.setChat(env.chat);
    var owed = typeof env.t === "number" && isFinite(env.t) ? Math.floor(Math.max(0, Date.now() - env.t) / TICK_MS) : 0;
    startJob(owed, CAP_CLOSED, "load", env.t);
    if (late) UI.banner("Save restored", "good");
  }

  // ----------------------------------------------------------------
  // --------------------------- Catch-up ---------------------------
  // ----------------------------------------------------------------

  // savedAt: the loaded envelope's wall time, shown in the summary so an old save is easy to spot.
  function startJob(owed, cap, kind, savedAt) {
    var n = Math.min(owed, cap);
    if (!(n > 0)) return;
    job = { left: n, total: n, cap: cap, capped: owed > cap, over: Math.max(0, owed - cap), kind: kind, sum: null,
      savedAt: savedAt || 0 };
    Input.closeMenu();
    if (n > CATCHUP_VEIL_TICKS) UI.veil("catchup", 0);
  }

  function runJob() {
    var t0 = performance.now();
    while (job.left > 0 && performance.now() - t0 < CATCHUP_BUDGET_MS) {
      var n = Math.min(CATCHUP_SLICE, job.left);
      job.sum = job.sum ? Engine.catchUp(state, n, job.sum) : Engine.catchUp(state, n);
      job.left -= n;
      if (job.sum.frozen) job.left = 0;
    }
    if (job.total > CATCHUP_VEIL_TICKS) UI.veil("catchup", 100 * (job.total - job.left) / job.total);
    if (job.left <= 0) finishJob();
  }

  function changed(m) {
    return Object.keys(m.xp).length > 0 || Object.keys(m.items).length > 0 || Object.keys(m.kills).length > 0 ||
      Object.keys(m.couriered).length > 0 || Object.keys(m.dropped || {}).length > 0 || m.recalls > 0 || m.quests.length > 0 || !!m.stop ||
      (m.notes && m.notes.length > 0);
  }

  // Why a catch-up stopped early (Summary.frozen): a boss fight, or a region where time stands still.
  function pausedLine() {
    var st = Engine.status(state);
    if (st.foe) return "Time stood still while you were away: you're fighting " + st.foe.name + ".";
    return "Time stands still in " + (st.region ? st.region.name : "this place") + " while you're away.";
  }

  function skillName(k) {
    var sk = (Data.skills || []).filter(function (d) { return d.id === k; })[0];
    return sk ? sk.name : k;
  }

  // "While hidden (0:42): +6 Oak logs, +225 Woodcutting XP, Woodcutting level 1 → 4."
  function awayLine(m, kind) {
    var parts = [];
    Object.keys(m.items).forEach(function (id) {
      if (m.items[id] > 0 && Util.has(Data.items, id)) parts.push("+" + Util.fmtInt(m.items[id]) + " " + Data.items[id].name);
    });
    Object.keys(m.xp).forEach(function (k) {
      if (m.xp[k] > 0) parts.push("+" + Util.fmtInt(m.xp[k]) + " " + skillName(k) + " XP");
    });
    Object.keys(m.levels || {}).forEach(function (k) {
      parts.push(skillName(k) + " level " + m.levels[k][0] + " → " + m.levels[k][1]);
    });
    var head = (kind === "load" ? "While away (" : "While hidden (") + Util.fmtDur(m.ticks) + "): ";
    return head + (parts.length ? parts.join(", ") : m.doing) + ".";
  }

  function finishJob() {
    var j = job;
    job = null;
    if (j.total > CATCHUP_VEIL_TICKS) UI.veil(null);
    UI.resync();
    dirty = true;
    var m = j.sum;
    // Time past the cap was never played: it rests the adventurer instead (10.14; its line and banner follow).
    var rested = j.over > 0 ? Engine.rest(state, j.over) : 0;
    if (m && rested > 0) m.rested = rested;
    // Quest steps from the catch-up (their chat lines were folded away), then why it paused, if it skipped a minute.
    if (m && m.notes) m.notes.forEach(function (t) { UI.chatLine(t, "quest"); });
    if (m && m.frozen && j.total - m.ticks >= SUMMARY_MIN_TICKS) {
      m.paused = pausedLine();
      UI.chatLine(m.paused, "warn");
    }
    if (!m || !(changed(m) || rested > 0)) return;
    m.capped = j.capped;
    m.savedAt = j.savedAt;
    persistSoon();
    if (m.ticks >= (j.kind === "load" ? SUMMARY_MIN_TICKS : RESUME_SUMMARY_MIN_TICKS)) {
      UI.summary(m, j.cap);
    } else if (m.ticks >= CHATLINE_MIN_TICKS) {
      UI.chatLine(awayLine(m, j.kind), "game");
      var drops = Object.keys(m.xp).filter(function (k) { return m.xp[k] > 0; }).map(function (k) {
        return { type: "xp", skill: k, amt: m.xp[k] };
      });
      // The catch-up folded its level events into m.levels: one per skill, from -> to (toast, flash, fireworks).
      var lv = Object.keys(m.levels || {}).map(function (k) { return { type: "level", skill: k, lvl: m.levels[k][1], from: m.levels[k][0] }; });
      if (drops.length || lv.length) Render.onEvents(state, forRender(drops.concat(lv)), performance.now());
      if (lv.length) UI.onEvents(lv, performance.now());
    }
  }

  // ----------------------------------------------------------------
  // ---------------------------- Frames ----------------------------
  // ----------------------------------------------------------------

  // XP drops and level-up fireworks follow their Options toggles.
  function forRender(evs) {
    var p = UI.prefs();
    if (p.xpDrops && p.fireworks) return evs;
    return evs.filter(function (e) { return !((e.type === "xp" && !p.xpDrops) || (e.type === "level" && !p.fireworks)); });
  }

  function events(now) {
    var evs = Engine.drainEvents(state);
    if (!evs || !evs.length) return;
    dirty = true;
    Render.onEvents(state, forRender(evs), now);
    UI.onEvents(evs, now);
    for (var i = 0; i < evs.length; i++) {
      if (evs[i].type === "save") { persistSoon(); break; }
    }
  }

  function checkDpr() {
    var d = window.devicePixelRatio || 1;
    if (d === dpr) return;
    dpr = d;
    Icons.init(d);
    Sprites.flush();
    UI.applyLayout();
  }

  function draw(now) {
    var fps = busy ? UI.prefs().fps : IDLE_FPS;
    if (!dirty && now - drawAt < 1000 / fps - 2) return;
    drawAt = now;
    dirty = false;
    busy = !!Render.draw(state, Math.max(0, Math.min(1, acc / tickMs)), now);
    UI.update(now);
    Input.update(now);
  }

  function step(dt) {
    acc += dt;
    var n = 0;
    while (acc >= tickMs && n < MAX_FRAME_TICKS) {
      Engine.tick(state);
      acc -= tickMs;
      n++;
    }
    if (acc >= tickMs) acc = tickMs - 1;
    if (n) dirty = true;
  }

  function frame(now) {
    requestAnimationFrame(frame);
    var dt = Math.max(0, now - last);
    last = now;
    var wall = Date.now();
    var gap = wall >= lastWall ? Math.max(dt, wall - lastWall) : dt;
    lastWall = wall;
    checkDpr();
    if (booting) { draw(now); return; }
    if (job) runJob();
    else if (gap >= CATCHUP_AFTER_MS) {
      events(now);
      var owed = Math.floor((acc + gap) / tickMs);
      acc = owed > CAP_HIDDEN ? 0 : (acc + gap) - owed * tickMs;
      startJob(owed, CAP_HIDDEN, "hidden");
    } else step(dt);
    events(now);
    draw(now);
    if (!job && state.tick !== persistTick && wall - persistAt >= PERSIST_EVERY_MS) persist();
  }

  // ----------------------------------------------------------------
  // ---------------------------- Bridge ----------------------------
  // ----------------------------------------------------------------

  function endBoot() {
    if (!booting) return;
    booting = false;
    last = performance.now();
    lastWall = Date.now();
    acc = 0;
    dirty = true;
    if (!job || job.total <= CATCHUP_VEIL_TICKS) UI.veil(null);
  }

  function onMessage(m) {
    if (!m || typeof m !== "object") return;
    if (m.command === "state" && !remoteSeen) {
      remoteSeen = true;
      clearTimeout(helloTimer);
      var env = parseEnv(m.save);
      if (env) loadEnv(env, !booting);
      if (typeof m.dock === "string") UI.setDock(m.dock);
      endBoot();
      // The plugin keeps an unreadable save as save_bad; the first real save comes from play, not boot.
      if (typeof m.save === "string" && m.save && !env) { UI.banner(BAD_SAVE, "warn"); chip(); }
      else persist();
    } else if (m.command === "reset" && remoteSeen) {
      swap(Engine.createState(Date.now() >>> 0));
      UI.reset();
      UI.setPrefs({});
      UI.setDock("right");
      UI.banner("New character: defaults restored", "good");
      persist();
    }
  }

  function hello() {
    if (remoteSeen) return;
    bridge.postMessage({ command: "hello" });
    hellos++;
    helloTimer = setTimeout(hello, hellos < HELLO_TRIES ? HELLO_EVERY_MS : HELLO_SLOW_MS);
  }

  // True when a stored save could not be read (it is copied to BAD_KEY first).
  function loadLocal() {
    var text = null;
    try { text = localStorage.getItem(STORE_KEY); } catch (e) { storeFailed = true; }
    var env = parseEnv(text);
    if (env) loadEnv(env, false);
    if (env || !text) return false;
    try { localStorage.setItem(BAD_KEY, text); } catch (e) { /* the banner still tells */ }
    return true;
  }

  // ----------------------------------------------------------------
  // ----------------------------- Boot -----------------------------
  // ----------------------------------------------------------------

  function testHook() {
    if (window.__orcadiaTest !== true) return;
    window.__orcadia = {
      Engine: Engine, Data: Data, Icons: Icons, Render: Render, Layout: Layout, Music: Music,
      state: function () { return state; },
      ticks: function (n) {
        var k = Math.max(0, Math.min(100000, Math.floor(Number(n)) || 0));
        for (var i = 0; i < k; i++) {
          Engine.tick(state);
          events(performance.now());
        }
        dirty = true;
      },
      speed: function (k) { tickMs = TICK_MS / Math.max(0.1, Math.min(50, Number(k) || 1)); },
      layout: function () { return UI.layout(); },
      tileAt: function (cx, cy) { var p = Render.pick(cx, cy); return p ? { x: p.x, y: p.y } : null; },
      screenOf: function (ref) { return Render.refToClient(ref); },
      client: function (x, y) { return Render.tileToClient(x, y); },
      menu: function () { return Input.menu(); },
      persist: persist
    };
  }

  Icons.init(dpr);
  Render.init(document.getElementById("game"), document.getElementById("minimap"));
  UI.init(ctx);
  Input.init(ctx);
  UI.applyLayout();
  document.addEventListener("visibilitychange", function () { if (document.hidden) persist(); });
  window.addEventListener("pagehide", persist);
  testHook();
  if (bridge) {
    UI.veil("loading");
    chip();
    bridge.onMessage(onMessage);
    hello();
    setTimeout(function () {
      if (remoteSeen) return;
      endBoot();
      chip();
    }, BOOT_WAIT_MS);
  } else {
    var bad = loadLocal();
    endBoot();
    if (bad) UI.banner(BAD_SAVE, "warn");
    else persist();
  }
  last = performance.now();
  requestAnimationFrame(frame);
})();
})();
</script></body></html>
"""


class Orcadia(orca.script.ScriptPluginCapabilityBase):
    panel = None
    wrote_save = False
    saved_at = 0  # _stamp() of this panel's last save write

    def get_name(self):
        return "Orcadia"

    def get_default_config(self):
        # OrcaSlicer stores this when the plugin first loads and on "Restore defaults".
        return {"dock": "right", "restored": _stamp()}

    def execute(self):
        # The capability lives as long as the plugin, so a second run finds the open panel.
        if self.panel is not None and self.panel.is_open():
            if hasattr(self.panel, "show"):
                self.panel.show()
            return orca.ExecutionResult.success("Orcadia is already open.")
        dock = self._config().get("dock", "right")
        self.wrote_save = False
        ui = orca.host.ui
        if dock == "window" or not hasattr(ui, "create_dock_panel"):
            self.panel = ui.create_window(html=PAGE, title="Orcadia", width=960, height=640,
                                          on_message=self.on_message, on_close=self.on_close)
        else:
            self.panel = ui.create_dock_panel(html=PAGE, title="Orcadia", width=400, height=760,
                                              on_message=self.on_message, on_close=self.on_close,
                                              dock=dock if dock in DOCKS else "right")
        return orca.ExecutionResult.success("Orcadia is open. Adventure awaits.")

    # Called on the UI thread when the page posts.
    def on_message(self, message):
        if not isinstance(message, dict) or self.panel is None:
            return
        command = message.get("command")
        if command == "hello":
            config = self._config()
            save = config.get("save")
            if isinstance(save, str) and not _readable(save) and config.get("save_bad") != save:
                # The page can't read it and starts a new character: keep a copy before any save replaces it.
                config["save_bad"] = save
                self.save_config(json.dumps(config))
            dock = config.get("dock", "right")
            self.panel.post({"command": "state", "save": save if isinstance(save, str) else None,
                             "dock": dock if isinstance(dock, str) and dock in DOCK_CHOICES else "right"})
        elif command == "save":
            self._save(message.get("save"))
        elif command == "dock":
            dock = message.get("dock")
            if isinstance(dock, str) and dock in DOCK_CHOICES:
                config = self._config()
                config["dock"] = dock
                self.save_config(json.dumps(config))

    def _save(self, save):
        if not isinstance(save, str) or len(save) > MAX_SAVE_CHARS:
            return
        try:
            parsed = json.loads(save)
        except (ValueError, RecursionError):
            return
        if not isinstance(parsed, dict):
            return
        config = self._config()
        restored = config.pop("restored", None)
        if self.wrote_save and isinstance(restored, (int, float)) and restored > self.saved_at:
            # "Restore defaults" ran after this panel's last save: start over instead of writing the
            # old character back. An older stamp is a stale Config-tab copy saved back, not a restore.
            self.wrote_save = False
            self.panel.post({"command": "reset"})
            return
        # Kept as a string, so OrcaSlicer's pretty-printed config stays compact.
        config["save"] = save
        self.wrote_save = self.save_config(json.dumps(config)) is not False
        if self.wrote_save:
            self.saved_at = _stamp()

    def on_close(self):
        self.panel = None
        self.wrote_save = False

    def _config(self):
        try:
            config = json.loads(self.get_config())
        except (TypeError, ValueError, RecursionError):
            return {}
        return config if isinstance(config, dict) else {}


_last_stamp = [0]


def _stamp():
    """Wall-clock milliseconds, strictly increasing within this process, so a restore always
    stamps later than the save before it (same millisecond or a clock stepping back included)."""
    _last_stamp[0] = max(int(time.time() * 1000), _last_stamp[0] + 1)
    return _last_stamp[0]


def _readable(save):
    """True when the page can load this save: a JSON object holding a "game" object."""
    try:
        env = json.loads(save)
    except (ValueError, RecursionError):
        return False
    return isinstance(env, dict) and isinstance(env.get("game"), dict)


@orca.plugin
class OrcadiaPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(Orcadia)
