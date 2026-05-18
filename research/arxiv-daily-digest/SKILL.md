---
name: arxiv-daily-digest
description: "每日arXiv论文日报：筛选cs.CV相关论文、TOP分析、发送邮件摘要+PDF附件"
version: 1.3.0
author: Hermes Agent
prerequisites:
  commands: [curl, python3]
  environment: [SMTP邮箱凭据]
---

# arXiv Daily Digest Workflow

每天8:00自动执行，生成3D视觉方向日报并邮件发送。

## 步骤

### 0. 启动代理（如需）

先检查Clash代理是否已在运行：

```bash
curl -s --max-time 5 -x http://127.0.0.1:7890 https://www.google.com -o /dev/null -w "%{http_code}" 2>/dev/null || echo "0"
```

如果返回 `200` 则跳过；否则启动：

```bash
mihomo -d /root/.config/clash/ &
sleep 3
```

**⚠️ arxiv.org需在Clash Proxy规则中：** 确保 `/root/.config/clash/config.yaml` 的 `rules` 段包含：
```
- DOMAIN-SUFFIX,arxiv.org,Proxy
- DOMAIN-SUFFIX,arxivstatic.com,Proxy
- DOMAIN-SUFFIX,export.arxiv.org,Proxy
```
否则curl走代理时Clash仍会直连arxiv.org导致超时。可通过 `curl -s http://127.0.0.1:9090/rules | grep arxiv` 验证。如缺失，手动追加到 `- DOMAIN-SUFFIX,pypi.org,Proxy` 之后，并用 `curl -X PUT http://127.0.0.1:9090/configs -d '{"path":"/root/.config/clash/config.yaml"}'` 重载。

### 1. 获取最新论文

通过cs.CV的RSS feed获取最近论文（最多547条，RSS实际返回数量可能超过官方文档标注）：

```bash
curl -sL "https://rss.arxiv.org/rss/cs.CV" -H "User-Agent: Mozilla/5.0" --max-time 30 > /tmp/arxiv_rss_cv.xml
```

**📅 RSS日期说明：** RSS中的`pubDate`是arXiv**公布日**，不是论文实际**提交日**。每篇论文的提交日期需要从arXiv API或页面获取。一般规律：
- 新提交(new)论文：提交日在公布日之前3-7天
- 更新版(replace/cross)论文：提交日可能是几个月前
- 筛选时以RSS公布日为准，精读时再查实际提交日

### 1b. RSS为空时的回退方案

**⚠️ 周末/节假日RSS为空：** arXiv的RSS feed包含 `<skipDays>` 跳过周六日和节假日。因此：
- **周一早上执行时RSS可能返回0条** — 上次公布是周五，经过周末后feed重置
- 节假日后第一个工作日同样可能为空

**检测方法：** RSS解析后若 `<item>` 数量为0，说明feed当前为空。

**回退方案：** 使用arXiv export API搜索最近几天（May 13-14通常还有未处理的论文）：

```bash
# 方案A：按关键词搜索cs.CV中的3D相关论文
curl -s "https://export.arxiv.org/api/query?search_query=(cat:cs.CV)+AND+(abs:3d+gaussian+OR+abs:nerf+OR+abs:feed-forward+OR+abs:3d+reconstruction+OR+abs:slam+OR+abs:bundle+adjustment+OR+abs:novel+view+synth+OR+abs:depth+estimation+OR+abs:pose+estimation+OR+abs:implicit+representation)&sortBy=submittedDate&sortOrder=descending&max_results=200" -x http://127.0.0.1:7890 | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom'}
root = ET.parse(sys.stdin).getroot()
for entry in root.findall('a:entry', ns):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')[:120]
    published = entry.find('a:published', ns).text[:10]
    arxiv_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
    print(f'{arxiv_id} | {published} | {title}')
"
```

**API限流注意：** arXiv export API限流约1req/3s。一次查询200条不会触发（是单次请求），但多次连续调用需要注意间隔。

**检查提交日期分布：** 快速查看API返回的论文日期分布：

