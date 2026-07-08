import api from "./utils/api.js";
import { setState } from "./utils/state.js";
import { initTasks, renderTasks } from "./components/tasks.js";
import { initCalendar, renderCal } from "./components/calendar.js";
import { initExplore } from "./components/explore.js";
import { initRecommendations, onRecommendationsEnter } from "./components/recommendations.js";

// ——— TAB SWITCHING ———
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${name}`).classList.add("active");
      if (name === "recommendations") onRecommendationsEnter();
    });
  });
}

// ——— LOGIN ———
function initLogin() {
  const form = document.getElementById("login-form");
  const input = document.getElementById("login-name");
  const btn = document.getElementById("btn-login");
  const err = document.getElementById("login-error");

  const doLogin = async () => {
    const name = input.value.trim();
    if (!name) { err.textContent = "Please enter your name."; return; }
    btn.disabled = true;
    btn.textContent = "Entering...";
    err.textContent = "";
    try {
      const user = await api.login(name);
      setState({ user });
      document.getElementById("screen-login").style.display = "none";
      document.getElementById("screen-app").style.display = "flex";
      document.getElementById("user-name-label").textContent = user.name;
      await loadUserData(user.id);
    } catch (e) {
      err.textContent = "Could not connect to server. Is the backend running?";
      btn.disabled = false;
      btn.textContent = "Enter FocusFlow";
    }
  };

  btn.addEventListener("click", doLogin);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
}

async function loadUserData(userId) {
  try {
    const tasks = await api.getTasks(userId);
    setState({ tasks });
    renderTasks();
    renderCal();
  } catch (e) {
    console.error("Failed to load tasks:", e);
  }
}

// ——— BOOT ———
document.addEventListener("DOMContentLoaded", () => {
  initLogin();
  initTabs();
  initTasks();
  initCalendar();
  initExplore();
  initRecommendations();
});
