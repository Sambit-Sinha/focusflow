// =============================================================================
// tasks.js — Everything related to the Tasks tab.
//
// Responsibilities:
//   1. Bind the "Add task" input and filter buttons (initTasks / bindTaskInput)
//   2. CRUD operations: add, toggle, delete, edit tasks via the API
//   3. Build and render the task table HTML (renderTasks)
//
// Key pattern — "delegated events":
// Instead of attaching a click listener to each button in every row,
// we attach ONE listener to the entire table. When a button is clicked,
// the event "bubbles up" to the table, and we check data-action to decide
// what to do. This is more efficient (fewer listeners) and works even after
// the table HTML is completely replaced by re-renders.
// =============================================================================

import api from "../utils/api.js";
import { getState, setState, subscribe, isStale, todayStr, getFilteredTasks } from "../utils/state.js";

// CSS class name for each category's colour tag
const CATS = {
  work: "tag-work", personal: "tag-personal",
  health: "tag-health", study: "tag-study", misc: "tag-misc",
};

// Human-readable labels with emojis shown in the UI
const CAT_LABELS = {
  work: "💼 Work", personal: "🏠 Personal",
  health: "💚 Health", study: "📚 Study", misc: "📌 Misc",
};

// Escapes HTML special characters before injecting user-provided text into innerHTML.
// Without this, a task named "<script>..." would execute as JavaScript — a classic
// Cross-Site Scripting (XSS) vulnerability. Always escape untrusted input.
function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// Builds the <option> list for the category dropdown, pre-selecting the current value
function catOptions(selected) {
  return Object.entries(CAT_LABELS)
    .map(([v, l]) => `<option value="${v}" ${selected === v ? "selected" : ""}>${l}</option>`)
    .join("");
}

// Builds the <option> list for the task type dropdown
function typeOptions(selected) {
  return `<option value="one-time" ${selected === "one-time" ? "selected" : ""}>✓ One-time</option>
          <option value="repetitive" ${selected === "repetitive" ? "selected" : ""}>🔁 Repetitive</option>`;
}

// Returns the most recent completion date for a task as "YYYY-MM-DD", or null.
// Used to display the "Last worked" column in the task table.
// Array.at(-1) gets the last element after sorting ascending — clean shorthand
// for .sort()[.sort().length - 1].
function lastWorked(task) {
  if (!task.completions?.length) return null;
  return [...task.completions]
    .map(c => c.date)
    .sort()
    .at(-1);
}

// ——— INIT ———

// Called once at boot. Subscribes renderTasks to state changes and wires inputs.
// subscribe(renderTasks) means: "every time setState() is called anywhere,
// re-run renderTasks()". So adding a task from the AI chat would also update
// this list automatically — no manual coordination needed.
export function initTasks() {
  subscribe(renderTasks);
  bindTaskInput();
}

// Wires all the input controls in the "Add task" bar:
//   - Enter key and Add button → addTask()
//   - Task type dropdown → show/hide date range row (one-time only)
//   - Filter pills → update currentFilter in state → triggers re-render via subscribe
function bindTaskInput() {
  document.getElementById("task-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addTask();
  });
  document.getElementById("btn-add-task").addEventListener("click", addTask);

  const typeSelect   = document.getElementById("task-type");
  const dateRangeRow = document.getElementById("task-date-range");
  function syncDateRow() {
    // Date pickers only make sense for one-time tasks with a known end date
    dateRangeRow.style.display = typeSelect.value === "one-time" ? "flex" : "none";
  }
  typeSelect.addEventListener("change", syncDateRow);
  syncDateRow();   // run immediately to set the correct initial state

  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setState({ currentFilter: btn.dataset.filter });
      document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });
}

// ——— ADD TASK ———