```bash
# 接上一步，在parse循环中添加日期计数
dates = {}
for entry in entries:
    d = entry.find('a:published', ns).text[:10]
    dates[d] = dates.get(d, 0) + 1
for d in sorted(dates.keys(), reverse=True):
    print(f'{d}: {dates[d]} papers')
```

筛选出提交日在最近2-3天的论文（排除已发ID后），用关键词列表手动过滤（同第2步关键词列表）。

### 2. 关键词过滤 (自动化脚本)

使用 `scripts/filter_arxiv_rss.py` 一键完成 RSS 下载 + 关键词过滤 + 去重 + 排名输出：

```bash
# 默认：cs.CV + 去重 + 全部结果
python scripts/filter_arxiv_rss.py

# 仅显示 TOP 15，最低匹配分数≥2
python scripts/filter_arxiv_rss.py --top 15 --min-score 2

# 保存到文件
python scripts/filter_arxiv_rss.py --output-file /tmp/candidates.tsv

# 跳过去重（首次运行或测试）
python scripts/filter_arxiv_rss.py --no-dedup
```

输出格式：`score | arxiv_id | date | title | keywords`（Tab分隔，方便导入表格）。

**⚠️ 关键词误报：** 关键字匹配是词袋式的，可能匹配到不在3D视觉领域的论文。例如"Neural Field Thermal Tomography"虽然匹配了"neural field/surface reconstruction/depth estimation/voxel"（score=4），但实际是关于热无损检测的。**必须在精选前人工审核每篇候选人是否确实在3D视觉范围内**。过滤掉明显不相关的论文，再进入评分和排序。

**⚠️ 脚本代理依赖：** `filter_arxiv_rss.py` 的 `fetch_rss()` 函数使用 `urllib.request.ProxyHandler` 代理，但只在工作环境变量 `HTTP_PROXY` 已设置时启用（在模块级通过 `os.environ.get("HTTP_PROXY", "")` 读取）。如果在中国环境下运行，需在调用脚本前设置代理：`HTTP_PROXY=http://127.0.0.1:7890 python scripts/filter_arxiv_rss.py`。如果RSS可直连下载则无需设置。

**手动过滤（备选）：** 以下为关键词列表，也可自行编写解析脚本：

```
bundle adjustment, implicit ba, differentiable ba,
3d gaussian splatting, 3dgs, gaussian splatting,
neural radiance field, nerf, feed-forward, feed forward,
3d reconstruction, slam, visual odometry, structure from motion, sfm,
novel view synthesis, pose estimation, camera pose, depth estimation,
implicit representation, neural field, view synthesis, 3d generation,
pose-free, multi-view stereo
```

### 3. 分类与精选

- 按相关度打分（匹配关键词数量）
- **加权考虑来源质量**：
  - 名校（MIT/Stanford/Berkeley/CMU/牛津/剑桥/ETH/清华/北大/港科大/港中大等）
  - 知名实验室（Google Research/DeepMind/Meta FAIR/NVIDIA Research/Microsoft Research/Apple/OpenAI等）
  - 资深团队（持续的细分方向产出、高引团队）
  - 以上来源的论文在评分中加成优先
- 选出TOP 2-3篇
- 对TOP论文：先查arXiv页面获取作者单位，确认来源后下载PDF并提取文本精读

  **自动化精读：** 使用 `scripts/extract_paper_text.py` 下载PDF并提取关键章节：

  ```bash
  python scripts/extract_paper_text.py --ids 2605.12399 2605.11354 2605.12494
  python scripts/extract_paper_text.py --ids 2605.12399 --find-tables
  ```

  输出：每个ID一个文本文件（`/tmp/arxiv_extracted/{ID}_text.txt`），包含前12页全文 + 关键章节标记。`--find-tables` 额外尝试提取实验数据表格。

