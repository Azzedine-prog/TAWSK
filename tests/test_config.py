from tracker_app.tracker.controllers import AppConfig


def test_to_toml_roundtrip_no_last_activity():
    cfg = AppConfig(
        export_path="stats.xlsx",
        default_range_days=7,
        last_window_width=1000,
        last_window_height=700,
        last_selected_activity=None,
        last_layout="abc",
    )

    toml_text = cfg.to_toml()
    assert "last_selected_activity = """ in toml_text

    parsed = AppConfig.from_toml({
        "export_path": "stats.xlsx",
        "default_range_days": 7,
        "last_window_width": 1000,
        "last_window_height": 700,
        "last_selected_activity": "",
        "last_layout": "abc",
        "show_help_tips": True,
    })
    assert parsed.last_selected_activity is None
    assert parsed.last_layout == "abc"
    assert parsed.show_help_tips is True


def test_to_toml_with_last_activity():
    cfg = AppConfig(
        export_path="stats.xlsx",
        default_range_days=7,
        last_window_width=1000,
        last_window_height=700,
        last_selected_activity=3,
        last_layout="abc",
    )

    toml_text = cfg.to_toml()
    assert "last_selected_activity = 3" in toml_text

    parsed = AppConfig.from_toml({
        "export_path": "stats.xlsx",
        "default_range_days": 7,
        "last_window_width": 1000,
        "last_window_height": 700,
        "last_selected_activity": 3,
        "last_layout": "abc",
        "show_help_tips": False,
    })
    assert parsed.last_selected_activity == 3
    assert parsed.last_layout == "abc"
    assert parsed.show_help_tips is False