// Reads the form values, calls the backend, updates state.
// Disabling the input during the API call prevents duplicate submissions
// if the user presses Enter twice quickly (debounce via UI lock).
async function addTask() {
  const input    = document.getElementById("task-input");
  const cat      = document.getElementById("task-cat").value;
  const taskType = document.getElementById("task-type").value;
  const name     = input.value.trim();
  if (!name) return;   // do nothing if the field is empty
  const { user } = getState();
  if (!user) return;

  const fromDate = taskType === "one-time" ? (document.getElementById("task-from-date").value || null) : null;
  const toDate   = taskType === "one-time" ? (document.getElementById("task-to-date").value   || null) : null;

  input.value    = "";       // clear immediately so it feels responsive
  input.disabled = true;     // lock the input to prevent double submissions
  try {
    // todayStr() gives "YYYY-MM-DD" for the creation date
    const task = await api.createTask(user.id, name, cat, taskType, todayStr(), fromDate, toDate);
    const { tasks } = getState();
    // Prepend the new task so it appears at the top of the list
    setState({ tasks: [task, ...tasks] });
    if (fromDate) document.getElementById("task-from-date").value = "";
    if (toDate)   document.getElementById("task-to-date").value   = "";
  } catch (e) {
    console.error(e);
    alert("Could not save task. Is the backend running?");
  } finally {
    // finally runs whether the try succeeded or the catch fired — always re-enable input
    input.disabled = false;
    input.focus();
  }
}

// ——— TOGGLE TASK ———

// Flips a task's "completed" flag via the backend, then updates state.
// The PATCH call sends only { completed: true/false } — the backend knows to
// leave all other fields unchanged (model_fields_set pattern in Python).
// After setState, all subscribers (renderTasks, renderCal) re-render automatically.
export async function toggleTask(taskId) {
  const { user, tasks } = getState();
  try {
    const updated = await api.updateTask(user.id, taskId, {
      completed: !tasks.find((t) => t.id === taskId)?.completed,
    });
    // Replace only the updated task in the array; leave all others unchanged
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    // Force a calendar re-render in case the calendar tab is visible
    if (window._renderCal) window._renderCal();
  } catch (e) { console.error(e); }
}

// ——— DELETE TASK ———

// Deletes the task from the database and removes it from local state.
// The backend cascade-deletes all completion records for this task automatically.
export async function deleteTask(taskId) {
  const { user, tasks } = getState();
  try {
    await api.deleteTask(user.id, taskId);
    setState({ tasks: tasks.filter((t) => t.id !== taskId) });
    if (window._renderCal) window._renderCal();
  } catch (e) { console.error(e); }
}

// ——— EDIT ———

// Sets editingTaskId in state, which triggers renderTasks to swap that row
// from normalRow() to editRow() (showing the inline edit form).
export function startEdit(taskId) { setState({ editingTaskId: taskId }); }

// Reads the values from the inline edit form, sends a PATCH, updates state.
// If the name is empty on save, we cancel instead of saving a blank task.
export async function saveEdit(taskId) {
  const nameEl = document.getElementById(`edit-name-${taskId}`);
  const catEl  = document.getElementById(`edit-cat-${taskId}`);
  const typeEl = document.getElementById(`edit-type-${taskId}`);
  if (!nameEl) return;
  const name = nameEl.value.trim();
  if (!name) { setState({ editingTaskId: null }); return; }   // cancel gracefully on empty name
  const { user, tasks } = getState();

  const updates = { name, category: catEl?.value, task_type: typeEl?.value };
  // Date pickers only exist for one-time tasks; null means "clear the date"
  const fromEl = document.getElementById(`edit-from-${taskId}`);
  const toEl   = document.getElementById(`edit-to-${taskId}`);
  if (fromEl) updates.from_date = fromEl.value || null;
  if (toEl)   updates.to_date   = toEl.value   || null;

  try {
    const updated = await api.updateTask(user.id, taskId, updates);
    // Update the task in state and clear editingTaskId → row returns to normal view
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)), editingTaskId: null });
  } catch (e) {
    console.error(e);
    setState({ editingTaskId: null });   // close edit form even on failure
  }
}

