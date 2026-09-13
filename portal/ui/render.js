import {
  canEdit,
  canPause,
  canResume,
  canStart,
  canStop,
  opcUaTargets,
  simulationProgress,
  sourceKindLabel,
  sourceLabel,
  statusTarget,
  targetLabel,
} from "./model.js";

const TABS = [
  ["overview", "Overview"],
  ["source", "Source"],
  ["timing", "Timing & Replay"],
  ["mapping", "Signals & Mapping"],
  ["targets", "Targets"],
];

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function attr(value) { return esc(value); }
function checked(value) { return value ? "checked" : ""; }
function selected(value, expected) { return String(value ?? "") === String(expected) ? "selected" : ""; }
function disabled(value) { return value ? "disabled" : ""; }

function stateClass(state) {
  return ["running", "paused", "degraded", "error"].includes(state) ? state : "";
}

function humanState(state) {
  if (state === "created") return "Configured";
  if (state === "starting") return "Starting";
  return state ? state[0].toUpperCase() + state.slice(1) : "Unknown";
}

function percent(value) {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}

function endpointFor(target) {
  if (!target) return "";
  const config = target.config || {};
  if (target.kind === "opcua") {
    const host = config.advertised_host || "localhost";
    const port = config.port || 4840;
    const path = String(config.path || "simulator").replace(/^\/+|\/+$/g, "");
    return `opc.tcp://${host}:${port}/${path}`;
  }
  if (target.kind === "mqtt") return `${config.host || "localhost"}:${config.port || 1883}/${config.topic_prefix || ""}`;
  if (target.kind === "sql_server") return `${config.server || "localhost"}:${config.port || 1433}/${config.database || ""}`;
  if (target.kind === "odata") return `/odata/simulations/{simulation}/${target.target_id}`;
  if (target.kind === "http") return `/api/v2/simulations/{simulation}/targets/${target.target_id}`;
  return target.target_id;
}

export function renderRailSummary(simulations) {
  const states = simulations.map((item) => item.status?.state);
  const running = states.filter((state) => state === "running" || state === "degraded").length;
  const issues = states.filter((state) => state === "error" || state === "degraded").length;
  const opcua = simulations.reduce((count, item) => count + opcUaTargets(item.definition).length, 0);
  return `
    <div class="summary-cell"><span>Active</span><strong>${running}</strong></div>
    <div class="summary-cell"><span>OPC UA</span><strong>${opcua}</strong></div>
    <div class="summary-cell"><span>Issues</span><strong>${issues}</strong></div>`;
}

export function renderSimulationList(simulations, selectedId) {
  if (!simulations.length) return `<div class="simulation-list-empty">No simulations match the current filter.</div>`;
  return simulations.map((item) => {
    const definition = item.definition;
    const status = item.status || {};
    const progress = simulationProgress(status);
    const targets = (definition.targets || []).filter((target) => target.enabled).slice(0, 4);
    return `
      <button class="sim-row ${definition.simulation_id === selectedId ? "selected" : ""}" data-select-simulation="${attr(definition.simulation_id)}">
        <div class="sim-row-head">
          <span class="sim-state-mark ${stateClass(status.state)}"></span>
          <div class="sim-row-title">
            <strong>${esc(definition.name)}</strong>
            <span>${esc(definition.simulation_id)}</span>
          </div>
          <span class="sim-state-text">${esc(humanState(status.state))}</span>
        </div>
        <div class="sim-row-meta">
          <span class="sim-row-source">${esc(sourceKindLabel(definition.source?.kind))} · ${esc(sourceLabel(definition.source))}</span>
          <span class="sim-targets">${targets.map((target) => `<span class="target-glyph ${target.kind === "opcua" ? "opcua" : ""}">${esc(target.kind === "opcua" ? "UA" : target.kind.slice(0, 3).toUpperCase())}</span>`).join("")}</span>
        </div>
        <div class="sim-progress">
          <span class="progress-track"><span class="progress-fill" style="width:${progress ?? 0}%"></span></span>
          <span>${percent(progress)}</span>
        </div>
      </button>`;
  }).join("");
}

