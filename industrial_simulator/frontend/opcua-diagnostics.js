(() => {
  function esc(value) {
    return String(value ?? '').replace(/[&<>\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[ch]));
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '-';
  }

  function sessionTable(rows) {
    if (!rows?.length) return '<div class="hint">No connected sessions.</div>';
    const body = rows.map(row => `<tr>
      <td>${esc(row.name)}</td><td class="mono">${esc(row.session_id)}</td><td>${esc(row.state)}</td>
      <td>${esc(row.user)}</td><td>${esc(row.subscriptions ?? 0)}</td>
      <td>${row.last_activity_age_seconds == null ? '-' : esc(row.last_activity_age_seconds + ' s')}</td>
    </tr>`).join('');
    return `<table><thead><tr><th>Name</th><th>Session</th><th>State</th><th>User</th><th>Subscriptions</th><th>Activity age</th></tr></thead><tbody>${body}</tbody></table>`;
  }

  function activityTable(rows) {
    if (!rows?.length) return '<div class="hint">No read/write activity yet.</div>';
    const body = rows.slice(0, 30).map(row => {
      const nodes = Array.isArray(row.nodes) ? row.nodes.map(node => typeof node === 'string' ? node : node.node_id).filter(Boolean).join(', ') : '';
      return `<tr><td>${esc(row.at)}</td><td>${esc(String(row.kind || '').toUpperCase())}</td><td>${esc(row.node_count ?? 0)}</td><td>${esc(row.failed ?? 0)}</td><td class="mono">${esc(nodes)}</td></tr>`;
    }).join('');
    return `<table><thead><tr><th>Time</th><th>Operation</th><th>Nodes</th><th>Failed</th><th>Node IDs</th></tr></thead><tbody>${body}</tbody></table>`;
  }

  function renderStatus(data) {
    const opc = data?.protocol?.opcua || {};
    const diag = opc.diagnostics || {};
    setText('opcClientCount', diag.connected_clients ?? 0);
    setText('opcReadCount', diag.read_requests ?? 0);
    setText('opcWriteCount', diag.write_requests ?? 0);
    setText('opcDiagAvailability', opc.diagnostics_available === false ? 'unavailable' : (opc.running ? 'live' : 'stopped'));
    setText('opcDiagClients', diag.connected_clients ?? 0);
    setText('opcDiagSessions', diag.session_count ?? 0);
    setText('opcDiagReads', diag.read_requests ?? 0);
    setText('opcDiagReadNodes', diag.read_nodes ?? 0);
    setText('opcDiagWrites', diag.write_requests ?? 0);
    setText('opcDiagWriteNodes', diag.write_nodes ?? 0);
    setText('opcDiagFailedWrites', diag.failed_writes ?? 0);
    const last = [diag.last_read_at, diag.last_write_at].filter(Boolean).sort().pop() || '-';
    setText('opcDiagLastActivity', last);
    const sessions = document.getElementById('opcDiagSessionTable');
    const activity = document.getElementById('opcDiagActivityTable');
    if (sessions) sessions.innerHTML = sessionTable(diag.sessions || []);
    if (activity) activity.innerHTML = activityTable(diag.recent_activity || []);
  }

  function renderRawStatus() {
    const raw = document.getElementById('rawStatus');
    if (!raw) return;
    try {
      renderStatus(JSON.parse(raw.textContent || '{}'));
    } catch (_) {
      // Main status renderer owns connectivity/parse errors.
    }
  }

  function start() {
    renderRawStatus();
    const raw = document.getElementById('rawStatus');
    if (!raw) return;
    const observer = new MutationObserver(renderRawStatus);
    observer.observe(raw, {childList: true, characterData: true, subtree: true});
  }

  window.renderOpcUaDiagnostics = renderStatus;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
