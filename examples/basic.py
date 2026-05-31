"""Minimal library example.

Run after: pip install 'zion-recall-ai[openai]'  (and set OPENAI_API_KEY)
"""

from recall import Recall

r = Recall()

# Teach it about you (persisted locally, reused across runs and models).
r.remember("I prefer concise answers with tables", tags=["style"])
r.remember("I do A-share and HK quant research", tags=["work"])

# Chat — memory is auto-injected, the call is auto-traced.
out = r.chat("openai", "gpt-4o-mini", "How should you reply to me, and what do I work on?")
print(out.text)

# Observability — see what you spent.
print("\n--- stats ---")
print(r.stats())

r.close()
