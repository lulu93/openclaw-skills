---
name: paper-analyst
description: "论文精读与分析专家：下载论文、提取文本、写分析笔记、更新知识库。使用pro模型执行，专用于深度分析任务。"
version: 1.1.0
author: Hermes Agent
prerequisites:
  commands: [curl, python3, ffprobe]
  files: [arxir_papers_2024_2026.json, obssidian-vault]
---

# Paper Analyst Skill

专用于**论文精读与分析笔记**工作流。设计为通过 cron job 调用时使用 pro 模型（deepseek-v4-pro）以获得最佳推理质量。

由于 `delegate_task` 不支持子 agent 独立换模型，使用 **`cronjob` 的 model override** 是让子 agent 用不同模型跑分析任务的唯一方式。

## 使用方式

### 方式一：一次性 cron job（推荐，可换模型）

主 agent 创建一条带 pro 模型的一次性 cron job：

```python
# 由主 agent 执行（不是子 agent）
cronjob(
    action="create",
    name="分析 arXiv:XXXX.XXXXX (pro模型)",
    prompt="分析论文... 完成后写笔记、更新JSON、同步GitHub",
    skills=["paper-analyst"],
    model={"provider": "deepseek", "model": "deepseek-v4-pro"},
    schedule="in 1 min",  # 或 ISO时间，但注意⚠️必须晚于当前时间
    deliver="origin",     # 结果发回当前对话
    enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)
```

**⚠️ schedule 时间坑：** 时间格式如 `in 1 min`（推荐，自动计算）或用 ISO 时间如 `2026-05-19T06:00:00`。如果用 ISO 时间且已过点，任务不会触发。创建后：
- 若立即跑：`cronjob(action="run", job_id="...")`
- 若等到点：等待 cron scheduler 触发

**执行结果：** 子 agent 的最终回复会自动发回 origin（当前微信对话），主 agent 和用户都能看到。

### 方式二：手动机

主 agent 直接用 pro 模型分析：
1. 发 `/model deepseek/deepseek-v4-pro` 切换
2. 加载 paper-analyst skill
3. 执行分析
4. 切回 `/model deepseek/deepseek-v4-flash`

### 方式三：定时任务（每日6:00）

见 论文分析（pro模型） cron job ID `57cb48d5a00b`，每天6:00自动跑，处理 arXiv 日报新增论文。

### 方式四：通过微信命令

用户说"精读 2401.10891" → 创建一条一次性 cron job 带 model override：
```python
cronjob(action='create',
  name='分析论文XXX (pro模型)',
  skills=['paper-analyst'],
  model={'model': 'deepseek-v4-pro', 'provider': 'deepseek'},
  schedule='<时间>',  # 用当前时间+1分钟
  prompt='分析论文 XXX (arXiv:XXXX.XXXXX)...'
)
```
cron job 用 pro 模型运行，结果自动发回微信。比 `delegate_task` 更灵活（后者不能独立设置模型）。

**已验证（2026-05-18）：** SLAM-Former 分析（2509.16909）使用此模式成功，pro 模型生成 280 行完整分析笔记，写入 Obsidian + 更新 JSON + 同步 GitHub。
**已验证（2026-05-18）：** PointForward 分析（2605.11594）已有笔记，无需 pro 模型，直接用完整笔记生成播客。

---

## 核心工作流

### 第1步：论文检查与去重

**双重验证机制（防止幻觉/错误摘要）：**

1. **查标题**：先访问 arXiv 页面获取真实标题
   ```bash
   curl -sL "https://arxiv.org/abs/XXXX.XXXXX" | grep -oP '<meta name="citation_title" content="\K[^"]+'
   ```

2. **查核心贡献**：下载PDF提取摘要，确认核心内容

3. **去重检查**：搜索 `/opt/data/obsidian-vault/论文笔记/` 下是否已存在笔记（按 arxiv ID 或标题关键词匹配）

