FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 git curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code @openai/codex opencode-ai
RUN curl -fsSL https://cursor.com/install -o /tmp/cursor-install.sh && HOME=/opt/cursor bash /tmp/cursor-install.sh && chmod -R a+rX /opt/cursor && rm /tmp/cursor-install.sh
ENV PATH="/opt/cursor/.local/bin:${PATH}"
COPY scripts/evaluation_container.py /opt/basis/scripts/
USER node
WORKDIR /work
ENTRYPOINT ["python3", "/opt/basis/scripts/evaluation_container.py"]
