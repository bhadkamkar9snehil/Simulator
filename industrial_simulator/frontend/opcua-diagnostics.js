(() => {
  function esc(value) {
    return String(value ?? '').replace(/[&<>\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[ch]));
  }

  function ensureUi() {
    const statusGrid = document.getElementById('statusGrid');
    if (statusGrid && !document.getElementById('opcClientCount')) {
      statusGrid.insertAdjacentHTML('beforeend', `
        <div><span>OPC Clients</span><strong id="opcClientCount">0</strong></div>
        <div><span>OPC Reads</span><strong id="opcReadCount">0</strong></div>
        <div><span>OPC Writes</span><strong id="opcWriteCount">0</strong></div>`);
    }

    const rawStatus = document.getElementById('rawStatus');
    const hostCard = rawStatus?.closest('.card');
    const grid = hostCard?.parentElement;
    if (grid && !document.getElementById('opcDiagnosticsPanel')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'card';
      wrapper.id = 'opcDiagnosticsPanel';
      wrapper.innerHTML = `
        <div class="card-header"><h3>OPC UA Live Diagnostics</h3><strong id="opcDiagAvailability">-</strong></div>
        <div class="opc-diag-metrics">
          <div><span>Connected clients</span><strong id="opcDiagClients">0</strong></div>
          <div><span>Sessions</span><strong id="opcDiagSessions">0</strong></div>
          <div><span>Read requests</span><strong id="opcDiagReads">0</strong></div>
          <div><span>Nodes read</span><strong id="opcDiagReadNodes">0</strong></div>
          <div><span>Write requests</span><strong id="opcDiagWrites">0</strong></div>
          <div><span>Nodes written</span><strong id="opcDiagWriteNodes">0</strong></div>
          <div><span>Failed writes</span><strong id="opcDiagFailedWrites">0</strong></div>
          <div><span>Last activity</span><strong id="opcDiagLastActivity">-</strong></div>
        </div>
        <h4>Connected sessions</h4>
        <div id="opcDiagSessionTable" class="table-wrap"><div class="hint">No connected sessions.</div></div>
        <h4>Recent read / write activity</h4>
        <div id="opcDiagActivityTable" class="table-wrap"><div class="hint">No activity yet.</div></div>`;
      grid.parentElement?.insertBefore(wrapper, grid.nextSibling);
    }

    if (!document.getElementById('opcDiagnosticsStyles')) {
      const style = document.createElement('style');
      style.id = 'opcDiagnosticsStyles';
      style.textContent = `
        .opc-diag-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.5rem;margin:.75rem 0}
        .opc-diag-metrics>div{border:1px solid var(--line);background:var(--panel-2);padding:.625rem;min-width:0}
        .opc-diag-metrics span{display:block;color:var(--muted);font-size:.6875rem;text-transform:uppercase;margin-bottom:.25rem}
        .opc-diag-metrics strong{display:block;font-size:1rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        #opcDiagnosticsPanel h4{margin:.875rem 0 .375rem;text-transform:uppercase;font-size:.75rem;letter-spacing:.04rem}
        @media(max-width:900px){.opc-diag-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
      `;
      document.head.appendChild(style);
    }
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
    ensureUi();
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
    ensureUi();
    renderRawStatus();
    const raw = document.getElementById('rawStatus');
    if (!raw) return;
    const observer = new MutationObserver(renderRawStatus);
    observer.observe(raw, {childList: true, characterData: true, subtree: true});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
