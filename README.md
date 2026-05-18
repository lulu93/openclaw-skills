# openclaw-skills

Hermes Agent skills collection.

## Skills

| Skill | Description |
|-------|-------------|
| paper-analyst | 论文精读与分析工作流。下载PDF→提取文本→写分析笔记→更新知识库→同步GitHub |
| volcengine-speech | 火山引擎语音服务（TTS + 豆包语音播客大模型） |
| arxiv-daily-digest | 每日arXiv论文日报：筛选cs.CV论文、TOP分析、邮件发送 |

## Scripts

| Script | Description |
|--------|-------------|
| publish_podcast.py | 播客发布工具 — 上传音频 → 生成RSS Feed → 自动同步GitHub |
| sync_knowledge.sh | 知识库自动同步到GitHub |

## Pipeline

论文 → pro模型精读 → 分析笔记 → 豆包播客 → RSS发布 → GitHub同步
