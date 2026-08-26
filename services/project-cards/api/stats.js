// api/stats.js
//
// Self-hosted replacement for the github-readme-stats "Stats" +
// "Most Used Languages" cards -- built from scratch rather than a
// fork, since every forked service used this session (github-readme-
// stats, github-readme-streak-stats) hit real reliability problems
// (Vercel domain drift, wrong production branch, GitHub API rate
// limits) that had nothing to do with the code itself, just the
// deploy. Same GH_TOKEN this project's other endpoint already uses.
//
// GET /api/stats?username=TomasPosada0626&theme=dark|light

const THEMES = {
  dark: {
    bg: "#0A101F", card: "#0D1526", border: "#22D3EE33",
    title: "#E7ECFB", desc: "#9AA4C0", chrome: "#22D3EE", accent: "#10B981",
    rank: ["#A78BFA", "#22D3EE", "#10B981", "#F5B942", "#EF4444", "#8892B0"],
  },
  light: {
    bg: "#FFFFFF", card: "#F3F1FC", border: "#0891B233",
    title: "#1E2433", desc: "#5B6478", chrome: "#0891B2", accent: "#10B981",
    rank: ["#7C3AED", "#0891B2", "#10B981", "#F5B942", "#EF4444", "#8892B0"],
  },
};

const QUERY = `
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        description
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        repositoryTopics(first: 10) {
          nodes { topic { name } }
        }
      }
    }
  }
}`;

async function fetchStats(login, token) {
  const res = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "User-Agent": "gh-stats-card",
    },
    body: JSON.stringify({ query: QUERY, variables: { login } }),
  });
  if (!res.ok) throw new Error(`GitHub GraphQL HTTP ${res.status}`);
  const json = await res.json();
  if (json.errors) throw new Error(`GraphQL: ${json.errors.map((e) => e.message).join("; ")}`);
  return json.data.user;
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function statRow(y, icon, label, value, theme) {
  return (
    `<text x="24" y="${y}" font-size="13" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">${icon}</text>` +
    `<text x="46" y="${y}" font-size="13" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(label)}:</text>` +
    `<text x="270" y="${y}" text-anchor="end" font-size="13" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.title}">${value}</text>`
  );
}

function buildStatsCard(user, theme) {
  const totalStars = user.repositories.nodes.reduce((a, r) => a + r.stargazerCount, 0);
  const c = user.contributionsCollection;
  const W = 380, H = 172;

  const rows = [
    ["★", "Total Stars Earned", totalStars],
    ["○", "Total Commits (last yr)", c.totalCommitContributions],
    ["⥇", "Total PRs", c.totalPullRequestContributions],
    ["◉", "Total Issues", c.totalIssueContributions],
    ["⌘", "Contributed To (last yr)", c.totalRepositoriesWithContributedCommits],
  ];

  let svg = `<rect width="${W}" height="${H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<text x="24" y="30" font-size="14" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">TomasPosada0626's GitHub Stats</text>`;
  rows.forEach(([icon, label, value], i) => {
    svg += statRow(58 + i * 22, icon, label, value.toLocaleString(), theme);
  });
  return { svg, w: W, h: H };
}

// Excluded from the aggregate, same call made for the project cards'
// top-langs earlier: a notebook's saved cell OUTPUT (images, tables)
// is stored as JSON in the .ipynb file itself, so GitHub counts it as
// "Jupyter Notebook" bytes even though little of it is authored code
// -- it was dwarfing every real language at ~72% of the total.
const EXCLUDED_LANGS = new Set(["Jupyter Notebook"]);

