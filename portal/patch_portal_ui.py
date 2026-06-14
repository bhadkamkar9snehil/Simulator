#!/usr/bin/env python3
"""
patch_portal_ui.py
Run from the same directory as portal_app.py:
    python patch_portal_ui.py

Creates portal_app.py.bak then rewrites the <style> block and
two small HTML snippets in-place with an industrial 3D-button theme.
No external dependencies – pure stdlib.
"""

import re
import shutil
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "portal_app.py"

# ── Safety ──────────────────────────────────────────────────────────────────
if not TARGET.exists():
    raise FileNotFoundError(f"Cannot find {TARGET}")

shutil.copy(TARGET, TARGET.with_suffix(".py.bak"))
print(f"Backup written → {TARGET.with_suffix('.py.bak')}")

src = TARGET.read_text(encoding="utf-8")

# ── New CSS (replaces everything between <style> … </style>) ─────────────────
NEW_CSS = r"""
/* ═══════════════════════════════════════════════════════════════════
   INDUSTRIAL FORGE UI  —  dual-theme  (light: Solarised-lite  /
   dark: warm grey-orange-yellow)
   3-D bevelled buttons via layered box-shadows; no border-radius
   on structural elements; monospace accent font.
═══════════════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow+Condensed:wght@400;600;700;900&family=Barlow:wght@400;600;700&display=swap');

/* ── Tokens ──────────────────────────────────────────────────────── */
:root {
  /* LIGHT (solarised-lite) */
  --bg:        #fdf6e3;
  --bg2:       #eee8d5;
  --bg3:       #e4ddc8;
  --ink:       #073642;
  --ink2:      #586e75;
  --muted:     #839496;
  --card:      #fdf6e3;
  --line:      #b8af94;
  --brand:     #cb4b16;   /* solarised orange */
  --brand-hi:  #dc322f;   /* red accent */
  --ok:        #2aa198;   /* cyan */
  --ok-hi:     #268bd2;
  --warn:      #b58900;   /* yellow */
  --bad:       #dc322f;
  --blue:      #268bd2;
  --dark:      #002b36;
  --term-bg:   #002b36;
  --term-ink:  #93a1a1;
  --term-hi:   #eee8d5;

  /* 3-D button shadow stacks (light) */
  --btn-face:       #e8e0c8;
  --btn-hi:         #f5edd8;
  --btn-sh:         #a09880;
  --btn-deep:       #6e6050;
  --btn-3d: inset 0 1px 0 var(--btn-hi),
            inset 0 -1px 0 var(--btn-deep),
            inset 1px 0 0 var(--btn-hi),
            inset -1px 0 0 var(--btn-sh),
            0 3px 6px rgba(0,0,0,.28),
            0 1px 2px rgba(0,0,0,.18);
  --btn-3d-press: inset 0 2px 4px rgba(0,0,0,.35),
                  0 1px 0 rgba(255,255,255,.15);

  --header-bg:  linear-gradient(180deg,#073642 0%,#002b36 100%);
  --tab-active-bg: #cb4b16;
  --shadow:     0 4px 14px rgba(7,54,66,.18), 0 1px 3px rgba(7,54,66,.10);
}

[data-theme="dark"] {
  --bg:        #1c1a17;
  --bg2:       #242018;
  --bg3:       #2e2a22;
  --ink:       #ede0c4;
  --ink2:      #c8b89a;
  --muted:     #8a7d68;
  --card:      #2a2620;
  --line:      #3e3828;
  --brand:     #e8870a;
  --brand-hi:  #ffaa33;
  --ok:        #44c49a;
  --ok-hi:     #5ee0a8;
  --warn:      #f0c040;
  --bad:       #e05050;
  --blue:      #5ba8e8;
  --dark:      #0e0c0a;
  --term-bg:   #0e0c0a;
  --term-ink:  #a89878;
  --term-hi:   #ffe8a0;

  --btn-face:   #3a342a;
  --btn-hi:     #504840;
  --btn-sh:     #1a1610;
  --btn-deep:   #0e0a06;
  --btn-3d: inset 0 1px 0 var(--btn-hi),
            inset 0 -1px 0 var(--btn-deep),
            inset 1px 0 0 var(--btn-hi),
            inset -1px 0 0 var(--btn-sh),
            0 3px 8px rgba(0,0,0,.55),
            0 1px 2px rgba(0,0,0,.35);
  --btn-3d-press: inset 0 2px 5px rgba(0,0,0,.6),
                  0 1px 0 rgba(255,255,255,.05);

  --header-bg: linear-gradient(180deg,#2a2218 0%,#1a1510 100%);
  --tab-active-bg: #e8870a;
  --shadow: 0 4px 18px rgba(0,0,0,.55), 0 1px 4px rgba(0,0,0,.35);
}

/* ── Reset / base ────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html, body {
  height: 100%; margin: 0; overflow: hidden;
  font-family: 'Barlow', sans-serif;
  font-size: 14px;
  color: var(--ink);
  background: var(--bg);
  line-height: 1.45;
}

/* ── App shell ───────────────────────────────────────────────────── */
.app {
  height: 100vh;
  display: grid;
  grid-template-rows: 56px 50px 1fr;
  gap: 0;
}

/* ── Header ──────────────────────────────────────────────────────── */
.mainHeader {
  background: var(--header-bg);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  border-bottom: 3px solid var(--brand);
  box-shadow: 0 3px 12px rgba(0,0,0,.4);
  position: relative;
  /* subtle rivet texture */
  background-image: var(--header-bg),
    repeating-linear-gradient(90deg,
      transparent 0, transparent 39px,
      rgba(255,255,255,.03) 39px, rgba(255,255,255,.03) 40px);
}

.brandTitle {
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 20px;
  font-weight: 900;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: #fff;
}
.brandSub {
  font-size: 10px;
  color: rgba(255,255,255,.55);
  font-family: 'Share Tech Mono', monospace;
  letter-spacing: .04em;
}
.headerPills {
  display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end;
}

/* Status chips */
.chip, .pill {
  display: inline-flex; align-items: center; gap: 4px;
  border: 1px solid rgba(255,255,255,.22);
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.85);
  padding: 3px 7px;
  font-size: 10px;
  font-family: 'Share Tech Mono', monospace;
  letter-spacing: .05em;
  clip-path: polygon(6px 0%,100% 0%,calc(100% - 6px) 100%,0% 100%);
}
.pill {
  border-color: var(--line);
  background: var(--bg2);
  color: var(--ink2);
  clip-path: none;
}
.appChromeHint {
  display: inline-flex; align-items: center;
  background: rgba(203,75,22,.20);
  border: 1px solid var(--brand);
  color: var(--brand-hi);
  padding: 3px 8px;
  font-size: 10px;
  font-family: 'Share Tech Mono', monospace;
}

/* Theme toggle button — top-right */
#themeToggle {
  background: transparent;
  border: 1px solid rgba(255,255,255,.3);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  padding: 3px 8px;
  font-family: 'Share Tech Mono', monospace;
  margin-left: 8px;
  letter-spacing: .04em;
  transition: background .15s;
}
#themeToggle:hover { background: rgba(255,255,255,.1); }

/* ── Tab bar ─────────────────────────────────────────────────────── */
.appTabs {
  display: flex;
  gap: 2px;
  align-items: stretch;
  padding: 6px 14px;
  background: var(--bg2);
  border-bottom: 2px solid var(--line);
}
.appTabs button {
  min-width: 108px;
  border: 1px solid var(--line);
  background: var(--btn-face);
  color: var(--ink);
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  cursor: pointer;
  padding: 5px 12px;
  box-shadow: var(--btn-3d);
  transition: box-shadow .08s, transform .08s, background .1s;
  position: relative;
  top: 0;
}
.appTabs button:hover {
  background: var(--btn-hi);
}
.appTabs button:active {
  box-shadow: var(--btn-3d-press);
  top: 2px;
}
.appTabs button.active {
  background: var(--tab-active-bg);
  color: #fff;
  border-color: var(--brand);
  box-shadow: var(--btn-3d-press), 0 0 6px rgba(203,75,22,.4);
  top: 1px;
}

/* ── Main area ───────────────────────────────────────────────────── */
.appMain {
  min-height: 0; overflow: hidden; padding: 10px 14px 12px;
  background: var(--bg);
}
.panel { display: none; height: 100%; min-height: 0; }
.panel.active { display: block; }
.panelScroller {
  height: 100%; overflow: auto; padding: 0 0 4px;
  scrollbar-width: thin;
  scrollbar-color: var(--brand) var(--bg2);
}

/* ── Cards ───────────────────────────────────────────────────────── */
.card, .softCard {
  background: var(--card);
  border: 1px solid var(--line);
  padding: 12px;
  min-width: 0;
  /* Flat top, subtle 3-D ledge on bottom */
  box-shadow: 0 3px 0 var(--line), var(--shadow);
}
.card h2, .softCard h2, .softCard h3,
.card h3 {
  margin: 0 0 8px;
  font-family: 'Barlow Condensed', sans-serif;
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
  font-size: 13px;
  color: var(--ink);
  border-bottom: 1px solid var(--line);
  padding-bottom: 5px;
}

/* ── Status / terminal boxes ─────────────────────────────────────── */
.statusBox {
  background: var(--term-bg);
  color: var(--term-ink);
  padding: 10px;
  white-space: pre-wrap;
  overflow: auto;
  font-family: 'Share Tech Mono', monospace;
  font-size: 11px;
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: inset 0 2px 8px rgba(0,0,0,.5);
  line-height: 1.6;
}
.statusBox .hi { color: var(--term-hi); }

/* ── Layouts ─────────────────────────────────────────────────────── */
.layoutGenerate {
  height: 100%;
  display: grid;
  grid-template-columns: 168px 1fr;
  gap: 12px;
  min-height: 0;
}
.leftRail {
  display: grid;
  grid-template-rows: minmax(170px,auto) minmax(170px,auto) 1fr;
  gap: 10px;
  min-height: 0;
}
.filesPanel {
  height: 100%; min-height: 0;
  display: grid; grid-template-rows: auto 1fr auto; gap: 10px;
}
.tableWrap {
  overflow: auto; border: 1px solid var(--line);
  background: var(--card); min-height: 0;
  box-shadow: inset 0 2px 4px rgba(0,0,0,.12);
}
.filesPanel .tableWrap { height: 100%; }
.smallPreview { max-height: 120px; overflow: auto; }

.layoutTags {
  height: 100%; display: grid;
  grid-template-rows: auto auto 1fr; gap: 10px; min-height: 0;
}
.commonRun {
  display: grid;
  grid-template-columns: repeat(6,minmax(90px,1fr)) auto;
  gap: 10px; align-items: end;
}
.protocolTop { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.protocolBody { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; min-height: 0; }
.tagPanel { min-height: 0; display: grid; grid-template-rows: auto 1fr; }
.tagPanel .tableWrap { min-height: 0; }

/* API panel */
.apiLayout {
  height: 100%; display: grid; grid-template-columns: 148px 1fr;
  gap: 10px; min-height: 0;
}
.apiMenu {
  background: var(--dark);
  color: var(--ink2);
  border: 1px solid var(--line);
  padding: 10px; overflow: auto;
  box-shadow: var(--shadow);
}
.apiMenu h3 {
  margin: 0 0 8px; color: var(--brand);
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 13px; font-weight: 900; letter-spacing: .08em;
  text-transform: uppercase; border-bottom: 1px solid var(--line);
  padding-bottom: 5px;
}
.apiMenu button {
  display: block; width: 100%; text-align: left;
  background: transparent; color: var(--muted);
  border: 0; padding: 7px 8px; margin: 2px 0;
  cursor: pointer; font-family: 'Share Tech Mono', monospace;
  font-size: 11px; letter-spacing: .04em;
  border-left: 2px solid transparent;
  transition: color .12s, border-color .12s;
}
.apiMenu button.active,
.apiMenu button:hover {
  color: var(--brand-hi);
  border-left-color: var(--brand);
  background: rgba(203,75,22,.08);
}
.apiStage {
  background: var(--dark); border: 1px solid var(--line);
  min-height: 0; overflow: hidden;
  box-shadow: inset 0 2px 10px rgba(0,0,0,.4);
}
.subpanel { display: none; height: 100%; min-height: 0; overflow: auto; padding: 10px; }
.subpanel.active { display: block; }
.apiFrame {
  height: 100%; width: 100%; min-height: 520px;
  border: 0; background: var(--dark);
}

/* ── Grid helpers ────────────────────────────────────────────────── */
.grid { display: grid; grid-template-columns: repeat(12,1fr); gap: 10px; }
.full { grid-column: 1/-1; }
.half { grid-column: span 6; }
.third { grid-column: span 4; }
.twoThird { grid-column: span 8; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.right { justify-content: flex-end; }
.muted { color: var(--muted); font-size: 11px; line-height: 1.45; }

/* ── Form elements ───────────────────────────────────────────────── */
label {
  display: block;
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 11px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--ink2);
  margin: 6px 0 2px;
}
input, select, textarea {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--bg2);
  color: var(--ink);
  padding: 6px 8px;
  outline: none;
  font-family: 'Share Tech Mono', monospace;
  font-size: 12px;
  box-shadow: inset 0 2px 3px rgba(0,0,0,.15);
  transition: border-color .12s, box-shadow .12s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--brand);
  box-shadow: inset 0 2px 3px rgba(0,0,0,.15), 0 0 0 2px rgba(203,75,22,.25);
}
textarea {
  min-height: 90px;
  font-family: 'Share Tech Mono', monospace;
  resize: vertical;
}
input[type="checkbox"] { width: auto; accent-color: var(--brand); }
input[readonly] { opacity: .65; cursor: default; }

/* ── 3-D Buttons ─────────────────────────────────────────────────── */
.btn, button.btn {
  border: 1px solid var(--line);
  background: var(--btn-face);
  color: var(--ink);
  padding: 7px 12px;
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 12px; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase;
  cursor: pointer; text-decoration: none; display: inline-block;
  box-shadow: var(--btn-3d);
  position: relative; top: 0;
  transition: box-shadow .08s, top .08s, background .1s;
  white-space: nowrap;
}
.btn:hover, button.btn:hover {
  background: var(--btn-hi);
  color: var(--ink);
}
.btn:active, button.btn:active {
  box-shadow: var(--btn-3d-press);
  top: 2px;
}

/* Colour variants */
.btn.primary, button.btn.primary {
  background: var(--brand);
  border-color: color-mix(in srgb,var(--brand) 70%,#000 30%);
  color: #fff;
  --btn-hi: color-mix(in srgb,var(--brand) 80%,#fff 20%);
  --btn-sh: color-mix(in srgb,var(--brand) 70%,#000 30%);
  --btn-deep: color-mix(in srgb,var(--brand) 50%,#000 50%);
}
.btn.blue, button.btn.blue {
  background: var(--blue);
  border-color: color-mix(in srgb,var(--blue) 70%,#000 30%);
  color: #fff;
  --btn-hi: color-mix(in srgb,var(--blue) 80%,#fff 20%);
  --btn-sh: color-mix(in srgb,var(--blue) 70%,#000 30%);
  --btn-deep: color-mix(in srgb,var(--blue) 50%,#000 50%);
}
.btn.ok, button.btn.ok {
  background: var(--ok);
  border-color: color-mix(in srgb,var(--ok) 70%,#000 30%);
  color: #fff;
  --btn-hi: color-mix(in srgb,var(--ok) 80%,#fff 20%);
  --btn-sh: color-mix(in srgb,var(--ok) 70%,#000 30%);
  --btn-deep: color-mix(in srgb,var(--ok) 50%,#000 50%);
}
.btn.bad, button.btn.bad {
  background: var(--bad);
  border-color: color-mix(in srgb,var(--bad) 70%,#000 30%);
  color: #fff;
  --btn-hi: color-mix(in srgb,var(--bad) 80%,#fff 20%);
  --btn-sh: color-mix(in srgb,var(--bad) 70%,#000 30%);
  --btn-deep: color-mix(in srgb,var(--bad) 50%,#000 50%);
}
.btn.small, button.btn.small {
  font-size: 10px; padding: 4px 7px;
}

/* ── Tables ──────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td {
  border-bottom: 1px solid var(--line);
  padding: 6px 8px;
  text-align: left; vertical-align: top;
}
th {
  background: var(--bg3);
  color: var(--ink2);
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 10px; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase;
  position: sticky; top: 0; z-index: 1;
  border-bottom: 2px solid var(--brand);
}
tr:nth-child(even) td { background: rgba(0,0,0,.04); }
tr:hover td { background: rgba(203,75,22,.06); }

/* ── Control grid (launcher) ─────────────────────────────────────── */
.controlGrid {
  display: grid;
  grid-template-columns: repeat(3,minmax(180px,1fr));
  gap: 10px;
}
.controlBlock {
  background: var(--bg2);
  border: 1px solid var(--line);
  padding: 12px;
  box-shadow: 0 2px 0 var(--line);
}
.controlBlock h3 {
  margin: 0 0 8px;
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 12px; font-weight: 800; letter-spacing: .08em;
  text-transform: uppercase; color: var(--brand);
  border-bottom: 1px solid var(--line); padding-bottom: 4px;
}

/* ── Scrollbars ──────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: var(--bg2); }
::-webkit-scrollbar-thumb { background: var(--muted); }
::-webkit-scrollbar-thumb:hover { background: var(--brand); }

/* ── Responsive ──────────────────────────────────────────────────── */
@media (max-width: 1050px) {
  .app { grid-template-rows: auto auto 1fr; }
  .mainHeader { display: block; padding: 8px; }
  .layoutGenerate, .apiLayout { grid-template-columns: 1fr; }
  .leftRail { grid-template-rows: auto; }
  .commonRun, .protocolTop, .protocolBody, .controlGrid { grid-template-columns: 1fr; }
  .half, .third, .twoThird { grid-column: 1/-1; }
  .headerPills { justify-content: flex-start; margin-top: 6px; }
}
"""

