const POLL_MS = 2000;
const COLORS = {
  accent: "#22d3ee",
  warn: "#fbbf24",
  cold: "#64748b",
  series: ["#22d3ee", "#fbbf24", "#34d399", "#a78bfa", "#f472b6"],
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function renderStats(summary) {
  const root = document.getElementById("stats");
  root.innerHTML = "";
  const items = [
    { label: "Repos tracked", value: summary.repos, cls: "" },
    { label: "Sessions today", value: `${summary.sessions_today} (${summary.sessions_total} all-time)`, cls: "" },
    { label: "Avg compression", value: `${Math.round(summary.avg_compression * 100)}%`, cls: "ok" },
    {
      label: "Semantic pending",
      value: summary.semantic_pending,
      cls: summary.semantic_pending ? "warn" : "ok",
    },
  ];
  for (const item of items) {
    const box = el("div", `stat ${item.cls}`);
    box.appendChild(el("div", "value", String(item.value)));
    box.appendChild(el("div", "label", item.label));
    root.appendChild(box);
  }
}

function layoutOrbs(repos) {
  const n = repos.length || 1;
  return repos.map((repo, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const dist = 55 + (i % 3) * 18;
    const cx = 160 + Math.cos(angle) * dist;
    const cy = 110 + Math.sin(angle) * dist * 0.65;
    const r = Math.max(14, Math.min(42, 12 + Math.sqrt(repo.sessions_total) * 3));
    return { repo, cx, cy, r };
  });
}

function renderConstellation(repos) {
  const svg = document.getElementById("constellation");
  svg.innerHTML = "";
  document.getElementById("repo-count").textContent = `${repos.length} repos`;

  for (let row = 0; row < 8; row++) {
    for (let col = 0; col < 12; col++) {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", String(20 + col * 26));
      dot.setAttribute("cy", String(18 + row * 26));
      dot.setAttribute("r", "1");
      dot.setAttribute("fill", "#2a3548");
      dot.setAttribute("opacity", "0.5");
      svg.appendChild(dot);
    }
  }

  const orbs = layoutOrbs(repos);
  if (orbs.length > 1) {
    for (let i = 0; i < orbs.length - 1; i++) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(orbs[i].cx));
      line.setAttribute("y1", String(orbs[i].cy));
      line.setAttribute("x2", String(orbs[Math.min(i + 1, orbs.length - 1)].cx));
      line.setAttribute("y2", String(orbs[Math.min(i + 1, orbs.length - 1)].cy));
      line.setAttribute("stroke", "#2a3548");
      line.setAttribute("stroke-width", "1");
      if (orbs[i].repo.active_now) line.setAttribute("stroke-dasharray", "4 4");
      svg.appendChild(line);
    }
  }

  for (const { repo, cx, cy, r } of orbs) {
    const stroke = repo.active_now ? COLORS.accent : repo.pending_semantic ? COLORS.warn : COLORS.cold;
    if (repo.active_now) {
      const ring = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      ring.setAttribute("cx", String(cx));
      ring.setAttribute("cy", String(cy));
      ring.setAttribute("r", String(r + 6));
      ring.setAttribute("fill", "none");
      ring.setAttribute("stroke", COLORS.accent);
      ring.setAttribute("stroke-width", "2");
      ring.setAttribute("opacity", "0.6");
      svg.appendChild(ring);
    }
    const fill = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    fill.setAttribute("cx", String(cx));
    fill.setAttribute("cy", String(cy));
    fill.setAttribute("r", String(r));
    fill.setAttribute("fill", stroke);
    fill.setAttribute("fill-opacity", repo.active_now ? "0.35" : "0.2");
    fill.setAttribute("stroke", stroke);
    fill.setAttribute("stroke-width", "1.5");
    svg.appendChild(fill);

    const count = document.createElementNS("http://www.w3.org/2000/svg", "text");
    count.setAttribute("x", String(cx));
    count.setAttribute("y", String(cy + 4));
    count.setAttribute("text-anchor", "middle");
    count.setAttribute("fill", "#e8ecf4");
    count.setAttribute("font-size", "10");
    count.setAttribute("font-weight", "600");
    count.textContent = String(repo.sessions_total);
    svg.appendChild(count);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(cx));
    label.setAttribute("y", String(cy + r + 14));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("fill", "#8b95a8");
    label.setAttribute("font-size", "9");
    label.textContent = repo.label.slice(0, 14);
    svg.appendChild(label);
  }
}

