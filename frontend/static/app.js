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
              ["library", "Library"], ["assistant", "Assistant"], ["system", "System"]],
  faculty:   [["classes", "My Classes"], ["timetable", "My Timetable"],
              ["assistant", "Assistant"], ["system", "System"]],
  hod:       [["dept", "Department"], ["classes", "My Classes"],
              ["assistant", "Assistant"], ["system", "System"]],
  principal: [["institution", "Institution"], ["assistant", "Assistant"],
              ["system", "System"]],
  admin:     [["admissions", "Admissions"], ["institution", "Institution"],
              ["assistant", "Assistant"], ["system", "System"]],
  librarian: [["desk", "Library Desk"], ["assistant", "Assistant"], ["system", "System"]],
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
    <div class="card">
      <h3>Library <span class="sub">· Library Agent</span></h3>
      ${d.library.borrowed.length === 0 ? `<p class="muted">No books currently borrowed.</p>` :
        d.library.borrowed.map(b => `<div class="kv"><span>${esc(b.title)}</span>
          <span class="v">due ${esc(b.due_date.slice(0, 10))}</span></div>`).join("")}
      ${d.library.fines.total_unpaid > 0
        ? `<div class="kv" style="margin-top:8px"><span>Outstanding fines</span>
           <span class="v pill bad">₹${d.library.fines.total_unpaid.toLocaleString()}</span></div>`
        : `<p class="muted" style="margin-top:8px">No outstanding library fines.</p>`}
      <button class="btn ghost tiny" style="margin-top:10px" onclick="selectTab('library')">Open Library</button>
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

/* ================= STUDENT: LIBRARY ================= */
RENDER.library = async (main) => {
  const [books, reqs, borrowed, fines, recs] = await Promise.all([
    api("/library/books?limit=12"),
    api("/student/library/requests").catch(() => ({ items: [] })),
    api("/student/library/borrowed"),
    api("/student/library/fines"),
    api("/student/library/recommendations"),
  ]);
  const pendingReqs = (reqs.items || []).filter(r => r.status === "pending");
  main.innerHTML = `<div class="grid">
    <div class="card span2">
      <h3>Search the Catalogue <span class="sub">· Library Agent</span></h3>
      <div class="action-row">
        <input id="lib-q" placeholder="Search title, author or category…" style="flex:1;padding:9px">
        <button class="btn gold tiny" id="lib-search-btn">Search</button>
      </div>
      <div id="lib-results">${bookListHtml(books.items)}</div>
    </div>
    <div class="card">
      <h3>My Reservations <span class="sub">· show your slip to the librarian to collect</span></h3>
      ${pendingReqs.length === 0 ? `<p class="muted">No pending reservations.</p>` :
        pendingReqs.map(r => `<div class="kv"><span>${esc(r.title || ("Book #" + r.book_id))}<br>
          <span class="muted">pickup by ${esc(String(r.pickup_deadline).slice(0, 16))}</span></span>
          <span class="v">
            <button class="btn tiny gold" onclick="libShowSlip(${r.id})">View Slip</button>
            <button class="btn tiny ghost" onclick="libCancel(${r.id})">Cancel</button>
          </span></div>
        <div id="slip-${r.id}" class="hidden mono" style="padding:10px;margin:6px 0;border:1px dashed var(--border);border-radius:8px"></div>`).join("")}
    </div>
    <div class="card">
      <h3>Currently Borrowed</h3>
      <div id="lib-borrowed">${borrowedListHtml(borrowed.items)}</div>
    </div>
    <div class="card">
      <h3>Fines <span class="sub">· auto-generated by the agent</span></h3>
      ${fines.total === 0 ? `<div class="stat good">✓</div><p class="muted">No library fines.</p>` :
        `<div class="stat ${fines.total_unpaid > 0 ? "bad" : "good"}">₹${fines.total_unpaid.toLocaleString()}</div>
         <div class="stat-label">outstanding${fines.total_unpaid >= fines.threshold ? " — at/above the reservation limit" : ""}</div>` +
        fines.items.map(f => `<div class="kv"><span>${esc(f.reason)}</span>
          <span class="v">₹${f.amount.toLocaleString()} ${pill(f.status === "paid", "PAID", "UNPAID")}</span></div>`).join("")}
    </div>
    <div class="card span2">
      <h3>Recommended for You <span class="sub">· explainable, no black-box model</span></h3>
      ${recBlockHtml("Personalized", "history + branch match", recs.personalized)}
      ${recBlockHtml("Trending in your branch", "most borrowed among books relevant to you right now", recs.trending_in_branch, true)}
      ${recBlockHtml("Most borrowed overall", "institution-wide, any branch", recs.most_borrowed_overall, true)}
    </div>
  </div>`;

  const runSearch = async () => {
    const q = $("lib-q").value.trim();
    const res = await api("/library/books?q=" + encodeURIComponent(q) + "&limit=12");
    $("lib-results").innerHTML = bookListHtml(res.items);
  };
  $("lib-search-btn").onclick = runSearch;
  $("lib-q").onkeydown = (e) => { if (e.key === "Enter") runSearch(); };
};

