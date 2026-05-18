# Cron Job as Sub-Agent (Model Override Pattern)

`delegate_task` 不支持为子 agent 指定不同模型，这是 Hermes 当前的限制。**替代方案：使用 cron job 的 model override 参数**。

## 模式

```python
cronjob(
    action='create',
    name='分析论文XXX',
    skills=['paper-analyst'],              # 加载 skill
    model={'model': 'deepseek-v4-pro',      # 指定不同模型
           'provider': 'deepseek'},
    schedule='once at <future_timestamp>',  # 一次性任务
    prompt='分析论文...',
    enabled_toolsets=['terminal','file','web','search','vision'],
    deliver='origin'                        # 结果发回微信
)
```

## 与 delegate_task 对比

| 方面 | delegate_task | cron job (model override) |
|------|--------------|--------------------------|
| 模型独立 | ❌ 继承父 agent | ✅ 可指定任意模型 |
| 上下文传递 | ✅ 直接 | ⚠️ 需在 prompt 中写明 |
| 运行方式 | 同步（等待结果） | 异步（结果发回渠道） |
| 并发数 | 最多3个 | 无限（排队执行） |
| 适用场景 | 轻量子任务（编码、搜索） | 重量级任务（精读论文、长分析） |

## 已验证

- **2026-05-18**: SLAM-Former 分析使用此模式，pro 模型生成了 280 行完整分析笔记，自动写入 Obsidian + 更新 JSON + 同步 GitHub
- **2026-05-18**: VGGT-Omega 深度研究同样使用此模式（pro 模型 + 多 skill 联调）
- **2026-05-18**: PointForward 已有笔记（无需 pro 模型分析），直接提取笔记全文传给豆包→生成 29 轮/7:57 播客并自动发布

## 与其他模式的配合

分析完成后可接播客生成：完整分析笔记去掉 frontmatter → 作为 topic text 传给 podcast_gen.py（action=0）→ 自动发布到 GitHub RSS。pro 模型写笔记 + 豆包播客一条龙。

## 注意事项

- 一次性 cron job 创建后自动清理，不需要手动删除
- 设置 `schedule` 时确保时间在未来（`in 1 min` 格式最安全）
- **⚠️ schedule 时间坑：** 如果使用 ISO 格式如 `2026-05-19T06:00:00` 且时间已经过去，任务**不会触发也不会报错**（停留在 scheduled 状态）。正确的做法：
  - 用 `"in 1 min"`、`"in 5 min"` 这种相对格式
  - 如果用 ISO 时间，先 `date` 确认当前时间再加 1-2 分钟
  - 如果已创建但时间已过，用 `cronjob(action="run", job_id="...")` 手动触发
- 结果通过 `deliver='origin'` 自动发回微信
- cron job 运行时独立于当前会话，互不干扰
