---
name: paper-analyst
description: "论文精读与分析专家：下载论文、提取文本、写分析笔记、更新知识库。使用pro模型执行，专用于深度分析任务。"
version: 1.37.0
author: Hermes Agent
prerequisites:
  commands: [curl, python3, ffprobe]
  files: [arxir_papers_2024_2026.json, obssidian-vault]
---

# Paper Analyst Skill

专用于**论文精读与分析笔记**工作流。设计为通过 cron job 调用时使用 pro 模型（deepseek-v4-pro）以获得最佳推理质量。

由于 `delegate_task` 不支持子 agent 独立换模型，使用 **`cronjob` 的 model override** 是让子 agent 用不同模型跑分析任务的唯一方式。

## 使用方式

### ⚠️ 论文+GitHub 仓库双重分析模式

**场景：** 用户要求"精读论文和GitHub仓库"（如 DPT 解码器）。在一次性 cron job 的 prompt 中需同时包含论文分析和仓库分析两部分。

**在 prompt 中注入仓库分析要求：**

```python
prompt = """深度精读论文 + GitHub 仓库。

## 论文信息
- 标题：Vision Transformers for Dense Prediction
- arXiv ID: 2103.13413

## GitHub 仓库
- 主仓库：https://github.com/isl-org/MiDaS
- DPT 实现在此仓库的 `midas/` 目录中

## 分析要求

### 论文方面
（标准 paper-analyst 分析内容）

### GitHub 仓库方面
1. **仓库结构与组织**：主要代码文件、目录结构
2. **模型定义**：关键文件（如 `dpt_depth.py`）中解码器的具体实现
   - 核心函数/类的 signature 和实现细节
   - 关键参数（上采样模式、卷积核大小、通道数）
   - 最终 head 的设计
3. **预训练权重**：提供的模型系列及其区别
4. **推理代码**：加载模型、前向传播流程、后处理
5. **关键文件阅读**：列出需阅读的核心文件及其作用
"""
```

**GitHub 信息获取方法（优先顺序）：**
1. 用 `curl -sL "https://raw.githubusercontent.com/{user}/{repo}/main/README.md"` 获取 README
2. 用 `curl -sL "https://github.com/{user}/{repo}"` 获取 star 数（从 HTML 提取）
3. 用 `curl -sL "https://api.github.com/repos/{user}/{repo}"` 获取仓库信息（注意 API 限流）
4. 注意：GitHub API 有 rate limit，用 Web 页面 HTML 解析作为备用

**⚠️ GitHub API 限流：** 未认证的 GitHub API 请求有严格速率限制（~60 req/hour/ip）。
- 优先用 HTML 页面提取 star/desc：`curl -sL "https://github.com/user/repo" | grep -oP 'Counter[^>]*>[\d,]+<'`
- API 限流时返回 `{"message":"API rate limit exceeded"}`，此时转用 Web 页面解析

**笔记结构：** 仓库分析不单独成篇，而是作为论文笔记中「技术方法」和「思路起源与发展脉络」的一部分。源码细节写在「技术方法」中对应组件的旁边，用 `⚠️ 源码细节` 标记。

### 方式一：一次性 cron job（推荐，可换模型）

**⚠️ 黄金规则：创建前必须先 `date` 确认当前系统时间。** 凭感觉估算时间会导致任务排到已过去的时间点，静默不触发。

主 agent 创建一条带 pro 模型的一次性 cron job：

```python
# 由主 agent 执行（不是子 agent）
cronjob(
    action="create",
    name="分析 arXiv:XXXX.XXXXX (pro模型)",
    prompt="分析论文... 完成后写笔记、更新JSON、同步GitHub",
    skills=["paper-analyst"],
    model={"provider": "deepseek", "model": "deepseek-v4-pro"},
    schedule="1m",  # ⚠️ 用户偏好：主动请求精读时用1m，默认值已从30m改为1m
    deliver="origin",     # 结果发回当前对话
    enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)
```

**⚠️ schedule 时间坑：** cron job 的 schedule 参数不支持 `in 1 min` 格式。可用的格式：
- 持续时间（一次性）：`1m`, `30m`, `2h`, `1d`
- ISO 时间（一次性）：`2026-05-19T06:00:00`（注意：如果时间已过，任务不会触发）
- 周期执行：`every 30m`, `every 2h`
- Cron 表达式：`0 9 * * *`
- 若立即跑：`cronjob(action="run", job_id="...")`
- 若等到点：等待 cron scheduler 触发

**⚠️ 用户偏好：主动请求时用 `1m` 调度，不要默认 `30m`。** 用户说"精读"后等太久会催你改短。这是 2026-05-22 多次出现的纠正。主动请求场景的 cron 用 `1m`。

**执行结果：** 子 agent 的最终回复会自动发回 origin（当前微信对话），主 agent 和用户都能看到。

**批量 pro 模型精读（多篇并发，已验证 2026-05-26）：** 当需要一次性精读多篇论文且全部用 pro 模型时，创建多条 cron job 错峰执行。单条 cron job 不支持并发，但多条 cron job（schedule 各差 1-2 分钟）可并行运行不冲突。每条独立下载 PDF、写笔记到 vault，互不干扰。

```python
# 主 agent 创建 3 条错峰 cron job（LangFlash 实战模式）
cronjob(action="create", name="精读 论文A",
  skills=["paper-analyst"],
  model={"provider": "deepseek", "model": "deepseek-v4-pro"},
  schedule="1m",   # 第一条1分钟后启动
  prompt="深度精读 arXiv:XXXX.XXXXX ... 写笔记更新JSON同步GitHub",
  enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)

cronjob(action="create", name="精读 论文B",
  skills=["paper-analyst"],
  model={"provider": "deepseek", "model": "deepseek-v4-pro"},
  schedule="2m",   # 第二条错峰2分钟
  prompt="深度精读 arXiv:XXXX.XXXXX ... 写笔记更新JSON同步GitHub",
  enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)
# 第三条用 schedule="2m" 同上；不必担心写冲突——各写不同文件
```

每条 cron job 独立运行，pro 模型精读各自论文，最终结果自动发回 origin。注意每条 job 的 prompt 要自包含（url/路径/id 全在里面），因为 cron 在新 session 中执行。

### 方式二：手动机

主 agent 直接用 pro 模型分析：
1. 发 `/model deepseek/deepseek-v4-pro` 切换
2. 加载 paper-analyst skill
3. 执行分析
4. 切回 `/model deepseek/deepseek-v4-flash`

### 方式三：定时任务（每日6:00）

见 论文分析（pro模型） cron job ID `57cb48d5a00b`，每天6:00自动跑。

**⚠️ 时序关系：** arXiv 每日日报 cron（`0f38955352a5`）在 **7:30 AM** 运行，论文分析 cron 在 **6:00 AM** 运行。因此论文分析 job 实际处理的是**昨天的 arXiv 日报新增论文**（或更早的未分析论文），而非当天的。

**每日 cron job 执行流程（无显式指定论文时）：**
1. 读取 `/opt/hermes-notes/arxiv_sent_ids.txt` 获取已发送论文 ID
   - **⚠️ 文件格式解析**：该文件每行格式为 `     N|XXXX.XXXXX`（行号 + 竖线 + arXiv ID），**不要直接用 `line.strip()` 当 ID**——会得到 `"1|2605.07041"` 而非 `"2605.07041"`
   - 正确解析方式：`re.search(r'(\d{4}\.\d{4,5})', line)` 提取纯 arXiv ID
2. 交叉对比 `/opt/hermes/arxiv_papers_2024_2026.json` 和 vault 中已有笔记
   - **⚠️ 必须用 frontmatter `arxiv_id` 字段匹配，不能用文件名**（vault 文件名使用论文标题，不含 arXiv ID 数字）
   - 扫描策略：遍历 vault 所有 .md → 读 frontmatter 提取 `arxiv_id` 或 `arxiv:` → 建立 id→path 映射
   - **⚠️ frontmatter 格式双模式匹配**：部分旧笔记使用 `arxiv:` （无 `_id` 后缀，如 `arxiv: 2605.07287`），必须同时匹配两种格式：
     ```python
     m = re.search(r'^(?:arxiv_id|arxiv):\s*(\S+)', content, re.MULTILINE)
     if m:
         # ⚠️ 只用 re.sub 剥离版本后缀 v1/v2，不能用 rstrip('v0123456789')（会错误剥离末尾数字如 2605.14315→2605.1431）
         aid = re.sub(r'v\d+$', '', m.group(1))
     ```
   - 备选：对缺少 frontmatter 的旧笔记，从内容中搜索 `arxiv.org/abs/XXXX.XXXXX` URL
3. 过滤出「已发送但未深度分析」的论文
   - 已分析 = vault 中有该 arXiv ID 的笔记 **且** JSON 中 `笔记路径` 字段非空
   - 未分析 = JSON 中有但 vault 无笔记，或 vault 有但 JSON `笔记路径` 缺失
4. 按 arXiv ID 排序（越新越优先），选取 TOP 1-2 篇精读
5. 优先选择前馈重建/VGGT/3DGS 相关的核心方向论文
6. 同步到 GitHub 前先检查代理（见第6步）

### 方式五（新增）：批量并行深度精读（flash模型，3个并发）

**场景：** 用户要求一次性精读多篇论文（如"把这些都精读一遍"）。

**工作流（已验证 2026-05-18 和 2026-05-20，含合并笔记拆分模式）：**

1. **分类规划**：按子趋势分组（视觉基础模型 / 前馈核心 / 流式重建 / TTT 方向 / 3D生成），每组 2-3 篇
2. **并行执行**：使用 `delegate_task` 的 `tasks` 数组参数，每条 task 一篇论文，**最多 3 个并发**
3. **每个子 agent 的工作**：
   - 下载 PDF：`curl -sLo /tmp/paper_ID.pdf https://arxiv.org/pdf/ID.pdf`
   - pypdf 提取全文，精读
   - 提取架构图（fitz，方案A优先。⚠️ 只保存架构图本身，不要提取全部嵌入式图片——PDF每张图表/子图都会被解出，造成 repo 冗余）
   - 撰写结构化分析笔记（200+行），**直接 write_file 写入 vault 目标路径**（在 context 中指定文件路径即可）
4. **父 agent 验证**：所有子 agent 完成后，验证文件名和大小即可，无需再收集/搬运文件
   - **推荐：在 context 中指定 target 路径**，让子 agent 直接 write_file 写入 vault
   - 示例 context: `"现有笔记路径: /opt/data/obsidian-vault/论文笔记/{category}/{name}.md（占位符，需覆盖）"`
   - 如果子 agent 写到了临时路径，用 `ls /root/*.md /tmp/*.md 2>/dev/null` 搜索收集
5. **⚠️ 审计（2026-05-19 必做）**：子 agent 可能自报告成功但没写文件。写入 vault 后执行：
   ```bash
   ls -la /opt/data/obsidian-vault/论文笔记/{分类}/论文名.md
   ```
   确认文件存在再 commit。同时执行 JSON `笔记路径` 扫补（见第4.5步）。
6. **⚠️ 修复 frontmatter（2026-05-20 批量11篇时发现）**：子 agent 写的笔记**缺少 frontmatter**（arxiv_id/title/tags）。主 agent 收集后必须为每篇添加 frontmatter 并更新 JSON。示例如下：
   ```python
   for name, arxiv_id, tags in notes:
       with open(f"/tmp/note_{name}.md") as f:
           content = f.read()
       tags_str = ", ".join(tags)
       fm = f"""---
   title: {name}
   arxiv_id: {arxiv_id}
   created: {datetime.now().strftime("%Y-%m-%d")}
   tags: [{tags_str}]
   ---

   """
       with open(f"/opt/data/obsidian-vault/论文笔记/{category}/{name}.md", 'w') as f:
           f.write(fm + content)
       # 同时更新 JSON 笔记路径
   ```

**模板：**
```python
# 主 agent 执行
tasks = [
    {"goal": "精读论文 A (arXiv:XXXX.XXXXX)", "context": "...", "toolsets": ["terminal", "file", "web"]},
    {"goal": "精读论文 B (arXiv:XXXX.XXXXX)", "context": "...", "toolsets": ["terminal", "file", "web"]},
    {"goal": "精读论文 C (arXiv:XXXX.XXXXX)", "context": "...", "toolsets": ["terminal", "file", "web"]},
]
delegate_task(tasks=tasks)
# 等待完成后，读取各子 agent 输出文件，写入 vault
```

**⚠️ 限制：**\n- 子 agent 使用当前模型（通常是 flash），不可独立换 pro 模型\n- 若需要 pro 模型深度分析，走「方式一」一次性 cron job\n- 子 agent 输出文件可能散落在 `/root/` 和 `/tmp/`，主 agent 需要主动收集\n- 子 agent 的 write_file 输出到临时路径，主 agent **必须验证**后再写入 vault\n\n**⚠️ 深坑：子 agent 可能把笔记写到 /root/ 而非 vault（2026-05-20 22篇 3D-VLM 批量实测）。**\n\n**症状：** 子 agent 报告「已写入」但实际上文件在 `/root/xxx.md` 而非 vault 中，且多个子 agent 可能写入同一个 `/root/3D-VLM/` 临时目录下的同名文件，后覆盖先，数据丢失。\n\n**根因：** 子 agent 的 context 中指定了「覆盖旧文件」但没有指定**绝对路径**，子 agent 默认在 `/root/` 下创建同名文件。\n\n**正确做法（双层保险）：**\n1. **在 context 中指定 vault 绝对路径**，让子 agent 直接 write_file 到目标位置：\n   ```\n   context=\"现有笔记路径: /opt/data/obsidian-vault/论文笔记/3D-VLM（视觉语言模型）/XXX.md（占位符，需覆盖）\"\n   ```\n2. **子 agent 的 goal 中明确要求写 vault 路径**：`\"写分析笔记覆盖 /opt/data/obsidian-vault/论文笔记/{分类}/{论文名}.md（旧文件）\"`\n3. **批量完成后主 agent 审计**：`ls -la /opt/data/obsidian-vault/论文笔记/{分类}/*.md` 确认每篇都存在且行数达标\n4. **检查 /root/ 是否有残留**：`ls /root/*.md /tmp/*.md 2>/dev/null`，如有则搬运到 vault 并添加 frontmatter\n\n**批量后 frontmatter 修复（必要步骤）：**\n即使子 agent 直接写入了 vault，也可能缺少 frontmatter（arxiv_id/title/tags）。批量完成后必须：\n```python\nimport os, re\nvault = \"/opt/data/obsidian-vault/论文笔记/3D-VLM（视觉语言模型）\"\nfor fn in os.listdir(vault):\n    if not fn.endswith('.md'): continue\n    path = os.path.join(vault, fn)\n    with open(path) as f:\n        first = f.readline().strip()\n    if first != '---':\n        # 缺少 frontmatter，需添加\n        with open(path) as f: content = f.read()\n        fm = f\"---\\ntitle: {fn.replace('.md','')}\\narxiv_id: {extract_id(content)}\\ncreated: {date}\\ntags: [{cat}]\\n---\\n\\n\"\n        with open(path, 'w') as f: f.write(fm + content)\n```

### 方式六（新增）：批量分类与占位符笔记清理

**场景：** 从「其他」文件夹整理大量未归类论文（如56篇）。

**高效工作流：**

```python
# 批量读取所有笔记（不要逐篇 read_file，会触发 dedup 上限）
import os
files = sorted(os.listdir(folder))
for f in files:
    # 用 cat 或 Python open 读取，不走 read_file
    path = os.path.join(folder, f)
    with open(path) as fh:
        lines = fh.read().split('\n')
    # 提取 title, core, category
```

**分类前先用 `terminal` 的 `for f in *.md; do head -30 "$f"; done` 批量预览。**

### 方式七（新增）：合并笔记拆分为独立深度分析

**场景：** vault 中有两篇论文被合并为一个对比笔记（如 tttLRM & ZipMap），需要拆分为各自独立的深度分析笔记。

**工作流：**
1. 并行创建两篇的独立深度分析（delegate_task batch，各一篇）
2. 每篇子 agent 写自己的独立完整笔记到 vault（200+行）
3. 均完成后，删除原合并笔记文件（.md + .html）
4. 运行 generate_index.py 重新生成（自动处理 URLs）
5. git commit/push

**⚠️ 注意：** 删除原合并文件前确保两篇独立笔记都已写入成功。

### 方式九（新增）：综合主题分析（pro模型）

**场景：** 用户要求对一个技术主题（如"register token"、"CLS token"）做深度综合分析，涉及多篇论文的融合对比和额外检索。不同于单篇精读或批量并行精读——主题分析需要：读取vault中已有笔记 + 检索arXiv更多相关论文 + 写作综合分析笔记（非单篇论文笔记）。