# ── Theme toggle button injection into header HTML ───────────────────────────
# We'll add it to the headerPills div.  The JS below handles the toggle.

NEW_THEME_JS = r"""
// ── Theme toggle ──────────────────────────────────────────────────
(function(){
  const root = document.documentElement;
  const btn  = document.getElementById('themeToggle');
  const key  = 'iforge_theme';
  function apply(t){ root.setAttribute('data-theme', t); btn.textContent = t==='dark' ? '☀ LIGHT' : '⬛ DARK'; }
  apply(localStorage.getItem(key) || 'light');
  btn.addEventListener('click', function(){
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    localStorage.setItem(key, next); apply(next);
  });
})();
"""

# ────────────────────────────────────────────────────────────────────────────
# 1.  Replace <style> … </style>
# ────────────────────────────────────────────────────────────────────────────
patched = re.sub(
    r'<style>.*?</style>',
    '<style>' + NEW_CSS + '</style>',
    src,
    count=1,
    flags=re.DOTALL,
)

# ────────────────────────────────────────────────────────────────────────────
# 2.  Add theme-toggle button to headerPills div
# ────────────────────────────────────────────────────────────────────────────
patched = patched.replace(
    '<span class=\\"appChromeHint\\">Application Mode</span></div>',
    '<span class=\\"appChromeHint\\">Application Mode</span>'
    '<button id=\\"themeToggle\\">⬛ DARK</button></div>',
    1,
)

# ────────────────────────────────────────────────────────────────────────────
# 3.  Inject theme JS just before </body>
# ────────────────────────────────────────────────────────────────────────────
# We want it after the existing <script> block so all DOM is ready.
# The existing template ends with: …loadLauncher();...setInterval(…);\n</script>\n</body>
CLOSE_MARKER = '\n</script>\n</body></html>'
JS_INJECT = (
    '\n</script>\n<script>\n'
    + NEW_THEME_JS
    + '\n</script>\n</body></html>'
)
if CLOSE_MARKER in patched:
    patched = patched.replace(CLOSE_MARKER, JS_INJECT, 1)
    print("Theme JS injected.")
else:
    print("WARNING: could not find JS injection point — theme toggle JS skipped.")

# ────────────────────────────────────────────────────────────────────────────
# 4.  Write back
# ────────────────────────────────────────────────────────────────────────────
TARGET.write_text(patched, encoding="utf-8")
print(f"Patched → {TARGET}")
print("Done. Restart the portal server to see the new UI.")
