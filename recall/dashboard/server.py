"""Minimal local web dashboard: browse memories + see cost/usage.

Single-file FastAPI app, no build step, no external assets. Renders one HTML
page that reads straight from the local SQLite store. Optional dependency:
  pip install 'recall-ai[dashboard]'
"""

from __future__ import annotations

import html

from ..core import Recall


def _page() -> str:
    r = Recall()
    s = r.stats()
    mems = r.store.all_memories()
    recent = r.recent(limit=15)
    r.close()

    mem_rows = "".join(
        f"<tr><td>{m.id}</td><td>{html.escape(m.content)}</td>"
        f"<td class='dim'>{html.escape(', '.join(m.tags))}</td></tr>"
        for m in mems
    ) or "<tr><td colspan=3 class='dim'>No memories yet.</td></tr>"

    call_rows = "".join(
        f"<tr><td>{html.escape(c['model'])}</td><td>{c['input_tokens']}</td>"
        f"<td>{c['output_tokens']}</td><td>${c['cost_usd']:.4f}</td>"
        f"<td>{c['latency_ms']} ms</td></tr>"
        for c in recent
    ) or "<tr><td colspan=5 class='dim'>No calls yet.</td></tr>"

    model_rows = "".join(
        f"<tr><td>{html.escape(b['model'])}</td><td>{b['calls']}</td>"
        f"<td>{b['tokens']:,}</td><td>${b['cost']:.4f}</td></tr>"
        for b in s["by_model"]
    ) or "<tr><td colspan=4 class='dim'>No usage yet.</td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>recall dashboard</title>
<style>
  body{{font-family:-apple-system,system-ui,sans-serif;max-width:880px;margin:40px auto;
       padding:0 20px;color:#222;background:#fafafa}}
  h1{{margin-bottom:4px}} .sub{{color:#888;margin-top:0}}
  .cards{{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}}
  .card{{flex:1;min-width:140px;background:#fff;border:1px solid #eee;border-radius:12px;
        padding:16px}} .card .n{{font-size:26px;font-weight:700}}
  .card .l{{color:#888;font-size:13px}}
  table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #eee;
        border-radius:12px;overflow:hidden;margin:12px 0}}
  th,td{{text-align:left;padding:10px 12px;border-bottom:1px solid #f0f0f0;font-size:14px}}
  th{{background:#f7f7f7;color:#555}} .dim{{color:#aaa}}
  h2{{margin-top:32px;font-size:18px}}
</style></head>
<body>
  <h1>🧠 recall</h1>
  <p class="sub">Local AI brain — memory & cost. Data never leaves this machine.</p>
  <div class="cards">
    <div class="card"><div class="n">{s['memory_count']}</div><div class="l">memories</div></div>
    <div class="card"><div class="n">{s['calls']}</div><div class="l">model calls</div></div>
    <div class="card"><div class="n">{s['input_tokens']+s['output_tokens']:,}</div><div class="l">tokens</div></div>
    <div class="card"><div class="n">${s['cost_usd']:.4f}</div><div class="l">total cost</div></div>
  </div>
  <h2>Cost by model</h2>
  <table><tr><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>{model_rows}</table>
  <h2>Memories</h2>
  <table><tr><th>ID</th><th>Memory</th><th>Tags</th></tr>{mem_rows}</table>
  <h2>Recent calls</h2>
  <table><tr><th>Model</th><th>In</th><th>Out</th><th>Cost</th><th>Latency</th></tr>{call_rows}</table>
</body></html>"""


def serve(port: int = 8745) -> None:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    app = FastAPI(title="recall dashboard")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _page()

    print(f"recall dashboard → http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
