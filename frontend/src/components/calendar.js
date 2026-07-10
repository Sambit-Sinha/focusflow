// =============================================================================
// calendar.js — Everything related to the Calendar tab.
//
// The calendar renders a monthly grid where each cell shows:
//   - For repetitive tasks: a binary checkbox the user can click in-place
//   - For one-time tasks: just the task name (progress is set in the day modal)
//
// Clicking any calendar cell opens a "day modal" — a popup showing all tasks
// for that day, with checkboxes for repetitive tasks and a slider (0–100%) for
// one-time tasks.
//
// Key architectural decision: calendar.js registers itself as window._renderCal
// so tasks.js can call it after toggling or deleting tasks — without importing
// calendar.js directly (which would create a circular import).
// =============================================================================

import api from "../utils/api.js";
import { getState, setState, subscribe, isCompletedOnDate, progressOnDate, progressImprovedOnDate, streakDays, todayStr } from "../utils/state.js";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const CATS   = { work:"tag-work", personal:"tag-personal", health:"tag-health", study:"tag-study", misc:"tag-misc" };
const CAT_LABELS = { work:"💼 Work", personal:"🏠 Personal", health:"💚 Health", study:"📚 Study", misc:"📌 Misc" };

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ——— INIT ———

// Called once at boot. Wires up the month navigation buttons and the day modal close buttons.
// Also registers renderCal on window._renderCal so tasks.js can call it without a direct import.
// subscribe(renderCal) means the calendar auto-updates whenever state changes (e.g. a task is added).
export function initCalendar() {
  subscribe(renderCal);
  window._renderCal = renderCal;   // expose to tasks.js which can't import calendar.js directly

  // ← and → buttons to navigate months
  document.getElementById("btn-prev-month").addEventListener("click", () => {
    let { calYear, calMonth } = getState();
    calMonth--;
    if (calMonth < 0) { calMonth = 11; calYear--; }   // wrap December → January
    setState({ calYear, calMonth });
  });
  document.getElementById("btn-next-month").addEventListener("click", () => {
    let { calYear, calMonth } = getState();
    calMonth++;
    if (calMonth > 11) { calMonth = 0; calYear++; }   // wrap December → January
    setState({ calYear, calMonth });
  });
  document.getElementById("btn-today").addEventListener("click", () => {
    const now = new Date();
    setState({ calYear: now.getFullYear(), calMonth: now.getMonth() });
  });

  // Close the day modal when clicking the backdrop or the X button
  document.getElementById("cal-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("cal-modal")) closeDayModal();
  });
  document.getElementById("modal-close").addEventListener("click", closeDayModal);
}

// ——— VISIBILITY LOGIC FOR ONE-TIME TASKS ———

// Should a one-time task appear in a given calendar cell?
// Rules:
//   - Not visible before its from_date (or created_at if no from_date is set)
//   - Not visible after its to_date
//   - Not visible once the task reached 100% on any EARLIER day
//     (it's done — no point showing it again for future dates)
function isOneTimeVisibleOnDate(task, dateStr) {
  const from = task.from_date || task.created_at;
  const to   = task.to_date;
  if (dateStr < from) return false;
  if (to && dateStr > to) return false;
  // Hide the task on dates after it was completed (100% on any prior day)
  const completedBefore = (task.completions ?? []).some(
    (c) => c.date < dateStr && parseInt(c.progress ?? "0", 10) >= 100
  );
  return !completedBefore;
}

// ——— RENDER CALENDAR ———

