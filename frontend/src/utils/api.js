// ============================================================
//  api.js — All backend calls live here.
//  CHANGE BASE_URL to your Render URL when deploying.
// ============================================================

// Development: http://localhost:8000
// Production:  https://un-poco-loco-api.onrender.com
const BASE_URL = "https://un-poco-loco-api.onrender.com";

const api = {
  // ——— USERS ———
  async login(name) {
    const res = await fetch(`${BASE_URL}/users/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // ——— TASKS ———
  async getTasks(userId) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

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

  async updateTask(userId, taskId, updates) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async deleteTask(userId, taskId) {
    const res = await fetch(`${BASE_URL}/tasks/${userId}/${taskId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  // progress = null → binary toggle (repetitive); 0-100 → set percentage (one-time)
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
export { BASE_URL };
