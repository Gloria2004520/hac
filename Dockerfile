FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    VIDEO_BACKEND_URL=http://127.0.0.1:8000 \
    DATABASE_URL=sqlite:////data/cookclip.db \
    LOCAL_STORAGE_ROOT=/data/storage

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY scripts/start-production.sh ./scripts/start-production.sh

# --- YouTube 下载加固（机房 IP 反风控三件套）---
# 1) Deno：yt-dlp EJS n-challenge 解算器的运行时（debian 源里没有，直接取官方二进制）
RUN python -c "import urllib.request,zipfile,io; d=urllib.request.urlopen('https://github.com/denoland/deno/releases/download/v2.9.7/deno-x86_64-unknown-linux-gnu.zip', timeout=300).read(); zipfile.ZipFile(io.BytesIO(d)).extract('deno','/usr/local/bin')" \
    && chmod +x /usr/local/bin/deno
# 2) bgutil POT 提供器服务端：yt-dlp 插件（requirements.txt 里的 bgutil-ytdlp-pot-provider）
#    会请求 http://127.0.0.1:4416 拿 BotGuard token。基础镜像没带 npm，用 npm-cli 引导安装。
RUN python -c "import urllib.request,tarfile,io; d=urllib.request.urlopen('https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/2.0.1.tar.gz', timeout=300).read(); tarfile.open(fileobj=io.BytesIO(d), mode='r:gz').extractall('/opt')" \
    && python -c "import urllib.request,tarfile,io; d=urllib.request.urlopen('https://registry.npmjs.org/npm/-/npm-10.9.0.tgz', timeout=300).read(); tarfile.open(fileobj=io.BytesIO(d), mode='r:gz').extractall('/opt/npm-bootstrap')" \
    && cd /opt/bgutil-ytdlp-pot-provider-2.0.1/server \
    && node /opt/npm-bootstrap/package/bin/npm-cli.js install --no-audit --no-fund \
    && node node_modules/typescript/bin/tsc \
    && rm -rf /opt/npm-bootstrap

RUN chmod +x ./scripts/start-production.sh \
    && mkdir -p /data/storage

EXPOSE 8080

CMD ["./scripts/start-production.sh"]