**与单篇精读的区别：**
- prompt中不指定单个arXiv ID，而是指定主题和需要读取的vault笔记路径
- 要求子agent先读取已有笔记全文，再做arXiv API检索补充
- 产出写在 `分析笔记/` 目录（非分类目录），`type: analysis`
- 通常不需要提取架构图

**工作流（2026-05-27 已验证 CLS Token + Register Token 主题）：**

```python
# 主 agent 创建一次性 cron job
cronjob(
    action="create",
    name="小驴：{主题}深度研究笔记",
    prompt="""你被称为「小驴」，是用户的深度研究助手。
围绕 **{主题}** 写一篇深度分析笔记。

## 已有素材（必须完整阅读）
读取：/opt/data/obsidian-vault/论文笔记/{分类1}/{笔记1}.md
...

## 检索要求
通过 arXiv API（走代理 -x http://127.0.0.1:7890）检索相关论文...

## 笔记要求
写入路径：/opt/data/obsidian-vault/论文笔记/分析笔记/{主题}.md
（需带标准 frontmatter，type: analysis）

## 内容结构（示例）
1. 引子
2. {子主题A} 的演化与设计
3. {子主题B} 的发现与方案
4. {子主题A vs 子主题B} 的对比与协同
5. 知识库关联
6. 批判与改进建议
7. 深度分析与独特见解

## 完成后
1. 写入笔记
2. python3 generate_index.py
3. git commit + git push
""",
    skills=["paper-analyst"],
    model={"provider": "deepseek", "model": "deepseek-v4-pro"},
    schedule="1m",
    deliver="origin",
    enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)
```

**⚠️ 主题范围坑（2026-05-27 实测）：** 用户先在 prompt 中把范围从"CLS Token + Register Token"缩小到"Register Token 为主"，然后又纠正回"CLS和register都可以"。**不要自己猜测用户想要的主题范围——优先按用户原始表述写 prompt。** 如果用户模糊（如只说"register"），用并列结构比缩小主题更安全。主题范围改来改去会浪费一次 pro 模型的 token。正确的做法：先确认范围再创建 cron job。

**⚠️ prompt 主题覆盖原则：** 子 agent 一次只跑一个 cron 任务，写一个笔记。如果用户说「结合这些论文写一篇深度笔记」但未明确主题，先问清楚主题范围再创建。不要擅自决定把 CLS token 降级为对比参照——用户可能本意就是并列主题。

### 方式四：通过微信命令

用户说"精读 2401.10891" → 创建一条一次性 cron job 带 model override：
```python
cronjob(action='create',
  name='分析论文XXX (pro模型)',
  skills=['paper-analyst'],
  model={'model': 'deepseek-v4-pro', 'provider': 'deepseek'},
  schedule='1m',  # ⚠️ 用户偏好：主动请求时用1m，不要默认30m（用户会催着改短）
  prompt='分析论文 XXX (arXiv:XXXX.XXXXX)...'
)
```
cron job 用 pro 模型运行，结果自动发回微信。比 `delegate_task` 更灵活（后者不能独立设置模型）。

**已验证（2026-05-18）：** SLAM-Former 分析（2509.16909）使用此模式成功，pro 模型生成 280 行完整分析笔记，写入 Obsidian + 更新 JSON + 同步 GitHub。
**已验证（2026-05-18）：** PointForward 分析（2605.11594）已有笔记，无需 pro 模型，直接用完整笔记生成播客。

---

## 论文名称→arXiv ID 检索

当用户只提供论文名称（如"检索一下PAGE-4D和VGGT-DET"）而未给出 arXiv ID 时，按以下顺序检索：

### ⚠️ 坑：subagent + web 搜索不可靠

2026-05-22 实测：`delegate_task` + `toolsets=["web"]` 搜索 PAGE-4D 完全失败，搜 VGGT-DET 的结果也存疑。subagent 可能声称搜索了但实际没调 web_search 工具（hallucination），也可能搜到无关结果。不要依赖此方式。

### 可靠检索方法

**方法1（推荐）：arXiv API 查询** — 先直连，失败走代理
```bash
# Try direct first
result=$(curl -sL --max-time 10 "https://export.arxiv.org/api/query?search_query=ti:PAGE-4D&max_results=5" 2>/dev/null)
# Fall back to proxy if empty
if [ -z "$result" ]; then
  result=$(curl -sL --max-time 15 -x http://127.0.0.1:7890 "https://export.arxiv.org/api/query?search_query=ti:PAGE-4D&max_results=5" 2>/dev/null)
fi
echo "$result" | grep -oP '<title>\K[^<]+' | grep -v 'arXiv Query'
```
返回 Atom XML，含 title/id/abstract，解析可靠。或用 Python `xml.etree.ElementTree` 解析更准确。

**方法2：arXiv 搜索页面**
```bash
curl -sL --max-time 10 "https://arxiv.org/search/?searchtype=title&query=PAGE-4D" 2>/dev/null | grep -oP 'arXiv:\d{4}\.\d{4,5}' | head -3
```

**方法3：直接用浏览器打开 Google Scholar（可能超时）**

**最后手段：** 如果都搜不到，让用户提供 arXiv ID。

详见 `references/paper-id-discovery.md`。

## 核心工作流

### 第1步：论文检查与去重

**双重验证机制（防止幻觉/错误摘要）：**

1. **查标题**：先访问 arXiv 页面获取真实标题。**⚠️ 网络策略：先直连尝试，失败再走代理**（arXiv API 在中国有时可直接访问；Clash 代理也可能未运行）：
   ```bash
   # 先直连
   title=$(curl -sL --max-time 10 "https://arxiv.org/abs/XXXX.XXXXX" 2>/dev/null | grep -oP '<meta name="citation_title" content="\K[^"]+')
   # 若为空，再走代理
   if [ -z "$title" ]; then
     title=$(curl -sL --max-time 15 -x http://127.0.0.1:7890 "https://arxiv.org/abs/XXXX.XXXXX" 2>/dev/null | grep -oP '<meta name="citation_title" content="\K[^"]+')
   fi
   echo "$title"
   ```

2. **查核心贡献**：下载PDF提取摘要，确认核心内容

3. **去重检查**：搜索 `/opt/data/obsidian-vault/论文笔记/` 下是否已存在笔记（按 arxiv ID 或标题关键词匹配）

4. **JSON 元数据检查**：搜索 `/opt/hermes/arxiv_papers_2024_2026.json` 确认论文是否已在知识库中

### 第1.5步：读取关联论文图谱

精读前先查阅知识库论文关联图谱，找到当前论文的 related 论文，读它们的笔记增强关联分析：

```python
import json

with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data

# 查找当前论文的 related 论文
current_aid = "XXXX.XXXXX"  # 替换为当前论文的 arXiv ID
for p in papers:
    if p['arXiv号'] == current_aid:
        related = p.get('related', [])
        print(f"📎 关联论文 ({len(related)} 篇):")
        for r in related:
            rel_id = r['id']
            rel_type = r.get('关系', '互补')
            desc = r.get('说明', '')
            # 查找关联论文的标题
            r_title = next((pp.get('标题前几个词', '?') for pp in papers if pp['arXiv号'] == rel_id), rel_id)
            print(f"  [{rel_type}] {r_title}")
            print(f"    {desc}")
            
            # 读关联论文的笔记
            r_note_path = next((pp.get('笔记路径', '') for pp in papers if pp['arXiv号'] == rel_id), '')
            if r_note_path:
                full_path = f"/opt/data/obsidian-vault/{r_note_path}"
                if os.path.exists(full_path):
                    print(f"    📄 笔记: {full_path}")
        break
```

**输出到分析提示词**：将 related 论文的核心思想+关系说明注入精读 prompt，确保：
1. 笔记中包含明确的关联引用 [[关联论文名]]
2. 在"知识库关联"章节列出所有 related 论文
3. 在"技术方法"中对比相关方法的差异

### 第2步：下载与提取

```bash
# 下载 PDF — 先直连，失败再走代理
curl -sLo /tmp/paper_XXXX.pdf "https://arxiv.org/pdf/XXXX.XXXXX.pdf" 2>/dev/null
if [ ! -s /tmp/paper_XXXX.pdf ]; then
  curl -sLo /tmp/paper_XXXX.pdf -x http://127.0.0.1:7890 "https://arxiv.org/pdf/XXXX.XXXXX.pdf"
fi
ls -la /tmp/paper_XXXX.pdf

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

### 第2.2步：发现并阅读补充资源（博客/项目页/GitHub/HF）

对于知名研究机构（Meta/FAIR, Google/DeepMind, NVIDIA, Microsoft, OpenAI 等）的高影响力论文，arXiv 页面可能**不包含**项目主页/博客/GitHub 链接——这些信息需要通过主动搜索发现。

**发现方法（按优先级）：**

1. **GitHub 仓库**：尝试 `https://github.com/{机构}/{论文名}`（全小写，去特殊字符），如 `github.com/facebookresearch/dinov3`。也可用 `curl -sL "https://api.github.com/search/repositories?q={论文名}+{机构}&sort=stars&per_page=3"`（注意限流）

2. **项目主页**：常见模式包括：
   - `ai.meta.com/{论文名}/`（Meta）
   - `ai.meta.com/blog/{论文名}-{关键词}/`（Meta 博客）
   - `{机构}.github.io/{论文名}/`（学术机构）
   - `{论文名}.{机构}.ai/` 或 `{论文名}.github.io/`

3. **博客文章**：`ai.meta.com/blog/`（Meta）、`research.google/blog/`（Google）、`openai.com/index/`（OpenAI）

4. **HuggingFace 模型**：`huggingface.co/{机构}/{论文名}` 或搜索 `https://huggingface.co/api/models?search={论文名}&author={机构}`

5. **GitHub README 提取**：如果 GitHub 存在，README 通常包含项目页和博客链接。用 `curl -sL "https://raw.githubusercontent.com/{user}/{repo}/main/README.md" | head -50` 快速获取头部链接。

**读取要求：**
- **博客**：重点阅读论文中没有的部署建议、实际用例、性能对比 demo、作者访谈/背景
- **项目主页**：关注演示、交互 demo、视频结果
- **GitHub README**：关注模型权重获取方式、安装说明、支持的集成（HuggingFace/timm/PyTorch Hub）、后续更新（如蒸馏代码、下游任务代码）
- **HF 模型卡**：关注模型架构细节、使用示例、基准测试

**⚠️ 常见坑：** arXiv 页面底部「Code/Data」链接区域可能被截断或没有——不要假设 arXiv 页面会列出这些链接。对于 DINOv3（2025-08）、Image Gen（2025-03）等 Meta 论文，项目链接出现在 GitHub README 里而非 arXiv 页面。

**笔记整合：** 补充资源中发现的重要信息应整合到笔记的「技术方法」「实验结果」「深度分析与独特见解」等对应章节中。博客中的独创内容（如部署 FPS、量化结果）可单独成段或作为核心洞察的佐证。

### ⚠️ 架构图全黑质量验证（2026-06-01 新增）

**症状（2026-06-01 实测 DGGT）：** 子代理提取的 `DGGT_架构图.jpeg`（678×1886）平均像素值仅 0.4（纯黑）。浏览器显示为黑块。根因是旧版提取得到了损坏图像但未验证就提交了。

**正确做法：** 每次提取架构图后立即进行质量检查：

```python
from PIL import Image
import numpy as np
img = Image.open(img_path)
arr = np.array(img)
if arr.mean() < 5:
    print(f"⚠️ 架构图全黑 (mean={arr.mean():.1f})，方案A失败→用方案C裁剪重新提取")
    # 回退到方案C裁剪渲染
```

**批量检查 git 中已有黑图：**
```bash
git ls-tree -r HEAD --name-only | grep -E '\.(png|jpe?g)$' | while read f; do
    python3 -c "from PIL import Image; import numpy as np
arr = np.array(Image.open('$f'))
if arr.mean() < 5: print(f'⚠️ 全黑: $f')" 2>/dev/null
done
```

### 第2.5步：提取模型架构图（仅对模型/方法类论文）

如果论文包含方法/模型架构图，从论文中提取图片保存到笔记同目录。

#### ⚠️ 优先方案：arXiv HTML 页面按 caption 找图（2026-06-01 新增）

**不要直接从 PDF 随意提取图片然后猜测哪个是架构图。** 用户纠正过此错误（2026-06-01 DGGT）。

**正确做法：**
1. 访问 `https://arxiv.org/html/{arXiv_ID}` 获取 HTML 版论文
2. 在页面中用 console 脚本列出所有 `<figure>` 及其 caption：
   ```javascript
   // 在浏览器 console 执行
   const figs = document.querySelectorAll('figure');
   figs.forEach((f, i) => {
     const imgs = f.querySelectorAll('img');
     const cap = f.querySelector('figcaption, p:last-of-type');
     const srcs = Array.from(imgs).map(img => img.src);
     console.log(`Figure ${i+1}:`, cap?.textContent?.substring(0,200));
     console.log(`  Images:`, srcs);
   });
   ```
3. **根据 caption 判断哪个 figure 是架构图**：搜索 "Overall Architecture" / "Pipeline" / "Method Overview" / "Framework" 等关键词
4. **架构图通常是 Figure 2 或 3（方法图），不是 Figure 1**。Figure 1 通常是对比概览/效果展示/定量对比，不包含模型架构细节（用户明确纠正过此误区）
5. 从正确的 figure 的 `<img>` 标签获取图片 URL（通常是 `https://arxiv.org/html/{ID}/x3.png` 等）
6. 用 curl 下载高清 PNG：
   ```bash
   curl -sLo "论文名_架构图.png" "https://arxiv.org/html/2512.03004v1/x3.png"
   ```

**例外情况：** 若 arXiv HTML 版不可用（返回 404），或图片分辨率过低（< 500px），回退到 PDF 方案。

#### 备选方案（PDF 提取 — 仅当 arXiv HTML 不可用）

如果论文包含方法/模型架构图（通常是 Figure 2-3 方法图，不是 Figure 1 对比概览），从 PDF 中提取图片保存到笔记同目录。

**⚠️ 时序坑**：图提取前必须先去重确认 vault 中是否已有笔记。已有深度笔记的论文再提取图会遗留无用图片文件到 vault。

**⚠️ 页面选择坑**：架构图通常是 **Figure 2-3（方法图）**，不是 Figure 1（对比概览/效果展示）。用 pypdf 搜索 "Pipeline" / "Architecture" / "Overview of our" / "Method" 定位正确页码。

**⚠️ clip 宽度坑**：clip 右边界必须用 `page.rect.width - 25`（约 580-700pt），不要硬编码 580pt。Mask2Former 的 Figure 2 从 x=269 延伸到 x=725，clip=(30,25,580,240) 会截掉右侧组件。

**⚠️ 诊断步骤**：用 `page.get_drawings()` 检测矢量路径 bbox 大小。如果矢量路径 bbox 跨度 ≥300pt（如 (269,42) 到 (725,270)）且嵌入式图片在该区域内只有小图标，说明架构图是矢量绘制的，直接走方案C。

**方案A：提取嵌入式图片**（仅当最大嵌入式图片宽 ≥500px 且 bpp≥0.05 时才保存）：
```bash
python3 << 'PYEOF'
import fitz, os
doc = fitz.open("/tmp/paper_XXXX.pdf")
page = doc[0]
imgs = page.get_images(full=True)
if imgs:
    best = max(imgs, key=lambda img: img[2] * img[3])
    base = doc.extract_image(best[0])
    ext = base["ext"]
    w, h = base["width"], base["height"]
    # ⚠️ 字节/像素 < 0.05 说明是高度压缩的小图标/图例，不是架构图
    bpp = len(base["image"]) / (w * h) if (w * h) > 0 else 0
    if bpp < 0.05:
        print(f"⚠️ 提取图 {w}x{h} 但仅 {len(base['image'])/1024:.1f}KB (bpp={bpp:.3f}) — 可能是图标，非架构图")
        print("→ 该页的架构图很可能是矢量图，转方案C裁剪渲染")
        # 不要保存，交给方案C
    else:
        img_path = f"/opt/data/obsidian-vault/论文笔记/{category}/论文名_架构图.{ext}"
        with open(img_path, 'wb') as f:
            f.write(base["image"])
        print(f"✅ 架构图已保存: {img_path} ({w}x{h}, {len(base['image'])/1024:.0f}KB)")
else:
    print("⚠️ 第1页无嵌入式图片，尝试方案C")
doc.close()
PYEOF
```

**方案C（首选备选 — 矢量图裁剪渲染）**：当嵌入式图片提取不到架构图时（矢量图/小图标），裁剪图区域。**不要渲染整页。** 先定位架构图所在页（搜索 "Pipeline"/"Architecture"），用 200 DPI + clip 裁剪：

