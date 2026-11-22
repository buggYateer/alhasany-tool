/* أداة الحسني — الواجهة (صفحة واحدة، الصفحات بالـ #) */
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const app = $("#app");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const isLocal = ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname);
let pollTimer = null;

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({error: "رد غير مفهوم من الأداة"}));
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, err ? 6000 : 3000);
}
function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn._html = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spin"></span>${label || "استنى…"}`; }
  else { btn.disabled = false; if (btn._html) btn.innerHTML = btn._html; }
}
const media = (p, dl) => `/media?path=${encodeURIComponent(p)}${dl ? "&dl=1" : ""}`;
const roleInfo = r => ({isha: ["تلاوة العشاء", "b-tilawa", "graphic_eq"], jumua: ["صلاة الجمعة", "b-tilawa", "graphic_eq"],
  khutba: ["خطبة", "b-khutba", "campaign"], lesson: ["درس", "b-lesson", "menu_book"]}[r] || ["ملف", "b-lesson", "audio_file"]);
// الوصف بشكل تليجرام: HTML بتاع تليجرام + الهاشتاجات ملونة
function tgHtml(cap) {
  const safe = String(cap || "").replace(/<(?!\/?(b|i|u|s|a|code|pre|tg-spoiler|blockquote)\b)[^>]*>/g, "");
  return safe.replace(/(^|[\s(])(#[\p{L}\p{N}_]+)/gu, '$1<span class="ht">$2</span>');
}
function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach(a => a.toggleAttribute("aria-current", a.dataset.nav === name));
}

/* ---------------- الراوتر ---------------- */
async function route() {
  clearInterval(pollTimer);
  const h = location.hash.slice(1) || "/";
  const [path, qs] = h.split("?");
  const q = new URLSearchParams(qs || "");
  window.scrollTo(0, 0);
  try {
    if (path.startsWith("/job/")) return await pageJob(decodeURIComponent(path.slice(5)));
    if (path === "/new") return await pageNew(q.get("f"));
    if (path === "/settings") return await pageSettings();
    return await pageHome();
  } catch (e) {
    app.innerHTML = `<div class="badline"><span class="ms">error</span>${esc(e.message)}</div>`;
  }
}
addEventListener("hashchange", route);

/* ---------------- الرئيسية ---------------- */
async function pageHome() {
  setNav("home");
  const st = await api("/api/status");
  if (!st.root) return pageSetup(st);
  const [raw, jobs] = await Promise.all([api("/api/raw"), api("/api/jobs")]);
  const r = st.report;
  const chips = [
    r.gpu ? `<span class="chip ok"><span class="ms">memory</span>${esc(r.gpu.split(",")[0])}</span>` : `<span class="chip warn"><span class="ms">memory</span>من غير كارت شاشة (أبطأ)</span>`,
    r.model ? `<span class="chip ok"><span class="ms">check_circle</span>موديل التفريغ</span>` : `<span class="chip bad"><span class="ms">error</span>الموديل ناقص</span>`,
    r.ffmpeg ? `<span class="chip ok"><span class="ms">check_circle</span>ffmpeg</span>` : `<span class="chip bad"><span class="ms">error</span>ffmpeg ناقص</span>`,
    st.has_bot ? `<span class="chip ok"><span class="ms">send</span>البوت متوصل</span>` : `<a class="chip warn" href="#/settings"><span class="ms">send</span>حط توكن البوت</a>`,
    st.has_gemini ? `<span class="chip ok"><span class="ms">auto_awesome</span>Gemini</span>` : `<a class="chip" href="#/settings"><span class="ms">auto_awesome</span>من غير Gemini</a>`,
    st.site_sync ? `<span class="chip ok"><span class="ms">language</span>الموقع بيتحدث</span>` : `<span class="chip"><span class="ms">language</span>تحديث الموقع مقفول</span>`,
  ].join("");
  const missing = !r.model || !r.ffmpeg || r.missing_packages.length;
  const running = jobs.running.filter(x => x.kind === "process");
  app.innerHTML = `
    <div class="page-h"><h1>أهلًا بيك 👋</h1><p>اختار التسجيل الخام، والأداة تقصّه وتفرّغه وتفحص التلاوة وتكتب الوصف.</p></div>
    <div class="chips">${chips}</div>
    ${missing ? `<div class="warnline" style="margin-top:12px"><span class="ms">download</span>فيه حاجات ناقصة على الجهاز <button class="btn small" id="fixBtn">نزّل الناقص</button></div>` : ""}
    ${running.map(x => `<a class="okline" style="margin-top:12px" href="#/job/${encodeURIComponent(x.id)}"><span class="spin"></span>شغال دلوقتي على ${esc(x.id)} — دوس تتابع</a>`).join("")}
    <div class="grid2" style="margin-top:6px">
      <div>
        <div class="sec-h"><h2>تسجيل جديد</h2><small dir="ltr">Alhasany\\Raw</small></div>
        <label class="drop" id="drop"><span class="ms">upload_file</span><b>${isLocal ? "اسحب ملف هنا أو دوس تختار" : "اختار التسجيل من الموبايل"}</b>
          <span class="muted small">بيتنقل لفولدر Raw على الكمبيوتر</span>
          <input type="file" id="upFile" accept="audio/*,.wav,.mp3,.m4a,.aac,.amr,.3gp" hidden></label>
        <div id="upProg" hidden><div class="row-flex small"><span id="upName"></span><span class="spacer"></span><b id="upPct"></b></div><div class="bar"><i id="upBar"></i></div></div>
        <div class="sec-h"><h2>التسجيلات الخام</h2><small>${raw.files.length} ملف</small></div>
        ${raw.files.length ? `<div class="list">${raw.files.slice(0, 40).map(f => `
          <a class="item" href="${f.job ? "#/job/" + encodeURIComponent(f.job) : "#/new?f=" + encodeURIComponent(f.path)}">
            <span class="ic ${f.job ? "done" : ""}"><span class="ms">${f.job ? "task_alt" : "mic"}</span></span>
            <span class="tx"><span class="t fname" dir="auto">${esc(f.name)}</span>
              <span class="m"><span>${f.mb} ميجا</span><span>${new Date(f.mtime * 1000).toLocaleString("ar-EG-u-nu-latn", {weekday: "long", day: "numeric", month: "numeric", hour: "numeric", minute: "2-digit"})}</span>${f.job ? "<span>اتعمل قبل كده</span>" : ""}</span></span>
            <span class="ms go">chevron_left</span></a>`).join("")}</div>` : `<p class="empty">مفيش تسجيلات — ارفع واحد أو حطه في فولدر Raw</p>`}
      </div>
      <div>
        ${isLocal ? `<div class="sec-h"><h2>افتحها من الموبايل</h2></div>
        <div class="card qr">${st.qr ? `<div class="code">${st.qr}</div>` : ""}
          <div><b>صوّر الكود بكاميرا الموبايل</b><p class="muted small" style="margin:4px 0">لازم الموبايل والكمبيوتر على نفس الواي فاي. ولو الويندوز سألك عن الشبكة، اختار «Private» واسمح.</p><code>${esc(st.phone_url)}</code></div></div>` : ""}
        <div class="sec-h"><h2>آخر الشغل</h2></div>
        ${jobs.jobs.length ? `<div class="list">${jobs.jobs.slice(0, 12).map(j => {
          const pub = j.files.filter(f => f.published).length;
          return `<a class="item" href="#/job/${encodeURIComponent(j.id)}">
            <span class="ic ${pub === j.files.length && pub ? "done" : ""}"><span class="ms">${j.kind === "friday" ? "mosque" : "nights_stay"}</span></span>
            <span class="tx"><span class="t">${esc(j.files.map(f => roleInfo(f.role)[0]).join(" + ") || j.id)} — ${esc(j.date || "")}هـ</span>
            <span class="m"><span>${pub ? `اتنشر ${pub} من ${j.files.length}` : "لسه متنشرش"}</span></span></span>
            <span class="ms go">chevron_left</span></a>`;
        }).join("")}</div>` : `<p class="empty">لسه مفيش</p>`}
      </div>
    </div>`;
  $("#fixBtn")?.addEventListener("click", async e => {
    const big = [!r.model && "موديل التفريغ (حوالي 1.6 جيجا)", !r.ffmpeg && "ffmpeg (حوالي 130 ميجا)", r.missing_packages.length && "مكتبات: " + r.missing_packages.join("، ")].filter(Boolean);
    if (!confirm("هينزّل من النت:\n• " + big.join("\n• ") + "\n\nأكمّل؟")) return;
    busy(e.currentTarget, true); await api("/api/setup", {install: true}); location.hash = "#/job/setup"; });
  const inp = $("#upFile"), drop = $("#drop");
  inp.addEventListener("change", () => inp.files[0] && upload(inp.files[0]));
  drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); });
}

