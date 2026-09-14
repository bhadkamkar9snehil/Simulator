(() => {
  function esc(value) {
    return String(value ?? '').replace(/[&<>\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[ch]));
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '-';
  }

  function renderRows(tableId, rowsId, emptyId, rows, rowHtml) {
    const table = document.getElementById(tableId);
    const body = document.getElementById(rowsId);
    const empty = document.getElementById(emptyId);
    if (!table || !body || !empty) return;
    const hasRows = Array.isArray(rows) && rows.length > 0;
    table.classList.toggle('hidden', !hasRows);
    empty.classList.toggle('hidden', hasRows);
    body.innerHTML = hasRows ? rows.map(rowHtml).join('') : '';
  }

  function renderSessions(rows) {
    renderRows('opcDiagSessionTable', 'opcDiagSessionRows', 'opcDiagSessionEmpty', rows, row => `<tr>
      <td>${esc(row.name)}</td>
      <td class="mono">${esc(row.session_id)}</td>
      <td>${esc(row.state)}</td>
      <td>${esc(row.user)}</td>
      <td>${esc(row.subscriptions ?? 0)}</td>
      <td>${row.last_activity_age_seconds == null ? '-' : esc(row.last_activity_age_seconds + ' s')}</td>
    </tr>`);
  }

  function renderActivity(rows) {
    const recent = Array.isArray(rows) ? rows.slice(0, 30) : [];
    renderRows('opcDiagActivityTable', 'opcDiagActivityRows', 'opcDiagActivityEmpty', recent, row => {
      const nodes = Array.isArray(row.nodes)
        ? row.nodes.map(node => typeof node === 'string' ? node : node.node_id).filter(Boolean).join(', ')
        : '';
      return `<tr>
        <td>${esc(row.at)}</td>
        <td>${esc(String(row.kind || '').toUpperCase())}</td>
        <td>${esc(row.node_count ?? 0)}</td>
        <td>${esc(row.failed ?? 0)}</td>
        <td class="mono">${esc(nodes)}</td>
      </tr>`;
    });
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
    renderSessions(diag.sessions || []);
    renderActivity(diag.recent_activity || []);
  }

  window.renderOpcUaDiagnostics = renderStatus;
})();
