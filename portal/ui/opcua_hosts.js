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

function memberControls(simulationId) {
  const id = attr(simulationId);
  return `<div class="panel-actions">
    <button class="button compact secondary" data-opc-action="pause" data-simulation-id="${id}">Pause</button>
    <button class="button compact secondary" data-opc-action="resume" data-simulation-id="${id}">Resume</button>
    <button class="button compact secondary" data-opc-action="restart" data-simulation-id="${id}">Restart</button>
    <button class="button compact danger" data-opc-action="stop" data-simulation-id="${id}">Stop</button>
  </div>`;
}

function bulkControls(host) {
  const ids = (host.simulation_targets || []).map((member) => member.simulation_id).join(",");
  if (!ids) return "";
  const encoded = attr(ids);
  return `<div class="panel-actions" style="margin-top:10px">
    <button class="button compact secondary" data-opc-bulk-action="pause" data-simulation-ids="${encoded}">Pause all</button>
    <button class="button compact secondary" data-opc-bulk-action="resume" data-simulation-ids="${encoded}">Resume all</button>
    <button class="button compact secondary" data-opc-bulk-action="restart" data-simulation-ids="${encoded}">Restart all</button>
    <button class="button compact danger" data-opc-bulk-action="stop" data-simulation-ids="${encoded}">Stop all</button>
  </div>`;
}

function sharedMembers(host) {
  const members = host.simulation_targets || [];
  if (!members.length) return "";
  return `<div class="table-shell" style="margin-top:12px"><table class="data-table"><thead><tr><th>Simulation</th><th>Target</th><th>Folder</th><th>Tags</th><th>Writable</th><th>Controls</th></tr></thead><tbody>${members.map((member) => `<tr>
    <td class="mono">${esc(member.simulation_id)}</td>
    <td class="mono">${esc(member.target_id)}</td>
    <td class="mono">${esc(member.folder || "—")}</td>
    <td>${member.tag_count ?? 0}</td>
    <td>${member.writable_count ?? 0}</td>
    <td>${memberControls(member.simulation_id)}</td>
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
      <dt>Target</dt><dd class="mono">${esc(host.target_id || "—")}</dd>
      <dt>Folder</dt><dd>${esc(host.folder || "—")}</dd>
      <dt>Tags</dt><dd>${host.tag_count ?? 0}</dd>
      <dt>Writable</dt><dd>${host.writable_count ?? 0}</dd>
      <dt>Security</dt><dd>${esc(host.security_policy || "none")}</dd>
      <dt>Authentication</dt><dd>${esc(host.authentication || "anonymous")}</dd>
    </dl>
    ${host.simulation_id ? memberControls(host.simulation_id) : ""}
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
