// api/index.js
//
// Self-hosted "pinned projects" card grid, in the same spirit as
// self-hosted github-readme-stats: this is a Vercel serverless
// function that hits the GitHub API live on every request and renders
// an SVG, rather than a static asset -- so new commits/stars/topics
// on the underlying repos show up on next page view, no rebuild step.
//
// GET /api?repos=owner/name,owner/name&theme=dark|light
//
// Auth: reads GH_TOKEN from the environment (same PAT-in-env-var
// pattern as the github-readme-stats deploy). Works without it too --
// falls back to GitHub's 60 req/hr unauthenticated limit -- but two
// calls per repo (details + languages) will exhaust that fast on any
// real traffic, so setting GH_TOKEN is the difference between "works"
// and "works reliably."

const CARD_W = 380;
const CARD_H = 172;
const GAP = 18;
const COLS = 2;
const PAD = 4;

const THEMES = {
  dark: {
    bg: "#0A101F", card: "#0D1526", cardEnd: "#0A0F1D", border: "#22D3EE33",
    title: "#E7ECFB", desc: "#9AA4C0", chrome: "#22D3EE",
    accent: "#10B981", tagBg: "#A78BFA26", tagText: "#A78BFA",
    ring_track: "#1E2740",
    // rank palette: 1st/2nd/3rd language by share, NOT tied to which
    // language it actually is -- every card cycles the same three
    // profile-palette hues so the grid reads as one cohesive system
    // instead of a scatter of each language's own (clashing) brand
    // colour. Matches the reference profile's card style.
    rank: ["#A78BFA", "#22D3EE", "#10B981"],
  },
  light: {
    bg: "#FFFFFF", card: "#F3F1FC", cardEnd: "#ECE9FA", border: "#0891B233",
    title: "#1E2433", desc: "#5B6478", chrome: "#0891B2",
    accent: "#10B981", tagBg: "#7C3AED26", tagText: "#7C3AED",
    ring_track: "#E2E6F0",
    rank: ["#7C3AED", "#0891B2", "#10B981"],
  },
};

// Icons keyed to each repo's actual dominant language rather than a
// hand-drawn metaphor for what the project does -- only two real
// languages show up as the top slot across these six repos, so this
// only needs two real logo renders plus a generic fallback.
const ICON_TS = {
  type: "ts", color: "#3178C6",
};
const ICON_PY = {
  // simplified two-tone recreation of the Python mark: two interlocked
  // rounded bodies (blue on top, yellow on bottom) each with an "eye".
  type: "py", colorTop: "#3776AB", colorBottom: "#FFD43B",
  dTop: "M14,3 C10,3 8,4.5 8,7 L8,11 L16,11 L16,12.5 L6.5,12.5 C4.5,12.5 3,14.5 3,17.5 C3,20.5 4.5,22 6.5,22 L9,22 L9,19 C9,16.5 10.5,15 13,15 L18,15 C20.5,15 22,13.3 22,11 L22,7 C22,4.5 19,3 14,3 Z",
  dBottom: "M14,25 C18,25 20,23.5 20,21 L20,17 L12,17 L12,15.5 L21.5,15.5 C23.5,15.5 25,13.5 25,10.5 C25,7.5 23.5,6 21.5,6 L19,6 L19,9 C19,11.5 17.5,13 15,13 L10,13 C7.5,13 6,14.7 6,17 L6,21 C6,23.5 9,25 14,25 Z",
  eyeTop: [11, 6.3], eyeBottom: [17, 21.7],
};
const ICON_JUPYTER = {
  // simplified recreation of the Jupyter mark: a small core "planet"
  // with three elliptical orbits at 60deg apart, each carrying one
  // "moon" -- same idea as the real logo, without tracing its exact
  // (non-simple) bezier outlines.
  type: "jupyter", color: "#F37626",
};
const DEFAULT_ICON = { type: "path", color: "#8892B0", d: "M10,9 L5,14 L10,19 M18,9 L23,14 L18,19 M15,7 L13,21" };

const ICONS = {
  cucu: ICON_PY,
  amparo: ICON_JUPYTER,
  opera: ICON_TS,
  prodexa: ICON_TS,
  epsilon: ICON_PY,
  neuroroutine: ICON_TS,
};