export function renderDetailHeader(definition, status, dirty, isNew) {
  const source = `${sourceKindLabel(definition.source?.kind)} · ${sourceLabel(definition.source)}`;
  const targetCount = (definition.targets || []).filter((target) => target.enabled).length;
  const progress = simulationProgress(status);
  const editLocked = !canEdit(status);
  return `
    <div class="detail-title-row">
      <div class="detail-title">
        <div class="detail-title-line">
          <h2>${esc(definition.name || "Simulation")}</h2>
          <span class="status-word ${stateClass(status?.state)}">${esc(isNew ? "New" : humanState(status?.state))}</span>
          ${dirty ? `<span class="unsaved-note">Unsaved changes</span>` : ""}
        </div>
        <div class="detail-id">${esc(definition.simulation_id)}</div>
      </div>
      <div class="detail-actions">
        ${isNew ? "" : `<button class="button secondary" data-action="duplicate">Duplicate</button>`}
        <button class="button secondary" data-action="save" ${disabled(editLocked && !isNew)}>Save</button>
        <button class="button primary" data-action="start" ${disabled(!canStart(status) && !isNew)}>Start</button>
        <button class="button secondary" data-action="pause" ${disabled(!canPause(status))}>Pause</button>
        <button class="button secondary" data-action="resume" ${disabled(!canResume(status))}>Resume</button>
        <button class="button danger" data-action="stop" ${disabled(!canStop(status))}>Stop</button>
        <button class="button danger" data-action="delete">${isNew ? "Discard" : "Delete"}</button>
      </div>
    </div>
    <div class="detail-subline">
      <span><strong>${esc(source)}</strong></span>
      <span class="inline-separator"></span>
      <span>${esc(definition.clock?.mode === "source_timestamp" ? `${definition.clock.speed}× source time` : `${definition.clock?.frequency_hz || 1} Hz`)}</span>
      <span class="inline-separator"></span>
      <span>${targetCount} target${targetCount === 1 ? "" : "s"}</span>
      <span class="inline-separator"></span>
      <span>${status?.emitted_count || 0} frames</span>
      ${progress == null ? "" : `<span class="inline-separator"></span><span>${percent(progress)} source progress</span>`}
    </div>`;
}

export function renderTabs(activeTab) {
  return TABS.map(([id, label]) => `<button class="detail-tab ${activeTab === id ? "active" : ""}" data-tab="${id}" role="tab">${label}</button>`).join("");
}

export function renderTab(activeTab, context) {
  const renderers = {
    overview: renderOverview,
    source: renderSource,
    timing: renderTiming,
    mapping: renderMapping,
    targets: renderTargets,
  };
  return `<div class="content-width">${(renderers[activeTab] || renderOverview)(context)}</div>`;
}

function renderOverview({ definition, status, snapshot }) {
  const progress = simulationProgress(status);
  const opcua = opcUaTargets(definition)[0];
  const opcStatus = opcua ? statusTarget(status, opcua.target_id) : null;
  const values = Object.entries(snapshot?.frame?.values || {}).slice(0, 50);
  return `
    <div class="section-stack">
      <div class="metric-grid">
        ${metric("State", humanState(status?.state), status?.last_error || "Simulation lifecycle")}
        ${metric("Frames", status?.emitted_count || 0, "Emitted canonical frames")}
        ${metric("Source", status?.source_count == null ? status?.source_position || 0 : `${status.source_position || 0} / ${status.source_count}`, progress == null ? "Position" : `${percent(progress)} complete`)}
        ${metric("OPC UA", opcStatus?.published_frames ?? 0, opcStatus?.endpoint || (opcua ? endpointFor(opcua) : "No OPC UA target"))}
      </div>
      <div class="two-col">
        <section class="panel">
          <div class="panel-head"><div><h3>Target health</h3><p>Independent delivery state for this simulation.</p></div></div>
          <div class="panel-body">${renderTargetHealth(definition, status)}</div>
        </section>
        <section class="panel">
          <div class="panel-head"><div><h3>Simulation definition</h3><p>The persisted configuration driving this runtime instance.</p></div></div>
          <div class="panel-body">
            <dl class="key-value">
              <dt>Source</dt><dd>${esc(sourceKindLabel(definition.source?.kind))}</dd>
              <dt>Source identity</dt><dd>${esc(sourceLabel(definition.source))}</dd>
              <dt>Clock</dt><dd>${esc(definition.clock?.mode || "fixed_rate")}</dd>
              <dt>Loop</dt><dd>${esc(definition.loop_mode)}</dd>
              <dt>Mappings</dt><dd>${definition.mappings?.length || 0}</dd>
              <dt>World</dt><dd>${esc(definition.world_id || "None")}</dd>
              <dt>Updated</dt><dd>${esc(status?.updated_at || "—")}</dd>
            </dl>
          </div>
        </section>
      </div>
      <section class="panel">
        <div class="panel-head"><div><h3>Current values</h3><p>Latest canonical frame after mappings, before protocol-specific projection.</p></div><span class="muted">${values.length} shown</span></div>
        <div class="panel-body">${values.length ? renderValueTable(values) : `<div class="notice info">Start the simulation to inspect live canonical values.</div>`}</div>
      </section>
    </div>`;
}

