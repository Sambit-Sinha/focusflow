import api from "../utils/api.js";
import { getState, setState, subscribe, isCompletedOnDate, progressOnDate, progressImprovedOnDate, streakDays, todayStr } from "../utils/state.js";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS   = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const CATS   = { work:"tag-work", personal:"tag-personal", health:"tag-health", study:"tag-study", misc:"tag-misc" };
const CAT_LABELS = { work:"💼 Work", personal:"🏠 Personal", health:"💚 Health", study:"📚 Study", misc:"📌 Misc" };

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

export function initCalendar() {
  subscribe(renderCal);
  window._renderCal = renderCal;

  document.getElementById("btn-prev-month").addEventListener("click", () => {
    let { calYear, calMonth } = getState();
    calMonth--;
    if (calMonth < 0) { calMonth = 11; calYear--; }
    setState({ calYear, calMonth });
  });
  document.getElementById("btn-next-month").addEventListener("click", () => {
    let { calYear, calMonth } = getState();
    calMonth++;
    if (calMonth > 11) { calMonth = 0; calYear++; }
    setState({ calYear, calMonth });
  });
  document.getElementById("btn-today").addEventListener("click", () => {
    const now = new Date();
    setState({ calYear: now.getFullYear(), calMonth: now.getMonth() });
  });

  document.getElementById("cal-modal").addEventListener("click", (e) => {
    if (e.target === document.getElementById("cal-modal")) closeDayModal();
  });
  document.getElementById("modal-close").addEventListener("click", closeDayModal);
}

// Should a one-time task appear in a given calendar cell?
function isOneTimeVisibleOnDate(task, dateStr) {
  const from = task.from_date || task.created_at;
  const to   = task.to_date;
  if (dateStr < from) return false;
  if (to && dateStr > to) return false;
  // hide once the task hit 100% on any earlier day
  const completedBefore = (task.completions ?? []).some(
    (c) => c.date < dateStr && parseInt(c.progress ?? "0", 10) >= 100
  );
  return !completedBefore;
}

export function renderCal() {
  const { calYear, calMonth, tasks } = getState();
  const calMonthLabel = document.getElementById("cal-month-label");
  if (!calMonthLabel) return;

  calMonthLabel.textContent = `${MONTHS[calMonth]} ${calYear}`;
  renderStreaks();

  const grid = document.getElementById("cal-grid");
  grid.innerHTML = DAYS.map((d) => `<div class="cal-day-label">${d}</div>`).join("");

  const firstDay    = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const todayD      = new Date();

  for (let i = 0; i < firstDay; i++) {
    grid.innerHTML += `<div class="cal-cell empty-cell"></div>`;
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${calYear}-${String(calMonth + 1).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    const isToday = todayD.getFullYear() === calYear && todayD.getMonth() === calMonth && todayD.getDate() === day;
    const relevant = tasks.filter((t) =>
      t.task_type === "repetitive"
        ? t.created_at <= dateStr
        : isOneTimeVisibleOnDate(t, dateStr)
    );
    const shown    = relevant.slice(0, 3);
    const extra    = relevant.length - 3;

    const taskHtml = shown.map((t) => {
      if (t.task_type === "repetitive") {
        const done = isCompletedOnDate(t, dateStr);
        // Repetitive: binary checkbox, click to toggle
        return `<div class="cal-task-item" data-action="cal-toggle" data-id="${t.id}" data-date="${dateStr}">
          <div class="cal-task-cb ${done ? "done" : ""}"></div>
          <div class="cal-task-name ${done ? "done" : ""}">${escHtml(t.name)}</div>
        </div>`;
      } else {
        // One-time: just the name; progress slider is only in the day modal
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

  // Delegated click: repetitive tasks toggle in-place; everything else opens modal
  grid.onclick = async (e) => {
    const toggleEl = e.target.closest("[data-action='cal-toggle']");
    if (toggleEl) {
      e.stopPropagation();
      await calToggle(toggleEl.dataset.id, toggleEl.dataset.date);
      return;
    }
    const cellEl = e.target.closest("[data-action='open-modal']");
    if (cellEl) openDayModal(cellEl.dataset.date);
  };
}

function renderStreaks() {
  const { tasks, calYear, calMonth } = getState();
  const todayS = todayStr();

  // "Done today" = tasks where progress actually improved today
  const todayDone = tasks.filter((t) => progressImprovedOnDate(t, todayS)).length;
  document.getElementById("today-done").textContent = todayDone;

  // "This month" = total progress records (any %) in the viewed month
  const prefix = `${calYear}-${String(calMonth + 1).padStart(2,"0")}`;
  let monthCount = 0;
  tasks.forEach((t) => t.completions?.forEach((c) => { if (c.date.startsWith(prefix)) monthCount++; }));
  document.getElementById("month-done").textContent = monthCount;

  // Streak = consecutive days going back from today where ANY task had progress > 0
  document.getElementById("streak-num").textContent = streakDays(tasks);
}

// ——— Toggle (repetitive only) ———
async function calToggle(taskId, dateStr) {
  const { user, tasks } = getState();
  try {
    const updated = await api.toggleCompletion(user.id, taskId, dateStr);
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    renderStreaks();  // guarantee immediate update regardless of listener order
    if (getState().modalDate === dateStr) renderDayModal(dateStr);
  } catch (e) { console.error(e); }
}

// ——— Set progress (one-time tasks) ———
async function calSetProgress(taskId, dateStr, pct) {
  const { user, tasks } = getState();
  try {
    const updated = await api.toggleCompletion(user.id, taskId, dateStr, pct);
    setState({ tasks: tasks.map((t) => (t.id === taskId ? updated : t)) });
    renderStreaks();  // guarantee immediate update regardless of listener order
    if (getState().modalDate === dateStr) renderDayModal(dateStr);
  } catch (e) { console.error(e); }
}

// ——— Modal ———
function openDayModal(dateStr) {
  setState({ modalDate: dateStr });
  renderDayModal(dateStr);
  document.getElementById("cal-modal").style.display = "flex";
}

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

  // Live slider label update
  box.oninput = (e) => {
    const slider = e.target.closest(".prog-slider");
    if (!slider) return;
    const valEl = document.getElementById(slider.id.replace("ps-", "pv-"));
    if (valEl) valEl.textContent = slider.value + "%";
  };

  // Click events
  box.onclick = async (e) => {
    const repEl  = e.target.closest("[data-action='modal-toggle']");
    if (repEl)  { await calToggle(repEl.dataset.id, repEl.dataset.date); return; }

    const progEl = e.target.closest("[data-action='save-progress']");
    if (progEl) {
      const slider = document.getElementById(`ps-${progEl.dataset.id}`);
      await calSetProgress(progEl.dataset.id, progEl.dataset.date, parseInt(slider.value));
    }
  };
}

function closeDayModal() {
  document.getElementById("cal-modal").style.display = "none";
  setState({ modalDate: null });
}
