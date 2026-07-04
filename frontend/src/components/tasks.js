import api from "../utils/api.js";
import { getState, setState, subscribe, isStale, todayStr, getFilteredTasks } from "../utils/state.js";

const CATS = {
  work: "tag-work", personal: "tag-personal",
  health: "tag-health", study: "tag-study", misc: "tag-misc",
};
const CAT_LABELS = {
  work: "💼 Work", personal: "🏠 Personal",
  health: "💚 Health", study: "📚 Study", misc: "📌 Misc",
};

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function catOptions(selected) {
  return Object.entries(CAT_LABELS)
    .map(([v, l]) => `<option value="${v}" ${selected === v ? "selected" : ""}>${l}</option>`)
    .join("");
}

function typeOptions(selected) {
  return `<option value="one-time" ${selected === "one-time" ? "selected" : ""}>✓ One-time</option>
          <option value="repetitive" ${selected === "repetitive" ? "selected" : ""}>🔁 Repetitive</option>`;
}

// Most recent calendar completion date for a task
function lastWorked(task) {
  if (!task.completions?.length) return null;
  return [...task.completions]
    .map(c => c.date)
    .sort()
    .at(-1);  // latest date string
}


export function initTasks() {
  subscribe(renderTasks);
  bindTaskInput();
}

function bindTaskInput() {
  document.getElementById("task-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addTask();
  });
  document.getElementById("btn-add-task").addEventListener("click", addTask);

  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setState({ currentFilter: btn.dataset.filter });
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}

async function addTask() {
  const input    = document.getElementById("task-input");
  const cat      = document.getElementById("task-cat").value;
  const taskType = document.getElementById("task-type").value;
  const name     = input.value.trim();
  if (!name) return;
  const { user } = getState();
  if (!user) return;

  input.value    = "";
  input.disabled = true;
  try {
    const task = await api.createTask(user.id, name, cat, taskType, todayStr());
    const { tasks } = getState();
    setState({ tasks: [task, ...tasks] });
  } catch (e) {
    console.error(e);
    alert("Could not save task. Is the backend running?");
  } finally {
    input.disabled = false;
    input.focus();
  }
}

export async function toggleTask(taskId) {
  const { user, tasks } = getState();
  try {
    const updated = await api.updateTask(user.id, taskId, {
      completed: !tasks.find((t) => t.id === taskId)?.completed,
    });
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    if (window._renderCal) window._renderCal();
  } catch (e) { console.error(e); }
}

export async function deleteTask(taskId) {
  const { user, tasks } = getState();
  try {
    await api.deleteTask(user.id, taskId);
    setState({ tasks: tasks.filter((t) => t.id !== taskId) });
    if (window._renderCal) window._renderCal();
  } catch (e) { console.error(e); }
}

export function startEdit(taskId) { setState({ editingTaskId: taskId }); }

export async function saveEdit(taskId) {
  const nameEl = document.getElementById(`edit-name-${taskId}`);
  const catEl  = document.getElementById(`edit-cat-${taskId}`);
  const typeEl = document.getElementById(`edit-type-${taskId}`);
  if (!nameEl) return;
  const name = nameEl.value.trim();
  if (!name) { setState({ editingTaskId: null }); return; }
  const { user, tasks } = getState();
  try {
    const updated = await api.updateTask(user.id, taskId, {
      name, category: catEl?.value, task_type: typeEl?.value,
    });
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)), editingTaskId: null });
  } catch (e) {
    console.error(e);
    setState({ editingTaskId: null });
  }
}

// ——— Row builders ———

function staleBadge(task) {
  if (!isStale(task)) return "";
  return task.task_type === "repetitive"
    ? `<span class="stale-badge">⚡ Going stale</span>`
    : `<span class="overdue-badge">⏳ Overdue</span>`;
}

