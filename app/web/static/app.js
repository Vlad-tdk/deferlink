// DeferLink Admin — minimal vanilla JS frontend.
// No build step. ES modules served as static files.

const API = "/api/v1";

// ─── tiny helpers ─────────────────────────────────────────────────────────────

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function toast(msg, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.textContent = msg;
  $("#toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

async function api(path, opts = {}) {
  const init = {
    method:  opts.method || "GET",
    headers: { "Content-Type": "application/json" },
  };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);

  const res = await fetch(API + path, init);
  let body  = null;
  try { body = await res.json(); } catch (_) { /* may be empty */ }
  if (!res.ok) {
    const detail = (body && (body.detail || body.error || body.message)) || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(s.replace(" ", "T") + (s.endsWith("Z") ? "" : "Z"));
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString();
};

const tagOf = (kind, text) => `<span class="tag tag-${esc(kind)}">${esc(text ?? kind)}</span>`;

const yn = (v) => v ? "✓" : "—";

// ─── Router ───────────────────────────────────────────────────────────────────

const routes = {};   // section name -> render fn

function register(name, fn) { routes[name] = fn; }

async function navigate() {
  const hash = window.location.hash.replace(/^#/, "") || "dashboard";

  $$(".section").forEach((s) => s.classList.remove("active"));
  $$(".nav-item").forEach((n) => n.classList.remove("active"));

  const sec = $(`#section-${hash}`);
  const nav = $(`.nav-item[data-section="${hash}"]`);
  if (sec) sec.classList.add("active");
  if (nav) nav.classList.add("active");

  const fn = routes[hash];
  if (fn) {
    try { await fn(); }
    catch (e) { toast(`Load error: ${e.message}`, "error"); }
  }
}

window.addEventListener("hashchange", navigate);

// ─── Modals ───────────────────────────────────────────────────────────────────

function openModal(id) { $("#" + id)?.classList.add("open"); }
function closeModal(id) { $("#" + id)?.classList.remove("open"); }

document.addEventListener("click", (e) => {
  const opener = e.target.closest("[data-modal]");
  if (opener) { openModal(opener.dataset.modal); return; }
  if (e.target.matches("[data-close]") || e.target.classList.contains("modal")) {
    e.target.closest(".modal")?.classList.remove("open");
  }
});

// ─── Health indicator ────────────────────────────────────────────────────────

async function pollHealth() {
  try {
    await api("/health/quick");
    $("#health-indicator").className = "dot dot-ok";
    $("#health-text").textContent    = "online";
  } catch {
    $("#health-indicator").className = "dot dot-fail";
    $("#health-text").textContent    = "offline";
  }
}

// ─── Section: Overview ────────────────────────────────────────────────────────

register("dashboard", async () => {
  const [cloak, postbacks, capi] = await Promise.all([
    api("/cloaking/stats?days=7").catch(() => null),
    api("/skan/postbacks?limit=1").catch(() => null),
    api("/capi/log?limit=1").catch(() => null),
  ]);

  const total   = cloak?.total_decisions ?? 0;
  const bots    = (cloak?.breakdown || [])
    .filter((r) => r.visitor_type === "bot")
    .reduce((s, r) => s + r.total, 0);
  $("#ov-decisions").textContent = total;
  $("#ov-bots").textContent      = bots;
  $("#ov-postbacks").textContent = postbacks?.count ?? "—";
  $("#ov-capi").textContent      = capi?.count ?? "—";

  const tbody = $("#ov-cloak-table tbody");
  const rows  = cloak?.breakdown || [];
  tbody.innerHTML = rows.length ? rows.map((r) => `
    <tr>
      <td>${tagOf(r.visitor_type)}</td>
      <td>${esc(r.action)}</td>
      <td>${r.total}</td>
      <td>${r.avg_confidence ?? "—"}</td>
      <td>${r.unique_ips}</td>
    </tr>
  `).join("") : `<tr><td colspan="5" class="empty">No data yet.</td></tr>`;
});

// ─── Section: IP rules ────────────────────────────────────────────────────────

register("cloak-ip", async () => {
  const r = await api("/cloaking/rules/ip");
  const tbody = $("#ip-rules-table tbody");
  tbody.innerHTML = (r.rules || []).length ? r.rules.map((rule) => {
    const match = rule.cidr || rule.ip_exact || (rule.asn ? `AS${rule.asn}` : "—");
    return `
      <tr>
        <td>${rule.id}</td>
        <td><code>${esc(match)}</code></td>
        <td>${tagOf(rule.visitor_type)}</td>
        <td>${rule.confidence}</td>
        <td>${esc(rule.description || "")}</td>
        <td>${yn(rule.enabled)}</td>
        <td><button class="btn-link btn-danger" data-del-ip="${rule.id}">Delete</button></td>
      </tr>
    `;
  }).join("") : `<tr><td colspan="7" class="empty">No rules yet.</td></tr>`;
});

$("#form-ip-rule").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const matchType = fd.get("match_type");
  const value     = fd.get("match_value");
  const body = {
    cidr:         matchType === "cidr"     ? value : null,
    ip_exact:     matchType === "ip_exact" ? value : null,
    asn:          matchType === "asn"      ? Number(value) : null,
    visitor_type: fd.get("visitor_type"),
    confidence:   Number(fd.get("confidence")),
    description:  fd.get("description") || "",
    enabled:      true,
  };
  try {
    await api("/cloaking/rules/ip", { method: "POST", body });
    toast("IP rule added", "success");
    closeModal("modal-ip-rule");
    e.target.reset();
    if (location.hash === "#cloak-ip") navigate();
  } catch (err) { toast(err.message, "error"); }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-ip]");
  if (!btn) return;
  if (!confirm("Delete this IP rule?")) return;
  try {
    await api(`/cloaking/rules/ip/${btn.dataset.delIp}`, { method: "DELETE" });
    toast("Deleted", "success");
    navigate();
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: UA rules ────────────────────────────────────────────────────────

register("cloak-ua", async () => {
  const r = await api("/cloaking/rules/ua");
  const tbody = $("#ua-rules-table tbody");
  tbody.innerHTML = (r.rules || []).length ? r.rules.map((rule) => `
    <tr>
      <td>${rule.id}</td>
      <td><code>${esc(rule.pattern)}</code></td>
      <td>${tagOf(rule.visitor_type)}</td>
      <td>${rule.confidence}</td>
      <td>${esc(rule.description || "")}</td>
      <td>${yn(rule.enabled)}</td>
      <td><button class="btn-link btn-danger" data-del-ua="${rule.id}">Delete</button></td>
    </tr>
  `).join("") : `<tr><td colspan="7" class="empty">No rules yet.</td></tr>`;
});

$("#form-ua-rule").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    pattern:      fd.get("pattern"),
    visitor_type: fd.get("visitor_type"),
    confidence:   Number(fd.get("confidence")),
    description:  fd.get("description") || "",
    enabled:      true,
  };
  try {
    await api("/cloaking/rules/ua", { method: "POST", body });
    toast("UA rule added", "success");
    closeModal("modal-ua-rule");
    e.target.reset();
    if (location.hash === "#cloak-ua") navigate();
  } catch (err) { toast(err.message, "error"); }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-ua]");
  if (!btn) return;
  if (!confirm("Delete this UA rule?")) return;
  try {
    await api(`/cloaking/rules/ua/${btn.dataset.delUa}`, { method: "DELETE" });
    toast("Deleted", "success");
    navigate();
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: Cloaking test ───────────────────────────────────────────────────

register("cloak-test", async () => { /* stateless */ });

$("#cloak-test-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  let headers = {};
  const raw = fd.get("headers")?.toString().trim();
  if (raw) {
    try { headers = JSON.parse(raw); }
    catch { toast("Headers must be valid JSON", "error"); return; }
  }
  try {
    const r = await api("/cloaking/test", {
      method: "POST",
      body:   { ip: fd.get("ip"), user_agent: fd.get("user_agent"), headers },
    });
    const out = $("#cloak-test-result");
    out.hidden = false;
    out.textContent = JSON.stringify(r, null, 2);
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: Cloaking log ────────────────────────────────────────────────────

register("cloak-log", async () => {
  const type = $("#cloak-log-type").value;
  const q    = type ? `?visitor_type=${encodeURIComponent(type)}&limit=200` : "?limit=200";
  const r    = await api("/cloaking/log" + q);
  const tbody = $("#cloak-log-table tbody");
  tbody.innerHTML = (r.rows || []).length ? r.rows.map((row) => `
    <tr>
      <td>${fmtDate(row.timestamp)}</td>
      <td><code>${esc(row.ip)}</code></td>
      <td title="${esc(row.user_agent)}">${esc((row.user_agent || "").slice(0, 60))}</td>
      <td>${tagOf(row.visitor_type)}</td>
      <td>${esc(row.action)}</td>
      <td>${row.confidence ?? "—"}</td>
    </tr>
  `).join("") : `<tr><td colspan="6" class="empty">No decisions yet.</td></tr>`;
});

$("#cloak-log-refresh").addEventListener("click", () => navigate());

// ─── Section: SKAN postbacks ──────────────────────────────────────────────────

register("skan-postbacks", async () => {
  const app = $("#skan-pb-app").value.trim();
  const seq = $("#skan-pb-seq").value;
  const params = new URLSearchParams({ limit: "100" });
  if (app) params.set("app_id", app);
  if (seq !== "") params.set("sequence_index", seq);
  const r = await api("/skan/postbacks?" + params);
  const tbody = $("#skan-pb-table tbody");
  tbody.innerHTML = (r.postbacks || []).length ? r.postbacks.map((p) => `
    <tr>
      <td>${fmtDate(p.received_at)}</td>
      <td>${esc(p.app_id || "—")}</td>
      <td>${esc(p.source_identifier || p.campaign_id || "—")}</td>
      <td><code>${esc((p.transaction_id || "").slice(0, 8))}</code></td>
      <td>PB${(p.postback_sequence_index ?? 0) + 1}</td>
      <td>${p.conversion_value ?? "—"}</td>
      <td>${esc(p.coarse_conversion_value || "—")}</td>
      <td>${p.signature_verified ? tagOf("ok", "✓") : tagOf("fail", "✗")}</td>
      <td>${p.capi_forwarded ? tagOf("ok", "✓") : "—"}</td>
    </tr>
  `).join("") : `<tr><td colspan="9" class="empty">No postbacks yet.</td></tr>`;
});

$("#skan-pb-refresh").addEventListener("click", () => navigate());

// ─── Section: SKAN decoders ───────────────────────────────────────────────────

register("skan-decoders", async () => {
  const r = await api("/skan/decoders");
  const tbody = $("#skan-decoders-table tbody");
  tbody.innerHTML = (r.decoders || []).length ? r.decoders.map((d) => `
    <tr>
      <td>${d.id}</td>
      <td>${esc(d.app_id || "—")}</td>
      <td>${esc(d.source_identifier || "—")}</td>
      <td>${d.campaign_id ?? "—"}</td>
      <td>${(d.rules || []).length}</td>
      <td>${esc(d.description || "")}</td>
      <td>${yn(d.enabled)}</td>
      <td>
        <button class="btn-link" data-edit-decoder='${esc(JSON.stringify(d))}'>Edit</button>
        <button class="btn-link btn-danger" data-del-decoder="${d.id}">Delete</button>
      </td>
    </tr>
  `).join("") : `<tr><td colspan="8" class="empty">No decoders.</td></tr>`;
});

function decoderRuleRow(rule = {}) {
  const tr = document.createElement("tr");
  tr.innerHTML = `
    <td><input name="cv_min" type="number" min="0" max="63" value="${rule.cv_min ?? 0}"></td>
    <td><input name="cv_max" type="number" min="0" max="63" value="${rule.cv_max ?? 63}"></td>
    <td><input name="capi_event" value="${esc(rule.capi_event || "Purchase")}"></td>
    <td><input name="forward" type="checkbox" ${rule.forward !== false ? "checked" : ""}></td>
    <td><input name="static_value" type="number" step="0.01" value="${rule.static_value ?? ""}"></td>
    <td><input name="value_multiplier" type="number" step="0.1" value="${rule.value_multiplier ?? 1}"></td>
    <td><input name="currency" value="${esc(rule.currency || "USD")}" style="width:70px"></td>
    <td><button type="button" class="btn-link btn-danger" data-rule-del>×</button></td>
  `;
  return tr;
}

$("#decoder-add-rule").addEventListener("click", () => {
  $("#decoder-rules-body").appendChild(decoderRuleRow());
});

document.addEventListener("click", (e) => {
  if (e.target.matches("[data-rule-del]")) {
    e.target.closest("tr").remove();
  }
});

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-edit-decoder]");
  if (!btn) return;
  const d = JSON.parse(btn.dataset.editDecoder);
  const f = $("#form-decoder");
  f.elements.id.value                = d.id;
  f.elements.app_id.value            = d.app_id || "";
  f.elements.source_identifier.value = d.source_identifier || "";
  f.elements.campaign_id.value       = d.campaign_id ?? "";
  f.elements.description.value       = d.description || "";
  f.elements.enabled.checked         = !!d.enabled;
  $("#modal-decoder-title").textContent = `Edit decoder #${d.id}`;
  const body = $("#decoder-rules-body");
  body.innerHTML = "";
  (d.rules || []).forEach((r) => body.appendChild(decoderRuleRow(r)));
  openModal("modal-decoder");
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-decoder]");
  if (!btn) return;
  if (!confirm("Delete this decoder?")) return;
  try {
    await api(`/skan/decoders/${btn.dataset.delDecoder}`, { method: "DELETE" });
    toast("Deleted", "success");
    navigate();
  } catch (err) { toast(err.message, "error"); }
});

