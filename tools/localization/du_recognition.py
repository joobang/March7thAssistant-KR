"""Divergent Universe OCR rules shared by the task and collector replay."""

from dataclasses import dataclass
import re

from .runtime import game_language, normalize, strings


def crop(x, y, width, height):
    return x / 1920, y / 1080, width / 1920, height / 1080


@dataclass(frozen=True)
class Label:
    id: str
    zh: str
    candidate: str
    variants: tuple[str, ...] = ()


@dataclass(frozen=True)
class Probe:
    area: tuple
    labels: tuple[Label, ...]
    include_zh: bool = False


STATIONS = (
    Label("battle", "战斗", "전투"), Label("elite", "精英", "정예"),
    Label("event", "事件", "사건"), Label("abnormal", "异常", "이상"),
    Label("reward", "奖励", "보상"), Label("wealth", "财富", "재물"),
    Label("adventure", "冒险", "모험"), Label("shop", "商店", "상점"),
    Label("forge", "铸造", "주조"), Label("blank", "空白", "공백"),
    Label("encounter", "奇遇", "기연"), Label("boss", "首领", "우두머리"),
    Label("rest", "休整", "휴식"), Label("conversion", "转化", "전환"),
)
STATION_BY_ID = {label.id: label.zh for label in STATIONS}
STAGE_ROUTES = {
    "battle": ("boss", "battle", "elite", "conversion"),
    "walk": ("blank", "rest", "shop", "wealth"),
    "event": ("event", "abnormal", "reward", "forge"),
}


def stage_route(station):
    return next((route for route, stations in STAGE_ROUTES.items() if station in stations), "unsupported")


def legacy_station_id(text):
    # Keep the legacy branch order and substring fallback for Chinese OCR.
    ids = (*STAGE_ROUTES["battle"], *STAGE_ROUTES["walk"], *STAGE_ROUTES["event"], "adventure")
    return next((station for station in ids if STATION_BY_ID[station] in text), None)


PLANES = tuple(Label(f"plane_{i}", f"第{zh}位面", f"제{i}차원")
               for i, zh in enumerate("一二三", 1))
STAGE_AREA = crop(57, 15, 260, 27)
WEEKLY_SCORE_AREA = crop(182, 977, 209, 43)
WEEKLY_SCORE_LIMITS = ("12000", "14000", "18000")
STATION_AREAS = (crop(570, 433, 252, 403), crop(835, 432, 251, 405), crop(1097, 432, 252, 405))

PROBES = {
    "guide_entry": Probe(crop(238, 257, 449, 525), (Label("open", "差分宇宙", "차분화 우주"),)),
    "guide_participate": Probe(crop(684, 278, 981, 656), (
        Label("participate", "前往参与", "참여하러 가기"),
    )),
    "mode": Probe(crop(39, 291, 672, 431), (
        Label("normal", "常规演算", "일반 연산"), Label("cycle", "周期演算", "주기 연산"),
    )),
    "title": Probe(crop(96, 63, 142, 34), (
        Label("mask", "欢愉假面", "환락의 가면"),
        Label("equation", "选择方程", "방정식을 선택하세요"),
        Label("blessing", "选择祝福", "일반 적 처치! 축복 1회 선택 가능",
              ("보스 적 처치! 축복을 1회 선택할 수 있습니다",)),
        Label("curio", "选择奇物", "기물 선택"),
        Label("discard_curio", "丢弃奇物", "기물 버리기"),
        Label("destroy_curio", "奇物损毁", "기물 훼손"),
        Label("wish", "愿力满盈", "당신의 기적을 선택하세요"),
        Label("next_station", "选择下一站", "다음 행선지 선택"),
        Label("event", "事件", "사건"),
        Label("station_card", "选择站点卡", "스테이션 카드 선택"),
        Label("save", "存档管理", "저장 기록 관리"),
        Label("chaos_box", "混沌药箱", "혼돈의 약상자"),
        Label("talent", "人才管理阶段", "인재 관리 단계"),
    ), True),
    "mask_action": Probe((0, 0, 1, 1), (
        Label("choose_mask", "选择一张面具", "가면을 1개 선택하세요"), Label("confirm", "确定", "확인"),
    )),
    "settlement_action": Probe(crop(573, 947, 792, 85), (
        Label("abort_battle", "终止战斗并结算", "전투 중단 후 정산"),
        Label("return_main", "返回主界面", "메인 화면으로 돌아가기"),
        Label("confirm_settlement", "确认结算", "정산 확인"),
    ), True),
    "weekly_reward_mail": Probe(crop(33, 911, 397, 103), (
        Label("mailed", "奖励已由邮件发放", "보상이 우편으로 발송되었습니다"),
    ), True),
    "settlement_result": Probe((0, 0, 1, 1), (
        Label("success", "探索成功", "탐사 성공"), Label("interrupted", "探索中断", "탐사 중단"),
    ), True),
    "end_previous": Probe(crop(39, 215, 748, 597), (Label("end_run", "结束并结算", "종료 및 결산"),)),
    "end_run": Probe(crop(1238, 859, 562, 165), (Label("end_run", "结束并结算", "종료 및 결산"),)),
    "continue_run": Probe(crop(39, 215, 748, 597), (Label("continue", "继续进度", "진도 계속하기"),)),
    "equation_confirm": Probe(crop(1657, 948, 99, 49), (Label("confirm", "确认", "확인"),), True),
    "blessing_confirm": Probe(crop(1644, 934, 88, 48), (Label("confirm", "确认", "확인"),), True),
    "curio_confirm": Probe(crop(1660, 948, 93, 49), (Label("confirm", "确认", "확인"),), True),
    "discard_confirm": Probe(crop(1695, 948, 69, 50), (Label("discard", "丢弃", "버리기"),), True),
    "station_confirm": Probe(crop(561, 937, 794, 60), (Label("confirm", "确定", "확인"),), True),
    **{f"station_{i}": Probe(area, STATIONS, True) for i, area in enumerate(STATION_AREAS, 1)},
}

