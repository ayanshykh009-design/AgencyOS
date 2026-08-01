# AgencyOS n8n image.
# Extends the official image. The compose file mounts workflows/n8n as the
# n8n data directory, so workflow JSON exports remain in git.
FROM n8nio/n8n:latest

# Community nodes can be pre-installed here once chosen, e.g.:
# RUN npm install -g n8n-nodes-supabase
# Credentials/keys must come from environment variables, never baked in.

EXPOSE 5678
