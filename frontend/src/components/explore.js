// =============================================================================
// explore.js — The AI Coach tab (chat interface).
//
// This is a standard chat UI pattern: a scrolling message list and an input field.
// When the user sends a message:
//   1. Display the user's message immediately (optimistic UI)
//   2. Show a "typing" animation while waiting for the backend
//   3. POST the full conversation history to /explore/chat
//   4. Display the AI's reply; remove the typing animation
//   5. If the reply mentions certain keywords, show a tool recommendations panel
//
// The full conversation history is passed with each request so Gemini has context.
// (LLMs are stateless — each API call is independent, so we send everything.)
//
// RECS is a static list of ADHD-friendly tools. If the AI's reply mentions
// anything tool-related, we surface 3 random picks from this list below the chat.
// =============================================================================

import api from "../utils/api.js";
import { getState, setState, buildTaskSummary } from "../utils/state.js";

// Static list of ADHD-friendly tool recommendations.
// These are shown client-side when the AI mentions tools/apps.
// They never come from the backend — this keeps the response fast and avoids
// the AI having to "know" which tools to recommend.
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

// ——— INIT ———

// Wire up the input field and quick-prompt pills.
// Quick pills pre-fill the input with a common question and immediately send it —
// useful for users who don't know what to ask ("What should I do first?")
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

// ——— CHAT BUBBLE BUILDER ———

// Appends a new chat message bubble to the conversation.
// role = "user" → right-aligned "Me" bubble
// role = "ai"   → left-aligned "FF" bubble
// We replace \n with <br> so the AI's line breaks render as HTML line breaks.
//
// requestAnimationFrame waits one browser paint cycle before scrolling —
// without it, scrollHeight might not yet include the newly added bubble,
// causing the scroll to fall short.
function appendMsg(content, role) {
  const msgs = document.getElementById("chat-messages");
  const div = document.createElement("div");
  div.className = `chat-msg ${role} fade-in`;
  div.innerHTML = `
    <div class="chat-avatar ${role}">${role === "ai" ? "FF" : "Me"}</div>
    <div class="chat-bubble">${content.replace(/\n/g, "<br>")}</div>`;
  msgs.appendChild(div);
  requestAnimationFrame(() => { msgs.scrollTop = msgs.scrollHeight; });
}

// ——— TYPING INDICATOR ———

// Shows the animated "..." bubble while waiting for the AI to respond.
// Uses a fixed id="typing-indicator" so removeTyping() can find and delete it.
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

// Removes the typing indicator once the AI reply arrives.
// The ?. (optional chaining) prevents an error if the element doesn't exist.
function removeTyping() {
  document.getElementById("typing-indicator")?.remove();
}

// ——— TOOL RECOMMENDATIONS ———

// If the AI mentions tools or specific app names, show 3 random picks from RECS.
// This is a simple keyword regex match — intentionally crude but works well enough.
// The cards are shown below the chat, not injected into the AI's message.
function maybeShowRecs(text) {
  if (/app|tool|recommend|forest|todoist|notion|headspace|timer|pomodoro/i.test(text)) {
    const section = document.getElementById("recs-section");
    const cards = document.getElementById("rec-cards");
    // Pick 3 random tools by shuffling the array and slicing
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

// ——— SEND MESSAGE ———

// The main send flow:
//   1. Read and clear the input
//   2. Display the user's message bubble
//   3. Append to chatHistory in state (so future sends include this message)
//   4. Show typing animation
//   5. POST to the backend with the full recent conversation
//   6. Display the AI reply; update chatHistory; maybe show tool recs
//
// We send buildTaskSummary() as context so Gemini knows the user's situation
// without needing the user to explain it manually every session.
//
// We send newHistory.slice(-12) because Gemini has a token limit — older messages
// are dropped from the payload but still stored locally in chatHistory.
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
    // api.chat sends the last 12 messages + task summary to the backend
    const data = await api.chat(user.id, newHistory.slice(-12), buildTaskSummary());
    removeTyping();
    appendMsg(data.reply, "ai");
    setState({ chatHistory: [...newHistory, { role: "assistant", content: data.reply }] });
    maybeShowRecs(data.reply);   // check if the reply warrants showing tool cards
  } catch (e) {
    removeTyping();
    appendMsg("Couldn't reach the AI coach right now. Check your backend is running.", "ai");
    console.error(e);
  }
}
