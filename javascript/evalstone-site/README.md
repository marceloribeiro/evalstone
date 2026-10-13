# evalstone-site

**evalstone.com** — the landing page and the learning docs for Evalstone.

| | |
| --- | --- |
| Stack | Next.js 16 · React 19 · Tailwind 4 · Fumadocs (MDX) |
| Output | `standalone` (self-hosted: local build → rsync → systemd → nginx) |
| Content | `content/docs/learn/*` (Evals 101) · `content/docs/evalstone/*` (product) |
| Tests | Playwright, `tests/specs/*.spec.ts` with page objects in `tests/pages/` |

## Develop

```bash
just install
just up            # http://localhost:3000
just check         # eslint + next typegen + tsc
just test          # Playwright against a production build on :3180
```

Node ≥ 20.19 is required by the toolchain (`nvm use 23` locally; the server
unit runs Node 20.20.2).

## Deploy

```bash
just deploy             # builds locally, rsyncs .next/standalone to web01, restarts the unit
just setup-systemd      # first time: installs systemd/evalstone-site.service (port 8180)
just setup-nginx-http   # installs nginx/nginx-http.conf as /opt/nginx site evalstone-site
just setup-nginx-https  # after certs land in shared/certs/
```

`deploy.json` holds the server, deploy location and branch. `.env.production`
(gitignored) carries `NEXT_PUBLIC_SITE_URL`.

## Writing docs

Pages are MDX under `content/docs`. `meta.json` in each folder sets the
sidebar order. Every page gets a markdown mirror at
`/llms.mdx/docs/<path>/content.md` and the whole set at `/llms-full.txt`.
Keep the status callouts on the Evalstone pages truthful: they describe the
design until the piece ships.