function ratingStars(avg) {
  if (avg === null || avg === undefined) return "";
  return ` <span class="pill">★ ${avg}</span>`;
}

function recBlockHtml(title, sub, items, trending = false) {
  const body = !items || items.length === 0
    ? `<p class="muted">Nothing to show yet.</p>`
    : items.map(r => trending
        ? `<div class="kv"><span>${esc(r.title)} <span class="pill info">${esc(r.category)}</span>${ratingStars(r.avg_rating)}<br>
            <span class="muted">borrowed ${r.popularity_count} times</span></span></div>`
        : `<div class="kv"><span>${esc(r.title)} <span class="pill info">${esc(r.category)}</span>${ratingStars(r.avg_rating)}<br>
            <span class="muted">${esc(r.reason.join(" · "))}</span></span>
            <span class="v">score ${r.score}</span></div>`).join("");
  return `<h4 style="margin:14px 0 4px">${title} <span class="sub">· ${sub}</span></h4>${body}`;
}

function bookListHtml(items) {
  if (!items.length) return `<p class="muted">No books found.</p>`;
  return items.map(b => `<div class="kv"><span>${esc(b.title)} <span class="pill info">${esc(b.category)}</span>${ratingStars(b.avg_rating)}<br>
      <span class="muted">${esc(b.author)} · ${b.available_copies}/${b.total_copies} available</span></span>
      <span class="v">
        <button class="btn tiny ghost" onclick="libShowReviews(${b.id})">Reviews</button>
        <button class="btn tiny gold" ${b.available_copies === 0 ? "disabled" : ""}
          onclick="libRequest(${b.id})">Reserve</button>
      </span></div>
    <div id="reviews-${b.id}" class="hidden" style="padding:6px 0 12px"></div>`).join("");
}

function borrowedListHtml(items) {
  if (!items.length) return `<p class="muted">No books currently borrowed.</p>`;
  return items.map(b => {
    if (b.status === "return_pending") {
      return `<div class="kv"><span>${esc(b.title)}<br>
          <span class="muted">return submitted ${esc(String(b.return_requested_at).slice(0, 16))} — awaiting librarian confirmation</span></span>
          <span class="v">${pill(false, "PENDING", "PENDING")}</span></div>`;
    }
    return `<div class="kv" id="borrowed-${b.id}"><span>${esc(b.title)}<br>
        <span class="muted">due ${esc(b.due_date.slice(0, 10))}</span></span>
        <span class="v"><button class="btn tiny gold" onclick="libShowReturn(${b.id})">Return</button></span></div>
      <div id="return-form-${b.id}" class="hidden" style="padding:8px 0 14px">
        <div class="action-row">
          <select id="rating-${b.id}" style="padding:8px">
            <option value="">No review</option>
            <option value="5">★★★★★ Excellent</option>
            <option value="4">★★★★ Good</option>
            <option value="3">★★★ Okay</option>
            <option value="2">★★ Not great</option>
            <option value="1">★ Poor</option>
          </select>
          <input id="comment-${b.id}" placeholder="Optional comment…" style="flex:1;padding:8px">
          <button class="btn tiny gold" onclick="libReturn(${b.id})">Submit Return Request</button>
        </div>
      </div>`;
  }).join("");
}

