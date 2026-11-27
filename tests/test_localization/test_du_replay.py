import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.localization import du_recognition as du
from tools.localization.du_replay import replay


def row(text, x=105, y=68, confidence=0.99, width=100):
    return {
        "text": text,
        "confidence": confidence,
        "box": [[x, y], [x + width, y], [x + width, y + 15], [x, y + 15]],
    }


def frame(name, *rows):
    return {"image": name, "resolution": [1920, 1080], "language": "ko_KR",
            "screen_id": "unknown", "ocr_results": list(rows)}


def write_jsonl(path, frames):
    path.write_text("".join(json.dumps(frame, ensure_ascii=False) + "\n" for frame in frames),
                    encoding="utf-8")


def approve(registry, group, label_id, text=None):
    labels = (du.PLANES + du.STATIONS) if group == "stage" else du.PROBES[group].labels
    label = next(label for label in labels if label.id == label_id)
    registry[f"du.{group}.{label_id}"] = {
        "status": "verified", "zh_CN": label.zh, "ko_KR": text or label.candidate,
    }


def test_replay_uses_collector_schema_and_reports_ambiguity(tmp_path):
    ocr = [
        frame("spacing.png", row("방정식을　선택하세요")),
        frame("joined.png", row("방정식을선택하세요")),
        frame("wrong-area.png", row("방정식을 선택하세요", x=60)),
        frame("short.png", row("사건")),
        frame("ambiguous.png", row("방정식을선택하세요"), row("일반 적 처치! 축복 1회 선택 가능")),
        frame("low.png", row("방정식을선택하세요", confidence=0.79)),
        frame("longer.png", row("방정식을선택하세요방법")),
        frame("progress.png", row("• （ 5 / 13 ）제 2 차원 — 전투", x=72, y=19, width=160)),
        frame("both-modes.png", row("일반연산", x=470, y=325), row("주기연산", x=470, y=420)),
    ]
    write_jsonl(tmp_path / "ocr.jsonl", ocr)
    write_jsonl(tmp_path / "events.jsonl", [*ocr, frame("no-ocr.png")])

    report = replay(tmp_path, data=tmp_path)
    assert report["missing_ocr"] == ["no-ocr.png"]
    decisions = {item["image"]: item["decisions"] for item in report["frames"]}
    for image in ("spacing.png", "joined.png"):
        assert decisions[image]["title"]["hits"] == [{"id": "equation", "row": 0, "status": "candidate"}]
    assert decisions["wrong-area.png"]["title"]["outside_crop"][0]["id"] == "equation"
    assert decisions["wrong-area.png"]["title"]["status"] == "missing"
    assert decisions["short.png"]["title"]["status"] == "unsafe_label"
    assert decisions["ambiguous.png"]["title"]["status"] == "ambiguous"
    assert decisions["low.png"]["title"]["status"] == "low_confidence"
    assert decisions["longer.png"]["title"]["status"] == "missing"
    assert decisions["progress.png"]["stage"]["hits"] == [
        {"status": "candidate", "row": 0, "current": 5, "total": 13, "plane": 2,
         "station": "battle", "route": "battle"}
    ]
    assert decisions["both-modes.png"]["mode.normal"]["status"] == "candidate"
    assert decisions["both-modes.png"]["mode.cycle"]["status"] == "candidate"


@pytest.fixture
def task(monkeypatch):
    auto = Mock()
    auto.screenshot = SimpleNamespace(size=(1920, 1080))
    auto.calculate_text_position.side_effect = lambda box, relative: (box[0], box[2])
    for name, exports in {
        "module.automation": {"auto": auto},
        "module.config": {"cfg": SimpleNamespace(divergent_station_priority_enable=False)},
        "module.config.platform": {"get_control_backend": lambda cfg: "native"},
        "module.screen": {"screen": Mock()},
        "module.logger": {"log": Mock()},
        "module.automation.screenshot": {"Screenshot": Mock()},
        "module.notification.notification": {"NotificationLevel": Mock()},
        "tasks.base.base": {"Base": Mock()},
        "tasks.base.task_steps": {"optional_reward": Mock()},
        "tasks.power.power": {"Power": Mock()},
        "tasks.weekly.weekly_reward": {"claim_weekly_reward": Mock()},
    }.items():
        stub = ModuleType(name)
        vars(stub).update(exports)
        monkeypatch.setitem(sys.modules, name, stub)

    path = Path(__file__).resolve().parents[2] / "tasks/weekly/divergent_universe.py"
    spec = importlib.util.spec_from_file_location("_test_du_replay_task", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=Mock()))
    registry = {}
    monkeypatch.setattr(du, "strings", lambda: registry)
    monkeypatch.setenv("M7A_GAME_LANGUAGE", "ko_KR")
    return module.DivergentUniverse(), auto, registry


def set_ocr(auto, *rows):
    auto.ocr_result = [(r["box"], (r["text"], r["confidence"])) for r in rows]