def n150_area(x, y, width, height):
    """Coordinates relative to the captured 1024×768 game viewport."""
    return x / 1024, y / 768, width / 1024, height / 768


KOREAN_STAGE_AREA = n150_area(10, 4, 275, 34)
KOREAN_WEEKLY_SCORE_AREA = n150_area(70, 673, 190, 60)
KOREAN_AREAS = {
    "mode": n150_area(220, 170, 200, 238),
    "title": n150_area(40, 42, 650, 83),
}
DISCONNECT_PROBE = Probe(n150_area(340, 343, 360, 82), (
    Label("disconnected", "",
          "서버와 연결이 끊겼습니다. 다시 로그인해 주세요",
          ("서버와 연결이 끊겼습니다 다시 로그인해 주세요",)),
))


MIN_CONFIDENCE = 0.80
GENERIC_KOREAN = {"확인", "선택", "취소", "닫기", "나가기", "계속", "버리기", "돌아가기"}
PROGRESS = r"[（(]\s*(\d+)\s*/\s*(13|17|20)\s*[)）]"
ZH_STAGE = re.compile(PROGRESS + r"\s*第\s*([一二三])\s*位面(?:\s*[-—－]\s*(.+))?")
KO_STAGE = re.compile(PROGRESS + r"\s*([^-—－]+)\s*[-—－]\s*(.+)")


def compact(text):
    return normalize(text).replace(" ", "")


def korean_label(group, label, registry):
    row = registry.get(f"du.{group}.{label.id}", {})
    if (row.get("status") == "verified" and row.get("zh_CN") == label.zh
            and isinstance(row.get("ko_KR"), str) and compact(row["ko_KR"])):
        return compact(row["ko_KR"]), True
    return compact(label.candidate), False


def korean_match(group, probe, rows, registry, *, only=None):
    """Return a status and exact OCR hits, including blocked and pending hits."""
    hits = []
    labels = [(label, *korean_label(group, label, registry)) for label in probe.labels]
    for index, (_, (text, confidence)) in enumerate(rows):
        token = compact(text).lstrip("•·※.")
        for label, expected, verified in labels:
            # Alternate observed text remains a candidate until it is selected for live verification.
            if token != expected and token not in map(compact, label.variants):
                continue
            if sum(char.isalnum() for char in token) < 3 or token in GENERIC_KOREAN:
                status = "unsafe_label"
            elif not confidence >= MIN_CONFIDENCE:
                status = "low_confidence"
            else:
                status = "matched" if verified and token == expected else "candidate"
            hits.append({"id": label.id, "row": index, "status": status})

    if group == "mode" and only is not None:
        # The same menu can legitimately show both modes. A shared spelling or
        # a second position for the requested mode is still ambiguous.
        requested_rows = {hit["row"] for hit in hits if hit["id"] == only}
        hits = [hit for hit in hits if hit["row"] in requested_rows]
    if len(hits) > 1:
        return "ambiguous", hits
    return (hits[0]["status"] if hits else "missing"), hits


def area_in_viewport(area, viewport):
    left, top, width, height = viewport
    x, y, w, h = area
    return left + x * width, top + y * height, w * width, h * height


def korean_viewport(screenshot):
    # The N150 sample has a 1024×768 viewport centered in its 1024×1280 client.
    if screenshot.size == (1024, 1280):
        strips = (screenshot.crop((256, y, 768, y + 4)).convert("L") for y in (128, 1152))
        if all(strip.getextrema()[1] <= 8 for strip in strips):
            return 0, 256 / 1280, 1, 768 / 1280
    return 0, 0, 1, 1


def rows_in_area(rows, resolution, area):
    width, height = resolution
    x, y, w, h = area
    return [
        row for row in rows
        if all(x * width <= px <= (x + w) * width and y * height <= py <= (y + h) * height
               for px, py in row[0])
    ]