function renderSource({ definition, editable, resources, generatorSpec, preview }) {
  const source = definition.source || { kind: "csv", config: {} };
  const config = source.config || {};
  const kind = source.kind;
  return `
    <div class="section-stack">
      ${!editable ? lockedNotice() : ""}
      <section class="panel">
        <div class="panel-head"><div><h3>Identity</h3><p>Stable simulation ID with a user-facing name.</p></div></div>
        <div class="panel-body"><div class="form-grid">
          ${fieldText("Simulation name", "name", definition.name || "Simulation", "span-6", editable, "Used throughout the workspace and protocol diagnostics.")}
          ${readOnlyField("Simulation ID", definition.simulation_id, "span-6", "Stable runtime identity; duplicate to create a new ID.")}
        </div></div>
      </section>
      <section class="panel">
        <div class="panel-head"><div><h3>Source</h3><p>One source drives this simulation. Targets never know where values came from.</p></div><div class="panel-actions"><button class="button secondary" data-action="preview-source">Preview source</button></div></div>
        <div class="panel-body">
          <div class="form-grid">
            ${fieldSelect("Source type", "source.kind", kind, [
              ["csv", "CSV / Excel file"], ["dataset", "Registered dataset"], ["generator", "Domain generator"], ["sap_pp", "SAP PP source"], ["lims_odbc", "LIMS source"],
            ], "span-4", editable)}
            ${kind === "csv" ? renderCsvSource(config, resources, editable) : ""}
            ${kind === "dataset" ? renderDatasetSource(config, resources, editable) : ""}
            ${kind === "generator" ? renderGeneratorSource(config, resources, generatorSpec, editable) : ""}
            ${kind === "sap_pp" || kind === "lims_odbc" ? renderEnterpriseSource(kind, config, editable) : ""}
          </div>
        </div>
      </section>
      ${preview ? renderPreview(preview) : `<div class="notice info"><strong>Preview before mapping.</strong> The preview opens this exact source definition without starting any target and shows the schema the runtime will use.</div>`}
    </div>`;
}

function renderCsvSource(config, resources, editable) {
  const area = config.csv_source || "uploaded";
  const files = (resources.files || []).filter((file) => file.source === area);
  return `
    ${fieldSelect("File area", "source.config.csv_source", area, [["uploaded", "Uploaded"], ["generated", "Generated"], ["sample", "Sample"]], "span-4", editable)}
    ${fieldSelect("File", "source.config.filename", config.filename || "", [["", files.length ? "Select file" : "No files in this area"], ...files.map((file) => [file.filename, `${file.filename} · ${file.row_count} rows`])], "span-8", editable)}
    ${fieldNumber("Start row", "source.config.start_row", config.start_row ?? 0, "span-4", editable, "integer")}
    ${fieldNumber("Maximum rows", "source.config.max_rows", config.max_rows ?? "", "span-4", editable, "integer", "Blank means all available rows.")}
    ${fieldText("Context fields", "source.config.context_fields_text", Array.isArray(config.context_fields) ? config.context_fields.join(", ") : (config.context_fields_text || ""), "span-4", editable, "Comma-separated fields to keep in frame context.", "context-fields")}`;
}

function renderDatasetSource(config, resources, editable) {
  const datasets = resources.datasets || [];
  return `
    ${fieldSelect("Dataset", "source.config.dataset_id", config.dataset_id || "", [["", "Select dataset"], ...datasets.map((dataset) => [dataset.dataset_id, `${dataset.name || dataset.dataset_id} · ${dataset.storage_format || "dataset"}`])], "span-8", editable)}
    ${fieldNumber("Start row", "source.config.start_row", config.start_row ?? 0, "span-4", editable, "integer")}
    ${fieldNumber("Maximum rows", "source.config.max_rows", config.max_rows ?? "", "span-4", editable, "integer", "Blank means all available rows.")}
    ${fieldText("Context fields", "source.config.context_fields_text", Array.isArray(config.context_fields) ? config.context_fields.join(", ") : (config.context_fields_text || ""), "span-8", editable, "Comma-separated frame context fields.", "context-fields")}`;
}

function renderGeneratorSource(config, resources, spec, editable) {
  const generators = resources.generators || [];
  const scenarios = spec?.scenarios || [];
  const parameters = spec?.parameters || [];
  return `
    ${fieldSelect("Generator", "source.config.domain_id", config.domain_id || "", [["", "Select domain generator"], ...generators.map((item) => [item.domain_id, item.display_name])], "span-6", editable, "generator-domain")}
    ${fieldSelect("Scenario", "source.config.scenario", config.scenario || scenarios[0]?.id || "", [["", "Select scenario"], ...scenarios.map((item) => [item.id, item.label])], "span-6", editable)}
    ${parameters.length ? `<div class="form-divider"></div><div class="subsection-title">Generator parameters</div>${parameters.map((parameter) => renderGeneratorParameter(parameter, config.parameters?.[parameter.name], editable)).join("")}` : ""}
  `;
}