window.libRequest = async (bookId) => {
  try {
    const r = await api("/library/requests", { body: { book_id: bookId } });
    alert(r.ok ? `Reserved — pick up by ${String(r.pickup_deadline).slice(0, 16)}. See "My Reservations" for your slip.` : r.error);
  } catch (e) { alert(e.message); }
  selectTab("library");
};
window.libCancel = async (requestId) => {
  try {
    const r = await api(`/library/requests/${requestId}/cancel`, { body: {} });
    if (!r.ok) alert(r.error);
  } catch (e) { alert(e.message); }
  selectTab("library");
};
window.libShowSlip = async (requestId) => {
  const el = document.getElementById(`slip-${requestId}`);
  if (!el) return;
  if (!el.classList.contains("hidden")) { el.classList.add("hidden"); return; }
  const slip = await api(`/library/requests/${requestId}/slip`);
  el.innerHTML = slip.ok
    ? `ACKNOWLEDGEMENT SLIP — #${slip.request_id}<br>Student: ${esc(slip.student_name)} (${esc(slip.usn)})<br>` +
      `Book: ${esc(slip.book_title)} — ${esc(slip.book_author)}<br>Requested: ${esc(String(slip.requested_at).slice(0, 16))}<br>` +
      `Pickup by: ${esc(String(slip.pickup_deadline).slice(0, 16))}<br>` +
      `<div style="margin:10px 0;padding:10px;text-align:center;font-size:22px;letter-spacing:4px;
           border:1px solid var(--border);border-radius:6px;background:var(--panel-2, rgba(0,0,0,.03))">
         ${esc(slip.slip_code || "------")}</div>` +
      `<em>Show this code to the librarian to collect your book.</em><br>` +
      `<button class="btn tiny gold" style="margin-top:8px" onclick="libDownloadSlipPdf(${slip.request_id})">Download PDF slip</button>`
    : esc(slip.error);
  el.classList.remove("hidden");
};
window.libDownloadSlipPdf = async (requestId) => {
  const res = await fetch(`/api/library/requests/${requestId}/slip/pdf`,
    { headers: { Authorization: "Bearer " + TOKEN } });
  if (!res.ok) { alert("Could not generate the PDF slip."); return; }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `library_slip_${requestId}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
};
window.libShowReviews = async (bookId) => {
  const el = document.getElementById(`reviews-${bookId}`);
  if (!el) return;
  if (!el.classList.contains("hidden")) { el.classList.add("hidden"); return; }
  const res = await api(`/library/books/${bookId}/reviews`);
  el.innerHTML = res.items.length === 0 ? `<p class="muted">No reviews yet.</p>` :
    res.items.map(r => `<div class="kv"><span>${"★".repeat(r.rating)}${"☆".repeat(5 - r.rating)} — ${esc(r.student_name)}<br>
      <span class="muted">${r.comment ? esc(r.comment) : "(no comment)"}</span></span></div>`).join("");
  el.classList.remove("hidden");
};
window.libShowReturn = (issueId) => {
  const form = document.getElementById(`return-form-${issueId}`);
  if (form) form.classList.toggle("hidden");
};
window.libReturn = async (issueId) => {
  const ratingEl = document.getElementById(`rating-${issueId}`);
  const commentEl = document.getElementById(`comment-${issueId}`);
  const rating = ratingEl && ratingEl.value ? parseInt(ratingEl.value, 10) : null;
  const comment = commentEl ? commentEl.value.trim() : "";
  try {
    const r = await api("/library/return-request", { body: { issue_id: issueId, rating, comment: comment || null } });
    alert(r.ok
      ? `Return request submitted.${r.review_saved ? " Thanks for the review!" : ""} Hand the book to the librarian to complete it.`
      : r.error);
  } catch (e) { alert(e.message); }
  selectTab("library");
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
        <button class="btn ghost tiny" id="tt-sim">Watch solver (live simulation)</button>
      </div>
      <div id="tt-out"></div>
      <div id="sim-out"></div>
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
  $("tt-sim").onclick = async () => {
    const [y, s] = $("tt-sec").value.split("-");
    await runLiveSimulation(d.dept, y, s);
  };
};

/* Replays the real P1 solver's own event trace (seed placements, then the
 * actual cost/temperature curve from simulated annealing) so the user can
 * watch the timetable for one section get built. This regenerates the
 * WHOLE department (same as "Regenerate department timetable") — the
 * animation just focuses on one section's slice of the trace. */
async function runLiveSimulation(dept, year, section) {
  const btn = $("tt-sim");
  btn.disabled = true; btn.textContent = "Solving…";
  const out = $("sim-out");
  out.innerHTML = `<p class="muted">Running the solver…</p>`;
  let r;
  try {
    r = await api("/hod/generate-timetable-live", { method: "POST" });
  } catch (e) {
    btn.disabled = false; btn.textContent = "Watch solver (live simulation)";
    out.innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`;
    return;
  }
  btn.disabled = false; btn.textContent = "Watch solver (live simulation)";

  const key = `${dept}-${year}-${section}`;
  const events = r.seed_events.filter(e => e.section === key);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const PERIODS = ["9:00", "10:00", "11:15", "12:15", "14:00", "15:00"];

  out.innerHTML = `
    <div class="sim-wrap">
      <div class="sim-status">
        <span class="sim-phase on" id="sim-phase">Phase: Seeding</span>
        <span class="sim-stat" id="sim-count">placed 0 / ${events.length}</span>
      </div>
      <div class="tt-wrap" id="sim-grid-wrap"><table class="tt">
        <tr><th>Day</th>${PERIODS.map(p => `<th>${esc(p)}</th>`).join("")}</tr>
        ${DAYS.map((day, d) => `<tr><th>${esc(day)}</th>${PERIODS.map((_, p) =>
          `<td class="free" data-cell="${d}-${p}"></td>`).join("")}</tr>`).join("")}
      </table></div>
      <div class="sim-chart-wrap">
        <div class="sim-chart-label"><span>Simulated annealing — cost vs. temperature</span>
          <span id="sim-chart-readout">—</span></div>
        <svg viewBox="0 0 600 110" preserveAspectRatio="none">
          <polyline id="sim-cost-line" fill="none" stroke="var(--data)" stroke-width="2"/>
          <polyline id="sim-temp-line" fill="none" stroke="var(--gold)" stroke-width="1.5" stroke-dasharray="4 3"/>
        </svg>
      </div>
      <p class="muted" id="sim-final"></p>
    </div>`;

  for (const ev of events) {
    const cell = out.querySelector(`[data-cell="${ev.day}-${ev.period}"]`);
    cell.classList.remove("free");
    cell.classList.add("placing");
    cell.innerHTML = `<div class="subj">${esc(ev.subject)}</div>`;
    $("sim-count").textContent = `placed ${events.indexOf(ev) + 1} / ${events.length}`;
    await new Promise(res => setTimeout(res, 40));
  }

  $("sim-phase").textContent = "Phase: Annealing";
  const trace = r.anneal_trace;
  const maxCost = Math.max(...trace.map(t => t.cost), 1);
  const maxTemp = Math.max(...trace.map(t => t.temp), 1);
  const toXY = (i, v, max) => `${(600 * i / (trace.length - 1)).toFixed(1)},${(108 - 100 * v / max).toFixed(1)}`;
  const costPts = [], tempPts = [];
  const costLine = $("sim-cost-line"), tempLine = $("sim-temp-line"), readout = $("sim-chart-readout");
  const step = Math.max(1, Math.floor(trace.length / 150));
  for (let i = 0; i < trace.length; i += step) {
    costPts.push(toXY(i, trace[i].cost, maxCost));
    tempPts.push(toXY(i, trace[i].temp, maxTemp));
    costLine.setAttribute("points", costPts.join(" "));
    tempLine.setAttribute("points", tempPts.join(" "));
    readout.textContent = `cost ${trace[i].cost.toFixed(1)} · T ${trace[i].temp.toFixed(3)} · best ${trace[i].best.toFixed(1)}`;
    await new Promise(res => setTimeout(res, 20));
  }

  $("sim-phase").textContent = "Done"; $("sim-phase").classList.remove("on");
  const g = await api(`/timetable/${dept}/${year}/${section}`);
  out.querySelector("#sim-grid-wrap").outerHTML = ttTable(g);
  $("sim-final").textContent =
    `Final: ${r.slots_placed}/${r.slots_required} slots placed (${r.placement_rate}%) · ` +
    `objective ${r.objective} (seed ${r.objective_at_seed}) · 0 teacher conflicts · ${r.solve_ms} ms total`;
}

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

