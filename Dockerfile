FROM node:22-bookworm-slim AS node

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Node.js runs the Tavily and Gmail MCP servers. Copied from the official image instead of
# apt's npm, which pulls hundreds of Debian packages.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Trust extra root CAs from certs/ (HTTPS-filtering networks). Python's httpx/requests and Node
# do not read the system store by default, hence the explicit bundle variables.
COPY certs/ /usr/local/share/ca-certificates/extra/
RUN find /usr/local/share/ca-certificates/extra -type f ! -name "*.crt" -delete \
    && update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the MiniLM embedding model and the MCP server packages into the image
# so the first CV upload, screening and decision email do not block on downloads.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction; DefaultEmbeddingFunction()(['warmup'])"
RUN npm install -g tavily-mcp@latest
RUN npm install -g @gongrzhe/server-gmail-autoauth-mcp@1.1.11

COPY . .

RUN mkdir -p /app/data /app/uploads /app/chroma_data

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "wsgi:app"]