- **并行查作者单位（推荐）：** 对于多个候选论文，使用 `delegate_task` 分批次并行查询。**在goal中包含明确URL路径比抽象描述更可靠：**

  ```python
  # 按3个一批分多次调用（受 max_concurrent_children=3 限制）
  delegate_task(tasks=[
      {"context": "查作者单位...",
       "goal": "获取 arXiv 论文 2605.14880 的作者单位。访问 https://arxiv.org/html/2605.14880 解析 <div class='ltx_authors'> 提取作者-机构映射。备选: curl -s https://api.semanticscholar.org/graph/v1/paper/arXiv:2605.14880?fields=title,authors",
       "toolsets": ["web","terminal"]},
      # 每批最多3个
  ])
  ```
  每个子任务：访问 `https://arxiv.org/html/{ID}` 解析 `<div class="ltx_authors">` 提取作者-机构映射。
  - **⚠️ 关键坑：arXiv抽象页（`/abs/ID`）不包含作者单位信息**。必须使用HTML版本（`/arxiv.org/html/ID`）并在`<div class="ltx_authors">`中通过上标标记解析机构映射，或从项目页JavaScript数据中提取。
  - **⚠️ 第二坑：HTML版有时也不包含机构文本**。某些论文的HTML版使用上标标记(¹,²)但`<div class="ltx_authors">`中只包含作者名和上标，**不包含机构名称文本**（如2605.12144）。此时需要从LaTeX源码(`/src/ID`)中提取，或用Semantic Scholar API备选。
  - 备选：用Semantic Scholar API查作者信息，或从论文HTML版脚注中获取。
- **结合知识库分析**：阅读 `/opt/data/obsidian-vault/论文笔记/` 下的已有笔记，将新论文与知识库中已有的相关工作建立关联

### 3.5 去重

读取 `/opt/hermes-notes/arxiv_sent_ids.txt`，过滤掉所有已发送过的arXiv ID。如果所有候选论文都已发送过，则跳过当天日报。

**⚠️ 版本后缀处理：** arXiv ID可能带版本号后缀（如 `2605.10360v1`），去重时需要去除版本后缀。使用 `base_id()` 函数：

```python
def base_id(full_id):
    return full_id.split('v')[0]
```

比较时使用 `base_id(paper_id) not in {base_id(sent) for sent in sent_ids}`，确保 `2605.10360` 能匹配 `2605.10360v1`。

### 4. 生成邮件内容

邮件格式：
- 标题: `[arXiv日报] YYYY-MM-DD 3D视觉精选 | TOP论文名`
- 正文: **每条论文需包含以下四部分**：
  - **📝 核心思想** — 2-3句话：要解决什么问题 + 提出的方案是什么
  - **🔧 方法要点** — 关键技术组件、架构高维描述（2-4条）
  - **💡 创新点** — 与已有工作的关键区别（1-2条）
  - **📊 实验结论** — 数据集、核心指标、关键数值、与对比方法的差距
- TOP论文额外增加完整精读分析，包含详细方法描述、架构图说明、消融实验解读
论文PDF链接直接在正文中以超链接形式提供。

### 5b. 记录已发论文ID

将本次邮件中发送的所有arXiv ID追加写入 `/opt/hermes-notes/arxiv_sent_ids.txt`，每行一个ID，用于下次去重。如果文件不存在则创建。

### 6. 写入知识库

将TOP论文以Obsidian Markdown格式写入知识库：
- 路径: `/opt/data/obsidian-vault/论文笔记/{category}/{论文名}.md`
- 格式: 包含arxiv号、年份、分类、核心贡献、技术路线、与知识库关联
- **⚠️ 去重检查**：写入前先用`search_files()`或`os.listdir()`检查目标目录是否已存在同名笔记（按arxiv号或标题关键词）。已存在的论文只需在每日简报中引用，不需要覆盖。
- 同时写入每日简报: `/opt/data/obsidian-vault/每日简报/YYYY-MM-DD arXiv简报.md`

### 7. SMTP发送

使用smtplib通过126.com邮箱发送。**只发文本+HTML，不附加PDF文件**（126邮箱附件过大易被退回）：

```python
sender = "lulu93@126.com"
password = "JRfp6CdtJq8VNuub"
receiver = "sunlu28@huawei.com"
msg = MIMEMultipart('alternative')  # 不用'mixed'，不加附件
msg.attach(MIMEText(content, 'plain', 'utf-8'))
msg.attach(MIMEText(html, 'html', 'utf-8'))
server = smtplib.SMTP_SSL("smtp.126.com", 465, timeout=60)
```

