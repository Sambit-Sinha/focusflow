// =============================================================================
// state.js — The single source of truth for the whole app.
//
// In data science terms, think of this as your "master DataFrame" — one
// central object that every function reads from and writes to. No component
// stores its own copy of the tasks; they all read from here. This prevents
// the classic bug where the calendar shows stale data because the tasks panel
// updated its local copy but forgot to tell the calendar.
//
// Pattern used: "Observable State" (also called a "store" in React/Redux)
//   - getState()      → read the current values (like df.copy())
//   - setState(patch) → merge new values in + notify all listeners
//   - subscribe(fn)   → register a function to run whenever state changes
//
// When setState is called, every subscribed function fires automatically.
// This is how renderTasks() and renderCal() stay in sync without either
// calling the other — they both subscribe, and state drives them both.
// =============================================================================

const state = {
  user:          null,   // { id, name } — set after login
  tasks:         [],     // full task list with completions[] for each
  chatHistory:   [],     // array of { role, content } for the AI coach conversation
  currentFilter: "all",  // which filter pill is active in the Tasks tab
  calYear:       new Date().getFullYear(),
  calMonth:      new Date().getMonth(),   // 0-indexed (0 = January)
  editingTaskId: null,   // which task row is showing its inline edit form
  modalDate:     null,   // which date the day-detail modal is open for
};

// listeners is an array of callback functions registered via subscribe().
// Each element is a function that should run whenever state changes.
const listeners = [];

// Returns the current state object (same reference, not a copy).
// Reading from it is fast and safe as long as you don't mutate it directly
// — always use setState() to make changes.
function getState() { return state; }

// Merges `updates` into the state and notifies all listeners.
// Object.assign is like Python's dict.update() — it copies keys from updates
// into state, overwriting any matching keys, leaving others untouched.
// Example: setState({ tasks: newList }) only changes tasks, not user or filter.
function setState(updates) {
  Object.assign(state, updates);
  listeners.forEach((fn) => {
    try { fn(state); } catch (e) { console.error("setState listener error:", e); }
  });
}

// Subscribes a function to be called on every setState.
// Returns an "unsubscribe" function — call it to stop receiving updates.
// (Like cancelling a Kafka consumer or removing a DataFrame observer hook.)
function subscribe(fn) {
  listeners.push(fn);
  return () => {
    const idx = listeners.indexOf(fn);
    if (idx > -1) listeners.splice(idx, 1);
  };
}

// ——— Derived helpers ———
// These are "computed columns" — derived values calculated from the raw state
// rather than stored separately. Keeping them as functions (not stored values)
// means they're always up-to-date: call them, get the answer from today's data.

// A task is "stale" if it hasn't been touched recently.
// Repetitive: no completion in the last 3 days = stale.
// One-time: created more than 3 days ago without completion = stale.
// Completed tasks are never stale — they're done.
const STALE_DAYS = 3;

function isStale(task) {
  if (task.completed) return false;
  const now = new Date();
  if (task.task_type === "repetitive") {
    if (!task.completions?.length) return true;   // never touched at all = definitely stale
    // Sort descending and take the most recent completion date
    const mostRecent = task.completions
      .map((c) => new Date(c.date))
      .sort((a, b) => b - a)[0];
    // Convert millisecond difference to days
    return (now - mostRecent) / (1000 * 60 * 60 * 24) >= STALE_DAYS;
  }
  // One-time: stale if created more than STALE_DAYS ago and still not done
  return (now - new Date(task.created_at)) / (1000 * 60 * 60 * 24) >= STALE_DAYS;
}

// Returns today's date as "YYYY-MM-DD" — the format used everywhere in this app
// and in the database. Slicing the ISO string is simpler and timezone-safe
// (Date.toLocaleDateString() varies by locale and can give unexpected formats).
function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// Looks up a task's recorded progress on a specific date.
// Returns 0 if there's no completion record for that date.
// Repetitive tasks always store "100" when completed; one-time tasks store 0-100.
function progressOnDate(task, dateStr) {
  const c = task.completions?.find((c) => c.date === dateStr);
  return c ? parseInt(c.progress ?? "100", 10) : 0;
}

// "Visual done" — should the checkbox show as checked on this date?
// Repetitive: any record = done (binary, like a habit tracker)
// One-time: only 100% counts as done (you could be 80% and still "in progress")
function isCompletedOnDate(task, dateStr) {
  if (task.task_type === "repetitive") {
    return task.completions?.some((c) => c.date === dateStr) ?? false;
  }
  return progressOnDate(task, dateStr) >= 100;
}

// "Did this task make meaningful progress on this date?"
// Used for streak counting — we don't want a task that's been stuck at 50%
// for 10 days to count as "active" every day.
// Repetitive: any completion = progress (it either happened or it didn't)
// One-time: the percentage must have GONE UP compared to the most recent prior recording
function progressImprovedOnDate(task, dateStr) {
  if (task.task_type === "repetitive") return isCompletedOnDate(task, dateStr);
  const onDate = progressOnDate(task, dateStr);
  if (onDate === 0) return false;
  // Find the most recent completion before this date
  const prior = (task.completions ?? [])
    .filter((c) => c.date < dateStr)
    .sort((a, b) => b.date.localeCompare(a.date));
  const priorPct = prior.length > 0 ? parseInt(prior[0].progress ?? "0", 10) : 0;
  return onDate > priorPct;   // true only if we made forward progress
}

// Counts consecutive days (going back from today) where at least one task
// had "improved" progress. Stops the moment a day has no progress.
// Cap at 366 days to avoid infinite loops.
// Think of it like counting a run of non-zero values from the end of a time series.
function streakDays(tasks) {
  let streak = 0;
  const d = new Date();
  while (streak < 366) {
    const ds = d.toISOString().slice(0, 10);
    const anyProgress = tasks.some((t) => progressImprovedOnDate(t, ds));
    if (!anyProgress) break;
    streak++;
    d.setDate(d.getDate() - 1);   // go back one day
  }
  return streak;
}

// Returns the tasks matching the current active filter.
// Mirrors pandas-style filtering: tasks.filter(condition).
// "stale" filter uses the isStale() helper; category filters compare the
// task's category string to the filter name.
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
    default:         return tasks;   // "all" — return everything
  }
}

// Builds a plain-text summary of the user's tasks to inject into the AI prompt.
// The AI coach uses this as context so it can give personalised advice without
// needing the user to explain their situation every time.
// Example output: "5 tasks total. Categories: work, health. Stale: 2. Completed: 1."
function buildTaskSummary() {
  const { tasks } = state;
  if (!tasks.length) return "No tasks added yet.";
  const cats = [...new Set(tasks.map((t) => t.category))].join(", ");
  return `${tasks.length} tasks total. Categories: ${cats}. Stale: ${tasks.filter(isStale).length}. Completed: ${tasks.filter((t) => t.completed).length}.`;
}

export {
  getState, setState, subscribe,
  isStale, todayStr,
  progressOnDate, isCompletedOnDate, progressImprovedOnDate, streakDays,
  getFilteredTasks, buildTaskSummary,
};
