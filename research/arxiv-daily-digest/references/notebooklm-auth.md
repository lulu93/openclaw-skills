# NotebookLM 认证与播客生成

## 认证方式

notebooklm-py 使用 Google OAuth cookie 认证，存储在 Playwright 格式的 `storage_state.json` 中。

### Cookie 获取（首次）

用户通过浏览器 Cookie Editor 插件导出 Netscape 格式 cookie → 用脚本合并到 storage_state.json：

**关键操作：更新 SIDCC/PSIDCC/PSIDTS 这几个会话cookie**
其他cookie（HSID/SSID/APISID等）通常不变，但 SIDCC/1PSIDCC/3PSIDCC/1PSIDTS/3PSIDTS 每次浏览器登录都会变。

**存储路径：** `/opt/data/profiles/wechat-2/home/.notebooklm/profiles/default/storage_state.json`

合并步骤：
1. 用户导出 Netscape cookie 文件
2. 用 python 解析文件，更新 storage_state.json 中同名cookie的 value/expires
3. 运行 `notebooklm auth check --test` 验证

### Cookie 自动续期

```yaml
cron:
  schedule: "0 */2 * * *"      # 每2小时（不要每15分钟，太频繁）
  deliver: local                # 不通知用户
  command: notebooklm auth refresh --quiet
```

需要 Clash 代理运行中（访问 google.com）。

### Clash 代理规则

需要添加：
```yaml
- DOMAIN-SUFFIX,googleusercontent.com,Proxy  # 音频文件下载
- DOMAIN-SUFFIX,google.com,Proxy              # API访问
```

## Deep Dive Audio 生成

### 单篇 vs 合并

| 方式 | 适合场景 | 说明 |
|:----|:--------|:-----|
| 单篇 | 单篇精读笔记 | 用 `notebooklm_podcast.py --note` |
| 批量 | 多篇独立笔记（日报） | 用 `notebooklm_podcast.py --batch` |
| **合并** | **同分类全集（收藏级）** | **手动合并txt → 手动创建Notebook** |

### 合并多篇笔记为一个播客（收藏级播客）

不要用 `--batch`，手动操作：

```python
# 1. 将所有.md文件合并为一个txt
with open("/tmp/merged.txt", "w") as out:
    out.write("# 分类名称\n\n")
    for md_file in sorted_md_files:
        with open(md_file) as f:
            out.write(f"\n## {title}\n\n{f.read()}\n\n---\n")

# 2. 创建Notebook + 添加Source + 提交音频
nb = await client.notebooks.create("分类名称 全集")
source = await client.sources.add_text(nb.id, "分类合集", merged_content, wait=True)
result = await client.artifacts.generate_audio(nb.id, source_ids=[source.id], 
    audio_length=AudioLength.SHORT, language='zh-CN')
```

**注意：**
- 内容量 20KB~500KB 适合一个播客（太大NotebookLM可能处理不了）
- 66篇3DGS笔记约55KB，效果很好
- 用 `## 标题` 分隔每篇笔记，NotebookLM自动识别章节

### 限流处理

NotebookLM Deep Dive Audio 有**每日生成上限**（hard quota，按Google账号）。

**症状：**
```
API rate limit or quota exceeded. Please wait before retrying.
```

**策略：**
- 不要在同一个账号上频繁重试（每30分钟会消耗更多配额）
- 每2小时重试一次比较合理
- 如果多个播客在排队，合并成一个重试cron
- 限流在次日自然恢复（每日重置）
- Notebook 和 Source 不受限流影响——可以提前创建好

### 播客脚本

```bash
# 正确的Python路径（重要！）
cd /opt/data/profiles/wechat-2/skills/research/arxiv-daily-digest/scripts && \
HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890 \
  /opt/hermes-v0130/.venv/bin/python3 notebooklm_podcast.py \
  --batch /tmp/notes.txt
```

已创建的Notebook IDs（供cron重试）：
- 3DGS 66篇合集: `4dfb4875-3564-4921-865e-e24ce46f3abe`
- PointForward: `59b31bbd-747c-4105-abcd-f5774ff92a85`
