import { simulatorApi } from "./api.js";
import {
  addTarget,
  canEdit,
  clone,
  duplicateSimulation,
  newSimulation,
  normalizeSource,
  parseInputValue,
  removeTarget,
  setPath,
  sourceSchemaToMappings,
} from "./model.js";
import {
  renderDetailHeader,
  renderInterfaces,
  renderRailSummary,
  renderSimulationList,
  renderSources,
  renderTab,
  renderTabs,
} from "./render.js";

const launcher = window.SIMULATOR_LAUNCHER_CONFIG || {};
const els = Object.fromEntries([
  "simulationCount", "railSummary", "simulationSearch", "simulationStateFilter", "simulationList",
  "emptyState", "simulationDetail", "detailHeader", "detailTabs", "detailContent", "interfacesContent",
  "sourcesContent", "industrialState", "opcHostState", "toastStack", "busyOverlay",
].map((id) => [id, document.getElementById(id)]));

const state = {
  simulations: [],
  selectedId: null,
  draft: null,
  baseline: null,
  draftStatus: null,
  isNew: false,
  tab: "overview",
  navigation: "simulations",
  search: "",
  stateFilter: "all",
  sourcePreview: null,
  snapshot: null,
  interfaces: {},
  resources: { files: [], datasets: [], generators: [] },
  generatorSpecs: new Map(),
  mappingView: { search: "", page: 0 },
  busyCount: 0,
};

function dirty() {
  return !!state.draft
    && JSON.stringify(prepareDefinition(state.draft)) !== JSON.stringify(prepareDefinition(state.baseline));
}

function selectedRecord() {
  return state.simulations.find((item) => item.definition.simulation_id === state.selectedId) || null;
}

function selectedStatus() {
  return state.isNew ? state.draftStatus : selectedRecord()?.status || state.draftStatus || { state: "created" };
}

function editable() {
  return state.isNew || canEdit(selectedStatus());
}

function cleanDefinition(definition) {
  if (!definition) return null;
  const output = clone(definition);
  if (output.source?.config) delete output.source.config.context_fields_text;
  return output;
}

function prepareDefinition(definition) {
  const output = cleanDefinition(definition);
  if (!definition || !output) return output;
  const contextText = definition.source?.config?.context_fields_text;
  if (contextText !== undefined) {
    output.source.config.context_fields = String(contextText)
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return output;
}

function fakeStatus(definition, stateName = "created") {
  return {
    simulation_id: definition.simulation_id,
    name: definition.name,
    state: stateName,
    emitted_count: 0,
    source_position: 0,
    source_count: null,
    targets: [],
  };
}

function withBusy(action) {
  state.busyCount += 1;
  renderBusy();
  return Promise.resolve()
    .then(action)
    .finally(() => {
      state.busyCount = Math.max(0, state.busyCount - 1);
      renderBusy();
    });
}

function renderBusy() {
  els.busyOverlay.hidden = state.busyCount === 0;
}

function toast(message, type = "info", title = "Simulator") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.innerHTML = `<strong>${escapeHtml(title)}</strong>${escapeHtml(message)}`;
  els.toastStack.append(node);
  setTimeout(() => node.remove(), 5000);
}

function escapeHtml(value) {
  const span = document.createElement("span");
  span.textContent = String(value ?? "");
  return span.innerHTML;
}

async function bootstrap() {
  bindEvents();
  await withBusy(async () => {
    await Promise.all([loadResources(), loadRuntime()]);
    await loadSimulations();
  });
  render();
  setInterval(refreshLive, 1500);
}

async function loadResources() {
  const [files, datasets, generators] = await Promise.all([
    simulatorApi.files().catch(() => ({ files: [] })),
    simulatorApi.datasets().catch(() => ({ datasets: [] })),
    simulatorApi.generators().catch(() => ({ generators: [] })),
  ]);
  state.resources.files = files.files || [];
  state.resources.datasets = datasets.datasets || [];
  state.resources.generators = generators.generators || [];
}