function iconMarkup(icon) {
  if (icon.type === "ts") {
    return `<text x="14" y="19" text-anchor="middle" font-size="12" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${icon.color}">TS</text>`;
  }
  if (icon.type === "py") {
    return (
      `<path d="${icon.dTop}" fill="${icon.colorTop}"/>` +
      `<path d="${icon.dBottom}" fill="${icon.colorBottom}"/>` +
      `<circle cx="${icon.eyeTop[0]}" cy="${icon.eyeTop[1]}" r="0.9" fill="#0A101F"/>` +
      `<circle cx="${icon.eyeBottom[0]}" cy="${icon.eyeBottom[1]}" r="0.9" fill="#0A101F"/>`
    );
  }
  if (icon.type === "jupyter") {
    const orbits = [0, 60, 120]
      .map((deg) => {
        return `<g transform="rotate(${deg} 14 14)">
          <ellipse cx="14" cy="14" rx="11" ry="4" fill="none" stroke="${icon.color}" stroke-width="1.1" opacity=".85"/>
          <circle cx="24.5" cy="14" r="1.8" fill="${icon.color}"/>
        </g>`;
      })
      .join("");
    return `${orbits}<circle cx="14" cy="14" r="2.6" fill="${icon.color}"/>`;
  }
  return `<path d="${icon.d}" fill="none" stroke="${icon.color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`;
}

// Framework/database/tool keywords worth surfacing over generic topic
// words like "full-stack" or "manufacturing" -- checked (in this
// order) against a repo's topics, then its description text, since
// three of these six repos have no topics set at all but do name
// their stack in the description (e.g. opera: "Electron + React +
// TypeScript ... NestJS + Prisma + PostgreSQL").
const KNOWN_TECH = [
  ["nextjs", "Next.js"], ["next.js", "Next.js"], ["nestjs", "NestJS"], ["react", "React"],
  ["django-rest-framework", "DRF"], ["django", "Django"], ["flask", "Flask"], ["fastapi", "FastAPI"],
  ["electron", "Electron"], ["vite", "Vite"], ["tailwindcss", "Tailwind"], ["tailwind", "Tailwind"],
  ["zustand", "Zustand"], ["prisma", "Prisma"], ["postgresql", "PostgreSQL"], ["postgres", "PostgreSQL"],
  ["mongodb", "MongoDB"], ["supabase", "Supabase"], ["express", "Express"], ["nodejs", "Node.js"],
  ["node.js", "Node.js"], ["redis", "Redis"], ["rabbitmq", "RabbitMQ"], ["celery", "Celery"],
  ["nginx", "Nginx"], ["docker", "Docker"], ["playwright", "Playwright"], ["pytorch", "PyTorch"],
  ["tensorflow", "TensorFlow"], ["flutter", "Flutter"], ["firebase", "Firebase"],
];

function extractStack(topics, description) {
  const found = [];
  const seen = new Set();
  const add = (label) => {
    if (!seen.has(label)) {
      seen.add(label);
      found.push(label);
    }
  };
  const topicSet = new Set((topics || []).map((t) => t.toLowerCase()));
  for (const [key, label] of KNOWN_TECH) {
    if (topicSet.has(key)) add(label);
  }
  const desc = (description || "").toLowerCase();
  for (const [key, label] of KNOWN_TECH) {
    if (found.length >= 4) break;
    if (desc.includes(key)) add(label);
  }
  // fall back to filling remaining slots with the repo's own topics
  // (domain descriptors) if recognized stack keywords didn't fill it
  for (const t of topics || []) {
    if (found.length >= 3) break;
    add(t);
  }
  return found.slice(0, 3);
}

async function fetchJSON(url, token) {
  const headers = { "User-Agent": "project-cards", Accept: "application/vnd.github+json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.json();
}

function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86400000);
  if (days < 1) return "today";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

// naive word-wrap into at most `maxLines` lines of ~maxChars each
function wrap(text, maxChars, maxLines) {
  if (!text) return [];
  const words = text.split(/\s+/);
  const lines = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > maxChars) {
      lines.push(cur.trim());
      cur = w;
      if (lines.length === maxLines - 1) break;
    } else {
      cur = (cur + " " + w).trim();
    }
  }
  if (cur) lines.push(cur.trim());
  if (lines.length > maxLines) lines.length = maxLines;
  const consumed = lines.join(" ").length;
  if (consumed < text.length && lines.length === maxLines) {
    lines[maxLines - 1] = truncate(lines[maxLines - 1] + " ", maxChars - 1);
  }
  return lines;
}