```bash
python3 << 'PYEOF'
import fitz, re
doc = fitz.open("/tmp/paper_XXXX.pdf")

# 1. 定位架构图所在页（不是第1页！Figure 1 通常是对比概览）
from pypdf import PdfReader
reader = PdfReader("/tmp/paper_XXXX.pdf")
target_page = 0
for i, page in enumerate(reader.pages[:6]):
    text = page.extract_text()
    if any(kw in text for kw in ["Overview of our", "Pipeline", "Architecture",
                                   "Method Overview", "Overall architecture",
                                   "Framework", "our proposed"]):
        target_page = i
        break

# 2. 找图区域 — 用文本块定位 "Figure N." caption
page = doc[target_page]
blocks = page.get_text("blocks")
fig_bottom = 0
for b in blocks:
    if re.search(r'Figure\s+[23]\.', b[4]):  # 优先匹配 Figure 2/3
        fig_bottom = b[1] + 10
        break
if fig_bottom == 0:
    for b in blocks:
        if re.search(r'Figure\s+\d+\.', b[4]):  # 回退匹配任何 Figure N.
            fig_bottom = b[1] + 10
            break
if fig_bottom == 0:
    fig_bottom = 240  # 默认：页面顶部到y=240pt

# 3. ⚠️ clip 必须足够宽 — 用 page.rect.width - 25 而非硬编码
clip = fitz.Rect(25, 30, page.rect.width - 25, fig_bottom)
zoom = 200 / 72
pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
img_path = f"/opt/data/obsidian-vault/论文笔记/{category}/论文名_架构图.png"
pix.save(img_path)
print(f"✅ 裁剪架构图: {img_path} ({pix.width}x{pix.height}) (page {target_page+1})")
doc.close()
PYEOF
```

**对比图（Figure 1 效果展示）同理提取**：不要渲染整页。用文本块定位 Figure 1 caption y 坐标裁剪：

```bash
# 对比图通常在论文第1页（Figure 1），在裁剪架构图后附加提取：
page1 = doc[0]
blocks1 = page1.get_text("blocks")
# Figure 1 通常占据页面顶部到y=350左右
fig1_bottom = 350
for b in blocks1:
    if re.search(r'Figure\s+1\.', b[4]):
        fig1_bottom = b[1] + 10
        break
clip1 = fitz.Rect(30, 50, page1.rect.width - 30, fig1_bottom)
pix1 = page1.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip1)
overview_path = f"/opt/data/obsidian-vault/论文笔记/{category}/论文名_对比概览.png"
pix1.save(overview_path)
print(f"✅ 裁剪对比图: {overview_path} ({pix1.width}x{pix1.height})")
```

**诊断标准（判断用方案A还是方案C）：**
- 方案A成功标志：提取到的图片宽 ≥ 500px **且** 字节/像素(bpp) >= 0.05（12KB 以上的 453×781 图片是妥当的；12KB 以下说明是压缩图标）
- 方案C时机：该页嵌入式图片全部 < 400px **或** bpp < 0.05（都是小图标/logo），说明架构图是矢量绘制
- **矢量图检出（重要诊断）**：用 `page.get_drawings()` 检查目标页是否有大面积矢量路径。如果矢量路径 bbox 跨度 ≥300pt（如 `Rect(269, 42, 725, 270)` 含 90+ 条路径），而嵌入式图片在该 bbox 内只有小图标，说明架构图是矢量绘制的，直接走方案C
- ⚠️ 绝不使用无 clip 的 `get_pixmap` 渲染整页。会截入标题、摘要、正文文字，用户会投诉
- ⚠️ clip 右边界用 `page.rect.width - 25`，不用硬编码。Mask2Former 的图延伸到 x=725

**在笔记中引用**（放在标题后核心思想前）：
```markdown
![[论文名_架构图.png]]
```

**注意：**
- 命名规则：`论文名_架构图.png` 放在笔记**同级目录**
- 使用 `page.get_image_info()` 可查看图片在页面的位置坐标
- 并非所有论文的架构图都在第一页——先通过文本搜索确定页面
- 对比图（Figure 1效果展示、与其他方法的对比）同理需要裁剪，不要渲染整页
- 对于纯理论/评测/数据集论文可能没有架构图，跳过此步

### 第2.6步：检查公式格式（⚠️ 新的）

**问题**：笔记中的数学公式如果写在 ``` 代码块里，会生成为 `<pre><code>`，MathJax 不会渲染它们——用户看到的是纯文本公式。

**正确格式**：使用 `$$...$$`（显示公式）或 `$...$`（行内公式）包裹：

```markdown
标准 cross-attention：
$$ \text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d}}\right) \cdot V $$
```

**不要用**代码块：
```markdown
标准 cross-attention：
```
Attention(Q, K, V) = softmax(QK^T / √d) · V
```
```

**修复已有笔记**：更新知识库关联/修改笔记时，将代码块中的公式转换为 LaTeX 格式。尤其注意：
- 正确转义：`\text{}`、`\left`、`\right`、`\frac{}{}`、`\sqrt{}`
- `cases` 环境：`\begin{cases} ... \end{cases}`，内部行用 `\\` 分隔

**检查方法**：`grep -n '```' *.md | xargs grep -l 'softmax\|Attention\|∫\|frac\|mathbf\|mathcal'` 可以找出笔记中代码块内可能包含公式的文件。

### 第3步：精读与分析

**前置准备**：精读前必须执行 Step 1.5 读取该论文的关联论文图谱和对应笔记，确保分析时已有全局视野。

**⚠️ 关联论文不在知识库中**：JSON 的 `related` 字段指向的论文可能尚未加入 `arxiv_papers_2024_2026.json`（常见于作为 baseline 引用的论文如 GenFusion/CAT3D/Gen3C 等）。此时 Step 1.5 返回空结果是正常的——不要阻塞流程。分析笔记中仍应引用这些论文（用 arXiv ID 或标题），只是无法做 Obsidian 双向链接。后续可将这些论文补充到知识库中再补建双向关系。

使用 pro 模型进行深度分析，输出结构：

1. **论文元信息**：标题、作者、单位、年份、arXiv ID
1. **核心思想**（2-3句话）
2. **思路起源与发展脉络**（必写）：这个思路是怎么想出来的？分析作者的灵感来源——从什么现象/问题出发、受到了什么工作的启发、关键的洞察moment是什么。例如：3DGS的灵感来自传统图形学中的点云渲染+可微优化，DINO的发现源自对ViT注意力图的无意观察。

   同时梳理该方向从早期工作到本论文的演化路径。例如"DUSt3R→Fast3R→MonST3R→本论文"或"VGGT→SparseVGGT→FastVGGT→TurboVGGT"，每条转折标明关键变化（什么motivation推动了这一步演变）。让读者能看懂这篇论文在整条技术路线上处于什么位置。

   **写作建议**：将「思路如何起源」和「后续如何演化」放在一节叙述，形成一个完整的叙事弧——从灵感到定位，读者能一口气理解这篇论文的来龙去脉。
3. **数据策略**（⚠️ 对数据驱动/Scaling Law类论文必写，可作独立章节）
4. **技术方法**（关键组件、架构）
4. **创新点**（与已有工作的区别）
5. **实验结论**（数据集、指标、数值）
7. **深度分析与独特见解**（⚠️ 必写，合并原独特观点+延伸思考，分点分析）：从多个不同角度对论文进行深度分析，每点一个独立视角。内容应包含：

   - **核心洞察**——你发现的、作者没有明说的深层原因：为什么这个方法能work、反直觉的设计选择、被忽略的局限性、方法论是否可迁移到其他领域
   - **未来方向**——基于洞察的延伸：直接后续方向、该工作在领域中的长期定位、作者没意识到的潜力
   - **复现性与工程落地**——代码/权重可用性、复现难度、部署壁垒（硬件、推理速度）、优化空间（量化、蒸馏、稀疏化）
   - **方法学反思**——该论文的设计哲学对领域有什么启示？有没有值得被后续工作吸收的元方法论贡献？
   
   **要求**：每点独立成条，用 `- **视角X：标题**：...` 格式，至少3条，每条100-200字。不要求连续叙事，但每点要有实质深度，而非简单归纳。
8. **批判与改进建议**（⚠️ 必写，至少3条，每条包含「核心矛盾」+「改进思路」两个子项）：

   **原则**：这不是凑缺点清单，而是展现**对论文设计选择的深层理解**——找到作者没有明说、甚至被实验设计掩盖的 trade-off。每条需回答「这个方法为什么没完美解决 X？」以及「我能想到什么具体方案？」。

   **寻找矛盾的 6 个切入角度**（从已实践的 GemDepth 分析中提炼）：
   
   - **假设冲突**：论文模块 A 和模块 B 之间有无隐含的、相互矛盾的假设？例如 GEM 的全局刚性位姿假设 vs ASTT 的逐点时序对应——动态场景中两者冲突。
   - **实验构造偏差**：消融实验的噪声注入方式是否过于理想化（独立同分布噪声），掩盖了现实场景（相关性/系统性偏差）下的退化？噪声是否只覆盖了「表面对齐」而非「本质退化」？
   - **被选择的边界条件**：论文的某个设计选择（如固定窗口大小、全局归一化因子、串行模块）排除了哪些合理的替代方案？它是否做了「方便自己、不帮用户」的选择？
   - **领域泛化的盲区**：训练数据的分布特点（合成场景、运动模式、光照条件）与现实部署中可能遇到的分布外场景之间有多大 gap？有没有被「SOTA 数字」掩盖的泛化短板？
   - **级联退化**：流水线中的上游模块（如位姿预测）如果表现不佳，如何级联影响下游模块（如深度对齐）？论文是否只报告了「完美上游」下的性能？
   - **效率与普适性的二选一**：论文报的 FPS/参数量是否充分考虑了工程落地（量化、优化、硬件依赖）？有没有选择性地报「对自身有利」的指标？

   每条的格式：
   ```
   ### 问题 N：一句话核心矛盾
   
   **核心矛盾**：1-3 句话说明问题本质
   
   **改进思路**：
   - 具体方案 1（为什么这个方案能解决问题）
   - 具体方案 2（与该方案互补的其他思路）
   - （可选）实验验证方案（如何设计消融实验来检验）
   ```
   每个关联写在单独的子条目中，格式：`- **[文章名] — [结合/相似/打破]**：[一句话说明]`
9. **知识库关联**（⚠️ 必须详细，至少3条，每条从以下三个维度中选择一个撰写）：
   - **可与哪篇文章结合？** — 提出一个具体的跨论文整合思路，例如：「RoMa 的密集 warp + certainty map 可直接馈入 DUSt3R 的交叉注意力模块，替换其现有的特征关联机制，有望在弱纹理区域提升重建精度。」
   - **与哪篇文章思路相似/平行？** — 指出方法学或设计哲学层面的共鸣，例如：「与 AdaptSplat 共享『冻结视觉基础模型 + 轻量适配器』的设计哲学，都是在前馈框架中最大化利用 DINO 系列预训练先验。」
   - **打破了哪篇文章的思想/假设？** — 指出该论文颠覆或质疑了哪个已有工作的核心假设或设计选择，例如：「RoMa 打破了 DKM『共享 backbone 同时提取粗细特征』的设计假设，证明粗/细特征解耦后各自专业化（冻结的 DINOv2 + 训练的 VGG19）能获得更好的鲁棒-精度 trade-off。」
   
    每个关联写在单独的子条目中，格式：`- **[文章名] — [结合/相似/打破]**：[一句话说明]`

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

## 数据策略（可选，对数据驱动类论文必写）

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

## 思路起源与发展脉络

> 思路从何而来？该方向从早期工作到本论文的演化路径是什么？

## 深度分析与独特见解

- **视角1：核心洞察** — ...
- **视角2：未来方向** — ...
- **视角3：复现性与工程落地** — ...

## 批判与改进建议
```

**⚠️ 去重检查与覆盖策略：**
- 写入前用 `search_files()` 或 `os.listdir()` 检查目标目录
- 如果 arxiv ID 相同但之前笔记不完整，可以覆盖更新
- 如果已存在完整笔记，则跳过写入

### 第4.3步：建立/更新论文关联关系（双向）

**⚠️ 时序规则：必须在精读分析完成后才建关联。** 当用户要求精读多篇论文并建立相互关联时，正确的顺序是：
1. 先创建所有论文的精读任务（cron job）
2. 等所有 cron job 完成、笔记写入 vault
3. 再统一建立双向关联（更新 JSON related + 更新每篇笔记的知识库关联章节 + 重新生成网站 + 同步 GitHub）

**永远不要在精读完成前预先建立关联**——此时论文的核心贡献、技术细节尚未分析完整，关联描述会不够准确。用户纠正过此误区。

分析完成后，必须在 JSON 中为此论文**建立双向关系**：

1. **为本论文添加 related 字段**：根据分析中引用的关联论文，填写关系类型（继承/互补/对比）和说明
2. **反向更新**：对 every 关联论文，也在它们的 related 中回写指向本论文的关系（关系类型保持一致）
3. **避免重复**：检查目标论文的 related 是否已包含本论文 ID，已存在则跳过不加

```python
import json

with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data

current_aid = "XXXX.XXXXX"  # 当前论文 ID
new_relations = [
    {"id": "2410.03825", "关系": "互补", "说明": "..."},
    # ... 从分析中提取
]

# 1. 为本论文添加 related
for p in papers:
    if p.get('arXiv号') == current_aid:
        existing = {r['id'] for r in p.get('related', [])}
        for rel in new_relations:
            if rel['id'] not in existing:
                p.setdefault('related', []).append(rel)
        break

# 2. 反向更新
for rel in new_relations:
    for p in papers:
        if p.get('arXiv号') == rel['id']:
            existing_ids = {r['id'] for r in p.get('related', [])}
            if current_aid not in existing_ids:
                p.setdefault('related', []).append({
                    "id": current_aid,
                    "关系": rel['关系'],
                    "说明": rel['说明']  # 保持说明一致
                })
            break

with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ 已建立 {len(new_relations)} 条双向关系")
```

**⚠️ 原则：** 关系是双向的，A→B 和 B→A 的关系类型必须一致。不强行关联，每篇 1-5 条有意义的关联即可。

### 第4.5步：更新 JSON 中现有论文的笔记路径

⚠️ **关键步骤（2026-05-19 验证缺失）**：写笔记后必须更新 JSON 中**对应论文**的 `笔记路径` 字段，否则 cron job 会反复重分析已完成的论文。

```python
import json, os
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data

arxiv_id = "XXXX.XXXXX"  # 当前分析的论文ID
note_rel_path = "论文笔记/{分类}/{论文名}.md"

for p in papers:
    if p.get('arXiv号') == arxiv_id or re.sub(r'v\d+$', '', p.get('arXiv号', '')) == arxiv_id:
        p['笔记路径'] = note_rel_path
        # 如果还缺分类字段，一并补充
        if not p.get('分类'):
            p['分类'] = category_name
        break

with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

**为什么这步重要？** 每日 cron job（6:00）的去重逻辑依赖 JSON 中的 `笔记路径` 字段判断「已分析」。如果不更新，即使 vault 里已有 200+ 行笔记，cron 仍会认为该论文「无分析笔记」并重新拉取精读，浪费 pro 模型 token。

**批量场景**：批量精读后，对所有完成论文统一执行一次 JSON 更新：
```python
for note_file in newly_written_notes:
    update_json_note_path(arxiv_id, note_rel_path)
```

### 第4.6步：重新生成网站（首页、搜索、标签、HTML渲染）

笔记写入 vault 后，立刻运行索引生成脚本。**脚本需 30-60s 完成**，生成全部页面：

```bash
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py
```

**执行时机**：每次写完/更新笔记后立即执行，不要在最后统一做（避免漏掉）。

**生成内容**（v3.1 完整功能清单）：
- 🏠 首页 index.html — 卡片布局、最新更新（论文名+分类标签, 按mtime取10篇）、播客列表、导航栏
- 🔍 `/搜索.html` — 客户端搜索（JS索引所有笔记，搜标题/标签/摘要）
- 🏷️ `/标签/` — 标签云 + 每标签独立页面
- 📄 所有 .md → .html — 完整渲染（含标题、代码块、表格、图片、wikilink链接）
- 🌊 **Mermaid.js 动态渲染** — ```mermaid 代码块实时渲染为 SVG（flow/sequence/gantt/timeline），自动深色/浅色双主题
- ↔️ **文本演化路径自动转流程图** — 检测 `A → B → C → D`（3+箭头+短条目）自动转为 graph LR 节点图。自动过滤含冒号前缀、长句子等非路径场景
- 🌳 **ASCII 树图→mermaid graph TD** — 代码块中的 `├── └── │` 树连接符被解析并转为 mermaid 树形图（根深紫、子浅紫、边标签取首行注解）。失败后fallback到深色终端框。注解子节点已移除（用户偏好：保持树结构干净）
- 📊 **对齐表格→HTML table** — 多行 `│` 对齐图（如层级注意力分布表）自动转为真实 HTML `<table>`，含表头colspan、标签列高亮、数列高亮。检测条件：无 ├──└──、3+行同理有等量│、Count分析≥60%匹配
- 📋 **Markdown 表格 (`| xxx |`) → `<table>`** — 笔记中的 `| 方法 | 指标 | 值 |` 表格自动转为 `<table><tbody><tr><td>`。⚠️ `in_table` 状态跟踪确保 `<table>` 包裹（2026-05-26 修复：旧代码只输出裸 `<tr><td>` 导致浏览器不渲染）。详见 `references/html-diagram-pipeline.md` 第5节
🗺️ **知识图谱交互页** — `/图谱/index.html` — D3.js 力导向图可视化全部 184 篇论文的关联关系。节点颜色=分类，大小=关联度，连线颜色=关系类型（蓝=继承/红=打破/绿=结合）。支持悬停看详情、点击跳转笔记、图例切换分类显隐、搜索过滤、拖拽缩放。D3.js 同样自托管于 `assets/d3.min.js`。知识图谱由独立脚本 `generate_kg.py` 生成，在 Step 4.6 后可选运行。详见 `references/knowledge-graph.md`。