async function loadRuntime() {
  const [health, interfaces] = await Promise.all([
    simulatorApi.health().catch(() => null),
    simulatorApi.interfaces().catch(() => ({})),
  ]);
  state.interfaces = interfaces || {};
  renderServiceStatus(health);
}

async function loadSimulations(preferredId = state.selectedId) {
  state.simulations = await simulatorApi.listSimulations();
  if (state.isNew) return;
  const nextId = state.simulations.some((item) => item.definition.simulation_id === preferredId)
    ? preferredId
    : state.simulations[0]?.definition.simulation_id || null;
  if (nextId) selectSimulation(nextId, false);
  else clearSelection();
}

function selectSimulation(id, renderNow = true) {
  const record = state.simulations.find((item) => item.definition.simulation_id === id);
  if (!record) return;
  state.selectedId = id;
  state.draft = clone(record.definition);
  state.baseline = clone(record.definition);
  state.draftStatus = record.status;
  state.isNew = false;
  state.sourcePreview = null;
  state.snapshot = null;
  state.mappingView.page = 0;
  ensureGeneratorSpec().finally(() => render());
  loadSnapshot(id).finally(() => render());
  if (renderNow) render();
}

function clearSelection() {
  state.selectedId = null;
  state.draft = null;
  state.baseline = null;
  state.draftStatus = null;
  state.isNew = false;
  state.sourcePreview = null;
  state.snapshot = null;
}

function createDraft() {
  const definition = newSimulation(Number(launcher.opcua_port || 4840));
  state.selectedId = definition.simulation_id;
  state.draft = definition;
  state.baseline = null;
  state.draftStatus = fakeStatus(definition);
  state.isNew = true;
  state.sourcePreview = null;
  state.snapshot = null;
  state.tab = "source";
  state.mappingView = { search: "", page: 0 };
  render();
}

async function ensureGeneratorSpec() {
  const domainId = state.draft?.source?.kind === "generator" ? state.draft.source.config?.domain_id : null;
  if (!domainId || state.generatorSpecs.has(domainId)) return;
  const spec = await simulatorApi.generatorSpec(domainId);
  state.generatorSpecs.set(domainId, spec);
  if (!state.draft.source.config.scenario && spec.scenarios?.length) state.draft.source.config.scenario = spec.scenarios[0].id;
  state.draft.source.config.parameters ||= {};
  for (const parameter of spec.parameters || []) {
    if (state.draft.source.config.parameters[parameter.name] == null && parameter.default != null) {
      state.draft.source.config.parameters[parameter.name] = parameter.default;
    }
  }
}

async function loadSnapshot(id = state.selectedId) {
  if (!id || state.isNew) return;
  state.snapshot = await simulatorApi.snapshot(id).catch(() => null);
}

async function previewSource() {
  if (!state.draft) return;
  state.sourcePreview = await simulatorApi.previewSimulation(prepareDefinition(state.draft));
  toast(`Loaded ${state.sourcePreview.source_schema?.length || 0} source signals.`, "success", "Source preview");
  render();
}

function seedMappings() {
  if (!state.sourcePreview?.source_schema) {
    toast("Preview the source first.", "error", "Signals & mapping");
    return;
  }
  state.draft.mappings = sourceSchemaToMappings(state.sourcePreview.source_schema, state.draft.mappings || []);
  state.mappingView.page = 0;
  state.tab = "mapping";
  render();
  toast(`${state.draft.mappings.length} signals loaded into the canonical mapping.`, "success", "Signals & mapping");
}

async function saveDraft() {
  if (!state.draft) return null;
  const definition = prepareDefinition(state.draft);
  if (state.isNew) {
    const status = await simulatorApi.createSimulation(definition);
    state.isNew = false;
    state.selectedId = definition.simulation_id;
    await loadSimulations(definition.simulation_id);
    toast("Simulation created.", "success");
    return status;
  }
  const status = await simulatorApi.replaceSimulation(definition.simulation_id, definition);
  await loadSimulations(definition.simulation_id);
  toast("Simulation definition saved.", "success");
  return status;
}

