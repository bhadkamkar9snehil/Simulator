const launcher = window.SIMULATOR_LAUNCHER_CONFIG || {};
const industrialPort = Number(launcher.industrial_web_port || 8000);
const industrialBase = `http://${location.hostname || "localhost"}:${industrialPort}`;

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function attr(value) { return esc(value); }
function humanState(state) { return state ? state[0].toUpperCase() + state.slice(1) : "Unknown"; }

function allowed(action, state) {
  if (action === "pause") return state === "running" || state === "degraded";
  if (action === "resume") return state === "paused";
  if (action === "restart") return state !== "starting" && state !== "unknown";
  if (action === "stop") return ["running", "paused", "degraded", "starting"].includes(state);
  return false;
}

function memberControls(simulationId, state) {
  const id = attr(simulationId);
  const button = (action, label, danger = false) => `<button class="button compact ${danger ? "danger" : "secondary"}" data-opc-action="${action}" data-simulation-id="${id}" ${allowed(action, state) ? "" : "disabled"}>${label}</button>`;
  return `<div class="panel-actions">${button("pause", "Pause")}${button("resume", "Resume")}${button("restart", "Restart")}${button("stop", "Stop", true)}</div>`;
}

function eligibleIds(host, action) {
  return [...new Set((host.simulation_targets || [])
    .filter((member) => allowed(action, member.simulation_state))
    .map((member) => member.simulation_id))];
}

function bulkButton(host, action, label, danger = false) {
  const ids = eligibleIds(host, action);
  return `<button class="button compact ${danger ? "danger" : "secondary"}" data-opc-bulk-action="${action}" data-simulation-ids="${attr(ids.join(","))}" ${ids.length ? "" : "disabled"}>${label}${ids.length ? ` (${ids.length})` : ""}</button>`;
}

function bulkControls(host) {
  if (!(host.simulation_targets || []).length) return "";
  return `<div class="panel-actions" style="margin-top:10px">
    ${bulkButton(host, "pause", "Pause all")}
    ${bulkButton(host, "resume", "Resume all")}
    ${bulkButton(host, "restart", "Restart all")}
    ${bulkButton(host, "stop", "Stop all", true)}
  </div>`;
}

function sharedMembers(host) {
  const members = host.simulation_targets || [];
  if (!members.length) return "";
  return `<div class="table-shell" style="margin-top:12px"><table class="data-table"><thead><tr><th>Simulation</th><th>State</th><th>Target</th><th>Folder</th><th>Tags</th><th>Writable</th><th>Controls</th></tr></thead><tbody>${members.map((member) => `<tr>
    <td class="mono">${esc(member.simulation_id)}</td>
    <td>${esc(humanState(member.simulation_state))}</td>
    <td class="mono">${esc(member.target_id)}</td>
    <td class="mono">${esc(member.folder || "—")}</td>
    <td>${member.tag_count ?? 0}</td>
    <td>${member.writable_count ?? 0}</td>
    <td>${memberControls(member.simulation_id, member.simulation_state)}</td>
  </tr>`).join("")}</tbody></table></div>`;
}

function sharedHostCard(key, host) {
  return `<article class="host-card">
    <h3>Shared OPC UA</h3>
    <p class="mono">${esc(host.endpoint || key)}</p>
    <dl class="key-value">
      <dt>Running</dt><dd>${host.running ? "Yes" : "No"}</dd>
      <dt>Simulations</dt><dd>${host.simulation_count ?? 0}</dd>
      <dt>Targets</dt><dd>${host.target_count ?? 0}</dd>
      <dt>Joining</dt><dd>${host.pending_targets ?? 0}</dd>
      <dt>Tags</dt><dd>${host.tag_count ?? 0}</dd>
      <dt>Writable</dt><dd>${host.writable_count ?? 0}</dd>
      <dt>Security</dt><dd>${esc(host.security_policy || "none")}</dd>
      <dt>Authentication</dt><dd>${esc(host.authentication || "anonymous")}</dd>
      <dt>Namespace</dt><dd>${esc(host.namespace_uri || "—")}</dd>
      <dt>Root</dt><dd>${esc(host.root_folder || "—")}</dd>
    </dl>
    ${bulkControls(host)}
    ${sharedMembers(host)}
  </article>`;
}

function dedicatedHostCard(key, host) {
  return `<article class="host-card">
    <h3>Dedicated OPC UA</h3>
    <p class="mono">${esc(host.endpoint || key)}</p>
    <dl class="key-value">
      <dt>Simulation</dt><dd class="mono">${esc(host.simulation_id || "—")}</dd>
      <dt>State</dt><dd>${esc(humanState(host.simulation_state))}</dd>
      <dt>Target</dt><dd class="mono">${esc(host.target_id || "—")}</dd>
      <dt>Folder</dt><dd>${esc(host.folder || "—")}</dd>
      <dt>Tags</dt><dd>${host.tag_count ?? 0}</dd>
      <dt>Writable</dt><dd>${host.writable_count ?? 0}</dd>
      <dt>Security</dt><dd>${esc(host.security_policy || "none")}</dd>
      <dt>Authentication</dt><dd>${esc(host.authentication || "anonymous")}</dd>
    </dl>
    ${host.simulation_id ? memberControls(host.simulation_id, host.simulation_state) : ""}
  </article>`;
}

function apiRouteCard(route) {
  const url = `${industrialBase}${route.path}`;
  return `<article class="host-card"><h3>REST API</h3><p class="mono">${esc(route.method)} ${esc(url)}</p><dl class="key-value"><dt>Simulation</dt><dd class="mono">${esc(route.simulation_id)}</dd><dt>Target</dt><dd class="mono">${esc(route.target_id)}</dd><dt>Body</dt><dd>${esc(route.body_mode || "json")}</dd><dt>Response</dt><dd>${esc(route.response_mode)}</dd><dt>Selection</dt><dd>${esc(route.selection_mode || "current")}</dd><dt>Requests</dt><dd>${route.request_count || 0}</dd><dt>Last status</dt><dd>${route.last_status_code ?? "—"}</dd><dt>Last latency</dt><dd>${route.last_latency_ms == null ? "—" : `${route.last_latency_ms} ms`}</dd></dl></article>`;
}

export function renderInterfaces(status) {
  const shared = Object.entries(status?.shared_opcua_hosts || {});
  const dedicated = Object.entries(status?.dedicated_opcua_hosts || {});
  const apiRoutes = status?.api_routes || [];
  const cards = [
    ...shared.map(([key, host]) => sharedHostCard(key, host)),
    ...dedicated.map(([key, host]) => dedicatedHostCard(key, host)),
    ...apiRoutes.map(apiRouteCard),
  ];
  if (!cards.length) {
    return `<div class="notice info">No interface hosts or simulated API routes are active. They are created on demand when simulations start.</div>`;
  }
  return `<div class="host-grid">${cards.join("")}</div>`;
}