function renderGeneratorParameter(parameter, value, editable) {
  const path = `source.config.parameters.${parameter.name}`;
  const span = "span-4";
  const actual = value ?? parameter.default ?? "";
  if (parameter.type === "select") return fieldSelect(parameter.label, path, actual, (parameter.options || []).map((option) => [String(option), String(option)]), span, editable, null, parameter.description);
  if (parameter.type === "number") return fieldNumber(parameter.label, path, actual, span, editable, "number", parameter.description, parameter.min, parameter.max, parameter.step);
  return fieldText(parameter.label, path, actual, span, editable, parameter.description);
}

function renderEnterpriseSource(kind, config, editable) {
  const defaultEntity = kind === "sap_pp" ? "production_orders" : "samples";
  return `
    ${fieldText("Entity", "source.config.entity", config.entity || defaultEntity, "span-6", editable, "Entity exposed by the existing source simulator.")}
    ${fieldNumber("Seed cycles", "source.config.seed_cycles", config.seed_cycles ?? 1, "span-3", editable, "integer")}
    ${fieldNumber("Top rows", "source.config.top", config.top ?? "", "span-3", editable, "integer", "Blank returns all matching rows.")}
    ${fieldText("Filter", "source.config.filter_text", config.filter_text || "", "span-6", editable, "Existing simple source-simulator filter expression.")}
    ${fieldText("Watermark", "source.config.watermark", config.watermark || "", "span-6", editable, "Optional source watermark.")}`;
}

function renderPreview(preview) {
  const schema = preview.source_schema || [];
  const sample = preview.sample_frame?.values || preview.raw_sample_frame?.values || {};
  return `
    ${preview.mapping_error ? `<div class="notice warning"><strong>Mapping needs attention.</strong> ${esc(preview.mapping_error)}. The raw source schema is still shown below so you can reload or repair the mapping.</div>` : ""}
    <section class="panel">
      <div class="panel-head"><div><h3>Source preview</h3><p>${esc(preview.source_kind)} · ${preview.source_count ?? "unknown"} rows/samples</p></div><button class="button primary" data-action="seed-mappings">Use schema for mappings</button></div>
      <div class="panel-body">
        <div class="table-shell">
          <div class="table-scroll">
            <table class="data-table"><thead><tr><th style="width:28%">Signal</th><th style="width:24%">Node ID</th><th style="width:16%">Type</th><th style="width:14%">Unit</th><th>Sample</th></tr></thead><tbody>
              ${schema.map((signal) => `<tr><td>${esc(signal.name)}</td><td class="mono">${esc(signal.node_id)}</td><td>${esc(signal.data_type)}</td><td>${esc(signal.unit || "—")}</td><td class="mono">${esc(sample[signal.name]?.value ?? "—")}</td></tr>`).join("")}
            </tbody></table>
          </div>
        </div>
      </div>
    </section>`;
}

function renderTiming({ definition, editable }) {
  const clock = definition.clock || {};
  return `
    <div class="section-stack">
      ${!editable ? lockedNotice() : ""}
      <section class="panel">
        <div class="panel-head"><div><h3>Simulation clock</h3><p>Independent timing for this simulation instance.</p></div></div>
        <div class="panel-body"><div class="form-grid">
          ${fieldSelect("Clock mode", "clock.mode", clock.mode || "fixed_rate", [["fixed_rate", "Fixed rate"], ["source_timestamp", "Source timestamps"]], "span-4", editable)}
          ${fieldNumber("Frequency (Hz)", "clock.frequency_hz", clock.frequency_hz ?? 1, "span-4", editable, "number", "Used directly in fixed-rate mode and as fallback timing.", 0.001)}
          ${fieldNumber("Speed multiplier", "clock.speed", clock.speed ?? 1, "span-4", editable, "number", "1 = real source timing, 10 = 10× faster.", 0.001)}
          ${fieldNumber("Maximum delay (s)", "clock.max_delay_seconds", clock.max_delay_seconds ?? 60, "span-4", editable, "number")}
          ${fieldSelect("Replay policy", "loop_mode", definition.loop_mode || "loop_forever", [["loop_forever", "Loop forever"], ["once", "Run once"], ["hold_last", "Hold last frame"], ["ping_pong", "Ping-pong"]], "span-4", editable)}
          <div class="field span-4"><span class="field-label">Autostart</span><div class="checkbox-line"><input id="autostart" type="checkbox" data-bind="autostart" ${checked(definition.autostart)} ${disabled(!editable)} /><label for="autostart">Start after runtime loads this definition</label></div></div>
        </div></div>
      </section>
      <div class="notice info"><strong>Independent clock.</strong> Changing this simulation never changes the cursor or timing of another active simulation.</div>
    </div>`;
}

