# Re-recording the walkthrough

`docs/img/walkthrough.gif` is two recordings joined. Re-record after a CLI or center UI change.

1. **Terminal** (`walkthrough.tape`, [vhs](https://github.com/charmbracelet/vhs)): from this folder,
   `vhs walkthrough.tape` with `evalstone` on `PATH`. It works in `$DEMO_DIR`
   (default `/Users/Shared/my-bot`, a neutral path that is printed by `evalstone init`).
2. **Center** (`record-center.js`, Playwright): a *local* center, never the public demo.
   - API + web on :8181/:8182 (or set `WEB=http://localhost:<port>`), a fresh database.
   - `python/evalstone-api/scripts/seed_demo.py` with a local test login.
   - An org provider for the judge, the project's default judge model, then
     `evalstone run judged` on `samples/rag-bot` attached to that project.
   - A grade queue over that run's `helpful` results (`POST /projects/{id}/label-queues`).
   - `ORG_ID=… PROJECT_ID=… RUN_ID=… QUEUE_ID=… DEMO_EMAIL=… DEMO_PASSWORD=…
     node record-center.js <javascript/evalstone-web/node_modules> <out-dir>` — signs in off
     camera, opens the run, types the ten grades, calibrates and promotes.
3. **Join + encode** (ffmpeg):

```bash
ffmpeg -i walkthrough-terminal.mp4 -i center.webm -filter_complex \
  "[0:v]fps=25,scale=1280:720,setsar=1[a];[1:v]fps=25,scale=1280:720,setsar=1[b];[a][b]concat=n=2:v=1[v]" \
  -map "[v]" -c:v libx264 -crf 26 -preset slow -pix_fmt yuv420p -movflags +faststart walkthrough.mp4
ffmpeg -i walkthrough.mp4 -vf "fps=10,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" ../walkthrough.gif
```
