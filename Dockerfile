FROM node:20-slim

# Python for FastAPI + Claude Code CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# non-root user (claude refuses --dangerously-skip-permissions as root)
RUN useradd -m agent
USER agent
WORKDIR /home/agent/app

ENV PATH="/home/agent/.venv/bin:$PATH"
RUN python3 -m venv /home/agent/.venv

COPY --chown=agent:agent requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=agent:agent src/ ./src/

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