function normalRow(t) {
  const staleRowClass = isStale(t) && t.task_type === "repetitive" ? "stale-rep" : "";
  const isRep = t.task_type === "repetitive";
  const lw    = lastWorked(t);

  const lwCell = lw
    ? `<span class="cell-date">${lw}</span>`
    : `<span class="cell-empty">—</span>`;

  const typeBadgeHtml = isRep
    ? `<span class="tag tag-repetitive">🔁 Repetitive</span>`
    : `<span class="tag tag-onetime">✓ One-time</span>`;

  return `<tr class="task-row ${staleRowClass} ${t.completed ? "row-done" : ""}" data-id="${t.id}">
    <td class="col-cb">
      <div class="task-check ${t.completed ? "done" : ""}" data-action="toggle" data-id="${t.id}"></div>
    </td>
    <td class="col-name">
      <span class="task-name">${escHtml(t.name)}</span>
      ${staleBadge(t)}
    </td>
    <td class="col-cat">
      <span class="tag ${CATS[t.category] || "tag-misc"}">${CAT_LABELS[t.category] || t.category}</span>
    </td>
    <td class="col-added"><span class="cell-date">${t.created_at}</span></td>
    <td class="col-last">${lwCell}</td>
    <td class="col-type">${typeBadgeHtml}</td>
    <td class="col-actions">
      <div class="task-actions">
        <button class="icon-btn" data-action="edit"   data-id="${t.id}" title="Edit">✎</button>
        <button class="icon-btn delete" data-action="delete" data-id="${t.id}" title="Delete">✕</button>
      </div>
    </td>
  </tr>`;
}

function editRow(t) {
  return `<tr class="task-row task-row-editing" data-id="${t.id}">
    <td class="col-cb">
      <div class="task-check ${t.completed ? "done" : ""}" data-action="toggle" data-id="${t.id}"></div>
    </td>
    <td colspan="7" class="col-edit-span">
      <div class="task-edit-form">
        <input
          class="edit-input"
          id="edit-name-${t.id}"
          value="${escHtml(t.name)}"
          placeholder="Task name…"
          data-action="edit-key"
          data-id="${t.id}"
          autofocus>
        <div class="edit-controls">
          <select class="edit-select" id="edit-cat-${t.id}">${catOptions(t.category)}</select>
          <select class="edit-select" id="edit-type-${t.id}">${typeOptions(t.task_type)}</select>
          <button class="btn btn-primary btn-sm" data-action="save-edit"   data-id="${t.id}">Save</button>
          <button class="btn btn-ghost   btn-sm" data-action="cancel-edit" data-id="${t.id}">Cancel</button>
        </div>
      </div>
    </td>
  </tr>`;
}

// ——— Main render ———

export function renderTasks() {
  const { tasks, editingTaskId } = getState();
  const list = document.getElementById("task-list");
  if (!list) return;

  // Progress bar
  const done = tasks.filter((t) => t.completed).length;
  const pct  = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  document.getElementById("prog-label").textContent = `${done} of ${tasks.length} tasks done`;
  document.getElementById("prog-pct").textContent   = `${pct}%`;
  document.getElementById("prog-fill").style.width  = `${pct}%`;

  const filtered = getFilteredTasks();
  if (!filtered.length) {
    list.innerHTML = `<div class="empty"><div class="empty-icon">🎯</div><p>No tasks here. Add one above!</p></div>`;
    return;
  }

  list.innerHTML = `
    <table class="task-table">
      <thead>
        <tr class="task-thead">
          <th class="col-cb"></th>
          <th class="col-name">Task</th>
          <th class="col-cat">Category</th>
          <th class="col-added">Date added</th>
          <th class="col-last">Last worked</th>
          <th class="col-type" style="text-align:right">Type</th>
          <th class="col-actions"></th>
        </tr>
      </thead>
      <tbody>
        ${filtered.map((t) => (editingTaskId === t.id ? editRow(t) : normalRow(t))).join("")}
      </tbody>
    </table>`;

  // ——— Delegated events ———
  list.onclick = async (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const { id, action } = el.dataset;
    if (action === "toggle")      await toggleTask(id);
    if (action === "edit")        startEdit(id);
    if (action === "delete")      await deleteTask(id);
    if (action === "save-edit")   await saveEdit(id);
    if (action === "cancel-edit") setState({ editingTaskId: null });
  };
  list.onkeydown = async (e) => {
    const el = e.target.closest("[data-action='edit-key']");
    if (!el) return;
    if (e.key === "Enter")  await saveEdit(el.dataset.id);
    if (e.key === "Escape") setState({ editingTaskId: null });
  };

  if (editingTaskId) {
    const el = document.getElementById(`edit-name-${editingTaskId}`);
    if (el) { el.focus(); el.select(); }
  }
}