// ——— Row builders ———
// These functions generate HTML strings for a single table row.
// We use template literals (backtick strings with ${...}) to embed dynamic values.
// The row is either a "normal" read-only view or an "edit" form depending on state.

// Shows "⚡ Going stale" for stale repetitive tasks, "⏳ Overdue" for stale one-time tasks
function staleBadge(task) {
  if (!isStale(task)) return "";
  return task.task_type === "repetitive"
    ? `<span class="stale-badge">⚡ Going stale</span>`
    : `<span class="overdue-badge">⏳ Overdue</span>`;
}

// Builds the read-only table row HTML.
// data-action="toggle/edit/delete" attributes power the delegated click handler below.
// data-id lets the handler know which task was acted on without querying the DOM further.
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

  // Only show the date window for one-time tasks that have dates set
  const dateWindowHtml = !isRep && (t.from_date || t.to_date)
    ? `<div class="task-date-window">📅 ${t.from_date || "?"} → ${t.to_date || "∞"}</div>`
    : "";

  return `<tr class="task-row ${staleRowClass} ${t.completed ? "row-done" : ""}" data-id="${t.id}">
    <td class="col-cb">
      <div class="task-check ${t.completed ? "done" : ""}" data-action="toggle" data-id="${t.id}"></div>
    </td>
    <td class="col-name">
      <span class="task-name">${escHtml(t.name)}</span>
      ${staleBadge(t)}
      ${dateWindowHtml}
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

// Builds the inline-edit row HTML.
// colspan="7" makes this row span all columns so the edit form has full width.
// data-action="edit-key" on the input handles keyboard shortcuts (Enter/Escape).
function editRow(t) {
  const isOneTime = t.task_type === "one-time";
  const datePickers = isOneTime ? `
    <span class="edit-date-sep">|</span>
    <label class="edit-date-field">From <input type="date" class="edit-date" id="edit-from-${t.id}" value="${t.from_date || ""}"></label>
    <label class="edit-date-field">To <input type="date" class="edit-date" id="edit-to-${t.id}" value="${t.to_date || ""}"></label>` : "";
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
          ${datePickers}
          <button class="btn btn-primary btn-sm" data-action="save-edit"   data-id="${t.id}">Save</button>
          <button class="btn btn-ghost   btn-sm" data-action="cancel-edit" data-id="${t.id}">Cancel</button>
        </div>
      </div>
    </td>
  </tr>`;
}

// ——— Main render ———

// Rebuilds the entire task table from scratch every time state changes.
// This is simpler than surgically updating individual rows, and fast enough
// because JS string building + one innerHTML assignment is very cheap.
// (No virtual DOM needed at this scale — the DOM update is the bottleneck,
// and we only do one innerHTML = ... per render.)
export function renderTasks() {
  const { tasks, editingTaskId } = getState();
  const list = document.getElementById("task-list");
  if (!list) return;

  // Update the progress bar at the top of the task panel
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

  // Build the full table HTML in one go, then set innerHTML once.
  // For each task: if it's the one being edited, show editRow; otherwise normalRow.
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
  // One click handler on the whole table routes to the right action via data-action.
  // e.target.closest("[data-action]") walks up the DOM tree from the clicked element
  // to find the nearest ancestor with a data-action attribute — handles clicks on
  // child elements (e.g. clicking the checkbox icon inside the button div).
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

  // Keyboard shortcuts inside the edit row input field
  list.onkeydown = async (e) => {
    const el = e.target.closest("[data-action='edit-key']");
    if (!el) return;
    if (e.key === "Enter")  await saveEdit(el.dataset.id);
    if (e.key === "Escape") setState({ editingTaskId: null });
  };

  // Auto-focus the edit input and select its text so the user can start typing immediately
  if (editingTaskId) {
    const el = document.getElementById(`edit-name-${editingTaskId}`);
    if (el) { el.focus(); el.select(); }
  }
}
