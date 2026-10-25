FROM python:3.11-slim AS rustscan-builder

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential \
    && rm -rf /var/lib/apt/lists/*

# === RUSTSCAN ===
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . $HOME/.cargo/env && \
    cargo install rustscan && \
    cp $HOME/.cargo/bin/rustscan /usr/local/bin/rustscan && \
    chmod +x /usr/local/bin/rustscan && \
    rm -rf $HOME/.cargo $HOME/.rustup

FROM python:3.11-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates nmap chromium curl wget unzip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=rustscan-builder /usr/local/bin/rustscan /usr/local/bin/rustscan

# === PIP requirements (ДО httpx!) ===
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# === GOWITNESS ===
RUN wget -q https://github.com/sensepost/gowitness/releases/download/3.0.5/gowitness-3.0.5-linux-amd64 -O /usr/local/bin/gowitness && \
    chmod +x /usr/local/bin/gowitness

# === HTTPX ProjectDiscovery (ПОСЛЕ pip) ===
RUN wget -q https://github.com/projectdiscovery/httpx/releases/download/v1.6.0/httpx_1.6.0_linux_amd64.zip -O /tmp/httpx.zip && \
    unzip /tmp/httpx.zip -d /tmp/httpx && \
    mv /tmp/httpx/httpx /usr/local/bin/httpx && \
    chmod +x /usr/local/bin/httpx && \
    rm -rf /tmp/httpx*

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
