/* MAWOS v3 — university portal SPA (no build step).
 * Trust model: single-institution research prototype on localhost; rendered
 * values originate from the server's own seeded DB. Chat/LLM text is
 * rendered via textContent. */
let TOKEN = localStorage.getItem("mawos_token") || null;
let USER = JSON.parse(localStorage.getItem("mawos_user") || "null");
let AI_MODE = localStorage.getItem("mawos_ai") || "lexicon";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, {
    method: opts.method || (opts.body ? "POST" : "GET"),
    headers: { "Content-Type": "application/json",
               ...(TOKEN ? { Authorization: "Bearer " + TOKEN } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { logout(); throw new Error("Session expired"); }
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

/* ---------------- auth ---------------- */
async function login(u, p) {
  $("login-error").textContent = "";
  try {
    const data = await api("/auth/login", { body: {
      username: u ?? $("login-username").value,
      password: p ?? $("login-password").value } });
    TOKEN = data.token; USER = data.user; AI_MODE = data.ai_mode;
    localStorage.setItem("mawos_token", TOKEN);
    localStorage.setItem("mawos_user", JSON.stringify(USER));
    localStorage.setItem("mawos_ai", AI_MODE);
    showApp();
  } catch (e) { $("login-error").textContent = e.message; }
}
function logout() {
  TOKEN = USER = null;
  localStorage.clear();
  $("app-view").classList.add("hidden");
  $("login-view").classList.remove("hidden");
}

/* ---------------- shell ---------------- */
const TABS = {
  student:   [["overview", "My Studies"], ["timetable", "Timetable"],
              ["assistant", "Assistant"], ["system", "System"]],
  faculty:   [["classes", "My Classes"], ["timetable", "My Timetable"],
              ["assistant", "Assistant"], ["system", "System"]],
  hod:       [["dept", "Department"], ["classes", "My Classes"],
              ["assistant", "Assistant"], ["system", "System"]],
  principal: [["institution", "Institution"], ["assistant", "Assistant"],
              ["system", "System"]],
  admin:     [["admissions", "Admissions"], ["institution", "Institution"],
              ["assistant", "Assistant"], ["system", "System"]],
};
const RENDER = {};   // tab -> async render fn, filled below

function showApp() {
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("user-name").textContent = `${USER.name}`;
  const badge = $("ai-badge");
  badge.textContent = AI_MODE === "llm" ? "AI · hybrid router" : "AI · lexicon only";
  badge.className = "ai-badge " + AI_MODE;
  badge.title = AI_MODE === "llm"
    ? "Confidence-gated router: the lexicon answers, and only low-confidence queries escalate to the local LLM"
    : "Local LLM not detected — the lexicon answers everything, including the queries it is least sure about.";
  const nav = $("nav-tabs");
  nav.innerHTML = "";
  for (const [key, label] of TABS[USER.role]) {
    const b = document.createElement("button");
    b.textContent = label; b.dataset.tab = key;
    b.onclick = () => selectTab(key);
    nav.appendChild(b);
  }
  selectTab(TABS[USER.role][0][0]);
}
async function selectTab(key) {
  document.querySelectorAll("nav button").forEach(b =>
    b.classList.toggle("active", b.dataset.tab === key));
  const main = $("main-content");
  main.innerHTML = `<p class="muted">Loading…</p>`;
  try { await RENDER[key](main); }
  catch (e) { main.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`; }
}

/* ---------------- shared components ---------------- */
const pill = (ok, good = "OK", bad = "ISSUE") =>
  `<span class="pill ${ok ? "good" : "bad"}">${ok ? good : bad}</span>`;

function barRow(label, value, max, display, alt = false) {
  const w = max > 0 ? Math.max(2, 100 * value / max) : 0;
  return `<div class="bar-row" title="${esc(label)}: ${esc(display)}">
    <span class="bar-label">${esc(label)}</span>
    <span class="bar-track"><span class="bar-fill${alt ? " alt" : ""}" style="width:${w}%"></span></span>
    <span class="bar-value">${esc(display)}</span></div>`;
}

function ttTable(g, showClass = false) {
  let html = `<div class="tt-wrap"><table class="tt"><tr><th>Day</th>`;
  g.periods.forEach(p => html += `<th>${esc(p)}</th>`);
  html += "</tr>";
  g.days.forEach((day, d) => {
    html += `<tr><th>${esc(day)}</th>`;
    for (let p = 0; p < g.periods.length; p++) {
      const c = g.cells[`${d}-${p}`];
      html += c
        ? `<td><div class="subj">${esc(c.subject)}</div>
             <div class="fac">${esc(showClass ? "" : (c.subject_name || ""))}</div>
             <div class="${showClass ? "cls" : "fac"}">${esc(showClass ? c.class : c.faculty || "")}</div></td>`
        : `<td class="free"></td>`;
    }
    html += "</tr>";
  });
  return html + "</table></div>";
}

async function downloadCsv(dept, year, section) {
  const res = await fetch(`/api/timetable/${dept}/${year}/${section}/csv`,
    { headers: { Authorization: "Bearer " + TOKEN } });
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `timetable_${dept}_${year}${section}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ================= STUDENT ================= */
RENDER.overview = async (main) => {
  const d = await api("/student/dashboard");
  const att = d.attendance, ht = d.hall_ticket, sch = d.scholarship;
  const pendingFees = d.fees.items.filter(f => f.status !== "paid");
  main.innerHTML = `<div class="grid">
    <div class="card">
      <h3>Attendance <span class="sub">· Attendance Agent</span></h3>
      <div class="stat ${att.overall < 75 ? "bad" : "good"}">${att.overall}%</div>
      <div class="stat-label">overall · requirement 75%</div>
      ${att.subjects.map(s => `<div class="kv"><span>${esc(s.subject)}</span>
        <span class="v">${s.attended}/${s.held} · ${s.pct}%</span></div>
        <div class="mini-bar"><i class="${s.pct < 75 ? "low" : ""}" style="width:${s.pct}%"></i></div>`).join("")}
    </div>
    <div class="card">
      <h3>Hall Ticket <span class="sub">· Exam Agent</span></h3>
      <div class="stat ${ht?.eligible ? "good" : "bad"}">${ht?.eligible ? "✓" : "✗"}</div>
      ${pill(!!ht?.eligible, "ELIGIBLE", "BLOCKED")}
      <p class="muted" style="margin-top:10px">${esc(ht?.reasons || "not evaluated")}</p>
      <h3 style="margin-top:16px">Exams <span class="sub">· sem ${d.profile.semester}</span></h3>
      ${d.exams.slice(0, 5).map(e => `<div class="kv"><span>${esc(e.subject)}</span>
        <span class="v">${esc(e.date)}</span></div>`).join("")}
    </div>
    <div class="card">
      <h3>Scholarship <span class="sub">· CART model</span></h3>
      <div class="stat ${sch?.status === "eligible" ? "good" : sch?.status === "waitlist" ? "warn" : "bad"}">
        ${sch ? ({eligible:"✓", waitlist:"…", not_eligible:"✗"})[sch.status] : "—"}</div>
      <p class="muted" style="margin-top:8px">${esc(sch?.reasons || "")}</p>
      <h3 style="margin-top:16px">Profile</h3>
      <div class="kv"><span>USN</span><span class="v">${esc(d.profile.usn)}</span></div>
      <div class="kv"><span>Programme</span><span class="v">${esc(d.profile.dept)} · Year ${d.profile.year} ${esc(d.profile.section)}</span></div>
      <div class="kv"><span>CGPA</span><span class="v">${d.profile.cgpa}</span></div>
      <div class="kv"><span>Backlogs</span><span class="v">${d.profile.backlogs}</span></div>
    </div>
    <div class="card">
      <h3>Fees <span class="sub">· Finance Agent</span></h3>
      ${pendingFees.length === 0 ? `<div class="stat good">✓</div><p class="muted">All fees cleared.</p>` :
        `<div class="stat bad">₹${d.fees.total_outstanding.toLocaleString()}</div>
         <div class="stat-label">outstanding</div>` +
        pendingFees.map(f => `<div class="kv"><span>${esc(f.type)}${f.fine ? ` <span class="pill bad">fine ₹${f.fine.toLocaleString()}</span>` : ""}</span>
          <span class="v">₹${f.amount_due.toLocaleString()}
          <button class="btn tiny gold" onclick="payFee(${f.id})">Pay</button></span></div>`).join("")}
    </div>
    <div class="card span2">
      <h3>Internal Marks (CIE) <span class="sub">· Academic Agent</span></h3>
      <table><tr><th>Subject</th><th>CIE-1</th><th>CIE-2</th><th>CIE-3</th><th>Avg</th></tr>
      ${d.marks.map(m => `<tr><td>${esc(m.subject)}<br><span class="muted">${esc(m.name)}</span></td>
        <td>${m.internals["CIE-1"] ?? "—"}</td><td>${m.internals["CIE-2"] ?? "—"}</td>
        <td>${m.internals["CIE-3"] ?? "—"}</td><td><b>${m.cie_average ?? "—"}</b></td></tr>`).join("")}
      </table>
    </div>
    <div class="card span2">
      <h3>Placements <span class="sub">· Random Forest ranking</span></h3>
      ${d.profile.year !== 4 ? `<p class="muted">Placement drives open in final year. ${d.placements.length} drives currently running for the 4th years.</p>` : ""}
      <table><tr><th>Company</th><th>Package</th><th>Date</th><th>Status</th><th>Prob.</th></tr>
      ${d.placements.slice(0, 6).map(p => `<tr><td>${esc(p.company)}<br><span class="muted">${esc(p.role)}</span></td>
        <td>${p.package_lpa} LPA</td><td>${esc(p.date)}</td>
        <td>${pill(p.eligible, "ELIGIBLE", "—")}</td>
        <td>${p.probability != null ? Math.round(p.probability * 100) + "%" : "—"}</td></tr>`).join("")}
      </table>
    </div>
    <div class="card span4">
      <h3>Notices <span class="sub">· Notification Agent</span></h3>
      ${d.notifications.length === 0 ? `<p class="muted">No notifications yet.</p>` :
        d.notifications.map(n => `<div class="kv"><span><b>${esc(n.title)}</b><br>
          <span class="muted">${esc(n.message)}</span></span>
          <span class="muted">${esc(n.at.slice(0, 16))}</span></div>`).join("")}
    </div>
  </div>`;
};

window.payFee = async (feeId) => {
  const r = await api("/student/pay-fee", { body: { fee_id: feeId } });
  alert(r.ok ? `Paid ₹${r.paid.toLocaleString()} (${r.fee_type}). Eligibility re-evaluated automatically.` : r.error);
  selectTab("overview");
};

RENDER.timetable = async (main) => {
  if (USER.role === "student") {
    const d = await api("/student/dashboard");
    const g = d.timetable;
    main.innerHTML = `<div class="card span4">
      <h3>Weekly Timetable — ${esc(g.dept)} Year ${g.year} Section ${esc(g.section)}
        <span class="sub">· Timetable Agent (conflict-free by construction)</span></h3>
      <div class="action-row">
        <button class="btn gold tiny" id="dl-btn">Download CSV</button>
        <button class="btn ghost tiny" onclick="window.print()">Print</button>
      </div>${ttTable(g)}</div>`;
    $("dl-btn").onclick = () => downloadCsv(g.dept, g.year, g.section);
  } else {
    const o = await api("/faculty/overview");
    main.innerHTML = `<div class="card span4">
      <h3>My Teaching Timetable</h3>${ttTable(o.timetable, true)}</div>`;
  }
};

/* ================= FACULTY ================= */
RENDER.classes = async (main) => {
  const o = await api("/faculty/overview");
  const opts = o.assignments.map((a, i) =>
    `<option value="${i}">${esc(a.subject)} — ${esc(a.dept)} Year ${a.year} ${esc(a.section)} (${esc(a.subject_name)})</option>`).join("");
  main.innerHTML = `<div class="grid">
    <div class="card span2">
      <h3>My Teaching Assignments</h3>
      ${o.assignments.map(a => `<div class="kv"><span>${esc(a.subject)} · ${esc(a.subject_name)}</span>
        <span class="v">${esc(a.dept)} ${a.year}${esc(a.section)} · ${a.credits} hrs/wk</span></div>`).join("")}
      <h3 style="margin-top:16px">Notices</h3>
      ${o.notifications.slice(0, 5).map(n => `<div class="kv"><span><b>${esc(n.title)}</b><br>
        <span class="muted">${esc(n.message)}</span></span></div>`).join("") || '<p class="muted">None.</p>'}
    </div>
    <div class="card span2">
      <h3>Mark Attendance <span class="sub">· fires the live agent cascade</span></h3>
      <div class="action-row">
        <select id="cls-select">${opts}</select>
        <input type="date" id="att-date" value="${new Date().toISOString().slice(0, 10)}" style="padding:9px">
      </div>
      <div id="roster-box"><p class="muted">Choose a class to load the roster.</p></div>
      <pre id="att-result" class="mono hidden"></pre>
    </div>
  </div>`;
  const load = async () => {
    const a = o.assignments[+$("cls-select").value];
    if (!a) return;
    const r = await api(`/faculty/roster/${a.dept}/${a.year}/${a.section}`);
    $("roster-box").innerHTML = `
      <p class="muted">Tick students who are <b>absent</b>, then submit.</p>
      <div style="max-height:300px;overflow-y:auto;margin:8px 0">
      <table><tr><th></th><th>USN</th><th>Name</th><th>Att%</th></tr>
      ${r.roster.map(s => `<tr><td><input type="checkbox" class="abs" value="${esc(s.usn)}"></td>
        <td>${esc(s.usn)}</td><td>${esc(s.name)}</td>
        <td>${s.attendance}%</td></tr>`).join("")}</table></div>
      <button class="btn primary" id="submit-att">Submit attendance (${r.roster.length} students)</button>`;
    $("submit-att").onclick = async () => {
      const absent = [...document.querySelectorAll(".abs:checked")].map(c => c.value);
      const t0 = performance.now();
      try {
        const res = await api("/faculty/attendance", { body: {
          dept: a.dept, year: a.year, section: a.section,
          subject_code: a.subject, date: $("att-date").value,
          absent_usns: absent } });
        const box = $("att-result");
        box.classList.remove("hidden");
        let txt = `accepted ${res.accepted} · rejected ${res.rejected.length} · round-trip ${(performance.now() - t0).toFixed(0)} ms`;
        if (res.workflow_id) {
          const t = await api("/workflows/" + res.workflow_id);
          txt += `\nworkflow ${res.workflow_id}\n` + t.events.map(e =>
            `  +${String(e.elapsed_ms.toFixed(1)).padStart(8)} ms  ${e.agent.padEnd(20)} ${e.topic}`).join("\n");
        } else if (res.rejected.length && res.rejected[0].reason === "duplicate entry") {
          txt += `\nAll records were duplicates for this date — duplicate prevention working.`;
        }
        box.textContent = txt;
      } catch (e) { alert(e.message); }
    };
  };
  $("cls-select").onchange = load;
  if (o.assignments.length) load();
};

/* ================= HOD ================= */
RENDER.dept = async (main) => {
  const d = await api("/hod/analytics");
  main.innerHTML = `<div class="grid">
    <div class="card"><h3>Students</h3><div class="stat">${d.students}</div>
      <div class="stat-label">${esc(d.dept)} department</div></div>
    <div class="card"><h3>Avg attendance</h3>
      <div class="stat ${d.avg_attendance < 75 ? "bad" : "good"}">${d.avg_attendance}%</div>
      <div class="stat-label">across all subjects</div></div>
    <div class="card"><h3>Avg CGPA</h3><div class="stat">${d.avg_cgpa}</div>
      <div class="stat-label">enrolled students</div></div>
    <div class="card"><h3>Attendance shortage</h3>
      <div class="stat ${d.shortage_students > 0 ? "warn" : "good"}">${d.shortage_students}</div>
      <div class="stat-label">students below 75%</div></div>
    <div class="card span2">
      <h3>Students by year</h3>
      ${[1, 2, 3, 4].map(y => barRow(`Year ${y}`, d.by_year[y] || 0,
        Math.max(...Object.values(d.by_year)), String(d.by_year[y] || 0))).join("")}
      <h3 style="margin-top:18px">Timetable <span class="sub">· Timetable Agent</span></h3>
      <div class="action-row">
        <select id="tt-sec">${d.sections.map(s =>
          `<option value="${s.year}-${s.section}">Year ${s.year} · Section ${s.section}</option>`).join("")}</select>
        <button class="btn ghost tiny" id="tt-view">View</button>
        <button class="btn gold tiny" id="tt-gen">Regenerate department timetable</button>
      </div>
      <div id="tt-out"></div>
    </div>
    <div class="card span2">
      <h3>Fee defaulters <span class="sub">· Finance Agent</span></h3>
      <table><tr><th>USN</th><th>Name</th><th>Yr</th><th>Type</th><th>Due</th><th>Fine</th></tr>
      ${d.fee_defaulters.map(f => `<tr><td>${esc(f.usn)}</td><td>${esc(f.name)}</td>
        <td>${f.year}</td><td>${esc(f.fee_type)}</td>
        <td>₹${f.amount_due.toLocaleString()}</td><td>₹${f.fine.toLocaleString()}</td></tr>`).join("")}
      </table>
    </div>
  </div>`;
  $("tt-view").onclick = async () => {
    const [y, s] = $("tt-sec").value.split("-");
    const g = await api(`/timetable/${d.dept}/${y}/${s}`);
    $("tt-out").innerHTML = ttTable(g) +
      `<div class="action-row"><button class="btn gold tiny" id="tt-dl">Download CSV</button></div>`;
    $("tt-dl").onclick = () => downloadCsv(d.dept, y, s);
  };
  $("tt-gen").onclick = async () => {
    $("tt-gen").disabled = true; $("tt-gen").textContent = "Solving…";
    const r = await api("/hod/generate-timetable", { method: "POST" });
    $("tt-gen").disabled = false; $("tt-gen").textContent = "Regenerate department timetable";
    $("tt-out").innerHTML = `<p class="muted">Solver: ${r.slots_placed}/${r.slots_required} slots placed
      (${r.placement_rate}%) · 0 teacher conflicts · ${r.restarts_used} restart(s) · ${r.solve_ms} ms</p>`;
  };
};

/* ================= PRINCIPAL / INSTITUTION ================= */
RENDER.institution = async (main) => {
  const d = await api("/principal/analytics");
  const depts = Object.entries(d.departments);
  const maxStudents = Math.max(...depts.map(([, x]) => x.students));
  const adm = d.admissions.stages;
  main.innerHTML = `<div class="grid">
    <div class="card span2">
      <h3>Average attendance by department</h3>
      ${depts.map(([c, x]) => barRow(c, x.avg_attendance, 100, x.avg_attendance + "%")).join("")}
      <h3 style="margin-top:18px">Average CGPA by department</h3>
      ${depts.map(([c, x]) => barRow(c, x.avg_cgpa, 10, String(x.avg_cgpa), true)).join("")}
    </div>
    <div class="card span2">
      <h3>Fee collection by department <span class="sub">· Finance Agent</span></h3>
      ${Object.entries(d.fee_collection).map(([c, x]) =>
        barRow(c, x.pct, 100, x.pct + "%")).join("")}
      <h3 style="margin-top:18px">Placement-eligible finalists <span class="sub">· Placement Agent</span></h3>
      ${Object.entries(d.placements.eligible_finalists_by_dept || {}).map(([c, n]) =>
        barRow(c, n, 60, String(n), true)).join("") || '<p class="muted">No data yet.</p>'}
      <p class="muted" style="margin-top:8px">${d.placements.upcoming_drives} upcoming drives</p>
    </div>
    <div class="card span4">
      <h3>Admissions funnel <span class="sub">· Admission Agent</span></h3>
      <div class="funnel">${["submitted", "verified", "merit_listed", "seat_allotted", "enrolled", "rejected"]
        .map(s => `<div class="stage"><b>${adm[s] ?? 0}</b><span>${s.replace("_", " ")}</span></div>`).join("")}</div>
      <table><tr><th>Dept</th><th>Applications</th><th>Seats allotted</th><th>Intake</th><th>Fill</th></tr>
      ${Object.entries(d.admissions.departments).map(([c, x]) =>
        `<tr><td>${c}</td><td>${x.applications}</td><td>${x.allotted}</td><td>${x.intake}</td>
         <td>${Math.round(100 * x.allotted / x.intake)}%</td></tr>`).join("")}</table>
    </div>
    <div class="card span4">
      <h3>Department headcount</h3>
      ${depts.map(([c, x]) => barRow(c, x.students, maxStudents, String(x.students))).join("")}
    </div>
  </div>`;
};

/* ================= ADMIN / ADMISSIONS ================= */
RENDER.admissions = async (main) => {
  const d = await api("/admin/admissions");
  const s = d.funnel.stages;
  main.innerHTML = `<div class="card span4">
    <h3>Admissions Pipeline <span class="sub">· Admission Agent — verify → merit → allot → enrol</span></h3>
    <div class="funnel">${["submitted", "verified", "merit_listed", "seat_allotted", "enrolled", "rejected"]
      .map(k => `<div class="stage"><b>${s[k] ?? 0}</b><span>${k.replace("_", " ")}</span></div>`).join("")}</div>
    <div class="action-row">
      <button class="btn primary tiny" id="adm-verify">1 · Verify all submitted</button>
      <button class="btn primary tiny" id="adm-merit">2 · Run merit ranking</button>
      <button class="btn gold tiny" id="adm-allot">3 · Allot seats</button>
      <select id="adm-filter">
        <option value="">All statuses</option>
        ${["submitted", "verified", "merit_listed", "seat_allotted", "enrolled", "rejected"]
          .map(x => `<option>${x}</option>`).join("")}</select>
      <button class="btn ghost tiny" id="adm-sim">Simulate attendance day (demo cascade)</button>
    </div>
    <pre id="adm-log" class="mono hidden"></pre>
    <table><tr><th>#</th><th>Applicant</th><th>Dept</th><th>Cat.</th><th>10th</th>
      <th>12th</th><th>CET</th><th>Merit</th><th>Rank</th><th>Status</th><th></th></tr>
    ${d.applications.map(a => `<tr><td>${a.id}</td><td>${esc(a.name)}</td>
      <td>${esc(a.dept)}</td><td>${esc(a.category)}</td><td>${a.tenth}</td><td>${a.twelfth}</td>
      <td>${a.entrance}</td><td>${a.merit_score ?? "—"}</td><td>${a.merit_rank ?? "—"}</td>
      <td><span class="pill ${a.status === "enrolled" ? "good" : a.status === "rejected" ? "bad" : "info"}">${esc(a.status)}</span>
      ${a.usn ? `<br><span class="muted">${esc(a.usn)}</span>` : ""}</td>
      <td>${a.status === "seat_allotted" ?
        `<button class="btn tiny gold" onclick="enrol(${a.id})">Enrol</button>` : ""}</td></tr>`).join("")}
    </table></div>`;
  const log = (t) => { const b = $("adm-log"); b.classList.remove("hidden"); b.textContent = t; };
  // Pipeline stages mutate shared state, so the whole action row locks while
  // one runs — an out-of-order click would rank or allot on partial data.
  const stageButtons = ["adm-verify", "adm-merit", "adm-allot", "adm-sim"];
  const runStage = (id, label, path) => {
    $(id).onclick = async () => {
      const original = $(id).textContent;
      stageButtons.forEach(b => $(b).disabled = true);
      $(id).textContent = label;
      try {
        log(JSON.stringify(await api(path, { method: "POST" }), null, 1));
        await selectTab("admissions");
      } catch (e) {
        log("Error: " + e.message);
        stageButtons.forEach(b => $(b) && ($(b).disabled = false));
        $(id).textContent = original;
      }
    };
  };
  runStage("adm-verify", "Verifying…", "/admin/admissions/verify-all");
  runStage("adm-merit", "Ranking…", "/admin/admissions/run-merit");
  runStage("adm-allot", "Allotting…", "/admin/admissions/allot");
  $("adm-sim").onclick = async () => {
    const r = await api("/admin/simulate-day", { method: "POST" });
    let txt = `accepted ${r.accepted} records`;
    if (r.workflow_id) {
      const t = await api("/workflows/" + r.workflow_id);
      txt += `\n` + t.events.map(e => `  +${String(e.elapsed_ms.toFixed(1)).padStart(8)} ms  ${e.agent.padEnd(20)} ${e.topic}`).join("\n");
    } else { txt += ` — duplicates for today (already simulated)`; }
    log(txt);
  };
  $("adm-filter").onchange = async () => {
    selectTab("admissions"); // simple refresh; server-side filter kept minimal
  };
};
window.enrol = async (id) => {
  const r = await api("/admin/admissions/enrol", { body: { application_id: id } });
  alert(r.ok ? `Enrolled. USN ${r.usn} created, login + first-term fee issued, cascade fired.` : r.error);
  selectTab("admissions");
};

/* ================= ASSISTANT ================= */
const SUGGESTIONS = {
  student: ["What is my attendance percentage?", "Will I get my hall ticket?",
            "Show my internal marks", "What classes do I have this week?",
            "Am I eligible for the scholarship?", "Any pending fees?",
            "When do semester exams start?", "Which placement drives can I sit for?"],
  faculty: ["Show my timetable", "Department analytics",
            "Any notifications for me?"],
  hod: ["How is my department performing?", "Who are the fee defaulters?",
        "Show my timetable"],
  principal: ["Institution analytics", "Admissions funnel status",
              "Placement statistics"],
  admin: ["Admissions funnel status", "Institution analytics",
          "Fee defaulters"],
};
RENDER.assistant = async (main) => {
  main.innerHTML = `<div class="chat-card">
    <div class="chat-head">
      <div><h2 class="serif">MAWOS Assistant</h2>
        <p class="muted">Orchestrator Agent · ${AI_MODE === "llm"
          ? "confidence-gated hybrid — the lexicon answers, uncertain queries escalate to the local LLM"
          : "lexicon only (install Ollama to enable escalation)"}</p></div>
      <span class="ai-badge ${AI_MODE}">${AI_MODE === "llm" ? "hybrid" : "lexicon"}</span>
    </div>
    <div id="chat-log" class="chat-log">
      <div class="msg agent"><div class="msg-meta">orchestrator_agent</div>Good day, ${esc(USER.name.split(" ")[0])}. Ask me anything about your ${USER.role === "student" ? "studies — attendance, fees, marks, timetable, exams, scholarship, placements" : "institution data"}.</div>
    </div>
    <div class="chat-input">
      <input id="chat-text" placeholder="Ask the assistant…">
      <button id="chat-send" class="btn primary">Send</button>
    </div>
    <div class="chips" id="chat-chips"></div>
  </div>`;
  const chips = $("chat-chips");
  (SUGGESTIONS[USER.role] || []).forEach(s => {
    const b = document.createElement("button");
    b.textContent = s;
    b.onclick = () => { $("chat-text").value = s; sendChat(); };
    chips.appendChild(b);
  });
  $("chat-send").onclick = sendChat;
  $("chat-text").addEventListener("keydown", e => e.key === "Enter" && sendChat());
};
function addMsg(kind, text, meta) {
  const log = $("chat-log");
  const div = document.createElement("div");
  div.className = "msg " + kind;
  div.innerHTML = (meta ? `<div class="msg-meta"></div>` : "") + `<div class="msg-body"></div>`;
  if (meta) div.querySelector(".msg-meta").textContent = meta;
  div.querySelector(".msg-body").textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}
async function sendChat() {
  const text = $("chat-text").value.trim();
  if (!text) return;
  $("chat-text").value = "";
  addMsg("user", text);
  const thinking = addMsg("agent", "…", "orchestrator_agent");
  try {
    const r = await api("/chat", { body: { message: text } });
    thinking.querySelector(".msg-body").textContent = r.text;
    const tools = (r.tools_used || []).map(t => t.name).join(" → ") || "no tools";
    thinking.querySelector(".msg-meta").textContent =
      `${r.mode === "llm" ? "LLM (" + (r.model || "local") + ")" : "lexicon · intent: " + r.intent}`
      + (r.routing ? ` · margin ${r.routing.margin.toFixed(2)} vs τ ${r.routing.tau.toFixed(2)}`
                     + (r.routing.fallback_from ? " · escalation failed" : "") : "")
      + ` · tools: ${tools} · ${r.latency_ms} ms`;
  } catch (e) { thinking.querySelector(".msg-body").textContent = "Error: " + e.message; }
}

/* ================= SYSTEM (research view) ================= */
RENDER.system = async (main) => {
  const [m, ag, wf] = await Promise.all([
    api("/metrics/summary"), api("/agents"), api("/workflows/recent")]);
  const i = m.intent, p = m.propagation;
  main.innerHTML = `<div class="grid">
    <div class="card"><h3>Intent decisions</h3><div class="stat">${i.total_classifications || 0}</div>
      <div class="stat-label">avg ${i.avg_classify_latency_ms ?? "—"} ms</div></div>
    <div class="card"><h3>Escalation rate</h3>
      <div class="stat">${i.escalation_rate != null ? Math.round(i.escalation_rate * 100) + "%" : "—"}</div>
      <div class="stat-label">${m.router ? "τ " + m.router.tau.toFixed(2) + " · tuned for "
        + Math.round(m.router.escalation_rate_dev * 100) + "% on dev" : "lexicon answers the rest"}</div></div>
    <div class="card"><h3>Cascades measured</h3>
      <div class="stat">${p.cascades_measured || 0}</div>
      <div class="stat-label">avg ${p.avg_cascade_ms ?? "—"} ms · p95 ${p.p95_cascade_ms ?? "—"} ms</div></div>
    <div class="card"><h3>Bus events</h3><div class="stat">${m.bus_events_logged}</div>
      <div class="stat-label">${m.notifications_generated} notifications generated</div></div>
    <div class="card span2">
      <h3>Recent workflow cascades <span class="sub">· click to trace</span></h3>
      <div id="workflow-list">${wf.workflows.map(w => `
        <div class="wf-row" data-wid="${esc(w.workflow_id)}">
          <span class="mono-id">${esc(w.workflow_id.slice(0, 8))}</span>
          <span class="muted">${esc(w.started_at.slice(5, 19))}</span>
          <span>${w.events} ev · ${w.depth_hops} hops</span>
          <span><b>${w.duration_ms} ms</b></span></div>`).join("") ||
        '<p class="muted">No cascades yet — mark attendance or run a simulation.</p>'}</div>
    </div>
    <div class="card span2">
      <h3>Workflow timeline <span class="sub" id="trace-id"></span></h3>
      <div id="workflow-trace" class="timeline"><p class="muted">Select a workflow.</p></div>
    </div>
    <div class="card span4"><h3>The agents (${ag.agents.length})</h3>
      <div class="agents-grid">${ag.agents.map(a =>
        `<div class="agent-tile"><b>${esc(a.name)}</b><p>${esc(a.description)}</p></div>`).join("")}</div>
    </div>
  </div>`;
  document.querySelectorAll(".wf-row").forEach(row => row.onclick = async () => {
    document.querySelectorAll(".wf-row").forEach(r => r.classList.remove("active"));
    row.classList.add("active");
    const t = await api("/workflows/" + row.dataset.wid);
    $("trace-id").textContent = "· " + row.dataset.wid.slice(0, 13);
    $("workflow-trace").innerHTML = t.events.map(e => `
      <div class="tl-item"><span class="tl-time">+${e.elapsed_ms.toFixed(1)} ms</span>
        <span class="tl-agent"> ${esc(e.agent)}</span>
        <span class="tl-topic">hop ${e.hop}</span>
        <div class="tl-topic">${esc(e.topic)}</div></div>`).join("");
  });
};

/* ---------------- wire up ---------------- */
$("login-btn").onclick = () => login();
$("login-password").addEventListener("keydown", e => e.key === "Enter" && login());
document.querySelectorAll(".demo-chips button").forEach(b =>
  b.onclick = () => login(b.dataset.u, b.dataset.p));
$("logout-btn").onclick = logout;

if (TOKEN && USER) showApp();
