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

async function control(button) {
  const action = button.dataset.opcAction;
  const simulationId = button.dataset.simulationId;
  const invoke = actions[action];
  if (!invoke || !simulationId) return;

  button.disabled = true;
  try {
    const result = await invoke(simulationId);
    await refreshInterfaces();
    notify(`${simulationId}: ${result?.state || action}.`, "success");
  } catch (error) {
    button.disabled = false;
    notify(error.message || String(error), "error");
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-opc-action]");
  if (!button) return;
  control(button);
});
