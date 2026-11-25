"""工具箱：分组卡片，每张卡一个工具。"""
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, FluentIcon as FIF, InfoBar, InfoBarPosition, MessageBox, PushButton, ScrollArea,
                            TitleLabel, qconfig)

import tasks.tool as tool
from app.tools.adb_service import display_connection
from module.config import cfg
from module.localization import tr
from tasks.base.tasks import start_task
from utils.desktop_twin import in_desktop_twin
from utils.tasks import task_is_supported
from .common.icon import UiIcon
from .overview.widgets import Pill
from .pages.common import is_evernight, secondary
from .toolbox.autoplot import AutoPlotCard
from .toolbox.cards import ScreenshotCard, ToolCard, ToolGrid
from .toolbox.redemption import RedemptionCodeCard


class ToolsInterface(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.setObjectName('toolsInterface')
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName("view")
        self.scrollWidget.setStyleSheet("#view{background: transparent}")
        self.setWidget(self.scrollWidget)

        self.toolsLabel = TitleLabel(self.scrollWidget)
        self.subtitleLabel = secondary(BodyLabel(self.scrollWidget))
        self.automaticPlotCard = AutoPlotCard(FIF.CHAT, self.scrollWidget)
        self.gameScreenshotCard = ScreenshotCard(FIF.CAMERA, self.scrollWidget)
        self.screenTestCard = ToolCard(UiIcon.BEAKER, self.scrollWidget)
        self.redemptionCodeCard = RedemptionCodeCard(UiIcon.TICKET, self)
        self.characterExportCard = ToolCard(FIF.PEOPLE, self.scrollWidget)
        self.desktopTwinCard = ToolCard(FIF.APPLICATION, self.scrollWidget)
        self.twinPill = Pill(self.desktopTwinCard)
        self.desktopTwinCard.head.addWidget(self.twinPill)
        self._desktop_twin = None
        self._desktop_twin_hosting = False

        self.grid = ToolGrid(self.scrollWidget)
        self.groupLabels = (
            self.grid.addGroup(self.automaticPlotCard),
            self.grid.addGroup(self.gameScreenshotCard, self.screenTestCard),
            self.grid.addGroup(self.redemptionCodeCard, self.characterExportCard),
            self.grid.addGroup(self.desktopTwinCard, beside=True),
        )
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(self.toolsLabel)
        head.addWidget(self.subtitleLabel, 1, Qt.AlignmentFlag.AlignBottom)
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        self.vBoxLayout.setContentsMargins(20, 14, 24, 24)
        self.vBoxLayout.setSpacing(14)
        self.vBoxLayout.addLayout(head)
        self.vBoxLayout.addWidget(self.grid, 1)

        if sys.platform != 'win32':
            for card in (self.automaticPlotCard, self.desktopTwinCard):
                card.setDisabled(True)
        self.gameScreenshotCard.setVisible(True)
        self.desktopTwinCard.setHidden(sys.platform == 'win32' and in_desktop_twin())
        self._setTexts()
        self.__connectSignalToSlot()
        self.refreshBackendTasks()
        qconfig.themeChanged.connect(self._restyle)
        qconfig.themeColorChanged.connect(self._restyle)

        if sys.platform == 'win32' and not self.automaticPlotCard.isHidden() and self.automaticPlotCard.getSwitchState():
            self.__startAutoPlot()

    def locate(self, tool_id):
        from module.tool_catalog import TOOL_BY_ID
        from app.navigation import highlight
        tool = TOOL_BY_ID.get(tool_id)
        card = getattr(self, tool.widget, None) if tool else None
        if card is None or card.isHidden():
            return False
        bar = self.verticalScrollBar()
        center = card.mapTo(self.viewport(), card.rect().center())
        bar.setValue(bar.value() + center.y() - self.viewport().rect().center().y())
        highlight(card)
        return True

    def retranslateUi(self):
        """保留自动对话开关及其运行状态，不再次启动后台工具。"""
        self._setTexts()
        self.automaticPlotCard.retranslateUi()
        if self._desktop_twin is not None:
            self._desktop_twin.retranslateUi()

    def _setTexts(self):
        self.toolsLabel.setText(tr('工具箱'))
        self.subtitleLabel.setText(tr('不参与完整运行，需要时单独打开'))
        for label, text in zip(self.groupLabels, (tr('游戏辅助'), tr('排查'), tr('数据'), tr('高级'))):
            label.setText(text)
        self.automaticPlotCard.setTexts(
            tr('自动对话'), tr('进入剧情页面后自动开始运行，支持大于等于 1920*1080 的 16:9 分辨率，不支持云·星穹铁道'), tr('选项'))
        self.gameScreenshotCard.setTexts(
            tr('游戏截图'), tr('检查程序获取的图像是否正确，支持OCR识别文字（可用于自行排查异常）'), tr('捕获游戏窗口'))
        self.gameScreenshotCard.fileButton.setText(tr('手动选择图片'))
        self.screenTestCard.setTexts(
            tr('界面可切换性测试'), tr('以最短路径遍历所有可达界面，验证界面切换是否正常'), tr('测试'))
        self.redemptionCodeCard.setTexts(
            tr('兑换码'), tr('批量使用兑换码，每行一个，自动过滤空格等无效字符'), tr('执行'))
        self.characterExportCard.setTexts(
            tr('角色面板导出'), tr('读取全部角色的属性、光锥、星魂、技能和遗器，保存到程序目录的 characters.json'), tr('导出'))
        self._refreshDesktopTwinCard()
        self._restyle()

    def _restyle(self, *_):
        evernight = is_evernight()
        self.twinPill.setPill(tr('运行中'), 'success', evernight=evernight)

    def _refreshDesktopTwinCard(self):
        active = self._desktop_twin_hosting
        self.desktopTwinCard.setTexts(
            tr("桌面分身"),
            tr("分身正在运行，打开窗口可查看分身画面或注销分身") if active else tr("在独立的 Windows 桌面中运行小助手和游戏"),
            tr("打开"))
        self.twinPill.setVisible(active)

    def __onGameScreenshotCardClicked(self):
        """从总览的快捷启动打开时，先选择来源：游戏窗口或本地图片。"""
        connection = display_connection(cfg)
        if connection.error or connection.control_backend == "adb":
            self.__openScreenshotFile()
            return

        message_box = MessageBox(tr("截图来源"), tr("请选择截图方式"), self.window())
        message_box.contentLabel.setMinimumWidth(500)

        message_box.yesButton.setText(tr("捕获游戏窗口"))
        message_box.cancelButton.setText(tr("取消"))

        choose_file_button = PushButton(tr("手动选择图片"), message_box)
        message_box.buttonLayout.insertWidget(1, choose_file_button, 1, Qt.AlignmentFlag.AlignVCenter)

        action = {"value": None}

        def _choose_local_file():
            action["value"] = "file"
            message_box.reject()

        choose_file_button.clicked.connect(_choose_local_file)

        accepted = message_box.exec()

        if action["value"] == "file":
            self.__openScreenshotFile()
        elif accepted:
            self.__captureScreenshot()

    def __captureScreenshot(self):
        tool.start("screenshot")

    def __openScreenshotFile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("选择图片"), "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            tool.start_screenshot_from_file(file_path)

    def __connectSignalToSlot(self):
        self.gameScreenshotCard.clicked.connect(self.__onGameScreenshotCardClicked)
        self.gameScreenshotCard.captureClicked.connect(self.__captureScreenshot)
        self.gameScreenshotCard.fileClicked.connect(self.__openScreenshotFile)
        self.automaticPlotCard.switchChanged.connect(self.__onAutoPlotSwitchChanged)
        self.automaticPlotCard.optionsChanged.connect(self.__onAutoPlotOptionsChanged)
        self.screenTestCard.clicked.connect(self.__onScreenTestCardClicked)
        self.characterExportCard.clicked.connect(self.__onCharacterExportCardClicked)
        self.desktopTwinCard.clicked.connect(self.openDesktopTwin)

    def openDesktopTwin(self):
        if sys.platform != "win32" or in_desktop_twin():
            return
        if self._desktop_twin is None:
            from .tools.desktop_twin import DesktopTwinDialog

            self._desktop_twin = DesktopTwinDialog(
                self.window(), self.parent.runController, getattr(self.parent, "checkDesktopTwinReady", None),
            )
            hosting_changed = getattr(self.parent, "setDesktopTwinHosting", None)
            if hosting_changed:
                self._desktop_twin.hostingChanged.connect(hosting_changed)
            self._desktop_twin.destroyed.connect(self._forgetDesktopTwin)
        if self._desktop_twin.isMinimized():
            # 还原到最小化之前的状态，最大化的窗口仍然最大化
            self._desktop_twin.setWindowState(self._desktop_twin.windowState() & ~Qt.WindowState.WindowMinimized)
        self._desktop_twin.show()
        self._desktop_twin.raise_()
        self._desktop_twin.activateWindow()

    def _forgetDesktopTwin(self):
        self._desktop_twin = None

    def desktopTwinActive(self):
        return self._desktop_twin is not None and self._desktop_twin.active

    def closeDesktopTwin(self):
        if self.desktopTwinActive():
            self.openDesktopTwin()
        return self._desktop_twin is None or self._desktop_twin.close()

    def setDesktopTwinHosting(self, active):
        if self._desktop_twin_hosting == active:
            return
        self._desktop_twin_hosting = active
        self._refreshDesktopTwinCard()
        self.automaticPlotCard.setDisabled(active or sys.platform != "win32")
        for card in (self.gameScreenshotCard, self.redemptionCodeCard, self.screenTestCard, self.characterExportCard):
            card.setDisabled(active)
        if active:
            tool.stop_plot()
        elif self.automaticPlotCard.isEnabled() and not self.automaticPlotCard.isHidden() and self.automaticPlotCard.getSwitchState():
            self.__startAutoPlot()

    def refreshBackendTasks(self, *, connection_changed=False):
        connection = display_connection(cfg)
        adb = connection.control_backend == "adb"
        was_hidden = self.automaticPlotCard.isHidden()
        can_run_plot = not adb and connection.error is None
        self.automaticPlotCard.setVisible(can_run_plot)
        self.gameScreenshotCard.setFileOnly(bool(connection.error or adb))
        if not can_run_plot:
            tool.stop_plot()
        elif (sys.platform == "win32" and (was_hidden or connection_changed) and not self._desktop_twin_hosting
              and self.automaticPlotCard.getSwitchState()):
            self.__startAutoPlot()
        self.redemptionCodeCard.setVisible(task_is_supported("redemption", connection))
        self.screenTestCard.setVisible(task_is_supported("screen_test", connection))
        self.characterExportCard.setVisible(task_is_supported("character_export", connection))
        self.grid.arrange()

    def __onScreenTestCardClicked(self):
        start_task("screen_test")

    def __onCharacterExportCardClicked(self):
        start_task("character_export")

    def __onAutoPlotSwitchChanged(self, isChecked: bool):
        """Handle auto plot switch state change"""
        cfg.set_value("autoplot_enable", isChecked and bool(cfg.get_value("autoplot_remember_enable", False)))
        if isChecked:
            self.__startAutoPlot()
            InfoBar.success(
                title=tr('自动对话已启动'),
                content="",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self
            )
        else:
            # Stop auto plot
            tool.stop_plot()
            InfoBar.info(
                title=tr('自动对话已停止'),
                content="",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self
            )

    def __startAutoPlot(self):
        tool.update_plot_options(self.automaticPlotCard.getOptions())
        tool.start("plot")

    def __onAutoPlotOptionsChanged(self, options: dict):
        """Handle auto plot options change"""
        # Update options if auto plot is running
        if self.automaticPlotCard.getSwitchState():
            tool.update_plot_options(options)

    def toggleAutoPlot(self):
        """切换自动对话状态（供全局热键调用）"""
        if self.automaticPlotCard.isHidden() or not self.automaticPlotCard.isEnabled():
            return
        current_state = self.automaticPlotCard.getSwitchState()
        new_state = not current_state
        self.automaticPlotCard.setValue(new_state)