def test_task_title_dispatch_only_for_verified_unique_in_crop(task):
    obj, auto, registry = task
    obj.process_equation = Mock()
    set_ocr(auto, row("방정식을선택하세요"))
    assert not obj.check_title()
    approve(registry, "title", "equation")
    set_ocr(auto, row("방정식을선택하세요", x=1400))
    assert not obj.check_title()
    set_ocr(auto, row("방정식을선택하세요"), row("일반적처치!축복1회선택가능"))
    assert not obj.check_title()
    obj.process_equation.assert_not_called()

    set_ocr(auto, row("방정식을선택하세요"))
    assert obj.check_title()
    obj.process_equation.assert_called_once()


def test_mode_click_uses_requested_id_and_blocks_collisions(task):
    _, auto, registry = task
    approve(registry, "mode", "normal")
    approve(registry, "mode", "cycle")
    normal = row("일반연산", x=470, y=325)
    cycle = row("※주기 연산", x=470, y=420)
    set_ocr(auto, normal, cycle)

    assert du.click_text(auto, None, "mode", "cycle")
    auto.click_element_with_pos.assert_called_once_with((cycle["box"][0], cycle["box"][2]))

    auto.click_element_with_pos.reset_mock()
    approve(registry, "mode", "normal", "주기연산")
    assert not du.click_text(auto, None, "mode", "cycle")
    auto.click_element_with_pos.assert_not_called()


def test_generic_verified_button_never_clicks(task):
    _, auto, registry = task
    approve(registry, "equation_confirm", "confirm")
    set_ocr(auto, row("확인", x=1680, y=955, width=50))
    assert not du.click_text(auto, None, "equation_confirm", "confirm")
    auto.click_element_with_pos.assert_not_called()


def test_stage_routing_requires_verified_full_progress(task):
    obj, auto, registry = task
    obj.process_battle_stage = Mock()
    obj.process_event_stage = Mock()
    auto.find_element.side_effect = lambda target, *_args, **_kwargs: target.endswith("/stage.png")
    assert not obj.current_stage
    set_ocr(auto, row("(5/13) 제2차원-전투", x=72, y=19, width=170))
    obj.check_stage()
    assert not obj.current_stage

    approve(registry, "stage", "plane_2")
    approve(registry, "stage", "battle")
    for text in ("전투", "(99/13) 제2차원-전투", "(5/13) 제2차원-전", "(5/13) 전투"):
        set_ocr(auto, row(text, x=72, y=19, width=170))
        obj.check_stage()
        assert not obj.current_stage
    obj.process_battle_stage.assert_not_called()

    set_ocr(auto, row("( 5 / 13 ) 제 2 차원 - 전 투", x=72, y=19, width=170))
    obj.check_stage()
    obj.process_battle_stage.assert_called_once()
    obj.process_event_stage.assert_not_called()


@pytest.mark.parametrize(("text", "expected"), [("탐사성공", True), ("탐사 중단", False)])
def test_settlement_result_stays_unknown_on_conflict(task, text, expected):
    obj, auto, registry = task
    approve(registry, "settlement_result", "success")
    approve(registry, "settlement_result", "interrupted")
    set_ocr(auto, row(text))
    obj._check_battle_result()
    assert obj.result is expected

    set_ocr(auto, row("탐사성공"), row("탐사 중단", y=100))
    obj._check_battle_result()
    assert obj.result is None


def test_legacy_zh_dispatch_and_progress(task, monkeypatch):
    obj, auto, _ = task
    monkeypatch.setenv("M7A_GAME_LANGUAGE", "zh_CN")
    obj.process_blessing = Mock()
    auto.matched_text = "选择祝福"
    assert obj.check_title()
    obj.process_blessing.assert_called_once()
    assert du.zh_stage("（5/13）第三位面-战斗") == ("5", "13", 2, "战斗")
    assert du.zh_progress("( 7 / 17 )") == (7, 17)
    assert du.zh_progress("( 99 / 17 )") is None


def test_task_station_dispatch_skips_ambiguous_card(task):
    obj, auto, registry = task
    approve(registry, "title", "next_station")
    approve(registry, "station_1", "boss")
    approve(registry, "station_2", "battle", "전투 구역")
    approve(registry, "station_confirm", "confirm", "구역 선택 확정")
    auto.click_element.return_value = False  # Optional image confirmation is not present.
    boss = row("우두머리", x=610, y=460, width=80)
    battle = row("전투구역", x=855, y=460)
    confirm = row("구역선택확정", x=640, y=960)
    set_ocr(auto, row("다음행선지선택"), boss, row("우두머리", x=610, y=510), battle, confirm)

    assert obj.check_title()
    assert obj.stage_finish
    assert [call.args[0] for call in auto.click_element_with_pos.call_args_list] == [
        (battle["box"][0], battle["box"][2]),
        (confirm["box"][0], confirm["box"][2]),
    ]