function drawLineChart(canvas, categories, seriesMap) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth * 2;
  const h = canvas.height = canvas.clientHeight * 2;
  ctx.scale(2, 2);
  const cw = w / 2;
  const ch = h / 2;
  ctx.clearRect(0, 0, cw, ch);

  const names = Object.keys(seriesMap);
  const maxVal = Math.max(1, ...names.flatMap((n) => seriesMap[n]));
  const pad = { l: 28, r: 8, t: 8, b: 24 };
  const plotW = cw - pad.l - pad.r;
  const plotH = ch - pad.t - pad.b;

  ctx.strokeStyle = "#2a3548";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, pad.t + plotH);
  ctx.lineTo(pad.l + plotW, pad.t + plotH);
  ctx.stroke();

  names.forEach((name, si) => {
    const data = seriesMap[name];
    const color = COLORS.series[si % COLORS.series.length];
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((v, i) => {
      const x = pad.l + (i / Math.max(categories.length - 1, 1)) * plotW;
      const y = pad.t + plotH - (v / maxVal) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  ctx.fillStyle = "#8b95a8";
  ctx.font = "9px system-ui";
  ctx.fillText("sessions", 2, pad.t + 8);
}

function drawBarChart(canvas, repos) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.clientWidth * 2;
  const h = canvas.height = canvas.clientHeight * 2;
  ctx.scale(2, 2);
  const cw = w / 2;
  const ch = h / 2;
  ctx.clearRect(0, 0, cw, ch);

  const pad = { l: 32, r: 8, t: 8, b: 28 };
  const plotW = cw - pad.l - pad.r;
  const plotH = ch - pad.t - pad.b;
  const n = Math.max(repos.length, 1);
  const barW = plotW / n - 6;

  repos.forEach((repo, i) => {
    const pct = Math.round(repo.compression_rate * 100);
    const x = pad.l + i * (plotW / n) + 3;
    const barH = (pct / 100) * plotH;
    const y = pad.t + plotH - barH;
    ctx.fillStyle = COLORS.accent;
    ctx.fillRect(x, y, barW, barH);
    ctx.fillStyle = "#8b95a8";
    ctx.font = "8px system-ui";
    ctx.save();
    ctx.translate(x + barW / 2, pad.t + plotH + 10);
    ctx.rotate(-0.4);
    ctx.fillText(repo.label.slice(0, 10), -16, 0);
    ctx.restore();
  });

  ctx.fillStyle = "#8b95a8";
  ctx.font = "9px system-ui";
  ctx.fillText("% saved", 2, pad.t + 8);
}

function renderSemantic(events) {
  const root = document.getElementById("semantic-log");
  root.innerHTML = "";
  if (!events.length) {
    root.appendChild(el("p", "tele-detail", "No semantic runs recorded yet."));
    return;
  }
  for (const ev of events) {
    const row = el("div", "event-row");
    const meta = el("div", "event-meta");
    meta.appendChild(el("span", "pill info", ev.mode));
    meta.appendChild(document.createTextNode(ev.repo));
    meta.appendChild(el("span", "tele-detail", ev.time));
    meta.appendChild(el("span", "tele-detail", `${ev.before_lines} → ${ev.after_lines} lines`));
    row.appendChild(meta);
    if (ev.detail) row.appendChild(el("div", "tele-detail", ev.detail));
    root.appendChild(row);
  }
}

function renderTiers(repos) {
  const root = document.getElementById("tier-usage");
  root.innerHTML = "";
  for (const repo of repos.slice(0, 5)) {
    const total = repo.hot_bytes + repo.warm_bytes + repo.cold_bytes || 1;
    const row = el("div", "tier-row");
    const head = el("div", "tier-head");
    head.appendChild(el("span", "", repo.label));
    head.appendChild(el("span", "pill ok", `${Math.round(repo.compression_rate * 100)}%`));
    row.appendChild(head);
    const track = el("div", "bar-track");
    for (const [cls, val] of [
      ["hot", repo.hot_bytes],
      ["warm", repo.warm_bytes],
      ["cold", repo.cold_bytes],
    ]) {
      const seg = el("div", `bar-seg ${cls}`);
      seg.style.width = `${(val / total) * 100}%`;
      track.appendChild(seg);
    }
    row.appendChild(track);
    root.appendChild(row);
  }
}

function renderTable(repos) {
  const tbody = document.getElementById("repo-table");
  tbody.innerHTML = "";
  for (const repo of repos) {
    const tr = document.createElement("tr");
    const sem = el("span", `pill ${repo.pending_semantic ? "warn" : repo.semantic_enabled === "off" ? "" : "ok"}`, repo.semantic_enabled);
    tr.innerHTML = `
      <td>${repo.active_now ? "● " : ""}${repo.label}</td>
      <td>${repo.sessions_today} today / ${repo.sessions_total}</td>
      <td></td>
      <td>${repo.last_change || "—"}</td>
      <td>${repo.recent_context || "—"}</td>
    `;
    tr.children[2].appendChild(sem);
    tbody.appendChild(tr);
  }
}

function renderTelemetry(events) {
  const root = document.getElementById("telemetry");
  root.innerHTML = "";
  for (const ev of events) {
    const row = el("div", "tele-row");
    const code = document.createElement("code");
    code.textContent = ev.time;
    row.appendChild(code);
    row.appendChild(el("span", "pill", ev.repo.split("-")[0]));
    const tone = ev.event.includes("pending") ? "warn" : ev.event.includes("session") ? "info" : "ok";
    row.appendChild(el("span", `pill ${tone}`, ev.event));
    row.appendChild(el("span", "tele-detail", ev.detail));
    root.appendChild(row);
  }
}

function render(data) {
  renderStats(data.summary);
  renderConstellation(data.repos);
  drawLineChart(
    document.getElementById("sessions-chart"),
    data.sessions_by_day.categories,
    data.sessions_by_day.series,
  );
  drawBarChart(document.getElementById("compression-chart"), data.repos);
  document.getElementById("sessions-caption").textContent =
    `Session count · ${data.sessions_by_day.categories.join(", ")} · scanned ${data.scanned_at}`;
  renderSemantic(data.semantic_events);
  renderTiers(data.repos);
  renderTable(data.repos);
  renderTelemetry(data.telemetry);
  document.getElementById("footer").textContent =
    `Roots: ${data.roots.join(" · ")} · refresh every ${POLL_MS / 1000}s`;
}

async function poll() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) throw new Error(await res.text());
    render(await res.json());
    document.getElementById("live-badge").textContent = "live";
  } catch (err) {
    document.getElementById("live-badge").textContent = "offline";
    document.getElementById("subtitle").textContent = String(err);
  }
}

poll();
setInterval(poll, POLL_MS);