💬 **论文讨论助手（右侧面板）** — 每个论文页右侧固定面板集成实时讨论功能。右栏 `position: sticky; width: 340px`，滚动时不遮挡笔记内容。手机端自动折叠到下方。用户直接输入问题，子 agent（pro 模型，session_id="paper-discuss"）带着笔记全文 + PDF 原文 + 知识库关联做上下文回答。Q&A 自动保存到 `讨论记录/{论文名}.json`，重新生成网站时自动渲染历史。详见 `references/website-discuss-button.md`。modify generate_index.py 的 `_DISCUSS_INLINE_STYLES` 和 `generate_note_page` 模板切换布局。注意 container 宽度需同步改为 1200px。

**MathJax 必须自托管**：下载到 `assets/mathjax/tex-chtml.min.js`（所有外部 CDN 在国内都不可靠）。配置简化：只保留 `inlineMath: [['$', '$']]`，`$$...$$` 由 MathJax 默认处理。路径用 `/assets/mathjax/tex-chtml.min.js`（绝对路径，在所有子页面有效）。**不能使用 `async`**。详见 `references/20260601-mathjax-cdn-async-fix.md` 和 `references/vault-website-setup.md`。
- 🖱️ **Mermaid 图点击放大** — 所有 mermaid 图支持点击全屏放大（暗色遮罩+95vw SVG），点击遮罩关闭
- 🎙️ 播客页 `/podcast/` — 播客列表 + 内嵌播放器
- 📂 子目录 index.html — 文件列表 + 播客徽章
- 🌙 深色模式 — 自动跟随系统 `prefers-color-scheme`
- 📑 ToC — 可折叠目录（默认收起，手机上一行，点开展开，无悬浮）
- 🖼️ 可点击放大图片 — `![[...]]` 图片自动包裹 `<a target="_blank">`，点开看大图
- 🔗 反向链接 — 每篇底部显示「被以下笔记引用」
- 📍 面包屑 — 页面顶部 `首页 › 分类 › 笔记名`

**⚠️ vault 网站端口**：nginx 监听 9755，不是 80 也不是 8080。访问地址：http://192.168.3.121:9755/

**⚠️ 用户反馈「网站没更新」排查清单**：当用户说「网站没更新」时，按顺序排查：
1. **确认 nginx 端口**：vault 站点在 9755 端口。用户可能记住了旧的 8080 端口（旧 Quartz 站点已迁移到 `/旧站/`）
2. **检查文件时间戳**：`stat` 验证 .html 和 .png 文件的修改时间是否正确
3. **验证 nginx 实际发送的内容**：`curl` 直接访问 nginx URL，比较 `Last-Modified` 和 `Content-Length` 是否匹配磁盘文件
4. **浏览器缓存**：提醒用户 Ctrl+F5 强制刷新（不是普通 F5）
5. **检查 nginx 缓存配置**：确认站点配置中没有 `expires`/`proxy_cache`/`add_header Cache-Control` 等缓存指令
6. **验证 MathJax 脚本加载**（如果用户反馈公式未渲染）：检查 HTML 中 `/<script src="/assets/mathjax/tex-chtml.min.js"></script>` 是否被浏览器正确加载（DevTools Network 面板）

### 第4.7步：上传 index 和 HTML 到 GitHub

生成首页和 HTML 后，立即提交并推送到 GitHub。如果论文关联关系有修改，可选运行知识图谱生成：

```bash
python3 /opt/data/profiles/wechat-2/scripts/generate_kg.py
```

```bash
cd /opt/data/obsidian-vault
git add -A
git commit -m "auto: regenerate vault index and HTML [skip ci]"
git -c http.proxy=http://127.0.0.1:7890 push
```

**注意**：如果代理（Clash）未运行，git push 可能因 GitHub 在中国直连不通而失败。**先尝试带代理的 push（`git -c http.proxy=http://127.0.0.1:7890 push`），若代理也未运行 git push 也可能直接成功（视网络环境而定）。** 若 push 失败，跳过 push，后续 Step 6 统一同步。

**验证**：push 后，在服务器端 curl 验证更新已生效。如果用户反馈"没看到更新"，按 `references/vault-website-setup.md` 的「Troubleshooting」清单排查。

**批量场景**（主 agent 批量写笔记后）：写完所有笔记后统一跑一次 generate_index.py + git commit/push，见「批量精读策略」章节末尾。在批量场景的父 agent 汇总步骤中增加：
```python
# 最后：生成索引 + 上传
terminal("python3 /opt/data/profiles/wechat-2/scripts/generate_index.py")
terminal("cd /opt/data/obsidian-vault && git add -A && git commit -m 'auto: regenerate vault index [skip ci]' && git -c http.proxy=http://127.0.0.1:7890 push")
```

### 第5步：更新 JSON 知识库（新论文）

将**新论文**（JSON 中不存在的）元数据追加到 `/opt/hermes/arxiv_papers_2024_2026.json`（注意：根结构可能是 list 或 dict['papers']）：

```python
import json
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
# 安全检查根结构
if isinstance(data, dict) and 'papers' in data:
    papers_list = data['papers']
else:
    papers_list = data if isinstance(data, list) else []
papers_list.append(new_entry)
with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data if isinstance(data, dict) else papers_list, f, ensure_ascii=False, indent=2)
```

### 第6步：同步到 GitHub

分析笔记写入知识库后，运行同步脚本推送变更。

**⚠️ 在中国网络环境下需要 Clash 代理：** `sync_knowledge.sh` 内部调用 `git push` 到 GitHub，直连可能 TLS 握手失败。推送前先确保代理运行：

```bash
# 检查代理状态
curl -s --max-time 5 -x http://127.0.0.1:7890 https://www.google.com -o /dev/null -w "%{http_code}"
# 若返回非200，启动代理
# ⚠️ 不能在前台terminal用 & 后台化 — 必须用 terminal(background=true)
# terminal(background=true, command="mihomo -d /root/.config/clash/")
# sleep 3 后验证代理可通，再执行同步
bash /opt/hermes/scripts/podcast-tools/sync_knowledge.sh
```

如果代理已运行但 git push 仍失败（GnuTLS handshake），需要显式指定代理：
```bash
cd /opt/data/obsidian-vault && git -c http.proxy=http://127.0.0.1:7890 push
```

**注意：** `arxiv_papers_2024_2026.json` 位于 `/opt/hermes/`（非 git repo），不会随 vault 同步。JSON 更新是本地操作。

### 方式H：文件夹分类清理与不相关论文批量删除

**场景：** 用户要求清理某个分类文件夹（如"把3D-VLM目录里不相关的删掉"），只保留真正属于该分类的论文。

**工作流：**

1. **全面扫描**：列出文件夹下所有 .md 文件，确认哪些是占位符（300-600 字节，仅含 arXiv 链接）哪些有深度分析
2. **边界论文确认**：对分类模糊的论文，用 curl 查 arXiv 摘要页确认核心内容：
   ```bash
   curl -sL -x http://127.0.0.1:7890 "https://arxiv.org/abs/XXXX.XXXXX" | grep -oP '<meta name="citation_title" content="\K[^"]+'
   ```
   或用 delegate_task 并行查询多个 arXiv 页面。
3. **判断标准示例**（以 3D-VLM 为例）：
   - KEEP：同时涉及 3D（场景/点云/3D 空间推理）AND VLM/LLM/MLLM
   - REMOVE → 纯 3D 文件夹：纯 3D 重建/理解方法（无语言组件）
   - REMOVE → 删除：2D 空间推理 benchmark、非 3D 评估
4. **执行删除**（.md + .html 都删，keep 只保留 .md 因 .html 由 generate_index 重新生成）：
   ```python
   # 按关键词列表批量删除
   remove_keywords = ["SpatialTree", "GRAFT", ...]
   for fn in os.listdir(folder):
       for kw in remove_keywords:
           if kw.lower() in fn.lower():
               os.remove(os.path.join(folder, fn))
   ```
5. **清理搜索索引**：搜索.html 的 INDEX 数组（第 149 行 JSON），移除匹配的条目
6. **清理 JSON**：同时检查 `/opt/hermes/arxiv_papers_2024_2026.json` 和 vault 的 JSON 副本，移除对应 arXiv ID
7. **重新生成网站 + Git 推送**

**⚠️ 注意：**
- 不要按内容模式匹配删除（`(待补充...)` 过滤），只按明确的关键词/arXiv ID 列表删除
- 被删除的笔记都是占位符（300-600 字节），不是深度分析，无需担心数据丢失
- JSON 中一般不存在这些占位符论文，但需要检查确认
- 删除后运行 generate_index.py 会自动处理断链和目录列表更新

**场景：** 一个文件夹的全部（或大部分）论文已深度分析，需要写一篇整合性全景技术脉络笔记并生成播客。

**工作流：**
1. **pro模型全景笔记**：创建一次性 cron job，prompt 要求阅读文件夹下所有深度笔记（cat *.md → /tmp/all.txt 批量读取），写全景分析笔记到 `分析笔记/` 目录
2. **播客预处理**：笔记写好后，去除 frontmatter + Markdown 表格 + mermaid 代码块 + `![[图片]]` 引用
3. **豆包播客**：`terminal(background=true, notify_on_complete=true, timeout=600)` 运行 podcast_gen.py
4. **发布**：publish_podcast.py 发布到 GitHub + RSS

**实战数据（2026-05-20，21篇 Feed-Forward 前馈重建）:**
- 全景笔记：483行 / 28KB
- 预处理后：4KB（去表格/mermaid/图片后核心叙事文本）
- 播客输出：52轮 / 14:47 / 10.6MB

**⚠️ 注意：**
- 全景笔记和已有笔记不冲突——这是新的综合分析笔记，存于 `分析笔记/`，不覆盖单篇论文笔记
- 生成后运行 generate_index.py（自动处理播客玩家嵌入）
- 表格去过 + 无表格 -> 豆包内容更贴合原文

有两种方式：

**方式A：短话题（快速出，2min）**
```bash
/opt/hermes/.venv/bin/python3 /opt/hermes/scripts/podcast-tools/gen_and_publish.py \
  "论文名: 核心话题" "简述论文内容..."
```

**方式B：完整笔记作为话题（15min+，更详细）**

⚠️ **内容坑（2026-05-18 实测）**：豆包话题模式对专业技术论文可能生成**完全无关**的内容。PointForward 笔记（7.5KB）做话题时，生成的播客音频与论文完全不相关。

**修复方案：传入前预处理——去除 Frontmatter 和 Markdown 表格**。表格数据会干扰豆包对叙事主线的理解。

```python
import re
text = re.sub(r'\|[^\n]+\|(\n\|[:\- |]+\|)?', '', full_note)  # 去表格行
text = re.sub(r'---.*?---', '', text, flags=re.DOTALL)        # 去 frontmatter
```

预处理后 PointForward 笔记 7.5KB→1.8K（1783字符），31轮/7:30min，内容贴合原文。
**发表前必先验证前30s音频或RSS描述。**
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

⚠️ **内容坑：** 豆包话题模式对专业论文可能生成**完全无关**的内容。用完整笔记做话题前，必须先验证前30s音频或RSS描述。替代方案：用300-500字摘要做话题（内容更可靠），或改用脚本模式（action=3）。详见 `self-built-podcast` skill 的「局限」章节。

**已验证**：SLAM-Former 分析后，300字话题→2:15播客；13KB完整笔记→30轮对话播客（需要300s+）。
参见 `self-built-podcast` skill 获取完整播客建指南。

---

## 批量精读策略（多论文并行）

当需要一次性精读多篇论文时（如清理知识库中的待补充笔记），可以使用 `delegate_task(tasks=[...])` 并行处理，每批最多 3 篇：

1. **按子趋势分组** — 将同类论文（如"流式重建"相关）放入同一批次，便于跨论文对比
2. **每篇一个子代理** — 独立下载PDF、提取文本、精读、写分析文件
3. **父代理收集整理** — 子代理返回后，读取分析文件写入Obsidian vault + 复制架构图 + 删除旧占位符

**已验证（2026-05-18）：** 14 篇论文分 5 批并行精读，约 10 分钟完成全部。每篇产生 5-14KB 分析笔记，含架构图。

**注意：** 子代理的摘要输出是自报告，写入 vault 后仍需手动验证文件完整性。子代理的分析文件路径不定（/root/ 或 /tmp/ 或 /opt/data/home/），父代理需搜索并统一收集。

论文笔记按以下目录组织（`/opt/data/obsidian-vault/论文笔记/`）：

| 目录 | 说明 |
|------|------|
| `3DGS/` | 3D Gaussian Splatting 相关 |
| `NeRF/` | NeRF 相关 |
| `Feed-Forward 前馈重建/` | 前馈式3D重建（核心——DUSt3R/VGGT系列及所有变体，约75篇） |
| `前馈重建效率优化/` | 前馈重建效率优化（VGT/DUSt3R加速、Token选择等，如GoodTokenHunting/SparseVGGT）。注意：VGT加速类论文**不归**3DGS效率优化 |
| `3D 生成/` | 3D内容生成（TripoSR/Bolt3D/MeshLRM/世界模型等） |
| `3D目标检测/` | 3D检测 |
| `SLAM/` | SLAM相关 |
| `SfM与BA/` | Bundle Adjustment、SfM（可微BA/隐式BA/雷达BA等） |
| `深度估计/` | 深度估计（含光流SEA-RAFT） |
| `视觉基础模型/` | 自监督视觉模型（DINO/DINOv2/v3、SSM架构、生成式预训练） |
| `MLLM与3D/` | 多模态大语言模型+3D理解 |
| `人体重建/` | 人体/手部重建（Human3R/POEM等） |
| `分析笔记/` | 综合分析笔记（技术脉络、跨论文对比） |

---

## 注意事项

- **诚实归因**：明确区分"论文原文结果"vs"个人推断"
- **封面图片**：分析笔记可选配图片，使用 `![alt](url)` 格式
- **双向链接**：使用 `[[已有笔记]]` 语法建立知识库关联
- **避免重复**：每次写笔记前先检查是否已存在
- **同步GitHub**：分析完成后一定运行 `sync_knowledge.sh` 同步
- **模型选择**：本 skill 设计为使用 pro 模型运行，在 cron job 中通过 `model: {"model": "deepseek-v4-pro", "provider": "deepseek"}` 指定

## 查询精读进度

**当用户问「全部精读完了吗」「精读进度如何」「还有多少篇没精读」时：**

⚠️ **禁止凭 session_search 记忆回答** — 会话历史会遗漏/延迟最新进度，给出不准确答案。

**正确做法：直接读知识库 JSON 源数据：**

```python
import json
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers']

total = len(papers)
with_note = sum(1 for p in papers if p.get('笔记路径'))
no_note = [p for p in papers if not p.get('笔记路径')]

print(f'总论文数: {total}')
print(f'已精读（有笔记路径）: {with_note}')
print(f'未精读（无笔记路径）: {total - with_note}')
print()

# 列出未精读论文
for p in no_note:
    print(f'{p["arXiv号"]} | {p.get("标题前几个词", "?")} | 分类: {p.get("分类", "未分类")}')
```

**同时交叉验证 vault 磁盘文件（注意 `论文笔记/` 前缀变体）：**
```bash
# 总笔记数
find /opt/data/obsidian-vault/论文笔记/ -name "*.md" -not -name "知识库总览*" -not -name "index*" | wc -l
```