function upload(file) {
  $("#upProg").hidden = false; $("#upName").textContent = file.name;
  const x = new XMLHttpRequest();
  x.open("POST", "/api/upload?name=" + encodeURIComponent(file.name));
  x.upload.onprogress = e => { const p = Math.round(e.loaded / e.total * 100); $("#upBar").style.width = p + "%"; $("#upPct").textContent = p + "%"; };
  x.onload = () => {
    let j = {}; try { j = JSON.parse(x.responseText); } catch (e) {}
    if (x.status !== 200 || j.error) return toast(j.error || "الرفع فشل", true);
    toast("✓ الملف وصل الكمبيوتر");
    location.hash = "#/new?f=" + encodeURIComponent(j.path);
  };
  x.onerror = () => toast("الرفع اتقطع — اتأكد إنك على نفس الواي فاي", true);
  x.send(file);
}

/* ---------------- أول تشغيل: مكان الفولدر ---------------- */
function pageSetup(st) {
  app.innerHTML = `
    <div class="page-h"><h1>أهلًا بيك في أداة الحسني</h1><p>أول مرة بس: اختار البارتيشن اللي هيتعمل فيه فولدر <b dir="ltr">Alhasany</b> (فيه الخام والمقصوص وكل شغل الأداة).</p></div>
    <div class="card">
      <div class="list">${st.drives.map(d => `
        <button class="item" data-p="${esc(d.path)}"><span class="ic"><span class="ms">hard_drive</span></span>
          <span class="tx"><span class="t" dir="ltr" style="display:block;text-align:right">${esc(d.path)}Alhasany</span>
          <span class="m"><span>فاضي ${d.free_gb} من ${d.total_gb} جيجا</span>${d.path === st.suggest ? "<span style='color:var(--ok);font-weight:700'>← مقترح</span>" : ""}${d.path.startsWith("C") ? "<span>(C بيتمسح لو الويندوز اتسطّب من جديد)</span>" : ""}</span></span>
          <span class="ms go">chevron_left</span></button>`).join("")}</div>
      <p class="muted small" style="margin:12px 4px 0">جواه هيتعمل: <span dir="ltr">Raw · Cut · Work · Backups · Models · Tools</span> — ومفيش أي تنزيل من غير ما تأكد.</p>
    </div>`;
  app.querySelectorAll("[data-p]").forEach(b => b.addEventListener("click", async () => {
    if (!confirm(`هعمل الفولدر في ${b.dataset.p}Alhasany — تمام؟`)) return;
    busy(b, true, "بعمل الفولدرات…");
    try { await api("/api/setup", {parent: b.dataset.p}); location.hash = "#/"; }
    catch (e) { toast(e.message, true); busy(b, false); }
  }));
}