async function lifecycle(action) {
  if (!state.draft) return;
  if (["start", "restart"].includes(action) && (state.isNew || dirty())) await saveDraft();
  const id = state.selectedId;
  if (!id) return;
  const actions = {
    start: simulatorApi.startSimulation,
    pause: simulatorApi.pauseSimulation,
    resume: simulatorApi.resumeSimulation,
    stop: simulatorApi.stopSimulation,
    restart: simulatorApi.restartSimulation,
  };
  const result = await actions[action](id);
  state.draftStatus = result;
  await refreshSelected(id);
  toast(`${action[0].toUpperCase()}${action.slice(1)} completed.`, "success");
}

async function moveCursor(action) {
  const id = state.selectedId;
  if (!id || state.isNew) return;
  let result;
  if (action === "reset-cursor") {
    result = await simulatorApi.resetCursor(id);
  } else {
    const raw = document.getElementById("seekPosition")?.value;
    const position = Number.parseInt(raw, 10);
    if (!Number.isInteger(position) || position < 0) throw new Error("Seek position must be a non-negative integer.");
    result = await simulatorApi.seekSimulation(id, position);
  }
  state.draftStatus = result;
  await refreshSelected(id);
  toast(action === "reset-cursor" ? "Cursor reset to the configured start." : "Cursor position updated.", "success", "Simulation cursor");
}

async function refreshSelected(id) {
  await Promise.all([loadSimulations(id), loadRuntime()]);
  await loadSnapshot(id);
}

async function duplicateCurrent() {
  if (!state.draft) return;
  const copy = duplicateSimulation(state.draft);
  state.selectedId = copy.simulation_id;
  state.draft = copy;
  state.baseline = null;
  state.draftStatus = fakeStatus(copy);
  state.isNew = true;
  state.sourcePreview = null;
  state.snapshot = null;
  state.tab = "overview";
  render();
  toast("Review the copied definition, then save or start it.", "info", "Duplicate simulation");
}

async function deleteCurrent() {
  if (state.isNew) {
    clearSelection();
    render();
    return;
  }
  if (!state.selectedId) return;
  if (!confirm(`Delete simulation ${state.draft?.name || state.selectedId}?`)) return;
  await simulatorApi.deleteSimulation(state.selectedId);
  const deleted = state.selectedId;
  clearSelection();
  await loadSimulations();
  toast(`Deleted ${deleted}.`, "success");
  render();
}

function bindEvents() {
  document.addEventListener("click", handleClick);
  document.addEventListener("change", handleInput);
  document.addEventListener("input", handleInput);
  els.simulationSearch.addEventListener("input", () => { state.search = els.simulationSearch.value; renderRail(); });
  els.simulationStateFilter.addEventListener("change", () => { state.stateFilter = els.simulationStateFilter.value; renderRail(); });
}

function handleClick(event) {
  const selection = event.target.closest("[data-select-simulation]");
  if (selection) {
    if (dirty() && !confirm("Discard unsaved changes and switch simulations?")) return;
    selectSimulation(selection.dataset.selectSimulation);
    return;
  }
  const tab = event.target.closest("[data-tab]");
  if (tab) { state.tab = tab.dataset.tab; renderDetail(); return; }
  const nav = event.target.closest("[data-nav]");
  if (nav) { setNavigation(nav.dataset.nav); return; }
  const actionNode = event.target.closest("[data-action]");
  if (!actionNode) return;
  const action = actionNode.dataset.action;
  withBusy(() => runAction(action, actionNode)).catch((error) => toast(error.message, "error"));
}

