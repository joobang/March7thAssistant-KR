from utils.game_options import game_option_enabled
from module.screen import screen
from module.automation import auto
from module.config import cfg
from module.config.platform import get_control_backend
from module.logger import log
from module.automation.screenshot import Screenshot
from module.notification.notification import NotificationLevel
from tasks.base.base import Base
from tasks.base.task_steps import optional_reward
from utils.date import Date
from module.overview import plan
from utils.game_key_templates import find_interact_prompt
from typing import Literal, Tuple, Optional
import numpy as np
import time
import os
import re
from tasks.power.power import Power
from tasks.weekly.weekly_reward import claim_weekly_reward
from tools.localization import du_recognition as du


class DivergentUniverse:
    def __init__(self):
        self.screenshot = None  # 任务截图
        self.result: Optional[bool] = None  # 对局结果
        self.current_stage: str = ""  # 当前关卡阶段
        self.process_stage: bool = False  # 是否正在处理关卡中
        self.end_loop: bool = False  # 是否结束主循环
        self._save_attempted: bool = False  # 本轮是否尝试过存档
        self.stage_finish: bool = False  # 是否完成当前阶段
        self.unsupported_area: bool = False  # 是否遇到暂不支持区域
        self._korean_selection = None

    @staticmethod
    def _get_count_config(cycle: Literal["daily", "weekly"]):
        return plan.count_keys(cycle)

    @staticmethod
    def get_recorded_run_count(cycle: Literal["daily", "weekly"], sync: bool = True) -> int:
        count, needs_reset = plan.current_count(cfg, cycle)
        if sync and needs_reset:
            DivergentUniverse.reset_recorded_run_count(cycle)
        return count

    @staticmethod
    def reset_recorded_run_count(cycle: Optional[Literal["daily", "weekly"]] = None):
        cycles = (cycle,) if cycle else ("daily", "weekly")
        values = {}
        for current_cycle in cycles:
            count_key, timestamp_key = DivergentUniverse._get_count_config(current_cycle)
            values.update({count_key: 0, timestamp_key: 0})
        cfg.set_values(values)

    @staticmethod
    def record_completed_run() -> dict:
        now = time.time()
        counts = {}
        values = {}
        for cycle in ("daily", "weekly"):
            count_key, timestamp_key = DivergentUniverse._get_count_config(cycle)
            count = DivergentUniverse.get_recorded_run_count(cycle, sync=False) + 1
            values.update({count_key: count, timestamp_key: now})
            counts[cycle] = count
        cfg.set_values(values)
        return counts

    def start(self, universe_type: Optional[Literal["normal", "cycle"]] = None) -> bool:
        if du.game_language(cfg) == "ko_KR":
            return self.run_korean(universe_type)
        log.hr('准备差分宇宙', '0')
        success = self.run(universe_type)
        if success:
            Base.send_notification_with_screenshot("差分宇宙已完成", NotificationLevel.ALL, self.screenshot)
            self.screenshot = None
        else:
            if self.unsupported_area:
                Base.send_notification_with_screenshot("差分宇宙未完成\n遇到暂不支持的区域", NotificationLevel.ERROR, self.screenshot)
            else:
                Base.send_notification_with_screenshot("差分宇宙未完成", NotificationLevel.ERROR, self.screenshot)
            self.screenshot = None
        has_reward = self.get_reward()
        if Date.is_next_mon_x_am(cfg.weekly_divergent_timestamp, cfg.refresh_hour):
            with optional_reward("差分宇宙周期积分检查"):
                self.check_divergent_universe_score()
        if has_reward and cfg.weekly_divergent_bonus_enable:
            with optional_reward("差分宇宙周期奖励饰品提取"):
                self.process_ornament()
        log.hr("完成", 2)
        return success

    def check_divergent_universe_score(self) -> bool:
        """
        检查差分宇宙积分，达到 18000 时记录时间戳
        """
        if du.game_language(cfg) == "ko_KR":
            frame = self.korean_frame()
            score = frame.score() if frame.find("lobby_start") else None
            if score:
                log.info(f"차분화 우주 주간 점수 {score['current']} / {score['limit']}")
                if score["state"] == "quota_reached":
                    cfg.save_timestamp("weekly_divergent_timestamp")
                    return True
            return False
        screen.change_to("divergent_main", max_recursion=1)

        # 4.2版本周期积分将合并。本期积分奖励已由邮件发放。
        if du.find_text(auto, cfg, "weekly_reward_mail"):
            log.info("检测到积分奖励已由邮件发放，跳过积分检查")
            cfg.save_timestamp("weekly_divergent_timestamp")
            return True

        score = auto.get_single_line_text(du.WEEKLY_SCORE_AREA)
        if not score:
            log.warning("未识别到差分宇宙积分")
            return False

        parsed = du.weekly_score(score)
        if parsed:
            current, max_score = parsed
            log.info(f"差分宇宙积分：{current} / {max_score}")
            if current == max_score:
                cfg.save_timestamp("weekly_divergent_timestamp")
                log.info(f"已达到最高积分 {max_score}，记录时间")
                return True
        else:
            log.warning(f"无法解析差分宇宙积分: {score}")
        return False

    def run(self, universe_type: Optional[Literal["normal", "cycle"]] = None) -> bool:
        if universe_type is None:
            universe_type = cfg.weekly_divergent_type
        if self.start_war(universe_type):
            return self.loop()
        return False

    def run_korean(self, universe_type=None, *, resume=False):
        from module.automation.automation import capture_viewport, screenshot_retry_timeout
        from utils.screenshot_util import save_error_screenshot

        if get_control_backend(cfg) != "local":
            log.error("한국어 차분화 우주 테스트는 Windows PC 게임 창에서 실행해 주세요.")
            return False

        try:
            with screenshot_retry_timeout(10):
                auto.take_screenshot()
                viewport = du.korean_viewport(auto.screenshot)
                with capture_viewport(viewport):
                    return self.loop() if resume else self.run(universe_type)
        except RuntimeError as error:
            log.error(f"차분화 우주 중지. {error}")
            self.screenshot = auto.screenshot
            with screenshot_retry_timeout(0):
                save_error_screenshot(log)
            return False

    @staticmethod
    def korean_frame():
        frame = du.KoreanFrame(auto)
        if frame.find("disconnect"):
            raise RuntimeError("서버 연결이 끊겼습니다. 게임에 다시 로그인한 뒤 탐사를 이어가세요.")
        return frame

    def wait_korean(self, group, action=None, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.korean_frame()
            if frame.find(group, action):
                return frame
            time.sleep(1)
        return None

    def start_korean_war(self, mode):
        level = int(cfg.weekly_divergent_level)
        if mode == "cycle":
            level = min(level, 5)
        if mode not in {"normal", "cycle"} or not 1 <= level <= 5:
            raise RuntimeError("한국어 테스트는 일반·주기 연산의 난이도 I–V를 지원합니다.")

        frame = self.korean_frame()
        if frame.find("world_entry"):
            auto.press_key(cfg.get_game_hotkey("hotkey_interact", "f"))
            frame = self.wait_korean("lobby_start")
            if frame is None:
                raise RuntimeError("차분화 우주 입구에서 메인 화면이 열리지 않았습니다.")

        if frame.find("mission_page"):
            auto.press_key("esc")
            frame = self.wait_korean("lobby_start")
            if frame is None:
                raise RuntimeError("안정적 배열에서 차분화 우주 메인 화면으로 돌아오지 못했습니다.")

        if lobby := frame.find("lobby_start"):
            score = frame.score()
            if score:
                log.info(f"차분화 우주 주간 점수 {score['current']} / {score['limit']}")
            if not auto.click_element_with_pos(lobby[1]):
                raise RuntimeError("게임 시작 버튼을 클릭하지 못했습니다.")
            frame = self.wait_korean("mode_page")
        if frame is None:
            raise RuntimeError("모드 선택 화면이 열리지 않았습니다.")
        if frame.find("mode_page"):
            if frame.find("continue_run") or frame.find("end_previous"):
                raise RuntimeError("진행 중인 탐사가 있습니다. 게임에서 진도를 계속한 뒤 이어서 실행해 주세요.")
            option = frame.find("mode", mode)
            if not option or not auto.click_element_with_pos(option[1]):
                raise RuntimeError("설정한 연산 모드를 선택하지 못했습니다.")
            frame = self.wait_korean("launch")
        if frame is None:
            raise RuntimeError("연산 입장 화면을 확인하지 못했습니다.")
        # The five difficulty buttons share the same vertical rail as the PC UI.
        if not auto.click_element(du.n150_area(51, 99 + (level - 1) * 58, 34, 32), "crop",
                                  take_screenshot=False):
            raise RuntimeError("연산 난이도를 선택하지 못했습니다.")

        time.sleep(1)
        frame = self.wait_korean("launch")
        if frame is None or not frame.difficulty(level):
            raise RuntimeError(f"선택한 난이도 {level}을 입장 화면에서 확인하지 못했습니다.")
        if not frame.find("party") or auto.find_element(
            "./assets/images/share/universe/empty_character_slot.png", "image_count", 0.8,
            crop=du.n150_area(581, 660, 213, 64), pixel_bgr=[233, 233, 233],
        ):
            raise RuntimeError("입장 화면에서 사용할 파티를 편성한 뒤 다시 실행해 주세요.")

        if not du.click_text(auto, cfg, "launch", "start", max_retries=3):
            raise RuntimeError("차분화 우주 가동 버튼을 클릭하지 못했습니다.")
        log.info(f"차분화 우주 탐사를 시작합니다. 난이도 {level}")
        return True

    def get_reward(self):
        log.info("开始领取奖励")
        claimed = False
        with optional_reward("差分宇宙周期奖励"):
            if not auto.click_element("./assets/images/share/base/RedExclamationMark.png", "image", 0.9, crop=(0 / 1920, 877.0 / 1080, 422.0 / 1920, 202.0 / 1080)):
                return False
            def notify(image):
                with optional_reward("差分宇宙周期奖励通知"):
                    Base.send_notification_with_screenshot(
                        cfg.notify_template['SimulatedUniverseRewardClaimed'], NotificationLevel.ALL, image)

            claimed = claim_weekly_reward(on_receipt=notify)
            if claimed:
                auto.press_key("esc")
        return claimed

    def process_ornament(self):
        Power.process_immersifier_only()

    def start_war(self, type: Literal["normal", "cycle"] = "normal") -> bool:
        if du.game_language(cfg) == "ko_KR":
            return self.start_korean_war(type)
        log.info("开始「差分宇宙」")
        screen.change_to("divergent_mode_select")

        if du.click_text(auto, cfg, "end_previous", "end_run"):
            log.warning("检测到未结算的对局，放弃并结算中")
            if auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9, max_retries=10):
                self.loop()

        if type == "normal":
            log.info("选择常规演算")
            screen.change_to("divergent_mode_select_normal")
        else:
            log.info("选择周期演算")
            screen.change_to("divergent_mode_select_cycle")

        if not self.choose_level(int(cfg.weekly_divergent_level), type):
            log.error("选择关卡失败，结束任务")
            return False

        self.choose_team()

        if type == "normal" and int(cfg.weekly_divergent_level) == 6:
            if not auto.click_element("./assets/images/screen/divergent_universe/astronomical.png", "image", 0.9, 10):
                log.error("未找到进入星阶模式按钮，结束任务")
                return False

        if not auto.click_element("./assets/images/screen/divergent_universe/start.png", "image", 0.9, 10):
            log.error("未找到开始对局按钮，结束任务")
            return False
        else:
            time.sleep(1)
            auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9, max_retries=4)

        log.info("开始对局")
        return True

    def choose_level(self, level: int, type: Literal["normal", "cycle"] = "normal") -> bool:
        """
        选择关卡难度
        """
        log.info("选择关卡")

        level_positions = [
            (94 / 1920, 145 / 1080, 67 / 1920, 68 / 1080),
            (93 / 1920, 253 / 1080, 68 / 1920, 68 / 1080),
            (92 / 1920, 362 / 1080, 68 / 1920, 67 / 1080),
            (94 / 1920, 469 / 1080, 67 / 1920, 67 / 1080),
            (93 / 1920, 580 / 1080, 68 / 1920, 64 / 1080),
            (93 / 1920, 689 / 1080, 68 / 1920, 64 / 1080)
        ]

        if type == "cycle" and level == 6:
            log.info("周期演算不开启阈值协议，难度 6 视为难度 5")
            level = 5

        if auto.click_element(level_positions[level - 1], 'crop'):
            log.info(f"已选择难度 {level} 的关卡")
            time.sleep(1)
            if type == "cycle":
                for _ in range(10):
                    if auto.find_element("阈值协议", "text", crop=(1616 / 1920, 822 / 1080, 92 / 1920, 32 / 1080)):
                        auto.click_element((1492 / 1920, 868 / 1080, 75 / 1920, 39 / 1080), "crop")
                        time.sleep(1)
                    else:
                        break
            return True
        return False

    def choose_team(self):
        team_slot_crop = (1098 / 1920, 922 / 1080, 375 / 1920, 96 / 1080)
        if auto.find_element("./assets/images/share/universe/empty_character_slot.png", "image_count", 0.8, crop=team_slot_crop, pixel_bgr=[233, 233, 233]) == 4:
            if auto.click_element("./assets/images/share/universe/empty_character_slot.png", "image", 0.8, crop=team_slot_crop, take_screenshot=False):
                time.sleep(2)
                if auto.click_element("预设编队", "text", max_retries=4, retry_delay=0.5, crop=(6 / 1920, 8 / 1080, 578 / 1920, 168 / 1080)):
                    click_x = auto.screenshot_pos[0] + 260 / auto.screenshot_scale_factor
                    click_y = auto.screenshot_pos[1] + 175 / auto.screenshot_scale_factor
                    time.sleep(1.0)
                    if auto.click_element_with_pos(((click_x, click_y), (click_x, click_y))):
                        time.sleep(1.0)
                        auto.press_key("esc")
            time.sleep(1.0)

    def loop(self) -> bool:
        """
        差分宇宙任务主循环
        """
        self.screenshot = None  # 任务截图
        self.result = None  # 重置结果
        self.current_stage = ""  # 重置当前关卡阶段
        self.process_stage = False  # 重置关卡处理状态
        self.end_loop = False  # 重置结束循环标志
        self._save_attempted = False  # 每轮探索最多尝试一次存档
        self.stage_finish = False  # 重置阶段完成标志
        self.unsupported_area = False  # 重置暂不支持区域标志

        start_time = time.monotonic()
        timeout = 60 * 120  # 120分钟超时
        korean = du.game_language(cfg) == "ko_KR"
        last_stage = ""
        last_progress = start_time
        while True:
            if korean:
                if time.monotonic() - start_time > timeout:
                    raise RuntimeError("탐사 실행 시간 120분을 초과했습니다.")
                frame = self.korean_frame()
                if self.check_korean_settlement(frame):
                    return self.finish_korean_run()

                stage = frame.stage()
                if self.current_stage != last_stage:
                    last_stage = self.current_stage
                    last_progress = time.monotonic()
                if time.monotonic() - last_progress > 360:
                    raise RuntimeError("6분 동안 다음 구역 진입을 확인하지 못했습니다. 현재 화면에서 탐사를 이어갈 수 있습니다.")
                if self.check_title(frame) or self.check_click_close(frame):
                    time.sleep(1)
                    continue
                if stage:
                    self.check_stage(stage)
                    time.sleep(1)
                    continue
                self.check_auto_battle()
                time.sleep(2)
                continue

            # 检查超时
            if time.monotonic() - start_time > timeout:
                log.error("差分宇宙主循环超时（120分钟），强制退出")
                return False

            if (
                self.check_stage()
                or self.check_title()
                or self.check_auto_battle()
                or self.check_click_close()
                or self.check_click_return()
            ):
                continue
            elif self.end_loop:
                end_time = time.monotonic()
                elapsed_time = end_time - start_time
                minutes = int(elapsed_time // 60)
                seconds = int(elapsed_time % 60)
                log.info(f"本次差分宇宙用时：{minutes} 分钟 {seconds} 秒")
                time.sleep(4)
                screen.wait_for_screen_change("divergent_main")
                log.info("已返回差分宇宙首页")
                result = self.result if self.result is not None else False
                if result:
                    counts = DivergentUniverse.record_completed_run()
                    log.info(f"已记录差分宇宙次数：今日 {counts['daily']} 次，本周 {counts['weekly']} 次")
                return result

            time.sleep(4)

    def check_stage(self, stage=None):
        if du.game_language(cfg) == "ko_KR":
            stage = stage or self.korean_frame().stage()
            if not stage:
                return
            current, total = str(stage.current), str(stage.total)
            plane = "一二三"[stage.plane - 1]
            station_id = stage.station
            station = du.STATION_BY_ID[station_id]
        else:
            if not self.stage_visible():
                return
            if result := auto.find_element("./assets/images/screen/divergent_universe/show.png", "image", 0.9, crop=(383 / 1920, 57 / 1080, 71 / 1920, 48 / 1080)):
                auto.press_key_down("alt")
                try:
                    time.sleep(1)
                    auto.click_element_with_pos(result)
                    time.sleep(1)
                finally:
                    auto.press_key_up("alt")
                time.sleep(2)
            stage = self._read_zh_stage()
            if not stage:
                return
            current, total, plane, station = stage
            station_id = du.legacy_station_id(station)

        route = du.stage_route(station_id)
        new_stage = f"{current}/{total}|第{plane}位面|{station}"
        if new_stage != self.current_stage:
            self.stage_finish = False
            self.current_stage = new_stage
            log.hr(f"当前阶段 {current}/{total}，第{plane}位面，区域：{station}", 2)
            if route == "battle":
                self.process_battle_stage()
            elif route == "walk":
                auto.press_mouse()
                time.sleep(2)
                for _ in range(100):
                    if self.check_click_close() or self.check_title():
                        time.sleep(2)
                    else:
                        break
                auto.press_key("w", 2)
                self.process_battle_stage_finish()
            elif route == "event":
                self.process_event_stage()
            else:
                if du.game_language(cfg) == "ko_KR":
                    raise RuntimeError(f"자동 이동을 지원하지 않는 구역입니다 ({station_id}).")
                log.info("检测到暂不支持的区域类型")
                self.unsupported_area = True
                if station_id == "adventure":
                    time.sleep(5)
                    if self.check_click_close():
                        log.info("检测到冒险区域且存在教学弹窗，尝试关闭")
                        time.sleep(2)
                        for _ in range(10):
                            if not auto.click_element("关闭", "text", crop=(926 / 1920, 869 / 1080, 65 / 1920, 38 / 1080)):
                                auto.click_element((1811 / 1920, 461 / 1080, 70 / 1920, 94 / 1080), "crop")
                                time.sleep(2)
                            else:
                                time.sleep(2)
                                break
                        else:
                            if not self.stage_visible():
                                log.error("多次尝试关闭冒险教学弹窗失败")
                                raise RuntimeError("多次尝试关闭冒险教学弹窗失败")
                self.process_leave()

        elif self.stage_finish:
            # 选中特定 “惊世奇迹” 例如 “财猫面具·破” 以后，存在 bug，虽然不计算区域进度，但是左上角的区域类型不会变化
            # 此时只需要暂离，重新进入，左上角就会显示正确的区域类型
            # 火箭喷射信标也有类似效果
            log.info("发现阶段完成但区域未变化，可能存在区域类型显示错误")
            if du.game_language(cfg) == "ko_KR":
                # The old HUD can remain visible for a frame after door input.
                return
            self.process_re_enter()
            # 避免区域相同 反复重进
            self.current_stage = ""  # 重置当前关卡阶段

        elif self.process_stage and route in ("battle", "event"):
            self.process_battle_stage_finish()

    def stage_visible(self, max_retries=1):
        if du.game_language(cfg) == "ko_KR":
            return auto.find_element(
                "./assets/images/screen/divergent_universe/ko_stage.png", "image", 0.90,
                crop=du.n150_area(12, 25, 60, 44), scale_range=(0.8, 1.45),
                max_retries=max_retries, retry_delay=0.5,
            )
        return auto.find_element(
            "./assets/images/screen/divergent_universe/stage.png", "image", 0.9,
            crop=(33 / 1920, 52 / 1080, 68 / 1920, 60 / 1080),
            max_retries=max_retries, retry_delay=0.5,
        )

    def interact_prompt(self, key, *, compact=False):
        if du.game_language(cfg) == "ko_KR" and key == "f":
            return auto.find_element(
                "./assets/images/screen/divergent_universe/ko_interact_f.png", "image", 0.90,
                crop=du.n150_area(550, 370, 85, 100), scale_range=(0.8, 1.45),
            )
        return find_interact_prompt(auto, key, compact=compact)

    def loot_prompt(self):
        if du.game_language(cfg) == "ko_KR":
            return self.korean_frame().find("loot", "loot")
        return auto.find_element(("战利品", "混沌药箱"), "text",
                                 crop=(1205 / 1920, 589 / 1080, 193 / 1920, 49 / 1080), include=True)

    def _read_zh_stage(self):
        keywords = ["战斗", "精英", "事件", "异常", "奖励", "财富", "冒险", "商店", "铸造", "空白", "首领", "休整", "转化"]

        def normalize_station(raw_station):
            station_name = raw_station.strip() if raw_station else "未知"
            if station_name and station_name not in keywords:
                for keyword in keywords:
                    if any(char in keyword for char in station_name):
                        return keyword
            return station_name

        def parse_stage_info(stage_value):
            if not stage_value:
                return None
            stage_info_match = re.match(r"^(\d+)/(\d+)\|第([一二三])位面\|(.+)$", stage_value)
            if not stage_info_match:
                return None
            return stage_info_match.groups()

        stage_match = du.zh_stage(auto.get_single_line_text(crop=du.STAGE_AREA))
        if stage_match:
            current, total, plane_index, station = stage_match
            plane = "一二三"[plane_index - 1]
            station = normalize_station(station)

            if station == "未知":
                previous_stage_info = parse_stage_info(self.current_stage)
                if previous_stage_info:
                    prev_current, prev_total, prev_plane, prev_station = previous_stage_info
                    if (current, total, plane) == (prev_current, prev_total, prev_plane):
                        station = prev_station
                        log.debug(f"区域识别为未知且关卡未变化，沿用上一阶段区域：{station}")

                if station == "未知":
                    for retry in range(3):
                        time.sleep(1)
                        retry_stage_text = auto.get_single_line_text(crop=du.STAGE_AREA)
                        if not retry_stage_text:
                            continue

                        retry_stage_match = du.zh_stage(retry_stage_text)
                        if not retry_stage_match:
                            continue

                        _, _, _, retry_station = retry_stage_match
                        retry_station = normalize_station(retry_station)
                        if retry_station != "未知":
                            station = retry_station
                            log.debug(f"区域识别重试成功（第 {retry + 1} 次）：{station}")
                            break

            return current, total, plane, station

    def detect_events(self):
        """使用YOLO检测所有事件目标。"""
        return auto.find_element(
            target={"model_path": "./assets/model/divergent.onnx", "names": ["door", "event"], "target_class": "event"},
            find_type="yolo_with_multiple_targets",
            threshold=0.2
        )

    def find_closest_event(self, events, screen_center_x):
        """从事件列表中找到距离屏幕中心最近的事件。"""
        if not events:
            return None
        closest = None
        min_dist = float('inf')
        for top_left, bottom_right in events:
            center_x = (top_left[0] + bottom_right[0]) // 2
            dist = abs(center_x - screen_center_x)
            if dist < min_dist:
                min_dist = dist
                closest = (top_left, bottom_right)
        return closest

    def calculate_area(self, top_left, bottom_right):
        """根据左上角和右下角坐标计算区域面积。"""
        width = max(0, bottom_right[0] - top_left[0])
        height = max(0, bottom_right[1] - top_left[1])
        return width * height

    def process_event_stage(self):
        stable_mode = get_control_backend(cfg) == "cloud" or cfg.weekly_divergent_stable_mode
        window = Screenshot.get_window(cfg.game_title_name)
        win_x, _, width, _ = Screenshot.get_window_region(window)
        screen_center_x = win_x + width // 2
        tolerance = width // 12
        fine_tolerance = width // 15
        interact_key = cfg.get_game_hotkey("hotkey_interact", "f")

        event_count = 0
        timeout_retries = 0

        while event_count < 5:
            log.info(f"事件处理第 {event_count + 1}/5 轮（超时重试 {timeout_retries}/3）")

            # 检测所有事件
            time.sleep(4)
            events = self.detect_events()
            if not events:
                log.info("未检测到任何事件，尝试向前移动后重试")
                auto.press_key("w", 1)
                events = self.detect_events()
                if not events:
                    log.info("未检测到任何事件，尝试向前移动后重试")
                    auto.press_key("w", 1)
                    events = self.detect_events()
                    if not events:
                        log.info("未检测到任何事件，事件处理完成")
                        self.process_stage = True
                        return

            event_length = len(events)
            log.info(f"检测到 {event_length} 个事件")

            # 找到距离屏幕中心最近的事件
            closest = self.find_closest_event(events, screen_center_x)
            top_left, bottom_right = closest
            event_center_x = (top_left[0] + bottom_right[0]) // 2

            # 左右移动，将事件对齐到屏幕中心
            if abs(event_center_x - screen_center_x) > tolerance:
                key = "a" if event_center_x < screen_center_x else "d"
                log.debug(f"事件在屏幕{'左边' if key == 'a' else '右边'}，正在调整位置")
                if stable_mode:
                    start_time = time.monotonic()
                    while time.monotonic() - start_time < 10:
                        auto.press_key(key, wait_time=0.15)
                        events = self.detect_events()
                        if not events:
                            break
                        closest = self.find_closest_event(events, screen_center_x)
                        if not closest:
                            break
                        top_left, bottom_right = closest
                        event_center_x = (top_left[0] + bottom_right[0]) // 2
                        if abs(event_center_x - screen_center_x) <= tolerance:
                            log.debug("事件已调整到屏幕中间")
                            break
                else:
                    auto.press_key_down(key)
                    try:
                        start_time = time.monotonic()
                        while time.monotonic() - start_time < 10:
                            time.sleep(0.1)
                            events = self.detect_events()
                            if not events:
                                break
                            closest = self.find_closest_event(events, screen_center_x)
                            if not closest:
                                break
                            top_left, bottom_right = closest
                            event_center_x = (top_left[0] + bottom_right[0]) // 2
                            if abs(event_center_x - screen_center_x) <= tolerance:
                                log.debug("事件已调整到屏幕中间")
                                break
                    finally:
                        auto.press_key_up(key)
            else:
                log.debug("事件已在屏幕中间")

            # 向事件走去，边走边检测交互键和事件位置
            event_interacted = False

            timeout = 60 if stable_mode else 15
            area_growth_ratio = 1.08

            if not stable_mode:
                auto.press_key_down("w")

            area_window_start_time = time.monotonic()
            area_window_start_value = None
            area_window_latest_value = None
            has_f_or_adjusted_in_window = False

            try:
                start_time = time.monotonic()
                while time.monotonic() - start_time < timeout:
                    if self.interact_prompt(interact_key, compact=True):
                        has_f_or_adjusted_in_window = True
                        log.debug("检测到交互键提示")
                        if not stable_mode:
                            auto.press_key_up("w")
                        if (du.game_language(cfg) == "ko_KR"
                                or auto.find_element("事件", "text", crop=(1205 / 1920, 589 / 1080, 193 / 1920, 49 / 1080), include=True)):
                            auto.press_key(interact_key)
                            time.sleep(2)
                            event_start_time = time.monotonic()
                            # for _ in range(100):
                            event_timeout = 120 if du.game_language(cfg) == "ko_KR" else 30 * 60
                            while time.monotonic() - event_start_time < event_timeout:  # 最多等待30分钟 应该不会有人战斗能打半小时吧
                                if self.check_click_close() or self.check_title() or self.check_auto_battle():
                                    if self.stage_finish:
                                        return
                                    time.sleep(2)
                                elif self.stage_visible():
                                    break
                                else:
                                    time.sleep(2)
                            event_interacted = True
                            break
                        else:
                            if not stable_mode:
                                auto.press_key_down("w")
                            time.sleep(0.5)

                    # 细微调整方向
                    events = self.detect_events()
                    if events:
                        closest = self.find_closest_event(events, screen_center_x)
                        if closest:
                            top_left, bottom_right = closest
                            current_area = self.calculate_area(top_left, bottom_right)
                            area_window_latest_value = current_area
                            if area_window_start_value is None:
                                area_window_start_value = current_area

                            event_center_x = (top_left[0] + bottom_right[0]) // 2
                            offset = event_center_x - screen_center_x
                            if abs(offset) > fine_tolerance:
                                adjust_key = "a" if offset < 0 else "d"
                                # has_f_or_adjusted_in_window = True
                                if stable_mode:
                                    auto.press_key_down("w")
                                try:
                                    auto.press_key(adjust_key, wait_time=0.15)
                                finally:
                                    if stable_mode:
                                        auto.press_key_up("w")
                            else:
                                if stable_mode:
                                    auto.press_key("w")
                    else:
                        if timeout_retries > 1 and self.detect_random_door:
                            has_f_or_adjusted_in_window = True
                            # 可能将随意门识别成事件了，尝试一次直接找门
                            if self.process_random_door():
                                log.info("中断事件处理，已检测到随意门并成功进入")
                                return

                    if time.monotonic() - area_window_start_time >= 2:
                        area_growth_ok = (
                            area_window_start_value is not None
                            and area_window_latest_value is not None
                            and area_window_latest_value >= area_window_start_value * area_growth_ratio
                        )
                        log.debug(
                            f"事件区域面积增长检测 - 起始值: {area_window_start_value}, 最新值: {area_window_latest_value}, 增长率: {area_window_latest_value / area_window_start_value if area_window_start_value else 'N/A'}, 是否满足增长条件: {area_growth_ok}")

                        if (not has_f_or_adjusted_in_window) and (not area_growth_ok):
                            log.info("可能遇到可破坏物遮挡，尝试攻击")
                            auto.press_key_up("w")
                            auto.press_mouse()
                            time.sleep(2)
                            has_interaction = False
                            for _ in range(100):
                                if self.check_click_close() or self.check_title():
                                    has_interaction = True
                                    time.sleep(2)
                                else:
                                    break
                            if self.stage_finish:
                                return
                            if has_interaction:
                                start_time = time.monotonic()
                            else:
                                start_time += 2

                            if not stable_mode:
                                auto.press_key_down("w")

                        area_window_start_time = time.monotonic()
                        area_window_start_value = area_window_latest_value
                        has_f_or_adjusted_in_window = False

            finally:
                if not stable_mode:
                    auto.press_key_up("w")

            if event_interacted:
                # 事件交互后视角会变化，且不容易判断是否还有其他事件
                # 重进关卡是最简单粗暴的解决办法，能大大提高稳定性
                log.info("事件交互成功")

                # 如果只有一个事件且检测到了随意门，尝试一下直接去找门
                if event_length == 1:
                    time.sleep(2)  # 事件卡消失要一定时间
                    timeout = 40 if stable_mode else 10
                    if self.detect_random_door and self.process_random_door(timeout=timeout):
                        log.info("中断事件处理，已检测到随意门并成功进入")
                        return

                if self.stage_finish or self.process_re_enter():
                    return
                event_count += 1
                timeout_retries = 0
            else:
                timeout_retries += 1
                if timeout_retries >= 3:
                    log.info("事件连续超时3次，尝试离开关卡")
                    self.process_leave()
                    return
                log.info(f"事件超时（第 {timeout_retries}/3 次），重新进入关卡重试")

                if self.interact_prompt(interact_key) and self.loot_prompt():
                    log.info(f"检测到{auto.matched_text}，尝试点击")
                    auto.press_key(interact_key)
                    time.sleep(2)
                    for _ in range(100):
                        if self.check_click_close() or self.check_title():
                            time.sleep(2)
                        else:
                            break

                time.sleep(1)
                auto.press_mouse()
                time.sleep(2)
                for _ in range(100):
                    if self.check_click_close() or self.check_title():
                        time.sleep(2)
                    else:
                        break

                if self.stage_finish or self.process_re_enter():
                    return

        log.info("事件处理超过5轮，尝试离开关卡")
        self.process_leave()

    def process_battle_stage(self):
        interact_key = cfg.get_game_hotkey("hotkey_interact", "f")
        is_boss = self.current_stage.endswith("|首领")
        forward_attempts = 0

        for _ in range(3):
            time.sleep(2)
            enemy_crop = (675 / 1920, 41 / 1080, 274 / 1920, 37 / 1080)
            sprint = get_control_backend(cfg) != "cloud" and not cfg.weekly_divergent_stable_mode
            auto.press_key_down("w")
            try:
                time.sleep(0.2)
                if sprint:
                    auto.press_key_down("shift")
                start_time = time.monotonic()
                while time.monotonic() - start_time < 3:
                    if auto.find_element("./assets/images/screen/divergent_universe/enemy.png", "image", 0.9, crop=enemy_crop):
                        log.info("检测到敌对目标")
                        break
                else:
                    log.info("未检测到敌对目标")
                time.sleep(0.8)
            finally:
                try:
                    auto.press_key_up("w")
                finally:
                    if sprint:
                        auto.press_key_up("shift")

            if self.interact_prompt(interact_key) and self.loot_prompt():
                log.info(f"检测到{auto.matched_text}，尝试点击")
                auto.press_key(interact_key)
                time.sleep(2)
                for _ in range(100):
                    if self.check_click_close() or self.check_title():
                        time.sleep(2)
                    else:
                        break
                if self.stage_finish or self.process_re_enter():
                    return
                continue

            log.info("尝试进入战斗")
            for _ in range(5):
                auto.press_mouse()
                time.sleep(0.5)
                if not self.stage_visible():
                    break
            for _ in range(100):
                if self.check_click_close() or self.check_title():
                    time.sleep(2)
                else:
                    break

            if self.stage_finish:
                return

            # 进入战斗失败，尝试重新进入
            if self.stage_visible():
                auto.press_key("s")
                log.info("尝试进入战斗")
                for _ in range(5):
                    auto.press_mouse()
                    time.sleep(0.5)
                    if not self.stage_visible():
                        break
                for _ in range(100):
                    if self.check_click_close() or self.check_title():
                        time.sleep(2)
                    else:
                        break
                if self.stage_finish:
                    return
                on_stage = self.stage_visible(max_retries=2 if is_boss else 1)
                if is_boss:
                    while on_stage and forward_attempts < 5:
                        forward_attempts += 1
                        log.info(f"前进 1 秒接近首领（{forward_attempts}/5）")
                        moved = auto.press_key("w", 1)
                        on_stage = self.stage_visible(max_retries=2)
                        if on_stage and moved is not False:
                            auto.press_mouse()
                            time.sleep(1)
                            on_stage = self.stage_visible(max_retries=2)
                    if not on_stage:
                        self.process_stage = True
                        return
                if on_stage:
                    if self.process_re_enter():
                        return
                    continue
            else:
                self.process_stage = True
                return
        log.info("多次尝试进入战斗失败")
        self.process_stage = True

    def process_battle_stage_finish(self):
        interact_key = cfg.get_game_hotkey("hotkey_interact", "f")
        time.sleep(2)
        self.process_stage = False

        if self.interact_prompt(interact_key) and self.loot_prompt():
            log.info(f"检测到{auto.matched_text}，尝试点击")
            auto.press_key(interact_key)
            time.sleep(2)
            for _ in range(100):
                if self.check_click_close() or self.check_title():
                    time.sleep(2)
                else:
                    break

        if self.process_random_door():
            return

        if self.interact_prompt(interact_key) and self.loot_prompt():
            log.info(f"检测到{auto.matched_text}，尝试点击")
            auto.press_key(interact_key)
            time.sleep(2)
            for _ in range(100):
                if self.check_click_close() or self.check_title():
                    time.sleep(2)
                else:
                    break
            if self.stage_finish or self.process_re_enter():
                return
            if self.process_random_door():
                return

        auto.press_mouse()
        time.sleep(2)
        for _ in range(100):
            if self.check_click_close() or self.check_title():
                time.sleep(2)
            else:
                break

        if self.process_random_door():
            return

        auto.press_key("a", 0.5)
        time.sleep(0.2)
        auto.press_key("w", 0.5)
        if self.process_random_door():
            return

        auto.press_mouse()
        time.sleep(2)
        for _ in range(100):
            if self.check_click_close() or self.check_title():
                time.sleep(2)
            else:
                break
        if self.stage_finish or self.process_re_enter():
            return
        auto.press_key("w", 2)
        if self.process_random_door():
            return

        auto.press_key("d", 0.5)
        time.sleep(0.2)
        auto.press_key("w", 1)
        time.sleep(0.2)
        auto.press_key("a", 0.5)
        if self.process_random_door():
            return

        auto.press_mouse()
        time.sleep(2)
        for _ in range(100):
            if self.check_click_close() or self.check_title():
                time.sleep(2)
            else:
                break
        if self.stage_finish or self.process_re_enter():
            return
        auto.press_key("w", 2)
        if self.process_random_door(stable_mode=True):
            return

        auto.press_key("a", 0.5)
        time.sleep(0.2)
        auto.press_key("w", 0.5)
        if self.process_random_door(stable_mode=True):
            return

        auto.press_key("d", 0.5)
        time.sleep(0.2)
        auto.press_key("w", 1)
        time.sleep(0.2)
        auto.press_key("a", 0.5)
        if self.process_random_door(stable_mode=True):
            return

        self.process_leave()

    def process_leave(self):
        if du.game_language(cfg) == "ko_KR":
            if self.korean_frame().is_report():
                return
            raise RuntimeError("현재 구역에서 자동 진행을 계속할 수 없습니다. 탐사 진도를 보존했습니다.")
        log.info("尝试离开当前关卡")
        auto.press_key("esc")
        if du.click_text(auto, cfg, "end_run", "end_run", max_retries=10):
            auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9, max_retries=10)
        else:
            self.stage_finish = True

    def has_stage_changed(self) -> bool:
        """只核对区域编号，交由主循环处理新区域，避免嵌套执行关卡。"""
        previous = re.match(r"^(\d+)/(13|17|20)\|", self.current_stage)
        if not previous:
            return False
        previous_progress = tuple(map(int, previous.groups()))
        last_progress = None
        korean = du.game_language(cfg) == "ko_KR"
        for attempt in range(3):
            if korean:
                stage = du.read_korean_stage(auto)
                progress = stage.progress if stage else None
            else:
                progress = du.zh_progress(auto.get_single_line_text(crop=du.STAGE_AREA))
            if progress:
                if progress == previous_progress:
                    return False
                # 连续两次读到同一新编号才退出旧流程，避免单帧 OCR 误识别。
                if progress == last_progress:
                    log.info(f"区域进度已变化：{previous_progress[0]}/{previous_progress[1]} → {progress[0]}/{progress[1]}，返回主循环处理")
                    return True
                last_progress = progress
            else:
                last_progress = None
            if attempt < 2:
                time.sleep(0.5)
        return False

    def process_re_enter(self) -> bool:
        """重新进入关卡；区域编号已变化时返回 True，调用方应停止旧区域流程。"""
        if du.game_language(cfg) == "ko_KR":
            return self.has_stage_changed()
        interact_key = cfg.get_game_hotkey("hotkey_interact", "f")
        log.info("尝试重新进入当前关卡")
        for _ in range(3):
            auto.press_key("esc")
            if auto.click_element("暂离", "text", max_retries=10, crop=(1238 / 1920, 859 / 1080, 562 / 1920, 165 / 1080)):
                screen.wait_for_screen_change("main")
                if self.interact_prompt(interact_key):
                    auto.press_key(interact_key)
                    screen.wait_for_screen_change('divergent_main')
                screen.change_to("divergent_mode_select")
                if du.click_text(auto, cfg, "continue_run", "continue"):
                    if not self.wait_stage_after_continue():
                        raise RuntimeError("重新进入关卡失败")
                    return self.has_stage_changed()
                else:
                    raise RuntimeError("未找到继续进度按钮")
        log.error("多次尝试重新进入关卡失败")
        return False

    def wait_stage_after_continue(self, max_retries: int = 120) -> bool:
        """等待“继续进度”后进入关卡界面，顺带处理跨周确认框（#1175）。

        周期演算每周一 4:00 更新：循环运行跨过这个时间点时，上一次的存档已属于上一周，
        点“继续进度”后游戏会先弹确认框“当前存档非本周演算进度，进度所在玩法已过期，
        仍可获得拟合值和「模拟宇宙」积分，确定继续进度吗？”。
        不处理它就会一直卡在弹窗上，把原本等待关卡界面的 120 次重试耗光，最后误报
        “重新进入关卡失败”；弹窗说明继续进度仍会结算积分，所以这里点“确认”继续原进度。
        """
        # 弹窗在点击“继续进度”后立刻出现，只在开头几秒内探测，避免常态路径反复 OCR
        prompt_deadline = time.monotonic() + 10
        for attempt in range(max_retries):
            if self.stage_visible():
                return True
            # 关卡界面通常一两秒内就会出现，迟迟不出现时优先怀疑这个弹窗
            if (attempt >= 3 and time.monotonic() < prompt_deadline
                    and auto.find_element("当前存档非本周演算进度", "text", max_retries=1, include=True, threshold=0.7)):
                log.info("检测到“当前存档非本周演算进度”提示，点击确认继续进度")
                auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9, max_retries=10,
                                   crop=(1100 / 1920, 630 / 1080, 280 / 1920, 82 / 1080))
                prompt_deadline = time.monotonic() + 10  # 点击没生效时还能再次识别
                continue
            time.sleep(1)
        return False

    def detect_random_door(self):
        return auto.find_element(
            target={"model_path": "./assets/model/divergent.onnx", "names": ["door", "event"], "target_class": "door"},
            find_type="yolo",
            threshold=0.01
        )
        # LOWER = np.array([112, 82, 174])
        # UPPER = np.array([170, 126, 239])
        # crop = (68 / 1920, 4 / 1080, 1718 / 1920, 818 / 1080)
        # return auto.find_element((LOWER, UPPER), "hsv", crop=crop)
        LOWER = np.array([129, 57, 143])
        UPPER = np.array([174, 163, 229])
        remove_crop = (1494 / 1920, 0 / 1080, 424 / 1920, 268 / 1080)
        auto.fill_crop_with_color(remove_crop, (0, 0, 0))
        return auto.find_element((LOWER, UPPER), "hsv", take_screenshot=False)

    def process_random_door(self, stable_mode=False, timeout=15):
        if self.stage_finish:
            return True
        if get_control_backend(cfg) == "cloud" or cfg.weekly_divergent_stable_mode:
            stable_mode = True
        window = Screenshot.get_window(cfg.game_title_name)
        win_x, _, width, _ = Screenshot.get_window_region(window)
        screen_center_x = win_x + width // 2
        tolerance = width // 10  # 屏幕宽度10%作为容差

        result = self.detect_random_door()
        if not result:
            log.debug("未检测到随意门")
            return False

        top_left, bottom_right = result
        door_center_x = (top_left[0] + bottom_right[0]) // 2

        if abs(door_center_x - screen_center_x) <= tolerance:
            log.debug("随意门已在屏幕中间")
        else:
            key = "a" if door_center_x < screen_center_x else "d"
            log.debug(f"随意门在屏幕{'左边' if key == 'a' else '右边'}，正在调整位置")

            if stable_mode:
                start_time = time.monotonic()
                while time.monotonic() - start_time < 10:
                    auto.press_key(key, wait_time=0.15)
                    result = self.detect_random_door()
                    if not result:
                        return False
                    top_left, bottom_right = result
                    door_center_x = (top_left[0] + bottom_right[0]) // 2
                    if abs(door_center_x - screen_center_x) <= tolerance:
                        log.debug("随意门已调整到屏幕中间")
                        break
            else:
                auto.press_key_down(key)
                try:
                    start_time = time.monotonic()
                    while time.monotonic() - start_time < 10:
                        time.sleep(0.1)
                        result = self.detect_random_door()
                        if not result:
                            return False
                        top_left, bottom_right = result
                        door_center_x = (top_left[0] + bottom_right[0]) // 2
                        if abs(door_center_x - screen_center_x) <= tolerance:
                            log.debug("随意门已调整到屏幕中间")
                            break
                finally:
                    auto.press_key_up(key)

        # 向随意门走去，边走边检测交互键和门的位置
        interact_key = cfg.get_game_hotkey("hotkey_interact", "f")
        door_crop = (1146 / 1920, 585 / 1080, 57 / 1920, 57 / 1080)

        if stable_mode:
            fine_tolerance = width // 15
        else:
            fine_tolerance = width // 12  # 屏幕宽度10%作为容差

        if not stable_mode:
            auto.press_key_down("w")
            # time.sleep(0.2)
            # auto.press_key_down("shift")
        # else:
        #     auto.press_key("w", 1.5)

        if stable_mode:
            timeout = 60

        try:
            start_time = time.monotonic()
            # time.sleep(1)
            korean = du.game_language(cfg) == "ko_KR"
            while time.monotonic() - start_time < timeout:
                if self.interact_prompt(interact_key, compact=True):
                    if not stable_mode:
                        auto.press_key_up("w")
                    if korean:
                        frame = self.korean_frame()
                        door = frame.find("world_door") and frame.stage()
                    else:
                        door = auto.find_element("./assets/images/screen/divergent_universe/door.png", "image", 0.9, crop=door_crop)

                    if door:
                        for _ in range(1 if korean else 5):
                            auto.press_key(interact_key)
                        time.sleep(2)
                        if self.stage_visible():
                            return False
                        self.stage_finish = True
                        log.info("成功进入随意门")
                        return True
                    if not stable_mode:
                        auto.press_key_down("w")
                        time.sleep(0.5)

                # 检测随意门位置，细微调整方向
                result = self.detect_random_door()
                if not result:
                    return False
                top_left, bottom_right = result
                door_center_x = (top_left[0] + bottom_right[0]) // 2
                offset = door_center_x - screen_center_x

                if abs(offset) > fine_tolerance:
                    adjust_key = "a" if offset < 0 else "d"
                    if stable_mode:
                        auto.press_key_down("w")
                    try:
                        auto.press_key(adjust_key, wait_time=0.15)
                    finally:
                        if stable_mode:
                            auto.press_key_up("w")
                else:
                    if stable_mode:
                        auto.press_key("w")
        finally:
            if not stable_mode:
                auto.press_key_up("w")
                # auto.press_key_up("shift")
        return False

    def check_title(self, frame=None):
        korean = du.game_language(cfg) == "ko_KR"
        if korean:
            frame = frame or self.korean_frame()
            found = frame.find("title")
            if not found and frame.is_event():
                found = ("event", None)
        else:
            found = du.find_text(auto, cfg, "title")
        if not found:
            if korean:
                self._korean_selection = None
            return False

        title, _ = found
        if korean:
            self.process_korean_title(title, frame)
            return True
        log.info(f"检测到差分宇宙界面：{title}")
        handlers = {
            "mask": self.process_mask,
            "equation": self.process_equation,
            "blessing": self.process_blessing,
            "curio": self.process_relic_selection,
            "discard_curio": self.process_relic_discard,
            "destroy_curio": self.process_relic_destroy,
            "wish": self.process_wish,
            "next_station": self.process_next_station,
            "event": self.process_event,
            "station_card": self.process_station_card,
            "save": self.process_save_management,
            "chaos_box": self.process_chaos_box,
            "talent": self.process_talent_management,
        }
        advances_stage = title in ("next_station", "station_card")
        if advances_stage:
            self.stage_finish = True
        handlers[title]()
        return True

    def process_korean_title(self, title, frame):
        now = time.monotonic()
        if self._korean_selection is None or self._korean_selection[0] != title:
            self._korean_selection = title, now
            log.info(f"차분화 우주 선택 화면 {title}")
        elif now - self._korean_selection[1] > 45:
            raise RuntimeError(f"선택 화면에서 진행하지 못했습니다 ({title}).")

        if title == "mask":
            mask = frame.find("mask_action", "choose_mask")
            if mask:
                names = [(box, text) for box, (text, score) in frame.in_area(du.n150_area(85, 355, 255, 340))
                         if du.compact(text).endswith("가면") and score >= du.MIN_CONFIDENCE]
                if names:
                    auto.click_element_with_pos(auto.calculate_text_position(names[0][0], relative=False))
                else:
                    auto.click_element_with_pos(mask[1])
            return

        if title in {"shop", "workbench"}:
            auto.press_key("esc")
            return

        if title == "event":
            self.process_korean_event(frame)
            return

        if title == "next_station":
            self.process_korean_station(frame)
            return

        confirm = {
            "equation": "equation_confirm", "blessing": "blessing_confirm",
            "curio": "curio_confirm", "wish": "wish_confirm", "station_card": "card_confirm",
        }.get(title)
        if confirm is None:
            raise RuntimeError(f"지원하지 않는 선택 화면입니다 ({title}).")
        if title == "station_card":
            if not frame.find("card_upgrade"):
                return
            choice = du.n150_area(62, 166, 95, 80)
        else:
            # The first card occupies this strip in both the 2- and 3-card layouts.
            choice = du.n150_area(295, 305, 70, 112)
        if frame.find(confirm, "confirm") and auto.click_element(choice, "crop", take_screenshot=False):
            time.sleep(0.8)
            du.click_text(auto, cfg, confirm, "confirm")

    def process_korean_station(self, frame):
        priorities = {"boss": 0, "rest": 0, "battle": 1, "elite": 1, "reward": 2, "event": 2,
                      "forge": 3, "shop": 3, "wealth": 3, "abnormal": 3, "blank": 3}
        if cfg.divergent_station_priority_enable:
            for station, name in du.STATION_BY_ID.items():
                if name in cfg.divergent_station_disabled:
                    priorities[station] = 99
                elif name in cfg.divergent_station_priority:
                    priorities[station] = cfg.divergent_station_priority[name]

        stations = [frame.find(f"station_{index}") for index in range(1, 4)]
        choices = [station for station in stations if station and du.stage_route(station[0]) != "unsupported"]
        if choices:
            station, pos = min(choices, key=lambda choice: priorities.get(choice[0], 100))
            if not auto.click_element_with_pos(pos):
                return
        elif auto.click_element("./assets/images/screen/divergent_universe/ko_boss_card.png", "image",
                                0.87, crop=du.n150_area(460, 335, 105, 122), scale_range=(0.8, 1.2)):
            station = "boss"
        else:
            return
        time.sleep(0.8)
        if du.click_text(auto, cfg, "station_confirm", "confirm"):
            log.info(f"다음 행선지 선택 {station}")

    def process_korean_event(self, frame):
        for action in ("select", "confirm"):
            button = frame.find("event_confirm", action)
            if button:
                auto.click_element_with_pos(button[1])
                return
        right_panel = du.n150_area(679, 69, 332, 659)
        for icon in ("event_next", "event_choose", "event_leave"):
            if auto.click_element(f"./assets/images/screen/divergent_universe/{icon}.png",
                                  "image", 0.9, crop=right_panel, scale_range=(0.55, 1)):
                return
        candidates = auto.find_element("./assets/images/screen/divergent_universe/event_option.png",
                                       "image_with_multiple_targets", 0.9, crop=right_panel)
        if not candidates:
            candidates = auto.find_element("./assets/images/screen/divergent_universe/event_option.png",
                                           "image_with_multiple_targets", 0.9, crop=right_panel, scale_range=0.6)
        if candidates:
            auto.click_element_with_pos(max(candidates, key=lambda box: box[0][1]))

    def process_mask(self):
        """
        处理欢愉假面界面：默认选择中间的面具"""
        mask_crop = (396 / 1920, 519 / 1080, 172 / 1920, 485 / 1080)
        mask_positions = [
            (408 / 1920, 529 / 1080, 147 / 1920, 48 / 1080),
            (411 / 1920, 713 / 1080, 144 / 1920, 50 / 1080),
            (413 / 1920, 900 / 1080, 142 / 1920, 51 / 1080),
        ]
        mask_names = []
        found = du.find_text(auto, cfg, "mask_action")
        if found and auto.click_element_with_pos(found[1]):
            if found[0] == "choose_mask":
                if auto.find_element("面具", "text", crop=mask_crop, include=True):
                    for box in auto.ocr_result:
                        text = box[1][0]
                        if text.endswith("面具") and len(text) > 2:
                            log.info(f"检测到面具：{text}")
                            mask_names.append(text)
                    if any(mask_names):
                        for name in mask_names:
                            log.info(f"尝试选择面具：{name}")
                            if auto.click_element(name, "text", crop=mask_crop, include=True):
                                time.sleep(2)
                                return

                # for i, pos in enumerate(mask_positions):
                #     result = auto.get_single_line_text(crop=pos)
                #     if result and result.endswith("面具") and len(result) > 2:
                #         log.info(f"检测到第 {i + 1} 张面具：{result}")
                #         has_mask[i] = True

                # if any(has_mask):
                #     for i, has in enumerate(has_mask):
                #         if has:
                #             log.info(f"尝试选择第 {i + 1} 张面具")
                #             auto.click_element(mask_positions[i], 'crop')
                #             time.sleep(2)
                #             return

                log.info("默认选择中间的面具")
                auto.click_element(mask_positions[1], 'crop')
                time.sleep(2)

    def process_talent_management(self):
        """
        处理人才管理阶段界面：默认选择中间的区域卡片并确认
        """
        card_positions = [
            (570 / 1920, 200 / 1080, 252 / 1920, 520 / 1080),
            (835 / 1920, 200 / 1080, 251 / 1920, 520 / 1080),
            (1097 / 1920, 200 / 1080, 252 / 1920, 520 / 1080),
        ]
        confirm_crop = (551 / 1920, 942 / 1080, 805 / 1920, 62 / 1080)

        time.sleep(2)
        log.info("默认选择中间的区域卡片")
        auto.click_element(card_positions[1], 'crop')
        time.sleep(1)
        auto.click_element('确认', 'text', None, 10, crop=confirm_crop, include=True)
        time.sleep(2)

    def process_equation(self):
        """
        处理选择方程界面：优先选择未收集的方程或已展开的方程
        """
        equation_positions = [
            (281 / 1920, 244 / 1080, 417 / 1920, 607 / 1080),
            (753 / 1920, 243 / 1080, 418 / 1920, 609 / 1080),
            (1222 / 1920, 243 / 1080, 418 / 1920, 606 / 1080),
        ]

        has_choose = False

        time.sleep(2)
        # if auto.click_element(("繁育", "巡猎"), "text", 0.9, crop=(274 / 1920, 790 / 1080, 1371 / 1920, 59 / 1080), include=True):
        #     log.info(f"检测到“{auto.matched_text}”选项，尝试点击")
        #     has_choose = True

        # if not has_choose:
        #     if auto.click_element(("欢愉", "智识"), "text", 0.9, crop=(274 / 1920, 790 / 1080, 1371 / 1920, 59 / 1080), include=True):
        #         log.info(f"检测到“{auto.matched_text}”选项，尝试点击")
        #         has_choose = True

        if not has_choose:
            for pos in equation_positions:
                if auto.click_element("./assets/images/screen/divergent_universe/new_equation.png", "image", 0.9, crop=pos):
                    log.info("检测到 “图鉴未收集” 选项，尝试点击")
                    has_choose = True
                    break

        if not has_choose:
            for pos in equation_positions:
                if auto.click_element("已展开", "text", crop=pos):
                    log.info("检测到 “已展开” 选项，尝试点击")
                    has_choose = True
                    break

        if not has_choose:
            log.info("未检测到优先可选项，默认选择中间的方程")
            auto.click_element(equation_positions[1], 'crop')
            has_choose = True

        time.sleep(1)
        du.click_text(auto, cfg, "equation_confirm", "confirm", max_retries=10)
        time.sleep(2)

    def process_blessing(self):
        """
        处理选择祝福界面：优先选择未收集的祝福或建议选项
        """
        blessing_positions = [
            (280 / 1920, 241 / 1080, 409 / 1920, 611 / 1080),
            (758 / 1920, 242 / 1080, 407 / 1920, 608 / 1080),
            (1236 / 1920, 242 / 1080, 409 / 1920, 610 / 1080),
        ]

        blessing2_positions = [
            (519 / 1920, 241 / 1080, 408 / 1920, 610 / 1080),
            (999 / 1920, 242 / 1080, 405 / 1920, 609 / 1080),
        ]

        has_choose = False

        time.sleep(2)
        # if auto.click_element(("繁育", "巡猎"), "text", 0.9, crop=(274 / 1920, 790 / 1080, 1371 / 1920, 59 / 1080), include=True):
        #     log.info(f"检测到“{auto.matched_text}”选项，尝试点击")
        #     has_choose = True

        # if not has_choose:
        #     if auto.click_element(("欢愉", "智识"), "text", 0.9, crop=(274 / 1920, 790 / 1080, 1371 / 1920, 59 / 1080), include=True):
        #         log.info(f"检测到“{auto.matched_text}”选项，尝试点击")
        #         has_choose = True

        if not has_choose:
            for pos in blessing_positions:
                if auto.click_element("./assets/images/screen/divergent_universe/new_blessing.png", "image", 0.9, crop=pos,):
                    log.info("检测到 “图鉴未收集” 选项，尝试点击")
                    has_choose = True
                    break

        if not has_choose:
            for pos in blessing_positions:
                if auto.click_element("./assets/images/screen/divergent_universe/rec_blessing.png", "image", 0.9, crop=pos):
                    log.info("检测到建议选项，尝试点击")
                    has_choose = True
                    break

        if not has_choose:
            log.info("未检测到优先可选项，默认选择中间的祝福")
            auto.click_element(blessing2_positions[0], 'crop')
            auto.click_element(blessing_positions[1], 'crop')
            has_choose = True

        time.sleep(1)
        du.click_text(auto, cfg, "blessing_confirm", "confirm", max_retries=10)
        time.sleep(2)

    def process_relic_selection(self):
        """
        处理选择奇物界面：优先选择未收集的奇物或建议选项
        """
        relic_positions = [
            (281 / 1920, 242 / 1080, 407 / 1920, 610 / 1080),
            (757 / 1920, 242 / 1080, 410 / 1920, 610 / 1080),
            (1235 / 1920, 242 / 1080, 410 / 1920, 610 / 1080),
        ]
        relic2_positions = [
            (517 / 1920, 242 / 1080, 409 / 1920, 610 / 1080),
            (997 / 1920, 241 / 1080, 405 / 1920, 609 / 1080)
        ]

        time.sleep(2)
        has_choose = False

        for pos in relic_positions:
            if auto.click_element("./assets/images/screen/divergent_universe/new_relic.png", "image", 0.9, crop=pos):
                log.info("检测到 “图鉴未收集” 选项，尝试点击")
                has_choose = True
                break

        if not has_choose:
            log.info("未检测到优先可选项，默认选择中间的奇物")
            auto.click_element(relic2_positions[0], 'crop')
            auto.click_element(relic_positions[1], 'crop')
            has_choose = True

        time.sleep(1)
        du.click_text(auto, cfg, "curio_confirm", "confirm", max_retries=10)
        time.sleep(2)

    def process_relic_discard(self):
        """
        处理丢弃奇物界面：默认选择中间的奇物进行丢弃
        """
        relic_positions = [
            (281 / 1920, 242 / 1080, 407 / 1920, 610 / 1080),
            (757 / 1920, 242 / 1080, 410 / 1920, 610 / 1080),
            (1235 / 1920, 242 / 1080, 410 / 1920, 610 / 1080),
        ]
        relic2_positions = [
            (517 / 1920, 242 / 1080, 409 / 1920, 610 / 1080),
            (997 / 1920, 241 / 1080, 405 / 1920, 609 / 1080)
        ]

        log.info("尝试丢弃中间的奇物")
        auto.click_element(relic2_positions[0], 'crop')
        auto.click_element(relic_positions[1], 'crop')
        time.sleep(1)
        du.click_text(auto, cfg, "discard_confirm", "discard", max_retries=10)
        time.sleep(2)

    def process_relic_destroy(self):
        """处理奇物损毁；只在标题、说明与按钮均符合时选择卡片。"""
        title_crop = (96 / 1920, 63 / 1080, 142 / 1920, 34 / 1080)
        prompt_crop = (520 / 1920, 118 / 1080, 880 / 1920, 65 / 1080)
        button_crop = (1540 / 1920, 934 / 1080, 345 / 1920, 75 / 1080)
        if not auto.find_element("奇物损毁", "text", crop=title_crop, include=False):
            raise RuntimeError("奇物损毁标题已变化，停止点击")
        if not auto.find_element("请选择要摧毁的奇物", "text", crop=prompt_crop, include=False):
            raise RuntimeError("奇物损毁说明未识别，停止点击")
        if not auto.find_element("摧毁", "text", crop=button_crop, include=False):
            raise RuntimeError("奇物损毁按钮未识别，停止点击")

        # 沿用选择/丢弃奇物的方式，先点双选项左侧，再点单/三选项中间。
        # 不用卡名 OCR 判断布局，避免读到相邻卡名后只点击中间空白。
        relic_positions = (
            (517 / 1920, 242 / 1080, 409 / 1920, 610 / 1080),
            (757 / 1920, 242 / 1080, 410 / 1920, 610 / 1080),
        )
        log.info("奇物损毁：尝试选择奇物")
        for pos in relic_positions:
            if not auto.click_element(pos, "crop"):
                raise RuntimeError("奇物损毁卡片点击失败")

        time.sleep(0.5)
        if not auto.click_element("摧毁", "text", max_retries=3, crop=button_crop, include=False):
            raise RuntimeError("奇物损毁：点击摧毁失败")
        # 点击成功不等于处理成功。连续两次确认标题与说明消失，
        # 若按钮未生效或出现未支持弹窗，则明确停止并由顶层保存截图。
        absent_frames = 0
        for _ in range(10):
            time.sleep(1)
            still_title = auto.find_element("奇物损毁", "text", crop=title_crop, include=False)
            still_prompt = auto.find_element("请选择要摧毁的奇物", "text", crop=prompt_crop, include=False)
            absent_frames = 0 if still_title or still_prompt else absent_frames + 1
            if absent_frames >= 2:
                log.info("奇物损毁处理完成，已离开选择界面")
                return
        raise RuntimeError("奇物损毁：点击后界面未退出，停止任务并保留现场")

    def process_wish(self):
        """
        处理愿力满盈界面：优先选择未收集的奇迹或建议选项
        """
        wish_positions = [
            (268 / 1920, 244 / 1080, 406 / 1920, 627 / 1080),
            (756 / 1920, 245 / 1080, 408 / 1920, 624 / 1080),
            (1246 / 1920, 245 / 1080, 406 / 1920, 623 / 1080),
        ]
        wish2_positions = [
            (519 / 1920, 257 / 1080, 392 / 1920, 599 / 1080),
            (1008 / 1920, 258 / 1080, 392 / 1920, 598 / 1080),
        ]

        has_choose = False

        time.sleep(2)
        for pos in wish_positions:
            if auto.click_element("./assets/images/screen/divergent_universe/new_wish.png", "image", 0.9, crop=pos):
                log.info("检测到 “图鉴未收集” 选项，尝试点击")
                has_choose = True
                break

        if not has_choose:
            log.info("未检测到优先可选项，默认选择中间的奇迹")
            auto.click_element(wish2_positions[0], 'crop')
            auto.click_element(wish_positions[1], 'crop')
            has_choose = True

        time.sleep(1)
        auto.click_element('确认', 'text', None, 10, crop=(551 / 1920, 942 / 1080, 805 / 1920, 62 / 1080), include=True)
        time.sleep(2)

    def process_next_station(self):
        korean = du.game_language(cfg) == "ko_KR"
        re_extract_crop = (560 / 1920, 940 / 1080, 374 / 1920, 56 / 1080)

        for _ in range(5):
            time.sleep(2)
            has_priority_station = False

            station_tags = []
            for index in range(1, len(du.STATION_AREAS) + 1):
                found = du.find_text(auto, cfg, f"station_{index}")
                station_tags.append(found[0] if found else None)

            log.debug(f"站点卡标签: {station_tags}")

            if not any(station_tags):
                return

            # 优先级相同时沿用从左到右的选择顺序。
            priority_map = {"boss": 0, "rest": 0, "conversion": 0}
            disabled_stations = set()

            if cfg.divergent_station_priority_enable:
                custom_priority = cfg.divergent_station_priority
                for station_id, name in du.STATION_BY_ID.items():
                    if name in custom_priority:
                        priority_map[station_id] = custom_priority[name]
                    if name in cfg.divergent_station_disabled:
                        disabled_stations.add(station_id)
            else:
                priority_map.update({
                    "battle": 1, "elite": 1, "event": 2, "reward": 2,
                    "abnormal": 2, "forge": 2, "blank": 3, "shop": 3, "wealth": 3,
                })

            # 未识别的站点不参与选择。
            # 禁用的站点优先级设为极高值（仅在没有重抽次数时才会被选择）
            station_priorities = []
            for tag in station_tags:
                if tag is None:
                    station_priorities.append(float('inf'))
                elif tag in disabled_stations:
                    station_priorities.append(99)
                else:
                    if tag in priority_map:
                        has_priority_station = True
                    station_priorities.append(priority_map.get(tag, 100))

            if not has_priority_station and not korean:
                if not auto.find_element("重抽0", "text", crop=re_extract_crop) and not auto.find_element("0", "text", crop=re_extract_crop):
                    auto.click_element(re_extract_crop, 'crop')
                    time.sleep(0.5)
                    if auto.find_element("当前无法重抽", "text", crop=(880 / 1920, 282 / 1080, 157 / 1920, 38 / 1080)):
                        break
                    time.sleep(1)
                    auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9)
                    continue
            break

        selected_index = station_priorities.index(min(station_priorities))
        station = station_tags[selected_index]
        selected = du.click_text(auto, cfg, f"station_{selected_index + 1}", station, max_retries=10)
        if korean and not selected:
            return False
        log.info(f"选择 “{du.STATION_BY_ID[station]}” 站点卡")

        time.sleep(1)
        confirmed = du.click_text(auto, cfg, "station_confirm", "confirm", max_retries=10)
        if korean and not confirmed:
            return False
        time.sleep(2)

        # 4.5 版本新更新的 “贪吃面具” 会在此处弹窗 “本次为最后一次区域选择阶段，之后将无法再进入储蓄间，是否继续？”
        if auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9):
            time.sleep(2)
        return confirmed

    @staticmethod
    def reveal_event_confirm():
        max_drags = 2
        for attempt in range(max_drags + 1):
            # 与后续点击使用相同的识别范围和包含匹配，兼容按钮位置变化及 OCR 合并文字。
            if auto.find_element("确定", "text", max_retries=2, retry_delay=0.5, include=True):
                return True
            if attempt == max_drags:
                break
            # 事件背景和选中框有动画。松手前停顿消除惯性，再重新识别按钮，
            # 避免把背景持续变化误判为列表还在移动。
            if not auto.drag_mouse((1805 / 1920, 820 / 1080), (1805 / 1920, 320 / 1080),
                                   duration=1.2, end_pause=0.25):
                auto.take_screenshot()
                raise RuntimeError("差分宇宙事件选项拖动中断，停止处理")
            time.sleep(1)
        return False

    @staticmethod
    def confirm_event_option():
        # OCR 能识别灰色按钮，输入成功也不代表选项满足条件。
        # 只比较右侧选项内容，排除左侧背景装饰字符的 OCR 波动。
        options_left = auto.screenshot.width * 1320 / 1920
        before = [text for box, (text, _) in auto.ocr_result if box[0][0] >= options_left]
        if not auto.click_element("确定", "text", None, 4, include=True):
            raise RuntimeError("差分宇宙事件确定按钮点击失败")
        absent_frames = 0
        for _ in range(4):
            time.sleep(0.5)
            if not auto.find_element("确定", "text", include=True):
                absent_frames += 1
                if absent_frames >= 2:
                    return True
            else:
                absent_frames = 0
                # 连续事件可能沿用相同布局，内容变化也表示已进入下一页。
                after = [text for box, (text, _) in auto.ocr_result if box[0][0] >= options_left]
                if after != before:
                    return True
        return False

    def process_event(self):
        start_time = time.monotonic()
        while time.monotonic() - start_time < 120:
            time.sleep(1)
            if auto.click_element("./assets/images/screen/divergent_universe/event_next.png", "image", 0.9):
                continue
            if auto.click_element("./assets/images/screen/divergent_universe/event_choose.png", "image", 0.9):
                continue
            if auto.click_element("./assets/images/screen/divergent_universe/event_leave.png", "image", 0.9):
                continue

            matchs = auto.find_element("./assets/images/screen/divergent_universe/event_option.png", "image_with_multiple_targets", 0.9)
            if not matchs:
                return
            # 重入时优先完成已有选择，避免再次点击选项而切换或取消选中态。
            if auto.find_element("确定", "text", include=True) and self.confirm_event_option():
                continue

            has_confirm = False
            for attempt in range(10):
                # 展开选项、确认和拖动都会改变位置，每次选择前都重新定位。
                matchs = auto.find_element("./assets/images/screen/divergent_universe/event_option.png", "image_with_multiple_targets", 0.9)
                if not matchs:
                    break
                # 首次失败后的拖动可能露出新的末项，从当前末项重新向上尝试。
                option_index = len(matchs) - max(1, attempt)
                if option_index < 0:
                    break
                if not auto.click_element_with_pos(matchs[option_index]):
                    raise RuntimeError("差分宇宙事件选项点击失败")
                time.sleep(0.5)
                if not self.reveal_event_confirm():
                    continue
                time.sleep(0.5)
                if self.confirm_event_option():
                    has_confirm = True
                    break
            if has_confirm:
                continue
            raise RuntimeError("差分宇宙事件选项无法确认，停止处理")
        raise RuntimeError("差分宇宙事件处理超时（120秒），停止处理")

    def process_station_card(self):
        if auto.find_element(("删除", "使其变为【空白】区域"), "text", crop=(110 / 1920, 136 / 1080, 1226 / 1920, 48 / 1080), include=True):
            auto.click_element(("冒险", "铸造"), "text", crop=(59 / 1920, 243 / 1080, 1262 / 1920, 786 / 1080), include=True)
        auto.click_element('确定', 'text', None, 10, crop=(1589 / 1920, 919 / 1080, 73 / 1920, 38 / 1080), include=True)
        time.sleep(2)

    def process_save_management(self, save_current_run: bool = False) -> bool:
        # check_title 也会调用此函数；只有从探索成功结果页进入时才执行保存。
        if not save_current_run:
            time.sleep(2)
            return False

        slot_ys = (240, 372, 503, 634)
        empty_icon = "./assets/images/screen/divergent_universe/empty_save_slot.png"

        for index, y in enumerate(slot_ys):
            slot_crop = (150 / 1920, (y - 20) / 1080, 70 / 1920, 40 / 1080)
            if not auto.click_element(slot_crop, "crop"):
                log.warning(f"无法点击第 {index + 1} 个存档位，跳过存档")
                return False
            time.sleep(0.7)

            # 左侧被选中的槽位底色更亮。先确认切换成功，避免把前一槽位误判为空槽。
            auto.take_screenshot()
            image = auto.screenshot.convert("RGB")
            sample_x = round(100 * image.width / 1920)
            brightness = []
            for slot_y in slot_ys:
                sample_y = round(slot_y * image.height / 1080)
                brightness.append(sum(image.getpixel((sample_x, sample_y))) / 3)
            other_brightness = max(value for other_index, value in enumerate(brightness) if other_index != index)
            if brightness[index] < other_brightness + 50:
                log.warning(f"无法确认第 {index + 1} 个存档位已选中，跳过存档")
                return False

            if auto.find_element(
                empty_icon,
                "image",
                0.9,
                crop=(1000 / 1920, 420 / 1080, 230 / 1920, 160 / 1080),
            ):
                log.info(f"找到第 {index + 1} 个空存档位")
                break
        else:
            log.info("四个存档位都未确认为空，跳过本轮存档")
            return False

        if not auto.click_element(
            "保存本轮数据",
            "text",
            max_retries=3,
            crop=(900 / 1920, 690 / 1080, 430 / 1920, 100 / 1080),
            include=True,
        ):
            log.warning("未找到“保存本轮数据”按钮")
            return False

        if not auto.find_element(
            "更改存档名",
            "text",
            max_retries=8,
            crop=(850 / 1920, 380 / 1080, 220 / 1920, 80 / 1080),
            include=True,
        ):
            log.warning("未出现更改存档名窗口")
            return False

        # 保留游戏给出的默认名称。
        if not auto.click_element(
            "确认",
            "text",
            max_retries=3,
            crop=(985 / 1920, 630 / 1080, 380 / 1920, 90 / 1080),
            include=False,
        ):
            log.warning("未找到存档确认按钮")
            return False

        if not auto.find_element(
            ("本轮存档", "本局已存档"),
            "text",
            max_retries=8,
            crop=(900 / 1920, 900 / 1080, 1000 / 1920, 140 / 1080),
            include=True,
        ):
            log.warning("点击确认后，未能确认存档完成")
            return False

        log.info("本轮差分宇宙已存档")
        return True

    def _save_completed_run(self) -> bool:
        opened_save_management = False
        try:
            if not auto.click_element(
                "记录本次存档",
                "text",
                max_retries=3,
                crop=(980 / 1920, 935 / 1080, 400 / 1920, 90 / 1080),
                include=True,
            ):
                log.warning("未找到“记录本次存档”按钮")
                return False
            opened_save_management = True

            if not auto.find_element(
                "存档管理",
                "text",
                max_retries=10,
                crop=(96 / 1920, 63 / 1080, 142 / 1920, 34 / 1080),
                include=True,
            ):
                log.warning("点击记录存档后，未进入存档管理")
                return False

            return self.process_save_management(save_current_run=True)
        except Exception as exc:
            log.error(f"自动记录差分宇宙存档失败：{exc}")
            return False
        finally:
            if opened_save_management:
                for _ in range(3):
                    if auto.find_element(
                        "返回主界面",
                        "text",
                        crop=(573 / 1920, 947 / 1080, 792 / 1920, 85 / 1080),
                        include=True,
                    ):
                        break
                    if not (
                        auto.find_element("存档管理", "text", crop=(96 / 1920, 63 / 1080, 142 / 1920, 34 / 1080), include=True)
                        or auto.find_element("更改存档名", "text", crop=(850 / 1920, 380 / 1080, 220 / 1920, 80 / 1080), include=True)
                    ):
                        log.warning("无法确认当前界面，停止自动关闭存档管理")
                        break
                    auto.press_key("esc")
                    time.sleep(1)

    def process_chaos_box(self):
        time.sleep(2)
        if not auto.click_element('获得', 'text', None, 10, crop=(1105 / 1920, 94 / 1080, 702 / 1920, 858 / 1080), include=True):
            auto.click_element('离开', 'text', None, 10, crop=(1105 / 1920, 94 / 1080, 702 / 1920, 858 / 1080), include=False)
        time.sleep(1)
        auto.click_element('确定', 'text', None, 10, crop=(1105 / 1920, 94 / 1080, 702 / 1920, 858 / 1080), include=False)
        time.sleep(2)

    def check_auto_battle(self):
        """
        检查并开启自动战斗
        """
        scales = (0.55, 1.1) if du.game_language(cfg) == "ko_KR" else None
        if game_option_enabled(cfg, "auto_battle_detect_enable") and auto.find_element("./assets/images/share/base/not_auto.png", "image", 0.9, crop=(0.0 / 1920, 903.0 / 1080, 144.0 / 1920, 120.0 / 1080), scale_range=scales):
            log.info("尝试开启自动战斗")
            auto.press_key(cfg.get_game_hotkey("hotkey_auto_battle", "v"))
            return True
        return False

    def check_click_close(self, frame=None):
        """
        检查并点击 “点击空白处关闭” 或 “点击领取今日补给” 的按钮
        """
        if du.game_language(cfg) == "ko_KR":
            found = (frame or self.korean_frame()).find("close_popup")
            return bool(found and auto.click_element_with_pos(found[1]))
        if auto.click_element(("点击空白处关闭", "点击领取今日补给"), 'text', None, crop=(816 / 1920, 778 / 1080, 284 / 1920, 298 / 1080), include=True):
            log.info(f"检测到 “{auto.matched_text}” 的按钮，尝试点击")
            return True
        return False

    def finish_korean_run(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            frame = self.korean_frame()
            if frame.find("lobby_start") or frame.find("mode_page"):
                if self.result is True:
                    self.record_completed_run()
                return self.result is True
            time.sleep(1)
        raise RuntimeError("정산 후 차분화 우주 화면으로 돌아오지 못했습니다.")

    def check_korean_settlement(self, frame):
        result = frame.find("settlement_result")
        button = frame.find("settlement_action", "return_main")
        if not button or not frame.is_report():
            return False
        self.result = result[0] == "success" if result else None
        self.screenshot = auto.screenshot
        if self.result is None:
            from module.automation.automation import screenshot_retry_timeout
            from utils.screenshot_util import save_error_screenshot

            log.warning("정산 화면에 도착했습니다. 탐사 성공 여부를 확인할 수 없어 완료 횟수를 기록하지 않습니다.")
            with screenshot_retry_timeout(0):
                save_error_screenshot(log)
        if not auto.click_element_with_pos(button[1]):
            raise RuntimeError("정산 화면의 메인 화면으로 돌아가기 버튼을 클릭하지 못했습니다.")
        if self.result is not None:
            log.info("탐사 성공 확인" if self.result else "탐사 중단 확인")
        return True

    def check_click_return(self):
        """
        检查并点击 “终止战斗并结算” 和 “返回主界面” 的按钮
        """
        found = du.find_text(auto, cfg, "settlement_action")
        if found:
            action, result = found
            if action == "abort_battle":
                log.info(f"检测到 “终止战斗并结算” 的按钮，尝试点击")
                auto.click_element_with_pos(result)
                time.sleep(2)
                if not auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9, max_retries=10):
                    auto.press_key("esc")
                return True

            elif action == "return_main":
                log.info(f"检测到 “返回主界面” 的按钮，尝试点击")
                self._check_battle_result()
                if self.result is True and cfg.get_value("divergent_auto_save_enable", True) and not self._save_attempted:
                    self._save_attempted = True
                    self._save_completed_run()
                    found = du.find_text(auto, cfg, "settlement_action", only="return_main", max_retries=3)
                    if not found:
                        log.warning("存档流程后未找到“返回主界面”，等待下一轮界面识别")
                        return True
                    result = found[1]
                time.sleep(2)
                if du.game_language(cfg) == "ko_KR":
                    if not du.click_text(auto, cfg, "settlement_action", "return_main"):
                        return False
                else:
                    auto.click_element_with_pos(result)
                if self.result is not None:
                    log.info(f"本次对局结果：{'成功' if self.result else '失败'}")
                else:
                    log.info("本次对局结果：未知")
                self.end_loop = True

                time.sleep(2)
                for _ in range(30):
                    if du.click_text(auto, cfg, "settlement_action", "return_main"):
                        log.info(f"检测到 “返回主界面” 的按钮，尝试点击")
                        time.sleep(2)
                    else:
                        break
                else:
                    log.warning("多次点击返回主界面失败，请确认是否已成功返回主界面")

                # 没有存档会显示一个弹窗，需要点击确认
                auto.click_element("./assets/images/zh_CN/base/confirm.png", "image", 0.9)

            elif action == "confirm_settlement":
                log.info(f"检测到 “确认结算” 的按钮，尝试点击")
                auto.click_element_with_pos(result)
                return True

        return False

    def _check_battle_result(self):
        """
        检查并记录对局结果
        """
        time.sleep(2)  # 等待分析报告加载完成后再截图
        found = du.find_text(auto, cfg, "settlement_result")
        if found:
            self.result = found[0] == "success"
            self.screenshot = auto.screenshot
        elif du.game_language(cfg) == "ko_KR":
            self.result = None
            self.screenshot = None