4. **JSON 元数据检查**：搜索 `/opt/hermes/arxiv_papers_2024_2026.json` 确认论文是否已在知识库中

### 第2步：下载与提取

```bash
# 下载 PDF
curl -sLo /tmp/paper_XXXX.pdf "https://arxiv.org/pdf/XXXX.XXXXXv2.pdf"

# 提取文本（前2页摘要）
python3 -c "
from pypdf import PdfReader
reader = PdfReader('/tmp/paper_XXXX.pdf')
for i, page in enumerate(reader.pages[:2]):
    print(f'=== Page {i+1} ===')
    print(page.extract_text())
"
```

**⚠️ 关键坑：**
- pypdf 提取 WSL 系统上可能不支持中文文件名，用纯 ID 命名
- 某些 PDF 的文本层是 OCR 或不标准格式，pypdf 可能提取为空，此时需用 `pdftotext` 备选
- 只用前2页（title + abstract + intro），减少 token 消耗

### 第2.5步：提取模型架构图（仅对模型/方法类论文）

如果论文包含方法/模型架构图（通常是 Figure 1 或 "Method Overview"），将第一页渲染为图片保存到附件目录，在笔记中嵌入：

```bash
# 用 PyMuPDF 将 PDF 第一页渲染为图片
python3 << 'PYEOF'
import fitz
doc = fitz.open("/tmp/paper_XXXX.pdf")
page = doc[0]  # 第一页通常包含架构图
# 高分辨率渲染（300 DPI）
pix = page.get_pixmap(dpi=300)
img_path = f"/opt/data/obsidian-vault/附件/{arxiv_id}_fig1.png"
pix.save(img_path)
print(f"✅ 架构图已保存: {img_path}")
doc.close()
PYEOF
```

在笔记中引用：
```markdown
![架构图](附件/{arxiv_id}_fig1.png)
```

**注意：**
- 并非所有论文的架构图都在第一页（有些在第二页或更后），如果第一页渲染后发现没有架构图（只有标题+摘要），可以尝试第2页
- 对于纯理论/评测/数据集论文可能没有架构图，跳过此步
- 图片会上传到 GitHub 知识库，注意不要太大（300 DPI 通常 ~2-5MB，不影响）

### 第3步：精读与分析

使用 pro 模型进行深度分析，输出结构：

1. **论文元信息**：标题、作者、单位、年份、arXiv ID
2. **核心思想**（2-3句话）
3. **技术方法**（关键组件、架构）
4. **创新点**（与已有工作的区别）
5. **实验结论**（数据集、指标、数值）
6. **与知识库的关联**（链接到已有笔记，定位在 3D 重建生态中的位置）
7. **优缺点评价**
8. **延伸思考**（未来方向、可复现性）

### 第4步：写分析笔记

Obsidian Markdown 格式，写入 `/opt/data/obsidian-vault/论文笔记/{category}/`：

```markdown
---
title: 论文名
arxiv_id: XXXX.XXXXX
created: YYYY-MM-DD
tags: [category1, category2]
---

# 论文名

> arXiv: [XXXX.XXXXX](https://arxiv.org/abs/XXXX.XXXXX) | 机构 | YYYY

## 核心思想

...

## 技术方法

...

## 创新点

...

## 实验结论

| 数据集 | 指标 | 数值 |
|--------|------|------|
| ... | ... | ... |

## 知识库关联

- 关联 [[已有笔记]]
- 定位：在前馈重建演化路线中的位置

## 评价

**优点：** ...
**不足：** ...

## 延伸思考

...
```

**⚠️ 去重检查与覆盖策略：**
- 写入前用 `search_files()` 或 `os.listdir()` 检查目标目录
- 如果 arxiv ID 相同但之前笔记不完整，可以覆盖更新
- 如果已存在完整笔记，则跳过写入

### 第5步：更新 JSON 知识库

将新论文元数据追加到 `/opt/hermes/arxiv_papers_2024_2026.json`：

