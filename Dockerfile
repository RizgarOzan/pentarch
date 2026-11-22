# Pentarch in a container: docker compose run --rm pentarch python setup.py, then docker compose up -d.
# AGENT_CLI picks the brain baked in: claude | gemini | codex | opencode | none (none = agent.cli "api", your own model).
# VOICE=false skips faster-whisper and edge-tts, which make the image a few hundred MB bigger.
# Node 22 comes from the official image: Debian's own nodejs is v18, too old for the agent CLIs.
FROM node:22-slim AS node
FROM python:3.12-slim

ARG AGENT_CLI=claude
# Pinned so a build is repeatable; override with --build-arg CLAUDE_VER=... to move up.
ARG CLAUDE_VER=2.1.329
ARG GEMINI_VER=0.70.0
ARG CODEX_VER=0.171.0
ARG OPENCODE_VER=1.19.6
ARG VOICE=true

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN case "$AGENT_CLI" in \
      claude) npm install -g @anthropic-ai/claude-code@${CLAUDE_VER} ;; \
      gemini) npm install -g @google/gemini-cli@${GEMINI_VER} ;; \
      codex) npm install -g @openai/codex@${CODEX_VER} ;; \
      opencode) npm install -g opencode-ai@${OPENCODE_VER} ;; \
      none) ;; \
      *) echo "AGENT_CLI must be claude, gemini, codex, opencode or none" && exit 1 ;; \
    esac \
 && rm -rf /root/.npm

WORKDIR /opt/pentarch
COPY requirements.txt .
RUN if [ "$VOICE" = "true" ]; then pip install --no-cache-dir -r requirements.txt; fi

COPY . .
# The career tracker keeps its state next to its code. Point that state at the home volume so it survives rebuilds
# (a named volume is filled from the image the first time it is used).
RUN useradd --create-home --uid 1000 pentarch  && mkdir -p /home/pentarch/tracker-state/data /home/pentarch/tracker-state/out  && ln -s /home/pentarch/tracker-state/data tracker/data  && ln -s /home/pentarch/tracker-state/out tracker/out  && ln -s /home/pentarch/tracker-state/profile.json tracker/profile.json  && ln -s /home/pentarch/tracker-state/config.json tracker/config.json  && chown -R pentarch:pentarch /home/pentarch /opt/pentarch
USER pentarch

# PENTARCH_DOCKER: setup skips systemd and says how to start; PENTARCH_PANEL_BIND: the panel listens inside the
# container, and compose publishes it on the host's 127.0.0.1 only.
ENV PENTARCH_DOCKER=1 PENTARCH_SUPERVISED=1 PENTARCH_PANEL_BIND=0.0.0.0 PYTHONUNBUFFERED=1
EXPOSE 47824
HEALTHCHECK --interval=1m --timeout=5s --start-period=30s CMD python -c "import socket; socket.create_connection(('127.0.0.1', 47824), 3)"
# Exit 78 = Telegram rejected the token. Restarting would only loop, so wait for the owner to fix it.
CMD ["sh", "-c", "python -u -I app/pentarch.py --quiet & p=$!; trap 'kill -TERM $p' TERM INT; wait $p; c=$?; if [ $c -eq 78 ]; then echo 'Telegram token rejected. Fix it: docker compose run --rm pentarch python setup.py, then docker compose restart'; sleep infinity; fi; exit $c"]
