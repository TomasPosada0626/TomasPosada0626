# project-cards

Self-hosted, live-updating "pinned projects" SVG card grid for the
profile README — same pattern as the self-hosted `github-readme-stats`
instance: a Vercel serverless function that hits the GitHub API on
every request, so new stars/commits/topics on the underlying repos
show up on the next page view with no rebuild step.

## Deploy

1. In Vercel: **Add New... → Project → Import** this same
   `TomasPosada0626/TomasPosada0626` repo again (as a second, separate
   project — it's fine to import one repo more than once).
2. When it asks for a **Root Directory**, click **Edit** and set it to
   `services/project-cards`.
3. Add an environment variable **`GH_TOKEN`** = the same classic PAT
   you already created for the stats instance (`repo` scope). Not
   strictly required, but without it you're limited to 60 GitHub API
   requests/hour shared across every visitor.
4. **Deploy.**
5. Test it: `https://YOUR-DOMAIN.vercel.app/api?repos=TomasPosada0626/cucu&theme=dark`
   should return an SVG with one card, not an error.

## Usage

```
GET /api?repos=owner/repo,owner/repo2&theme=dark|light
```

`repos` — comma-separated `owner/name` pairs, rendered in the order given, two per row.
`theme` — `dark` (default) or `light`.
