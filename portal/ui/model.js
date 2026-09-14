function slug(value) {
  return String(value || "simulation")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "simulation";
}

function shortId(prefix) {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  return `${prefix}_${Math.random().toString(16).slice(2, 14)}`;
}

export function defaultOpcUaTarget(opcuaPort = 4840) {
  return {
    target_id: "opcua",
    kind: "opcua",
    hosting_mode: "shared",
    enabled: true,
    failure_policy: "retry",
    queue_size: 256,
    overflow_policy: "drop_oldest",
    retry_seconds: 1,
    config: {
      bind_host: "0.0.0.0",
      advertised_host: "localhost",
      port: Number(opcuaPort || 4840),
      path: "simulator",
      namespace_uri: "http://local/unified-simulator",
      root_folder: "Simulations",
    },
  };
}

export function newSimulation(opcuaPort = 4840) {
  const id = shortId("sim");
  return {
    simulation_id: id,
    name: "New Simulation",
    source: { kind: "csv", config: { filename: "", csv_source: "uploaded", start_row: 0 } },
    mappings: [],
    drop_unmapped_signals: false,
    clock: { mode: "fixed_rate", frequency_hz: 1, speed: 1, max_delay_seconds: 60 },
    loop_mode: "loop_forever",
    targets: [defaultOpcUaTarget(opcuaPort)],
    world_id: null,
    autostart: false,
    metadata: {},
  };
}

export function duplicateSimulation(definition) {
  const copy = structuredClone(definition);
  copy.simulation_id = shortId("sim");
  copy.name = `${definition.name || "Simulation"} Copy`;
  copy.autostart = false;
  copy.targets = (copy.targets || []).map((target, index) => ({
    ...target,
    target_id: index === 0 && target.kind === "opcua" ? "opcua" : `${slug(target.kind)}-${index + 1}`,
  }));
  return copy;
}

export function clone(value) {
  return structuredClone(value);
}

export function sourceLabel(source) {
  const kind = source?.kind || "source";
  const config = source?.config || {};
  if (kind === "csv" || kind === "file") return config.filename || "File not selected";
  if (kind === "dataset") return config.dataset_id || "Dataset not selected";
  if (kind === "generator") return config.domain_id || "Generator not selected";
  if (kind === "sap_pp") return `SAP PP · ${config.entity || "entity"}`;
  if (kind === "lims_odbc") return `LIMS · ${config.entity || "entity"}`;
  if (kind === "source_simulator") return `${config.connector_id || "Source"} · ${config.entity || "entity"}`;
  if (kind === "inline" || kind === "rows") return `${(config.rows || []).length} inline rows`;
  return kind;
}

export function sourceKindLabel(kind) {
  return ({
    csv: "CSV / Excel",
    file: "CSV / Excel",
    dataset: "Registered dataset",
    generator: "Domain generator",
    sap_pp: "SAP PP source",
    lims_odbc: "LIMS source",
    source_simulator: "Source simulator",
    inline: "Inline rows",
  })[kind] || kind;
}

export function targetLabel(kind) {
  return ({
    opcua: "OPC UA",
    mqtt: "MQTT",
    http: "HTTP",
    http_stream: "HTTP",
    sql: "SQL Server",
    sql_server: "SQL Server",
    odata: "OData",
    memory: "Internal",
  })[kind] || kind;
}

export function findTarget(definition, targetId) {
  return (definition.targets || []).find((target) => target.target_id === targetId) || null;
}

export function opcUaTargets(definition) {
  return (definition.targets || []).filter((target) => target.kind === "opcua");
}

export function statusTarget(status, targetId) {
  return (status?.targets || []).find((target) => target.target_id === targetId) || null;
}

export function simulationProgress(status) {
  const count = Number(status?.source_count || 0);
  const position = Number(status?.source_position || 0);
  if (!count) return null;
  return Math.max(0, Math.min(100, (position / count) * 100));
}

export function canEdit(status) {
  return !["running", "paused", "starting"].includes(status?.state);
}

export function canStart(status) {
  return !["running", "paused", "starting"].includes(status?.state);
}

export function canPause(status) {
  return status?.state === "running" || status?.state === "degraded";
}

