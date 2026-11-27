import sys

import pytest
from PySide6.QtCore import QBoxLayout, QPoint


@pytest.mark.skipif(sys.platform != "win32", reason="原生设置界面仅在 Windows 验证")
def test_narrow_task_page_keeps_run_button_in_view(qtbot, page_config, content_window):
    from app.task_interface import TaskInterface

    page_config("{}\n")
    interface = TaskInterface(content_window)
    qtbot.addWidget(interface)
    content_window.resize(820, 740)
    interface.resize(content_window.size())
    content_window.show()
    interface.show()
    assert interface.showTask("universe")

    assert interface.body.direction() == QBoxLayout.Direction.TopToBottom
    page = interface.pages["universe"]
    button = page.header.runButton

    def assert_run_button_fits():
        top_left = button.mapTo(page.viewport(), QPoint(0, 0))
        assert top_left.x() >= 0
        assert top_left.x() + button.width() <= page.viewport().width()
        assert top_left.y() >= 0
        assert top_left.y() + button.height() <= page.viewport().height()

    qtbot.waitUntil(assert_run_button_fits)
    content_window.resize(1200, 800)
    interface.resize(content_window.size())
    assert interface.body.direction() == QBoxLayout.Direction.LeftToRight
    assert interface.currentTask() == "universe"
