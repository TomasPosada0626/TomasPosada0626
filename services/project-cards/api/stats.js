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

// Same rank palette as index.js's THEMES (kept in sync by hand, not
// imported -- each file under api/ is its own independent serverless
// function): warm/cool alternating so adjacent ranks never sit as two
// shades of the same temperature next to each other.
const THEMES = {
  dark: {
    bg: "#0A101F", card: "#0D1526", border: "#22D3EE33",
    title: "#E7ECFB", desc: "#9AA4C0", chrome: "#22D3EE", accent: "#10B981",
    rank: ["#A78BFA", "#FBBF24", "#22D3EE", "#F87171", "#10B981", "#94A3B8"],
  },
  light: {
    bg: "#FFFFFF", card: "#F3F1FC", border: "#0891B233",
    title: "#1E2433", desc: "#5B6478", chrome: "#0891B2", accent: "#10B981",
    rank: ["#7C3AED", "#D97706", "#0891B2", "#DC2626", "#10B981", "#64748B"],
  },
};

const QUERY = `
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      totalRepositoryContributions
      restrictedContributionsCount
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

function statRow(y, icon, label, value, theme, delay) {
  // Rows cascade in one at a time on load (like the project cards'
  // stagger, and the banner's own SMIL animation) instead of the whole
  // card just appearing -- makes it read as "live data streaming in"
  // rather than a static image.
  return `<g opacity="0">
      <animate attributeName="opacity" from="0" to="1" begin="${delay}s" dur="0.4s" fill="freeze"/>
      <animateTransform attributeName="transform" type="translate" from="-6 0" to="0 0" begin="${delay}s" dur="0.4s" fill="freeze"/>
      <text x="24" y="${y}" font-size="13" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">${icon}</text>
      <text x="46" y="${y}" font-size="13" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(label)}:</text>
      <text x="356" y="${y}" text-anchor="end" font-size="13" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.title}">${value}</text>
    </g>`;
}

function buildStatsCard(user, theme) {
  const totalStars = user.repositories.nodes.reduce((a, r) => a + r.stargazerCount, 0);
  const c = user.contributionsCollection;
  // GitHub's own profile graph total = every contribution type, not
  // just commits -- this card was missing PR reviews and repo-creation
  // (plus restrictedContributionsCount, contributions the querying
  // token can't see the detail of but that still count), so it always
  // undercounted vs. the number on the actual profile page.
  const totalContributions =
    c.totalCommitContributions +
    c.totalPullRequestContributions +
    c.totalPullRequestReviewContributions +
    c.totalIssueContributions +
    c.totalRepositoryContributions +
    c.restrictedContributionsCount;
  const W = 380, H = 194;

  const rows = [
    ["◆", "Total Contributions (last yr)", totalContributions],
    ["★", "Total Stars Earned", totalStars],
    ["○", "Commits (last yr)", c.totalCommitContributions],
    ["⥇", "PRs (last yr)", c.totalPullRequestContributions],
    ["◉", "Issues (last yr)", c.totalIssueContributions],
    ["⌘", "Contributed To (last yr)", c.totalRepositoriesWithContributedCommits],
  ];

  let svg = `<rect width="${W}" height="${H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<text x="24" y="30" font-size="14" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">TomasPosada0626's GitHub Stats</text>`;
  rows.forEach(([icon, label, value], i) => {
    const delay = (0.1 + i * 0.09).toFixed(2);
    svg += statRow(58 + i * 22, icon, label, value.toLocaleString(), theme, delay);
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

  // Matches buildStatsCard's H exactly -- side by side at width:49%
  // each in the README, a mismatched height showed up as a jagged
  // bottom edge between the two cards.
  const W = 380, H = 194;
  let svg = `<rect width="${W}" height="${H}" rx="10" fill="${theme.card}" stroke="${theme.border}" stroke-width="1.2"/>`;
  svg += `<text x="24" y="30" font-size="14" font-weight="700" font-family="ui-monospace,Consolas,monospace" fill="${theme.chrome}">Most Used Languages</text>`;

  const barX = 24, barY = 55, barW = W - 48, barH = 12;
  // Same fix as the project-card donuts: a real 1.1%/0.4% share is a
  // sub-pixel sliver at this bar width, invisible next to its
  // neighbour. Floor every segment to a minimum visible width,
  // borrowed proportionally from segments with slack above it.
  const minW = langs.length > 1 ? 10 : 0;
  const rawW = langs.map((l) => (l.pct / 100) * barW);
  const short = rawW.map((w) => w < minW);
  const shortTotal = short.reduce((a, s) => a + (s ? minW : 0), 0);
  const longRawTotal = rawW.reduce((a, w, i) => a + (short[i] ? 0 : w), 0);
  const scale = longRawTotal > 0 ? (barW - shortTotal) / longRawTotal : 1;
  const segW = rawW.map((w, i) => (short[i] ? minW : w * scale));

  // Bar fills left-to-right on load via a clip that grows, rather than
  // just appearing -- a "reading the data live" effect that fits a
  // stat this literally is a fraction of a whole.
  const wipeId = "langbar-wipe";
  svg += `<defs><clipPath id="${wipeId}"><rect x="${barX}" y="${barY}" width="0" height="${barH}">
      <animate attributeName="width" values="0;${barW}" keyTimes="0;1" calcMode="spline" keySplines="0.25 0.1 0.25 1" begin="0.1s" dur="0.9s" fill="freeze"/>
    </rect></clipPath></defs>`;
  svg += `<g clip-path="url(#${wipeId})">`;
  let cx = barX;
  langs.forEach((l, i) => {
    svg += `<rect x="${cx.toFixed(1)}" y="${barY}" width="${Math.max(segW[i], 0).toFixed(1)}" height="${barH}" fill="${l.color}"/>`;
    cx += segW[i];
  });
  svg += `</g>`;
  svg += `<rect x="${barX}" y="${barY}" width="${barW}" height="${barH}" rx="5" fill="none"/>`;

  const legendY = 92;
  langs.forEach((l, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const lx = 24 + col * 180;
    const ly = legendY + row * 24;
    const delay = (0.5 + i * 0.08).toFixed(2);
    svg += `<g opacity="0">
        <animate attributeName="opacity" from="0" to="1" begin="${delay}s" dur="0.4s" fill="freeze"/>
        <circle cx="${lx}" cy="${ly - 4}" r="4" fill="${l.color}"/>
        <text x="${lx + 12}" y="${ly}" font-size="11.5" font-family="ui-monospace,Consolas,monospace" fill="${theme.desc}">${esc(l.name)} ${l.pct.toFixed(1)}%</text>
      </g>`;
  });

  return { svg, w: W, h: H };
}

module.exports = async (req, res) => {
  try {
    const url = new URL(req.url, "https://x");
    const username = url.searchParams.get("username") || "TomasPosada0626";
    const themeName = url.searchParams.get("theme") === "light" ? "light" : "dark";
    const cardParam = url.searchParams.get("card");
    const card = cardParam === "langs" ? "langs" : "stats";
    const theme = THEMES[themeName];

    const token = process.env.GH_TOKEN || process.env.PAT_1;
    if (!token) throw new Error("GH_TOKEN/PAT_1 not set");

    const user = await fetchStats(username, token);
    const builders = { stats: buildStatsCard, langs: buildLangCard };
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