/* ---------------- بيانات التسجيل ---------------- */
async function pageNew(file) {
  setNav("home");
  const d = await api("/api/meta?file=" + encodeURIComponent(file));
  const m = d.meta;
  const name = file.split(/[\\/]/).pop();
  const shOpts = (sel) => d.sheikhs.map(s => `<option value="${esc(s.short)}" ${s.short === sel ? "selected" : ""}>${esc(s.full)}</option>`).join("");
  const guestOpts = d.guests.map(g => `<option value="${esc(g.replace(/_/g, " "))}">${esc(g.replace(/_/g, " "))}</option>`).join("");
  const serOpts = (sh) => `<option value="">من غير سلسلة</option>` + d.series.filter(s => !sh || s.sheikh === sh).map(s =>
    `<option value="${esc(s.key)}" ${s.key === m.series ? "selected" : ""}>${esc(s.name)}</option>`).join("");
  app.innerHTML = `
    <div class="page-h"><a class="crumb" href="#/"><span class="ms">arrow_forward</span>الرئيسية</a><h1>بيانات التسجيل</h1><p dir="ltr" style="text-align:right">${esc(name)}</p></div>
    <div class="card">
      <p class="muted small" style="margin:0 0 12px">الأداة خمّنت البيانات من اسم الملف وجدول المشايخ — راجعها وعدّل لو فيه حاجة.</p>
      <div class="form">
        <div class="fld full"><span>نوع التسجيل</span><div class="seg" id="kind">
          <button data-k="night" aria-pressed="${m.kind !== "friday"}">🌙 عشاء + درس</button>
          <button data-k="friday" aria-pressed="${m.kind === "friday"}">🕌 خطبة الجمعة</button></div></div>
        <label class="fld"><span>التاريخ الهجري</span><input id="date" value="${esc(m.date)}" inputmode="numeric" dir="ltr" style="text-align:right"><small>${esc(m.weekday || "")} — يوم-شهر-سنة</small></label>
        <div class="fld night"><span>الشيخ</span><select id="sheikh">${shOpts(m.sheikh)}<option value="__other">شيخ تاني…</option></select>
          <input id="sheikhOther" placeholder="اسم الشيخ" hidden></div>
        <div class="fld fri"><span>الخطيب</span><select id="khatib"><option value="">اختار الخطيب…</option>${shOpts("")}<optgroup label="ضيوف">${guestOpts}</optgroup><option value="__other">خطيب تاني…</option></select>
          <input id="khatibOther" placeholder="اسم الخطيب" hidden></div>
        <label class="check fri"><input type="checkbox" id="merge"> الخطبة والصلاة في ملف واحد</label>
        <label class="fld night"><span>السلسلة</span><select id="series">${serOpts(m.sheikh)}</select></label>
        <label class="fld night" id="numBox"><span>رقم الدرس في السلسلة</span><input id="number" type="number" min="1" value="${m.number || ""}"></label>
      </div>
      <div class="actions" style="margin-top:16px"><button class="btn gold" id="go"><span class="ms">content_cut</span>ابدأ القص والتفريغ</button>
        <span class="muted small" style="align-self:center">التسجيل الطويل بياخد حوالي ربع ساعة على كارت الشاشة</span></div>
    </div>`;
  let kind = m.kind === "friday" ? "friday" : "night";
  const sh = d.sheikhs;
  const showKind = () => {
    app.querySelectorAll(".night").forEach(e => e.hidden = kind !== "night");
    app.querySelectorAll(".fri").forEach(e => e.hidden = kind !== "friday");
    $("#numBox").hidden = kind !== "night" || !(d.series.find(s => s.key === $("#series").value) || {}).numbered;
  };
  app.querySelectorAll("#kind button").forEach(b => b.addEventListener("click", () => {
    kind = b.dataset.k; app.querySelectorAll("#kind button").forEach(x => x.setAttribute("aria-pressed", x === b)); showKind();
  }));
  $("#sheikh").addEventListener("change", e => {
    $("#sheikhOther").hidden = e.target.value !== "__other";
    $("#series").innerHTML = serOpts(e.target.value === "__other" ? "__none" : e.target.value);
    const s = d.series.find(x => x.sheikh === e.target.value);
    $("#series").value = s ? s.key : "";
    $("#number").value = s && s.numbered ? (s.last_number || 0) + 1 : "";
    showKind();
  });
  $("#khatib").addEventListener("change", e => {
    $("#khatibOther").hidden = e.target.value !== "__other";
    const s = sh.find(x => x.short === e.target.value);
    $("#merge").checked = !!(s && s.khutba_with_prayer);
  });
  $("#series").addEventListener("change", () => {
    const s = d.series.find(x => x.key === $("#series").value);
    $("#number").value = s && s.numbered ? (s.last_number || 0) + 1 : "";
    showKind();
  });
  showKind();
  $("#go").addEventListener("click", async e => {
    const [dd, mm, yy] = $("#date").value.trim().split("-").map(Number);
    if (!dd || !mm || !yy) return toast("اكتب التاريخ كده: 7-6-1448", true);
    const meta = {...m, kind, date: `${dd}-${mm}-${yy}`, day: dd, month: mm, year: yy};
    if (kind === "night") {
      meta.sheikh = $("#sheikh").value === "__other" ? $("#sheikhOther").value.trim() : $("#sheikh").value;
      meta.series = $("#series").value || null;
      meta.number = Number($("#number").value) || null;
      if (!meta.sheikh) return toast("اختار الشيخ", true);
    } else {
      meta.khatib = $("#khatib").value === "__other" ? $("#khatibOther").value.trim() : $("#khatib").value;
      meta.merge_prayer = $("#merge").checked;
      meta.series = null; meta.number = null;
      if (!meta.khatib) return toast("اختار الخطيب", true);
    }
    busy(e.currentTarget, true, "ببدأ…");
    try { const r = await api("/api/process", {file, meta}); location.hash = "#/job/" + encodeURIComponent(r.job); }
    catch (err) { toast(err.message, true); busy(e.currentTarget, false); }
  });
}