function renderMapping({ definition, editable, mappingView }) {
  const all = definition.mappings || [];
  const query = (mappingView?.search || "").trim().toLowerCase();
  const indexed = all.map((mapping, index) => ({ mapping, index }));
  const filtered = query ? indexed.filter(({ mapping }) => [mapping.source, mapping.target, mapping.node_id, mapping.data_type, mapping.unit].some((value) => String(value || "").toLowerCase().includes(query))) : indexed;
  const pageSize = 100;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.max(0, Math.min(mappingView?.page || 0, pages - 1));
  const visible = filtered.slice(page * pageSize, page * pageSize + pageSize);
  return `
    <div class="section-stack">
      ${!editable ? lockedNotice() : ""}
      <section class="panel">
        <div class="panel-head"><div><h3>Canonical signal mapping</h3><p>Transform once before fan-out. OPC UA NodeIds and all other targets consume the same canonical signals.</p></div><div class="panel-actions"><button class="button secondary" data-action="preview-source">Refresh source</button><button class="button primary" data-action="seed-mappings">Load source schema</button></div></div>
        <div class="panel-body">
          <div class="checkbox-line" style="margin-bottom:12px"><input id="dropUnmapped" type="checkbox" data-bind="drop_unmapped_signals" ${checked(definition.drop_unmapped_signals)} ${disabled(!editable)} /><label for="dropUnmapped">Drop source signals that do not have an enabled mapping</label></div>
          <div class="table-shell">
            <div class="table-toolbar">
              <label class="search-field"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg><input id="mappingSearch" value="${attr(mappingView?.search || "")}" placeholder="Search signals" /></label>
              <button class="button compact secondary" data-action="mapping-enable-all" ${disabled(!editable)}>Enable shown</button>
              <button class="button compact secondary" data-action="mapping-disable-all" ${disabled(!editable)}>Disable shown</button>
              <span class="table-toolbar-spacer"></span><span class="muted">${filtered.length} of ${all.length} signals</span>
            </div>
            <div class="table-scroll">
              <table class="data-table"><thead><tr>
                <th style="width:54px">On</th><th style="width:18%">Source</th><th style="width:18%">Output</th><th style="width:22%">Node ID</th><th style="width:100px">Type</th><th style="width:95px">Unit</th><th style="width:85px">Scale</th><th style="width:85px">Offset</th>
              </tr></thead><tbody>
                ${visible.map(({ mapping, index }) => mappingRow(mapping, index, editable)).join("") || `<tr><td colspan="8" class="muted">No mapping rows. Preview the source and load its schema.</td></tr>`}
              </tbody></table>
            </div>
            <div class="table-footer"><span>Rows ${visible.length ? page * pageSize + 1 : 0}–${page * pageSize + visible.length}</span><div class="pager"><button data-action="mapping-prev" ${disabled(page === 0)}>‹</button><span>${page + 1} / ${pages}</span><button data-action="mapping-next" ${disabled(page >= pages - 1)}>›</button></div></div>
          </div>
        </div>
      </section>
    </div>`;
}

function mappingRow(mapping, index, editable) {
  return `<tr data-mapping-row="${index}">
    <td><input type="checkbox" data-mapping-index="${index}" data-mapping-field="enabled" ${checked(mapping.enabled)} ${disabled(!editable)} /></td>
    <td class="mono">${esc(mapping.source)}</td>
    <td><input data-mapping-index="${index}" data-mapping-field="target" value="${attr(mapping.target ?? mapping.source)}" ${disabled(!editable)} /></td>
    <td><input class="mono" data-mapping-index="${index}" data-mapping-field="node_id" value="${attr(mapping.node_id ?? mapping.target ?? mapping.source)}" ${disabled(!editable)} /></td>
    <td><select data-mapping-index="${index}" data-mapping-field="data_type" ${disabled(!editable)}>${["Double", "Int64", "Boolean", "String"].map((type) => `<option ${selected(mapping.data_type || "String", type)}>${type}</option>`).join("")}</select></td>
    <td><input data-mapping-index="${index}" data-mapping-field="unit" value="${attr(mapping.unit || "")}" ${disabled(!editable)} /></td>
    <td><input type="number" step="any" data-mapping-index="${index}" data-mapping-field="scale" value="${attr(mapping.scale ?? 1)}" ${disabled(!editable)} /></td>
    <td><input type="number" step="any" data-mapping-index="${index}" data-mapping-field="offset" value="${attr(mapping.offset ?? 0)}" ${disabled(!editable)} /></td>
  </tr>`;
}

