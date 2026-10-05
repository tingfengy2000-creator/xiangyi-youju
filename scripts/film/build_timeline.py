"""按选中的旁白长度生成全片时间线：镜头起止、旁白放置、字幕与 SRT。

男女两版画面、字幕、配乐完全相同：每个镜头的长度取两版中较长的一句，
两版旁白在同一时刻开口；字幕换行时刻取两版自然换行时刻的平均值。
优先微调镜头时长，不对旁白变速。

用法：python scripts/film/build_timeline.py
输入：artifacts/film/vo/clips.json
输出：artifacts/film/timeline.json、artifacts/film/xiangyi-youju-film.srt
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "film"

TAGS = {
    1: "示意动画", 2: "示意动画 · 原创纹样", 3: "示意动画", 4: "示意动画 · 出处：中国非物质文化遗产网",
    5: "示意动画（虚构界面，不代表任何真实产品）", 6: "示意动画",
    8: "真实本地运行画面", 9: "真实本地运行画面 · 等待已剪短", 10: "真实本地运行画面", 11: "真实本地运行画面",
    12: "真实本地运行画面", 13: "示意动画 · 数据来自真实运行", 14: "真实本地运行画面 · 金额为演示测算",
    15: "真实本地运行画面", 16: "示意动画 · 原创纹样", 17: "真实本地运行画面（印章为示意叠加）",
    18: "真实本地运行画面", 19: "示意动画",
}

# 镜号: (旁白, 最短时长, 开口前留白, 句后留白)
SHOTS = {
    1: (None, 4.6, 0, 0), 2: ("VO-01", 8.0, 1.6, 0.5), 3: ("VO-02", 6.0, 2.2, 0.5), 4: ("VO-03", 7.0, 0.5, 0.45),
    5: ("VO-04", 9.0, 0.7, 0.5), 6: (None, 3.0, 0, 0), 7: ("VO-05", 9.0, 1.3, 0.5), 8: ("VO-06", 8.0, 0.6, 0.45),
    9: (None, 4.6, 0, 0), 10: ("VO-07", 10.0, 0.5, 0.45), 11: ("VO-08", 9.0, 0.5, 0.5), 12: ("VO-09", 7.0, 0.9, 0.5),
    13: ("VO-10", 10.0, 0.5, 0.5), 14: ("VO-11", 10.0, 0.5, 0.5), 15: ("VO-12", 9.5, 1.6, 0.5),
    16: ("VO-13", 4.6, 1.3, 0.6), 17: ("VO-14", 5.5, 0.9, 0.6), 18: ("VO-15", 9.5, 0.6, 0.5),
    19: ("VO-16", 8.0, 0.5, 0.5), 20: ("VO-17", 12.0, 1.0, 0.7), 21: (None, 4.2, 0, 0),
}

# 字幕：每行 (显示文字, 对应原文)；单行不超过 18 字，句末不加标点
SUBS = {
    "VO-01": [("剪纸的时候 刀留下线条 叫阳刻", "剪纸的时候刀留下线条叫阳刻")],
    "VO-02": [("刀刻去线条 叫阴刻", "刀刻去线条叫阴刻")],
    "VO-03": [("丰宁的剪纸 以阳刻为主", "丰宁的剪纸以阳刻为主"), ("蔚县的剪纸 以阴刻为主", "蔚县的剪纸以阴刻为主"),
              ("一刀之差 是两个地方的手艺", "一刀之差是两个地方的手艺")],
    "VO-04": [("如今 人们常常先从网上", "如今人们常常先从网上"), ("从 AI 那里认识一个地方", "从ai那里认识一个地方"),
              ("如果这一刀讲反了", "如果这一刀讲反了"), ("错的就不只是一个字", "错的就不只是一个字")],
    "VO-05": [("乡艺有据", "乡艺有据"), ("每一句讲解有出处 每一分钱有去处", "每一句讲解有出处每一分钱有去处")],
    "VO-06": [("这是一段准备给游客的讲解词", "这是一段准备给游客的讲解词"), ("我们先把每一句 送回出处去对一对", "我们先把每一句送回出处去对一对")],
    "VO-07": [("资料说得清楚", "资料说得清楚"), ("阳刻为主 讲的是丰宁", "阳刻为主讲的是丰宁"), ("蔚县 以阴刻为主", "蔚县以阴刻为主"),
              ("原文 出处 位置 都摆在这里", "原文出处位置都摆在这里")],
    "VO-08": [("至于“每天开放 无需预约”这样的承诺", "至于每天开放无需预约这样的承诺"), ("资料证明不了", "资料证明不了"),
              ("它不替人答应 留给接待方确认", "它不替人答应留给接待方确认")],
    "VO-09": [("如果客人说", "如果客人说"), ("不要茶歇 多留点手作时间", "不要茶歇多留点手作时间")],
    "VO-10": [("一句话 整场活动重新排", "一句话整场活动重新排"), ("茶歇撤下", "茶歇撤下"), ("手作从 50 分钟 变成 80 分钟", "手作从五十分钟变成八十分钟")],
    "VO-11": [("账也一起重算", "账也一起重算"), ("这 796 元里 524 元", "这七百九十六元里五百二十四元"), ("是付给本地讲解和手作老师的报酬", "是付给本地讲解和手作老师的报酬")],
    "VO-12": [("做不到的事", "做不到的事"), ("比如临时加一场英语讲解", "比如临时加一场英语讲解"), ("它会停下来 先问人", "它会停下来先问人")],
    "VO-13": [("作品 是手艺人的", "作品是手艺人的")],
    "VO-14": [("他说不用了 旧手册立刻作废", "他说不用了旧手册立刻作废")],
    "VO-15": [("重新核验 经人确认 才有新的一版", "重新核验经人确认才有新的一版"), ("拍板的 始终是人", "拍板的始终是人")],
    "VO-16": [("这一切 装在一台普通电脑里", "这一切装在一台普通电脑里"), ("离线运行 不花一分钱模型调用费", "离线运行不花一分钱模型调用费")],
    "VO-17": [("AI 正在成为人们", "ai正在成为人们"), ("认识一个地方的第一扇窗", "认识一个地方的第一扇窗"),
              ("我们让它只讲有出处的话", "我们让它只讲有出处的话"), ("把拍板权和收益 留在乡里", "把拍板权和收益留在乡里")],
}


def units(text):
    return re.findall(r"ai|[一-鿿]", text)


def line_times(clip, parts, offset):
    """一位录音者每一行字幕的 (开口, 收口)，换算到全片时间。"""
    chars = clip["chars"]
    total = sum(len(units(p)) for _, p in parts)
    n = len(chars)
    out, k = [], 0
    for _, part in parts:
        a, b = k, k + len(units(part))
        ia = min(n - 1, round(a * n / total))
        ib = min(n - 1, max(ia, round(b * n / total) - 1))
        start = chars[ia][1]
        end = chars[ib + 1][1] - 0.05 if ib + 1 < n else clip["speech_end"]
        end = min(end, chars[ib][1] + 0.45) if ib + 1 < n else end
        out.append((offset + start - 0.12, offset + end + 0.05))
        k = b
    return out


def fmt(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    clips = json.loads((OUT / "vo" / "clips.json").read_text(encoding="utf-8"))
    voices = list(clips)
    t = 0.0
    shots, placements, subtitles, cues = [], {v: [] for v in voices}, [], {}
    for n in range(1, 22):
        vo, min_dur, lead, tail = SHOTS[n]
        dur = min_dur
        if vo:
            speech = max(clips[v][vo]["speech_end"] - clips[v][vo]["speech_start"] for v in voices)
            dur = max(min_dur, lead + speech + tail)
        dur = round(dur * 24) / 24
        shots.append({"n": n, "start": round(t, 4), "end": round(t + dur, 4), "tag": TAGS.get(n, ""), "vo": vo})
        if vo:
            per_voice = {}
            for v in voices:
                c = clips[v][vo]
                offset = t + lead - c["speech_start"]
                placements[v].append({"vo": vo, "shot": n, "start": round(offset, 4), "file": c["file"],
                                      "duration": c["duration"], "take_no": c["take_no"],
                                      "source_start": c["source_start"], "source_end": c["source_end"]})
                per_voice[v] = line_times(c, SUBS[vo], offset)
            lines = SUBS[vo]
            for i, (text, _) in enumerate(lines):
                start = min(per_voice[v][i][0] for v in voices)
                if i + 1 < len(lines):
                    end = sum((per_voice[v][i][1] + per_voice[v][i + 1][0]) / 2 for v in voices) / len(voices)
                else:
                    end = max(per_voice[v][i][1] for v in voices) + 0.3
                if subtitles and subtitles[-1]["vo"] == vo:
                    subtitles[-1]["end"] = round(min(subtitles[-1]["end"], start), 3)
                    start = subtitles[-1]["end"]
                subtitles.append({"vo": vo, "line": i + 1, "start": round(start, 3), "end": round(end, 3), "text": text,
                                  "burn": vo not in ("VO-05", "VO-17")})
                cues[f"{vo}#{i + 1}"] = round(min(per_voice[v][i][0] for v in voices) + 0.12, 3)
            # 这句在两版中较晚说完的时刻（例如印章要等“作废”说完再落）
            cues[f"{vo}#end"] = round(max(p["start"] + clips[v][vo]["speech_end"] for v in voices
                                         for p in placements[v] if p["vo"] == vo), 3)
        t += dur
    # 片头字幕（镜 1，无旁白）也写入 SRT
    srt_items = [{"start": 1.6, "end": shots[0]["end"] + 0.1, "text": "同一张红纸。"}] + subtitles
    duration = round(t, 4)
    # 等待已剪短：镜 9 全程；镜 15 只在压缩段前后（与 stage-scenes.js 中的分段一致）
    notes = [{"start": shots[8]["start"] + 0.3, "end": shots[8]["end"] - 0.2, "text": "等待已剪短"},
             {"start": shots[14]["start"] + 2.3, "end": shots[14]["start"] + 4.2, "text": "等待已剪短"}]
    timeline = {"fps": 24, "duration": duration, "shots": shots, "subtitles": subtitles, "cues": cues,
                "notes": notes, "vo": placements,
                "beats": [shots[1]["start"], shots[6]["start"], shots[12]["start"], shots[16]["start"], shots[19]["start"]]}
    (OUT / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    srt = []
    for i, s in enumerate(srt_items, 1):
        srt.append(f"{i}\n{fmt(s['start'])} --> {fmt(s['end'])}\n{s['text']}\n")
    (OUT / "xiangyi-youju-film.srt").write_text("\n".join(srt), encoding="utf-8")
    for s in shots:
        print(f"镜 {s['n']:2d} {s['start']:7.2f}-{s['end']:7.2f} ({s['end'] - s['start']:5.2f}) {s['vo'] or ''}")
    print("总长", duration, "秒")


if __name__ == "__main__":
    main()
