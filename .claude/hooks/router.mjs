#!/usr/bin/env node
// Model-routing hook + control CLI. No dependencies. Fail-open: any internal
// error exits 0 silently so Claude Code is never blocked by this script.
//
// Hook modes (read the hook event JSON on stdin):
//   session  SessionStart  -> inject routing policy (unless routing is OFF)
//   pre      PreToolUse    -> log the requested route; block Fable unless allowed;
//                             block nested delegation from inside a subagent
//   post     PostToolUse   -> log the model that actually ran, tokens, duration
// CLI modes:
//   status [N] | on | off | fable on|off | log [N] | clear-log

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = path.resolve(HERE, '..');                 // the .claude dir this kit lives in
const ROUTING = path.join(BASE, 'routing');
const STATE = path.join(ROUTING, 'state');
const LOG = path.join(STATE, 'log.jsonl');
const OFF_FLAG = path.join(STATE, 'OFF');
const FABLE_FLAG = path.join(STATE, 'ALLOW_FABLE');
const POLICY = path.join(ROUTING, 'policy.md');
const MAX_LOG_BYTES = 1_000_000;
const ROUTED = new Set(['scout', 'worker', 'render-check', 'deep-reviewer', 'art-director']);

const exists = (p) => { try { return fs.existsSync(p); } catch { return false; } };
const isOff = () => exists(OFF_FLAG) || process.env.CLAUDE_ROUTING === 'off';
const fableAllowed = () => exists(FABLE_FLAG) || process.env.CLAUDE_ROUTING_ALLOW_FABLE === '1';

function readStdin() {
  try { return JSON.parse(fs.readFileSync(0, 'utf8') || '{}'); } catch { return {}; }
}

let SID = '';
function log(rec) {
  try {
    fs.mkdirSync(STATE, { recursive: true });
    if (exists(LOG) && fs.statSync(LOG).size > MAX_LOG_BYTES) fs.renameSync(LOG, LOG + '.old');
    fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), sid: SID, ...rec }) + '\n');
  } catch { /* never fail */ }
}

// Model declared in a subagent's frontmatter (project dirs walking up, then user dir).
function frontmatterModel(agentType, cwd) {
  if (!agentType) return null;
  const dirs = [];
  let d = cwd || process.cwd();
  for (let i = 0; i < 12; i++) {
    dirs.push(path.join(d, '.claude', 'agents'));
    const up = path.dirname(d); if (up === d) break; d = up;
  }
  dirs.push(path.join(os.homedir(), '.claude', 'agents'), path.join(BASE, 'agents'));
  for (const dir of dirs) {
    const f = path.join(dir, `${agentType}.md`);
    if (!exists(f)) continue;
    try {
      const fm = fs.readFileSync(f, 'utf8').split(/^---\s*$/m)[1] || '';
      const m = fm.match(/^model:\s*(\S+)/m);
      const e = fm.match(/^effort:\s*(\S+)/m);
      return { model: m ? m[1] : 'inherit', effort: e ? e[1] : null };
    } catch { return null; }
  }
  return null;
}

function emit(obj) { process.stdout.write(JSON.stringify(obj)); }

function hookSession(ev) {
  if (isOff()) { log({ ev: 'session', routing: 'off' }); return; }
  let policy = '';
  try { policy = fs.readFileSync(POLICY, 'utf8'); } catch { return; }
  log({ ev: 'session', routing: 'on', source: ev.source || '' });
  emit({ hookSpecificOutput: { hookEventName: 'SessionStart', additionalContext: policy } });
}

function deny(reason) {
  emit({ hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'deny', permissionDecisionReason: reason } });
}

function hookPre(ev) {
  if (!ev.tool_input) return;                            // malformed event: ignore
  const ti = ev.tool_input;
  const type = ti.subagent_type || 'general-purpose';
  const fm = frontmatterModel(type, ev.cwd);
  const reqModel = ti.model || (fm && fm.model) || 'inherit';
  const reqEffort = ti.effort || (fm && fm.effort) || (ev.effort && ev.effort.level) || '';
  const source = ti.model ? 'call' : fm ? 'agent-file' : 'inherit';
  const base = { ev: 'pre', agent: type, req_model: reqModel, req_effort: reqEffort, source,
                 routed: ROUTED.has(type), nested: !!ev.agent_id, desc: (ti.description || '').slice(0, 80) };

  // Fable is never used automatically (independent of ON/OFF).
  if (/fable/i.test(reqModel) && !fableAllowed()) {
    log({ ...base, decision: 'deny-fable' });
    return deny('Model routing: Fable is disabled by default. Use opus (deep-reviewer / art-director). ' +
      'If the user explicitly wants Fable, they enable it with: node <.claude>/hooks/router.mjs fable on');
  }
  if (isOff()) { log({ ...base, decision: 'pass-off' }); return; }
  // Loop guard: subagents must not delegate further.
  if (ev.agent_id) {
    log({ ...base, decision: 'deny-nested' });
    return deny('Model routing: subagents do not delegate further. Finish the task yourself and report back.');
  }
  log({ ...base, decision: 'allow' });
}

