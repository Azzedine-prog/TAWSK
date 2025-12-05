"""Main window and GTK application wiring."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from gi.repository import Gio, Gtk

from tracker_app.tracker.controllers import AppController, ConfigManager
from tracker_app.tracker.views.history_view import HistoryView
from tracker_app.tracker.views.stats_view import StatsView

LOGGER = logging.getLogger(__name__)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, controller: AppController, config_manager: ConfigManager):
        super().__init__(application=app)
        self.controller = controller
        self.config_manager = config_manager
        self.set_title("Study Tracker")
        self.set_default_size(config_manager.config.last_window_width, config_manager.config.last_window_height)
        self.set_resizable(True)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self._load_css()
        self.add_css_class("app-window")

        self.selected_activity: Optional[int] = config_manager.config.last_selected_activity
        self._build_ui()
        self._load_activities()

    # UI setup
    def _build_ui(self) -> None:
        header = Gtk.HeaderBar()
        header_label = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Daily Study Tracker")
        subtitle = Gtk.Label(label="Track time with Microsoft-inspired polish")
        title.set_xalign(0)
        subtitle.set_xalign(0)
        subtitle.add_css_class("subdued")
        header_label.append(title)
        header_label.append(subtitle)
        header.set_title_widget(header_label)

        export_btn = Gtk.Button.new_with_label("Export")
        export_btn.set_icon_name("document-save-symbolic")
        export_btn.set_tooltip_text("Export statistics to Excel (Ctrl+E)")
        export_btn.add_css_class("accent-button")
        export_btn.connect("clicked", self.on_export_clicked)
        header.pack_end(export_btn)
        header.add_css_class("header-accent")
        self.set_titlebar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.set_child(main_box)

        # Left panel activities
        left_frame = Gtk.Frame()
        left_frame.add_css_class("card")
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_frame.set_child(left_box)
        main_box.append(left_frame)

        activities_header = Gtk.Label(label="Activities", xalign=0)
        activities_header.add_css_class("section-title")
        left_box.append(activities_header)

        self.activity_list = Gtk.ListBox()
        self.activity_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.activity_list.connect("row-selected", self.on_activity_selected)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(self.activity_list)
        scroll.add_css_class("list-surface")
        left_box.append(scroll)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_box.add_css_class("command-bar")
        add_btn = Gtk.Button.new_with_label("Add")
        add_btn.set_icon_name("list-add-symbolic")
        add_btn.connect("clicked", self.on_add_activity)
        edit_btn = Gtk.Button.new_with_label("Edit")
        edit_btn.set_icon_name("document-edit-symbolic")
        edit_btn.connect("clicked", self.on_edit_activity)
        del_btn = Gtk.Button.new_with_label("Delete")
        del_btn.set_icon_name("user-trash-symbolic")
        del_btn.connect("clicked", self.on_delete_activity)
        btn_box.append(add_btn)
        btn_box.append(edit_btn)
        btn_box.append(del_btn)
        left_box.append(btn_box)

        # Center panel timer
        center_frame = Gtk.Frame()
        center_frame.add_css_class("card")
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        center_frame.set_child(center_box)
        main_box.append(center_frame)

        self.timer_label = Gtk.Label(label="00:00:00")
        self.timer_label.set_margin_top(4)
        self.timer_label.add_css_class("timer-display")
        center_box.append(self.timer_label)
        self.today_total_label = Gtk.Label(label="Today: 0 h")
        self.today_total_label.add_css_class("subdued")
        center_box.append(self.today_total_label)

        timer_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        timer_btn_box.add_css_class("command-bar")
        start_btn = Gtk.Button.new_with_label("Start")
        start_btn.set_icon_name("media-playback-start-symbolic")
        start_btn.add_css_class("accent-button")
        start_btn.connect("clicked", self.on_start_timer)
        pause_btn = Gtk.Button.new_with_label("Pause")
        pause_btn.set_icon_name("media-playback-pause-symbolic")
        pause_btn.connect("clicked", self.on_pause_timer)
        stop_btn = Gtk.Button.new_with_label("Stop")
        stop_btn.set_icon_name("media-playback-stop-symbolic")
        stop_btn.connect("clicked", self.on_stop_timer)
        reset_btn = Gtk.Button.new_with_label("Reset")
        reset_btn.set_icon_name("view-refresh-symbolic")
        reset_btn.connect("clicked", self.on_reset_timer)
        for btn in (start_btn, pause_btn, stop_btn, reset_btn):
            timer_btn_box.append(btn)
        center_box.append(timer_btn_box)

        objectives_label = Gtk.Label(label="Objectives succeeded", xalign=0)
        objectives_label.add_css_class("section-title")
        center_box.append(objectives_label)
        self.objectives_buffer = Gtk.TextBuffer()
        self.objectives_view = Gtk.TextView.new_with_buffer(self.objectives_buffer)
        self.objectives_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.objectives_view.add_css_class("text-panel")
        objectives_scroll = Gtk.ScrolledWindow()
        objectives_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        objectives_scroll.set_child(self.objectives_view)
        center_box.append(objectives_scroll)

        # Tabs right/bottom
        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.BOTTOM)
        notebook.add_css_class("card")
        main_box.append(notebook)

        self.history_view = HistoryView(self.controller)
        notebook.append_page(self.history_view, Gtk.Label(label="History"))

        self.stats_view = StatsView(self.controller)
        notebook.append_page(self.stats_view, Gtk.Label(label="Statistics"))

    def _load_css(self) -> None:
        style_paths = [
            Path(__file__).resolve().parents[3] / "resources" / "ui" / "style.css",
            Path(__file__).resolve().parents[2] / "resources" / "ui" / "style.css",
        ]
        for path in style_paths:
            if path.exists():
                provider = Gtk.CssProvider()
                provider.load_from_path(str(path))
                display = self.get_display() or Gtk.Display.get_default()
                Gtk.StyleContext.add_provider_for_display(
                    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
                break

    # Activity handling
    def _load_activities(self) -> None:
        self.activity_list.remove_all()
        activities = self.controller.list_activities()
        if not activities:
            for default in ["AUTOSAR", "TCF", "CAPM", "YOCTO", "Resume + job posting"]:
                activity = self.controller.add_activity(default)
                activities.append(activity)
        selected_row_index = 0
        for idx, activity in enumerate(activities):
            row = Gtk.ListBoxRow()
            row.set_data("activity_id", activity.id)
            row.set_child(Gtk.Label(label=activity.name, xalign=0))
            self.activity_list.append(row)
            if activity.id == self.selected_activity:
                selected_row_index = idx
        self.activity_list.show()
        self.activity_list.select_row(self.activity_list.get_row_at_index(selected_row_index))

    def on_activity_selected(self, listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if not row:
            return
        activity_id = row.get_data("activity_id")
        self.selected_activity = activity_id
        self.config_manager.config.last_selected_activity = activity_id
        self._refresh_today_total()
        self.timer_label.set_text(self.controller.get_timer_display(activity_id))

    def _refresh_today_total(self) -> None:
        if self.selected_activity is None:
            return
        entries = self.controller.get_today_entries()
        total = 0.0
        text = ""
        for entry in entries:
            if entry.activity_id == self.selected_activity:
                total = entry.duration_hours
                text = entry.objectives_succeeded
        self.today_total_label.set_text(f"Today: {total:.2f} h")
        self.objectives_buffer.set_text(text)

    def on_add_activity(self, _button) -> None:
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK_CANCEL, text="New activity name")
        entry = Gtk.Entry()
        entry.set_placeholder_text("Activity name")
        dialog.set_extra_child(entry)
        response = dialog.run()
        if response == Gtk.ResponseType.OK and entry.get_text():
            self.controller.add_activity(entry.get_text())
            self._load_activities()
        dialog.destroy()

    def on_edit_activity(self, _button) -> None:
        row = self.activity_list.get_selected_row()
        if not row:
            return
        activity_id = row.get_data("activity_id")
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK_CANCEL, text="Edit activity name")
        entry = Gtk.Entry()
        entry.set_text(row.get_child().get_text())
        dialog.set_extra_child(entry)
        response = dialog.run()
        if response == Gtk.ResponseType.OK and entry.get_text():
            self.controller.update_activity(activity_id, name=entry.get_text())
            self._load_activities()
        dialog.destroy()

    def on_delete_activity(self, _button) -> None:
        row = self.activity_list.get_selected_row()
        if not row:
            return
        activity_id = row.get_data("activity_id")
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK_CANCEL, text="Delete this activity?")
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.controller.delete_activity(activity_id)
            self._load_activities()
        dialog.destroy()

    # Timer callbacks
    def on_start_timer(self, _button) -> None:
        if self.selected_activity is None:
            return
        self.controller.start_timer(self.selected_activity, self._on_tick)

    def on_pause_timer(self, _button) -> None:
        if self.selected_activity is None:
            return
        self.controller.pause_timer(self.selected_activity)
        self._refresh_today_total()

    def on_stop_timer(self, _button) -> None:
        if self.selected_activity is None:
            return
        objectives = self.objectives_buffer.get_text(self.objectives_buffer.get_start_iter(), self.objectives_buffer.get_end_iter(), True)
        self.controller.stop_timer(self.selected_activity, objectives)
        self._refresh_today_total()

    def on_reset_timer(self, _button) -> None:
        if self.selected_activity is None:
            return
        self.controller.reset_timer(self.selected_activity)
        self.timer_label.set_text("00:00:00")

    def _on_tick(self, elapsed_seconds: float) -> None:
        if self.selected_activity is None:
            return
        self.timer_label.set_text(self.controller.get_timer_display(self.selected_activity))

    def on_export_clicked(self, _button) -> None:
        cfg = self.config_manager.config
        end_date = date.today()
        start_date = end_date - timedelta(days=cfg.default_range_days)
        try:
            path = self.controller.export_to_excel(start_date, end_date)
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK, text=f"Exported to {path}")
            dialog.run()
            dialog.destroy()
        except Exception as exc:  # pragma: no cover - GUI dialog only
            LOGGER.exception("Export failed")
            dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.OK, text=f"Export failed: {exc}")
            dialog.run()
            dialog.destroy()

    def save_state(self) -> None:
        self.config_manager.save_config(self.selected_activity)


class StudyTrackerApp(Gtk.Application):
    def __init__(self, controller: AppController, config_manager: ConfigManager):
        super().__init__(application_id="com.example.studytracker", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.controller = controller
        self.config_manager = config_manager
        self.window: Optional[MainWindow] = None

    def do_startup(self) -> None:  # type: ignore[override]
        Gtk.Application.do_startup(self)
        # Accelerators
        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", self._on_export_action)
        self.add_action(export_action)
        self.set_accels_for_action("app.export", ["<Primary>e"])

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Primary>q"])

    def do_activate(self) -> None:  # type: ignore[override]
        if not self.window:
            self.window = MainWindow(self, self.controller, self.config_manager)
        self.window.present()

    def _on_export_action(self, _action, _param) -> None:
        if self.window:
            self.window.on_export_clicked(None)

    def do_shutdown(self) -> None:  # type: ignore[override]
        if self.window:
            self.window.save_state()
        Gtk.Application.do_shutdown(self)
