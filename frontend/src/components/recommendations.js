import { getState, setState } from "../utils/state.js";
import { BASE_URL } from "../utils/api.js";

// ── State ────────────────────────────────────────────────────────────────────
let graphData   = { nodes: [], links: [] };
let d3Sim       = null;
let currentView = "graph";   // "graph" | "recs" | "stats"

// ── Genre colours ─────────────────────────────────────────────────────────────
const GENRE_COLOR = {
  "Pop":         "#f472b6",
  "Rock":        "#ef4444",
  "Electronic":  "#22d3ee",
  "Hip-Hop":     "#a78bfa",
  "R&B":         "#fb923c",
  "Indie":       "#4ade80",
  "Jazz":        "#fbbf24",
  "Metal":       "#94a3b8",
  "Classical":   "#e2e8f0",
  "Country":     "#d97706",
  "Latin":       "#f43f5e",
  "K-Pop":       "#e879f9",
  "Folk":        "#a3e635",
  "Blues":       "#60a5fa",
  "Alternative": "#f87171",
  "Soul":        "#fdba74",
  "Funk":        "#86efac",
  "Ambient":     "#7dd3fc",
};
const NODE_COLOR = {
  user:        "#00D4FF",
  genre:       "#1E1E36",
  recommended: "#111120",
};
function nodeColor(n) {
  if (n.type === "artist") return GENRE_COLOR[n.genre] || "#5c5c72";
  return NODE_COLOR[n.type] || "#5c5c72";
}

// ── Init ─────────────────────────────────────────────────────────────────────
export function initRecommendations() {
  renderShell();
  bindNav();
}

function renderShell() {
  const panel = document.getElementById("panel-recommendations");
  if (!panel) return;
  panel.innerHTML = `
    <div class="rec-header">
      <div class="rec-nav">
        <button class="rec-nav-btn active" data-view="graph">Graph</button>
        <button class="rec-nav-btn" data-view="recs">For You</button>
        <button class="rec-nav-btn" data-view="stats">Your Stats</button>
      </div>
      <button class="btn btn-primary btn-sm" id="btn-log-listen">+ Log a listen</button>
    </div>

    <div id="rec-view-graph" class="rec-view active">
      <div id="graph-empty" class="graph-empty" style="display:none">
        <p>Your graph is empty.</p>
        <button class="btn btn-primary" id="btn-start-onboard">Set up your taste →</button>
      </div>
      <svg id="kg-svg"></svg>
      <div id="graph-legend" class="graph-legend"></div>
      <div id="node-tooltip" class="node-tooltip" style="display:none"></div>
    </div>

    <div id="rec-view-recs" class="rec-view">
      <div id="rec-cards-container"></div>
    </div>

    <div id="rec-view-stats" class="rec-view">
      <div id="stats-container"></div>
    </div>
  `;
}

function bindNav() {
  const panel = document.getElementById("panel-recommendations");
  if (!panel) return;

  panel.addEventListener("click", async (e) => {
    const navBtn = e.target.closest(".rec-nav-btn");
    if (navBtn) {
      switchView(navBtn.dataset.view);
      return;
    }
    if (e.target.id === "btn-log-listen")   { openLogModal(); return; }
    if (e.target.id === "btn-start-onboard"){ openOnboarding(); return; }
  });
}

function switchView(view) {
  currentView = view;
  document.querySelectorAll(".rec-nav-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.view === view)
  );
  document.querySelectorAll(".rec-view").forEach(v =>
    v.classList.toggle("active", v.id === `rec-view-${view}`)
  );
  if (view === "graph") loadGraph();
  if (view === "recs")  loadRecs();
  if (view === "stats") loadStats();
}

// Called when user navigates to the Recommendations tab
export async function onRecommendationsEnter() {
  const { user } = getState();
  if (!user) return;
  if (currentView === "graph") await loadGraph();
}

