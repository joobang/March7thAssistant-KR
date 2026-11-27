"""Replay DU collector OCR without loading the game, OCR model, or input code."""

import argparse
from collections import Counter
from dataclasses import asdict
import json
import math
from pathlib import Path

from .common import DATA, save_json
from .du_recognition import (
    DISCONNECT_PROBE, KOREAN_AREAS, KOREAN_STAGE_AREA, KOREAN_WEEKLY_SCORE_AREA,
    PROBES, area_in_viewport, korean_match, korean_stage, rows_in_area, stage_route, weekly_score_hits,
)
from .du_missions import mission_rows
from .runtime import strings


def read_frames(path):
    frames = {}
    with path.open(encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                frame = json.loads(line)
                image = frame["image"]
                if not isinstance(image, str) or not image or image in frames:
                    raise ValueError(f"invalid or duplicate frame name {image!r}")
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
            frames[image] = frame
    return frames


def observations(frame):
    width, height = frame["resolution"]
    if any(type(size) is not int or size <= 0 for size in (width, height)):
        raise ValueError("invalid resolution")
    rows = []
    for row in frame["ocr_results"]:
        text, confidence, box = row["text"], float(row["confidence"]), row["box"]
        if (not isinstance(text, str) or not 0 <= confidence <= 1 or len(box) != 4
                or any(len(point) != 2 or not all(math.isfinite(v) for v in point) for point in box)):
            raise ValueError("invalid OCR text, confidence, or polygon")
        rows.append((box, (text, confidence)))
    return (width, height), rows


def diagnose(rows, resolution, area, detect):
    inside = rows_in_area(rows, resolution, area)
    row_indexes = {id(row): index for index, row in enumerate(rows)}
    inside_ids = {id(row) for row in inside}
    outside = [row for row in rows if id(row) not in inside_ids]
    status, hits = detect(inside)
    _, outside_hits = detect(outside)
    for hit in hits:
        hit["row"] = row_indexes[id(inside[hit["row"]])]
    for hit in outside_hits:
        hit["row"] = row_indexes[id(outside[hit["row"]])]
    return {
        "status": status,
        "crop": area,
        "rows_in_crop": [row_indexes[id(row)] for row in inside],
        "hits": hits,
        "outside_crop": outside_hits,
    }


def stage_hits(rows, registry):
    status, hits = korean_stage(rows, registry)
    return status, [
        {"row": index, "status": outcome, "route": stage_route(stage.station), **asdict(stage)}
        for outcome, index, stage in hits
    ]


def diagnose_frame(rows, resolution, registry, *, viewport=(0, 0, 1, 1)):
    decisions = {
        "stage": diagnose(rows, resolution, area_in_viewport(KOREAN_STAGE_AREA, viewport), lambda lines: stage_hits(lines, registry)),
        "weekly_score": diagnose(rows, resolution, area_in_viewport(KOREAN_WEEKLY_SCORE_AREA, viewport), weekly_score_hits),
        "disconnect": diagnose(
            rows, resolution, area_in_viewport(DISCONNECT_PROBE.area, viewport),
            lambda lines: korean_match("disconnect", DISCONNECT_PROBE, lines, {}),
        ),
    }
    for group, probe in PROBES.items():
        modes = ("normal", "cycle") if group == "mode" else (None,)
        for mode in modes:
            key = f"{group}.{mode}" if mode else group
            decisions[key] = diagnose(
                rows, resolution, area_in_viewport(KOREAN_AREAS.get(group, probe.area), viewport),
                lambda lines: korean_match(group, probe, lines, registry, only=mode),
            )
    return decisions


def replay(folder, data=DATA, *, viewport=(0, 0, 1, 1)):
    manifest = folder / "events.jsonl"
    events = read_frames(manifest) if manifest.is_file() else {}
    ocr_frames = read_frames(folder / "ocr.jsonl")
    registry = strings(data)
    reports = []
    totals = {}
    for image, frame in ocr_frames.items():
        try:
            resolution, rows = observations(frame)
            if frame.get("language", "ko_KR") != "ko_KR":
                raise ValueError("expected Korean collector OCR")
            if image in events and events[image].get("resolution") != frame["resolution"]:
                raise ValueError("resolution differs from events.jsonl")
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"{image}: {error}") from error
        decisions = diagnose_frame(rows, resolution, registry, viewport=viewport)
        for group, decision in decisions.items():
            totals.setdefault(group, Counter())[decision["status"]] += 1
        reports.append({
            "image": image,
            "resolution": resolution,
            "elapsed_seconds": frame.get("elapsed_seconds"),
            "screen_id": frame.get("screen_id"),
            "ocr_results": frame["ocr_results"],
            "decisions": decisions,
            "missions": mission_rows(rows, resolution, viewport),
        })
    return {
        "input": str(folder),
        "frames_with_ocr": len(reports),
        "missing_ocr": [image for image in events if image not in ocr_frames],
        "without_manifest_entry": [image for image in ocr_frames if image not in events] if events else [],
        "status_counts": totals,
        "frames": reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Collector recordings/ko_KR folder")
    parser.add_argument("--viewport", nargs=4, type=float, metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
                        help="Game viewport in normalized coordinates, e.g. 0 0.2 1 0.6 for the N150 capture.")
    parser.add_argument("--output", type=Path, default=DATA / "reports/du-replay.json")
    args = parser.parse_args()
    try:
        viewport = args.viewport or (0, 0, 1, 1)
        left, top, width, height = viewport
        if not (0 <= left < left + width <= 1 and 0 <= top < top + height <= 1):
            raise ValueError("Viewport must be within the capture and have a positive size")
        report = replay(args.folder, viewport=viewport)
        save_json(args.output, report)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    print(f"Frames with OCR: {report['frames_with_ocr']}, missing OCR: {len(report['missing_ocr'])}")
    print(args.output)


if __name__ == "__main__":
    main()