/* ---------------- المعالجة + المراجعة + النشر ---------------- */
async function pageJob(id) {
  setNav("home");
  const d = await api("/api/job?id=" + encodeURIComponent(id));
  if (d.state === "running" || (id === "setup" && d.state !== "missing") || d.state === "error") return showProgress(id, d);
  if (!d.job) { app.innerHTML = `<p class="empty">مش لاقي الشغل ده</p>`; return; }
  renderReview(id, d.job);
}

function logHtml(lines) {
  return lines.map(l => `<div class="${/^✓/.test(l) ? "ok" : /^(✗|⚠)/.test(l) ? "bad" : ""}">${esc(l)}</div>`).join("");
}
function showProgress(id, d) {
  const title = id === "setup" ? "تجهيز الجهاز" : "بقص وأفرّغ";
  app.innerHTML = `
    <div class="page-h"><a class="crumb" href="#/"><span class="ms">arrow_forward</span>الرئيسية</a><h1>${title}</h1><p dir="ltr" style="text-align:right">${esc(id === "setup" ? "" : id)}</p></div>
    <div class="card"><div class="row-flex" style="margin-bottom:10px" id="stLine"></div><div class="log" id="log"></div>
    <p class="muted small" style="margin:10px 0 0">تقدر تقفل الصفحة دي أو الموبايل — الشغل كمّل على الكمبيوتر، وارجع للرئيسية تلاقيه.</p></div>`;
  const draw = d => {
    $("#stLine").innerHTML = d.state === "running" ? `<span class="spin"></span><b>شغال…</b>` :
      d.state === "error" ? `<span class="badline"><span class="ms">error</span>وقف بسبب خطأ — شوف آخر سطر</span>` :
      `<span class="okline"><span class="ms">task_alt</span>خلص</span>`;
    const lg = $("#log"); const atEnd = lg.scrollTop + lg.clientHeight >= lg.scrollHeight - 30;
    lg.innerHTML = logHtml(d.log); if (atEnd) lg.scrollTop = lg.scrollHeight;
  };
  draw(d);
  pollTimer = setInterval(async () => {
    try {
      const n = await api("/api/job?id=" + encodeURIComponent(id));
      if (n.state === "running") return draw(n);
      clearInterval(pollTimer);
      draw(n);
      if (n.state === "done" && id === "setup") setTimeout(() => location.hash = "#/", 1200);
      else if (n.state === "done" && n.job) setTimeout(() => renderReview(id, n.job), 600);
    } catch (e) {}
  }, 1500);
}

