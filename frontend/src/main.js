// =============================================================================
// main.js — The boot file. This is the first JS file that runs.
//
// Think of it as the conductor of an orchestra: it doesn't play music itself,
// but it calls each section (login, tabs, tasks, calendar, AI, music) to
// initialize in the right order, and coordinates what happens at startup.
//
// Execution flow:
//   1. Browser fires "DOMContentLoaded" event → our boot() runs
//   2. Each component's init() function wires up its event listeners
//   3. User enters name → login() calls the backend → app screen appears
//   4. loadUserData() fetches tasks and renders the first view
// =============================================================================

import api from "./utils/api.js";
import { setState } from "./utils/state.js";
import { initTasks, renderTasks } from "./components/tasks.js";
import { initCalendar, renderCal } from "./components/calendar.js";
import { initExplore } from "./components/explore.js";
import { initRecommendations, onRecommendationsEnter } from "./components/recommendations.js";

// ——— TAB SWITCHING ———
// The app has four tabs: Tasks, Calendar, Music, Coach.
// Only one panel is visible at a time. Clicking a tab:
//   1. Removes "active" from all tabs, then adds it to the clicked one
//   2. Removes "active" from all panels, then shows the matching one
//   3. If switching to the Music/Graph tab, triggers a graph reload
//      (because the graph data may have changed since last visit)
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;                           // e.g. "tasks", "calendar"
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${name}`).classList.add("active");
      // Special case: music tab needs a fresh graph load each time
      if (name === "recommendations") onRecommendationsEnter();
    });
  });
}

// ——— LOGIN ———
// The login screen is the first thing the user sees.
// Clicking "Enter" (button or keyboard) calls the backend /users/login endpoint.
// If the name is new → the backend auto-creates an account.
// If the name already exists → the backend returns that user's data.
// This means there's no separate "sign up" step — intentionally low friction.
//
// On success:
//   - Saves the user object to global state (so every other component can read it)
//   - Hides the login screen, reveals the app screen
//   - Fetches the user's tasks from the backend
function initLogin() {
  const form = document.getElementById("login-form");
  const input = document.getElementById("login-name");
  const btn = document.getElementById("btn-login");
  const err = document.getElementById("login-error");

  const doLogin = async () => {
    const name = input.value.trim();
    if (!name) { err.textContent = "Please enter your name."; return; }
    btn.disabled = true;                          // prevent double-clicking
    btn.textContent = "Entering...";
    err.textContent = "";
    try {
      // api.login sends POST /users/login → returns { id, name }
      const user = await api.login(name);
      setState({ user });                         // store user globally so all components know who is logged in
      document.getElementById("screen-login").style.display = "none";
      document.getElementById("screen-app").style.display = "flex";
      document.getElementById("user-name-label").textContent = user.name;
      await loadUserData(user.id);                // fetch tasks from the DB
    } catch (e) {
      // Network error or backend is down (Render free tier may be sleeping)
      err.textContent = "Could not connect to server. Is the backend running?";
      btn.disabled = false;
      btn.textContent = "Enter Un Poco Loco";
    }
  };

  btn.addEventListener("click", doLogin);
  // Allow pressing Enter in the name field — common UX expectation
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
}

// Fetch this user's tasks from the backend and push them into global state.
// After setState, renderTasks() and renderCal() re-render with the new data.
// Separation of concern: this function only loads data; rendering is handled
// by each component independently via the state subscription system.
async function loadUserData(userId) {
  try {
    const tasks = await api.getTasks(userId);
    setState({ tasks });    // triggers all components subscribed to state changes
    renderTasks();          // explicitly render in case subscription fired too early
    renderCal();
  } catch (e) {
    console.error("Failed to load tasks:", e);
  }
}

// ——— BOOT ———
// DOMContentLoaded fires when the HTML has been parsed and is safe to query.
// We wait for it because our init functions call getElementById() — which
// would return null if the HTML elements haven't been created yet.
//
// Think of this like "df.head()" in data science — you can only call it
// after your DataFrame exists. DOMContentLoaded is the moment the DataFrame
// (the DOM) is ready to be queried.
document.addEventListener("DOMContentLoaded", () => {
  initLogin();
  initTabs();
  initTasks();
  initCalendar();
  initExplore();
  initRecommendations();
});