// ── Graph ─────────────────────────────────────────────────────────────────────
async function loadGraph() {
  const { user } = getState();
  if (!user) return;
  try {
    const res  = await fetch(`${BASE_URL}/music/${user.id}/graph`);
    graphData  = await res.json();
    if (!graphData.nodes || graphData.nodes.length <= 1) {
      document.getElementById("graph-empty").style.display = "flex";
      document.getElementById("kg-svg").style.display = "none";
      document.getElementById("graph-legend").style.display = "none";
    } else {
      document.getElementById("graph-empty").style.display = "none";
      document.getElementById("kg-svg").style.display = "block";
      document.getElementById("graph-legend").style.display = "flex";
      renderD3Graph(graphData);
      renderLegend();
    }
  } catch (e) { console.error("Graph load failed", e); }
}

function renderD3Graph(data) {
  const svg = document.getElementById("kg-svg");
  if (!svg || !window.d3) return;

  const W = svg.clientWidth  || svg.parentElement.clientWidth  || 700;
  const H = svg.clientHeight || 480;

  // clear previous
  const d3svg = d3.select("#kg-svg").attr("viewBox", `0 0 ${W} ${H}`);
  d3svg.selectAll("*").remove();

  // deep-copy nodes so D3 can mutate (position, velocity)
  const nodes = data.nodes.map(n => ({ ...n }));
  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
  const links = data.links
    .filter(l => nodeById[l.source] && nodeById[l.target])
    .map(l => ({ ...l, source: nodeById[l.source], target: nodeById[l.target] }));

  // defs for arrow markers
  const defs = d3svg.append("defs");
  defs.append("marker").attr("id","arrow").attr("viewBox","0 -5 10 10")
    .attr("refX",14).attr("refY",0).attr("markerWidth",6).attr("markerHeight",6)
    .attr("orient","auto")
    .append("path").attr("d","M0,-5L10,0L0,5").attr("fill","#3a3a46");

  const g = d3svg.append("g");

  // zoom
  d3svg.call(d3.zoom().scaleExtent([0.3, 4]).on("zoom", e => g.attr("transform", e.transform)));

  // links
  const link = g.append("g").selectAll("line").data(links).join("line")
    .attr("class",  d => `kg-link kg-link-${d.type}`)
    .attr("stroke-width", d => d.type === "played" ? Math.max(1, d.weight) : 0.8)
    .attr("marker-end", d => d.type === "similar" ? "url(#arrow)" : null);

  // nodes
  const node = g.append("g").selectAll("g").data(nodes).join("g")
    .attr("class", "kg-node-g")
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on("drag",  (e, d) => { d.fx=e.x; d.fy=e.y; })
      .on("end",   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; })
    );

  node.append("circle")
    .attr("r",    d => d.size || 8)
    .attr("fill", d => nodeColor(d))
    .attr("class", d => `kg-node kg-node-${d.type}`);

  node.append("text")
    .attr("dy", d => (d.size || 8) + 11)
    .attr("text-anchor","middle")
    .attr("class", d => `kg-label kg-label-${d.type}`)
    .text(d => d.label);

  // tooltip
  node.on("mouseenter", (e, d) => {
    const tip = document.getElementById("node-tooltip");
    if (!tip) return;
    let html = `<strong>${d.label}</strong>`;
    if (d.type === "artist") html += `<br>${(d.genre || "")}${d.play_count ? ` · ${d.play_count} plays` : ""}`;
    if (d.type === "recommended") html += `<br><em>Recommended for you</em>`;
    if (d.type === "genre") html += `<br>Genre`;
    tip.innerHTML = html;
    tip.style.display = "block";
    tip.style.left = (e.clientX + 12) + "px";
    tip.style.top  = (e.clientY - 20) + "px";
  }).on("mouseleave", () => {
    const tip = document.getElementById("node-tooltip");
    if (tip) tip.style.display = "none";
  });

  // force simulation
  if (d3Sim) d3Sim.stop();
  d3Sim = d3.forceSimulation(nodes)
    .force("link",   d3.forceLink(links).id(d => d.id).distance(d => d.type === "genre" ? 60 : 120).strength(0.5))
    .force("charge", d3.forceManyBody().strength(-250))
    .force("center", d3.forceCenter(W / 2, H / 2))
    .force("collision", d3.forceCollide(d => (d.size || 8) + 8))
    .on("tick", () => {
      link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
          .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

  const sim = d3Sim;
}

function renderLegend() {
  const el = document.getElementById("graph-legend");
  if (!el) return;
  el.innerHTML = [
    { color: "#00D4FF",  label: "You" },
    { color: "#4ade80",  label: "Artist (played)" },
    { color: "#111120",  label: "Recommended" },
    { color: "#1E1E36",  label: "Genre" },
  ].map(i => `<span class="legend-item"><span class="legend-dot" style="background:${i.color};border:1px solid #2E2E50"></span>${i.label}</span>`).join("");
}

// ── Recommendations ───────────────────────────────────────────────────────────
async function loadRecs() {
  const { user } = getState();
  if (!user) return;
  const box = document.getElementById("rec-cards-container");
  box.innerHTML = `<div class="rec-loading">Loading recommendations…</div>`;
  try {
    const res  = await fetch(`${BASE_URL}/music/${user.id}/recommendations`);
    const recs = await res.json();
    if (!recs.length) {
      box.innerHTML = `<div class="rec-empty">
        <p>No recommendations yet. Log some listens first, or <button class="link-btn" id="btn-onboard-from-recs">set up your taste</button>.</p>
      </div>`;
      document.getElementById("btn-onboard-from-recs")?.addEventListener("click", openOnboarding);
      return;
    }
    box.innerHTML = `<div class="rec-sq-grid">${recs.map(r => {
      const color = GENRE_COLOR[r.genres[0]] || '#5c5c72';
      return `
        <div class="rec-sq-card">
          <div class="rec-sq-strip" style="background:${color}"></div>
          <div class="rec-sq-body">
            <div class="rec-sq-genre">${escHtml(r.genres[0] || 'Music')}</div>
            <div class="rec-sq-name">${escHtml(r.artist_name)}</div>
            <div class="rec-sq-reason">${escHtml(r.reason)}</div>
          </div>
          <div class="rec-sq-foot">
            <div class="rec-sq-tags">${r.genres.slice(0,3).join(' · ')}</div>
            <button class="btn btn-ghost btn-sm rec-log-btn" data-artist="${escHtml(r.artist_name)}">+ Log</button>
          </div>
        </div>
      `;
    }).join("")}</div>`;

    box.querySelectorAll(".rec-log-btn").forEach(btn =>
      btn.addEventListener("click", () => openLogModal(btn.dataset.artist))
    );
  } catch (e) { box.innerHTML = `<div class="rec-empty">Could not load recommendations.</div>`; }
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  const { user } = getState();
  if (!user) return;
  const box = document.getElementById("stats-container");
  box.innerHTML = `<div class="rec-loading">Loading…</div>`;
  try {
    const res  = await fetch(`${BASE_URL}/music/${user.id}/stats`);
    const data = await res.json();
    const { top_artists, top_songs } = data;

    box.innerHTML = `
      <div class="stats-grid">
        <div class="stats-section">
          <div class="stats-title">Top Artists</div>
          ${top_artists.length ? top_artists.map(a => `
            <div class="stats-row">
              <div class="stats-dot" style="background:${GENRE_COLOR[a.genres?.[0]] || '#5c5c72'}"></div>
              <span class="stats-name">${escHtml(a.name)}</span>
              <span class="stats-count">${a.play_count} plays</span>
            </div>`).join("") : `<div class="stats-empty">No artists logged yet.</div>`}
        </div>
        <div class="stats-section">
          <div class="stats-title">Top Songs</div>
          ${top_songs.length ? top_songs.map(s => `
            <div class="stats-row">
              <div class="stats-dot" style="background:#5c5c72"></div>
              <span class="stats-name">${escHtml(s.name)}</span>
              <span class="stats-sub">${escHtml(s.artist)}</span>
              <span class="stats-count">${s.play_count} plays</span>
            </div>`).join("") : `<div class="stats-empty">No songs logged yet.</div>`}
        </div>
      </div>`;
  } catch (e) { box.innerHTML = `<div class="rec-empty">Could not load stats.</div>`; }
}

// ── Log a listen modal ────────────────────────────────────────────────────────
function openLogModal(prefillArtist = "") {
  const existing = document.getElementById("log-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "log-modal";
  modal.className = "modal-overlay";
  modal.innerHTML = `
    <div class="modal-box log-modal-box">
      <div class="modal-header">
        <div class="modal-title">Log a listen</div>
        <button class="modal-close" id="log-modal-close">✕</button>
      </div>
      <div class="log-search-row">
        <input type="text" id="log-search-input" class="log-search-input"
          placeholder="Search song or artist…" autocomplete="off"
          value="${escHtml(prefillArtist)}">
        <button class="btn btn-primary btn-sm" id="log-search-btn">Search</button>
      </div>
      <div id="log-search-results" class="log-search-results"></div>
      <div id="log-selected" class="log-selected" style="display:none">
        <div id="log-selected-info" class="log-selected-info"></div>
        <button class="btn btn-primary" id="log-confirm-btn">Log this listen ✓</button>
      </div>
    </div>`;
  document.body.appendChild(modal);

  let selectedSong = null;

  const close = () => modal.remove();
  modal.addEventListener("click", e => { if (e.target === modal) close(); });
  document.getElementById("log-modal-close").addEventListener("click", close);

  const input   = document.getElementById("log-search-input");
  const results = document.getElementById("log-search-results");
  const selected = document.getElementById("log-selected");
  const selInfo  = document.getElementById("log-selected-info");

  async function doSearch() {
    const q = input.value.trim();
    if (!q) return;
    results.innerHTML = `<div class="log-searching">Searching MusicBrainz…</div>`;
    selected.style.display = "none";
    try {
      const res  = await fetch(`${BASE_URL}/music/search?q=${encodeURIComponent(q)}`);
      const hits = await res.json();
      if (!hits.length) { results.innerHTML = `<div class="log-no-results">No results found. Try a different query.</div>`; return; }
      results.innerHTML = hits.map((h, i) => `
        <div class="log-result-row" data-idx="${i}">
          <div class="log-result-name">${escHtml(h.name)}</div>
          <div class="log-result-meta">${escHtml(h.artist_name)}${h.year ? ` · ${h.year}` : ""}</div>
        </div>`).join("");
      const hitData = hits;
      results.querySelectorAll(".log-result-row").forEach(row => {
        row.addEventListener("click", () => {
          results.querySelectorAll(".log-result-row").forEach(r => r.classList.remove("selected"));
          row.classList.add("selected");
          selectedSong = hitData[parseInt(row.dataset.idx)];
          selInfo.innerHTML = `<strong>${escHtml(selectedSong.name)}</strong> by ${escHtml(selectedSong.artist_name)}${selectedSong.year ? ` (${selectedSong.year})` : ""}`;
          selected.style.display = "flex";
        });
      });
    } catch (e) { results.innerHTML = `<div class="log-no-results">Search failed. Is the backend running?</div>`; }
  }

  document.getElementById("log-search-btn").addEventListener("click", doSearch);
  input.addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });

  document.getElementById("log-confirm-btn").addEventListener("click", async () => {
    if (!selectedSong) return;
    const { user } = getState();
    if (!user) return;
    try {
      await fetch(`${BASE_URL}/music/${user.id}/play`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          song_name:   selectedSong.name,
          artist_name: selectedSong.artist_name,
          year:        selectedSong.year || null,
          genres:      [],
          mbid:        selectedSong.mbid || null,
        }),
      });
      close();
      // refresh current view
      if (currentView === "graph")  loadGraph();
      if (currentView === "recs")   loadRecs();
      if (currentView === "stats")  loadStats();
    } catch (e) { alert("Could not log listen. Is the backend running?"); }
  });

  if (prefillArtist) doSearch();
  input.focus();
}