**完整精读进度审核脚本（含路径前缀容错）:**
```python
import json, os

with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers']

vault_base = '/opt/data/obsidian-vault'

deep = 0           # 笔记文件存在且≥2KB
shallow = 0        # 笔记文件存在但<2KB（占位符）
missing_file = []  # 有笔记路径但文件不存在
empty_path = []    # 笔记路径为空

for p in papers:
    note_path = p.get('笔记路径', '').strip()
    if not note_path:
        empty_path.append(p)
        continue

    # 尝试带前缀和不带前缀两种变体
    full_path = os.path.join(vault_base, note_path)
    if not os.path.exists(full_path):
        adjusted = note_path.replace('论文笔记/', '', 1)
        full_v2 = os.path.join(vault_base, '论文笔记', adjusted)
        if os.path.exists(full_v2):
            full_path = full_v2
        else:
            missing_file.append(p)
            continue

    size = os.path.getsize(full_path)
    with open(full_path) as fh:
        lines = fh.readlines()

    if size >= 2048 or len(lines) >= 20:
        deep += 1
    else:
        shallow += 1

print(f'总论文: {len(papers)}')
print(f'✅ 深度笔记 (≥2KB): {deep}')
print(f'⚠️ 占位符笔记 (<2KB): {shallow}')
print(f'❌ 文件不存在: {len(missing_file)}')
print(f'❌ 无笔记路径: {len(empty_path)}')
if missing_file:
    print('\n文件不存在的论文:')
    for p in missing_file:
        print(f'  {p["arXiv号"]} | {p.get("笔记路径","")}')
if empty_path:
    print('\n无笔记路径的论文:')
    for p in empty_path:
        print(f'  {p["arXiv号"]} | {p.get("标题前几个词","?")}')
```

**报告格式：** 表格展示已精读/未精读数，列出具体未精读论文清单，询问是否需要启动批量精读。

**为什么不能信 session_search：** session_search 返回的是历史会话摘要，可能未包含最新 cron 结果，且 cron job 可能中途截断（精读完但没写入笔记/更新JSON），导致已精读论文被误报为未完成。

## 用户偏好

### 日报论文不写笔记，只发邮件

**规则（2026-05-28 设定）：** 每天 7:00 的 arXiv 日报（cron ID: `0f38955352a5`）只做：获取论文 → 筛选 → 查作者 → 生成邮件 → 发送 → 记录已发 ID。**不写任何 Obsidian 笔记到知识库**。

**邮件格式（2026-05-31 更新）：** 模板在 `/opt/data/profiles/wechat-2/scripts/send_daily_email.py`。结构：
- TOP 3 论文：每篇含标题、作者、摘要、核心贡献、详细分析（4段）
- 其余论文：按子主题分组，每篇一个简要概述（1-2句核心贡献）
- 邮件末尾用分隔线区分两组

**每日 5:30 的论文分析 cron（ID: `57cb48d5a00b`）已暂停。** 不再自动精读日报论文。

**触发条件：** 只有当用户明确说「精读」「写笔记」「分析这篇论文」时，才创建一次性 cron job 用 pro 模型写笔记。

⚠️ **不要自行判断「这篇论文很重要应该写笔记」** — 宁可漏写也不要擅写。用户会在需要时明确要求。

### 始终用子agent分析论文

**⚠️ 核心规则：分析论文必须用子agent（一次性cron job + pro模型），不要直接在主对话中做。**

当用户说"精度""精读""分析这篇论文"时，应当：
1. 创建一次性 cron job（方式一），使用 pro 模型（deepseek-v4-pro）
2. 将微信文章上下文、论文ID、已有笔记路径等信息全部写入 prompt
3. cron job 自动运行并 deliver 回 origin
4. 主 agent 等待结果即可

**不要做：**
- 直接在对话中下载PDF、提取文本、精读——这是主agent的活，不是子agent的
- 用自己的模型分析——pro模型的深度分析质量更高
- 替子agent写完笔记——子agent会覆盖更新

**为什么：**
- 用户明确要求用子agent分析（被纠正过）
- pro模型的推理深度远超flash模型
- cron job 方式可以独立设置模型，无需影响当前对话的模型
- 分析结果自动发回微信，主agent和用户都能看到

### 事件触发优先于轮询

**规则**：用完成后立即运行的一次性步骤替代定期 cron。当需要在"做完某事后"执行后续操作时，直接在流程中增加步骤，不要创建定期 cron 轮询。

**例子**：
- ❌ 不要：`cron("*/5 * * * *", script="generate_index.py")` — 每5分钟轮询一次
- ✅ 要：在 Step 4.6 中直接 `python3 generate_index.py` — 写笔记后立即触发

**适用范围**：文件变更、状态检查、索引更新等所有"有明确触发事件"的场景。

### 验证后再通知

**规则**：用户说"你自己验证好了再通知我"时，必须：
1. 做完整��验证清单——测试所有 URL、检查错误日志、确认文件存在
2. 先验证全部通过
3. 再一次性通知用户结果

**验证清单模板**：
- 关键 URL 返回 200
- 错误日志无新增异常
- 数据文件（JSON、索引）存在且时间戳正确
- 外部 IP 模拟访问通过
- 权限正确（nginx 用户、目录权限）

### 后处理步骤链

写完笔记/生成文件后，后续操作按顺序执行（不要遗漏）：
1. generate_index.py（重新生成首页 + HTML 渲染）
2. git add/commit/push（上传到 GitHub）

---

## 删除论文笔记流程

当需要**删除单篇论文分析笔记**（空骨架/错误内容/已废弃）时，必须清理全部6个引用点，否则留下断链：

### 步骤清单

```bash
# 1. 删除文件（.html + .md）
rm "分析笔记/Pixie： Foo Bar.html"
rm "分析笔记/Pixie： Foo Bar.md"

# 2. 从 JSON 知识库移除（主 JSON + vault JSON 两份）
python3 -c "
import json
for path in ['/opt/hermes/arxiv_papers_2024_2026.json',
             '/opt/data/obsidian-vault/arxiv_papers_2024_2026.json']:
    with open(path) as f:
        data = json.load(f)
    papers = data['papers'] if isinstance(data, dict) else data
    papers = [p for p in papers if p.get('arXiv号') != 'XXXX.XXXXX']
    if isinstance(data, dict):
        data['papers'] = papers
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
"

# 3. 从分类目录 index.html 移除条目
# 用 patch 工具删除 `<li><a href="XXX.html">...标题...</span></a></li>`

# 4. 从搜索 INDEX 数组移除
python3 -c "
import json, re
with open('/opt/data/obsidian-vault/论文笔记/搜索.html') as f:
    content = f.read()
lines = content.split('\n')
idx_line = lines[148]  # 搜索索引在第149行
start = idx_line.find('[')
end = idx_line.rfind('];')
arr = json.loads(idx_line[start:end+1])
new_arr = [item for item in arr if '目标论文标题关键词' not in item.get('title', '').lower()]
lines[148] = idx_line[:start] + json.dumps(new_arr, ensure_ascii=False) + idx_line[end+1:]
with open('/opt/data/obsidian-vault/论文笔记/搜索.html', 'w') as f:
    f.write('\n'.join(lines))
"

# 5. 确认无残留
grep -rn '论文名\|arXiv.ID' /opt/data/obsidian-vault/论文笔记/ --include='*.html' --include='*.md' | grep -v '其他\.' | grep -v '跨领域'

# 6. Git 同步
cd /opt/data/obsidian-vault && git add -A && git commit -m '清理: 删除空骨架论文名' && git -c http.proxy=http://127.0.0.1:7890 push
```

### 分析笔记 vs 论文笔记删除的区别

**分析笔记**（位于 `论文笔记/分析笔记/`）**不在 arxiv_papers_2024_2026.json 中**，因此删除流程比论文笔记简单得多：
- ✅ 只需：`rm .md + .html` → `generate_index.py` → `git push`
- ❌ 不需要：更新 JSON、清理搜索 INDEX、清理分类目录 index.html、清理 wikilink 引用
- 分析笔记的引用仅存在于标签页（由 generate_index.py 自动重建），rm 后重新生成即自动消除

**论文笔记**（位于分类目录如 `3DGS/`、`Feed-Forward 前馈重建/`）必须走完整的 6 步清理流程（见上方「删除论文笔记流程」）。

### ⚠️ 批量删除分析笔记（按日期）— 读 frontmatter，不要用文件 mtime

当需要按日期删除分析笔记时（如「删除5月7日及之前的笔记」），**绝对不要用文件系统 mtime**（`ls -la` 显示的时间）——git checkout、git restore 等操作会重置 mtime 为当前时间，导致按日期筛选完全错误。

**正确做法：读笔记的 YAML frontmatter 中的 `date:` 或 `created:` 字段。**

#### 检测脚本

```bash
cd /opt/data/obsidian-vault/论文笔记/分析笔记/
# 查看所有笔记的创建日期
for f in *.md; do
  created=$(grep -m1 -E "^(date|created):" "$f" | sed 's/^.*: *//')
  echo "${created:-无日期}  $f"
done | sort
```

**⚠️ 术语澄清：** 用户说"只看标题里的日期"时，「标题」指的是笔记的 **frontmatter `title:` 字段所在区域**（文件抬头），**不是 H1 标题 `# xxx`**。「从名字来看日期」中的「名字」也是指 frontmatter 的 `date:`/`created:` 字段。文件系统 mtime（`ls -la` 时间）因 git checkout 等操作会被重置为当前时间，完全不可靠。

#### 🔴 深坑：用户反转删除方向 — 先恢复再确认，不要猜

**症状（2026-05-28 实测长达 5 轮来回纠正）：**
```
用户: "删除5月7日及之前的笔记" → 我删了17篇
用户: "删多了，今天生成的都不见了" → 我恢复
用户: "只删除5.7之后的" → 我删了5篇（反向）
用户: "错了！我说反了" → 我恢复
用户: "你从名字来看日期" → 我换方法
用户: "就按这个日期删吧" → 终于正确
```

**根因：** 用户自己也在想「应该删哪个方向」，表述前后不一致。主 agent 每次跟随最新指令立即执行，没有做「先恢复/确认再执行」的 safety check。

**正确做法（防坑流程）：**

当用户首次提出按日期删除笔记时，立刻做两件事：
1. **列出当前全部笔记及其 frontmatter `date`/`created` 字段**，让用户看到完整列表
2. **指出删除范围**：「将删除 N 篇（X月X日及之前），保留 M 篇（Y月Z日之后），对吗？」

```bash
cd /opt/data/obsidian-vault/论文笔记/分析笔记
for f in *.md; do
  created=$(grep -m1 -E "^(date|created):" "$f" | sed 's/^.*: *//')
  echo "${created:-无日期}  $f"
done | sort
```

如果用户反转方向（说「只删除5.7之后」后又纠正为「5.7及之前」），**不要立即执行**：
1. 先 `git checkout HEAD -- 论文笔记/分析笔记/` 恢复所有文件
2. 重新列出带日期的完整列表
3. 让用户确认「删这些，留这些」的精确范围

**永远不要在用户反转后猜测正确方向——必须恢复到原始状态后重新确认。**

#### Python 脚本精确删除（推荐）

分析笔记的 frontmatter 有两种日期字段格式：
- `date: 2026-05-07`（部分早期笔记）
- `created: 2026-05-07`（多数 cron 生成的笔记）

用 `re` 匹配两种格式，精确删除目标日期范围的笔记：

```python
import os, re, glob

for f in glob.glob("论文笔记/分析笔记/*.md"):
    with open(f) as fh:
        content = fh.read()
    
    date_match = re.search(r'^(?:date|created):\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if not date_match:
        print(f"⚠️ 无日期字段, 保守保留: {f}")
        continue
    
    dt = date_match.group(1)
    if dt <= "2026-05-07":  # 替换为实际截止日期
        name = f.replace(".md", "")
        os.remove(f"{name}.md")
        if os.path.exists(f"{name}.html"):
            os.remove(f"{name}.html")
        print(f"DEL: {name}")
    else:
        print(f"KEPT: {name}")
```

完成后执行：
```bash
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py
cd /opt/data/obsidian-vault && git add -A && git commit -m "删除5月7日及之前的分析笔记(N篇)" && git push
```

删除后执行：
```bash
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py
cd /opt/data/obsidian-vault && git add -A && git commit -m "删除早期分析笔记" && git push
```

### 删除后的清理步骤（完成批量删除后必须执行）

#### 1. 删除空目录

删除占位符笔记后，子目录可能变空（仅剩 index.html）。检查并删除：

```bash
cd /opt/data/obsidian-vault/论文笔记
for d in */; do
  md_count=$(find "$d" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l)
  if [ "$md_count" -eq 0 ]; then
    echo "空目录: $d"
    rm -rf "$d"
  fi
done
```

同时删除父级分类索引 .md（如 `3D 分割.md`、`NeRF.md` 等），因为它们引用的子目录已不存在。

#### 2. 重建 JSON 论文关联关系（related 字段）

从 vault 笔记的「知识库关联」章节提取论文关系，自动重建 JSON 的 `related` 字段：

**原理**：每篇深度笔记在结尾有 `## 知识库关联` 章节，包含 `[[笔记标题]] — 关系类型：说明` 格式的条目。通过解析这些条目，可以自动建立论文间的双向关联。

**流程（可用 pro 模型一次性 cron job 执行）：**

```python
import os, re, json, shutil

# 1. 建立 笔记标题 → arXiv ID 映射
vault_base = '/opt/data/obsidian-vault'
title_to_aid = {}
for root, dirs, files in os.walk(os.path.join(vault_base, '论文笔记')):
    for fn in files:
        if not fn.endswith('.md'): continue
        title = fn.replace('.md', '')
        with open(os.path.join(root, fn)) as fh:
            content = fh.read(2000)
        m = re.search(r'^(?:arxiv_id|arxiv):\s*(\S+)', content, re.MULTILINE)
        if m:
            title_to_aid[title] = re.sub(r'v\d+$', '', m.group(1))

# 2. 解析每篇笔记的知识库关联章节
# 格式: - **[[笔记标题]] — 关系类型**：说明
# 关系映射: 继承/基础/前身→继承, 互补→互补, 对比/对照→对比, 相似/平行→相似, 打破/颠覆→打破

# 3. 加载 JSON，为每篇论文重建 related 字段（双向）
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data

# ... 遍历 papers, 从 vault 笔记中提取关系写入 related ...

# 4. 保存并同步
with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
shutil.copy('/opt/hermes/arxiv_papers_2024_2026.json',
            '/opt/data/obsidian-vault/arxiv_papers_2024_2026.json')
```

**验证：**
```bash
# 检查断链数量
python3 -c "
import json;
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    d = json.load(f)
p = d['papers'] if isinstance(d, dict) else d
all_aids = {re.sub(r'v\d+$', '', x.get('arXiv号','')) for x in p}
broken = sum(1 for x in p for r in x.get('related',[]) if r['id'] not in all_aids)
print(f'断链: {broken}')
"
```

#### 3. 同步 JSON 到 vault

```bash
cp /opt/hermes/arxiv_papers_2024_2026.json /opt/data/obsidian-vault/arxiv_papers_2024_2026.json
```

#### 4. 提交并推送

```bash
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py
cd /opt/data/obsidian-vault
git add -A && git commit -m "vault维护: 批量清理占位符+重建关联" && git -c http.proxy=http://127.0.0.1:7890 push
```

### 删除笔记后的空目录清理

批量删除笔记后，原目录可能只剩 `index.html`（由 generate_index.py 生成）或完全为空。这些空目录需要清理。

**检测脚本：**
```bash
cd /opt/data/obsidian-vault/论文笔记
for d in */; do
  md_count=$(find "$d" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l)
  if [ "$md_count" -eq 0 ]; then
    echo "空目录: $d"
    rm -rf "$d"
  fi
done
```

**同时清理父级分类索引：** 如果子目录被删除，对应的父级分类索引文件（如 `论文笔记/3D 分割.md`、`论文笔记/NeRF.md`）也应一并删除，因为它们引用的论文已不存在。

```bash
# 检查并删除对应的父级分类索引
for f in 论文笔记/3D 分割.md 论文笔记/NeRF.md 论文笔记/统一3D框架.md; do
  if [ -f "$f" ]; then
    rm -f "$f" "${f%.md}.html"
  fi
done
```

**清理后：** 重新生成网站 + git push。generate_index.py 会自动处理 URL 断链。

### 重建论文关联关系（从知识库关联章节）

**场景：** 用户要求「重新建立所有论文关联关系」。不适用于单篇增量更新，适用于全局重构。

**最佳方法：从 vault 每篇笔记的「知识库关联」章节解析 Obsidian wiki 链接，自动重建 JSON 的 `related` 字段。**

#### 工作原理

每篇深度笔记的 `## 知识库关联` 章节包含标准格式的关联条目：
```markdown
- **[[DINOv2]] — 继承**：DINOv3 直接基于 DINOv2 的自蒸馏框架...
- **[[VGGT]] — 互补**：VGGT 使用 DINOv2 作为 backbone...
```

