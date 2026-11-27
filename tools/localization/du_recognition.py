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
    Label("battle", "战斗", "전투"), Label("elite", "精英", "정예", ("정에",)),
    Label("event", "事件", "사건"), Label("abnormal", "异常", "이상"),
    Label("reward", "奖励", "보상"), Label("wealth", "财富", "재물"),
    Label("adventure", "冒险", "모험"), Label("shop", "商店", "상점"),
    Label("forge", "铸造", "주조"), Label("blank", "空白", "공백"),
    Label("encounter", "奇遇", "기연"), Label("boss", "首领", "보스", ("우두머리",)),
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
        Label("normal", "常规演算", "일반 연산", ("3일반 연산", "0일반 연산", "--일반 연산")), Label("cycle", "周期演算", "주기 연산", ("-+주기 연산",)),
    )),
    "title": Probe(crop(96, 63, 142, 34), (
        Label("mask", "欢愉假面", "환락의 가면"),
        Label("shop", "", "축복 상점", ("방정식 상점",)),
        Label("workbench", "", "창조물 작업대"),
        Label("equation", "选择方程", "방정식을 선택하세요"),
        Label("blessing", "选择祝福", "일반 적 처치! 축복 1회 선택 가능",
              ("보스 적 처치! 축복을 1회 선택할 수 있습니다", "정예 적 처치! 축복 1회 선택 가능")),
        Label("curio", "选择奇物", "기물 선택"),
        Label("discard_curio", "丢弃奇物", "기물 버리기"),
        Label("destroy_curio", "奇物损毁", "기물 훼손"),
        Label("wish", "愿力满盈", "당신의 기적을 선택하세요", ("경이로운 기적을 선택하세요",)),
        Label("next_station", "选择下一站", "다음 행선지 선택"),
        Label("event", "事件", "사건", ("B 사건", "2 사건")),
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
}
# OCR landmarks from the Korean PC capture. Coordinates are within the game viewport.
PROBES.update({
    "lobby_start": Probe(n150_area(730, 650, 270, 85), (Label("start", "", "게임 시작"),)),
    "lobby_missions": Probe(n150_area(825, 403, 190, 100), (Label("open", "", "안정적 배열"),)),
    "mission_page": Probe(n150_area(25, 32, 160, 49), (Label("open", "", "안정적 배열", ("안정적 배멸",)),)),
    "mode_page": Probe(n150_area(15, 43, 165, 42), (Label("open", "", "모드 선택"),)),
    "launch": Probe(n150_area(785, 644, 225, 88), (Label("start", "", "차분화 우주 가동"),)),
    "party": Probe(n150_area(534, 575, 270, 92), (Label("ready", "", "캐릭터 다운로드"),)),
    "world_entry": Probe(n150_area(590, 365, 310, 90), (Label("open", "", "차분화 우주"),)),
    "close_popup": Probe(n150_area(395, 590, 240, 158), (Label("close", "", "빈 곳을 클릭해 닫기"),)),
    "wish_confirm": Probe(n150_area(453, 651, 118, 77), (Label("confirm", "", "확인"),)),
    "card_confirm": Probe(n150_area(795, 635, 142, 82), (Label("confirm", "", "확인"),)),
    "card_upgrade": Probe(n150_area(40, 82, 340, 41), (Label("upgrade", "", "구역 1개를 지정해 레벨+1"),)),
    "world_door": Probe(n150_area(600, 400, 253, 55), (Label("open", "", "어디로나 문"),)),
    "report_heading": Probe(n150_area(133, 233, 228, 60), (Label("report", "", "적합 레벨"),)),
    "report_content": Probe(n150_area(345, 235, 311, 65), (Label("report", "", "차분화 우주 구축 내용"),)),
    "du_header": Probe(n150_area(35, 33, 116, 33), (Label("header", "", "차분화 우주"),)),
    "event_confirm": Probe(n150_area(692, 100, 332, 590), (
        Label("confirm", "", "확인"), Label("select", "", "선택"),
    )),
    "loot": Probe(n150_area(585, 385, 305, 85), (
        Label("loot", "", "진귀한 전리품", ("페진귀한전리품",)),
    )),
    "disconnect": Probe(n150_area(340, 343, 360, 82), (
        Label("disconnected", "", "서버와 연결이 끊겼습니다. 다시 로그인해 주세요",
              ("서버와 연결이 끊겼습니다 다시 로그인해 주세요",)),
    )),
})
DISCONNECT_PROBE = PROBES["disconnect"]
KOREAN_AREAS.update({
    "title": n150_area(17, 39, 650, 78),
    "mask_action": n150_area(590, 430, 230, 100),
    "end_previous": n150_area(12, 340, 400, 289),
    "continue_run": n150_area(12, 340, 420, 289),
    "equation_confirm": n150_area(840, 657, 148, 72),
    "blessing_confirm": n150_area(832, 648, 148, 77),
    "curio_confirm": n150_area(845, 650, 150, 78),
    "discard_confirm": n150_area(845, 650, 150, 78),
    "station_confirm": n150_area(320, 648, 372, 82),
    "station_1": n150_area(345, 374, 111, 181),
    "station_2": n150_area(480, 374, 128, 181),
    "station_3": n150_area(624, 374, 124, 181),
    "settlement_action": n150_area(280, 633, 470, 100),
    "settlement_result": n150_area(135, 230, 240, 144),
})

# Screen-local matches for the PC layout. A success label still requires an
# explicit verified override until a Korean success report is captured.
VERIFIED_KOREAN = {
    "title": {"mask", "equation", "blessing", "curio", "wish", "next_station", "event", "station_card",
              "shop", "workbench"},
    "stage": {"plane_1", "plane_2", "plane_3", "battle", "elite", "wealth", "event", "forge", "shop",
              "boss", "reward", "rest", "abnormal", "blank"},
    "mode": {"normal", "cycle"},
    "end_previous": {"end_run"},
    "continue_run": {"continue"},
    "mask_action": {"choose_mask"},
    "settlement_action": {"return_main"},
    "settlement_result": {"interrupted"},
    "du_header": {"header"},
    "world_door": {"open"},
    "report_heading": {"report"},
    "report_content": {"report"},
    **{group: {label.id for label in PROBES[group].labels} for group in (
        "lobby_start", "lobby_missions", "mission_page", "mode_page", "launch", "party", "world_entry",
        "close_popup", "wish_confirm", "card_confirm", "card_upgrade", "event_confirm", "loot", "disconnect",
        "equation_confirm", "blessing_confirm", "curio_confirm", "station_confirm",
    )},
    **{f"station_{index}": {"battle", "elite", "event", "reward", "wealth", "shop", "forge", "boss", "rest", "abnormal", "blank"}
       for index in range(1, 4)},
}

# Short tokens only become actionable alongside an independently recognized screen.
KOREAN_GUARDS = {
    "equation_confirm": ("title", "equation"),
    "blessing_confirm": ("title", "blessing"),
    "curio_confirm": ("title", "curio"),
    "discard_confirm": ("title", "discard_curio"),
    "wish_confirm": ("title", "wish"),
    "station_confirm": ("title", "next_station"),
    "card_confirm": ("title", "station_card"),
    "event_confirm": ("title", "event"),
}


MIN_CONFIDENCE = 0.80
GENERIC_KOREAN = {"확인", "선택", "취소", "닫기", "나가기", "계속", "버리기", "돌아가기"}
PROGRESS = r"[（(]\s*(\d+)\s*/\s*(13|17|20)\s*[)）]"
ZH_STAGE = re.compile(PROGRESS + r"\s*第\s*([一二三])\s*位面(?:\s*[-—－]\s*(.+))?")
KO_STAGE = re.compile(r"(?:1?(?:\[|\())?([0-9]{1,2})/(113|13|17|20)[\])]?((?:제[123]차원))[-—－]?(.+)")


def compact(text):
    return normalize(text).replace(" ", "")


def korean_label(group, label, registry):
    row = registry.get(f"du.{group}.{label.id}", {})
    if (row.get("status") == "verified" and row.get("zh_CN") == label.zh
            and isinstance(row.get("ko_KR"), str) and compact(row["ko_KR"])):
        return compact(row["ko_KR"]), True
    return compact(label.candidate), label.id in VERIFIED_KOREAN.get(group, ())



def korean_match(group, probe, rows, registry, *, only=None, guarded=False):
    """Return a status and exact OCR hits, including blocked and pending hits."""
    hits = []
    labels = [(label, *korean_label(group, label, registry)) for label in probe.labels]
    for index, (_, (text, confidence)) in enumerate(rows):
        token = compact(text).lstrip("•·※.~×\x60:")
        if group in {"launch", "world_entry"}:
            token = re.sub(r"[\[\]「」『』]", "", token)
        for label, expected, verified in labels:
            # Variants are exact alternatives for the same screen-local label.
            if token != expected and token not in map(compact, label.variants):
                continue
            if (sum(char.isalnum() for char in token) < 3 or token in GENERIC_KOREAN) and not guarded:
                status = "unsafe_label"
            elif not confidence >= MIN_CONFIDENCE:
                status = "low_confidence"
            else:
                status = "matched" if verified else "candidate"
            hits.append({"id": label.id, "row": index, "status": status})

    if group in {"mode", "title", "settlement_action", "event_confirm"} and only is not None:
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


class KoreanFrame:
    """Read multiple probes from one capture before making a decision."""

    def __init__(self, auto):
        self.auto = auto
        auto.take_screenshot()
        auto.perform_ocr()
        self.resolution = auto.screenshot.size
        self.viewport = korean_viewport(auto.screenshot)
        self.rows = auto.ocr_result
        self.registry = strings()

    def in_area(self, area):
        return rows_in_area(self.rows, self.resolution, area_in_viewport(area, self.viewport))

    def find(self, group, only=None):
        probe = PROBES[group]
        rows = self.in_area(KOREAN_AREAS.get(group, probe.area))
        guard = KOREAN_GUARDS.get(group)
        guarded = bool(guard and (self.is_event() if group == "event_confirm" else self.find(*guard)))
        if group.startswith("station_") and group[-1].isdigit():
            guarded = bool(self.find("title", "next_station"))
        if group == "title" and only == "event":
            guarded = bool(self.find("du_header"))
        if guard and not guarded:
            return None
        status, hits = korean_match(group, probe, rows, self.registry, only=only, guarded=guarded)
        if status == "matched":
            hit = hits[0]
            if only is None or hit["id"] == only:
                return hit["id"], self.auto.calculate_text_position(rows[hit["row"]][0], relative=False)
        return None

    def is_event(self):
        if not self.find("du_header"):
            return False
        if self.find("title", "event"):
            return True
        # Some captures omit the short header but retain the event narrator
        # in the right-hand panel.
        return any(compact(text) in {"시뮬레이션우주", "시물레이션우주"} and score >= MIN_CONFIDENCE
                   for _, (text, score) in self.in_area(n150_area(695, 75, 300, 415)))

    def is_report(self):
        return bool(self.find("report_heading") and self.find("report_content"))

    def difficulty(self, wanted):
        levels = ("I", "II", "III", "IV", "V")
        area = n150_area(527, 70, 470, 75)
        hits = []
        for _, (text, score) in self.in_area(area):
            match = re.search(r"난이도([IV]+)$", compact(text))
            if match and score >= MIN_CONFIDENCE:
                hits.append(match[1])
        return hits == [levels[wanted - 1]]

    def stage(self):
        status, hits = korean_stage(self.in_area(KOREAN_STAGE_AREA), self.registry)
        return hits[0][2] if status == "matched" else None

    def score(self):
        status, hits = weekly_score_hits(self.in_area(KOREAN_WEEKLY_SCORE_AREA))
        return hits[0] if status == "candidate" else None


def find_text(auto, config, group, *, only=None, max_retries=1):
    """Resolve a screen-local ID and its position using the current capture."""
    probe = PROBES[group]
    if game_language(config) == "zh_CN":
        labels = tuple(label for label in probe.labels if label.zh and (only is None or label.id == only))
        text = tuple(label.zh for label in labels)
        pos = auto.find_element(text[0] if len(text) == 1 else text, "text", crop=probe.area,
                                include=probe.include_zh, max_retries=max_retries)
        if pos:
            for label in labels:
                if len(labels) == 1 or auto.matched_text == label.zh:
                    return label.id, pos
        return None

    import time

    for attempt in range(max_retries):
        found = KoreanFrame(auto).find(group, only)
        if found:
            return found
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
        match = KO_STAGE.fullmatch(compact(text).lstrip("•·\x60:"))
        if not match:
            continue
        current, total, plane_text, station_text = match.groups()
        current, total = int(current), 13 if total == "113" else int(total)
        if not 1 <= current <= total:
            continue
        for plane_index, plane in enumerate(PLANES, 1):
            expected_plane, plane_verified = korean_label("stage", plane, registry)
            if compact(plane_text) != expected_plane:
                continue
            for station in STATIONS:
                expected_station, station_verified = korean_label("stage", station, registry)
                if compact(station_text) not in {expected_station, *map(compact, station.variants)}:
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
    return KoreanFrame(auto).stage()
