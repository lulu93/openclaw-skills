# 2026-05-18 实战记录

## Papers Analyzed

| arXiv | Title | Notes | 
|-------|-------|-------|
| 2509.16909 | SLAM-Former | 280 lines, written by pro model via cron job |
| 2512.08924 | D4RT | 220 lines, written by pro model via cron job |
| 2605.11594 | PointForward | Already existed, used directly |
| — | 查询范式崛起 (cross-paper) | Written by main agent, 100 lines |

## Key Learnings

### Pro Model Sub-Agent Pattern

The `cronjob(model=...)` approach for running pro-model analysis was validated:

```python
cronjob(action="create",
  name="精读 D4RT (pro模型)",
  skills=["paper-analyst"],
  model={"provider": "deepseek", "model": "deepseek-v4-pro"},
  prompt="分析论文 ...",
  schedule="2026-05-18T20:00:00",  # ⚠️ must be future time
  deliver="origin",
  enabled_toolsets=["terminal", "file", "web", "search", "vision"]
)
```

**Results delivered back to WeChat automatically** via `deliver="origin"`.

### Cross-Paper Comparison

After pro model analyzed D4RT, user asked "分析一下跟PointForward什么关系". This led to:
1. Manual comparison using abstract + existing knowledge
2. User then asked "沿着这个思路，后面还能怎么发展" — triggering a future-outlook analysis
3. Both the comparison and outlook were written as a cross-paper analysis note (分析笔记/)
4. Used as podcast input → generated at 35 rounds / 9:04

Pattern: single paper → pro analysis → comparison with existing knowledge base → cross-paper analysis → podcast

### Schedule Time Pitfall

Setting an ISO time (e.g., `2026-05-18T11:35:00`) that's already passed means the job never fires.
**Always check current time first** with `date`, then set schedule 1-2 minutes ahead.
Or use `cronjob(action="run", job_id="...")` to trigger immediately.