def find_text(auto, config, group, *, only=None, max_retries=1):
    """Resolve a screen-local ID and its position using the current capture."""
    probe = PROBES[group]
    if game_language(config) == "zh_CN":
        labels = tuple(label for label in probe.labels if only is None or label.id == only)
        text = tuple(label.zh for label in labels)
        pos = auto.find_element(text[0] if len(text) == 1 else text, "text", crop=probe.area,
                                include=probe.include_zh, max_retries=max_retries)
        if pos:
            for label in labels:
                if len(labels) == 1 or auto.matched_text == label.zh:
                    return label.id, pos
        return None

    import time

    registry = strings()
    if not any(korean_label(group, label, registry)[1]
               for label in probe.labels if only is None or only == label.id):
        return None
    for attempt in range(max_retries):
        if auto.take_screenshot():
            auto.perform_ocr()
            # Use the same whole-box crop and ambiguity checks as collector replay.
            area = area_in_viewport(KOREAN_AREAS.get(group, probe.area), korean_viewport(auto.screenshot))
            rows = rows_in_area(auto.ocr_result, auto.screenshot.size, area)
            status, hits = korean_match(group, probe, rows, registry, only=only)
            if status == "matched":
                hit = hits[0]
                if only is None or hit["id"] == only:
                    box = rows[hit["row"]][0]
                    return hit["id"], auto.calculate_text_position(box, relative=False)
        if attempt + 1 < max_retries:
            time.sleep(1)
    return None


def click_text(auto, config, group, only, max_retries=1):
    if game_language(config) == "zh_CN":
        probe = PROBES[group]
        label = next(label for label in probe.labels if label.id == only)
        return auto.click_element(label.zh, "text", crop=probe.area, include=probe.include_zh,
                                  max_retries=max_retries)
    found = find_text(auto, config, group, only=only, max_retries=max_retries)
    return bool(found and auto.click_element_with_pos(found[1]))


@dataclass(frozen=True)
class Stage:
    current: int
    total: int
    plane: int
    station: str

    @property
    def progress(self):
        return self.current, self.total


def zh_stage(text):
    match = ZH_STAGE.search(text or "")
    if not match:
        return None
    current, total, plane_text, station = match.groups()
    plane = "一二三".index(plane_text) + 1
    if total == "13":
        for index, rooms in enumerate((range(1, 5), range(5, 10), range(10, 14)), 1):
            if current in map(str, rooms):
                plane = index
                break
    return current, total, plane, station


def zh_progress(text):
    match = re.search(PROGRESS, text or "")
    if match:
        current, total = map(int, match.groups())
        if 1 <= current <= total:
            return current, total
    return None


def weekly_score(text, *, korean=False):
    """Read the known score format. Korean layout and limits need game evidence."""
    if korean:
        text = compact(text)
    parts = text.split("/")
    if len(parts) != 2 or parts[1] not in WEEKLY_SCORE_LIMITS:
        return None
    current, limit = parts
    if korean:
        if not current.isdecimal() or len(current) > len(limit) or int(current) > int(limit):
            return None
    elif not current.isdigit():
        return None
    return current, limit


def weekly_score_hits(rows):
    hits = []
    for index, (_, (text, confidence)) in enumerate(rows):
        score = weekly_score(text, korean=True)
        if score:
            current, limit = map(int, score)
            hits.append({
                "row": index,
                "status": "candidate" if confidence >= MIN_CONFIDENCE else "low_confidence",
                "state": "quota_reached" if current == limit else "points_remaining",
                "current": current,
                "limit": limit,
            })
    if len(hits) > 1:
        return "ambiguous", hits
    return (hits[0]["status"] if hits else "missing"), hits


def korean_stage(rows, registry):
    hits = []
    for index, (_, (text, confidence)) in enumerate(rows):
        match = KO_STAGE.fullmatch(normalize(text).lstrip("•· "))
        if not match:
            continue
        current, total, plane_text, station_text = match.groups()
        current, total = int(current), int(total)
        if not 1 <= current <= total:
            continue
        for plane_index, plane in enumerate(PLANES, 1):
            expected_plane, plane_verified = korean_label("stage", plane, registry)
            if compact(plane_text) != expected_plane:
                continue
            for station in STATIONS:
                expected_station, station_verified = korean_label("stage", station, registry)
                if compact(station_text) != expected_station:
                    continue
                if not confidence >= MIN_CONFIDENCE:
                    status = "low_confidence"
                else:
                    status = "matched" if plane_verified and station_verified else "candidate"
                hits.append((status, index, Stage(current, total, plane_index, station.id)))
    if len(hits) > 1:
        return "ambiguous", hits
    return (hits[0][0] if hits else "missing"), hits


def read_korean_stage(auto):
    if auto.take_screenshot():
        auto.perform_ocr()
        area = area_in_viewport(KOREAN_STAGE_AREA, korean_viewport(auto.screenshot))
        rows = rows_in_area(auto.ocr_result, auto.screenshot.size, area)
        status, hits = korean_stage(rows, strings())
        if status == "matched":
            return hits[0][2]
    return None