export function canResume(status) {
  return status?.state === "paused";
}

export function canStop(status) {
  return ["running", "paused", "degraded", "starting"].includes(status?.state);
}

export function canRestart(status) {
  return status?.state !== "starting";
}

export function canMoveCursor(status) {
  return status?.state === "paused";
}

export function getPath(object, path) {
  return path.split(".").reduce((current, key) => current?.[key], object);
}

export function setPath(object, path, value) {
  const parts = path.split(".");
  let current = object;
  for (let index = 0; index < parts.length - 1; index += 1) {
    const key = parts[index];
    if (current[key] == null || typeof current[key] !== "object") current[key] = {};
    current = current[key];
  }
  current[parts.at(-1)] = value;
}

export function parseInputValue(element) {
  if (element.type === "checkbox") return element.checked;
  if (element.dataset.valueType === "number") {
    if (element.value === "") return null;
    return Number(element.value);
  }
  if (element.dataset.valueType === "integer") {
    if (element.value === "") return null;
    return Number.parseInt(element.value, 10);
  }
  if (element.dataset.valueType === "nullable") return element.value === "" ? null : element.value;
  return element.value;
}

export function normalizeSource(definition, kind) {
  const previous = definition.source?.config || {};
  const defaults = {
    csv: { filename: "", csv_source: "uploaded", start_row: 0 },
    dataset: { dataset_id: "", start_row: 0 },
    generator: { domain_id: "", scenario: "", parameters: {} },
    sap_pp: { entity: "production_orders", seed_cycles: 1, cycle_parameters: {} },
    lims_odbc: { entity: "samples", seed_cycles: 1, cycle_parameters: {} },
  };
  definition.source = { kind, config: { ...(defaults[kind] || {}), ...previous } };
  for (const key of Object.keys(definition.source.config)) {
    if (!(key in (defaults[kind] || {})) && !["max_rows", "context_fields"].includes(key)) delete definition.source.config[key];
  }
}

export function ensurePrimaryOpcUa(definition, opcuaPort = 4840) {
  if (opcUaTargets(definition).length) return;
  definition.targets = [defaultOpcUaTarget(opcuaPort), ...(definition.targets || [])];
}

export function addTarget(definition, kind, opcuaPort = 4840) {
  const existing = new Set((definition.targets || []).map((target) => target.target_id));
  const base = kind === "sql_server" ? "sql" : kind;
  let suffix = 1;
  let targetId = base;
  while (existing.has(targetId)) targetId = `${base}-${++suffix}`;

  const common = {
    target_id: targetId,
    kind,
    hosting_mode: "shared",
    enabled: true,
    failure_policy: "retry",
    queue_size: 256,
    overflow_policy: "drop_oldest",
    retry_seconds: 1,
    config: {},
  };
  if (kind === "opcua") Object.assign(common, defaultOpcUaTarget(opcuaPort), { target_id: targetId });
  if (kind === "mqtt") common.config = { host: "localhost", port: 1883, topic_prefix: `simulator/${definition.simulation_id}` };
  if (kind === "http") common.config = {};
  if (kind === "sql_server") common.config = { server: "localhost", port: 1433, database: "Simulator", table: "dbo.tag_snapshots", auth: "windows", batch_size: 100 };
  if (kind === "odata") common.config = { entity_set: "SimulationValues", max_rows: 10000 };
  definition.targets ||= [];
  definition.targets.push(common);
  return targetId;
}

export function removeTarget(definition, targetId) {
  definition.targets = (definition.targets || []).filter((target) => target.target_id !== targetId);
}

export function sourceSchemaToMappings(sourceSchema, existingMappings = []) {
  const bySource = new Map(existingMappings.map((mapping) => [mapping.source, mapping]));
  return sourceSchema.map((signal) => {
    const existing = bySource.get(signal.name);
    return existing ? { ...existing } : {
      source: signal.name,
      target: signal.name,
      node_id: signal.node_id || signal.name,
      enabled: true,
      data_type: signal.data_type || "String",
      unit: signal.unit || null,
      quality: null,
      scale: 1,
      offset: 0,
      metadata: {},
    };
  });
}
