#!/usr/bin/env python3
"""豆包语音播客大模型 — 独立播客生成器

Usage:
    python3 podcast_gen.py "话题描述" /tmp/output.mp3
    python3 podcast_gen.py --action 3 --script /tmp/script.json /tmp/output.mp3

Environment (optional):
    VOLC_APP_ID     — defaults to 3672726947
    VOLC_ACCESS_KEY — defaults to mIYA56zm0v_U-iqNxuqz6L93N9pM8EKi
"""

import asyncio, websockets, json, struct, uuid, os, sys, argparse

APP_ID = os.environ.get("VOLC_APP_ID", "3672726947")
ACCESS_KEY = os.environ.get("VOLC_ACCESS_KEY", "mIYA56zm0v_U-iqNxuqz6L93N9pM8EKi")
DEFAULT_SPEAKERS = [
    "zh_male_dayixiansheng_v2_saturn_bigtts",
    "zh_female_mizaitongxue_v2_saturn_bigtts",
]


def build_frame(msg_type_byte, event_num, session_id, payload):
    sb = session_id.encode()
    pb = json.dumps(payload, ensure_ascii=False).encode()
    return (
        struct.pack(">BBBB", 0x11, msg_type_byte, 0x10, 0x00)
        + struct.pack(">I", event_num)
        + struct.pack(">I", len(sb))
        + sb
        + struct.pack(">I", len(pb))
        + pb
    )


def parse_frame(data):
    if len(data) < 16:
        return None
    event = struct.unpack(">I", data[4:8])[0]
    sid_len = struct.unpack(">I", data[8:12])[0]
    offset = 12 + sid_len
    if offset + 4 > len(data):
        return event, data[12 : 12 + sid_len].decode(errors="replace"), b""
    plen = struct.unpack(">I", data[offset : offset + 4])[0]
    offset += 4
    return event, data[12 : 12 + sid_len].decode(errors="replace"), data[offset : offset + plen]


async def generate_podcast(input_text=None, nlp_texts=None, output_file="/tmp/podcast.mp3",
                           speakers=None, action=0, format="mp3", sample_rate=24000):
    speakers = speakers or DEFAULT_SPEAKERS
    headers = {
        "X-Api-App-Id": APP_ID,
        "X-Api-Access-Key": ACCESS_KEY,
        "X-Api-Resource-Id": "volc.service_type.10050",
        "X-Api-App-Key": "aGjiRDfUWi",
    }

    sid = f"hermes_{uuid.uuid4().hex[:12]}"
    payload = {
        "action": action,
        "audio_config": {"format": format, "sample_rate": sample_rate, "speech_rate": 0},
        "speaker_info": {"random_order": True, "speakers": speakers},
    }
    if action == 3 and nlp_texts:
        payload["nlp_texts"] = nlp_texts
    elif input_text:
        payload["input_text"] = input_text

    async with websockets.connect(
        "wss://openspeech.bytedance.com/api/v3/sami/podcasttts",
        additional_headers=headers,
        ping_interval=None,
        close_timeout=10,
    ) as ws:
        await ws.send(build_frame(0x14, 100, sid, payload))
        print(f"📡 播客请求已发送: {input_text[:60] if input_text else 'script'}...")

        audio_chunks = []
        round_num = 0
        while True:
            data = await asyncio.wait_for(ws.recv(), timeout=300)
            result = parse_frame(data)
            if not result:
                continue
            event, _, p = result

            if event == 150:
                print("🎙️ 播客生成中...")
            elif event == 360:
                round_num += 1
                info = json.loads(p.decode()) if p else {}
                spk = info.get("speaker", "?")[-30:]
                print(f"  #{round_num}: {spk}")
            elif event == 361:
                audio_chunks.append(p)
            elif event == 362:
                info = json.loads(p.decode()) if p else {}
                dur = info.get("audio_duration", 0)
                print(f"  ✅ #{round_num} ({dur:.1f}s)")
            elif event in (152, 363):
                print("✅ 播客完成!")
                break
            elif event == 154:
                info = json.loads(p.decode()) if p else {}
                print(f"  📊 usage: {info.get('usage', {})}")
            elif event == 45000000:
                err = p.decode(errors="replace")
                print(f"❌ {err[:200]}")
                break

        if audio_chunks:
            with open(output_file, "wb") as f:
                for c in audio_chunks:
                    f.write(c)
            size = sum(len(c) for c in audio_chunks)
            print(f"📁 {output_file} ({size:,} bytes, {round_num} 轮)")
            return output_file
        return None


def main():
    parser = argparse.ArgumentParser(description="豆包语音播客大模型生成器")
    parser.add_argument("input", nargs="?", help="话题文本")
    parser.add_argument("output", nargs="?", default="/tmp/podcast.mp3", help="输出文件")
    parser.add_argument("--action", type=int, default=0, help="0=话题, 3=脚本, 4=prompt")
    parser.add_argument("--script", help="action=3 时使用的 JSON 脚本文件")
    parser.add_argument("--speakers", nargs=2, default=DEFAULT_SPEAKERS, help="发音人对")
    parser.add_argument("--format", default="mp3")
    parser.add_argument("--sample-rate", type=int, default=24000)
    args = parser.parse_args()

    nlp_texts = None
    input_text = args.input
    if args.action == 3 and args.script:
        with open(args.script, "r", encoding="utf-8") as f:
            nlp_texts = json.load(f)
        input_text = None
    elif not input_text:
        input_text = "人工智能的未来发展趋势"

    asyncio.run(
        generate_podcast(
            input_text=input_text,
            nlp_texts=nlp_texts,
            output_file=args.output,
            speakers=args.speakers,
            action=args.action,
            format=args.format,
            sample_rate=args.sample_rate,
        )
    )


if __name__ == "__main__":
    main()