function donut(cx, cy, r, allLangs, track, rankColors) {
  // One arc segment per language, each sized to its own share and
  // coloured by RANK (1st/2nd/3rd, cycling rankColors) rather than by
  // which language it actually is -- keeps every card on the same
  // three-hue system regardless of what it's written in.
  const stroke = 5;
  const circumference = 2 * Math.PI * r;
  const gapDeg = allLangs.length > 1 ? 2.2 : 0; // small visual gap between segments
  let cum = 0;
  const segments = allLangs
    .map(({ pct }, i) => {
      const color = rankColors[i % rankColors.length];
      const segFraction = Math.max(0, pct / 100 - gapDeg / 360);
      const dash = segFraction * circumference;
      const offset = -(cum / 100) * circumference;
      cum += pct;
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
        stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${circumference.toFixed(1)}"
        stroke-dashoffset="${offset.toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    })
    .join("");
  const topColor = rankColors[0];
  const topPct = Math.round(allLangs[0]?.pct || 0);
  // number set larger than its own "%" (a smaller, slightly raised
  // sibling glyph) reads as a stat/metric instead of a plain label --
  // common editorial-dashboard convention.
  const numW = String(topPct).length * 8.6;
  return `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${track}" stroke-width="${stroke}"/>
    ${segments}
    <text x="${(cx - numW / 2).toFixed(1)}" y="${cy + 5}" font-size="16" font-weight="700"
      font-family="ui-monospace,Consolas,monospace" fill="${topColor}">${topPct}</text>
    <text x="${(cx - numW / 2 + numW).toFixed(1)}" y="${cy + 1}" font-size="10" font-weight="600"
      font-family="ui-monospace,Consolas,monospace" fill="${topColor}" opacity=".8">%</text>
  `;
}

function starIcon(cx, cy, r, color) {
  const pts = [];
  for (let i = 0; i < 10; i++) {
    const ang = (Math.PI / 5) * i - Math.PI / 2;
    const rad = i % 2 === 0 ? r : r * 0.42;
    pts.push(`${(cx + rad * Math.cos(ang)).toFixed(1)},${(cy + rad * Math.sin(ang)).toFixed(1)}`);
  }
  return `<polygon points="${pts.join(" ")}" fill="${color}"/>`;
}

async function buildCard(repoFull, x, y, theme, token) {
  const [owner, name] = repoFull.split("/");
  const [details, langBytes] = await Promise.all([
    fetchJSON(`https://api.github.com/repos/${owner}/${name}`, token),
    fetchJSON(`https://api.github.com/repos/${owner}/${name}/languages`, token),
  ]);

  const totalBytes = Object.values(langBytes).reduce((a, b) => a + b, 0) || 1;
  const allLangs = Object.entries(langBytes)
    .map(([lang, bytes]) => ({ lang, pct: (bytes / totalBytes) * 100 }))
    .sort((a, b) => b.pct - a.pct);
  const descLines = wrap(details.description || "No description yet.", 40, 2);
  const tags = extractStack(details.topics, details.description);

  const icon = ICONS[name.toLowerCase()] || DEFAULT_ICON;
  const gid = `cardbg-${name.toLowerCase().replace(/[^a-z0-9]/g, "")}`;
  const topAccent = theme.rank[0];

  const clipId = `${gid}-clip`;
  let svg = `<g transform="translate(${x},${y})">`;
  svg += `<defs>
      <linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${theme.card}"/>
        <stop offset="100%" stop-color="${theme.cardEnd}"/>
      </linearGradient>
      <clipPath id="${clipId}"><rect width="${CARD_W}" height="${CARD_H}" rx="10"/></clipPath>
    </defs>`;
  svg += `<rect width="${CARD_W}" height="${CARD_H}" rx="10" fill="url(#${gid})" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<g clip-path="url(#${clipId})"><rect width="${CARD_W}" height="3" fill="${topAccent}"/></g>`;
  svg += `<line x1="20" y1="54" x2="${CARD_W - 20}" y2="54" stroke="${theme.border}" stroke-width="1"/>`;

  const iconBorder = icon.color || icon.colorTop;
  svg += `<rect x="20" y="16" width="28" height="28" rx="7" fill="${iconBorder}22" stroke="${iconBorder}" stroke-width="1.2"/>`;
  svg += `<g transform="translate(20,16)">${iconMarkup(icon)}</g>`;
  svg += `<text x="58" y="30" font-size="15" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.title}">${esc(truncate(name, 22))}</text>`;
  svg += `<text x="58" y="46" font-size="10" letter-spacing=".04em" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}" opacity=".5">${esc(owner)}/${esc(name)}</text>`;

  // Every block sits at a FIXED y, the same in all six cards, rather
  // than flowing from wherever the previous block happened to end --
  // that's what makes the grid read as aligned instead of each card
  // drifting to its own rhythm. The legend row still has to stay a
  // single fixed-height row (a 2nd row was overflowing into the tag
  // row on repos with 3+ languages), so instead of a fixed 2-language
  // cap that silently hid real languages, it packs as many as fit by
  // *measured* text width -- capped at 3 for guaranteed single-row
  // safety even in the extreme case -- and appends "+N" for whatever's
  // left, so a repo's actual full language count is never hidden
  // without a trace. The donut ring already reflected 100% of it; this
  // just makes the text legend stop quietly truncating at "top 2."
  descLines.forEach((line, i) => {
    svg += `<text x="24" y="${66 + i * 14}" font-size="12" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(line)}</text>`;
  });

  const langY = 100;
  const CHAR_W = 5.6;
  const shownLangs = allLangs.slice(0, 3);
  let lx = 24;
  shownLangs.forEach((l, i) => {
    const label = `${l.lang} ${l.pct.toFixed(0)}%`;
    const color = theme.rank[i % theme.rank.length];
    svg += `<circle cx="${lx}" cy="${langY - 4}" r="3.5" fill="${color}"/>`;
    svg += `<text x="${lx + 10}" y="${langY}" font-size="11" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(label)}</text>`;
    lx += 10 + label.length * CHAR_W + 14;
  });
  const hiddenLangCount = allLangs.length - shownLangs.length;
  if (hiddenLangCount > 0) {
    svg += `<text x="${lx}" y="${langY}" font-size="11" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}" opacity=".6">+${hiddenLangCount}</text>`;
  }

  const tagY = 128;
  let tagX = 24;
  tags.forEach((tag) => {
    const w = tag.length * 6.2 + 16;
    svg += `<rect x="${tagX}" y="${tagY - 12}" width="${w}" height="18" rx="9" fill="${theme.tagBg}"/>`;
    svg += `<text x="${tagX + w / 2}" y="${tagY + 1}" text-anchor="middle" font-size="10" font-family="ui-monospace,Consolas,monospace" fill="${theme.tagText}">${esc(tag)}</text>`;
    tagX += w + 8;
  });

  svg += starIcon(27, CARD_H - 17, 5, "#F5B942");
  svg += `<text x="34" y="${CARD_H - 14}" font-size="10.5" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${details.stargazers_count}  ·  updated ${relativeTime(details.pushed_at)}</text>`;

  svg += donut(CARD_W - 46, 46, 26, allLangs, theme.ring_track, theme.rank);
  svg += `</g>`;
  return svg;
}

module.exports = async (req, res) => {
  try {
    const url = new URL(req.url, "https://x");
    const repoParam = url.searchParams.get("repos") || "";
    const themeName = url.searchParams.get("theme") === "light" ? "light" : "dark";
    const theme = THEMES[themeName];
    const repos = repoParam.split(",").map((s) => s.trim()).filter(Boolean);

    if (repos.length === 0) {
      res.setHeader("Content-Type", "image/svg+xml");
      res.status(400).send(`<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60"><text x="10" y="35" font-family="monospace" fill="red">missing ?repos=owner/name,owner/name</text></svg>`);
      return;
    }

    const token = process.env.GH_TOKEN || process.env.PAT_1;
    const rows = Math.ceil(repos.length / COLS);
    const width = COLS * CARD_W + (COLS - 1) * GAP + PAD * 2;
    const height = rows * CARD_H + (rows - 1) * GAP + PAD * 2;

    const cardResults = await Promise.allSettled(
      repos.map((r, i) =>
        buildCard(r, PAD + (i % COLS) * (CARD_W + GAP), PAD + Math.floor(i / COLS) * (CARD_H + GAP), theme, token)
      )
    );

    const cards = cardResults
      .map((r, i) =>
        r.status === "fulfilled"
          ? r.value
          : `<g transform="translate(${PAD + (i % COLS) * (CARD_W + GAP)},${PAD + Math.floor(i / COLS) * (CARD_H + GAP)})">
               <rect width="${CARD_W}" height="${CARD_H}" rx="10" fill="${theme.card}" stroke="${theme.border}"/>
               <text x="20" y="${CARD_H / 2}" font-size="12" font-family="monospace" fill="${theme.desc}">${esc(repos[i])}: unavailable</text>
             </g>`
      )
      .join("");

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
      <rect width="${width}" height="${height}" fill="${theme.bg}"/>
      ${cards}
    </svg>`;

    res.setHeader("Content-Type", "image/svg+xml");
    res.setHeader("Cache-Control", "public, max-age=7200, s-maxage=7200");
    res.status(200).send(svg);
  } catch (err) {
    res.setHeader("Content-Type", "image/svg+xml");
    res.status(500).send(`<svg xmlns="http://www.w3.org/2000/svg" width="500" height="60"><text x="10" y="35" font-family="monospace" fill="red">${esc(err.message)}</text></svg>`);
  }
};