/* ================= LIBRARIAN ================= */
RENDER.desk = async (main) => {
  const [pickups, returns, reqs, issues, overdue, fines, reviews] = await Promise.all([
    api("/librarian/library/pickups/pending"),
    api("/librarian/library/returns/pending"),
    api("/librarian/library/requests"),
    api("/librarian/library/issues"),
    api("/librarian/library/overdue"),
    api("/librarian/library/fines"),
    api("/librarian/library/reviews"),
  ]);
  main.innerHTML = `<div class="grid">
    <div class="card">
      <h3>Pending Pickups <span class="sub">· confirm once you've handed the book over</span></h3>
      <div class="action-row">
        <input id="verify-code" placeholder="6-digit slip code" maxlength="6" style="width:150px;padding:8px">
        <button class="btn ghost tiny" id="verify-btn">Verify Slip</button>
      </div>
      <div id="verify-result" style="margin:4px 0 10px"></div>
      ${pickups.items.length === 0 ? `<p class="muted">Nothing waiting for pickup.</p>` :
        pickups.items.map(r => `<div class="kv"><span>${esc(r.title)} — ${esc(r.student_name)}<br>
          <span class="muted">slip code <b class="mono">${esc(r.slip_code || "——————")}</b> · pickup by ${esc(String(r.pickup_deadline).slice(0, 16))}</span></span>
          <span class="v"><button class="btn tiny gold" onclick="deskConfirmPickup(${r.id})">Confirm Pickup</button></span></div>`).join("")}
    </div>
    <div class="card">
      <h3>Pending Returns <span class="sub">· confirm once the book is physically back</span></h3>
      ${returns.items.length === 0 ? `<p class="muted">No return requests waiting.</p>` :
        returns.items.map(i => `<div class="kv"><span>${esc(i.title)} — ${esc(i.student_name)}${i.review ? ` <span class="pill info">${"★".repeat(i.review.rating)}</span>` : ""}<br>
          <span class="muted">requested ${esc(String(i.return_requested_at).slice(0, 16))}</span></span>
          <span class="v">
            <button class="btn tiny gold" onclick="deskConfirmReturn(${i.id})">Confirm</button>
            <button class="btn tiny ghost" onclick="deskRejectReturn(${i.id})">Reject</button>
          </span></div>`).join("")}
    </div>
    <div class="card span2">
      <h3>Catalogue Management <span class="sub">· add stock, edit, or remove a title</span></h3>
      <div class="action-row">
        <input id="nb-isbn" placeholder="ISBN" style="width:140px;padding:8px">
        <input id="nb-title" placeholder="Title" style="flex:1;padding:8px">
        <input id="nb-author" placeholder="Author" style="width:140px;padding:8px">
      </div>
      <div class="action-row">
        <input id="nb-category" placeholder="Category (e.g. Machine Learning)" style="flex:1;padding:8px">
        <input id="nb-dept" placeholder="Dept codes, comma-sep (e.g. AIML,CSE)" style="width:220px;padding:8px">
        <input id="nb-copies" type="number" min="1" value="1" placeholder="Copies" style="width:90px;padding:8px">
        <button class="btn gold tiny" id="nb-add">Add Book</button>
      </div>
      <div class="action-row">
        <input id="lib-desk-q" placeholder="Search catalogue to edit/remove…" style="flex:1;padding:9px">
        <button class="btn ghost tiny" id="lib-desk-search-btn">Search</button>
      </div>
      <div id="lib-desk-results"><p class="muted">Search above to manage an existing book's stock.</p></div>
    </div>
    <div class="card">
      <h3>Overdue Right Now <span class="sub">· Library Agent, live</span></h3>
      ${overdue.items.length === 0 ? `<div class="stat good">✓</div><p class="muted">Nothing overdue.</p>` :
        overdue.items.map(i => `<div class="kv"><span>${esc(i.title)} — ${esc(i.student_name || i.usn)}<br>
          <span class="muted">${i.overdue_days} day(s) overdue${i.status === "return_pending" ? " · return pending confirmation" : ""}</span></span></div>`).join("")}
    </div>
    <div class="card">
      <h3>All Fines <span class="sub">· paid in person at the desk</span></h3>
      <div class="stat ${fines.total_unpaid > 0 ? "bad" : "good"}">₹${fines.total_unpaid.toLocaleString()}</div>
      <div class="stat-label">outstanding institution-wide</div>
      ${fines.items.slice(0, 8).map(f => `<div class="kv"><span>${esc(f.student_name || f.usn)} — ${esc(f.reason)}<br>
        <span class="muted">${pill(f.status === "paid", "PAID", "UNPAID")}</span></span>
        <span class="v">₹${f.amount.toLocaleString()}
          ${f.status === "unpaid" ? `<button class="btn tiny gold" onclick="deskMarkFinePaid(${f.id})">Mark Paid</button>` : ""}</span></div>`).join("")}
    </div>
    <div class="card span2">
      <h3>Counter Service <span class="sub">· walk-in issue/return, no reservation needed</span></h3>
      <div class="action-row">
        <input id="ci-usn" placeholder="Student USN" style="width:160px;padding:8px">
        <input id="ci-book" type="number" placeholder="Book ID" style="width:100px;padding:8px">
        <button class="btn gold tiny" id="ci-issue">Issue</button>
        <input id="cr-issue" type="number" placeholder="Issue ID" style="width:100px;padding:8px">
        <button class="btn ghost tiny" id="cr-return">Return</button>
      </div>
    </div>
    <div class="card span2">
      <h3>All Reservations <span class="sub">· agent-handled automatically, shown for oversight</span></h3>
      <table><tr><th>Student</th><th>Book</th><th>Status</th><th>Requested</th><th>Pickup by</th></tr>
      ${reqs.items.slice(0, 15).map(r => `<tr><td>${esc(r.student_name || r.usn)}</td>
        <td>${esc(r.title || "#" + r.book_id)}</td>
        <td><span class="pill ${r.status === "collected" ? "good" : r.status === "expired" ? "bad" : "info"}">${esc(r.status)}</span></td>
        <td>${esc(String(r.requested_at).slice(0, 16))}</td>
        <td>${esc(String(r.pickup_deadline).slice(0, 16))}</td></tr>`).join("")}
      </table>
    </div>
    <div class="card span2">
      <h3>Currently Issued</h3>
      <table><tr><th>Student</th><th>Book</th><th>Issued</th><th>Due</th><th>Status</th></tr>
      ${issues.items.slice(0, 15).map(i => `<tr><td>${esc(i.student_name || i.usn)}</td>
        <td>${esc(i.title)}</td><td>${esc(String(i.issue_date).slice(0, 10))}</td>
        <td>${esc(String(i.due_date).slice(0, 10))}</td>
        <td><span class="pill info">${esc(i.status)}</span></td></tr>`).join("")}
      </table>
    </div>
    <div class="card span2">
      <h3>Recent Reviews <span class="sub">· optional, left by students at return</span></h3>
      ${reviews.items.length === 0 ? `<p class="muted">No reviews yet.</p>` :
        reviews.items.slice(0, 10).map(r => `<div class="kv"><span>${esc(r.title)} — ${"★".repeat(r.rating)}${"☆".repeat(5 - r.rating)}<br>
          <span class="muted">${esc(r.student_name || r.usn)}${r.comment ? ": " + esc(r.comment) : ""}</span></span></div>`).join("")}
    </div>
  </div>`;

  $("verify-btn").onclick = async () => {
    const code = $("verify-code").value.trim();
    const out = $("verify-result");
    if (!/^\d{6}$/.test(code)) { out.innerHTML = `<p class="muted">Enter the 6-digit code from the slip.</p>`; return; }
    try {
      const r = await api(`/librarian/library/verify/${code}`);
      if (!r.ok) { out.innerHTML = `<p class="muted">${esc(r.error)}</p>`; return; }
      out.innerHTML = r.valid
        ? `<div class="kv"><span>${pill(true, "VALID", "")} ${esc(r.title)} — ${esc(r.student_name)} (${esc(r.usn)})<br>
             <span class="muted">pickup by ${esc(String(r.pickup_deadline).slice(0, 16))}</span></span>
             <span class="v"><button class="btn tiny gold" onclick="deskConfirmPickup(${r.request_id})">Confirm Pickup</button></span></div>`
        : `<div class="kv"><span>${pill(false, "", "NOT VALID")} ${esc(r.title || "")} — ${esc(r.student_name || "")}<br>
             <span class="muted">${esc(r.error)}</span></span></div>`;
    } catch (e) { out.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  };

  $("nb-add").onclick = async () => {
    const payload = {
      isbn: $("nb-isbn").value.trim(), title: $("nb-title").value.trim(),
      author: $("nb-author").value.trim(), category: $("nb-category").value.trim(),
      dept_relevance: $("nb-dept").value.split(",").map(s => s.trim()).filter(Boolean),
      total_copies: parseInt($("nb-copies").value, 10) || 1,
    };
    if (!payload.isbn || !payload.title || !payload.author || !payload.category) {
      alert("ISBN, title, author and category are all required.");
      return;
    }
    const r = await api("/library/books", { body: payload });
    alert(r.ok ? `Added "${r.book.title}".` : r.error);
    if (r.ok) selectTab("desk");
  };

  const runDeskSearch = async () => {
    const q = $("lib-desk-q").value.trim();
    const res = await api("/library/books?q=" + encodeURIComponent(q) + "&limit=10");
    $("lib-desk-results").innerHTML = res.items.length === 0 ? `<p class="muted">No matches.</p>` :
      res.items.map(b => `<div class="kv"><span>${esc(b.title)} <span class="pill info">${esc(b.category)}</span><br>
        <span class="muted">${b.available_copies}/${b.total_copies} available</span></span>
        <span class="v">
          <button class="btn tiny ghost" onclick="deskAdjustStock(${b.id}, ${b.total_copies})">+1 copy</button>
          <button class="btn tiny ghost" onclick="deskRemoveBook(${b.id})">Remove</button>
        </span></div>`).join("");
  };
  $("lib-desk-search-btn").onclick = runDeskSearch;
  $("lib-desk-q").onkeydown = (e) => { if (e.key === "Enter") runDeskSearch(); };

  $("ci-issue").onclick = async () => {
    const r = await api("/librarian/library/issue", {
      body: { usn: $("ci-usn").value.trim(), book_id: parseInt($("ci-book").value, 10) } });
    alert(r.ok ? `Issued — due back ${String(r.due_date).slice(0, 10)}` : r.error);
    if (r.ok) selectTab("desk");
  };
  $("cr-return").onclick = async () => {
    const r = await api("/librarian/library/return", { body: { issue_id: parseInt($("cr-issue").value, 10) } });
    alert(r.ok ? (r.overdue_days > 0 ? `Returned — ${r.overdue_days} day(s) late, fine ₹${r.fine_amount}` : "Returned, no fine.") : r.error);
    if (r.ok) selectTab("desk");
  };
};
window.deskConfirmPickup = async (requestId) => {
  const r = await api(`/librarian/library/requests/${requestId}/confirm-pickup`, { body: {} });
  alert(r.ok ? `Pickup confirmed — due back ${String(r.due_date).slice(0, 10)}` : r.error);
  selectTab("desk");
};
window.deskConfirmReturn = async (issueId) => {
  const r = await api(`/librarian/library/returns/${issueId}/confirm`, { body: {} });
  alert(r.ok ? (r.overdue_days > 0 ? `Return confirmed — ${r.overdue_days} day(s) late, fine ₹${r.fine_amount}` : "Return confirmed, no fine.") : r.error);
  selectTab("desk");
};
window.deskRejectReturn = async (issueId) => {
  const reason = prompt("Why is this return claim being rejected?");
  if (!reason) return;
  const r = await api(`/librarian/library/returns/${issueId}/reject`, { body: { reason } });
  alert(r.ok ? "Return claim rejected — book stays on the student's account." : r.error);
  selectTab("desk");
};
window.deskAdjustStock = async (bookId, currentTotal) => {
  const r = await api(`/library/books/${bookId}`, { method: "PUT", body: { total_copies: currentTotal + 1 } });
  alert(r.ok ? "Stock updated — 1 copy added." : r.error);
  selectTab("desk");
};
window.deskRemoveBook = async (bookId) => {
  if (!confirm("Remove this book from the catalogue?")) return;
  const r = await api(`/library/books/${bookId}`, { method: "DELETE" });
  alert(r.ok ? "Removed." : r.error);
  selectTab("desk");
};
window.deskMarkFinePaid = async (fineId) => {
  if (!confirm("Confirm you have collected this fine payment in person?")) return;
  const r = await api(`/librarian/library/fines/${fineId}/mark-paid`, { body: {} });
  alert(r.ok ? `Marked paid — ₹${r.amount}. Remaining unpaid for this student: ₹${r.remaining_unpaid}.` : r.error);
  selectTab("desk");
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
