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
const CARD_H = 190;
const GAP = 18;
const COLS = 2;
const PAD = 4;

const THEMES = {
  dark: {
    bg: "#0A101F", card: "#0D1526", border: "#22D3EE33",
    title: "#E7ECFB", desc: "#9AA4C0", chrome: "#22D3EE",
    accent: "#10B981", tagBg: "#22D3EE22", tagText: "#22D3EE",
    ring_track: "#1E2740",
  },
  light: {
    bg: "#FFFFFF", card: "#F3F1FC", border: "#0891B233",
    title: "#1E2433", desc: "#5B6478", chrome: "#0891B2",
    accent: "#10B981", tagBg: "#0891B222", tagText: "#0891B2",
    ring_track: "#E2E6F0",
  },
};

// A short lookup for the languages actually likely to show up here;
// unlisted languages fall back to the theme accent rather than guessing.
const LANG_COLORS = {
  TypeScript: "#3178C6", JavaScript: "#F1E05A", Python: "#3572A5",
  HTML: "#E34C26", CSS: "#563D7C", Java: "#B07219", SQL: "#E38C00",
  Vue: "#41B883", "Jupyter Notebook": "#DA5B0B", PLpgSQL: "#336790",
};

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

function donut(cx, cy, r, allLangs, track) {
  // One arc segment per language, each sized to its own share and
  // coloured to match its legend dot -- not just a single-language
  // ring with everything else left as bare track.
  const stroke = 5;
  const circumference = 2 * Math.PI * r;
  const gapDeg = allLangs.length > 1 ? 2.2 : 0; // small visual gap between segments
  let cum = 0;
  const segments = allLangs
    .map(({ lang, pct }) => {
      const color = LANG_COLORS[lang] || "#8892B0";
      const segFraction = Math.max(0, pct / 100 - gapDeg / 360);
      const dash = segFraction * circumference;
      const offset = -(cum / 100) * circumference;
      cum += pct;
      return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${stroke}"
        stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${circumference.toFixed(1)}"
        stroke-dashoffset="${offset.toFixed(1)}" transform="rotate(-90 ${cx} ${cy})"/>`;
    })
    .join("");
  const topColor = LANG_COLORS[allLangs[0]?.lang] || "#8892B0";
  const topPct = allLangs[0]?.pct || 0;
  return `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${track}" stroke-width="${stroke}"/>
    ${segments}
    <text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="15" font-weight="700"
      font-family="ui-monospace,Consolas,monospace" fill="${topColor}">${Math.round(topPct)}%</text>
  `;
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
  const langs = allLangs.slice(0, 3); // legend only shows the top few; the ring below uses all of them

  const descLines = wrap(details.description || "No description yet.", 40, 2);
  const tags = (details.topics || []).slice(0, 3);

  let svg = `<g transform="translate(${x},${y})">`;
  svg += `<rect width="${CARD_W}" height="${CARD_H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;

  svg += `<circle cx="24" cy="26" r="4" fill="${theme.accent}"/>`;
  svg += `<text x="36" y="31" font-size="15" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.title}">${esc(truncate(name, 24))}</text>`;
  svg += `<text x="24" y="48" font-size="10.5" letter-spacing=".04em" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}" opacity=".7">${esc(owner)}/${esc(name)}</text>`;

  descLines.forEach((line, i) => {
    svg += `<text x="24" y="${68 + i * 16}" font-size="12" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(line)}</text>`;
  });

  let ty = 106;
  langs.forEach((l, i) => {
    const lx = 24 + (i % 2) * 150;
    const ly = ty + Math.floor(i / 2) * 18;
    const color = LANG_COLORS[l.lang] || theme.accent;
    svg += `<circle cx="${lx}" cy="${ly - 4}" r="3.5" fill="${color}"/>`;
    svg += `<text x="${lx + 10}" y="${ly}" font-size="11" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(l.lang)} ${l.pct.toFixed(0)}%</text>`;
  });

  let tagY = ty + Math.ceil(langs.length / 2) * 18 + 12;
  let tagX = 24;
  tags.forEach((tag) => {
    const w = tag.length * 6.2 + 16;
    svg += `<rect x="${tagX}" y="${tagY - 12}" width="${w}" height="18" rx="9" fill="${theme.tagBg}"/>`;
    svg += `<text x="${tagX + w / 2}" y="${tagY + 1}" text-anchor="middle" font-size="10" font-family="ui-monospace,Consolas,monospace" fill="${theme.tagText}">${esc(tag)}</text>`;
    tagX += w + 8;
  });

  svg += `<text x="24" y="${CARD_H - 14}" font-size="10.5" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">★ ${details.stargazers_count}  ·  updated ${relativeTime(details.pushed_at)}</text>`;

  svg += donut(CARD_W - 46, 46, 26, allLangs, theme.ring_track);
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

    const token = process.env.GH_TOKEN;
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
