# 一次性 cron job 模板：论文分析（子agent + pro模型）

> 需要 `delegate_task` 之外设独立模型的场景 → 用此模式替代。

## 坑点速查

**⚠️ 时间坑（踩过）：** cron job 的 `schedule` 用 ISO 时间必须晚于当前时间。
- 错误写法：`schedule="once at 2026-05-18 11:35"` （当时是 12:29，已过去）
- 正确做法：先 `terminal("date '+%H:%M'")` 确认当前时间，再加 3-5 分钟
- 更稳妥：创建后用 `cronjob(action="run", job_id="...")` 立即触发

## 完整模板

```python
# 1. 先看时间
date_result = terminal("date '+%Y-%m-%dT%H:%M'")
# 2. 创建一次性 cron job
cronjob(
    action="create",
    name=f"精读 arXiv:2509.16909 (pro模型)",
    prompt=f"精读论文「XXX」(arXiv:XXXX.XXXXX)。\n\n"
           f"任务：\n"
           f"1. 下载PDF，提取文本精读\n"
           f"2. 写完整的分析笔记到 /opt/data/obsidian-vault/论文笔记/{category}/XXX.md\n"
           f"3. 更新 /opt/hermes/arxiv_papers_2024_2026.json\n"
           f"4. 运行同步: bash /opt/hermes/scripts/podcast-tools/sync_knowledge.sh\n\n"
           f"完成后将分析摘要返回给我。",
    skills=["paper-analyst"],
    model={"provider": "deepseek", "model": "deepseek-v4-pro"},
    schedule="2026-05-19T10:00:00",  # 确认晚于当前时间
    deliver="origin",
    enabled_toolsets=["terminal", "file", "web", "search", "vision"],
)
```

## 完整 pipeline（分析 → 播客 → 发布）

```
用户: "精读 arXiv:XXXX.XXXXX"
   ↓
创建 cron job (pro模型 + paper-analyst skill) → 自动分析
   ↓ 分析完成
分析笔记写入 obsidian + JSON 更新 + GitHub同步
   ↓ 结果发回微信
用户: "生成播客"
   ↓
完整笔记去掉frontmatter → 豆包话题模式 → 播客
   ↓
publish_podcast.py → RSS更新 → GitHub同步
   ↓
用户在小宇宙收听
```

## 验证记录

| 论文 | 方式 | 结果 |
|------|------|------|
| SLAM-Former (2509.16909) | cron job 11:35→手动run | 280行笔记 ✅ |
| D4RT (2512.08924) | cron job 20:00 | 220行笔记 ✅ |
| PointForward (2605.11594) | 已有笔记直接播客 | 29轮7:57 ✅ |
