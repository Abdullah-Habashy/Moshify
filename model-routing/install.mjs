#!/usr/bin/env node
// Installer for the model-routing kit. Works on Windows, macOS, Linux (Node 18+).
//
//   node install.mjs --user                 install into ~/.claude (all projects)   [recommended]
//   node install.mjs --project <dir>        install into <dir>/.claude (one project)
//   add --dry-run to only print what would happen
//   node install.mjs --user --uninstall     remove hooks + kit files, restore overwritten files
//   node install.mjs --user --restore <id>  put back settings.json exactly as it was in backup <id>
//
// Every install writes a backup to <.claude>/routing-backups/<id>/ first.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const KIT = path.join(path.dirname(fileURLToPath(import.meta.url)), 'kit');
const args = process.argv.slice(2);
const has = (f) => args.includes(f);
const val = (f) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };
const DRY = has('--dry-run');

let scope, target, projectDir;
if (has('--project')) {
  projectDir = path.resolve(val('--project') || '.');
  scope = 'project'; target = path.join(projectDir, '.claude');
} else if (has('--user')) {
  scope = 'user'; target = path.join(os.homedir(), '.claude');
} else {
  console.log('Usage: node install.mjs --user | --project <dir>  [--dry-run] [--uninstall] [--restore <id>]');
  process.exit(1);
}

const SETTINGS = path.join(target, 'settings.json');
const BACKUPS = path.join(target, 'routing-backups');
const MARK = 'hooks/router.mjs';
const routerPath = scope === 'user'
  ? '$HOME/.claude/hooks/router.mjs'                 // expands in Git Bash and in PowerShell
  : '$CLAUDE_PROJECT_DIR/.claude/hooks/router.mjs';
const cmd = (mode) => `node "${routerPath}" ${mode}`;
const HOOKS = {
  SessionStart: [{ hooks: [{ type: 'command', command: cmd('session'), timeout: 5 }] }],
  PreToolUse: [{ matcher: 'Agent|Task', hooks: [{ type: 'command', command: cmd('pre'), timeout: 5 }] }],
  PostToolUse: [{ matcher: 'Agent|Task', hooks: [{ type: 'command', command: cmd('post'), timeout: 5 }] }],
};

const say = (...m) => console.log(...m);
const act = (desc, fn) => { say((DRY ? '[dry-run] ' : '') + desc); if (!DRY) fn(); };

function readJson(p) {
  if (!fs.existsSync(p)) return {};
  const txt = fs.readFileSync(p, 'utf8');
  try { return JSON.parse(txt); }
  catch (e) { say(`ERROR: ${p} is not valid JSON (${e.message}). Fix it first; nothing was changed.`); process.exit(2); }
}

function kitFiles(dir = KIT, rel = '') {
  const out = [];
  for (const e of fs.readdirSync(path.join(dir, rel), { withFileTypes: true })) {
    const r = path.join(rel, e.name);
    if (e.isDirectory()) out.push(...kitFiles(dir, r)); else out.push(r);
  }
  return out;
}

const isOurHook = (h) => typeof h?.command === 'string' && h.command.replace(/\\/g, '/').includes(MARK);

function stripOurHooks(settings) {
  if (!settings.hooks) return 0;
  let removed = 0;
  for (const ev of Object.keys(settings.hooks)) {
    const groups = settings.hooks[ev];
    if (!Array.isArray(groups)) continue;
    for (const g of groups) {
      const before = (g.hooks || []).length;
      g.hooks = (g.hooks || []).filter((h) => !isOurHook(h));
      removed += before - g.hooks.length;
    }
    settings.hooks[ev] = groups.filter((g) => (g.hooks || []).length);
    if (!settings.hooks[ev].length) delete settings.hooks[ev];
  }
  if (!Object.keys(settings.hooks).length) delete settings.hooks;
  return removed;
}