def test_navigation_graph_calls_du_actions():
    path = Path(__file__).resolve().parents[2] / "assets/config/screens.json"
    screens = json.loads(path.read_text(encoding="utf-8"))
    calls = [
        command
        for screen in screens
        for action in screen.get("actions", [])
        for command in action.get("actions_list", [])
        if command.startswith("auto.click_divergent_text(")
    ]
    assert calls == [
        "auto.click_divergent_text('guide_entry', 'open')",
        "auto.click_divergent_text('guide_participate', 'participate')",
        "auto.click_divergent_text('mode', 'normal')",
        "auto.click_divergent_text('mode', 'cycle')",
    ]


def test_replay_reports_pending_weekly_points_without_marking_claimed(tmp_path):
    incomplete = row("９０００ ／ １８０００", x=204, y=980, width=130)
    capped = row("18000/18000", x=204, y=1000, width=130)
    mailing = row("보상이우편으로발송되었습니다", x=60, y=926, width=240)
    write_jsonl(tmp_path / "ocr.jsonl", [
        frame("incomplete.png", incomplete),
        frame("capped.png", capped),
        frame("conflict.png", capped, incomplete),
        frame("over-limit.png", row("19000/18000", x=204, y=980)),
        frame("mail.png", mailing),
    ])

    report = replay(tmp_path, data=tmp_path)
    decisions = {item["image"]: item["decisions"] for item in report["frames"]}
    for image, state in (("incomplete.png", "points_remaining"), ("capped.png", "quota_reached")):
        score = decisions[image]["weekly_score"]
        assert score["status"] == "candidate"
        assert score["hits"][0]["state"] == state
    assert decisions["conflict.png"]["weekly_score"]["status"] == "ambiguous"
    assert decisions["over-limit.png"]["weekly_score"]["status"] == "missing"
    assert decisions["mail.png"]["weekly_reward_mail"]["status"] == "candidate"


def test_legacy_weekly_score_still_marks_only_the_exact_limit(task, monkeypatch):
    obj, auto, _ = task
    monkeypatch.setenv("M7A_GAME_LANGUAGE", "zh_CN")
    cfg = obj.check_divergent_universe_score.__func__.__globals__["cfg"]
    cfg.save_timestamp = Mock()
    auto.find_element.return_value = None
    auto.get_single_line_text.side_effect = ["9000/18000", "18000/18000"]

    assert not obj.check_divergent_universe_score()
    cfg.save_timestamp.assert_not_called()
    assert obj.check_divergent_universe_score()
    cfg.save_timestamp.assert_called_once_with("weekly_divergent_timestamp")


def test_sample_letterbox_keeps_full_window_click_coordinates(task):
    from PIL import Image

    _, auto, registry = task
    approve(registry, "mode", "cycle")
    screenshot = Image.new("RGB", (1024, 1280), "black")
    screenshot.paste("white", (0, 256, 1024, 1024))
    auto.screenshot = screenshot
    cycle = row("※주기 연산", x=270, y=586, width=96)
    set_ocr(auto, cycle)

    assert du.click_text(auto, None, "mode", "cycle")
    auto.click_element_with_pos.assert_called_once_with((cycle["box"][0], cycle["box"][2]))

    screenshot.paste("white", (0, 0, 1024, 256))
    assert du.korean_viewport(screenshot) == (0, 0, 1, 1)


def test_server_disconnect_replays_separately_from_settlement(tmp_path):
    capture = frame("disconnect.png", row(
        "서버와 연결이 끊겼습니다. 다시 로그인해 주세요",
        x=725, y=520, width=400,
    ))
    write_jsonl(tmp_path / "ocr.jsonl", [capture])

    decisions = replay(tmp_path, data=tmp_path)["frames"][0]["decisions"]

    assert decisions["disconnect"]["status"] == "candidate"
    assert decisions["settlement_result"]["status"] == "missing"


def test_live_probe_reports_mission_and_preserves_letterbox_coordinates():
    from PIL import Image
    from tools.localization.du_probe import inspect

    screenshot = Image.new("RGB", (1024, 1280), "black")
    screenshot.paste("white", (0, 256, 1024, 1024))
    anchor = row("안정적 배열", x=54, y=297, width=60)
    objective = row("메인 운명의 길이 기억인 3성 방정식 1회 전개", x=260, y=395, width=315)
    status = row("진행 중", x=920, y=397, width=45)
    rows = [(r["box"], (r["text"], r["confidence"])) for r in (anchor, objective, status)]

    report = inspect(screenshot, rows)

    assert report["viewport"] == (0, 0.2, 1, 0.6)
    assert report["missions"] == [
        {"objective": objective["text"], "state": "in_progress",
         "confidence_status": "candidate", "goal": "expand_equation"}
    ]
    assert inspect(screenshot, rows[1:])["missions"] == []


def test_korean_automation_does_not_enter_or_settle_unverified_run(task):
    obj, auto, _ = task

    assert obj.start("cycle") is False
    assert obj.run("cycle") is False
    assert obj.check_divergent_universe_score() is False
    assert not auto.mock_calls
