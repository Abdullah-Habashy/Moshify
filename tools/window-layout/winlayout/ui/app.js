"use strict";

const TOKEN = document.body.dataset.token;
const $ = (sel, root = document) => root.querySelector(sel);
const bdi = text => Object.assign(document.createElement("bdi"), { textContent: text });
const el = (tag, props = {}, ...kids) => {
  const node = Object.assign(document.createElement(tag), props);
  kids.flat().forEach(k => node.append(k));
  return node;
};

async function api(path, { method = "GET", body, params = {} } = {}) {
  const query = new URLSearchParams({ ...params, t: TOKEN });
  const response = await fetch(`/api/${path}?${query}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await response.json(); } catch (_) { /* empty body */ }
  if (!response.ok) throw new Error(data.error || `خطأ ${response.status}`);
  return data;
}

function banner(message, kind = "") {
  const node = $("#banner");
  node.textContent = message;
  node.className = `banner ${kind}` + (message ? "" : " hidden");
}

const fmtDate = ts => new Date(ts * 1000).toLocaleString("ar-EG-u-nu-latn",
  { dateStyle: "medium", timeStyle: "short" });

// العدد في العربي بيتصرّف مع المعدود: مفرد، مثنى، جمع (٣-١٠)، ثم مفرد تاني.
function countAr(n, [one, two, few, many]) {
  if (n === 0) return `مافيش ${few}`;
  if (n === 1) return `${one} واحدة`;
  if (n === 2) return two;
  if (n <= 10) return `${n} ${few}`;
  return `${n} ${many}`;
}
const WINDOW = ["نافذة", "نافذتين", "نوافذ", "نافذة"];
const MONITOR = ["شاشة", "شاشتين", "شاشات", "شاشة"];

// ---------- الخريطة المرئية للتوزيع ----------
function drawMap(layout) {
  const [bl, bt, br, bb] = layout.bounds;
  const width = Math.max(1, br - bl), height = Math.max(1, bb - bt);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `${bl} ${bt} ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.style.maxHeight = "170px";

  const add = (rect, cls) => {
    const node = document.createElementNS(ns, "rect");
    node.setAttribute("x", rect[0]);
    node.setAttribute("y", rect[1]);
    node.setAttribute("width", Math.max(1, rect[2] - rect[0]));
    node.setAttribute("height", Math.max(1, rect[3] - rect[1]));
    node.setAttribute("rx", Math.min(24, width / 90));
    node.setAttribute("class", cls);
    svg.append(node);
    return node;
  };

  layout.monitors.forEach(mon => add(mon.rect, "screen"));
  [...layout.items].sort((a, b) => b.z - a.z).forEach(item => {
    const node = add(item.rect, item.state === "minimized" ? "win min" : "win");
    const title = document.createElementNS(ns, "title");
    title.textContent = `${item.app} — ${item.title}`;
    node.append(title);
  });
  return el("div", { className: "map" }, svg);
}

function appChips(layout) {
  const counts = new Map();
  layout.items.forEach(i => counts.set(i.app, (counts.get(i.app) || 0) + 1));
  const chips = [...counts.entries()].slice(0, 8).map(([app, n]) =>
    el("span", { className: "chip" }, bdi(n > 1 ? `${app} ×${n}` : app)));
  if (counts.size > 8) chips.push(el("span", { className: "chip plain", textContent: `+${counts.size - 8}` }));
  return el("div", { className: "applist" }, chips);
}

// ---------- كروت التوزيعات ----------
function card(layout) {
  const restore = el("button", { className: "primary big", textContent: "▶ استرجع" });
  restore.onclick = () => runRestore(layout.name);

  const shortcut = el("button", { className: "ghost", textContent: "اختصار على الديسكتوب", title: "يعمل ملف تدوس عليه دبل كليك فيرجّع التوزيع من غير ما تفتح البرنامج" });
  shortcut.onclick = async () => {
    shortcut.disabled = true;
    try {
      const { path, folder, kind } = await api("shortcut",
        { method: "POST", body: { name: layout.name } });
      const note = kind === "cmd" ? " (كملف .cmd — PowerShell مش متاح)" : "";
      banner(`الاختصار اتعمل${note} وفتحنالك مكانه: ${folder}`, "ok");
      console.log("shortcut:", path);
    } catch (err) { banner(err.message, "error"); }
    shortcut.disabled = false;
  };

  const update = el("button", { className: "ghost", textContent: "حدّث", title: "يستبدل التوزيع بشكل الشاشة الحالي" });
  update.onclick = () => openCapture(layout.name);

  const rename = el("button", { className: "link", textContent: "إعادة تسمية" });
  rename.onclick = async () => {
    const next = prompt("الاسم الجديد:", layout.name);
    if (!next || next === layout.name) return;
    try {
      await api("rename", { method: "POST", body: { name: layout.name, new_name: next.trim() } });
      await load();
    } catch (err) { banner(err.message, "error"); }
  };

  const remove = el("button", { className: "link danger", textContent: "حذف" });
  remove.onclick = async () => {
    if (!confirm(`تمسح «${layout.name}»؟`)) return;
    try {
      await api("delete", { method: "POST", body: { name: layout.name } });
      await load();
    } catch (err) { banner(err.message, "error"); }
  };

  const launchBox = Object.assign(document.createElement("input"),
    { type: "checkbox", checked: layout.launch_missing });
  launchBox.onchange = async () => {
    try {
      await api("options", { method: "POST",
        body: { name: layout.name, launch_missing: launchBox.checked } });
    } catch (err) {
      launchBox.checked = !launchBox.checked;
      banner(err.message, "error");
    }
  };
  const launch = el("label", { className: "check inline", title:
      "وقت الاسترجاع، أي برنامج في التوزيع ده يكون مقفول هيتفتح ويتحط مكانه" },
    launchBox, el("span", { textContent: "افتح البرامج المقفولة" }));

  return el("article", { className: "card" },
    el("header", {},
      el("div", {},
        el("h3", {}, bdi(layout.name)),
        el("div", { className: "sub", textContent:
          `${countAr(layout.windows, WINDOW)} · ${countAr(layout.monitors.length, MONITOR)}`
          + ` · اتحدّث ${fmtDate(layout.updated_at)}` }))),
    drawMap(layout),
    appChips(layout),
    launch,
    el("div", { className: "actions" }, restore, update, shortcut),
    el("div", { className: "actions" }, rename, remove),
  );
}

async function load() {
  const { layouts, home } = await api("layouts");
  $("#home").textContent = home;
  const grid = $("#layouts");
  grid.textContent = "";
  layouts.forEach(layout => grid.append(card(layout)));
  $("#empty").classList.toggle("hidden", layouts.length > 0);
}

// ---------- حفظ توزيع ----------
const captureDialog = $("#capture-dialog");
let liveWindows = [];

async function openCapture(existingName) {
  $("#capture-title").textContent = existingName ? `حدّث «${existingName}»` : "احفظ التوزيع الحالي";
  $("#capture-name").value = existingName || "";
  $("#capture-name").readOnly = Boolean(existingName);
  $("#capture-list").textContent = "";
  $("#capture-count").textContent = "بنقرا النوافذ المفتوحة…";
  captureDialog.showModal();
  try {
    const data = await api("snapshot");
    liveWindows = data.windows;
    renderCandidates(data);
  } catch (err) {
    $("#capture-count").textContent = err.message;
  }
}

function renderCandidates(data) {
  const list = $("#capture-list");
  const names = new Map(data.monitors.map((m, i) => [m.device, `شاشة ${i + 1}`]));
  list.textContent = "";
  liveWindows.forEach(win => {
    const box = el("input", { type: "checkbox", value: String(win.hwnd), checked: true });
    const size = `${win.rect[2] - win.rect[0]}×${win.rect[3] - win.rect[1]}`;
    const where = names.get(win.monitor) || "";
    const state = win.state === "maximized" ? "مكبّرة" : win.state === "minimized" ? "مصغّرة" : size;
    list.append(el("label", { className: "check" }, box,
      el("span", {},
        el("span", { className: "name" }, bdi(win.app)),
        el("span", { className: "meta" }, bdi(win.title)),
        el("span", { className: "meta" }, bdi(state), " · ", where))));
  });
  updateCount();
  list.onchange = updateCount;
}

function updateCount() {
  const total = $("#capture-list").querySelectorAll("input").length;
  const picked = $("#capture-list").querySelectorAll("input:checked").length;
  $("#capture-count").textContent = `هتتحفظ ${countAr(picked, WINDOW)} من أصل ${total}`;
}

document.querySelectorAll("[data-select]").forEach(btn => {
  btn.onclick = () => {
    const on = btn.dataset.select === "all";
    $("#capture-list").querySelectorAll("input").forEach(i => { i.checked = on; });
    updateCount();
  };
});

$("#capture-save").onclick = async () => {
  const name = $("#capture-name").value.trim();
  if (!name) { $("#capture-name").focus(); return; }
  const hwnds = [...$("#capture-list").querySelectorAll("input:checked")].map(i => Number(i.value));
  if (!hwnds.length) { banner("اختار نافذة واحدة على الأقل", "error"); return; }
  const button = $("#capture-save");
  button.disabled = true;
  try {
    await api("capture", { method: "POST", body: {
      name, hwnds, force: $("#capture-name").readOnly,
      launch_missing: $("#capture-launch").checked,
    } });
    captureDialog.close();
    banner(`اتحفظ «${name}»`, "ok");
    await load();
  } catch (err) {
    if (err.message.includes("بالفعل") && confirm(`${err.message}. تستبدله؟`)) {
      try {
        await api("capture", { method: "POST", body: {
          name, hwnds, force: true, launch_missing: $("#capture-launch").checked } });
        captureDialog.close();
        await load();
      } catch (e2) { banner(e2.message, "error"); }
    } else {
      banner(err.message, "error");
    }
  }
  button.disabled = false;
};

$("#btn-capture").onclick = () => openCapture(null);
document.querySelectorAll("[data-close]").forEach(btn => {
  btn.onclick = () => btn.closest("dialog").close();
});

// ---------- استرجاع ----------
const restoreDialog = $("#restore-dialog");

async function runRestore(name) {
  $("#restore-title").textContent = `بنرجّع «${name}»…`;
  $("#restore-log").textContent = "";
  $("#restore-results").textContent = "";
  $("#restore-close").disabled = true;
  restoreDialog.showModal();
  let job;
  try {
    ({ job } = await api("restore", { method: "POST", body: { name } }));
  } catch (err) {
    $("#restore-title").textContent = err.message;
    $("#restore-close").disabled = false;
    return;
  }
  let seen = 0;
  const timer = setInterval(async () => {
    let state;
    try {
      state = await api("job", { params: { id: job } });
    } catch (_) { return; }
    state.messages.slice(seen).forEach(m => $("#restore-log").append(el("div", { textContent: m })));
    seen = state.messages.length;
    $("#restore-log").scrollTop = $("#restore-log").scrollHeight;
    if (!state.done) return;
    clearInterval(timer);
    $("#restore-close").disabled = false;
    if (state.error) { $("#restore-title").textContent = `فيه مشكلة: ${state.error}`; return; }
    showReport(state.report);
  }, 500);
}

function showReport(report) {
  $("#restore-title").textContent = report.summary;
  const box = $("#restore-results");
  box.textContent = "";
  report.warnings.forEach(w => box.append(el("div", { className: "result" },
    el("span", { className: "tag missing", textContent: "تنبيه" }),
    el("span", { textContent: w }))));
  report.results.forEach(r => box.append(el("div", { className: "result" },
    el("span", { className: `tag ${r.status}`, textContent: r.label }),
    el("span", {}, bdi(`${r.app} — ${r.title}`)),
    r.message ? el("span", { className: "why", textContent: `(${r.message})` }) : "")));
}

// ---------- تشغيل ----------
load().catch(err => banner(err.message, "error"));

// نبضة تقول للسيرفر إن الصفحة لسه مفتوحة، ووداع لما تتقفل عشان يقفل بسرعة
// بدل ما يفضل شغال. الريلود بيبعت وداع كمان، فالسيرفر بيتراجع عنه مع أول طلب بعده.
setInterval(() => api("ping").catch(() => {}), 15000);
addEventListener("pagehide", () => {
  try { navigator.sendBeacon(`/api/bye?t=${encodeURIComponent(TOKEN)}`); } catch (_) {}
});
