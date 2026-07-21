# ============================================================
# AI 減肥生存管家 — Dockerfile
# ============================================================
# 使用方式：
#   docker build -t diet-bot .
#   docker run -p 8000:8000 --env-file .env diet-bot
#
# 部署到 Koyeb：
#   1. git push 到 GitHub
#   2. Koyeb 匯入 GitHub repo
#   3. Koyeb 會自動偵測 Dockerfile 並建置
# ============================================================

# ---------- 第一階段：基礎環境 ----------
# 使用 Python 3.11 slim 作為基底（體積小、速度快）
FROM python:3.11-slim AS build

# 設定工作目錄
WORKDIR /app

# 安裝 Node.js 18.x（OmniRoute 需要 Node.js 環境）
# NodeSource 提供的安裝腳本
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安裝 OmniRoute（作為 Node.js 全域套件）
RUN npm install -g omniroute@3.8.48 && \
    npm cache clean --force

# 複製 Python 相依套件列表並安裝
# 放在前面以便利用 Docker layer cache（requirements.txt 不改就不重安裝）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------- 第二階段：應用程式 ----------
FROM build AS runtime

# 複製專案程式碼
COPY main.py .
COPY ai_processor.py .
COPY notion_writer.py .
COPY start.sh .

# 設定執行權限
RUN chmod +x start.sh

# 建立非 root 使用者（安全性考量）
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# OmniRoute 儲存目錄（API tokens 快取等）
ENV OMNIROUTE_DATA_DIR=/app/data

# 設定環境變數預設值
# 【注意】實際部署時須在 Koyeb 後台覆蓋這些變數
ENV LINE_CHANNEL_SECRET=""
ENV LINE_CHANNEL_ACCESS_TOKEN=""
ENV NOTION_TOKEN=""
ENV DATABASE_ID=""
ENV AI_MODEL=auto/best-fast
ENV OMNIROUTE_BASE_URL=http://localhost:20128/v1

# 暴露兩個埠口：
#   8000 — FastAPI 伺服器（Line Webhook）
#   20128 — OmniRoute API（只在容器內部使用）
EXPOSE 8000
EXPOSE 20128

# 啟動腳本：先啟動 OmniRoute 背景服務，再啟動 uvicorn
CMD ["./start.sh"]