function buildLangCard(user, theme) {
  const totals = new Map();
  for (const repo of user.repositories.nodes) {
    for (const edge of repo.languages.edges) {
      if (EXCLUDED_LANGS.has(edge.node.name)) continue;
      totals.set(edge.node.name, (totals.get(edge.node.name) || 0) + edge.size);
    }
  }
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  const grand = sorted.reduce((a, [, v]) => a + v, 0) || 1;
  const langs = sorted.map(([name, size], i) => ({
    name, pct: (size / grand) * 100, color: theme.rank[i % theme.rank.length],
  }));

  const W = 380, H = 172;
  let svg = `<rect width="${W}" height="${H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<text x="24" y="30" font-size="14" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">Most Used Languages</text>`;

  const barX = 24, barY = 44, barW = W - 48, barH = 10;
  let cx = barX;
  langs.forEach((l) => {
    const w = (l.pct / 100) * barW;
    svg += `<rect x="${cx.toFixed(1)}" y="${barY}" width="${Math.max(w, 0).toFixed(1)}" height="${barH}" fill="${l.color}"/>`;
    cx += w;
  });
  svg += `<rect x="${barX}" y="${barY}" width="${barW}" height="${barH}" rx="5" fill="none"/>`;

  const legendY = 78;
  langs.forEach((l, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const lx = 24 + col * 180;
    const ly = legendY + row * 24;
    svg += `<circle cx="${lx}" cy="${ly - 4}" r="4" fill="${l.color}"/>`;
    svg += `<text x="${lx + 12}" y="${ly}" font-size="11.5" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(l.name)} ${l.pct.toFixed(1)}%</text>`;
  });

  return { svg, w: W, h: H };
}

// Same idea as extractStack() in index.js (frameworks/DBs/tools worth
// naming over raw topic words), duplicated rather than imported since
// each file under api/ is its own independent serverless function --
// expanded here because this aggregates ALL owned repos, not just the
// six featured ones, so it turns up tools that never showed up there.
// Categorized (not one flat pill list) because that's what actually
// reads as organized at 19+ items -- a wall of same-size pills in
// discovery order doesn't, no matter how good any individual pill
// looks; per-tech logos at 19 items would also cost more than they'd
// add (several of these -- PostgreSQL's elephant, RabbitMQ's rabbit --
// don't hold up at pill-icon size anyway).
const KNOWN_TECH = [
  ["nextjs", "Next.js", "Frontend"], ["next.js", "Next.js", "Frontend"],
  ["react", "React", "Frontend"], ["electron", "Electron", "Frontend"],
  ["vite", "Vite", "Frontend"], ["tailwindcss", "Tailwind", "Frontend"],
  ["tailwind", "Tailwind", "Frontend"], ["zustand", "Zustand", "Frontend"],
  ["vue", "Vue", "Frontend"], ["angular", "Angular", "Frontend"],
  ["nestjs", "NestJS", "Backend"], ["django-rest-framework", "DRF", "Backend"],
  ["django", "Django", "Backend"], ["flask", "Flask", "Backend"],
  ["fastapi", "FastAPI", "Backend"], ["express", "Express", "Backend"],
  ["nodejs", "Node.js", "Backend"], ["node.js", "Node.js", "Backend"],
  ["graphql", "GraphQL", "Backend"], ["websocket", "WebSocket", "Backend"],
  ["jwt", "JWT", "Backend"],
  ["postgresql", "PostgreSQL", "Database"], ["postgres", "PostgreSQL", "Database"],
  ["mongodb", "MongoDB", "Database"], ["prisma", "Prisma", "Database"],
  ["redis", "Redis", "Database"], ["sqlalchemy", "SQLAlchemy", "Database"],
  ["supabase", "Supabase", "Database"], ["firebase", "Firebase", "Database"],
  ["docker", "Docker", "DevOps"], ["kubernetes", "Kubernetes", "DevOps"],
  ["aws", "AWS", "DevOps"], ["nginx", "Nginx", "DevOps"],
  ["rabbitmq", "RabbitMQ", "DevOps"], ["celery", "Celery", "DevOps"],
  ["playwright", "Playwright", "DevOps"], ["stripe", "Stripe", "DevOps"],
  ["pytorch", "PyTorch", "ML"], ["tensorflow", "TensorFlow", "ML"],
  ["flutter", "Flutter", "Mobile"],
];
const CATEGORY_ORDER = ["Frontend", "Backend", "Database", "DevOps", "ML", "Mobile"];