function renderTargets({ definition, status, editable }) {
  const targets = definition.targets || [];
  return `
    <div class="section-stack">
      ${!editable ? lockedNotice() : ""}
      <section class="panel">
        <div class="panel-head">
          <div><h3>Targets</h3><p>OPC UA is the primary end-to-end interface; additional targets receive the same canonical frame independently.</p></div>
          <div class="panel-actions">
            <select id="addTargetKind" ${disabled(!editable)}><option value="mqtt">MQTT</option><option value="http">HTTP</option><option value="sql_server">SQL Server</option><option value="odata">OData</option><option value="opcua">Another OPC UA</option></select>
            <button class="button secondary" data-action="add-target" ${disabled(!editable)}>Add target</button>
          </div>
        </div>
        <div class="panel-body"><div class="target-list">
          ${targets.map((target, index) => renderTarget(target, index, statusTarget(status, target.target_id), editable)).join("")}
        </div></div>
      </section>
    </div>`;
}

function renderTarget(target, index, runtime, editable) {
  const primary = target.kind === "opcua";
  const endpoint = runtime?.endpoint || endpointFor(target);
  return `<article class="target-card ${primary ? "primary-target" : ""}">
    <header class="target-card-head">
      <span class="target-kind-mark ${primary ? "opcua" : ""}">${primary ? "UA" : esc(target.kind.slice(0, 3).toUpperCase())}</span>
      <div class="target-title"><strong>${esc(targetLabel(target.kind))}</strong><span>${esc(target.target_id)}</span></div>
      <span class="target-state ${stateClass(runtime?.state)}">${esc(runtime?.state ? humanState(runtime.state) : "Configured")}</span>
      <button class="button compact danger" data-action="remove-target" data-target-index="${index}" ${disabled(!editable)}>Remove</button>
    </header>
    <div class="target-card-body">
      ${target.kind === "opcua" ? renderOpcUaTarget(target, index, runtime, editable) : renderSecondaryTarget(target, index, runtime, editable)}
      ${endpoint ? `<div class="endpoint-preview" style="margin-top:12px"><code>${esc(endpoint)}</code><button data-action="copy-endpoint" data-copy="${attr(endpoint)}">Copy</button></div>` : ""}
    </div>
  </article>`;
}

function renderOpcUaTarget(target, index, runtime, editable) {
  const path = `targets.${index}`;
  const config = target.config || {};
  return `<div class="form-grid">
    ${fieldSelect("Hosting", `${path}.hosting_mode`, target.hosting_mode || "shared", [["shared", "Shared listener"], ["dedicated", "Dedicated endpoint"]], "span-3", editable)}
    ${fieldText("Bind host", `${path}.config.bind_host`, config.bind_host || "0.0.0.0", "span-3", editable, "Actual listener bind address.")}
    ${fieldText("Advertised host", `${path}.config.advertised_host`, config.advertised_host || "localhost", "span-3", editable, "Host clients should connect to.")}
    ${fieldNumber("Port", `${path}.config.port`, config.port || 4840, "span-3", editable, "integer", null, 1, 65535)}
    ${fieldText("Path", `${path}.config.path`, config.path || "simulator", "span-4", editable)}
    ${fieldText("Namespace URI", `${path}.config.namespace_uri`, config.namespace_uri || "http://local/unified-simulator", "span-4", editable)}
    ${fieldText("Root folder", `${path}.config.root_folder`, config.root_folder || "Simulations", "span-4", editable)}
    <div class="form-divider"></div><div class="subsection-title">Delivery policy</div>
    ${commonTargetFields(target, index, editable)}
    ${runtime ? `<div class="form-divider"></div><div class="subsection-title">Live state</div>${readOnlyMetric("Published", runtime.published_frames || 0)}${readOnlyMetric("Queue", runtime.queue_depth || 0)}${readOnlyMetric("Dropped", runtime.dropped_frames || 0)}${readOnlyMetric("Tags", runtime.details?.tag_count || 0)}` : ""}
  </div>`;
}

