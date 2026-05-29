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
    sessions = r.recent_sessions(limit=8)
    scopes = r.store.list_scopes()
    budget = s.get("daily_budget", 0) or 0
    today = s.get("cost_today", 0) or 0
    r.close()

    budget_html = ""
    if budget > 0:
        pct = min(today / budget * 100, 100)
        bar_color = "#e5484d" if pct >= 100 else "#f5a623" if pct >= 80 else "#30a46c"
        budget_html = (
            f"<div class='budget'><div class='blabel'>Today · "
            f"${today:.4f} / ${budget:.2f}</div>"
            f"<div class='btrack'><div class='bfill' style='width:{pct:.0f}%;"
            f"background:{bar_color}'></div></div></div>"
        )

    scope_html = " ".join(
        f"<span class='chip'>{html.escape(sc)} · {c}</span>" for sc, c in scopes
    ) or "<span class='dim'>no scopes</span>"

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

    def _session_html(sess: dict) -> str:
        p = sess["parent"]
        kids = "".join(
            f"<div class='kid'><span class='kind'>{html.escape(c['kind'])}</span> "
            f"{html.escape(c['model'])} · {c['input_tokens']}+{c['output_tokens']} tok · "
            f"${c['cost_usd']:.4f}</div>"
            for c in sess["children"]
        )
        total = (
            f"<div class='kid dim'>turn total: {sess['total_tokens']} tok · "
            f"${sess['total_cost']:.4f}</div>" if sess["children"] else ""
        )
        return (
            f"<div class='turn'><div class='root'><span class='kind chat'>"
            f"{html.escape(p['kind'])}</span> <b>{html.escape(p['model'])}</b> · "
            f"{p['input_tokens']}+{p['output_tokens']} tok · ${p['cost_usd']:.4f} · "
            f"{p['latency_ms']} ms</div>{kids}{total}</div>"
        )

    sessions_html = "".join(_session_html(x) for x in sessions) or \
        "<div class='dim'>No turns yet.</div>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>recall dashboard</title>
<meta http-equiv="refresh" content="5">
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
  .budget{{margin:16px 0}} .blabel{{font-size:13px;color:#666;margin-bottom:6px}}
  .btrack{{height:10px;background:#eee;border-radius:6px;overflow:hidden}}
  .bfill{{height:100%;border-radius:6px;transition:width .3s}}
  .chips{{margin:8px 0 0}} .chip{{display:inline-block;background:#eef;color:#446;
         border-radius:20px;padding:3px 12px;font-size:12px;margin:2px}}
  .turn{{background:#fff;border:1px solid #eee;border-radius:10px;padding:10px 14px;margin:8px 0}}
  .root{{font-size:14px}} .kid{{font-size:13px;color:#555;padding:3px 0 0 18px;
         border-left:2px solid #eee;margin-left:6px}}
  .kind{{display:inline-block;background:#eee;color:#666;border-radius:5px;
        padding:1px 7px;font-size:11px}} .kind.chat{{background:#dbeafe;color:#1e40af}}
</style></head>
<body>
  <h1>🧠 recall</h1>
  <p class="sub">Local AI brain — memory & cost. Data never leaves this machine. <span class="dim">(auto-refreshes)</span></p>
  <div class="cards">
    <div class="card"><div class="n">{s['memory_count']}</div><div class="l">memories</div></div>
    <div class="card"><div class="n">{s['calls']}</div><div class="l">model calls</div></div>
    <div class="card"><div class="n">{s['input_tokens']+s['output_tokens']:,}</div><div class="l">tokens</div></div>
    <div class="card"><div class="n">${s['cost_usd']:.4f}</div><div class="l">total cost</div></div>
  </div>
  {budget_html}
  <div class="chips">{scope_html}</div>
  <h2>Cost by model</h2>
  <table><tr><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>{model_rows}</table>
  <h2>Memories</h2>
  <table><tr><th>ID</th><th>Memory</th><th>Tags</th></tr>{mem_rows}</table>
  <h2>Recent turns</h2>
  {sessions_html}
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