function hookPost(ev) {
  const ti = ev.tool_input || {};
  const r = ev.tool_response || {};
  log({ ev: 'post', agent: ti.subagent_type || r.agentType || 'general-purpose',
        req_model: ti.model || '', resolved_model: r.resolvedModel || '',
        status: r.status || '', tokens: r.totalTokens ?? '', ms: r.totalDurationMs ?? '',
        tools: r.totalToolUseCount ?? '', desc: (ti.description || '').slice(0, 80) });
}

function readLog() {
  try { return fs.readFileSync(LOG, 'utf8').trim().split('\n').filter(Boolean).map((l) => JSON.parse(l)); }
  catch { return []; }
}

function status(n = 10) {
  const recs = readLog();
  const out = [];
  out.push(`التوجيه (routing): ${isOff() ? 'متوقف OFF' : 'يعمل ON'}   |   Fable: ${fableAllowed() ? 'مسموح' : 'ممنوع (افتراضي)'}`);
  out.push(`مجلد الإعداد: ${BASE}`);
  out.push(`السياسة: ${exists(POLICY) ? 'موجودة' : 'مفقودة!'}   |   السجل: ${LOG}`);
  const sess = recs.filter((r) => r.ev === 'session').pop();
  out.push(`آخر بدء جلسة مسجّل: ${sess ? sess.ts + ' (' + sess.routing + ')' : 'لا يوجد بعد'}`);
  const posts = recs.filter((r) => r.ev === 'post');
  const byModel = {};
  for (const p of posts) {
    const k = p.resolved_model || '?';
    byModel[k] ??= { runs: 0, tokens: 0 };
    byModel[k].runs++; byModel[k].tokens += Number(p.tokens) || 0;
  }
  out.push('', 'الاستخدام الفعلي للمساعدين (من السجل):');
  if (!posts.length) out.push('  لا توجد استدعاءات Subagent مسجلة بعد.');
  for (const [m, v] of Object.entries(byModel)) out.push(`  ${m.padEnd(22)} مرات=${v.runs}  توكنز=${v.tokens}`);
  const denies = recs.filter((r) => String(r.decision || '').startsWith('deny'));
  const mism = posts.filter((p) => p.req_model && p.resolved_model && !p.resolved_model.includes(p.req_model.replace(/\[.*$/, '')));
  out.push('', `حالات منع: ${denies.length}   |   اختلاف المطلوب عن الفعلي: ${mism.length}   |   فشل/غير مكتمل: ${posts.filter((p) => p.status && p.status !== 'completed' && p.status !== 'async_launched').length}`);
  out.push('', `آخر ${n} أحداث:`);
  const pres = recs.filter((r) => r.ev === 'pre');
  for (const r of recs.filter((r) => r.ev !== 'session').slice(-n)) {
    if (r.ev === 'pre') out.push(`  ${r.ts.slice(5, 19)} طلب  ${r.agent.padEnd(15)} ${String(r.req_model).padEnd(8)} ${String(r.req_effort).padEnd(6)} [${r.source}] ${r.decision}  ${r.desc}`);
    else {
      const pre = pres.filter((p) => p.desc === r.desc && p.ts <= r.ts).pop();
      out.push(`  ${r.ts.slice(5, 19)} نفّذ ${r.agent.padEnd(15)} -> ${r.resolved_model || '?'}  ${r.status}  ${r.tokens} tok  ${Math.round((Number(r.ms) || 0) / 1000)}s${pre ? '  (طُلب ' + pre.req_model + '/' + pre.req_effort + ')' : ''}`);
    }
  }
  out.push('', 'تحكم: node "' + path.join(HERE, 'router.mjs') + '" on | off | fable on | fable off | status');
  console.log(out.join('\n'));
}

function setFlag(file, on) {
  fs.mkdirSync(STATE, { recursive: true });
  if (on) fs.writeFileSync(file, new Date().toISOString() + '\n');
  else if (exists(file)) fs.unlinkSync(file);
}

const [mode, arg] = process.argv.slice(2);
const hook = (fn) => { const ev = readStdin(); SID = String(ev.session_id || '').slice(0, 8); fn(ev); };
try {
  switch (mode) {
    case 'session': hook(hookSession); break;
    case 'pre': hook(hookPre); break;
    case 'post': hook(hookPost); break;
    case 'on': setFlag(OFF_FLAG, false); console.log('التوجيه يعمل. يسري على الجلسات الجديدة (السياسة تُحقن عند بدء الجلسة).'); break;
    case 'off': setFlag(OFF_FLAG, true); console.log('التوجيه متوقف. الجلسات الجديدة لن تستلم السياسة، ولن يُمنع التفويض المتداخل. حماية Fable تبقى.'); break;
    case 'fable':
      if (arg === 'on') { setFlag(FABLE_FLAG, true); console.log('Fable مسموح الآن عند الطلب الصريح فقط.'); }
      else { setFlag(FABLE_FLAG, false); console.log('Fable ممنوع (الافتراضي).'); }
      break;
    case 'log': for (const r of readLog().slice(-(Number(arg) || 30))) console.log(JSON.stringify(r)); break;
    case 'clear-log': if (exists(LOG)) fs.unlinkSync(LOG); console.log('تم مسح السجل.'); break;
    case 'status': default: status(Number(arg) || 10);
  }
} catch { /* fail-open */ }
process.exit(0);
