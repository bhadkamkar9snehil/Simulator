import { simulatorApi } from "./api.js";
import { renderInterfaces } from "./opcua_hosts.js";

const actions = {
  pause: simulatorApi.pauseSimulation,
  resume: simulatorApi.resumeSimulation,
  restart: simulatorApi.restartSimulation,
  stop: simulatorApi.stopSimulation,
};

function notify(message, type = "info") {
  const stack = document.getElementById("toastStack");
  if (!stack) return;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  const title = document.createElement("strong");
  title.textContent = "OPC UA";
  node.append(title, document.createTextNode(message));
  stack.append(node);
  setTimeout(() => node.remove(), 4000);
}

async function refreshInterfaces() {
  const content = document.getElementById("interfacesContent");
  if (!content) return;
  const status = await simulatorApi.interfaces();
  content.innerHTML = renderInterfaces(status);
}

async function invokeAction(action, simulationId) {
  const invoke = actions[action];
  if (!invoke || !simulationId) return null;
  return invoke(simulationId);
}

async function control(button) {
  const action = button.dataset.opcAction;
  const simulationId = button.dataset.simulationId;
  if (!actions[action] || !simulationId) return;

  button.disabled = true;
  try {
    const result = await invokeAction(action, simulationId);
    await refreshInterfaces();
    notify(`${simulationId}: ${result?.state || action}.`, "success");
  } catch (error) {
    button.disabled = false;
    notify(error.message || String(error), "error");
  }
}

async function controlMany(button) {
  const action = button.dataset.opcBulkAction;
  const simulationIds = String(button.dataset.simulationIds || "").split(",").filter(Boolean);
  if (!actions[action] || !simulationIds.length) return;

  button.disabled = true;
  try {
    // Sequential execution is deliberate. Restarting every member concurrently
    // could temporarily remove the final group and bounce the shared listener.
    for (const simulationId of simulationIds) await invokeAction(action, simulationId);
    await refreshInterfaces();
    notify(`${action} applied to ${simulationIds.length} simulations.`, "success");
  } catch (error) {
    button.disabled = false;
    await refreshInterfaces().catch(() => {});
    notify(error.message || String(error), "error");
  }
}

document.addEventListener("click", (event) => {
  const bulk = event.target.closest("[data-opc-bulk-action]");
  if (bulk) {
    controlMany(bulk);
    return;
  }
  const button = event.target.closest("[data-opc-action]");
  if (button) control(button);
});