async function runAction(action, node) {
  if (action === "refresh") { await Promise.all([loadRuntime(), loadSimulations()]); render(); return; }
  if (action === "refresh-sources") { await loadResources(); renderSourcesView(); return; }
  if (action === "new-simulation") { if (!dirty() || confirm("Discard unsaved changes?")) createDraft(); return; }
  if (action === "save") { await saveDraft(); render(); return; }
  if (["start", "pause", "resume", "stop", "restart"].includes(action)) { await lifecycle(action); render(); return; }
  if (["reset-cursor", "seek-cursor"].includes(action)) { await moveCursor(action); render(); return; }
  if (action === "duplicate") { await duplicateCurrent(); return; }
  if (action === "delete") { await deleteCurrent(); return; }
  if (action === "preview-source") { await previewSource(); return; }
  if (action === "seed-mappings") { seedMappings(); return; }
  if (action === "add-target") { addSelectedTarget(); return; }
  if (action === "remove-target") { removeSelectedTarget(node); return; }
  if (action === "copy-endpoint") { await navigator.clipboard.writeText(node.dataset.copy || ""); toast("Endpoint copied.", "success"); return; }
  if (action === "mapping-enable-all") { setShownMappings(true); return; }
  if (action === "mapping-disable-all") { setShownMappings(false); return; }
  if (action === "mapping-prev") { state.mappingView.page = Math.max(0, state.mappingView.page - 1); renderDetail(); return; }
  if (action === "mapping-next") { state.mappingView.page += 1; renderDetail(); }
}

function handleInput(event) {
  const mappingIndex = event.target.dataset.mappingIndex;
  if (mappingIndex !== undefined && state.draft) {
    const mapping = state.draft.mappings?.[Number(mappingIndex)];
    if (!mapping) return;
    const field = event.target.dataset.mappingField;
    let value = event.target.type === "checkbox" ? event.target.checked : event.target.value;
    if (["scale", "offset"].includes(field)) value = Number(value || 0);
    if (["unit", "target", "node_id", "quality"].includes(field) && value === "") value = null;
    mapping[field] = value;
    renderHeaderOnly();
    return;
  }
  if (event.target.id === "mappingSearch") {
    state.mappingView.search = event.target.value;
    state.mappingView.page = 0;
    if (event.type === "input") renderDetail();
    return;
  }
  const path = event.target.dataset.bind;
  if (!path || !state.draft || !editable()) return;
  const role = event.target.dataset.role;
  const value = parseInputValue(event.target);
  if (role === "context-fields") {
    state.draft.source.config.context_fields_text = value;
    renderHeaderOnly();
    return;
  }
  if (path === "source.kind") {
    normalizeSource(state.draft, value);
    state.sourcePreview = null;
    state.mappingView.page = 0;
    ensureGeneratorSpec().finally(() => renderDetail());
    renderHeaderOnly();
    return;
  }
  setPath(state.draft, path, value);
  if (role === "generator-domain") {
    state.draft.source.config.scenario = "";
    state.draft.source.config.parameters = {};
    state.sourcePreview = null;
    ensureGeneratorSpec().finally(() => renderDetail());
  }
  renderHeaderOnly();
}

function addSelectedTarget() {
  if (!state.draft || !editable()) return;
  const kind = document.getElementById("addTargetKind")?.value || "mqtt";
  addTarget(state.draft, kind, Number(launcher.opcua_port || 4840));
  renderDetail();
}

function removeSelectedTarget(node) {
  if (!state.draft || !editable()) return;
  if ((state.draft.targets || []).length <= 1) {
    toast("A Simulation Definition requires at least one enabled target.", "error", "Targets");
    return;
  }
  const index = Number(node.dataset.targetIndex);
  const target = state.draft.targets?.[index];
  if (!target) return;
  removeTarget(state.draft, target.target_id);
  renderDetail();
}

function mappingMatches(mapping) {
  const query = state.mappingView.search.trim().toLowerCase();
  if (!query) return true;
  return [mapping.source, mapping.target, mapping.node_id, mapping.data_type, mapping.unit]
    .some((value) => String(value || "").toLowerCase().includes(query));
}

function setShownMappings(enabled) {
  if (!state.draft || !editable()) return;
  for (const mapping of state.draft.mappings || []) if (mappingMatches(mapping)) mapping.enabled = enabled;
  renderDetail();
}

function setNavigation(name) {
  state.navigation = name;
  for (const button of document.querySelectorAll("[data-nav]")) button.classList.toggle("active", button.dataset.nav === name);
  document.getElementById("simulationsWorkspace").hidden = name !== "simulations";
  document.getElementById("interfacesWorkspace").hidden = name !== "interfaces";
  document.getElementById("sourcesWorkspace").hidden = name !== "sources";
  if (name === "interfaces") renderInterfacesView();
  if (name === "sources") renderSourcesView();
}