// Reset decoder form when opening fresh
document.addEventListener("click", (e) => {
  const opener = e.target.closest('[data-modal="modal-decoder"]');
  if (!opener) return;
  const f = $("#form-decoder");
  f.reset();
  f.elements.id.value = "";
  $("#modal-decoder-title").textContent = "New decoder";
  const body = $("#decoder-rules-body");
  body.innerHTML = "";
  body.appendChild(decoderRuleRow({ cv_min: 0,  cv_max: 20, capi_event: "Lead" }));
  body.appendChild(decoderRuleRow({ cv_min: 21, cv_max: 41, capi_event: "Purchase", value_multiplier: 1 }));
  body.appendChild(decoderRuleRow({ cv_min: 42, cv_max: 63, capi_event: "Purchase", value_multiplier: 2 }));
});

$("#form-decoder").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f  = e.target;
  const id = f.elements.id.value;

  const rules = $$("#decoder-rules-body tr").map((tr) => {
    const get = (n) => tr.querySelector(`[name="${n}"]`);
    const num = (v) => v === "" || v == null ? null : Number(v);
    return {
      cv_min:           Number(get("cv_min").value),
      cv_max:           Number(get("cv_max").value),
      capi_event:       get("capi_event").value,
      forward:          get("forward").checked,
      static_value:     num(get("static_value").value),
      value_multiplier: num(get("value_multiplier").value) ?? 1.0,
      currency:         get("currency").value || "USD",
    };
  });

  const body = {
    app_id:            f.elements.app_id.value,
    source_identifier: f.elements.source_identifier.value || null,
    campaign_id:       f.elements.campaign_id.value === "" ? null : Number(f.elements.campaign_id.value),
    description:       f.elements.description.value || "",
    enabled:           f.elements.enabled.checked,
    rules,
  };

  try {
    if (id) {
      await api(`/skan/decoders/${id}`, {
        method: "PATCH",
        body:   { rules, description: body.description, enabled: body.enabled },
      });
    } else {
      await api("/skan/decoders", { method: "POST", body });
    }
    toast("Decoder saved", "success");
    closeModal("modal-decoder");
    if (location.hash === "#skan-decoders") navigate();
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: SKAN config ─────────────────────────────────────────────────────

register("skan-config", async () => { /* stateless */ });

$("#skan-config-load").addEventListener("click", async () => {
  const f      = $("#skan-config-form");
  const app    = f.elements.app_id.value.trim();
  if (!app) { toast("Enter app_id first", "error"); return; }
  try {
    const r = await api(`/skan/config?app_id=${encodeURIComponent(app)}`);
    (r.revenue_buckets_usd || []).forEach((v, i) => {
      const inp = f.elements[`b${i}`];
      if (inp) inp.value = v;
    });
    const t = r.engagement_thresholds || {};
    for (const k of ["bounce_max_seconds", "active_min_sessions",
                     "deep_min_sessions", "deep_min_core_actions"]) {
      if (f.elements[k] && t[k] != null) f.elements[k].value = t[k];
    }
    f.elements.power_requires_retention.checked = !!t.power_requires_retention;
    f.elements.conversion_window_hours.value    = r.conversion_window_hours;
    f.elements.cache_ttl_seconds.value          = r.cache_ttl_seconds;
    toast("Loaded", "success");
  } catch (err) { toast(err.message, "error"); }
});

$("#skan-config-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const buckets = [];
  for (let i = 0; i < 8; i++) buckets.push(Number(f.elements[`b${i}`].value));
  const body = {
    app_id:                   f.elements.app_id.value,
    schema_version:           1,
    schema_name:              "rev3_eng2_flag1",
    revenue_buckets_usd:      buckets,
    bounce_max_seconds:       Number(f.elements.bounce_max_seconds.value),
    active_min_sessions:      Number(f.elements.active_min_sessions.value),
    deep_min_sessions:        Number(f.elements.deep_min_sessions.value),
    deep_min_core_actions:    Number(f.elements.deep_min_core_actions.value),
    power_requires_retention: f.elements.power_requires_retention.checked,
    conversion_window_hours:  Number(f.elements.conversion_window_hours.value),
    cache_ttl_seconds:        Number(f.elements.cache_ttl_seconds.value),
  };
  try {
    await api("/skan/config", { method: "PUT", body });
    toast("Config saved", "success");
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: SKAN stats ──────────────────────────────────────────────────────

register("skan-stats", async () => {
  const app  = $("#skan-stats-app").value.trim();
  const days = $("#skan-stats-days").value || "7";
  const params = new URLSearchParams({ days });
  if (app) params.set("app_id", app);

  const r        = await api("/skan/stats?" + params);
  const buckets  = new Array(64).fill(0);
  (r.distribution || r.rows || []).forEach((row) => {
    const cv = row.conversion_value ?? row.cv;
    if (cv != null) buckets[cv] = row.count;
  });

  const max  = Math.max(1, ...buckets);
  const cont = $("#cv-bars");
  cont.style.gridTemplateColumns = "repeat(16, 1fr)";
  cont.innerHTML = buckets.map((n, i) => `
    <div class="cv-bar" title="CV ${i}: ${n}">
      <div class="cv-bar-count">${n || ""}</div>
      <div class="cv-bar-fill" style="height:${Math.max(3, (n / max) * 60)}px"></div>
      <div>${i}</div>
    </div>
  `).join("");
});

$("#skan-stats-refresh").addEventListener("click", () => navigate());

// ─── Section: CAPI configs ────────────────────────────────────────────────────

register("capi-configs", async () => {
  const r = await api("/capi/configs");
  const tbody = $("#capi-configs-table tbody");
  tbody.innerHTML = (r.configs || []).length ? r.configs.map((c) => `
    <tr>
      <td>${c.id}</td>
      <td>${esc(c.app_id)}</td>
      <td>${esc(c.platform)}</td>
      <td><code>${esc(c.pixel_id)}</code></td>
      <td>${esc(c.api_version)}</td>
      <td>${esc(c.test_event_code || "—")}</td>
      <td>${yn(c.enabled)}</td>
      <td><button class="btn-link btn-danger" data-del-capi="${c.id}">Delete</button></td>
    </tr>
  `).join("") : `<tr><td colspan="8" class="empty">No CAPI configs.</td></tr>`;
});

$("#form-capi-config").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    app_id:          fd.get("app_id"),
    platform:        fd.get("platform"),
    pixel_id:        fd.get("pixel_id"),
    access_token:    fd.get("access_token"),
    test_event_code: fd.get("test_event_code") || null,
    api_version:     fd.get("api_version") || "v21.0",
    enabled:         true,
    description:     fd.get("description") || "",
  };
  try {
    await api("/capi/configs", { method: "POST", body });
    toast("CAPI config saved", "success");
    closeModal("modal-capi-config");
    e.target.reset();
    if (location.hash === "#capi-configs") navigate();
  } catch (err) { toast(err.message, "error"); }
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-del-capi]");
  if (!btn) return;
  if (!confirm("Delete this CAPI config?")) return;
  try {
    await api(`/capi/configs/${btn.dataset.delCapi}`, { method: "DELETE" });
    toast("Deleted", "success");
    navigate();
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: CAPI log ────────────────────────────────────────────────────────

register("capi-log", async () => {
  const params = new URLSearchParams({ limit: "200" });
  const app    = $("#capi-log-app").value.trim();
  const src    = $("#capi-log-source").value;
  const status = $("#capi-log-status").value;
  if (app)    params.set("app_id", app);
  if (src)    params.set("event_source", src);
  if (status) params.set("succeeded", status);

  const r = await api("/capi/log?" + params);
  const tbody = $("#capi-log-table tbody");
  tbody.innerHTML = (r.rows || []).length ? r.rows.map((row) => `
    <tr>
      <td>${fmtDate(row.created_at)}</td>
      <td>${esc(row.app_id)}</td>
      <td>${esc(row.event_name)}</td>
      <td>${esc(row.event_source)}</td>
      <td><code>${esc(row.pixel_id || "—")}</code></td>
      <td>${row.response_code ?? "—"}</td>
      <td>${row.attempts}</td>
      <td>${row.succeeded ? tagOf("ok", "OK") : tagOf("fail", "FAIL")}</td>
      <td title="${esc(row.last_error || "")}">${esc((row.last_error || "").slice(0, 50))}</td>
    </tr>
  `).join("") : `<tr><td colspan="9" class="empty">No deliveries yet.</td></tr>`;
});

$("#capi-log-refresh").addEventListener("click", () => navigate());

$("#capi-log-retry").addEventListener("click", async () => {
  try {
    const r = await api("/capi/retry", { method: "POST" });
    toast(`Retry processed: ${r.processed}`, "success");
    navigate();
  } catch (err) { toast(err.message, "error"); }
});

// ─── Section: CAPI test event ────────────────────────────────────────────────

register("capi-test", async () => {
  const f = $("#capi-test-form");
  if (!f.elements.event_id.value) {
    f.elements.event_id.value = "test_" + Math.random().toString(36).slice(2, 10);
  }
});

$("#capi-test-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    app_id:      fd.get("app_id"),
    platform:    "facebook",
    event_name:  fd.get("event_name"),
    event_id:    fd.get("event_id"),
    value:       fd.get("value") ? Number(fd.get("value")) : null,
    currency:    fd.get("currency") || "USD",
    external_id: fd.get("external_id") || null,
  };
  try {
    const r = await api("/capi/test", { method: "POST", body });
    const out = $("#capi-test-result");
    out.hidden = false;
    out.textContent = JSON.stringify(r, null, 2);
    toast(r.success ? "Sent" : `Failed: ${r.error || r.status_code}`, r.success ? "success" : "error");
  } catch (err) { toast(err.message, "error"); }
});

// ─── Boot ─────────────────────────────────────────────────────────────────────

pollHealth();
setInterval(pollHealth, 15000);
navigate();
