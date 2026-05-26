# eval-harness web

Marketing + methodology + leaderboard site for the [eval-harness](../) project.

Lives at https://evals.kristenmartino.ai.

## Stack

Matches `portfolio-v2`: Next.js 16 (App Router) + React 19 + TypeScript + Tailwind v4 + MDX + IBM Plex fonts.

## Local development

```bash
npm install
npm run dev
```

Open http://localhost:3000.

## Pages

| Route | Source | Notes |
|---|---|---|
| `/` | `src/app/page.tsx` | Landing — elevator pitch + status |
| `/methodology` | `src/app/methodology/page.mdx` | Full methodology page |
| `/executive-summary` | `src/app/executive-summary/page.mdx` | Exec summary for hiring managers |
| `/leaderboard` | `src/app/leaderboard/page.tsx` | Placeholder until Phase 1 results land |

MDX content is ported from `../docs/`. When the canonical docs change, update the MDX copies too. (Future: build-time pull from `../docs/` to eliminate drift.)

## Deployment

Auto-deploys to Vercel on push to `main`. Vercel project root is set to `web/` so the rest of the repo (the harness itself) is ignored at build time.