function renderReview(id, job) {
  const m = job.meta;
  const who = m.kind === "friday" ? m.khatib : m.sheikh;
  app.innerHTML = `
    <div class="page-h"><a class="crumb" href="#/"><span class="ms">arrow_forward</span>الرئيسية</a>
      <h1>${m.kind === "friday" ? "🕌 الجمعة" : "🌙 العشاء والدرس"} — ${esc(m.date)}هـ</h1><p>${esc(m.weekday || "")} · الشيخ ${esc(who || "")}</p></div>
    <div class="card" style="margin-bottom:18px">
      <div class="row-flex"><span class="ms" style="color:var(--gold-d)">checklist</span><b>الخطوات:</b>
        <span class="muted small">١) اسمع وراجع ← ٢) اكتب العنوان ← ٣) ارفع الملفات على القناة بإيدك ← ٤) «دوّر على المرفوع» ← ٥) «طبّق على القناة»</span></div>
      <div class="actions"><button class="btn primary" id="findBtn"><span class="ms">travel_explore</span>دوّر على المرفوع في القناة</button></div>
      <div id="findOut"></div>
    </div>
    <div id="files"></div>`;
  $("#files").innerHTML = job.files.map((f, i) => fileCard(f, i)).join("") || `<p class="empty">مطلعش ملفات — شوف السجل</p>`;
  job.files.forEach((f, i) => wireFile(id, job, f, i));
  $("#findBtn").addEventListener("click", async e => {
    busy(e.currentTarget, true, "بدوّر في القناة…");
    try {
      const r = await api("/api/tg/find", {id});
      const n = Object.keys(r.found).length;
      toast(n ? `✓ لقيت ${n} ملف` : "ملقيتش الملفات — اتأكد إنك رفعتها بنفس الاسم", !n);
      renderReview(id, r.job);
    } catch (err) { toast(err.message, true); busy(e.currentTarget, false); }
  });
}

function fileCard(f, i) {
  const [label, cls] = roleInfo(f.role);
  const hasTitle = f.role === "lesson" || f.role === "khutba";
  const style = (f.cap_args && f.cap_args.series) ? "" : "";
  const iss = f.issues || [];
  return `
  <section class="fcard" id="f${i}">
    <div class="fhead"><span class="badge-k ${cls}">${label}</span>
      <div style="min-width:0"><h3 class="fname" dir="auto">${esc(f.name)}</h3><div class="m">${esc(f.duration)}${f.surahs && f.surahs.length ? " · " + esc(f.surahs.join(" ← ")) : ""}</div></div>
      <span class="spacer"></span><a class="btn small" href="${media(f.file, 1)}"><span class="ms">download</span>تنزيل</a></div>
    <div class="fbody">
      <div class="full"><audio controls preload="metadata" src="${media(f.file)}" id="au${i}"></audio></div>
      <div class="blk"><h4><span class="ms">content_cut</span>أماكن القص</h4>
        <div class="cuts">${(f.preview || []).map(p => `<div class="cut"><b>${esc(p[0])}</b><span>…${esc(p[1])}</span></div><div class="cut"><b>${esc(p[2])}</b><span>${esc(p[3])}…</span></div>`).join("")}</div>
        <p class="muted small" style="margin:6px 0 0">${esc(f.note || "")} (التوقيتات من التسجيل الخام)</p>
        ${(f.warnings || []).map(w => `<div class="warnline" style="margin-top:8px"><span class="ms">warning</span>${esc(w)}</div>`).join("")}</div>
      <div class="blk">${f.role === "lesson" ? `<h4><span class="ms">info</span>الدرس</h4><p class="muted small" style="margin:0">اسمع أوله وآخره واتأكد إن القص مظبوط.</p>` : `
        <h4><span class="ms">menu_book</span>فحص التلاوة</h4>
        ${iss.length ? `<p class="muted small" style="margin:0 0 6px">دوس على التوقيت تسمع المكان — التنبيه ممكن يكون من Whisper نفسه، القرار بسمعك.</p>
        <div class="issues">${iss.map(x => `<button class="issue" data-t="${esc(x.t)}"><span class="tm">${esc(x.t)}</span><span><span class="k">${esc(x.kind)}</span>
          <span class="d">${x.expected ? "المصحف: «" + esc(x.expected) + "»" : ""} ${x.heard ? "— المسموع: «" + esc(x.heard) + "»" : ""}</span></span></button>`).join("")}</div>`
        : `<div class="okline"><span class="ms">task_alt</span>مفيش ملاحظات على التلاوة</div>`}`}</div>
      <div class="full blk"><h4><span class="ms">edit_note</span>الوصف</h4>
        ${hasTitle ? titleFields(f, i) : ""}
        <div class="tgprev"><div class="bubble" id="cap${i}">${tgHtml(f.caption)}</div></div>
        <div class="actions">
          <button class="btn small" data-act="copy"><span class="ms">content_copy</span>انسخ الوصف</button>
          <button class="btn small" data-act="manual"><span class="ms">edit</span>تعديل يدوي</button>
          ${f.manual ? `<button class="btn small" data-act="reset"><span class="ms">restart_alt</span>رجّع القالب</button>` : ""}
        </div>
        <div class="fld" id="manBox${i}" hidden style="margin-top:10px"><textarea id="man${i}">${esc(f.caption)}</textarea>
          <div class="actions"><button class="btn small primary" data-act="saveman">احفظ التعديل</button></div></div>
      </div>
    </div>
    ${pubBox(f, i)}
  </section>`;
}