解析流程：
1. 扫描全部笔记，建立 `标题 → arXiv ID` 映射（读 frontmatter）
2. 提取每篇笔记的 `## 知识库关联` 章节
3. 解析 `[[笔记标题]]` → 查 arXiv ID
4. 解析 `— 关系类型`（继承/互补/对比/相似/打破）
5. 双向写入 JSON `related` 字段

#### 关系类型映射

| wiki 标记 | JSON 关系类型 |
|-----------|--------------|
| 继承/基础/前身 | `继承` |
| 互补/下游应用/发现问题 | `互补` |
| 对比/对照 | `对比` |
| 相似/平行 | `相似` |
| 打破/颠覆 | `打破` |

#### 完整 cron job 模板

```python
cronjob(
    action="create",
    name="小驴：重建论文关联关系",
    prompt=\"\"\"你被称为「小驴」，是用户的深度研究助手。
从 vault 每篇笔记的「知识库关联」章节提取论文间关系，重建 JSON 的 `related` 字段。

## 步骤
1. 建立标题→arXiv ID 映射（扫描所有 .md 的 frontmatter）
2. 提取每个笔记的「知识库关联」章节中的 [[wiki链接]] 和关系类型
3. 为每篇论文重新构建 related 字段（双向）
4. 保存 JSON + 同步到 vault + 提交到 GitHub
\"\"\",
    skills=["paper-analyst"],
    model={"provider": "deepseek", "model": "deepseek-v4-pro"},
    schedule="1m",
    deliver="origin",
    enabled_toolsets=["terminal", "file"]
)
```

#### 注意事项
- `[[笔记标题]]` 可能使用 `[[标题|显示别名]]` 格式，需要去掉 `|` 后面的部分
- 分析笔记（`分析笔记/` 目录）中的知识库关联不写入 JSON（分析笔记没有 arXiv ID）
- 如果笔记没有「知识库关联」章节，则保留其现有 related 字段，不清空
- 最终验证：检查断链关联（related 中引用的 ID 不在 JSON 中）和未设 related 的论文
- 关联关系重建后用 `shutil.copy` 同步 JSON 到 vault

#### 实战数据（2026-05-28）
- 176 篇论文，152 篇（86%）原有关联，836 条关联条目
- 重建后消除 58 条断链关联（指向已删除 placeholder 笔记的条目）
- 发现 2 条断链路径（TurboVGGT、SplatWeaver 文件位置变更）

**注意事项：**
- **搜索索引**: INDEX 在搜索.html 的**第 149 行**（整行 JSON 数组），不要用正则匹配大括号——用 json.loads 安全解析再序列化回写
- **分类 index.html**: 用支持 fuzzy match 的 patch 工具按唯一字符串删除，不要整行盲删
- **Obsidian vault JSON**: 可能独立于主 JSON（不同步的副本），**两个 JSON 都需清理**
- **跨笔记引用**: 综述笔记中的 `[[Pixie]]` wikilink 会变成灰色断链，这是正常行为——被删除笔记的引用应由相关笔记作者决定是否移除
- **Git push**: 删除后必须立刻推送，否则下次网站生成（generate_index.py）会将已删笔记的断链重新暴露

### ⚠️ 批量删除目录中的占位符笔记（按大小/行数/内容判断）

**场景：** 用户要求清理某个目录（如 `3DGS/`）中的「不符合精读格式」的笔记——通常是只有 frontmatter + 标题的骨架笔记。

**不同于「按日期删除分析笔记」：** 分析笔记（`分析笔记/` 目录）按 frontmatter 的 `date`/`created` 字段判断。而分类目录（如 `3DGS/`）的占位符按 **文件大小 + 行数 + 内容** 判断。

#### 判断标准

| 类型 | 行数 | 大小 | 内容特征 |
|------|------|------|----------|
| 占位符 | < 30行 | < 1KB | 仅有 frontmatter + `# 标题` + arXiv 链接，无 `## 核心思想` 等章节 |
| 深度笔记 | ≥ 60行 | ≥ 3KB | 有 `## 核心思想`、`## 技术方法`、`## 实验结论` 等完整章节 |

**注意：** 部分论文同时有占位符和深度版本（相同 arXiv ID）。只删占位符，保留深度版本。

#### 检测脚本

```python
import os, re

for f in sorted(os.listdir(directory)):
    if not f.endswith('.md'):
        continue
    size = os.path.getsize(f)
    with open(f) as fh:
        content = fh.read()
    lines = content.count('\n') + 1
    
    # 判断占位符：小尺寸 + 缺少核心章节
    has_core = any(kw in content for kw in ["## 核心思想", "## 技术方法", "## 实验结论", "## 核心贡献"])
    
    if size < 1000 and lines < 30 and not has_core:
        # 检查是否有对应深度版本（同 arXiv ID）
        deep_by_arxiv = {}  # 预构建 {arxiv_id: deep_note_name}
        if arxiv_id and arxiv_id in deep_by_arxiv:
            print(f"有深度版本，只删占位符: {f}")
        else:
            print(f"无深度版本，直接删除: {f}")
        os.remove(f)
        # 同时删除对应的 .html
        html = f.replace('.md', '.html')
        if os.path.exists(html):
            os.remove(html)
```

#### 批量删除完整工作流

```python
cd /opt/data/obsidian-vault/论文笔记/{分类目录}

# 1. 分析所有.md文件
python3 << 'PYEOF'
import os, re, glob

# 读取全部文件，建立 arxiv_id → 文件名的映射（用于找深度版本）
all_files = {}
deep_by_arxiv = {}
for f in glob.glob("*.md"):
    size = os.path.getsize(f)
    with open(f) as fh:
        content = fh.read()
    lines = content.count('\n') + 1
    arxiv = ''
    m = re.search(r'^arxiv(?:_id)?:\s*(\S+)', content, re.MULTILINE)
    if m:
        arxiv = re.sub(r'v\d+$', '', m.group(1))
    has_core = any(kw in content for kw in ["## 核心思想", "## 技术方法", "## 实验结论", "## 核心贡献"])
    all_files[f] = {'size': size, 'lines': lines, 'arxiv': arxiv, 'has_core': has_core}
    if not (size < 1000 and lines < 30 and not has_core):
        if arxiv:
            deep_by_arxiv[arxiv] = f

# 2. 找出占位符
to_delete = []
for f, info in all_files.items():
    if info['size'] < 1000 and info['lines'] < 30 and not info['has_core']:
        if info['arxiv'] and info['arxiv'] in deep_by_arxiv:
            print(f"有深度版本 [{deep_by_arxiv[info['arxiv']]}] → 删占位符: {f}")
        else:
            print(f"无深度版本 → 直接删除: {f}")
        to_delete.append(f)

# 3. 执行删除
for f in to_delete:
    os.remove(f)
    html = f.replace('.md', '.html')
    if os.path.exists(html):
        os.remove(html)

print(f"\n删除了 {len(to_delete)} 个占位符")
PYEOF

# 4. 检查 JSON 中是否有这些论文的笔记路径，如有则清空
python3 -c "
import json
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers']
deleted_basenames = [...]  # 从上面删除的文件名列表
updated = 0
for p in papers:
    np = p.get('笔记路径', '')
    if np:
        base = np.split('/')[-1].replace('.md', '')
        if base in deleted_basenames:
            p['笔记路径'] = ''
            updated += 1
with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'清空了 {updated} 条 JSON 笔记路径')
"

# 5. 同步JSON到vault + 重新生成网站 + 推送
cp /opt/hermes/arxiv_papers_2024_2026.json /opt/data/obsidian-vault/arxiv_papers_2024_2026.json
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py
cd /opt/data/obsidian-vault && git add -A && git commit -m "清理{分类}: 删除N篇占位符笔记" && git push
```

**⚠️ 注意：**
- 不要用内容模式匹配（如 `(待补充...)`）做全局删除——知识库中不同笔记可能有不同形式的"不完整"标记
- 判断占位符最可靠的指标是**文件大小 < 1KB 且 < 30 行且无核心章节**，三者缺一不可
- JSON 中一般不存在这些占位符论文的笔记路径，但仍需检查确认
- 删除后运行 generate_index.py 会自动处理断链和目录列表更新

#### 实战数据（2026-05-28，3DGS目录清理）

- 总笔记: 105 篇（.md + .html），其中 58 篇占位符（~21行, 300-600B），47 篇深度笔记（51-268行）
- 6 篇占位符有对应深度版本（如 pixelSplat 同时有英文占位符 + 中文深度版），仅删占位符
- 52 篇占位符无深度版本，直接删除
- JSON无受影响条目（占位符从未写入 JSON）
- 耗时: ~1 分钟（含 generate_index.py 重新生成）

### ⚠️ 全局清理：全 vault 按大小阈值删除占位符笔记

**场景：** 用户要求清理整个 vault 中不符合精读格式的笔记（如「<2KB的都删了」）。不同于单目录清理——需要全 vault 扫描，跳过分类索引页，处理所有 `论文笔记/` 下的分类子目录。

#### 注意事项

- **保留分类索引页**：如 `论文笔记/3D 分割.md`、`论文笔记/NeRF.md` 等含有「共 N 篇论文」和「返回 [[知识库总览]]」内容的文件是系统索引，**不能删除**
- **保留非论文目录**：`智能家居/`、`日记/`、`标签/`、`每日简报/`、`附件/`、`项目/` 中的文件不是论文笔记，不处理
- **分析笔记**：「分析笔记」目录的笔记不在 `arxiv_papers_2024_2026.json` 中，删除后只需 rm + 重新生成网站 + push
- **JSON 清理**：删除的占位符笔记从未写入 JSON（占位符不设笔记路径），通常无需更新 JSON。但如果占位符有笔记路径（清空之）

#### 检测脚本

```python
import os, re

# 系统/分类索引文件，需保留
system_keep = {
    "智能家居/总览.md",
    "论文笔记/3D 分割.md", "论文笔记/3D 综述.md",
    "论文笔记/NeRF.md", "论文笔记/统一3D框架.md",
}

threshold = 2048  # 2KB，也可设为 3072 (3KB)
to_delete = []

for root, dirs, files in os.walk("."):
    if ".git" in root:
        continue
    for fn in files:
        if not fn.endswith(".md"):
            continue
        fpath = os.path.join(root, fn)
        rel = os.path.relpath(fpath, ".")

        size = os.path.getsize(fpath)
        if size >= threshold:
            continue

        # 跳过系统索引文件
        if rel in system_keep:
            continue

        # 跳过分类索引页（含"共 N 篇论文"）
        with open(fpath) as fh:
            content = fh.read(500)
        if "共 " in content and "篇论文" in content:
            continue

        delete.append(rel)

# 执行删除（.md + .html）
for f in delete:
    os.remove(f)
    html = f.replace(".md", ".html")
    if os.path.exists(html):
        os.remove(html)
```

#### 完整工作流

```bash
# 1. 检测并删除
python3 << 'PYEOF'
import os, re
threshold = 2048
system_keep = {"智能家居/总览.md", "论文笔记/3D 分割.md", ...}
# ... 上述检测脚本 ...
PYEOF

# 2. 重新生成网站
python3 /opt/data/profiles/wechat-2/scripts/generate_index.py

# 3. 提交并推送
cd /opt/data/obsidian-vault
git add -A
git commit -m "全局清理: 删除N篇<XKB的占位符笔记"
git push
```

#### 实战数据（2026-05-28，全局 <2KB 清理）

- 扫描 vault 全部 179+ .md 文件
- 识别 46 篇占位符笔记（~22-29行，337-1081B），跨 15 个分类目录
- 保留 5 个系统/索引页（智能家居总览、3D分割、3D综述、NeRF、统一3D框架）
- JSON 无受影响条目（占位符从无笔记路径）
- 网站重新生成后，标签页和分类索引自动消除断链

### 示例（2026-05-20 实测）

删除 Pixie（arXiv 2508.17437）空骨架笔记时清理了：
1. HTML + MD 文件（分析笔记/ 目录）
2. 主 JSON：/opt/hermes/arxiv_papers_2024_2026.json（index 57）
3. vault JSON：/opt/data/obsidian-vault/arxiv_papers_2024_2026.json（index 57）
4. 分析笔记 index.html（移除 li 条目）
5. 搜索.html INDEX 数组（234→233 条）
6. git commit f0bd430，推送到 GitHub

---

## 已知坑与应对

### 🔴 深坑: arXiv ID 与论文标题不匹配 — pro 模型自动纠错

**症状（2026-05-22 实测）：** 用户指定 `2504.12551` 为 VGGT-DET，cron job 下载 PDF 后发现实际是 DFT 论文（与 3D 检测无关）。pro 模型通过 arXiv 搜索找到正确论文 `2603.00912`（VGGT-Det: Mining VGGT Internal Priors...），自动修正后完成精读。用户未被通知这一纠正，直到 session_search 才看到。

**根因：** 用户或主 agent 可能记错 arXiv ID，或论文被撤稿/更新。cron job 子 agent 若没有任何 cross-check 逻辑，会精读一篇完全无关的论文。

**正确做法（双重验证流程）：**
1. cron job 启动后第一件事：`curl` arXiv abs 页获取真实标题
2. 将真实标题与用户期望名称做**模糊匹配**（关键词比对）
3. 明显不匹配时（如用户说"VGGT-DET"但标题是"DFT: ..."），**暂停精读**，输出警告并尝试查找正确 ID
4. 查找方法：arXiv API 搜索 `search_query=all:VGGT-DET`
   ```bash
   curl -sL -x http://127.0.0.1:7890 "https://export.arxiv.org/api/query?search_query=ti:VGGT-DET&max_results=3"
   ```
5. 找到正确 ID 后，在最终输出中**明确标注**："⚠️ 用户提供的arXiv ID {xxx} 对应论文标题不匹配预期，已自动修正为 {yyy}"

**cron job prompt 模板应包含验证步骤**：
```python
# 在 prompt 开头注入验证逻辑
"第一件事：验证 arXiv ID 是否真的对应 VGGT-DET。用 curl 获取标题，与预期名称比较。
如果完全无关（如 DFT 论文），暂停并搜索正确 ID。"
```

### 🔴 深坑: VGGT家族论文名称混淆 — 同名不同ID

**症状（2026-05-22 实测）：** 用户说"检索PAGE-4D和VGGT-DET"，subagent 搜不出 PAGE-4D。用户随后补充 arXiv ID "2511.19971"，未验证就直接命名为「PAGE-4D」创建 cron job。实际 2511.19971 是 **VGGT4D**（VGGT4D: Mining Motion Cues...），而真正的 PAGE-4D 是 **2510.17568**（PAGE-4D: VGGT-4D Perception via Disentangled Pose...）。两篇完全不同。

**根因：** 多个 VGGT 系列扩展论文有非常相似的中英文名称（VGGT4D / VGGT-DET / VGGT-Edit / PAGE-4D），主 agent 凭印象匹配 arXiv ID→名称犯了错。

**正确做法（双重验证）：**
1. 用户提供论文名（无 arXiv ID）→ 先用 arXiv API 或搜索页查找匹配的 ID
2. 用户提供 arXiv ID → 先 `curl` arXiv 页面获取真实标题再命名 cron job：
   ```bash
   curl -sL -x http://127.0.0.1:7890 "https://arxiv.org/abs/XXXX.XXXXX" | grep -oP '<meta name="citation_title" content="\K[^"]+'
   ```
3. 不要凭记忆匹配名称和 ID，尤其是 VGGT/DUSt3R 系列名称相似度高的论文
4. cron job 的 `name` 参数和笔记文件名必须使用正式标题，而非猜测名称

参考 `references/paper-id-discovery.md` 获取完整检索方法。

### 🔴 深坑: 回答用户时漏计数 — 说"两篇"其实是三篇

**症状（2026-05-22 实测）：** 用户问还有哪几篇没精读，回答"两篇马上跑"——但实际是 VGGT-Edit（已精读完） + VGGT4D + VGGT-DET = **3篇**。用户纠正"大哥，一共是3篇"。

**根因：** 主 agent 心里把已完成的 VGGT-Edit 排除在计数外，只说了"待跑的两篇"，但用户关心的是"总共涉及几篇"这个总数。沟通角度不对齐。

**正确做法：** 向用户报告论文列表时，**按总数呈现，不要按子状态分类呈现后不说合计**。用表格列出全部论文及其状态（✅完成/⏳进行中），让用户一目了然看到完整概览。例如：

| # | 论文 | 状态 |
|---|------|------|
| 1 | VGGT-Edit | ✅ |
| 2 | VGGT4D | ⏳ |
| 3 | VGGT-DET | ⏳ |

**总计：3篇**（1已完成，2待完成）