function renderServiceStatus(health) {
  els.industrialState.classList.toggle("ok", !!health);
  els.industrialState.classList.toggle("bad", !health);
  els.industrialState.querySelector("strong").textContent = health ? "Connected" : "Unavailable";
  const sharedCount = Object.keys(state.interfaces?.shared_opcua_hosts || {}).length;
  const dedicatedCount = Object.keys(state.interfaces?.dedicated_opcua_hosts || {}).length;
  const total = sharedCount + dedicatedCount;
  els.opcHostState.classList.toggle("ok", total > 0);
  els.opcHostState.querySelector("strong").textContent = `${total} host${total === 1 ? "" : "s"}`;
}

function filteredSimulations() {
  const query = state.search.trim().toLowerCase();
  return state.simulations.filter((item) => {
    const status = item.status?.state || "created";
    const stateMatch = state.stateFilter === "all" || status === state.stateFilter;
    if (!stateMatch) return false;
    if (!query) return true;
    const text = [
      item.definition.name,
      item.definition.simulation_id,
      item.definition.source?.kind,
      item.definition.source?.config?.filename,
      item.definition.source?.config?.dataset_id,
      ...(item.definition.targets || []).map((target) => target.kind),
    ].join(" ").toLowerCase();
    return text.includes(query);
  });
}

function render() {
  renderRail();
  renderDetail();
  renderInterfacesView();
  renderSourcesView();
}

function renderRail() {
  els.simulationCount.textContent = `${state.simulations.length} configured`;
  els.railSummary.innerHTML = renderRailSummary(state.simulations);
  els.simulationList.innerHTML = renderSimulationList(filteredSimulations(), state.selectedId);
}

function renderHeaderOnly() {
  if (!state.draft) return;
  els.detailHeader.innerHTML = renderDetailHeader(state.draft, selectedStatus(), dirty(), state.isNew);
}

function renderDetail() {
  const hasDraft = !!state.draft;
  els.emptyState.hidden = hasDraft;
  els.simulationDetail.hidden = !hasDraft;
  if (!hasDraft) return;
  renderHeaderOnly();
  els.detailTabs.innerHTML = renderTabs(state.tab);
  const generatorId = state.draft.source?.kind === "generator" ? state.draft.source.config?.domain_id : null;
  els.detailContent.innerHTML = renderTab(state.tab, {
    definition: state.draft,
    status: selectedStatus(),
    editable: editable(),
    resources: state.resources,
    generatorSpec: generatorId ? state.generatorSpecs.get(generatorId) : null,
    preview: state.sourcePreview,
    snapshot: state.snapshot,
    mappingView: state.mappingView,
  });
}

function renderInterfacesView() {
  els.interfacesContent.innerHTML = renderInterfaces(state.interfaces);
}

function renderSourcesView() {
  els.sourcesContent.innerHTML = renderSources(state.resources);
}

async function refreshLive() {
  if (state.busyCount || document.hidden) return;
  try {
    const [interfaces, simulations] = await Promise.all([simulatorApi.interfaces(), simulatorApi.listSimulations()]);
    state.interfaces = interfaces || {};
    state.simulations = simulations;
    if (!state.isNew && state.selectedId) {
      const current = selectedRecord();
      if (current) {
        state.draftStatus = current.status;
        if (!dirty()) {
          state.draft = clone(current.definition);
          state.baseline = clone(current.definition);
        }
        await loadSnapshot(state.selectedId);
      }
    }
    renderServiceStatus({ status: "ok" });
    renderRail();
    if (state.navigation === "interfaces") renderInterfacesView();
    if (state.draft && ["overview", "timing", "targets"].includes(state.tab)) renderDetail();
  } catch {
    renderServiceStatus(null);
  }
}

bootstrap().catch((error) => {
  renderServiceStatus(null);
  toast(error.message, "error", "Startup failed");
});