function titleFields(f, i) {
  const ayah = f.cap_args && f.cap_args.series === "yahya";
  return `
    <div class="form" style="margin-bottom:12px">
      ${ayah ? `<label class="fld"><span>الآيات (زي: سورة هود (61))</span><input id="vr${i}" value="${esc(f.verses || "")}"></label>
               <label class="fld"><span>العنوان الفرعي 🔹</span><input id="sb${i}" value="${esc(f.subtitle || "")}"></label>` :
      `<div class="fld full"><span>العنوان</span><div class="titlebox"><input id="tt${i}" value="${esc(f.title || "")}" placeholder="اكتب العنوان أو دوس «اقترح»">
        <button class="btn small gold" data-act="ai"><span class="ms">auto_awesome</span>اقترح من Gemini</button>
        <button class="btn small" data-act="prompt"><span class="ms">content_copy</span>انسخ البرومبت</button></div>
        <small id="aiNote${i}"></small></div>`}
    </div>`;
}

function pubBox(f, i) {
  const url = "https://t.me/masjed_alhasany/";
  if (f.published) return `<div class="pubbox"><div class="okline"><span class="ms">task_alt</span>اتنشر — <a href="${url}${f.msg_id}" target="_blank" rel="noopener" style="text-decoration:underline">الرسالة ${f.msg_id}</a></div></div>`;
  if (!f.msg_id) return `<div class="pubbox"><h4>النشر</h4>
    <p class="muted small" style="margin:0 0 8px">ارفع الملف ده على القناة بإيدك، وبعدين دوس «دوّر على المرفوع» فوق. أو حط لينك الرسالة هنا:</p>
    <div class="secret"><input id="ml${i}" placeholder="https://t.me/masjed_alhasany/650" dir="ltr" style="background:var(--surface);border:1.5px solid var(--line);border-radius:10px;padding:8px 12px;min-height:44px">
    <button class="btn small" data-act="setmsg">ربط</button></div></div>`;
  return `<div class="pubbox"><h4>النشر — <a href="${url}${f.msg_id}" target="_blank" rel="noopener" style="color:var(--accent)">الرسالة ${f.msg_id}</a></h4>
    <div id="idx${i}"></div>
    <div class="actions"><button class="btn gold" data-act="publish"><span class="ms">send</span>طبّق على القناة</button></div>
    <ul class="steps" id="steps${i}"></ul></div>`;
}

function wireFile(id, job, f, i) {
  const card = $("#f" + i), au = $("#au" + i);
  const save = async (extra) => {
    const r = await api("/api/caption", {id, idx: i, ...extra});
    Object.assign(f, r.file); job.files[i] = f;
    $("#cap" + i).innerHTML = tgHtml(f.caption); $("#man" + i).value = f.caption;
  };
  card.querySelectorAll(".issue").forEach(b => b.addEventListener("click", () => {
    const [mm, ss] = b.dataset.t.split(":").map(Number); au.currentTime = Math.max(0, mm * 60 + ss - 2); au.play();
  }));
  let tmr;
  const live = () => { clearTimeout(tmr); tmr = setTimeout(() => save({title: $("#tt" + i)?.value ?? f.title, subtitle: $("#sb" + i)?.value ?? f.subtitle, verses: $("#vr" + i)?.value ?? f.verses}).catch(e => toast(e.message, true)), 400); };
  ["tt", "sb", "vr"].forEach(p => $("#" + p + i)?.addEventListener("input", live));
  card.addEventListener("click", async e => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const act = b.dataset.act;
    try {
      if (act === "copy") { await navigator.clipboard.writeText(f.caption); toast("✓ اتنسخ"); }
      if (act === "manual") { $("#manBox" + i).hidden = !$("#manBox" + i).hidden; }
      if (act === "saveman") { await save({caption: $("#man" + i).value, manual: true}); toast("✓ اتحفظ"); }
      if (act === "reset") { await save({}); renderReview(id, job); }
      if (act === "prompt") { await navigator.clipboard.writeText(f.prompt || ""); toast("✓ البرومبت اتنسخ — الصقه في أي شات ذكاء اصطناعي"); }
      if (act === "ai") {
        busy(b, true, "بفكر…");
        try { const r = await api("/api/title", {id, idx: i}); $("#tt" + i).value = r.title; $("#aiNote" + i).textContent = r.summary ? "الملخص: " + r.summary : ""; await save({title: r.title}); }
        finally { busy(b, false); }
      }
      if (act === "setmsg") { busy(b, true); const r = await api("/api/tg/setmsg", {id, idx: i, msg_id: $("#ml" + i).value.trim()}); job.files[i] = r.file; renderReview(id, job); }
      if (act === "publish") await publish(id, job, f, i, b);
    } catch (err) { toast(err.message, true); busy(b, false); }
  });
  if (f.msg_id && !f.published) loadIndex(id, f, i);
}