function conflicts(settings) {
  const notes = [];
  const plugins = JSON.stringify(settings.enabledPlugins || {});
  if (/model-router/i.test(plugins)) notes.push('claude-model-router-hook plugin is enabled — disable it to avoid double routing.');
  for (const f of ['model-router.json', 'hooks/model-router.json']) {
    if (fs.existsSync(path.join(target, f))) notes.push(`Found ${f} from another router; it is not used by this kit.`);
  }
  const env = settings.env || {};
  for (const k of ['CLAUDE_CODE_SUBAGENT_MODEL', 'CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE']) {
    if (env[k] || process.env[k]) notes.push(`${k} is set — it overrides per-subagent model/effort choices.`);
  }
  const other = JSON.stringify(settings.hooks || {});
  if (/Agent\|Task|"matcher":\s*"Agent"/.test(other.replace(/hooks\/router\.mjs[^"]*"/g, ''))) {
    notes.push('Another hook already matches the Agent tool — check it does not rewrite subagent models.');
  }
  return notes;
}

function install() {
  const settings = readJson(SETTINGS);
  const id = new Date().toISOString().replace(/[:.]/g, '-');
  const bdir = path.join(BACKUPS, id);
  const manifest = { id, scope, target, created: [], overwritten: [], settingsExisted: fs.existsSync(SETTINGS) };

  say(`Installing model-routing kit (${scope}) into ${target}`);
  const others = JSON.parse(JSON.stringify(settings)); stripOurHooks(others);
  for (const n of conflicts(others)) say('  WARNING: ' + n);
  const ours = installedBefore();

  act(`Backup -> ${bdir}`, () => {
    fs.mkdirSync(bdir, { recursive: true });
    if (manifest.settingsExisted) fs.copyFileSync(SETTINGS, path.join(bdir, 'settings.json'));
  });

  for (const rel of kitFiles()) {
    const src = path.join(KIT, rel), dst = path.join(target, rel);
    if (fs.existsSync(dst)) {
      if (fs.readFileSync(dst).equals(fs.readFileSync(src))) continue;
      if (ours.has(rel)) {                       // our own older copy: just update it
        act(`  update ${rel}`, () => fs.copyFileSync(src, dst));
        continue;
      }
      act(`  overwrite ${rel} (old copy kept in backup)`, () => {
        fs.mkdirSync(path.dirname(path.join(bdir, 'files', rel)), { recursive: true });
        fs.copyFileSync(dst, path.join(bdir, 'files', rel));
      });
      manifest.overwritten.push(rel);
    } else manifest.created.push(rel);
    act(`  copy ${rel}`, () => { fs.mkdirSync(path.dirname(dst), { recursive: true }); fs.copyFileSync(src, dst); });
  }

  stripOurHooks(settings);                       // idempotent re-install
  settings.hooks ??= {};
  for (const [ev, groups] of Object.entries(HOOKS)) settings.hooks[ev] = [...(settings.hooks[ev] || []), ...groups];
  act(`Merge 3 hooks into ${SETTINGS} (other settings untouched)`, () => {
    fs.writeFileSync(SETTINGS, JSON.stringify(settings, null, 2) + '\n');
    fs.writeFileSync(path.join(bdir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  });

  if (scope === 'project') {
    const gi = path.join(projectDir, '.gitignore');
    for (const line of ['.claude/routing/state/', '.claude/routing-backups/']) {
      const cur = fs.existsSync(gi) ? fs.readFileSync(gi, 'utf8') : '';
      if (!cur.split(/\r?\n/).includes(line)) act(`Add ${line} to .gitignore`, () => fs.appendFileSync(gi, (cur && !cur.endsWith('\n') ? '\n' : '') + line + '\n'));
    }
  }
  say(`\nDone. Backup id: ${id}\nStart a NEW Claude Code session, then run /routing to check status.`);
}

// Files a previous run of this installer put in place (so not user originals).
function installedBefore() {
  const set = new Set();
  if (!fs.existsSync(BACKUPS)) return set;
  for (const id of fs.readdirSync(BACKUPS)) {
    const m = path.join(BACKUPS, id, 'manifest.json');
    if (!fs.existsSync(m)) continue;
    const man = JSON.parse(fs.readFileSync(m, 'utf8'));
    for (const r of [...man.created, ...man.overwritten]) set.add(r);
  }
  return set;
}

// The pre-kit original of a file = the OLDEST backup that saved it (later
// re-installs see the kit's own copy and save nothing).
function originalBackup(rel) {
  if (!fs.existsSync(BACKUPS)) return null;
  for (const id of fs.readdirSync(BACKUPS).sort()) {
    const m = path.join(BACKUPS, id, 'manifest.json');
    if (!fs.existsSync(m)) continue;
    const man = JSON.parse(fs.readFileSync(m, 'utf8'));
    const saved = path.join(BACKUPS, id, 'files', rel);
    if (man.overwritten.includes(rel) && fs.existsSync(saved)) return { id, saved };
  }
  return null;
}

function uninstall() {
  const settings = readJson(SETTINGS);
  const n = stripOurHooks(settings);
  const first = fs.existsSync(BACKUPS) && fs.readdirSync(BACKUPS).sort()
    .map((id) => path.join(BACKUPS, id, 'manifest.json')).find((m) => fs.existsSync(m));
  const createdByUs = first && JSON.parse(fs.readFileSync(first, 'utf8')).settingsExisted === false;
  if (n && createdByUs && !Object.keys(settings).length) act(`Remove ${SETTINGS} (it did not exist before the kit)`, () => fs.unlinkSync(SETTINGS));
  else if (n) act(`Remove ${n} routing hook entries from ${SETTINGS}`, () => fs.writeFileSync(SETTINGS, JSON.stringify(settings, null, 2) + '\n'));
  else say('No routing hooks found in settings.json (nothing to change there).');
  for (const rel of kitFiles()) {
    const dst = path.join(target, rel);
    const orig = originalBackup(rel);
    if (orig) act(`  restore ${rel} from backup ${orig.id}`, () => fs.copyFileSync(orig.saved, dst));
    else if (fs.existsSync(dst)) act(`  remove ${rel}`, () => fs.unlinkSync(dst));
  }
  const state = path.join(target, 'routing', 'state');      // runtime log + flags only
  if (fs.existsSync(state)) act('  remove routing/state (log + flags)', () => fs.rmSync(state, { recursive: true }));
  for (const d of ['skills/routing', 'skills', 'hooks', 'routing', 'agents']) { // only if now empty
    const p = path.join(target, d);
    if (!DRY) { try { if (fs.readdirSync(p).length === 0) fs.rmdirSync(p); } catch {} }
  }
  say('\nUninstalled. Backups kept in ' + BACKUPS + ' (delete manually if not needed).');
}

function restore(id) {
  const src = path.join(BACKUPS, id, 'settings.json');
  const m = path.join(BACKUPS, id, 'manifest.json');
  if (!fs.existsSync(m)) { say('No such backup: ' + id); process.exit(1); }
  const man = JSON.parse(fs.readFileSync(m, 'utf8'));
  if (man.settingsExisted) act(`Restore ${SETTINGS} from ${id}`, () => fs.copyFileSync(src, SETTINGS));
  else act(`settings.json did not exist before ${id}; removing it`, () => fs.existsSync(SETTINGS) && fs.unlinkSync(SETTINGS));
  say('Settings restored. Run --uninstall too if you also want the kit files removed.');
}

if (has('--restore')) restore(val('--restore'));
else if (has('--uninstall')) uninstall();
else install();
