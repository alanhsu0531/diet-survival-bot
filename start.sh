#!/bin/bash
# ============================================================
# AI 減肥生存管家 — Docker 容器啟動腳本
# ============================================================
# 同時啟動兩個服務：
#   1. OmniRoute (背景) — Node.js AI 閘道，監聽 20128 埠
#   2. uvicorn (前景) — FastAPI 伺服器，監聽 8000 埠
#
# OmniRoute 設定會透過環境變數傳入（由 Koyeb/Railway 設定）
# ============================================================

set -e

echo "=== 🚀 啟動 AI 減肥生存管家 ==="
echo "  Python: $(python3 --version)"
echo "  Node.js: $(node --version)"
echo "  OmniRoute: $(omniroute --version 2>/dev/null || echo 'unknown')"
echo "  AI Model: ${AI_MODEL:-auto/best-fast}"
echo ""

# ---------- 啟動 OmniRoute（背景） ----------
echo "=== 🔧 啟動 OmniRoute 伺服器 (port 20128) ==="

# 如果使用者有設定 API Key 的環境變數，OmniRoute 會自動讀取
# 常見的環境變數格式（依你的 OmniRoute 設定而定）：
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-...
# 不需在此額外設定，直接傳遞環境變數即可

# 建立資料目錄
mkdir -p "$OMNIROUTE_DATA_DIR" 2>/dev/null || true

# 在背景啟動 OmniRoute
omniroute --port 20128 --host 0.0.0.0 --data-dir "$OMNIROUTE_DATA_DIR" &
OMNIROUTE_PID=$!

echo "  OmniRoute PID: $OMNIROUTE_PID"

# 等待 OmniRoute 就緒（最多等 30 秒）
echo "  等待 OmniRoute 就緒..."
for i in $(seq 1 30); do
    if curl -s http://localhost:20128/v1/models > /dev/null 2>&1; then
        echo "  ✅ OmniRoute 就緒！（耗時 ${i}s）"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "  ⚠️  OmniRoute 未在時限內就緒，仍繼續啟動伺服器"
    fi
    sleep 1
done

# ---------- 啟動 FastAPI 伺服器（前景） ----------
echo ""
echo "=== 🔥 啟動 FastAPI 伺服器 (port 8000) ==="

# 使用 uvicorn 啟動 FastAPI 應用
# Koyeb 會設定 PORT 環境變數，預設 8000
PORT="${PORT:-8000}"

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --log-level info