async function loadIndex(id, f, i) {
  const box = $("#idx" + i); if (!box) return;
  try {
    const r = await api("/api/tg/index", {id, idx: i});
    if (!r.index) return;
    box.innerHTML = `<div class="form" style="margin-bottom:6px">
      <label class="check full"><input type="checkbox" id="ia${i}" checked> أضيفه لفهرس السلسلة (رسالة ${r.index})</label>
      <label class="fld"><span>سطر الفهرس</span><input id="il${i}" value="${esc(f.index_line || r.default_line)}" placeholder="نفس العنوان"></label>
      <label class="fld"><span>القسم</span><select id="is${i}">${r.sections.map((s, k) => `<option ${(r.section ? s === r.section : k === r.sections.length - 1) ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label></div>`;
  } catch (e) { box.innerHTML = `<div class="warnline"><span class="ms">warning</span>مش قادر أقرا الفهرس: ${esc(e.message)}</div>`; }
}

async function publish(id, job, f, i, btn) {
  const addIdx = $("#ia" + i)?.checked;
  const line = $("#il" + i)?.value.trim();
  if ((f.role === "lesson" || f.role === "khutba") && !(f.title || f.subtitle || f.manual)) return toast("اكتب العنوان الأول", true);
  const what = [`الوصف هيتحط على الرسالة ${f.msg_id}`];
  if (addIdx) what.push(`«${line}» هيتضاف لفهرس السلسلة`);
  if (!confirm("متأكد؟\n\n• " + what.join("\n• ") + "\n\n(نسخة من القديم بتتحفظ في Backups)")) return;
  busy(btn, true, "بطبّق…");
  try {
    const r = await api("/api/tg/publish", {id, idx: i, add_index: !!addIdx, index_line: line, index_section: $("#is" + i)?.value});
    job.files[i] = r.file;
    toast("✓ اتنشر");
    renderReview(id, job);
    const ul = $("#steps" + i) || $("#f" + i + " .pubbox");
    ul.insertAdjacentHTML("beforeend", r.steps.map(s => `<div class="${s.startsWith("⚠") ? "warnline" : "okline"}" style="margin-top:6px">${esc(s)}</div>`).join(""));
  } catch (e) { toast(e.message, true); busy(btn, false); }
}

/* ---------------- الإعدادات ---------------- */
async function pageSettings() {
  setNav("settings");
  const d = await api("/api/settings");
  const s = d.settings, sec = d.secrets;
  const days = ["السبت", "الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة"];
  const shRow = (x = {}) => `<tr><td><input data-k="full" value="${esc(x.full || "")}"></td><td><input data-k="tag" value="${esc(x.tag || "")}" dir="rtl"></td>
    <td><select data-k="day"><option value="">—</option>${days.map(dd => `<option ${dd === x.day ? "selected" : ""}>${dd}</option>`).join("")}</select></td>
    <td style="text-align:center"><input type="checkbox" data-k="kwp" ${x.khutba_with_prayer ? "checked" : ""} style="width:22px;min-height:22px"></td>
    <td><button class="btn small" data-del>✕</button></td></tr>`;
  app.innerHTML = `
    <div class="page-h"><h1>الإعدادات</h1><p>كل جهاز ليه إعداداته ومفاتيحه — المفاتيح بتتحفظ على الجهاز ده بس، ومش بتترفع على GitHub.</p></div>
    <div class="sec-h"><h2>المفاتيح</h2></div>
    <div class="card"><div class="form">
      <div class="fld full"><span>توكن بوت تليجرام ${sec.bot_token ? "<b style='color:var(--ok)'>✓ متسجل</b>" : ""}</span>
        <div class="secret"><input id="bot" type="password" placeholder="${sec.bot_token ? "متسجل — اكتب جديد لو عايز تغيّره" : "من @BotFather"}" autocomplete="off">
        <button class="btn small primary" data-save="bot_token" data-in="bot">احفظ</button></div>
        <small>البوت لازم يكون أدمن في القناة (نشر + تعديل). وافتح البوت ودوس Start مرة واحدة.</small>
        <div class="actions"><button class="btn small" id="tgCheck"><span class="ms">wifi_tethering</span>جرّب الاتصال</button><span id="tgRes" class="small" style="align-self:center"></span></div></div>
      <div class="fld full"><span>مفتاح Gemini ${sec.gemini_key ? "<b style='color:var(--ok)'>✓ متسجل</b>" : "(اختياري — لاقتراح العناوين)"}</span>
        <div class="secret"><input id="gem" type="password" placeholder="${sec.gemini_key ? "متسجل — اكتب جديد لو عايز تغيّره" : "من aistudio.google.com/apikey (مجاني)"}" autocomplete="off">
        <button class="btn small primary" data-save="gemini_key" data-in="gem">احفظ</button></div></div>
    </div></div>

    <div class="sec-h"><h2>المشايخ وأيام الدروس</h2></div>
    <div class="card"><div class="tbl-wrap"><table class="tbl" id="shT"><thead><tr><th>الاسم</th><th>الهاشتاج</th><th>اليوم</th><th>الخطبة + الصلاة</th><th></th></tr></thead>
      <tbody>${s.sheikhs.map(shRow).join("")}</tbody></table></div>
      <div class="actions"><button class="btn small" id="shAdd">+ شيخ</button><button class="btn small primary" id="shSave">احفظ المشايخ</button></div></div>

    <div class="sec-h"><h2>الفولدرات</h2></div>
    <div class="card"><div class="form">
      <label class="fld full"><span>فولدر تسجيلات إضافي (اختياري — لو المايك بيحفظ في مكان تاني)</span><input id="rawDir" value="${esc(s.raw_dir || "")}" dir="ltr"></label>
      <label class="fld"><span>تصحيح التاريخ الهجري (أيام)</span><input id="hijri" type="number" value="${esc(s.hijri_offset_days || 0)}"></label>
    </div><div class="actions"><button class="btn small primary" id="dirSave">احفظ</button></div></div>

    <div class="sec-h"><h2>موقع المسجد</h2><small>${s.site_sync ? "مفتوح" : "مقفول"}</small></div>
    <div class="card"><div class="form">
      <label class="check full"><input type="checkbox" id="siteSync" ${s.site_sync ? "checked" : ""}> حدّث الموقع بعد كل نشر</label>
      <label class="fld full"><span>ملف المقاطع (channel_audio.json)</span><input id="siteJson" value="${esc(s.site_channel_json || "")}" dir="ltr"></label>
      <label class="fld full"><span>ملف السلاسل (gen_series.py)</span><input id="siteSeries" value="${esc(s.site_series_py || "")}" dir="ltr"></label>
      <label class="fld full"><span>أمر تحديث الموقع</span><input id="siteCmd" value="${esc(s.site_update_cmd || "")}" dir="ltr" placeholder='python "...\\update_site.py"'></label>
    </div><div class="actions"><button class="btn small primary" id="siteSave">احفظ</button></div></div>`;

  app.querySelectorAll("[data-save]").forEach(b => b.addEventListener("click", async () => {
    const v = $("#" + b.dataset.in).value.trim(); if (!v) return toast("اكتب المفتاح الأول", true);
    try { await api("/api/secrets", {[b.dataset.save]: v}); toast("✓ اتحفظ على الجهاز ده"); pageSettings(); } catch (e) { toast(e.message, true); }
  }));
  $("#tgCheck").addEventListener("click", async e => {
    busy(e.currentTarget, true);
    try { const r = await api("/api/tg/check", {}); $("#tgRes").innerHTML = `<b style="color:var(--ok)">✓ @${esc(r.bot.username)} شغال ومتوصل بيك</b>`; }
    catch (err) { $("#tgRes").innerHTML = `<b style="color:var(--bad)">${esc(err.message)}</b>`; }
    busy(e.currentTarget, false);
  });
  const tb = $("#shT tbody");
  $("#shAdd").addEventListener("click", () => tb.insertAdjacentHTML("beforeend", shRow()));
  tb.addEventListener("click", e => e.target.closest("[data-del]")?.closest("tr").remove());
  $("#shSave").addEventListener("click", async () => {
    const old = s.sheikhs;
    const list = [...tb.rows].map(r => {
      const g = k => r.querySelector(`[data-k=${k}]`);
      const full = g("full").value.trim(); if (!full) return null;
      const prev = old.find(o => o.full === full) || {};
      const x = {short: prev.short || full.split(" ")[0], tag: g("tag").value.trim() || full.replace(/ /g, "_"), full};
      if (g("day").value) x.day = g("day").value;
      if (g("kwp").checked) x.khutba_with_prayer = true;
      return x;
    }).filter(Boolean);
    try { await api("/api/settings", {sheikhs: list}); toast("✓ اتحفظ"); } catch (e) { toast(e.message, true); }
  });
  $("#dirSave").addEventListener("click", async () => {
    try { await api("/api/settings", {raw_dir: $("#rawDir").value.trim(), hijri_offset_days: Number($("#hijri").value) || 0}); toast("✓ اتحفظ"); } catch (e) { toast(e.message, true); }
  });
  $("#siteSave").addEventListener("click", async () => {
    try { await api("/api/settings", {site_sync: $("#siteSync").checked, site_channel_json: $("#siteJson").value.trim(), site_series_py: $("#siteSeries").value.trim(), site_update_cmd: $("#siteCmd").value.trim()}); toast("✓ اتحفظ"); } catch (e) { toast(e.message, true); }
  });
}

route();
