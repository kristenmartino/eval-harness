# eval-harness web

Implementation status and methodology site for the [eval-harness](../) project.

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
| `/methodology` | `src/app/methodology/content.mdx` | Full methodology page |
| `/executive-summary` | `src/app/executive-summary/content.mdx` | Implemented scope and pending study work |
| `/leaderboard` | `src/app/leaderboard/page.tsx` | Results status; no production rankings |

Server page components hold route metadata; MDX files hold the article content.
MDX content is ported from `../docs/`; tables use JSX because GFM is not configured. When the canonical docs change, update the MDX copies too. (Future: build-time pull from `../docs/` to eliminate drift.)

## Deployment

Auto-deploys to Vercel on push to `main`. Vercel project root is set to `web/` so the rest of the repo (the harness itself) is ignored at build time.
