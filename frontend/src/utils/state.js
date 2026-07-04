const state = {
  user: null,
  tasks: [],
  chatHistory: [],
  currentFilter: "all",
  calYear: new Date().getFullYear(),
  calMonth: new Date().getMonth(),
  editingTaskId: null,
  modalDate: null,
};

const listeners = [];

function getState() { return state; }

function setState(updates) {
  Object.assign(state, updates);
  listeners.forEach((fn) => {
    try { fn(state); } catch (e) { console.error("setState listener error:", e); }
  });
}

function subscribe(fn) {
  listeners.push(fn);
  return () => {
    const idx = listeners.indexOf(fn);
    if (idx > -1) listeners.splice(idx, 1);
  };
}

// ——— Derived helpers ———

const STALE_DAYS = 3;

function isStale(task) {
  if (task.completed) return false;
  const now = new Date();
  if (task.task_type === "repetitive") {
    // Stale if no completion in the last STALE_DAYS days
    if (!task.completions?.length) return true;
    const mostRecent = task.completions
      .map((c) => new Date(c.date))
      .sort((a, b) => b - a)[0];
    return (now - mostRecent) / (1000 * 60 * 60 * 24) >= STALE_DAYS;
  }
  // One-time: stale if created more than STALE_DAYS ago
  return (now - new Date(task.created_at)) / (1000 * 60 * 60 * 24) >= STALE_DAYS;
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// Returns the recorded progress (0–100) for a task on a specific date.
// Repetitive tasks always store "100"; one-time tasks store whatever was set.
function progressOnDate(task, dateStr) {
  const c = task.completions?.find((c) => c.date === dateStr);
  return c ? parseInt(c.progress ?? "100", 10) : 0;
}

// Visual "done" state:
//   repetitive  → any completion record = done
//   one-time    → progress must be 100
function isCompletedOnDate(task, dateStr) {
  if (task.task_type === "repetitive") {
    return task.completions?.some((c) => c.date === dateStr) ?? false;
  }
  return progressOnDate(task, dateStr) >= 100;
}

// Streak: consecutive days (going back from today) where ANY task had ANY progress > 0.
// This counts both repetitive completions and any partial one-time progress.
function streakDays(tasks) {
  let streak = 0;
  const d = new Date();
  while (streak < 366) {
    const ds = d.toISOString().slice(0, 10);
    const anyProgress = tasks.some((t) => progressOnDate(t, ds) > 0);
    if (!anyProgress) break;
    streak++;
    d.setDate(d.getDate() - 1);
  }
  return streak;
}

function getFilteredTasks() {
  const { tasks, currentFilter } = state;
  switch (currentFilter) {
    case "active":   return tasks.filter((t) => !t.completed);
    case "done":     return tasks.filter((t) => t.completed);
    case "stale":    return tasks.filter((t) => isStale(t));
    case "work":
    case "personal":
    case "health":
    case "study":
    case "misc":     return tasks.filter((t) => t.category === currentFilter);
    default:         return tasks;
  }
}

function buildTaskSummary() {
  const { tasks } = state;
  if (!tasks.length) return "No tasks added yet.";
  const cats = [...new Set(tasks.map((t) => t.category))].join(", ");
  return `${tasks.length} tasks total. Categories: ${cats}. Stale: ${tasks.filter(isStale).length}. Completed: ${tasks.filter((t) => t.completed).length}.`;
}

export {
  getState, setState, subscribe,
  isStale, todayStr,
  progressOnDate, isCompletedOnDate, streakDays,
  getFilteredTasks, buildTaskSummary,
};
