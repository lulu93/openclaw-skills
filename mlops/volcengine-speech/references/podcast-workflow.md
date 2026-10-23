# 播客发布全流程

论文分析笔记 → 豆包播客 → RSS发布 → GitHub同步

## 步骤

### 1. 准备话题文本

从分析笔记（.md）中提取正文，**去掉 frontmatter**（`---` 之间的元数据块）：

```python
lines = note.split("\n")
if lines[0].strip() == "---":
    end_idx = 1
    while end_idx < len(lines) and lines[end_idx].strip() != "---":
        end_idx += 1
    topic_text = "\n".join(lines[end_idx+1:]).strip()
```

### 2. 生成播客

使用话题模式（action=0），传入完整笔记全文：

```bash
/opt/hermes/.venv/bin/python3 \
  /opt/data/profiles/wechat-2/skills/mlops/volcengine-speech/scripts/podcast_gen.py \
  "$topic_text" /tmp/podcast_output.mp3
```

话题模式接受任意长度输入（实测 7,974 字/5,169 tokens），豆包自动生成双人对话。

生成时间：简短描述~30秒，完整笔记~5分钟。

### 3. 发布到 RSS

```bash
/opt/hermes/.venv/bin/python3 \
  /opt/hermes/scripts/podcast-tools/publish_podcast.py \
  --title "标题" \
  --audio /tmp/podcast_output.mp3 \
  --desc "描述"
```

发布脚本自动：
- 复制音频到 `/opt/hermes/podcast-feed/audio/`
- 更新 `feed.xml`
- 推送到 `github.com/lulu93/hermes-podcast`

### 4. 最终 RSS 地址

```
https://raw.githubusercontent.com/lulu93/hermes-podcast/main/feed.xml
```

## 注意

- 不要上传到 NAS（用户偏好）
- 知识库仓库 `lulu93/knowledge-base` 是 private
- 发布后小宇宙自动刷新
