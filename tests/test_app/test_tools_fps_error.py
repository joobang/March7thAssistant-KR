def test_removed_tools_are_not_available(qtbot):
    from app.tools_interface import ToolsInterface
    from module.tool_catalog import TOOL_BY_ID

    page = ToolsInterface()
    qtbot.addWidget(page)
    assert not hasattr(page, "unlockfpsCard")
    assert not hasattr(page, "cloudTouchCard")
    for tool_id in ("unlock_fps", "cloud_touch"):
        assert tool_id not in TOOL_BY_ID
        assert page.locate(tool_id) is False
