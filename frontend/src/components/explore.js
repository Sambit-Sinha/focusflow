import api from "../utils/api.js";
import { getState, setState, buildTaskSummary } from "../utils/state.js";

const RECS = [
  { emoji:"🌲", name:"Forest App", desc:"Grow virtual trees by keeping your phone face-down. Gamified focus sessions that actually work for ADHD.", tags:["Focus","Mobile","Gamification"] },
  { emoji:"✅", name:"Todoist", desc:"Fast task capture with natural language input. No friction brain-dumping.", tags:["Tasks","Cross-platform"] },
  { emoji:"🎵", name:"Brain.fm", desc:"AI-generated neural-phase-locking music designed to induce deep focus. Science-backed.", tags:["Focus","Audio"] },
  { emoji:"🍅", name:"Pomofocus", desc:"Free Pomodoro timer. 25-min work + 5-min break cycles fight ADHD time blindness.", tags:["Time","Free"] },
  { emoji:"🧠", name:"Notion", desc:"Flexible workspace for ADHD planning templates, brain dumps, and daily reviews.", tags:["Notes","Planning"] },
  { emoji:"📱", name:"Finch", desc:"A self-care pet app with tiny daily goals. Dopamine hits without shame spirals.", tags:["Wellbeing","Habits"] },
  { emoji:"⏰", name:"Time Timer", desc:"Visual countdown that shows time as a shrinking disc. Makes abstract time concrete.", tags:["Visual","Focus"] },
  { emoji:"🔇", name:"Krisp", desc:"AI noise cancellation for calls. Removes distractions from your audio environment.", tags:["Focus","Remote"] },
];

export function initExplore() {
  document.getElementById("explore-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMsg();
  });
  document.getElementById("btn-send-explore").addEventListener("click", sendMsg);

  document.querySelectorAll(".quick-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.getElementById("explore-input").value = pill.dataset.prompt;
      sendMsg();
    });
  });
}

function appendMsg(content, role) {
  const msgs = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = `chat-msg ${role} fade-in`;
  div.innerHTML = `
    <div class="chat-avatar ${role}">${role === "ai" ? "FF" : "Me"}</div>
    <div class="chat-bubble">${content.replace(/\n/g, "<br>")}</div>`;
  msgs.appendChild(div);
  // requestAnimationFrame waits for the browser to finish rendering the new
  // bubble before scrolling — without it, scrollHeight may not yet include the new content
  requestAnimationFrame(() => { msgs.scrollTop = msgs.scrollHeight; });
}

function showTyping() {
  const msgs = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.id = "typing-indicator";
  div.className = "chat-msg ai fade-in";
  div.innerHTML = `
    <div class="chat-avatar ai">FF</div>
    <div class="chat-bubble">
      <div class="typing-dots">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>
    </div>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTyping() {
  document.getElementById("typing-indicator")?.remove();
}

function maybeShowRecs(text) {
  if (/app|tool|recommend|forest|todoist|notion|headspace|timer|pomodoro/i.test(text)) {
    const section = document.getElementById("recs-section");
    const cards = document.getElementById("rec-cards");
    const shown = [...RECS].sort(() => Math.random() - 0.5).slice(0, 3);
    cards.innerHTML = shown
      .map(
        (r) => `<div class="rec-card fade-in">
          <div class="rec-emoji">${r.emoji}</div>
          <div class="rec-content">
            <div class="rec-name">${r.name}</div>
            <div class="rec-desc">${r.desc}</div>
            <div class="rec-tags">${r.tags.map((t) => `<span class="rec-tag">${t}</span>`).join("")}</div>
          </div>
        </div>`
      )
      .join("");
    section.style.display = "block";
  }
}

async function sendMsg() {
  const input = document.getElementById("explore-input");
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";

  const { user, chatHistory } = getState();
  appendMsg(msg, "user");

  const newHistory = [...chatHistory, { role: "user", content: msg }];
  setState({ chatHistory: newHistory });

  showTyping();

  try {
    const data = await api.chat(user.id, newHistory.slice(-12), buildTaskSummary());
    removeTyping();
    appendMsg(data.reply, "ai");
    setState({ chatHistory: [...newHistory, { role: "assistant", content: data.reply }] });
    maybeShowRecs(data.reply);
  } catch (e) {
    removeTyping();
    appendMsg("Couldn't reach the AI coach right now. Check your backend is running.", "ai");
    console.error(e);
  }
}
