// =============================================================================
// api.js — The only file that talks to the backend.
//
// Every HTTP request to the Render server goes through this file.
// No other file should use fetch() directly — centralising it here means:
//   - One place to change the URL when deploying
//   - One place to add auth headers later if needed
//   - Easier debugging (all network errors bubble to one place)
//
// Each function returns a Promise — meaning the caller must "await" it.
// A Promise is a placeholder for a value that doesn't exist yet (the server
// hasn't responded yet). Think of it like Python's asyncio.gather() pattern.
//
// If the server returns an HTTP error code (4xx/5xx), we throw an Error
// so the caller's try/catch can handle it gracefully.
// =============================================================================

// Development: http://localhost:8000
// Production:  https://focusflow-o1fz.onrender.com
// CHANGE THIS if your Render service gets a different URL.
const BASE_URL = "https://focusflow-o1fz.onrender.com";

const api = {
  // ——— USERS ———

  // POST /users/login
  // Sends the user's name. Backend finds or creates the user and returns { id, name }.
  // "Content-Type: application/json" tells the backend to parse the body as JSON,
  // not as form data. FastAPI's Pydantic schemas only accept JSON bodies.
  async login(name) {
    const res = await fetch(`${BASE_URL}/users/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(await res.text());   // surface the error message from FastAPI
    return res.json();
  },

  // ——— TASKS ———

  // GET /tasks/{userId}
  // Returns all tasks for this user, each with a completions[] array.
  // No body needed — userId is part of the URL path.
  async getTasks(userId) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // POST /tasks/{userId}
  // Creates a new task. fromDate/toDate only apply to one-time tasks
  // and are optional — we only add them to the body if they have values,
  // otherwise the backend would receive null and might complain.
  async createTask(userId, name, category, taskType, createdAt, fromDate, toDate) {
    const body = { name, category, task_type: taskType, created_at: createdAt };
    if (fromDate) body.from_date = fromDate;
    if (toDate)   body.to_date   = toDate;
    const res = await fetch(`${BASE_URL}/tasks/${userId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // PATCH /tasks/{userId}/{taskId}
  // Updates only the fields you pass in. PATCH (partial update) vs PUT (full replace).
  // The backend's TaskUpdate schema uses Optional fields, so anything you
  // don't send is left unchanged — this is how inline edits work without
  // accidentally clearing other fields.
  async updateTask(userId, taskId, updates) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // DELETE /tasks/{userId}/{taskId}
  // No body needed — task identity is in the URL.
  // The backend cascades deletion to all completion records for this task.
  async deleteTask(userId, taskId) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}/${taskId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // POST /tasks/{userId}/{taskId}/toggle
  // Records or removes a completion for a specific calendar day.
  // progress = null  → binary toggle (repetitive tasks: done or not done)
  // progress = 0-100 → set a percentage (one-time tasks with a slider)
  // The backend returns the updated task object with all its completions
  // so we can immediately update the UI without a second fetch.
  async toggleCompletion(userId, taskId, date, progress = null) {
    const body = progress !== null ? { date, progress } : { date };
    const res = await fetch(`${BASE_URL}/tasks/${userId}/${taskId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // ——— EXPLORE / AI ———

  // POST /explore/chat
  // Sends the conversation history to the backend, which forwards it to Gemini.
  // We send taskSummary separately so the AI knows what tasks the user has
  // without needing the user to explain — it's injected into the system prompt server-side.
  // The messages array is the full conversation so far (last 12 messages are used
  // by the backend to stay within Gemini's token limits).
  async chat(userId, messages, taskSummary = "") {
    const res = await fetch(`${BASE_URL}/explore/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        messages,
        task_summary: taskSummary,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

export default api;
export { BASE_URL };   // BASE_URL is also exported so recommendations.js can build music API URLs
