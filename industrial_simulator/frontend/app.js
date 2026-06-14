const state = {
  generators: [], selectedGeneratorSpec: null, selectedDomainId: null,
  selectedCsvFile: null, selectedCsvMetadata: null, replayConfig: null,
  simulatorStatus: null, currentValues: [], lastGeneratorRequest: null,
  files: [], selectedShared: new Set(), selectedOpcua: new Set(), selectedMqtt: new Set(),
  replayConfiguredMode: null,
  tagPlan: {opcua: [], mqtt: []}, tagPlanBuilt: false, tagPlanDirty: true
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  let data = null;
  try { data = await res.json(); } catch (_) { data = {}; }
  if (!res.ok) {
    const err = data.detail?.error || data.error || JSON.stringify(data);
    throw new Error(err);
  }
  return data;
}

function showMessage(text, kind = 'info') {
  const el = document.getElementById('messageArea');
  el.className = `message ${kind}`;
  el.textContent = text;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 6500);
}

window.addEventListener('error', event => {
  const msg = String(event.message || '');
  if (msg.includes("reading 'running'") || msg.includes('reading \"running\"')) {
    event.preventDefault();
    refreshStatus().catch(() => {});
  }
});

function escapeHtml(v) { return String(v ?? '').replace(/[&<>"]/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[s])); }
function fileKey(file) { return `${file.source}:${file.filename}`; }
function selectedFilesFrom(set) { return [...set].map(key => { const [source, ...rest] = key.split(':'); return {source, filename: rest.join(':')}; }); }
function selectedNames(set) { return [...set].map(k => k.split(':').slice(1).join(':')).join(', ') || '-'; }

function table(rows, columns = null, actions = null) {
  if (!rows || !rows.length) return '<div class="hint">No data.</div>';
  const cols = columns || Object.keys(rows[0]);
  const head = cols.map(c => `<th>${escapeHtml(c)}</th>`).join('') + (actions ? '<th>Actions</th>' : '');
  const body = rows.map((r, idx) => `<tr>${cols.map(c => `<td>${escapeHtml(r[c] ?? '')}</td>`).join('')}${actions ? `<td>${actions(r, idx)}</td>` : ''}</tr>`).join('');
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function switchTab(tab, updateHash = true) {
  const allowed = ['generate', 'files', 'replay', 'configs'];
  if (!allowed.includes(tab)) tab = 'generate';
  document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(`tab-${tab}`);
  if (panel) panel.classList.add('active');
  if (updateHash && window.location.hash !== `#${tab}`) {
    history.replaceState(null, '', `#${tab}`);
  }
}
document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
window.addEventListener('hashchange', () => switchTab((window.location.hash || '#generate').slice(1), false));

function updateAssignments() {
  document.getElementById('sharedAssignment').textContent = selectedNames(state.selectedShared);
  document.getElementById('opcAssignment').textContent = selectedNames(state.selectedOpcua);
  document.getElementById('mqttAssignment').textContent = selectedNames(state.selectedMqtt);
}

function safePrefix(filename) {
  return String(filename || 'file').replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'file';
}
function planEntryKey(entry) {
  return `${entry.protocol}:${entry.source}:${entry.filename}:${entry.csv_column}`;
}
function mergeFileLists(...groups) {
  const out = [];
  const seen = new Set();
  groups.flat().forEach(item => {
    const key = `${item.source}:${item.filename}`;
    if (!seen.has(key)) { seen.add(key); out.push(item); }
  });
  return out;
}
function activeProtocolFiles() {
  const mode = document.getElementById('protocolMode').value;
  const shared = selectedFilesFrom(state.selectedShared);
  const opcua = selectedFilesFrom(state.selectedOpcua);
  const mqtt = selectedFilesFrom(state.selectedMqtt);
  if (mode === 'both') return {opcua: mergeFileLists(shared, opcua), mqtt: mergeFileLists(shared, mqtt)};
  if (mode === 'opcua') return {opcua: mergeFileLists(shared, opcua), mqtt: []};
  if (mode === 'mqtt') return {opcua: [], mqtt: mergeFileLists(shared, mqtt)};
  return {opcua: [], mqtt: []};
}
function markTagPlanDirty() {
  state.tagPlanDirty = true;
  state.replayConfiguredMode = null;
  const el = document.getElementById('tagPlanSummary');
  if (el) el.textContent = 'Tag plan changed. Click Build / Refresh Tag Preview, review the selected tags, then Apply Selected Protocol Plans.';
}
async function metadataForFile(item) {
  return await api(`/api/csv/files/${encodeURIComponent(item.filename)}/metadata?source=${item.source}`);
}
async function buildTagPlanPreview(showSuccess = true) {
  const files = activeProtocolFiles();
  const previous = new Map([...state.tagPlan.opcua, ...state.tagPlan.mqtt].map(entry => [planEntryKey(entry), entry.enabled]));
  const next = {opcua: [], mqtt: []};
  const nodePrefix = document.getElementById('nodePrefix').value || 'TagSimulator';

  for (const protocol of ['opcua', 'mqtt']) {
    for (const item of files[protocol]) {
      const meta = await metadataForFile(item);
      const prefix = safePrefix(item.filename);
      for (const tag of (meta.default_tag_mappings || [])) {
        const nodeSuffix = String(tag.node_id || tag.csv_column).split('.').pop();
        const entry = {
          protocol,
          source: item.source,
          filename: item.filename,
          csv_column: tag.csv_column,
          tag_name: `${prefix}_${tag.tag_name}`,
          node_id: `${nodePrefix}.${prefix}.${nodeSuffix}`,
          data_type: tag.data_type || 'String',
          enabled: true,
        };
        const key = planEntryKey(entry);
        if (previous.has(key)) entry.enabled = previous.get(key);
        next[protocol].push(entry);
      }
    }
  }

  state.tagPlan = next;
  state.tagPlanBuilt = true;
  state.tagPlanDirty = false;
  state.replayConfiguredMode = null;
  renderTagPlanPreview();
  if (showSuccess) showMessage('Tag preview is ready. Check/uncheck tags, then click Apply Selected Protocol Plans before Start.', 'success');
}
function collectTagSelections() {
  return [...state.tagPlan.opcua, ...state.tagPlan.mqtt].map(entry => ({
    protocol: entry.protocol,
    filename: entry.filename,
    source: entry.source,
    csv_column: entry.csv_column,
    enabled: !!entry.enabled,
  }));
}
function tagPlanCounts(protocol) {
  const rows = state.tagPlan[protocol] || [];
  return {total: rows.length, selected: rows.filter(r => r.enabled).length, unselected: rows.filter(r => !r.enabled).length};
}
function tagRowsTable(rows, emptyText) {
  if (!rows.length) return `<div class="hint">${escapeHtml(emptyText)}</div>`;
  const body = rows.map(entry => {
    const key = escapeHtml(planEntryKey(entry));
    return `<tr>
      <td><input type="checkbox" data-tag-plan-key="${key}" ${entry.enabled ? 'checked' : ''}></td>
      <td><span class="pill ${entry.enabled ? 'run' : 'skip'}">${entry.enabled ? 'WILL RUN' : 'NOT RUN'}</span></td>
      <td>${entry.protocol === 'opcua' ? 'OPC UA' : 'MQTT'}</td>
      <td>${escapeHtml(entry.filename)}</td>
      <td class="mono">${escapeHtml(entry.csv_column)}</td>
      <td class="mono">${escapeHtml(entry.tag_name)}</td>
      <td>${escapeHtml(entry.data_type)}</td>
    </tr>`;
  }).join('');
  return `<table class="tag-plan-table"><thead><tr><th>Run</th><th>Status</th><th>Protocol</th><th>File</th><th>CSV/XLSX Column</th><th>Runtime Tag Name</th><th>Type</th></tr></thead><tbody>${body}</tbody></table>`;
}
function renderProtocolPlan(protocol) {
  const title = protocol === 'opcua' ? 'OPC UA Tag Plan' : 'MQTT Tag Plan';
  const rows = state.tagPlan[protocol] || [];
  const selected = rows.filter(r => r.enabled);
  const unselected = rows.filter(r => !r.enabled);
  const counts = tagPlanCounts(protocol);
  return `<div class="tag-plan-section">
    <div class="tag-plan-header"><h4>${title}</h4><div>${counts.selected} selected / ${counts.unselected} unselected / ${counts.total} total</div></div>
    <h5>Will Run</h5>${tagRowsTable(selected, 'No selected tags for this protocol.')}
    <h5>Not Run / Unselected</h5>${tagRowsTable(unselected, 'No unselected tags for this protocol.')}
  </div>`;
}
function renderTagPlanPreview() {
  const box = document.getElementById('protocolTagPlan');
  const summary = document.getElementById('tagPlanSummary');
  if (!box || !summary) return;
  if (!state.tagPlanBuilt) {
    summary.textContent = 'No tag preview built yet.';
    box.innerHTML = '<div class="hint">Select files in Files / Assignment, choose protocol mode, then click Build / Refresh Tag Preview.</div>';
    return;
  }
  const opc = tagPlanCounts('opcua');
  const mqtt = tagPlanCounts('mqtt');
  summary.textContent = `OPC UA: ${opc.selected} will run, ${opc.unselected} unselected. MQTT: ${mqtt.selected} will run, ${mqtt.unselected} unselected.`;
  box.innerHTML = renderProtocolPlan('opcua') + renderProtocolPlan('mqtt');
  box.querySelectorAll('[data-tag-plan-key]').forEach(cb => cb.addEventListener('change', e => {
    const key = e.target.dataset.tagPlanKey;
    for (const protocol of ['opcua', 'mqtt']) {
      const entry = state.tagPlan[protocol].find(item => planEntryKey(item) === key);
      if (entry) entry.enabled = e.target.checked;
    }
    state.replayConfiguredMode = null;
    renderTagPlanPreview();
  }));
}
function setTagPlanProtocol(protocol, enabled) {
  if (!state.tagPlanBuilt) return showMessage('Build the tag preview first.', 'info');
  state.tagPlan[protocol].forEach(entry => entry.enabled = enabled);
  state.replayConfiguredMode = null;
  renderTagPlanPreview();
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
function safeObj(value) {
  return value && typeof value === 'object' ? value : {};
}
function boolStatus(value) {
  return value === true ? 'running' : 'stopped';
}
async function refreshStatus() {
  try {
    const data = safeObj(await api('/api/status'));
    const proto = safeObj(data.protocol);
    const opc = safeObj(proto.opcua);
    const mqtt = safeObj(proto.mqtt);
    const sim = safeObj(data.simulator);
    state.simulatorStatus = sim;
    setText('backendStatus', data.backend || 'ok');
    setText('opcStatus', boolStatus(opc.running));
    setText('mqttStatus', boolStatus(mqtt.running));
    setText('opcEndpoint', proto.endpoint || '-');
    setText('simState', sim.state || 'idle');
    setText('loadedCsv', sim.csv_file || '-');
    setText('cursorStatus', `${sim.cursor ?? 0} / ${sim.row_count ?? 0}`);
    setText('freqStatus', sim.frequency_hz || '-');
    setText('tagStatus', sim.tag_count || 0);
    setText('rawStatus', JSON.stringify(data, null, 2));
  } catch (e) { showMessage(e.message || String(e), 'error'); }
}

async function loadGenerators() {
  const data = await api('/api/generators');
  state.generators = data.generators;
  const sel = document.getElementById('domainSelect');
  sel.innerHTML = data.generators.map(g => `<option value="${g.domain_id}">${escapeHtml(g.display_name)}</option>`).join('');
  if (data.generators.length) await loadGeneratorSpec(data.generators[0].domain_id);
}
async function loadGeneratorSpec(domainId) {
  const spec = await api(`/api/generators/${domainId}/spec`);
  state.selectedGeneratorSpec = spec; state.selectedDomainId = domainId;
  document.getElementById('generatorDescription').textContent = spec.description;
  document.getElementById('outputFilename').value = spec.default_output_filename;
  const scenario = document.getElementById('scenarioSelect');
  scenario.innerHTML = spec.scenarios.map(s => `<option value="${s.id}">${escapeHtml(s.label)}</option>`).join('');
  renderParameterForm();
}
function renderParameterForm() {
  const spec = state.selectedGeneratorSpec; const box = document.getElementById('parameterForm');
  if (!spec) { box.innerHTML = ''; return; }
  box.innerHTML = spec.parameters.map(p => {
    const unit = p.unit ? ` (${p.unit})` : '';
    if (p.type === 'select') return `<label>${escapeHtml(p.label + unit)}<select data-param="${p.name}">${(p.options || []).map(o => `<option value="${o}" ${o === p.default ? 'selected' : ''}>${escapeHtml(o)}</option>`).join('')}</select></label>`;
    const inputType = p.type === 'datetime' ? 'text' : p.type;
    return `<label>${escapeHtml(p.label + unit)}<input data-param="${p.name}" type="${inputType}" value="${escapeHtml(p.default ?? '')}" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} ${p.step != null ? `step="${p.step}"` : ''}></label>`;
  }).join('');
}
function collectGeneratorRequest(loadIntoReplay = false) {
  const params = {};
  document.querySelectorAll('[data-param]').forEach(el => {
    const spec = state.selectedGeneratorSpec.parameters.find(p => p.name === el.dataset.param);
    params[el.dataset.param] = spec?.type === 'number' ? Number(el.value) : el.value;
  });
  const req = {scenario: document.getElementById('scenarioSelect').value, output_filename: document.getElementById('outputFilename').value, parameters: params, load_into_replay: loadIntoReplay};
  state.lastGeneratorRequest = {domain_id: state.selectedDomainId, ...req};
  return req;
}
async function generate(loadIntoReplay = false) {
  const req = collectGeneratorRequest(loadIntoReplay);
  const data = await api(`/api/generators/${state.selectedDomainId}/generate`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(req)});
  document.getElementById('generationSummary').textContent = `${data.filename} generated with ${data.row_count} rows and ${data.column_count} columns.`;
  document.getElementById('generationPreview').innerHTML = table(data.preview);
  showMessage(`Generated ${data.filename}`, 'success');
  await refreshFiles();
  if (loadIntoReplay) await loadCsvIntoReplay(data.filename, 'generated');
}

async function refreshFiles() {
  const data = await api('/api/csv/files');
  state.files = data.files;
  document.getElementById('filesTable').innerHTML = table(data.files, ['filename','source','row_count','column_count','modified_at'], r => {
    const key = fileKey(r);
    return `<div class="file-actions">
      <label class="checkbox-line"><input type="checkbox" data-shared-file-key="${escapeHtml(key)}" ${state.selectedShared.has(key) ? 'checked' : ''}/> Shared / Both</label>
      <label class="checkbox-line"><input type="checkbox" data-opcua-file-key="${escapeHtml(key)}" ${state.selectedOpcua.has(key) ? 'checked' : ''}/> OPC UA Plan</label>
      <label class="checkbox-line"><input type="checkbox" data-mqtt-file-key="${escapeHtml(key)}" ${state.selectedMqtt.has(key) ? 'checked' : ''}/> MQTT Plan</label>
      <button onclick="previewCsv('${encodeURIComponent(r.filename)}','${r.source}')">Preview</button>
      <button onclick="loadCsvIntoReplay('${encodeURIComponent(r.filename)}','${r.source}')">Load Manual</button>
      <button onclick="deleteCsv('${encodeURIComponent(r.filename)}','${r.source}')">Delete</button>
    </div>`;
  });
  document.querySelectorAll('[data-shared-file-key]').forEach(cb => cb.addEventListener('change', e => { e.target.checked ? state.selectedShared.add(e.target.dataset.sharedFileKey) : state.selectedShared.delete(e.target.dataset.sharedFileKey); updateAssignments(); markTagPlanDirty(); }));
  document.querySelectorAll('[data-opcua-file-key]').forEach(cb => cb.addEventListener('change', e => { e.target.checked ? state.selectedOpcua.add(e.target.dataset.opcuaFileKey) : state.selectedOpcua.delete(e.target.dataset.opcuaFileKey); updateAssignments(); markTagPlanDirty(); }));
  document.querySelectorAll('[data-mqtt-file-key]').forEach(cb => cb.addEventListener('change', e => { e.target.checked ? state.selectedMqtt.add(e.target.dataset.mqttFileKey) : state.selectedMqtt.delete(e.target.dataset.mqttFileKey); updateAssignments(); markTagPlanDirty(); }));
  updateAssignments();
}
window.previewCsv = async function(filenameEnc, source) {
  const filename = decodeURIComponent(filenameEnc);
  const data = await api(`/api/csv/files/${encodeURIComponent(filename)}/metadata?source=${source}`);
  document.getElementById('filePreviewMeta').textContent = `${filename} | ${source} | ${data.row_count} rows | ${data.column_count} columns`;
  document.getElementById('filePreview').innerHTML = table(data.preview);
};
window.loadCsvIntoReplay = async function(filenameEnc, source) {
  const filename = decodeURIComponent(filenameEnc);
  const data = await api(`/api/csv/files/${encodeURIComponent(filename)}/load?source=${source}`, {method:'POST'});
  state.selectedCsvFile = {filename, source}; state.selectedCsvMetadata = data;
  document.getElementById('replayCsvName').textContent = filename;
  document.getElementById('replayCsvSource').textContent = source;
  document.getElementById('replayRows').textContent = data.row_count;
  document.getElementById('replayCols').textContent = data.column_count;
  renderMappingTable(data.default_tag_mappings);
  switchTab('replay'); showMessage(`Loaded ${filename} into manual replay mapping.`, 'success');
};
window.deleteCsv = async function(filenameEnc, source) {
  const filename = decodeURIComponent(filenameEnc);
  if (source === 'sample') return showMessage('Sample files cannot be deleted.', 'error');
  await api(`/api/csv/files/${encodeURIComponent(filename)}?source=${source}`, {method:'DELETE'});
  showMessage(`Deleted ${filename}`, 'success'); await refreshFiles();
};
async function uploadCsv() {
  const input = document.getElementById('uploadInput');
  if (!input.files.length) throw new Error('Choose one or more CSV/XLSX files first.');
  for (const file of input.files) { const form = new FormData(); form.append('file', file); await api('/api/csv/upload', {method:'POST', body:form}); }
  showMessage(`Uploaded ${input.files.length} file(s).`, 'success'); input.value = ''; await refreshFiles();
}

function renderMappingTable(mappings) {
  const rows = mappings || [];
  if (!rows.length) { document.getElementById('mappingTable').innerHTML = '<div class="hint">No CSV/XLSX loaded.</div>'; return; }
  const body = rows.map((m, i) => `<tr data-map-row="${i}">
    <td><input type="checkbox" data-field="enabled" ${m.enabled ? 'checked' : ''}></td><td class="mono">${escapeHtml(m.csv_column)}</td>
    <td><input data-field="tag_name" value="${escapeHtml(m.tag_name)}"></td><td><input data-field="node_id" value="${escapeHtml(m.node_id)}"></td>
    <td><select data-field="data_type">${['Double','Int64','Boolean','String'].map(t => `<option ${m.data_type === t ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
    <td><input data-field="initial_value" value="${escapeHtml(m.initial_value ?? '')}"></td><td><input type="checkbox" data-field="writable" ${m.writable ? 'checked' : ''}></td>
  </tr>`).join('');
  document.getElementById('mappingTable').innerHTML = `<table><thead><tr><th>Enable</th><th>CSV/XLSX Column</th><th>Tag Name</th><th>Node ID / Topic Suffix</th><th>Type</th><th>Initial</th><th>Writable</th></tr></thead><tbody>${body}</tbody></table>`;
}
function collectMappings() {
  const mappings = []; const defaults = state.selectedCsvMetadata?.default_tag_mappings || [];
  document.querySelectorAll('[data-map-row]').forEach(row => {
    const i = Number(row.dataset.mapRow); const base = defaults[i]; const get = f => row.querySelector(`[data-field="${f}"]`);
    mappings.push({enabled:get('enabled').checked, csv_column:base.csv_column, tag_name:get('tag_name').value, node_id:get('node_id').value, data_type:get('data_type').value, initial_value:get('initial_value').value || null, writable:get('writable').checked});
  });
  return mappings;
}
function commonReplayFields() {
  const maxRows = document.getElementById('maxRows').value;
  return {
    protocol: document.getElementById('protocolMode').value,
    frequency_hz: Number(document.getElementById('frequencyHz').value), loop_mode: document.getElementById('loopMode').value,
    timestamp_mode: document.getElementById('timestampMode').value, start_row: Number(document.getElementById('startRow').value), max_rows: maxRows ? Number(maxRows) : null,
    namespace_uri: document.getElementById('namespaceUri').value, root_folder: document.getElementById('rootFolder').value, node_id_prefix: document.getElementById('nodePrefix').value,
    mqtt_host: document.getElementById('mqttHost').value, mqtt_port: Number(document.getElementById('mqttPort').value), mqtt_topic_prefix: document.getElementById('mqttTopicPrefix').value,
    mqtt_device_id: document.getElementById('mqttDeviceId').value || 'FlowMeter01', mqtt_client_id: document.getElementById('mqttClientId').value, mqtt_username: document.getElementById('mqttUsername').value || null, mqtt_password: document.getElementById('mqttPassword').value || null,
    mqtt_qos: Number(document.getElementById('mqttQos').value), mqtt_retain: document.getElementById('mqttRetain').checked,
    publish_individual_tags: document.getElementById('publishIndividualTags').checked, publish_aggregate: document.getElementById('publishAggregate').checked
  };
}
function collectReplayConfig() {
  return {...commonReplayFields(), csv_file: state.selectedCsvFile.filename, csv_source: state.selectedCsvFile.source, tags: collectMappings()};
}
async function applyReplayConfig() {
  if (!state.selectedCsvFile) {
    const hasProtocolPlan = state.selectedShared.size || state.selectedOpcua.size || state.selectedMqtt.size;
    if (hasProtocolPlan) {
      showMessage('Manual config is only for a single file loaded with Load Manual. Your protocol plan is ready; click Start to run it.', 'info');
      return;
    }
    throw new Error('Manual config needs a CSV/XLSX loaded with Load Manual. For OPC UA Plan / MQTT Plan, select files, click Apply Selected Protocol Plans, then click Start.');
  }
  const config = collectReplayConfig();
  const data = await api('/api/replay/configure', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(config)});
  state.replayConfig = config; state.replayConfiguredMode = 'manual'; showMessage(`Manual replay configured with ${data.tag_count} tags. Click Start to run.`, 'success'); await refreshStatus();
}
async function applyMultiReplayConfig(showSuccess = true) {
  if (!state.tagPlanBuilt || state.tagPlanDirty) {
    await buildTagPlanPreview(false);
  }
  const cfg = {...commonReplayFields(), files:selectedFilesFrom(state.selectedShared), opcua_files:selectedFilesFrom(state.selectedOpcua), mqtt_files:selectedFilesFrom(state.selectedMqtt), tag_selections: collectTagSelections()};
  if (cfg.protocol === 'both') {
    if (!cfg.files.length && (!cfg.opcua_files.length || !cfg.mqtt_files.length)) throw new Error('BOTH mode needs either Shared / Both files, or at least one OPC UA Plan file and one MQTT Plan file.');
    if (!state.tagPlan.opcua.some(t => t.enabled)) throw new Error('Select at least one OPC UA tag in the tag preview.');
    if (!state.tagPlan.mqtt.some(t => t.enabled)) throw new Error('Select at least one MQTT tag in the tag preview.');
  } else if (!cfg.files.length) {
    const protocolSet = cfg.protocol === 'opcua' ? cfg.opcua_files : cfg.mqtt_files;
    if (!protocolSet.length) throw new Error(`Select Shared files or ${cfg.protocol.toUpperCase()} files.`);
    cfg.files = protocolSet;
    if (!state.tagPlan[cfg.protocol].some(t => t.enabled)) throw new Error(`Select at least one ${cfg.protocol.toUpperCase()} tag in the tag preview.`);
  }
  const data = await api('/api/replay/configure-files', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cfg)});
  state.replayConfig = {...cfg, configure_type: 'protocol_plans'};
  state.replayConfiguredMode = 'protocol_plans';
  const txt = data.assignment_mode === 'separate' ? `OPC UA Plan ${data.opcua_file_count || 0}, MQTT Plan ${data.mqtt_file_count || 0}` : `${data.file_count} file(s)`;
  const opc = tagPlanCounts('opcua');
  const mqtt = tagPlanCounts('mqtt');
  if (showSuccess) showMessage(`${String(data.protocol).toUpperCase()} configured: ${txt}, ${data.tag_count} selected tags. OPC UA selected ${opc.selected}, MQTT selected ${mqtt.selected}. Click Start to run.`, 'success');
  await refreshStatus();
}

async function startReplay() {
  const hasProtocolPlan = state.selectedShared.size || state.selectedOpcua.size || state.selectedMqtt.size;
  if (!state.selectedCsvFile && hasProtocolPlan && state.replayConfiguredMode !== 'protocol_plans') {
    if (!state.tagPlanBuilt || state.tagPlanDirty) {
      await buildTagPlanPreview(false);
      showMessage('Review the selected/unselected tag list, then click Apply Selected Protocol Plans. Start will run only after the plan is applied.', 'info');
      return;
    }
    showMessage('Click Apply Selected Protocol Plans first. Then click Start to run the selected tags.', 'info');
    return;
  }
  await api('/api/replay/start', {method:'POST'});
  showMessage('Replay started.', 'success');
  await refreshStatus();
}
async function refreshCurrentValues() { try { const data = await api('/api/replay/current-values'); state.currentValues = data.values; document.getElementById('currentValues').innerHTML = table(data.values, ['tag_name','node_id','value','data_type','last_updated']); } catch (_) {} }
async function refreshConfigs() { const data = await api('/api/configs'); document.getElementById('configsTable').innerHTML = table(data.configs, ['name','description','created_at','modified_at'], r => `<button onclick="loadConfig('${encodeURIComponent(r.name)}')">Load</button><button onclick="deleteConfig('${encodeURIComponent(r.name)}')">Delete</button>`); }
function buildCurrentConfig() { return {name:document.getElementById('configName').value, description:document.getElementById('configDescription').value, generator:state.lastGeneratorRequest, csv:state.selectedCsvFile, replay:state.selectedCsvFile ? collectReplayConfig() : state.replayConfig}; }
async function saveConfig() { const cfg = buildCurrentConfig(); if (!cfg.name) throw new Error('Config name is required.'); await api('/api/configs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cfg)}); showMessage(`Saved config ${cfg.name}`, 'success'); await refreshConfigs(); }
window.loadConfig = async function(nameEnc) {
  const name = decodeURIComponent(nameEnc); const cfg = await api(`/api/configs/${encodeURIComponent(name)}`);
  document.getElementById('configName').value = cfg.name; document.getElementById('configDescription').value = cfg.description || '';
  if (cfg.csv?.filename) await loadCsvIntoReplay(encodeURIComponent(cfg.csv.filename), cfg.csv.source || 'generated');
  if (cfg.replay) {
    document.getElementById('protocolMode').value = cfg.replay.protocol || 'opcua';
    document.getElementById('frequencyHz').value = cfg.replay.frequency_hz ?? 1; document.getElementById('loopMode').value = cfg.replay.loop_mode ?? 'loop_forever';
    document.getElementById('timestampMode').value = cfg.replay.timestamp_mode ?? 'wall_clock'; document.getElementById('startRow').value = cfg.replay.start_row ?? 0;
    document.getElementById('namespaceUri').value = cfg.replay.namespace_uri ?? 'http://local/industrial-tag-simulator'; document.getElementById('rootFolder').value = cfg.replay.root_folder ?? 'TagSimulator'; document.getElementById('nodePrefix').value = cfg.replay.node_id_prefix ?? 'TagSimulator';
    if (cfg.replay.tags) renderMappingTable(cfg.replay.tags); updateProtocolCards();
  }
  showMessage(`Loaded config ${name}`, 'success');
};
window.deleteConfig = async function(nameEnc) { const name = decodeURIComponent(nameEnc); await api(`/api/configs/${encodeURIComponent(name)}`, {method:'DELETE'}); showMessage(`Deleted ${name}`, 'success'); await refreshConfigs(); };
function setAllMappings(enabled) { document.querySelectorAll('[data-field="enabled"]').forEach(cb => cb.checked = enabled); }
function disableLabelColumns() {
  const defaults = state.selectedCsvMetadata?.default_tag_mappings || [];
  document.querySelectorAll('[data-map-row]').forEach(row => { const name = defaults[Number(row.dataset.mapRow)].csv_column.toLowerCase(); if (['timestamp','scenario','operating_state','phase','product','heat_id'].includes(name) || name.endsWith('_active') || name.endsWith('_alarm')) row.querySelector('[data-field="enabled"]').checked = false; });
}
function updateProtocolCards() {
  const mode = document.getElementById('protocolMode').value;
  document.getElementById('opcCard').style.display = (mode === 'opcua' || mode === 'both') ? '' : 'none';
  document.getElementById('mqttCard').style.display = (mode === 'mqtt' || mode === 'both') ? '' : 'none';
}

document.getElementById('domainSelect').addEventListener('change', e => loadGeneratorSpec(e.target.value).catch(err => showMessage(err.message, 'error')));
document.getElementById('generateBtn').addEventListener('click', () => generate(false).catch(e => showMessage(e.message, 'error')));
document.getElementById('generateLoadBtn').addEventListener('click', () => generate(true).catch(e => showMessage(e.message, 'error')));
document.getElementById('resetParamsBtn').addEventListener('click', renderParameterForm);
document.getElementById('refreshFilesBtn').addEventListener('click', () => refreshFiles().catch(e => showMessage(e.message, 'error')));
document.getElementById('uploadBtn').addEventListener('click', () => uploadCsv().catch(e => showMessage(e.message, 'error')));
document.getElementById('applyReplayBtn').addEventListener('click', () => applyReplayConfig().catch(e => showMessage(e.message, 'error')));
document.getElementById('previewTagPlanBtn').addEventListener('click', () => buildTagPlanPreview().catch(e => showMessage(e.message, 'error')));
document.getElementById('selectAllOpcuaTagsBtn').addEventListener('click', () => setTagPlanProtocol('opcua', true));
document.getElementById('clearOpcuaTagsBtn').addEventListener('click', () => setTagPlanProtocol('opcua', false));
document.getElementById('selectAllMqttTagsBtn').addEventListener('click', () => setTagPlanProtocol('mqtt', true));
document.getElementById('clearMqttTagsBtn').addEventListener('click', () => setTagPlanProtocol('mqtt', false));
document.getElementById('applyMultiReplayBtn').addEventListener('click', () => applyMultiReplayConfig().catch(e => showMessage(e.message, 'error')));
document.getElementById('startReplayBtn').addEventListener('click', () => startReplay().catch(e => showMessage(e.message, 'error')));
document.getElementById('stopReplayBtn').addEventListener('click', () => api('/api/replay/stop', {method:'POST'}).then(refreshStatus).catch(e => showMessage(e.message, 'error')));
document.getElementById('restartReplayBtn').addEventListener('click', () => api('/api/replay/restart', {method:'POST'}).then(refreshStatus).catch(e => showMessage(e.message, 'error')));
document.getElementById('resetCursorBtn').addEventListener('click', () => api('/api/replay/reset-cursor', {method:'POST'}).then(refreshStatus).catch(e => showMessage(e.message, 'error')));
document.getElementById('quickStopBtn').addEventListener('click', () => api('/api/replay/stop', {method:'POST'}).then(refreshStatus).catch(e => showMessage(e.message, 'error')));
document.getElementById('quickRestartBtn').addEventListener('click', () => api('/api/replay/restart', {method:'POST'}).then(refreshStatus).catch(e => showMessage(e.message, 'error')));
document.getElementById('refreshStatusBtn').addEventListener('click', refreshStatus);
document.getElementById('autoMapBtn').addEventListener('click', () => renderMappingTable(state.selectedCsvMetadata?.default_tag_mappings || []));
document.getElementById('disableLabelsBtn').addEventListener('click', disableLabelColumns);
document.getElementById('enableAllBtn').addEventListener('click', () => setAllMappings(true));
document.getElementById('disableAllBtn').addEventListener('click', () => setAllMappings(false));
document.getElementById('saveConfigBtn').addEventListener('click', () => saveConfig().catch(e => showMessage(e.message, 'error')));
document.getElementById('exportConfigBtn').addEventListener('click', () => { const blob = new Blob([JSON.stringify(buildCurrentConfig(), null, 2)], {type:'application/json'}); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${document.getElementById('configName').value || 'simulator-config'}.json`; a.click(); });
document.getElementById('importConfigBtn').addEventListener('click', () => document.getElementById('importConfigInput').click());
document.getElementById('importConfigInput').addEventListener('change', async e => { const file = e.target.files[0]; if (!file) return; const cfg = JSON.parse(await file.text()); await api('/api/configs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(cfg)}); await refreshConfigs(); showMessage(`Imported ${cfg.name}`, 'success'); });
document.getElementById('protocolMode').addEventListener('change', () => { updateProtocolCards(); markTagPlanDirty(); renderTagPlanPreview(); });

async function safeStartupStep(fn, name) {
  try { await fn(); } catch (e) { showMessage(`${name}: ${e.message}`, 'error'); }
}

function applyLauncherConfigDefaults() {
  const cfg = window.SIMULATOR_LAUNCHER_CONFIG || {};
  if (cfg.mqtt_host && document.getElementById('mqttHost')) document.getElementById('mqttHost').value = cfg.mqtt_host;
  if (cfg.mqtt_port && document.getElementById('mqttPort')) document.getElementById('mqttPort').value = cfg.mqtt_port;
  if (cfg.mqtt_device_id && document.getElementById('mqttDeviceId')) document.getElementById('mqttDeviceId').value = cfg.mqtt_device_id;
  if (cfg.opcua_port && document.getElementById('opcuaEndpointDisplay')) document.getElementById('opcuaEndpointDisplay').value = `opc.tcp://localhost:${cfg.opcua_port}/simulator`;
}

async function init() {
  switchTab((window.location.hash || '#generate').slice(1), false);
  applyLauncherConfigDefaults();
  updateProtocolCards();
  renderTagPlanPreview();
  await safeStartupStep(loadGenerators, 'Generators');
  await safeStartupStep(refreshFiles, 'Files');
  await safeStartupStep(refreshConfigs, 'Configs');
  await safeStartupStep(refreshStatus, 'Status');
  setInterval(() => refreshStatus().catch(() => {}), 1000);
  setInterval(() => refreshCurrentValues().catch(() => {}), 1000);
}
init().catch(e => showMessage(e.message, 'error'));