function extractRepoStack(repo) {
  const found = [];
  const topics = (repo.repositoryTopics?.nodes || []).map((n) => n.topic.name.toLowerCase());
  const desc = (repo.description || "").toLowerCase();
  for (const [key, label, category] of KNOWN_TECH) {
    if (topics.includes(key) || desc.includes(key)) found.push({ label, category });
  }
  return found;
}

function buildStackCard(user, theme) {
  const counts = new Map(); // label -> {count, category}
  for (const repo of user.repositories.nodes) {
    const seen = new Set();
    for (const { label, category } of extractRepoStack(repo)) {
      if (seen.has(label)) continue;
      seen.add(label);
      const cur = counts.get(label) || { count: 0, category };
      cur.count += 1;
      counts.set(label, cur);
    }
  }

  const byCategory = new Map();
  for (const [label, { count, category }] of counts.entries()) {
    if (!byCategory.has(category)) byCategory.set(category, []);
    byCategory.get(category).push({ label, count });
  }
  for (const items of byCategory.values()) items.sort((a, b) => b.count - a.count);

  const W = 1180;
  const padX = 24;
  const pillH = 24, pillGapX = 8, pillGapY = 10, rowGapY = 30;
  let py = 44;
  const parts = [];

  CATEGORY_ORDER.forEach((category, ci) => {
    const items = byCategory.get(category);
    if (!items || items.length === 0) return;
    const color = theme.rank[ci % theme.rank.length];

    parts.push(`<text x="${padX}" y="${py}" font-size="10.5" letter-spacing=".08em" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}" opacity=".75">${category.toUpperCase()}</text>`);
    let px = padX;
    let rowY = py + 16;
    items.forEach(({ label }) => {
      const w = label.length * 7.2 + 26;
      if (px + w > W - padX) {
        px = padX;
        rowY += pillH + pillGapY;
      }
      parts.push(
        `<rect x="${px.toFixed(1)}" y="${rowY}" width="${w.toFixed(1)}" height="${pillH}" rx="12" fill="${color}22" stroke="${color}66" stroke-width="1"/>` +
        `<text x="${(px + w / 2).toFixed(1)}" y="${rowY + 16}" text-anchor="middle" font-size="11.5" font-weight="600" font-family="ui-monospace,Consolas,monospace" fill="${color}">${esc(label)}</text>`
      );
      px += w + pillGapX;
    });
    py = rowY + pillH + rowGapY;
  });

  const H = parts.length ? py - rowGapY + 16 : 60;

  let svg = `<rect width="${W}" height="${H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<text x="${padX}" y="30" font-size="14" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">Tech Stack</text>`;
  svg += parts.join("");

  return { svg, w: W, h: H };
}

module.exports = async (req, res) => {
  try {
    const url = new URL(req.url, "https://x");
    const username = url.searchParams.get("username") || "TomasPosada0626";
    const themeName = url.searchParams.get("theme") === "light" ? "light" : "dark";
    const cardParam = url.searchParams.get("card");
    const card = cardParam === "langs" ? "langs" : cardParam === "stack" ? "stack" : "stats";
    const theme = THEMES[themeName];

    const token = process.env.GH_TOKEN || process.env.PAT_1;
    if (!token) throw new Error("GH_TOKEN/PAT_1 not set");

    const user = await fetchStats(username, token);
    const builders = { stats: buildStatsCard, langs: buildLangCard, stack: buildStackCard };
    const { svg: inner, w, h } = builders[card](user, theme);

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${inner}</svg>`;

    res.setHeader("Content-Type", "image/svg+xml");
    res.setHeader("Cache-Control", "public, max-age=7200, s-maxage=7200");
    res.status(200).send(svg);
  } catch (err) {
    res.setHeader("Content-Type", "image/svg+xml");
    res.status(500).send(`<svg xmlns="http://www.w3.org/2000/svg" width="500" height="60"><text x="10" y="35" font-family="monospace" fill="red">${esc(err.message)}</text></svg>`);
  }
};
