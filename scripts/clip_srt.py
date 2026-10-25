#!/usr/bin/env python3
"""Build source/edit SRTs and a traceable edit sheet from chosen cue ranges."""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


TIME = re.compile(r"(\d{2,}):(\d{2}):(\d{2})[,.](\d{3})")
OUTPUTS = ("01_source_timecodes.srt", "02_edit_timecodes.srt",
           "03_edit_sheet.md", "04_edit_map.json")


def milliseconds(value):
    match = TIME.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, millis = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid SRT timestamp: {value!r}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def timestamp(value):
    seconds, millis = divmod(value, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def parse_srt(text):
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    cues, seen = [], set()
    for part in re.split(r"\n[ \t]*\n+", normalized.strip()):
        lines = part.split("\n")
        if len(lines) < 3 or not lines[0].strip().isdigit():
            raise ValueError(f"Invalid SRT block near {part[:80]!r}")
        cue_id = int(lines[0].strip())
        times = re.fullmatch(r"\s*(\S+)\s+-->\s+(\S+)\s*", lines[1])
        if cue_id < 1 or cue_id in seen or not times:
            raise ValueError(f"Invalid/duplicate cue ID or time line: {cue_id}")
        start, end = map(milliseconds, times.groups())
        if end <= start or (cues and start < cues[-1]["start_ms"]):
            raise ValueError(f"Cue {cue_id}: invalid duration or source timeline reset")
        text_body = "\n".join(lines[2:])
        if not text_body.strip():
            raise ValueError(f"Cue {cue_id}: empty subtitle")
        seen.add(cue_id)
        cues.append(dict(id=cue_id, start_ms=start, end_ms=end, text=text_body))
    if not cues:
        raise ValueError("No subtitles found")
    return cues


def srt(cues):
    return "\n\n".join(
        f"{index}\n{timestamp(cue['start_ms'])} --> {timestamp(cue['end_ms'])}\n{cue['text']}"
        for index, cue in enumerate(cues, 1)
    ) + "\n\n"


def string_field(obj, key, default=""):
    value = obj.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def build(cues, plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("segments"), list) or not plan["segments"]:
        raise ValueError("Plan requires a nonempty segments array")
    title = string_field(plan, "title", "采访同期声剪辑单")
    theme = string_field(plan, "theme")
    notes = plan.get("notes", [])
    if not isinstance(notes, list) or any(not isinstance(item, str) for item in notes):
        raise ValueError("notes must be an array of strings")
    target = plan.get("target_seconds")
    if target is not None and (type(target) not in (int, float) or not math.isfinite(target) or target <= 0):
        raise ValueError("target_seconds must be a finite positive number")
    lookup = {cue["id"]: index for index, cue in enumerate(cues)}
    source, edited, blocks, mapping, used = [], [], [], [], set()
    cursor = 0
    for order, selection in enumerate(plan["segments"], 1):
        if not isinstance(selection, dict):
            raise ValueError(f"Segment {order}: expected an object")
        first, last = selection.get("first"), selection.get("last")
        if type(first) is not int or type(last) is not int or first not in lookup or last not in lookup:
            raise ValueError(f"Segment {order}: first/last must be existing integer cue IDs")
        if lookup[first] > lookup[last]:
            raise ValueError(f"Segment {order}: reversed source range")
        selected = cues[lookup[first]:lookup[last] + 1]
        label = string_field(selection, "label", f"Segment {order}")
        purpose = string_field(selection, "purpose")
        join_note = string_field(selection, "join_note")
        start, end = selected[0]["start_ms"], selected[-1]["end_ms"]
        for cue in selected:
            if cue["id"] in used:
                raise ValueError(f"Repeated source cue {cue['id']}")
            used.add(cue["id"])
            new_start = cursor + cue["start_ms"] - start
            new_end = cursor + cue["end_ms"] - start
            source.append(cue)
            edited.append(dict(start_ms=new_start, end_ms=new_end, text=cue["text"]))
            mapping.append(dict(segment=order, source_id=cue["id"],
                                source_start_ms=cue["start_ms"], source_end_ms=cue["end_ms"],
                                edit_start_ms=new_start, edit_end_ms=new_end, text=cue["text"]))
        blocks.append(dict(order=order, label=label, purpose=purpose, join_note=join_note,
                           source_first_id=first, source_last_id=last,
                           source_in_ms=start, source_out_ms=end, duration_ms=end-start,
                           edit_in_ms=cursor, edit_out_ms=cursor+end-start,
                           source_ids=[cue["id"] for cue in selected],
                           text="\n".join(cue["text"] for cue in selected)))
        cursor += end - start
    source.sort(key=lambda cue: cue["start_ms"])
    for name, timeline in (("source", source), ("edit", edited)):
        if any(right["start_ms"] < left["end_ms"] for left, right in zip(timeline, timeline[1:])):
            raise ValueError(f"Overlapping {name} intervals; inspect source and selections")
    report = dict(title=title, theme=theme, target_seconds=target,
                  actual_duration_ms=cursor, major_joins=len(blocks)-1,
                  notes=notes, segments=blocks, cues=mapping,
                  verification_scope="Subtitle text/time mapping only; audio and video not verified")
    return source, edited, report


def markdown(report):
    rows = [f"# {report['title']}", "", report["theme"], "",
            f"同期声参考时长：{report['actual_duration_ms']/1000:.3f}秒；"
            f"完整语段：{len(report['segments'])}；主要声音拼接点：{report['major_joins']}。", ""]
    if report["target_seconds"] is not None:
        difference = report["actual_duration_ms"]/1000 - report["target_seconds"]
        rows.extend([f"目标：{report['target_seconds']}秒；差值：{difference:+.3f}秒。", ""])
    rows.extend(["原片定位SRT按源时间排列；成片参考SRT按下表顺序从零拼接。", "",
                 "| 顺序／内容 | 原片入点 → 出点 | 段长 | 成片位置 |",
                 "| --- | --- | --- | --- |"])
    for block in report["segments"]:
        label = block["label"].replace("|", "／").replace("\n", " ")
        rows.append(f"| {block['order']} {label} | "
                    f"{timestamp(block['source_in_ms'])} → {timestamp(block['source_out_ms'])} | "
                    f"{block['duration_ms']/1000:.3f}秒 | "
                    f"{timestamp(block['edit_in_ms'])} → {timestamp(block['edit_out_ms'])} |")
    for block in report["segments"]:
        rows.extend(["", f"## {block['order']} {block['label']}", ""])
        if block["purpose"]:
            rows.extend([f"选用理由：{block['purpose']}", ""])
        rows.extend(["入选原话（保留原转写）：", ""])
        rows.extend("> " + line for line in block["text"].split("\n"))
        if block["join_note"]:
            rows.extend(["", f"剪口／画面建议：{block['join_note']}"])
    rows.extend(["", "## 待核实与使用范围", ""])
    rows.extend(f"- {note}" for note in report["notes"])
    rows.extend(["- 时间码对应输入SRT的源时间轴，不代表独立相机文件的时间码。",
                 "- 成片时间按整段原速、无额外间隔拼接；保留段内停顿。",
                 "- 字幕条目数量不等于视频切点数。原始识别错误尚未因本次选段而修正。",
                 "- 已核验字幕文字和时间换算；未试听音频或查看画面，切点需回听并取整到工程帧。", ""])
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        cues = parse_srt(args.source.read_text(encoding=args.encoding))
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
        source, edited, report = build(cues, plan)
        report["source_path"] = str(args.source.resolve())
        report["source_sha256"] = hashlib.sha256(args.source.read_bytes()).hexdigest()
        report["source_encoding"] = args.encoding
        paths = [args.out / name for name in OUTPUTS]
        inputs = {args.source.resolve(), args.plan.resolve()}
        if args.out.exists() and not args.out.is_dir():
            raise ValueError("Output path is not a directory")
        if any(path.resolve() in inputs for path in paths):
            raise ValueError("Output would overwrite a source or plan file")
        if not args.overwrite and any(path.exists() for path in paths):
            raise ValueError("Output already exists; choose another directory or pass --overwrite")
        contents = (srt(source), srt(edited), markdown(report),
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        # Check serializer behavior before any output mutation.
        for text, expected in zip(contents[:2], (source, edited)):
            round_trip = parse_srt(text)
            if [(c["start_ms"], c["end_ms"], c["text"]) for c in round_trip] != [
                (c["start_ms"], c["end_ms"], c["text"]) for c in expected
            ]:
                raise ValueError("SRT serialization changed text or timestamps")
        args.out.mkdir(parents=True, exist_ok=True)
        for path, content in zip(paths, contents):
            path.write_text(content, encoding="utf-8-sig")
        for path, expected in zip(paths[:2], (source, edited)):
            actual = parse_srt(path.read_text(encoding="utf-8-sig"))
            if [(c["start_ms"], c["end_ms"], c["text"]) for c in actual] != [
                (c["start_ms"], c["end_ms"], c["text"]) for c in expected
            ]:
                raise ValueError(f"Saved SRT verification failed: {path}")
        print(json.dumps(dict(status="verified", duration_seconds=report["actual_duration_ms"]/1000,
                              blocks=len(report["segments"]), joins=report["major_joins"],
                              selected_cues=len(edited), output=str(args.out.resolve())), ensure_ascii=True))
        return 0
    except (OSError, UnicodeError, ValueError, LookupError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