// ── Onboarding ────────────────────────────────────────────────────────────────
async function openOnboarding() {
  const existing = document.getElementById("onboard-modal");
  if (existing) existing.remove();

  // fetch seed data
  let seedByGenre = {};
  try {
    const res = await fetch(`${BASE_URL}/music/seed-artists`);
    seedByGenre = await res.json();
  } catch (e) { alert("Could not load artist list."); return; }

  const genres = Object.keys(seedByGenre);
  let selectedGenres  = new Set();
  let selectedArtists = new Set();
  let step = 1;   // 1 = genres, 2 = artists

  const modal = document.createElement("div");
  modal.id = "onboard-modal";
  modal.className = "modal-overlay";
  document.body.appendChild(modal);

  function renderStep1() {
    modal.innerHTML = `
      <div class="modal-box onboard-box">
        <div class="onboard-header">
          <div class="onboard-title">What genres do you love?</div>
          <div class="onboard-sub">Pick everything that resonates. You can always add more later.</div>
        </div>
        <div class="genre-grid">
          ${genres.map(g => `
            <button class="genre-chip ${selectedGenres.has(g) ? "selected" : ""}" data-genre="${escHtml(g)}"
              style="--chip-color:${GENRE_COLOR[g] || "#5c5c72"}">
              ${escHtml(g)}
            </button>`).join("")}
        </div>
        <div class="onboard-footer">
          <span class="onboard-hint">${selectedGenres.size} selected</span>
          <button class="btn btn-primary" id="onboard-next" ${selectedGenres.size === 0 ? "disabled" : ""}>
            Next: Pick artists →
          </button>
        </div>
      </div>`;

    modal.querySelectorAll(".genre-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const g = chip.dataset.genre;
        selectedGenres.has(g) ? selectedGenres.delete(g) : selectedGenres.add(g);
        renderStep1();
      });
    });
    document.getElementById("onboard-next")?.addEventListener("click", () => { step = 2; renderStep2(); });
  }

  function renderStep2() {
    const relevantGenres = [...selectedGenres];
    const artistPool = [...new Set(
      relevantGenres.flatMap(g => seedByGenre[g] || [])
    )];

    modal.innerHTML = `
      <div class="modal-box onboard-box">
        <div class="onboard-header">
          <div class="onboard-title">Pick artists you already love</div>
          <div class="onboard-sub">These seed your taste graph. Select as many as you like.</div>
        </div>
        <div class="artist-grid">
          ${artistPool.map(a => `
            <button class="artist-chip ${selectedArtists.has(a) ? "selected" : ""}"
              data-artist="${escHtml(a)}">${escHtml(a)}</button>`).join("")}
        </div>
        <div class="onboard-footer">
          <button class="btn btn-ghost" id="onboard-back">← Back</button>
          <span class="onboard-hint">${selectedArtists.size} selected</span>
          <button class="btn btn-primary" id="onboard-done" ${selectedArtists.size === 0 ? "disabled" : ""}>
            Build my graph →
          </button>
        </div>
      </div>`;

    modal.querySelectorAll(".artist-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const a = chip.dataset.artist;
        selectedArtists.has(a) ? selectedArtists.delete(a) : selectedArtists.add(a);
        renderStep2();
      });
    });
    document.getElementById("onboard-back")?.addEventListener("click", () => { step = 1; renderStep1(); });
    document.getElementById("onboard-done")?.addEventListener("click", async () => {
      const { user } = getState();
      if (!user) return;
      await fetch(`${BASE_URL}/music/${user.id}/preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artist_names: [...selectedArtists] }),
      });
      modal.remove();
      await loadGraph();
      switchView("graph");
    });
  }

  renderStep1();
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
