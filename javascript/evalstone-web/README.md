# evalstone-web

The Evalstone **center web app** (Next.js 16, React 19, Tailwind 4, shadcn) on port **8182**
→ app.evalstone.com. It is a client of the center API (`python/evalstone-api`, port 8181):
REST with the JWT from `/auth/login`, and the project WebSocket for live updates
(`POST /projects/{id}/ws-ticket` → `GET /ws/projects/{id}?ticket=…`).

```bash
cp .env.example .env.local      # NEXT_PUBLIC_API_URL
just install
just up                          # http://localhost:8182  (API: `just up` in python/evalstone-api)
just check                       # eslint + tsc
just test                        # Playwright against a production build + the running API
```

Layout: `src/app` (routes) · `src/components/{ui,layout,common,<feature>}` · `src/contexts`
(Auth, Workspace = org + project, WebSocket) · `src/hooks` · `src/lib` (api client, types) ·
`tests/{fixtures,pages,specs}` (Playwright, one spec per feature). Deploy kit: `deploy.sh`
(local standalone build + rsync), `systemd/`, `nginx/`, `just setup-*`.