论文PDF链接直接在正文中以超链接形式提供。
```

### 7b. 语音播客生成（自动步骤）

每天日报邮件发送后，自动为TOP论文生成NotebookLM Deep Dive Audio。

详见 `notebooklm` 技能。本技能提供了 `scripts/notebooklm_podcast.py` 脚本。

**⚠️ Python环境坑：** `notebooklm` Python包安装在 `/opt/hermes-v0130/.venv/` 中，**不是**系统默认Python。直接用 `python3` 运行 `notebooklm_podcast.py` 会报 `ModuleNotFoundError: No module named 'notebooklm'`。必须在命令中显式指定正确解释器路径。

**日报集成步骤：**

1. 完成邮件发送和知识库写入后，找到本次新创建的笔记文件路径
2. 写入 `/tmp/daily_podcast_notes.txt`（每行一个路径）
3. 执行（需要代理，用正确的venv Python）：
   ```bash
   cd /opt/data/profiles/wechat-2/skills/research/arxiv-daily-digest/scripts && \
   HTTP_PROXY=http://127.0.0.1:7890 HTTPS_PROXY=http://127.0.0.1:7890 \
     /opt/hermes-v0130/.venv/bin/python3 notebooklm_podcast.py \
     --batch /tmp/daily_podcast_notes.txt
   ```
   ⚠️ 用 `cd` 进入脚本目录后直接调 `notebooklm_podcast.py`（不要用全路径 `/opt/data/profiles/wechat-2/skills/research/notebooklm/scripts/`），因为脚本内部有相对路径依赖。
4. 不等待完成，cron直接结束

## 辅助脚本

该技能打包了以下脚本，存放于 `scripts/` 目录：

| 脚本 | 用途 | 调用方式 |
|:-----|:-----|:---------|
| `filter_arxiv_rss.py` | 下载RSS → 关键词过滤 → 去重 → 排名输出 | `python scripts/filter_arxiv_rss.py --top 15` |
| `extract_paper_text.py` | 下载PDF → 提取文本 → 标记关键章节 | `python scripts/extract_paper_text.py --ids ID1 ID2` |
| `notebooklm_podcast.py` | 生成NotebookLM Deep Dive Audio（详见 notebooklm 技能） | `python scripts/notebooklm_podcast.py --batch /tmp/notes.txt` |

## 注意事项

- arXiv API有严格限流（~1 req/3s），用RSS feed替代
- **RSS周末为空**：arXiv RSS feed跳过周末（Sat/Sun），周一早上执行时RSS返回0条。必须用1b的回退方案通过API搜索最近论文
- **即使RSS为空，最近1-2天仍有未处理的论文**：提交日(在API中) ≠ 公布日(在RSS中)。上周四/五提交的论文在RSS清空后仍可通过API搜索到，只要它们没有被之前的日报发过
- 126.com附件大小限制约50MB，注意总大小
- pypdf需要预先安装用于PDF文本提取
- Clash代理（mihomo -d /root/.config/clash/）中国环境下需要提前启动
- **PDF邮件附件大小**：126.com限制约50MB。下载全部TOP论文PDF后必须用os.path.getsize()求和，超过48MB则考虑压缩或不附加最大PDF
- **多论文并行查作者单位**：delegate_task默认max_concurrent_children=3，超过3个并行任务会报错。按3个一批分多次调用
- **作者单位提取**：arXiv抽象页（/abs/ID）的静态HTML不包含机构信息。必须使用/html/ID（实验性HTML版），解析<div class="ltx_authors">中的上标标记映射
- **系统时区与邮件日期**：服务器系统时间可能是UTC，邮件标题和正文中的日期建议使用RSS的pubDate（以arXiv公布日为准），不要依赖datetime.now()。RSS日期已经包含时区信息，直接用即可。UTC比CST(UTC+8)晚8小时，用系统时间会产生一天偏差