function renderSecondaryTarget(target, index, runtime, editable) {
  const path = `targets.${index}`;
  const config = target.config || {};
  let specific = "";
  if (target.kind === "mqtt") specific = `${fieldText("Host", `${path}.config.host`, config.host || "localhost", "span-4", editable)}${fieldNumber("Port", `${path}.config.port`, config.port || 1883, "span-2", editable, "integer")}${fieldText("Topic prefix", `${path}.config.topic_prefix`, config.topic_prefix || "", "span-6", editable)}`;
  if (target.kind === "sql_server") specific = `${fieldText("Server", `${path}.config.server`, config.server || "localhost", "span-4", editable)}${fieldNumber("Port", `${path}.config.port`, config.port || 1433, "span-2", editable, "integer")}${fieldText("Database", `${path}.config.database`, config.database || "Simulator", "span-3", editable)}${fieldText("Table", `${path}.config.table`, config.table || "dbo.tag_snapshots", "span-3", editable)}${fieldSelect("Authentication", `${path}.config.auth`, config.auth || "windows", [["windows", "Windows"], ["sql", "SQL login"]], "span-3", editable)}${fieldNumber("Batch size", `${path}.config.batch_size`, config.batch_size || 100, "span-3", editable, "integer")}${fieldText("Username", `${path}.config.username`, config.username || "", "span-3", editable)}${fieldText("Password", `${path}.config.password`, config.password || "", "span-3", editable)}`;
  if (target.kind === "odata") specific = `${fieldText("Entity set", `${path}.config.entity_set`, config.entity_set || "SimulationValues", "span-6", editable)}${fieldNumber("Retained rows", `${path}.config.max_rows`, config.max_rows || 10000, "span-3", editable, "integer")}`;
  if (target.kind === "http") specific = `<div class="notice info" style="grid-column:1/-1">HTTP uses the shared Industrial FastAPI host and exposes snapshot, NDJSON, SSE and WebSocket endpoints for this simulation.</div>`;
  return `<div class="form-grid">${specific}<div class="form-divider"></div><div class="subsection-title">Delivery policy</div>${commonTargetFields(target, index, editable)}${runtime ? `<div class="form-divider"></div><div class="subsection-title">Live state</div>${readOnlyMetric("Published", runtime.published_frames || 0)}${readOnlyMetric("Queue", runtime.queue_depth || 0)}${readOnlyMetric("Dropped", runtime.dropped_frames || 0)}` : ""}</div>`;
}

function commonTargetFields(target, index, editable) {
  const path = `targets.${index}`;
  return `
    ${fieldSelect("Failure policy", `${path}.failure_policy`, target.failure_policy || "retry", [["continue", "Continue"], ["retry", "Retry"], ["stop_simulation", "Stop simulation"]], "span-3", editable)}
    ${fieldNumber("Queue size", `${path}.queue_size`, target.queue_size || 256, "span-3", editable, "integer")}
    ${fieldSelect("Overflow", `${path}.overflow_policy`, target.overflow_policy || "drop_oldest", [["drop_oldest", "Drop oldest"], ["drop_newest", "Drop newest"], ["block", "Block"]], "span-3", editable)}
    ${fieldNumber("Retry delay (s)", `${path}.retry_seconds`, target.retry_seconds || 1, "span-3", editable, "number")}`;
}

export function renderInterfaces(status) {
  const shared = Object.entries(status?.shared_opcua_hosts || {});
  const dedicated = Object.entries(status?.dedicated_opcua_hosts || {});
  const cards = [
    ...shared.map(([key, host]) => hostCard("Shared OPC UA", key, host)),
    ...dedicated.map(([key, host]) => hostCard("Dedicated OPC UA", key, host)),
  ];
  if (!cards.length) return `<div class="notice info">No OPC UA hosts are active. Hosts are created on demand when a simulation starts.</div>`;
  return `<div class="host-grid">${cards.join("")}</div>`;
}

function hostCard(type, key, host) {
  return `<article class="host-card"><h3>${esc(type)}</h3><p class="mono">${esc(host.endpoint || key)}</p><dl class="key-value"><dt>Running</dt><dd>${host.running ? "Yes" : "No"}</dd><dt>Simulations</dt><dd>${host.simulation_count ?? (host.simulation_id ? 1 : "—")}</dd><dt>Targets</dt><dd>${host.target_count ?? 1}</dd><dt>Tags</dt><dd>${host.tag_count ?? "—"}</dd><dt>Namespace</dt><dd>${esc(host.namespace_uri || "—")}</dd><dt>Root</dt><dd>${esc(host.root_folder || "—")}</dd></dl></article>`;
}

export function renderSources(resources) {
  const files = resources.files || [];
  const datasets = resources.datasets || [];
  const generators = resources.generators || [];
  return `<div class="section-stack">
    <section><div class="panel-head" style="border:1px solid var(--line);border-radius:7px 7px 0 0"><div><h3>Files</h3><p>${files.length} available CSV/XLSX files</p></div></div><div class="source-grid" style="border:1px solid var(--line);border-top:0;padding:10px">${files.slice(0, 30).map((file) => `<article class="source-card"><h3>${esc(file.filename)}</h3><p>${esc(file.source)} · ${file.row_count} rows · ${file.column_count} columns</p></article>`).join("") || `<div class="muted">No files found.</div>`}</div></section>
    <section><div class="panel-head" style="border:1px solid var(--line);border-radius:7px 7px 0 0"><div><h3>Registered datasets</h3><p>${datasets.length} available datasets</p></div></div><div class="source-grid" style="border:1px solid var(--line);border-top:0;padding:10px">${datasets.slice(0, 30).map((dataset) => `<article class="source-card"><h3>${esc(dataset.name || dataset.dataset_id)}</h3><p>${esc(dataset.storage_format || "dataset")} · ${esc(dataset.dataset_id)}</p></article>`).join("") || `<div class="muted">No datasets found.</div>`}</div></section>
    <section><div class="panel-head" style="border:1px solid var(--line);border-radius:7px 7px 0 0"><div><h3>Domain generators</h3><p>${generators.length} industrial generators</p></div></div><div class="source-grid" style="border:1px solid var(--line);border-top:0;padding:10px">${generators.map((generator) => `<article class="source-card"><h3>${esc(generator.display_name)}</h3><p>${esc(generator.description || generator.domain_id)}</p></article>`).join("") || `<div class="muted">No generators found.</div>`}</div></section>
  </div>`;
}