```python
import json
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
# data 是列表，每项为 {title, arxiv_id, year, category, abstract, ...}
data.append(new_entry)
with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

### 第6步：同步到 GitHub

分析笔记写入知识库后，运行同步脚本推送变更：

```bash
bash /opt/hermes/scripts/podcast-tools/sync_knowledge.sh
```

### 第7步（可选）：生成播客

分析完成后，可为该论文生成 豆包语音播客 并发布到小宇宙 RSS。

有两种方式：

**方式A：短话题（快速出，2min）**
```bash
/opt/hermes/.venv/bin/python3 /opt/hermes/scripts/podcast-tools/gen_and_publish.py \
  "论文名: 核心话题" "简述论文内容..."
```

**方式B：完整笔记作为话题（15min+，更详细）**
```bash
# 读取刚写好的笔记，去除frontmatter后传给豆包
python3 -c "
lines = open('/path/to/note.md').read().split('\\n')
if lines[0].strip() == '---':
    end = next(i for i in range(1,len(lines)) if lines[i].strip()=='---')
    text = '\\n'.join(lines[end+1:]).strip()
else:
    text = open('/path/to/note.md').read()
open('/tmp/topic.txt', 'w').write(text)
"
# 用后台模式（完整笔记需300s+超时）
/opt/hermes/.venv/bin/python3 /opt/data/profiles/wechat-2/skills/mlops/volcengine-speech/scripts/podcast_gen.py \
  "$(cat /tmp/topic.txt)" /tmp/podcast.mp3
# 发布
/opt/hermes/.venv/bin/python3 /opt/hermes/scripts/podcast-tools/publish_podcast.py \
  --title "论文名" --audio /tmp/podcast.mp3 --desc "..."
```

**已验证**：SLAM-Former 分析后，300字话题→2:15播客；13KB完整笔记→30轮对话播客（需要300s+）。
参见 `self-built-podcast` skill 获取完整播客建指南。

---

## 分类目录

论文笔记按以下目录组织（`/opt/data/obsidian-vault/论文笔记/`）：

| 目录 | 说明 |
|------|------|
| `3DGS/` | 3D Gaussian Splatting 相关 |
| `NeRF/` | NeRF 相关 |
| `Feed-Forward 前馈重建/` | 前馈式3D重建 |
| `3D-VLM（视觉语言模型）/` | 3D VLM/LLM |
| `3D 生成/` | 3D内容生成 |
| `3D 分割/` | 3D分割 |
| `3D 目标检测/` | 3D检测 |
| `3D 基准评测/` | 基准与数据集 |
| `3D 数据集/` | 数据集 |
| `3D 综述/` | Survey论文 |
| `SLAM/` | SLAM相关 |
| `深度估计/` | 深度估计 |
| `扩散模型/` | 扩散模型架构 |
| `隐式表示/` | 隐式表示/Neural Field |
| `统一3D框架/` | 统一框架 |
| `分析笔记/` | 综合分析笔记 |

---

## 注意事项

- **诚实归因**：明确区分"论文原文结果"vs"个人推断"
- **封面图片**：分析笔记可选配图片，使用 `![alt](url)` 格式
- **双向链接**：使用 `[[已有笔记]]` 语法建立知识库关联
- **避免重复**：每次写笔记前先检查是否已存在
- **同步GitHub**：分析完成后一定运行 `sync_knowledge.sh` 同步
- **模型选择**：本 skill 设计为使用 pro 模型运行，在 cron job 中通过 `model: {"model": "deepseek-v4-pro", "provider": "deepseek"}` 指定

## 参考文件

- `references/cron-subagent-model-override.md` — cron job 替代 delegate_task 实现独立模型的模式详解
- `references/cross-paper-comparison.md` — 跨论文对比分析方法与维度框架
- `references/20260518-session-log.md` — 2026-05-18 会话日志 论文分析
- `templates/cron-job-paper-analysis.md` — 一次性 cron job 创建模板（含时间坑提示）
