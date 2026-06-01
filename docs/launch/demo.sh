#!/usr/bin/env bash
# Demo script for the README GIF. Records a tight ~40s story:
# memory persists across models + cost is tracked, all local.
#
# Record with asciinema (then convert to GIF with agg):
#   asciinema rec demo.cast -c "bash docs/launch/demo.sh"
#   agg demo.cast docs/launch/demo.gif        # https://github.com/asciinema/agg
#
# Needs: pip install 'memstash[openai]'  and  export OPENAI_API_KEY=...
# (Or swap to `ollama` for a fully-local, key-free recording.)
set -e
export MEMSTASH_HOME="$(mktemp -d)"          # clean store for the demo

type() { printf '\033[1;36m$ %s\033[0m\n' "$*"; "$@"; echo; sleep 1; }

clear
echo "# memstash — local-first memory + cost tracking for any LLM"; echo; sleep 1

type memstash add "I prefer concise answers with tables" --tags style
type memstash add "I do A-share & HK quant research" --tags work

echo "# Chat — it already knows you, and the call is traced:"; sleep 1
type memstash chat openai gpt-4o-mini "How should you reply to me, and what do I work on?"

echo "# Switch to a different model — same memory follows you:"; sleep 1
type memstash chat openai gpt-4o "Remind me what I work on."

echo "# See exactly what you spent — all local, one SQLite file:"; sleep 1
type memstash stats

echo "# Everything lives in ~/.memstash/memstash.db. No server, no account."; sleep 2