### 🔴 深坑: `md_to_html()` 输出裸 `<tr><td>` 没包 `<table>` — 表格在浏览器中完全不可见

**症状（2026-05-26 发现并修复）：** GemDepth 笔记的 6 个实验结论表格在网页上完全消失（`<table>` 标签数为 0）。浏览器只认 `<tr>` 包在 `<table>` 里的结构，裸 `<tr>` 不渲染。

**根因：** `generate_index.py` 的 `md_to_html()` 函数每行生成 `<tr>` 但从来不打开 `<table>` 包裹标签——缺失 `html += '<table>\n<tbody>\n'` 和关闭 `</tbody>\n</table>\n`。

**修复（3处 patch）：**
1. 增加 `in_table` 状态变量追踪是否在表格中
2. 第一条表格行前加 `<table>\n<tbody>\n`，最后一行后加 `</tbody>\n</table>\n`
3. 文件末尾（`return html.strip()` 前）额外检查 `in_table` 以防表格结束在文件末

**预防：** `md_to_html()` 中所有写 `<tr>` 的代码必须成对打开/关闭 `<table>`。非表格的 `||5.` 行（首格为空）需过滤: `if not cells or not cells[0]: continue`

**检出方法：** 检查任意 HTML 页面的 `<table>` 数与 `<tr>` 数是否匹配：
```bash
python3 -c "
with open('page.html') as f: c = f.read()
t, r = c.count('<table>'), c.count('<tr>')
print(f'table={t} tr={r} bare={r-t} (should be 0)')
```

**症状（2026-05-26 发现并修复）：** 标签云中出现 `--` 标签，点击显示 SAIL-Recon 等笔记。extract_tags() 的第二个正则 `^tags:\s*\n(\s*-\s*[^\n]+)+` 在匹配 `- xxx` 行时，会吞入 YAML 结束符 `---`（`\s*-\s*[^\n]+` 把 `---` 匹配为 `-` + `--`）。最终标签为 `--`。

**根因：** 正则的 `+` 贪婪量词持续匹配后续行，`---` 行被 `\s*-\s*[^\n]+` 捕获。

**修复（generate_index.py L249）：**
```python
for t in m.group(0).split('\n')[1:]:
    if t.strip().startswith('---'):  # skip YAML delimiter
        continue
    tag = re.sub(r'^\s*-\s*', '', t).strip().strip('"\'')
    if tag:
        tags.append(tag)
```

**预防：** extract_tags() 中任何新写的 tag 解析代码必须跳过 `---` 开头行。build_tag_index() 中已添加长度 < 2 的过滤守卫。

**症状（2026-05-22 实测）：** 每日 cron 扫描 65 篇 sent ID，全部显示「无笔记」— 0/65。但实际上 36/65 有完整深度笔记（如 TurboVGGT 179行、VGGT-Ω 275行、RoSplat 245行等）。

**根因：** 扫描代码使用 `aid = m.group(1).rstrip('v0123456789')` 剥离版本后缀。Python 的 `rstrip()` 剥离**所有**在字符集中的尾部字符，而非仅剥离完整字符串：
- `"2605.14315".rstrip('v0123456789')` → `"2605.1431"`（剥离了末尾的 `5`！）
- `"2605.15195".rstrip('v0123456789')` → `"2605.1519"`（剥离了末尾的 `5`！）
- 剥离后 ID 与 sent ID 不匹配 → 全部假阴性 → cron 反复重分析已完成论文

**正确做法：** 用正则只剥离显式版本后缀：
```python
# ❌ 错误
aid = m.group(1).rstrip('v0123456789')

# ✅ 正确
aid = re.sub(r'v\d+$', '', m.group(1))
# "2605.14315" → "2605.14315"  (不变)
# "2605.14315v2" → "2605.14315" (只剥离 'v2')
```

**影响范围：** 本 skill 中所有扫描代码已全部修复。新写代码必须遵循此规范。详细正确模板见 `references/vault-frontmatter-scan-correct-idiom.md`。

### 坑： `arxiv_papers_2024_2026.json` 只覆盖 2024 年后的论文

**症状（2026-05-28 实测）：** DINO (2104.14294) 和 DINOv2 (2304.07193) 是知识库中大量笔记的前身/基础，但它们本身不在 JSON 中（发表早于 2024）。用户要求补写笔记时，需要手动创建 JSON entry + 笔记。

**正确做法：**
- JSON 默认只包含 2024+ 论文，但 DINO/DINOv2 等奠基性论文应手动加入
- 加入时 insert 到列表开头（`papers.insert(0, new_entry)`）以保持顺序
- 笔记路径、分类、核心贡献等字段补齐
- 将 JSON 副本同步到 vault：`shutil.copy('/opt/hermes/arxiv_papers_2024_2026.json', '/opt/data/obsidian-vault/arxiv_papers_2024_2026.json')`
- 笔记放在同级目录（`视觉基础模型/`），不新建子目录

**⚠️ 用户偏好（2026-05-28）：** 论文笔记应放在同级目录而非二级子目录。用户说「不用新建二级目录了，把1和2的笔记补上」——说明同系列论文放在同一个分类目录下即可，不需要为每个系列创建子目录。

**根因：** 知识库中大量论文只有占位符（arXiv + 标题 + 待补充），它们分布在所有分类目录中。按内容匹配会误删全部。

**正确做法：**
- 只删除**明确已知**不再需要的文件，按文件名列表或目录操作
- 通过 `find | xargs grep -l` 统计后再决定，不要直接用 rm -rf 或 os.remove()
- 新旧笔记替换用「写新文件 + 删旧文件」两步走，确保新文件写完后再删
- 永远不要用内容模式匹配做全局删除

**恢复方法：**
JSON 知识库是权威元数据源。被误删的占位符可从 JSON 重建：
```python
import json, os
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data
for paper in papers:
    arxiv_id = paper.get('arXiv号', '')
    # 在 vault 中扫描此 arxiv ID 是否存在
    # 如不存在，从 JSON 的标题+核心贡献 字段重建
```

### 深坑: read_file 批量读取短笔记时触发去重限制

**症状：** 连续 read_file 多个笔记，第3次起被拦截 "BLOCKED: ... 3 times"。

**正确做法：** 批量浏览短文件用 terminal 的 head 或 cat：
```bash
cd /vault/目录 && for f in *.md; do echo "=== $f ==="; head -30 "$f"; done
```
或 execute_code 中用 Python open() 直接读取。

### 坑: frontmatter 格式不一致 — `arxiv:` vs `arxiv_id:`

**症状（2026-05-21 实测）：** 每日 cron job 去重扫描发现 62 篇 sent ID 全部"未分析"，但实际上 SplatWeaver (2605.07287) 已有 442 行深度笔记在 vault。导致重复分析已完成的论文，浪费 pro 模型 token。

**根因：** 旧笔记使用 `arxiv: 2605.07287`（无 `_id` 后缀），而扫描正则 `^arxiv_id:\s*(\S+)` 不匹配此格式。另外 TurboVGGT 旧笔记虽然有标准 `arxiv_id:` frontmatter，但其文件名与搜索预期不符（中文名 vs 英文名）。

**正确做法：**
1. 始终用 `re.search(r'^(?:arxiv_id|arxiv):\s*(\S+)', content, re.MULTILINE)` 同时匹配两种格式
2. 写作新笔记时**始终使用 `arxiv_id:` 标准格式**（写入旧格式是一次性的历史遗留问题）
3. 覆盖旧笔记后，删除旧的 .md + .html 文件，避免 vault 中同一论文有两份笔记
4. 清理后立即运行 `generate_index.py` + `git push` 保持网站一致

### 坑: JSON 笔记路径字段大量缺失 → cron 反复重分析

**症状（2026-05-21 实测）：** JSON 中仅 32/133 篇有 `笔记路径` 字段，但 vault 实际有 46 篇笔记（含 frontmatter `arxiv_id` 的）。扫描结果与实际严重不符，导致大量已完成论文显示为"未分析"。

**根因：** 过去写笔记时跳过了 Step 4.5（更新 JSON `笔记路径`），或笔记由子 agent 写入后主 agent 未执行 JSON 更新。

**修复：运行扫补脚本**，交叉对比 vault frontmatter 与 JSON，补填所有缺失的 `笔记路径`：
```python
import json, os, re

# 扫描 vault 提取 arxiv_id → path 映射
vault_base = '/opt/data/obsidian-vault'
vault_aids = {}
for root, dirs, files in os.walk(os.path.join(vault_base, '论文笔记')):
    for fn in files:
        if not fn.endswith('.md'):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path) as f:
                content = f.read(3000)
            m = re.search(r'^(?:arxiv_id|arxiv):\s*(\S+)', content, re.MULTILINE)
            if m:
                # ⚠️ 只用 re.sub 剥离版本后缀 v1/v2，不能用 rstrip('v0123456789')
                aid = re.sub(r'v\d+$', '', m.group(1))
                # 存储两种路径变体：带前缀和不带前缀
                # vault_aids 存完整的 relpath（含 论文笔记/）
                rel_with_prefix = os.path.relpath(path, vault_base)
                vault_aids[aid] = rel_with_prefix
        except:
            pass

# 更新 JSON
with open('/opt/hermes/arxiv_papers_2024_2026.json') as f:
    data = json.load(f)
papers = data['papers'] if isinstance(data, dict) else data
updated = 0
for p in papers:
    # ⚠️ 只用 re.sub 剥离版本后缀，不能用 rstrip('v0123456789')
    aid = re.sub(r'v\d+$', '', p.get('arXiv号', ''))
    if aid in vault_aids and not p.get('笔记路径', '').strip():
        # ⚠️ 使用带 论文笔记/ 前缀的路径，保持一致性
        p['笔记路径'] = vault_aids[aid]
        updated += 1

with open('/opt/hermes/arxiv_papers_2024_2026.json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"补填了 {updated} 条笔记路径")
```
**2026-05-21 实测：一次补填 85 条，32→117。**

**预防：** 每次写完笔记后严格执行 Step 4.5。批量场景中父 agent 必须对所有完成的论文统一更新 JSON。

### ⚠️ 坑: JSON _笔记路径_ 前缀不一致 — `论文笔记/` 前缀缺失

**症状（2026-05-21 实测）：** 查询精读进度时，123/133 篇 JSON 说有笔记路径，但按路径查找时 95 篇"文件不存在"——实际上笔记文件存在，只是 JSON 路径缺了 `论文笔记/` 前缀。

**根因：**
- 扫补脚本最初使用 `os.path.relpath(path, '/opt/data/obsidian-vault')` 生成路径，结果为 `论文笔记/分类/文件.md`（含前缀）
- 但一些早期条目直接写 `分类/文件.md`（无前缀），且 cron job 创建脚本用 `论文笔记/` 前缀模板写路径
- 两种格式混用，导致按路径查找时一半以上匹配失败

**检查代码（两条路径变体都要验证）：**
```python
note_path = p.get('笔记路径', '').strip()
full_path = os.path.join(vault_base, note_path)
if not os.path.exists(full_path):
    # 尝试补上/去掉 论文笔记/ 前缀
    adjusted = note_path.replace('论文笔记/', '', 1)
    full_path2 = os.path.join(vault_base, '论文笔记', adjusted)
    if os.path.exists(full_path2):
        full_path = full_path2  # 路径在前缀变体上存在
    else:
        # 文件真的不存在
        ...
```

**预防：**
1. **统一规范**：JSON 中 `笔记路径` 统一存储为 `论文笔记/分类/文件名.md`（带前缀，因为 vault 根目录下可能有其他文件）
2. **写入时检查**：写入 笔记路径 前检查是否以 `论文笔记/` 开头，若无则添加
3. **读取时容错**：任何读取笔记路径并验证文件存在的代码，必须尝试两种变体

### 深坑: cron job ISO 时间已过导致任务不触发

**症状：** 创建一次性 cron job 时用了 ISO 时间格式 `2026-05-19T13:42:00`，但该时间已经过去，任务从未执行且没有任何报错。

**根因：** cron scheduler 对已过的时间静默忽略，不触发也不报错。创建者以为任务很快执行，实际永远不会。

**正确做法：**
1. **永远先 `date` 确认系统当前时间**再计算未来时间
2. 推荐用持续时间格式 `30m`、`2h`，让系统自动计算未来时间
3. 如果用 ISO 时间，至少留 2-3 分钟余量
## 已知坑与应对

### 🔴 深坑: 设计新功能前先检查现有代码 — 不要重新造轮子

**症状（2026-06-01 实测）：** 用户提出论文讨论助手需求后，我设计了完整的子 agent + 前端方案并准备实现。但实际代码（api_server.py + generate_index.py + nginx）早已全部写好并部署——用户不得不喊停「停停停，看看聊天记录」。

**根因：** 主 agent 凭记忆认为「需要做新功能」，没有先检查现有代码中是否已有实现。

**正确做法：设计/实现新功能前的三连检查：**
1. **检查网关 API 路由**：`grep -n "add_post.*/api/" /opt/hermes/gateway/platforms/api_server.py` 查看已注册的端点
2. **检查前端渲染**：`grep -n "def _make" /opt/data/profiles/wechat-2/scripts/generate_index.py` 查看已有的页面组件生成函数
3. **检查 nginx 代理**：`grep "location /api/" /etc/nginx/sites-enabled/*` 查看已配置的路由

如果其中一个存在但其他不存在，说明功能是部分实现的，需要补全而非重做。

### 🔴 深坑: 论文讨论助手 JS 错误排查链

**症状（2026-06-01 实测）：** 用户反馈「发了内容没反应」，控制台报错：

1. `Identifier FPATH has already been declared` — discuss 脚本和 delete 脚本都声明了 `const FPATH` 和 `const NTITLE`，`const` 重复声明导致整个 JS 停摆
2. `Failed to execute insertBefore on Node` — `appendMessage` 以 `.qa-list` 为容器，但输入框 `.discuss-input-area` 是 `.qa-list` 的兄弟节点而非子节点
3. 大量 woff 404 — 浏览器自动请求系统字体，不影响 JS 运行，可忽略

**修复：**
1. 删掉 delete 脚本中的 `const FPATH` 和 `const NTITLE`（discuss 脚本已有，`deleteNote` 引用全局变量即可）
2. `appendMessage` 始终用 `.discuss-container` 做容器，不要回退到 `.qa-list`
3. 页面刷新后显示历史：JS 在页面加载时 fetch `/讨论记录/{STEM}.json` 加载已有 QA 并渲染

**症状（2026-06-01 实测）：** 添加 `[[wikilink]]` 到笔记的知识库关联章节后，用户说「mask2former里面没看到」——网站显示的仍是 `[[DETR]]` 文字而非可点击链接。

**根因：** generate_index.py 的 build_wikilink_map() + md_to_html() 已经内建 `[[wikilink]]`->`<a>` 自动转换。但 .html 文件被 check-in 到 git 仓库，只改 .md 不跑 generate_index.py 的话已有的 .html 不会更新。

**正确做法（首选）：用 `[[wikilink]]` 语法 + 运行 generate_index.py。** 不需要手动编辑 .html：
1. 在 .md 中写 `[[DETR]]` 或 `[[DETR|显示名]]` 语法
2. 运行 python3 generate_index.py 重新生成全部 HTML
3. git add/commit/push

注意：generate_index.py 的 wikilink 解析依赖文件名匹配，不是 frontmatter title。不存在的论文会渲染为灰显断链文本。

**备选方案：** 同时修改 .md 和 .html，见 references/vault-wikilink-maintenance.md。

### 🔴 深坑: 更新笔记时产生重复章节（知识库关联/独特观点/批判等）

**根因：** 更新已有笔记时，追加内容只关注「添加」，忽略了「检查已有章节并合并」。每次追加 `related` 条目或新关联时直接在文件末尾创建了新的 `## 知识库关联` 而非追加到已有的第一个。

**后果：** 用户直接发现并指出「为什么出现了两次知识库关联」，需要手动合并修复。

**正确做法（写入或更新笔记时的强制检查）：**
1. **写入前扫描**：`grep -c '^## [A-Za-z0-9\u4e00-\u9fff]' <file>` 检查各章节是否存在
2. **唯一性要求**：每个章节标题在文件中只能出现一次。如果章节已存在，追加条目到该章节末尾；如果不存在，在合理位置创建
3. **更新后验证**：在 Step 4.6 之前增加验证：
   ```bash
   for section in "知识库关联" "深度分析与独特见解" "批判与改进建议"; do
     count=$(grep -c "^## $section" "$note_path")
     if [ "$count" -gt 1 ]; then
       echo "❌ $section 章节重复（$count次）"; exit 1
     fi
   done
   ```
4. **修复已有**：如果发现重复章节，用 Python 合并：保留第一个章节，删除后续重复章节的全部条目（含标题行）