function renderTargetHealth(definition, status) {
  const targets = (definition.targets || []).filter((target) => target.enabled);
  if (!targets.length) return `<div class="notice warning">No enabled targets.</div>`;
  return `<div class="table-shell"><table class="data-table target-status-table"><thead><tr><th>Target</th><th>State</th><th>Endpoint</th><th>Published</th><th>Queue</th><th>Dropped</th></tr></thead><tbody>${targets.map((target) => {
    const runtime = statusTarget(status, target.target_id);
    return `<tr><td><strong>${esc(targetLabel(target.kind))}</strong><br><span class="muted mono">${esc(target.target_id)}</span></td><td><span class="target-state ${stateClass(runtime?.state)}">${esc(runtime?.state ? humanState(runtime.state) : "Configured")}</span></td><td class="endpoint-cell">${esc(runtime?.endpoint || endpointFor(target) || "—")}</td><td>${runtime?.published_frames || 0}</td><td>${runtime?.queue_depth || 0}</td><td>${runtime?.dropped_frames || 0}</td></tr>`;
  }).join("")}</tbody></table></div>`;
}

function renderValueTable(values) {
  return `<div class="table-shell"><div class="table-scroll"><table class="data-table value-table"><thead><tr><th>Signal</th><th>Value</th><th>Type</th><th>Unit</th><th>Quality</th></tr></thead><tbody>${values.map(([name, signal]) => `<tr><td>${esc(name)}</td><td>${esc(signal.value)}</td><td>${esc(signal.data_type)}</td><td>${esc(signal.unit || "—")}</td><td>${esc(signal.quality || "GOOD")}</td></tr>`).join("")}</tbody></table></div></div>`;
}

function metric(label, value, detail) {
  return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(detail || "")}</small></div>`;
}

function readOnlyMetric(label, value) {
  return `<div class="field span-3"><span class="field-label">${esc(label)}</span><input value="${attr(value)}" disabled /></div>`;
}

function readOnlyField(label, value, span = "span-6", help = "") {
  return `<div class="field ${span}"><label>${esc(label)}</label><input value="${attr(value)}" disabled />${help ? `<span class="help">${esc(help)}</span>` : ""}</div>`;
}

function lockedNotice() {
  return `<div class="notice warning"><strong>Stop before editing.</strong> Runtime definitions are immutable while a simulation is running or paused. Live controls remain available from the header.</div>`;
}

function fieldText(label, path, value, span = "span-6", editable = true, help = "", role = "") {
  return `<div class="field ${span}"><label>${esc(label)}</label><input data-bind="${attr(path)}" ${role ? `data-role="${attr(role)}"` : ""} value="${attr(value)}" ${disabled(!editable)} />${help ? `<span class="help">${esc(help)}</span>` : ""}</div>`;
}

function fieldNumber(label, path, value, span = "span-3", editable = true, valueType = "number", help = "", min = null, max = null, step = null) {
  const stepAttr = step != null ? `step="${attr(step)}"` : `step="any"`;
  return `<div class="field ${span}"><label>${esc(label)}</label><input type="number" data-bind="${attr(path)}" data-value-type="${valueType}" value="${attr(value)}" ${min != null ? `min="${attr(min)}"` : ""} ${max != null ? `max="${attr(max)}"` : ""} ${stepAttr} ${disabled(!editable)} />${help ? `<span class="help">${esc(help)}</span>` : ""}</div>`;
}

function fieldSelect(label, path, value, options, span = "span-4", editable = true, role = null, help = "") {
  return `<div class="field ${span}"><label>${esc(label)}</label><select data-bind="${attr(path)}" ${role ? `data-role="${attr(role)}"` : ""} ${disabled(!editable)}>${options.map(([optionValue, optionLabel]) => `<option value="${attr(optionValue)}" ${selected(value, optionValue)}>${esc(optionLabel)}</option>`).join("")}</select>${help ? `<span class="help">${esc(help)}</span>` : ""}</div>`;
}
