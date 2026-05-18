---
name: volcengine-speech
description: 火山引擎语音服务集成 — TTS 语音合成和豆包语音播客大模型。覆盖 V1/V3 API 鉴权方式、端点、请求格式。
triggers:
  - 使用火山引擎/豆包 TTS 语音合成
  - 生成 AI 双人播客（豆包语音播客大模型）
  - 配置火山引擎语音相关 API
  - 用户提到"火山tts"、"豆包语音"、"播客模型"
category: mlops
---

# 火山引擎语音服务

## API 体系概览

火山引擎语音服务有两套 API：**旧版（V1 HMAC 签名）** 和 **新版（V3 X-Api-Key 头）**。

| API 版本 | 端点 | 鉴权方式 | 适用服务 |
|----------|------|----------|----------|
| V1 | `openspeech.bytedance.com/api/v1/tts` | HMAC-SHA256 (AK/SK) | 语音合成 1.0 |
| V3 (新版控制台) | `openspeech.bytedance.com/api/v3/tts/*` | X-Api-Key 头 | 语音合成 2.0, SSE/Chunked |
| 播客 (旧版控制台) | `wss://openspeech.bytedance.com/api/v3/sami/podcasttts` | X-Api-App-Id + X-Api-Access-Key | 豆包语音播客大模型 |

## 鉴权方式

### V1 — HMAC-SHA256 签名（旧版）

```python
from volcenginesdkcore.signv4 import SignerV4
SignerV4.sign(path, method, headers, body, {}, {}, AK, SK, region, service)
```

- 需要 IAM Access Key (AKLT...) + Secret Key
- 签名方法详见 SDK `volcenginesdkcore/signv4.py`
- **常见失败**：`signature with grant: signature mismatch` = AK/SK 无 TTS 权限或服务未开通

### V3 — X-Api-Key（新版控制台）

```bash
curl "https://openspeech.bytedance.com/api/v3/tts/unidirectional" \
  -H "X-Api-Key: <api-key>" \
  -H "X-Api-Resource-Id: seed-tts-2.0" \
  -d '{"audio":{"voice_type":"...","encoding":"mp3"},"request":{"reqid":"x","text":"你好","text_type":"plain","operation":"submit"}}'
```

- 需要新版控制台生成的 API Key（UUID 格式）
- `X-Api-Resource-Id` 选择模型版本：`seed-tts-2.0` / `seed-tts-1.0`
- V2 音色格式：`zh_female_vv_uranus_bigtts`（前缀 `_uranus_bigtts`）
- V1 音色格式：`zh_male_lengkugege_emo_v2_mars_bigtts`（前缀 `_mars_bigtts`）
- **常见失败**：`resource ID is mismatched` = API Key 未绑定该 resource 或音色不匹配

### 播客 — 旧版控制台鉴权

WebSocket 建连时通过 HTTP Headers 鉴权（非 HMAC，非 X-Api-Key）：

| Header | 值 | 说明 |
|--------|-----|------|
| `X-Api-App-Id` | APP ID | 控制台获取 |
| `X-Api-Access-Key` | Access Token | 控制台获取 |
| `X-Api-Resource-Id` | `volc.service_type.10050` | 播客固定值 |
| `X-Api-App-Key` | `aGjiRDfUWi` | **固定值**，不可改 |
| `X-Api-Request-Id` | UUID | 可选 |

## 豆包语音播客大模型

**端点**: `wss://openspeech.bytedance.com/api/v3/sami/podcasttts`

**功能**: 输入话题文本 → AI 自动分析 → 双人播客脚本 → 流式生成双人对话音频

**action 模式**:
- `0` — **话题模式（推荐）**：输入话题/文章/笔记全文，AI 自动写稿+合成语音
  - ✅ **可接受超长输入**：实测 13KB 完整分析笔记全程传入无截断，`input_text_tokens` 达 5,169
  - 输入量直接决定输出篇幅：
    - **简短描述 ~300字** → 2-3 轮 / ~2 分钟，泛泛无细节
    - **完整笔记 ~7-13KB** → 29-85 轮 / 8-20 分钟，技术细节丰富
  - 生成耗时随输入线性增长，完整笔记需 300s+（用后台模式+notify_on_complete）
  - **推荐做法**：利用 paper-analyst skill 写好分析笔记后，去掉 frontmatter 全文传入。详见 `self-built-podcast` skill 的输入长度表。
- `3` — 指定脚本模式（提供 nlp_texts 对话文本列表，JSON 格式。更可控但需自己写稿）

### WebSocket 二进制协议

4 字节固定头 + 4 字节事件号 + session_id + payload：

```
Byte 0: 0x11 (v1, 4-byte header)
Byte 1: 0x14 (msg_type=1, with event number)  ← 关键！
Byte 2: 0x10 (JSON, no compression)
Byte 3: 0x00 (reserved)
[4 bytes] event number (uint32 big-endian)
[4 bytes] session_id length
[N bytes] session_id UTF-8
[4 bytes] payload length
[N bytes] payload JSON
```

**事件码**:
- `150` SessionStarted（下行）
- `360` PodcastRoundStart（下行，带 speaker 信息）
- `361` PodcastRoundResponse（下行，音频二进制数据）
- `362` PodcastRoundEnd（下行，时长信息）
- `152` SessionFinished（下行，会话结束）
- `363` PodcastEnd（下行，总结信息含 audio_url）

### 播客示例 Payload

```json
{
    "input_text": "人工智能大模型在2025年的最新进展",
    "action": 0,
    "audio_config": {
        "format": "mp3",
        "sample_rate": 24000,
        "speech_rate": 0
    },
    "speaker_info": {
        "random_order": true,
        "speakers": [
            "zh_male_dayixiansheng_v2_saturn_bigtts",
            "zh_female_mizaitongxue_v2_saturn_bigtts"
        ]
    }
}
```

**推荐发音人对**：
- 黑猫侦探社系列：`zh_male_dayixiansheng_v2_saturn_bigtts` + `zh_female_mizaitongxue_v2_saturn_bigtts`
- 刘飞和潇磊：`zh_male_liufei_v2_saturn_bigtts` + `zh_male_xiaolei_v2_saturn_bigtts`

### 运行脚本

```bash
cd /opt/hermes && source .venv/bin/activate && \
python3 scripts/podcast_gen.py "话题文本" /tmp/output.mp3
```

详见 `scripts/podcast_gen.py`（独立的播客生成器）。

## 踩坑记录

1. **别用 `$` 锚定正则** — 用户常跟在命令后加话。用 `re.match()` 前缀匹配。
2. **拿到密钥先 API 直调** — 用户给 AK/SK 就先用 curl/python 调 API，别先去浏览器登录控制台（CAPTCHA/密码重置是额外阻力）。
3. **V3 鉴权用头不用体** — `resource_id` 在 Header 里（`X-Api-Resource-Id`），不是 body 里。
4. **播客 msg_type=0x14 不是 0x94** — 文档示例易误读。正确消息类型是 1（0x14），不是 9（0x94）。
5. **IAM 子用户可能没有 TTS 权限** — 需要主账号在控制台授权 `SpeechSaaSFullAccess`。
6. **App ID vs Resource ID** — V1 用 `appid` 在 body，V3 用 `resource_id` 在 header，播客用 `X-Api-App-Id` 头。三者不同。