// Rebuilds the entire calendar grid from scratch.
// Steps:
//   1. Write the day-of-week header row (Sun Mon Tue ...)
//   2. Insert empty cells for the days before the 1st of the month
//   3. For each day: filter relevant tasks, build mini task items, build the cell HTML
//   4. Attach a delegated click handler for inline toggles and modal opens
export function renderCal() {
  const { calYear, calMonth, tasks } = getState();
  const calMonthLabel = document.getElementById("cal-month-label");
  if (!calMonthLabel) return;

  calMonthLabel.textContent = `${MONTHS[calMonth]} ${calYear}`;
  renderStreaks();   // update the streak/done counters above the grid

  const grid = document.getElementById("cal-grid");
  // Day-of-week header row
  grid.innerHTML = DAYS.map((d) => `<div class="cal-day-label">${d}</div>`).join("");

  // Calculate layout offsets
  const firstDay    = new Date(calYear, calMonth, 1).getDay();   // 0=Sun, 6=Sat
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();  // last day of month
  const todayD      = new Date();

  // Empty cells to align day 1 under the correct column
  for (let i = 0; i < firstDay; i++) {
    grid.innerHTML += `<div class="cal-cell empty-cell"></div>`;
  }

  for (let day = 1; day <= daysInMonth; day++) {
    // Zero-pad month and day to "YYYY-MM-DD" for consistent string comparison
    const dateStr = `${calYear}-${String(calMonth + 1).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    const isToday = todayD.getFullYear() === calYear && todayD.getMonth() === calMonth && todayD.getDate() === day;

    // Which tasks should appear in this cell?
    // Repetitive: visible on any day on or after creation
    // One-time: visibility controlled by isOneTimeVisibleOnDate()
    const relevant = tasks.filter((t) =>
      t.task_type === "repetitive"
        ? t.created_at <= dateStr
        : isOneTimeVisibleOnDate(t, dateStr)
    );
    // Only show up to 3 tasks in the mini cell; show "+N more" if there are extras
    const shown = relevant.slice(0, 3);
    const extra = relevant.length - 3;

    const taskHtml = shown.map((t) => {
      if (t.task_type === "repetitive") {
        const done = isCompletedOnDate(t, dateStr);
        // Repetitive task: inline checkbox that toggles without opening the modal
        // data-action="cal-toggle" is intercepted before the cell's open-modal action
        return `<div class="cal-task-item" data-action="cal-toggle" data-id="${t.id}" data-date="${dateStr}">
          <div class="cal-task-cb ${done ? "done" : ""}"></div>
          <div class="cal-task-name ${done ? "done" : ""}">${escHtml(t.name)}</div>
        </div>`;
      } else {
        // One-time task: just shows name + completion state; progress slider is in the modal
        const pct = progressOnDate(t, dateStr);
        return `<div class="cal-task-item">
          <div class="cal-task-name ${pct >= 100 ? "done" : ""}">${escHtml(t.name)}</div>
        </div>`;
      }
    }).join("");
    const extraHtml = extra > 0 ? `<div class="cal-more">+${extra} more</div>` : "";

    grid.innerHTML += `<div class="cal-cell ${isToday ? "today" : ""}" data-action="open-modal" data-date="${dateStr}">
      <div class="cal-date-num">${day}</div>
      <div class="cal-tasks-mini">${taskHtml}${extraHtml}</div>
    </div>`;
  }

  // ——— Delegated click handler ———
  // Two kinds of clicks on the grid:
  //   1. Click on a repetitive task checkbox → toggle it in-place (cal-toggle)
  //   2. Click anywhere else on a cell → open the day modal (open-modal)
  // e.stopPropagation() on the toggle prevents the cell's open-modal from also firing
  grid.onclick = async (e) => {
    const toggleEl = e.target.closest("[data-action='cal-toggle']");
    if (toggleEl) {
      e.stopPropagation();   // don't let this click also trigger the cell's open-modal
      await calToggle(toggleEl.dataset.id, toggleEl.dataset.date);
      return;
    }
    const cellEl = e.target.closest("[data-action='open-modal']");
    if (cellEl) openDayModal(cellEl.dataset.date);
  };
}

// ——— STREAK AND STATS BAR ———

// Updates the three counters shown above the calendar:
//   "Done today" — tasks with improved progress today
//   "This month" — total completion records in the viewed month
//   "Streak" — consecutive days with any progress going back from today
function renderStreaks() {
  const { tasks, calYear, calMonth } = getState();
  const todayS = todayStr();

  const todayDone = tasks.filter((t) => progressImprovedOnDate(t, todayS)).length;
  document.getElementById("today-done").textContent = todayDone;

  // Count completions in the currently viewed month (e.g. "2025-07")
  const prefix = `${calYear}-${String(calMonth + 1).padStart(2,"0")}`;
  let monthCount = 0;
  tasks.forEach((t) => t.completions?.forEach((c) => { if (c.date.startsWith(prefix)) monthCount++; }));
  document.getElementById("month-done").textContent = monthCount;

  document.getElementById("streak-num").textContent = streakDays(tasks);
}

// ——— TOGGLE (repetitive tasks, in-place) ———

// Sends the toggle to the backend, updates state, and re-renders if the modal is open.
// Calling renderStreaks() directly (rather than relying on the state subscription)
// guarantees the counters update immediately — subscriptions may fire in a different order.
async function calToggle(taskId, dateStr) {
  const { user, tasks } = getState();
  try {
    const updated = await api.toggleCompletion(user.id, taskId, dateStr);
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    renderStreaks();
    // If the day modal is open for this date, refresh it so it shows the updated state
    if (getState().modalDate === dateStr) renderDayModal(dateStr);
  } catch (e) { console.error(e); }
}

// ——— SET PROGRESS (one-time tasks, via day modal slider) ———

// Same flow as calToggle but sends a percentage (0–100) to the backend.
// pct=0 removes the completion record; pct=1-100 creates or updates it.
async function calSetProgress(taskId, dateStr, pct) {
  const { user, tasks } = getState();
  try {
    const updated = await api.toggleCompletion(user.id, taskId, dateStr, pct);
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    renderStreaks();
    if (getState().modalDate === dateStr) renderDayModal(dateStr);
  } catch (e) { console.error(e); }
}

// ——— DAY MODAL ———

// Opens the popup for a specific date.
// Stores the date in state so renderDayModal can re-render if a toggle happens
// while the modal is open.
function openDayModal(dateStr) {
  setState({ modalDate: dateStr });
  renderDayModal(dateStr);
  document.getElementById("cal-modal").style.display = "flex";
}

// Renders the contents of the day modal.
// Repetitive tasks: checkbox that triggers calToggle
// One-time tasks: a slider (0–100%) + Save button that triggers calSetProgress
//
// "Live slider label" — oninput fires as the user drags the slider, updating
// the "X%" label in real time without saving yet. Saving only happens on button click.
function renderDayModal(dateStr) {
  const { tasks } = getState();
  const [y, m, d] = dateStr.split("-").map(Number);
  document.getElementById("modal-date-title").textContent =
    new Date(y, m - 1, d).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  const relevant = tasks.filter((t) =>
    t.task_type === "repetitive"
      ? t.created_at <= dateStr
      : isOneTimeVisibleOnDate(t, dateStr)
  );
  const box = document.getElementById("modal-tasks");

  if (!relevant.length) {
    box.innerHTML = `<div class="modal-empty">No tasks for this date yet.</div>`;
    return;
  }

  box.innerHTML = relevant.map((t) => {
    if (t.task_type === "repetitive") {
      const done = isCompletedOnDate(t, dateStr);
      return `<div class="modal-task-row" data-action="modal-toggle" data-id="${t.id}" data-date="${dateStr}">
        <div class="cal-task-cb modal-cb ${done ? "done" : ""}"></div>
        <span class="tag tag-repetitive" style="font-size:10px">🔁</span>
        <span class="modal-task-name ${done ? "done" : ""}">${escHtml(t.name)}</span>
      </div>`;
    } else {
      const pct = progressOnDate(t, dateStr);
      // id="ps-{taskId}" for the slider and id="pv-{taskId}" for the percentage label
      // — paired by replacing "ps-" with "pv-" in the oninput handler below
      return `<div class="modal-task-progress">
        <div class="modal-prog-header">
          <div class="cal-task-cb modal-cb ${pct >= 100 ? "done" : ""}"></div>
          <span class="tag tag-onetime" style="font-size:10px">✓</span>
          <span class="modal-task-name ${pct >= 100 ? "done" : ""}">${escHtml(t.name)}</span>
          <span class="modal-prog-pct" id="pv-${t.id}">${pct}%</span>
        </div>
        <div class="modal-prog-controls">
          <input type="range" min="0" max="100" value="${pct}"
            class="prog-slider" id="ps-${t.id}">
          <button class="btn btn-primary btn-sm"
            data-action="save-progress" data-id="${t.id}" data-date="${dateStr}">Save</button>
        </div>
      </div>`;
    }
  }).join("");

  // Live update the "X%" label as the slider is dragged (before saving)
  box.oninput = (e) => {
    const slider = e.target.closest(".prog-slider");
    if (!slider) return;
    const valEl = document.getElementById(slider.id.replace("ps-", "pv-"));
    if (valEl) valEl.textContent = slider.value + "%";
  };

  // Delegated click handler for the modal
  box.onclick = async (e) => {
    // Repetitive task toggle
    const repEl  = e.target.closest("[data-action='modal-toggle']");
    if (repEl)  { await calToggle(repEl.dataset.id, repEl.dataset.date); return; }

    // One-time task: read slider value and save
    const progEl = e.target.closest("[data-action='save-progress']");
    if (progEl) {
      const slider = document.getElementById(`ps-${progEl.dataset.id}`);
      await calSetProgress(progEl.dataset.id, progEl.dataset.date, parseInt(slider.value));
    }
  };
}

// Hides the modal and clears the tracked date from state
function closeDayModal() {
  document.getElementById("cal-modal").style.display = "none";
  setState({ modalDate: null });
}
