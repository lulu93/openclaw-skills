#!/bin/bash
# 同步知识库到 GitHub
# 用法: bash /opt/hermes/scripts/podcast-tools/sync_knowledge.sh
# 可加在 cron 或 daily 任务中

set -e

VAULT="/opt/data/obsidian-vault"
JSON_SRC="/opt/hermes/arxiv_papers_2024_2026.json"
GITHUB_TOKEN="$(grep -oP '^GITHUB_TOKEN=\K.*' /opt/data/profiles/wechat-2/.env 2>/dev/null || true)"

# 如果没有 token 就退出
[ -z "$GITHUB_TOKEN" ] && echo "ERROR: GITHUB_TOKEN not found" && exit 1

cd "$VAULT"

# 同步 JSON
cp "$JSON_SRC" "$VAULT/arxiv_papers_2024_2026.json"

# 检查是否有变更
if git status --porcelain | grep -q .; then
    git add -A
    git -c user.name="Knowledge Bot" -c user.email="bot@knowledge.local" \
        commit -m "自动同步 $(date '+%Y-%m-%d %H:%M')"
    git push https://lulu93:${GITHUB_TOKEN}@github.com/lulu93/knowledge-base.git main
    echo "✅ 同步完成"
else
    echo "ℹ️ 无变更，跳过"
fi