**预防：** 所有写入/更新 vault 笔记的代码（子 agent、cron job、手动流程）必须将「章节唯一性」加入写入后验证清单，尤其是「知识库关联」「深度分析与独特见解」「批判」等可能在多次更新中追加的章节。

### 坑: 子代理渲染整页当架构图 → 用户投诉图片太大包含文字

**症状：** pro 模型子代理（一次性 cron job）提取架构图时用了 `page.get_pixmap(dpi=200)` 渲染整页，结果图片包含了标题、摘要文字、图注，用户反映"整页都截进去了"。

**根因：** 方案B（已弃用）渲染 PDF 整页导致架构图混杂正文文字。子代理可能加载了旧版 skill 或读错代码。

**正确做法：**
1. 方案A优先：提取嵌入式图片。若最大图 < 500px（宽），说明架构图是矢量绘制
2. 用 pypdf 搜索 "Figure" / "Pipeline" 确定架构图所在面——**不是第1页**（Figure 1 通常是对比概览，不是方法图）。架构图一般是 Figure 2 或 Figure 3
3. 用 `page.get_text("blocks")` 获取文本块坐标，找到 figure caption 的 y 作为下边界
4. 用 **200 DPI** + `fitz.Rect` clip 裁剪出图区域（不含 caption 文字）
5. **绝不使用无 clip 的 `get_pixmap` 渲染整页**

### 坑: 方案A提取嵌入式图片时解出全部子图 → 仓库被小图标污染

**症状：** Dark3R 的 PDF 包含 15 张 Figure 1 的子图/照片，方案A的 `page.get_images()` 把它们全部解出并写入 vault，造成 repo 多了 30+ 个 50-500KB 的小图文件（`dark3r_fig1_image0.jpg` 等）。

**根因：** `get_images(full=True)` 返回 PDF 页面上所有嵌入图片，包括构成 Figure 1 的多个照片子图、小图表、logo 等，它们并非模型架构图。

**正确做法：**
1. 方案A只保存**最大的一张嵌入式图片**（通常是架构图），方法见 Step 2.5
2. 若最大图 < 500px（宽），说明架构图是矢量绘制，转方案B裁剪
3. **绝不**批量提取并保存全部嵌入式图片
4. 若已有冗余图片被提交，在 git commit 前检查：`ls .../*_fig*.*`，多余的图片删掉再 push

### 🔴 深坑: 图提取先于去重确认 → 已分析论文的图片污染 vault

**症状（2026-05-27 实测）：** 每日 cron 在去重扫描发现 Cross3R (2605.07978) 在 JSON 中但未被 cross-reference 脚本识别为已分析，于是下载 PDF 并提取了 `Cross3R_架构图.png` 和 `Cross3R_对比概览.png` 到 vault。后续验证发现该论文已有 485 行深度笔记——必须手动清理残留图片。

**根因：** 图提取（Step 2.5）在「下载 PDF → 提取前2页文本」后立即执行，但此时尚未运行完整的去重验证（vault frontmatter 扫描）。交叉脚本的 `json_map` 构建可能因不同的解析逻辑产生 false-negative。

**正确做法：**
1. **图提取前增加第二步确认**：下载 PDF 后不立即提取图，先确认论文确实需要在 vault 中新建笔记
2. 确认逻辑：直接检查 vault 文件系统的 frontmatter（`re.search(r'^(?:arxiv_id|arxiv):\s*(\S+)', content)`），而不是仅依赖 JSON 判断
3. 如果已有笔记且大小 ≥ 2KB，**跳过整篇**——包括图提取
4. 图提取的 vault 路径应与笔记路径同级，所以笔记不存在时图也没地方放

**验证（2026-05-27）：** Cross3R 的架构图被保存到 vault 后又手动 `rm` 清理。

**症状：** 覆盖更新已有笔记时，旧笔记中的 `![[论文名_架构图.xxx]]` 引用的扩展名与实际磁盘文件扩展名不一致（如旧笔记写 `.jpeg`，实际文件是 `.png`）。

**根因：** 架构图提取工具（fitz）按 PDF 嵌入图片的原始扩展名保存（常见 `jpeg`/`png`），但笔记中可能被手工写成了不同的扩展名。

**正确做法：** 覆盖旧笔记前，先用 `ls` 确认架构图文件的实际扩展名：
```bash
ls /opt/data/obsidian-vault/论文笔记/{分类}/论文名_架构图.*
```
然后在笔记中使用匹配的扩展名：`![[论文名_架构图.png]]`（或 `.jpeg`/`.webp` 等）。

**预防：** 所有写入/更新 vault 笔记的代码（子 agent、cron job、手动流程）必须将「章节唯一性」加入写入后验证清单，尤其是「知识库关联」「深度分析与独特见解」「批判」等可能在多次更新中追加的章节。

### 坑: Vault文件名不含arXiv ID → 按文件名匹配全部失败

**症状：** 执行每日 cron 去重时，用 `find vault -name "*13093*"` 按 arXiv ID 搜索 vault 文件，返回 0 结果，但实际上 RoSplat (2605.13093) 的笔记已存在于 vault。

**根因：** Vault 中的笔记文件名使用论文标题（如 `RoSplat Robust Feed-Forward Pixel-wise Gaussian Splatting.md`），**不包含** arXiv ID 数字。同样，其他 vault 文件的命名也以标题为主，少数包含 ID 缩写但无规律。

**正确做法：**
1. **必须在 frontmatter 中提取 `arxiv_id` 字段**来匹配，不能用文件名：
```python
import os, re
for root, dirs, files in os.walk(vault_base):
    for fn in files:
        if fn.endswith('.md'):
            with open(os.path.join(root, fn)) as fh:
                content = fh.read(3000)
            m = re.search(r'^arxiv_id:\s*(\S+)', content, re.MULTILINE)
            if m:
                # ⚠️ 只用 re.sub 剥离版本后缀 v1/v2，不能用 rstrip('v0123456789')
                aid = re.sub(r'v\d+$', '', m.group(1))
                # aid 就是可匹配的规范化ID
```
2. 部分旧笔记可能缺少 frontmatter 的 `arxiv_id` 字段，此时需要从标题行或文件内容中搜索 arXiv URL 模式作为备选
3. 每日 cron 的去重逻辑**不应依赖文件名匹配**，应始终走 frontmatter 扫描路径

**验证（2026-05-20）：** 58篇 sent ID 按文件名匹配返回 0 篇 vault 有笔记；改为 frontmatter 扫描后正确识别出 49 篇已有完整笔记。

### ⚠️ 坑: DPT scales [4,2,1,0.5] 在 Uniform ViT backbone 下输出尺寸错误

**症状（2026-05-30 实测）：** ViT³ (Uniform) + DPT 的输出只有 28×28 而非 224×224。

**根因：** DPTDecoder 的 `scales = [4, 2, 1, 0.5]` 是针对多分辨率 backbone（如 Swin）设计的——假设 4 级特征分别在 H/16, H/8, H/4, H/2 分辨率。但 **Uniform ViT 的所有中间特征都在同一分辨率 H/16**。使用 [4,2,1,0.5] 时，第 4 级特征被 0.5× 下采样到 H/32，导致最终融合分辨率只有 H/32，4× 上采样后仅 H/8。

**正确做法：** Uniform ViT backbone 用 `scales = [4, 4, 4, 4]`，所有特征都 4× 上采样到 H/4，融合后再 4× 到 H。

**适用场景：** 标准 ViT、ViT³ (Uniform DeiT-like)、以及其他所有 patch embed 后不做下采样的 backbone。

**检出方法：**
```bash
python3 -c "
from vittt3_dpt import ViT3DPTSeg
m = ViT3DPTSeg(variant='tiny')
out = m(torch.randn(1,3,224,224))
print(out.shape)  # 应为 [1,21,224,224]
"
```

### ⚠️ 坑: ViT³ (Uniform) 不使用 cls_token 和 pos_embed

**症状：** `RuntimeError: shape '[2, 14, 14, 192]' is invalid for input of size 75648` — Block 的 reshape 失败。

**根因：** ViT³ 的 Block 内有 `self.cpe` (Conditional Position Encoding, 3x3 DWConv)，它替代了标准 ViT 的绝对位置编码 + CLS token。官方代码的 `__init__` 虽然定义了 cls_token 和 pos_embed（为兼容 timm 权重加载），但 **forward 中从不使用它们**。如果添加了 CLS token，Block 内的 `h = w = int(sqrt(N))` 会因 N+1 不是完全平方数而报错。

**正确做法：** 实现 Uniform ViT³ backbone 时，全程不用 cls_token 和 pos_embed。`forward` 中：`x = self.patch_embed(x)` 后直接 `self.blocks(x)`，Block 内通过 CPE 提供位置感知。

### 坑: 权重加载: 官方 checkpoint 包含 yacs.config.CfgNode

**症状：** `_pickle.UnpicklingError: Weights only load failed. GLOBAL yacs.config.CfgNode`

**根因：** 清华云盘下载的官方权重（PyTorch 2.x 格式）使用 `torch.save` 保存了包含 `yacs.config.CfgNode` 配置对象的完整 checkpoint。PyTorch 2.6+ 默认 `weights_only=True` 阻止了非安全类的加载。

**修改：** `torch.load(path, weights_only=False)`

### ⚠️ 坑: torch 2.6.0 的 PolyLR → PolynomialLR API 变更

**症状：** `AttributeError: module 'torch.optim.lr_scheduler' has no attribute 'PolyLR'`

**原因：** PyTorch 2.6.0 将 `PolyLR` 重命名为 `PolynomialLR`，参数增加了 `total_iters`（原 PolyLR 不需要）。Windows 版 conda 默认会装 torch 2.6.0+cu124，旧训练代码中的 `PolyLR(optimizer, power=0.9)` 需要改为 `PolynomialLR(optimizer, power=0.9, total_iters=args.epochs)`。

**检查方法：**
```python
import torch
print(hasattr(torch.optim.lr_scheduler, 'PolynomialLR'))  # True in 2.6+
```

### ⚠️ 坑: 大文件 SCP 通过 WSL 端口转发（2222）会断连

**症状：** `Connection reset by peer port 2222` — 几百 MB 以上的 SCP 传输在 WSL 端口转发上失败。

**原因：** Windows OpenSSH + WSL 的端口转发（netsh interface portproxy 2222→:22）对大文件传输的 TCP 稳定性不够。使用直连 Windows 原生 SSH 端口 22 可以稳定传输。

**正确做法：** 连接 Windows 始终使用端口 22（直连 OpenSSH Server），不要走 WSL 端口 2222 转发。

```bash
# ❌ 不稳定（WSL 端口转发，大文件必断）
sshpass -p 'pw' scp -P 2222 file.tar lulu@192.168.3.82:D:\\
# ✅ 稳定（直连 OpenSSH Server）
sshpass -p 'pw' scp -o StrictHostKeyChecking=no file.tar lulu@192.168.3.82:D:\\
```

### 坑: GitHub 同步需代理 + terminal `&` 后台化被拦截

**症状：** `sync_knowledge.sh` 执行 git push 时报 `GnuTLS handshake failed`，因为 GitHub 在中国网络下直连不通。尝试 `mihomo -d /root/.config/clash/ &` 启动代理被 terminal 工具拦截（"Foreground command uses '&' backgrounding"）。

**根因：** terminal 工具禁止前台模式使用 shell 级 `&` 后台化。

**正确做法：**
1. 用 `terminal(background=true, command="mihomo -d /root/.config/clash/ 2>&1")` 启动代理
2. `sleep 3` 后 `curl --max-time 5 -x http://127.0.0.1:7890 https://www.google.com` 验证
3. 执行 `sync_knowledge.sh`
4. 同步完成后 `process(action="kill", session_id="proc_xxx")` 关闭代理

## 参考文件

- `references/cross-paper-relationship-graph.md` — 建立论文间双向关联图谱的工作流（继承/互补/对比），含 Pre-2024 论文处理、批量 JSON 写入、反向关系说明规范
- `references/448-vram-batch-scaling.md` — ViT³+DPT 8GB GPU 上不同分辨率/batch 的 VRAM 实测，含 backbone 解冻导致的交换诊断\n- `references/html-diagram-pipeline.md` — HTML 图表渲染管线详解：Mermaid 集成、ASCII 树→mermaid、对齐表格→HTML 表格、文本演化路径自动转换、点击放大。所有 generate_index.py 图表渲染逻辑的权威参考。
- `references/paper-id-discovery.md` — 论文名称→arXiv ID 检索方法（API/curl/Google Scholar），含 subagent 不可用坑
- `references/vault-website-setup.md` — nginx vault hosting, HTML rendering, podcast player integration, wikilink resolution
- `references/website-discuss-button.md` — 网页讨论按钮设计模式（利用 nginx→gateway 代理，走 `/api/` 路由触发 WeChat 对话）
- `references/vault-wikilink-maintenance.md` — ⚠️ Batch convert `[[wikilink]]` to working hyperlinks in both `.md` and `.html` files. **Must modify both file types.** Title-to-path mapping approach for resolving wikilinks.
- `references/vault-frontmatter-scan-correct-idiom.md` — ⚠️ **MUST READ**: `rstrip('v0123456789')` bug — strips arXiv ID digits, causes 100% false negatives. Correct idiom: `re.sub(r'v\d+$', '', raw_id)`
- `references/cron-subagent-model-override.md` — cron job 替代 delegate_task 实现独立模型的模式详解
- `references/cross-paper-comparison.md` — 跨论文对比分析方法与维度框架
- `references/related-papers-graph.md` — 论文关联图谱格式与使用方式（继承/互补/对比关系类型）
- `references/20260518-session-log.md` — 2026-05-18 会话日志 论文分析
- `references/20260519-session-log.md` — 2026-05-19 会话日志 每日定时分析（时序问题+代理坑）
- `references/20260520-session-log.md` — 2026-05-20 会话日志 vault 首页搭建（nginx权限、动态索引、HTML渲染）
- `references/20260521-session-log.md` — 2026-05-21 会话日志 cron job精读（frontmatter格式不一致+JSON路径扫补+旧笔记清理）
- `templates/cron-job-paper-analysis.md` — 一次性 cron job 创建模板（含时间坑提示）
- `templates/vit-dpt-implementation.py` — 手写 ViT+DPT 语义分割模型模板（零外部依赖），精读模型架构论文后直接跑代码验证。含 ViT-Base 编码器 + DPT 4 级特征融合解码器 + 训练/推理流程
- `templates/vittt3-dpt.py` — 将 ViT³ (TTT) backbone 替换 ViT 的语义分割模型。含 TTT Block 手推闭式梯度、ViT³ 编码器（Tiny/Small/Base 三变体）、DPT 解码器、权重加载工具。用法: `python3 vittt3_dpt.py --variant tiny`
- `templates/train-vittt3.py` — ViT³+DPT 训练脚本，配套 `vittt3-dpt.py`。VOC 2012、PolyLR、分不同 LR 训练 backbone/decoder、自动下载数据集、断点续训
- `references/batch-parallel-deep-reading-2026-05-18.md` — 批量并行精读实战日志（37篇，~13个batch，含子代理输出收集坑）\n- `references/batch-parallel-deep-reading-2026-05-20.md` — 批量并行精读实战日志（7篇+拆分2篇，子代理直写vault模式，合并笔记拆分模式）\n- `references/batch-parallel-deep-reading-2026-05-20-3dvlm.md` — 3D-VLM 22篇批量精读实战日志（子代理路径失控+文件混淆+frontmatter修复）
- `references/related-papers-graph.md` — 论文关联图谱（JSON related字段）的维护方法与批量构建脚本模式
- `references/wechat-article-extraction.md` — 微信公众号文章内容提取方法（curl+正则，绕过CAPTCHA）
- `references/wechat-article-to-paper-analysis.md` — 公众号文章→论文精读完整工作流（提取→识别→子代理分析→验证架构图）
- `references/20260520-panoramic-synthesis-pipeline.md` — 全景分析笔记+播客流水线（21篇→全景笔记→播客）（定位页码+文本块坐标+74 DPI裁剪）
- `references/critique-improvements-example-gemdepth.md` — GemDepth 批判与改进建议实例，含6个维度的深层分析模板\n- `references/critique-improvements-example-gemdepth.md` — GemDepth 批判与改进建议实战示例，含6条完整的「核心矛盾+改进思路」写法，子 agent 可模仿此格式与深度
- `references/20260527-session-log.md` — 2026-05-27 每日 cron 精读（代理坑、图提取时序、cross-reference false-negative、PanoPlane 分析）
- `references/backbone-integration-for-dense-prediction.md` — 从论文仓库整合新 backbone 到 DPT/UPerNet 分割模型的系统流程（架构判断、特征提取、权重检查、模板创建）
- `references/remote-training-monitor.md` — 远程训练进度自动监控模式（no_agent cron + SSH bash脚本，用于在精读论文的同时监控长程训练）
