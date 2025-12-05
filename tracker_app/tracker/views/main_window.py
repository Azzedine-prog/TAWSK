"""Main window and wxPython application wiring."""
from __future__ import annotations

import logging
import tempfile
from datetime import date, timedelta
from typing import Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import wx
import wx.adv
import wx.aui

from tracker_app.tracker.controllers import AppController, ConfigManager

LOGGER = logging.getLogger(__name__)
ACCENT = "#0A66C2"  # LinkedIn blue for a familiar professional feel
BACKGROUND = "#0f172a"
SURFACE = "#111827"
CARD = "#1f2937"
TEXT_ON_DARK = "#e5e7eb"


class HistoryPanel(wx.Panel):
    """Tab for viewing historic entries."""

    def __init__(self, parent: wx.Window, controller: AppController):
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_picker = wx.adv.DatePickerCtrl(self)
        self.end_picker = wx.adv.DatePickerCtrl(self)
        for label, ctrl in (("Start", self.start_picker), ("End", self.end_picker)):
            filter_sizer.Add(wx.StaticText(self, label=label), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
            filter_sizer.Add(ctrl, 0, wx.ALL, 4)

        self.activity_choice = wx.Choice(self)
        filter_sizer.Add(wx.StaticText(self, label="Activity"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        filter_sizer.Add(self.activity_choice, 0, wx.ALL, 4)

        refresh_btn = wx.Button(self, label="Refresh")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        filter_sizer.Add(refresh_btn, 0, wx.ALL, 4)

        main_sizer.Add(filter_sizer, 0, wx.EXPAND)

        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Target", "%", "Objectives", "Reason"]):
            self.list_ctrl.InsertColumn(i, heading)
        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 4)
        self.SetSizer(main_sizer)

    def load_activities(self) -> None:
        activities = self.controller.list_activities()
        self.activity_choice.Clear()
        self.activity_choice.Append("All", None)
        for act in activities:
            self.activity_choice.Append(act.name, act.id)
        self.activity_choice.SetSelection(0)

    def on_refresh(self, event: wx.Event) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            start = self.start_picker.GetValue().FormatISODate()
            end = self.end_picker.GetValue().FormatISODate()
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            entries = self.controller.get_entries_between(start_date, end_date)
            selected_idx = self.activity_choice.GetSelection()
            selected_id = self.activity_choice.GetClientData(selected_idx) if selected_idx != wx.NOT_FOUND else None
            self.list_ctrl.DeleteAllItems()
            for entry_date, activity_name, hours, objectives, target_hours, completion_percent, stop_reason in entries:
                if selected_id and activity_name != self.activity_choice.GetString(selected_idx):
                    continue
                idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), entry_date)
                self.list_ctrl.SetItem(idx, 1, activity_name)
                self.list_ctrl.SetItem(idx, 2, f"{hours:.2f}")
                self.list_ctrl.SetItem(idx, 3, f"{target_hours:.2f}")
                self.list_ctrl.SetItem(idx, 4, f"{completion_percent:.0f}%")
                self.list_ctrl.SetItem(idx, 5, objectives)
                self.list_ctrl.SetItem(idx, 6, stop_reason)
            for col in range(7):
                self.list_ctrl.SetColumnWidth(col, wx.LIST_AUTOSIZE)
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("History refresh failed")
            wx.MessageBox(
                f"Unable to load history.\n\n{exc}\nEnsure the database is accessible and try again.",
                "History error",
                style=wx.ICON_ERROR,
            )


class StatsPanel(wx.Panel):
    """Tab for aggregated statistics and chart rendering."""

    def __init__(self, parent: wx.Window, controller: AppController):
        super().__init__(parent)
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        range_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.range_choice = wx.Choice(self, choices=["Last 7 days", "Last 30 days", "All time"])
        self.range_choice.SetSelection(0)
        range_sizer.Add(wx.StaticText(self, label="Range"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        range_sizer.Add(self.range_choice, 0, wx.ALL, 4)
        refresh_btn = wx.Button(self, label="Refresh")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        range_sizer.Add(refresh_btn, 0, wx.ALL, 4)
        export_btn = wx.Button(self, label="Export Excel")
        export_btn.Bind(wx.EVT_BUTTON, self.on_export)
        range_sizer.Add(export_btn, 0, wx.ALL, 4)
        main_sizer.Add(range_sizer, 0, wx.EXPAND)

        kpi_panel = wx.Panel(self)
        kpi_panel.SetBackgroundColour(CARD)
        kpi_sizer = wx.BoxSizer(wx.VERTICAL)
        self.kpi_text = wx.StaticText(kpi_panel, label="")
        self.kpi_text.SetForegroundColour(TEXT_ON_DARK)
        kpi_sizer.Add(self.kpi_text, 0, wx.ALL, 10)
        kpi_panel.SetSizer(kpi_sizer)
        main_sizer.Add(kpi_panel, 0, wx.EXPAND | wx.ALL, 6)

        chart_panel = wx.Panel(self)
        chart_panel.SetBackgroundColour(SURFACE)
        chart_sizer = wx.BoxSizer(wx.VERTICAL)
        self.chart_bitmap = wx.StaticBitmap(chart_panel)
        chart_sizer.Add(self.chart_bitmap, 1, wx.EXPAND | wx.ALL, 6)
        chart_panel.SetSizer(chart_sizer)
        main_sizer.Add(chart_panel, 1, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(main_sizer)


class OutcomeDialog(wx.Dialog):
    """Modal dialog to capture completion feedback and optional stop reasons."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        default_objectives: str,
        elapsed_hours: float,
        target_hours: float,
        early_stop: bool,
    ) -> None:
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.objectives = default_objectives
        self.completion_percent = 100.0
        self.stop_reason = ""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        summary = (
            f"Tracked {elapsed_hours:.2f}h with a target of {target_hours:.2f}h."
            if target_hours
            else f"Tracked {elapsed_hours:.2f}h."
        )
        subtitle = "Wrap up this task" if not early_stop else "You stopped before the target; tell us why."
        main_sizer.Add(wx.StaticText(self, label=summary), 0, wx.ALL, 6)
        main_sizer.Add(wx.StaticText(self, label=subtitle), 0, wx.LEFT | wx.RIGHT, 6)

        objectives_label = wx.StaticText(self, label="Objectives succeeded")
        objectives_label.SetForegroundColour(ACCENT)
        main_sizer.Add(objectives_label, 0, wx.ALL, 6)
        self.objectives_ctrl = wx.TextCtrl(self, value=default_objectives, style=wx.TE_MULTILINE, size=(400, 120))
        main_sizer.Add(self.objectives_ctrl, 1, wx.EXPAND | wx.ALL, 6)

        percent_row = wx.BoxSizer(wx.HORIZONTAL)
        percent_row.Add(wx.StaticText(self, label="Completion %"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        self.percent_ctrl = wx.SpinCtrlDouble(self, min=0, max=100, inc=5, initial=100.0)
        percent_row.Add(self.percent_ctrl, 0, wx.ALL, 6)
        main_sizer.Add(percent_row, 0, wx.ALL, 0)

        self.reason_ctrl: Optional[wx.TextCtrl] = None
        if early_stop:
            reason_label = wx.StaticText(self, label="Why stopping early?")
            reason_label.SetForegroundColour("#f97316")
            self.reason_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(400, 80))
            main_sizer.Add(reason_label, 0, wx.ALL, 6)
            main_sizer.Add(self.reason_ctrl, 0, wx.EXPAND | wx.ALL, 6)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
        self.SetSizerAndFit(main_sizer)

        ok_btn = self.FindWindowById(wx.ID_OK)
        if ok_btn:
            ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)

    def on_ok(self, event: wx.CommandEvent) -> None:
        if self.reason_ctrl and not self.reason_ctrl.GetValue().strip():
            wx.MessageBox("Please share why you stopped before the target.", "Feedback needed")
            return
        self.objectives = self.objectives_ctrl.GetValue()
        self.completion_percent = self.percent_ctrl.GetValue()
        self.stop_reason = self.reason_ctrl.GetValue().strip() if self.reason_ctrl else ""
        self.EndModal(wx.ID_OK)

    def get_values(self) -> tuple[str, float, str]:
        return self.objectives, self.completion_percent, self.stop_reason

    def _date_range(self):
        today = date.today()
        sel = self.range_choice.GetSelection()
        if sel == 0:
            return today - timedelta(days=6), today
        if sel == 1:
            return today - timedelta(days=29), today
        return date.min, today

    def on_refresh(self, event: wx.Event) -> None:
        self.refresh()

    def refresh(self) -> None:
        try:
            start, end = self._date_range()
            stats = self.controller.get_stats(start, end)
            if not stats:
                self.kpi_text.SetLabel("No data in selected range.")
                self.chart_bitmap.SetBitmap(wx.NullBitmap)
                return
            total_hours = sum(s.total_hours for s in stats)
            days = (end - start).days + 1
            avg_hours = total_hours / days if days else 0
            avg_completion = sum(s.avg_completion for s in stats) / len(stats)
            top = sorted(stats, key=lambda s: s.total_hours, reverse=True)[:3]
            top_str = ", ".join(f"{s.activity_name} ({s.total_hours:.1f}h, {s.avg_completion:.0f}% avg)" for s in top)
            self.kpi_text.SetLabel(
                f"Total hours: {total_hours:.1f}\nAverage per day: {avg_hours:.2f}\nAvg completion: {avg_completion:.0f}%\nTop activities: {top_str}"
            )

            fig, ax = plt.subplots(figsize=(6, 3))
            ax.bar([s.activity_name for s in stats], [s.total_hours for s in stats], color=ACCENT)
            ax.set_ylabel("Hours")
            ax.set_xlabel("Activity")
            ax.set_title("Hours & completion")
            ax2 = ax.twinx()
            ax2.plot([s.activity_name for s in stats], [s.avg_completion for s in stats], color="#22c55e", marker="o")
            ax2.set_ylabel("Avg %")
            fig.autofmt_xdate(rotation=30)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                fig.savefig(tmp.name, bbox_inches="tight")
                bitmap = wx.Bitmap(tmp.name, wx.BITMAP_TYPE_PNG)
                self.chart_bitmap.SetBitmap(bitmap)
            plt.close(fig)
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Statistics refresh failed")
            wx.MessageBox(
                f"Unable to render statistics.\n\n{exc}\nMake sure matplotlib and wxPython are installed and the database is readable.",
                "Statistics error",
                style=wx.ICON_ERROR,
            )

    def on_export(self, event: wx.Event) -> None:
        try:
            start, end = self._date_range()
            path = self.controller.export_to_excel(start, end)
            wx.MessageBox(f"Exported statistics to {path}", "Export complete")
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Export failed")
            wx.MessageBox(
                f"Excel export failed.\n\n{exc}\nClose any open Excel file and verify write access.",
                "Export error",
                style=wx.ICON_ERROR,
            )


class MainPanel(wx.Panel):
    def __init__(self, parent: wx.Window, controller: AppController, config_manager: ConfigManager):
        super().__init__(parent)
        self.controller = controller
        self.config_manager = config_manager
        self.selected_activity: Optional[int] = config_manager.config.last_selected_activity
        self.active_targets: Dict[int, float] = {}
        self.mgr: Optional[wx.aui.AuiManager] = None
        self._build_ui()
        self.load_activities()

    def _make_card(self, title: str, parent: wx.Window) -> tuple[wx.Panel, wx.BoxSizer]:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(CARD)
        panel.SetForegroundColour(TEXT_ON_DARK)
        sizer = wx.BoxSizer(wx.VERTICAL)
        heading = wx.StaticText(panel, label=title)
        heading_font = heading.GetFont()
        heading_font.MakeBold()
        heading.SetFont(heading_font)
        heading.SetForegroundColour(ACCENT)
        sizer.Add(heading, 0, wx.ALL, 6)
        panel.SetSizer(sizer)
        return panel, sizer

    def _build_ui(self) -> None:
        self.SetBackgroundColour(BACKGROUND)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        header = wx.Panel(self)
        header.SetBackgroundColour(ACCENT)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(header, label="Study Tracker")
        title.SetForegroundColour("white")
        title_font = title.GetFont()
        title_font.PointSize += 4
        title_font.MakeBold()
        title.SetFont(title_font)
        subtitle = wx.StaticText(header, label="Dock cards, rearrange layouts, and stay focused")
        subtitle.SetForegroundColour("#e0f2fe")
        layout_label = wx.StaticText(header, label="Layout")
        layout_label.SetForegroundColour("white")
        self.layout_choice = wx.Choice(header, choices=["Balanced grid", "Focus timer", "Wide stats"])
        self.layout_choice.SetSelection(0)
        self.layout_choice.Bind(wx.EVT_CHOICE, self.on_layout_choice)
        header_sizer.Add(title, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        header_sizer.Add(subtitle, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        header_sizer.AddStretchSpacer()
        header_sizer.Add(layout_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(self.layout_choice, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header.SetSizer(header_sizer)
        main_sizer.Add(header, 0, wx.EXPAND)

        dock_host = wx.Panel(self)
        dock_host.SetBackgroundColour(BACKGROUND)
        self.mgr = wx.aui.AuiManager(dock_host)

        self.activities_panel = self._build_activities_panel(dock_host)
        self.session_panel = self._build_session_panel(dock_host)
        self.objectives_panel = self._build_objectives_panel(dock_host)
        self.tabs_panel = self._build_tabs_panel(dock_host)

        self._setup_docking()

        main_sizer.Add(dock_host, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

    def _setup_docking(self) -> None:
        assert self.mgr is not None
        self.mgr.AddPane(
            self.activities_panel,
            wx.aui.AuiPaneInfo()
            .Name("activities")
            .Caption("Activities")
            .Left()
            .BestSize(260, 400)
            .CloseButton(False)
            .Floatable(True)
            .Movable(True),
        )
        self.mgr.AddPane(
            self.session_panel,
            wx.aui.AuiPaneInfo()
            .Name("session")
            .Caption("Focus session")
            .CenterPane()
            .BestSize(520, 320)
            .CloseButton(False),
        )
        self.mgr.AddPane(
            self.objectives_panel,
            wx.aui.AuiPaneInfo()
            .Name("objectives")
            .Caption("Objectives & notes")
            .Bottom()
            .BestSize(500, 200)
            .CloseButton(False)
            .Floatable(True),
        )
        self.mgr.AddPane(
            self.tabs_panel,
            wx.aui.AuiPaneInfo()
            .Name("insights")
            .Caption("Today, history & stats")
            .Right()
            .BestSize(520, 400)
            .CloseButton(False)
            .Floatable(True),
        )
        self.mgr.Update()
        self.perspectives = {
            "Balanced grid": self.mgr.SavePerspective(),
        }

        # Focused timer layout
        self.mgr.GetPane("activities").Left().BestSize(220, 500)
        self.mgr.GetPane("insights").Bottom().BestSize(700, 260)
        self.mgr.GetPane("objectives").Right().BestSize(360, 260)
        self.mgr.Update()
        self.perspectives["Focus timer"] = self.mgr.SavePerspective()

        # Stats-heavy layout
        self.mgr.GetPane("activities").Right().BestSize(200, 400)
        self.mgr.GetPane("insights").CenterPane()
        self.mgr.GetPane("session").Top().BestSize(520, 220)
        self.mgr.GetPane("objectives").Bottom().BestSize(520, 180)
        self.mgr.Update()
        self.perspectives["Wide stats"] = self.mgr.SavePerspective()

        # Restore default
        self.mgr.LoadPerspective(self.perspectives["Balanced grid"])
        self.mgr.Update()

    def on_layout_choice(self, event: wx.CommandEvent) -> None:
        choice = self.layout_choice.GetStringSelection()
        if self.mgr and choice in getattr(self, "perspectives", {}):
            self.mgr.LoadPerspective(self.perspectives[choice])
            self.mgr.Update()

    def _with_error_dialog(self, context: str, func):
        try:
            return func()
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("%s failed", context)
            wx.MessageBox(
                f"{context} failed.\n\n{exc}\n\nIf this keeps happening, ensure dependencies are installed and the database at {self.controller.storage.db_path} is writable.",
                "Operation failed",
                style=wx.ICON_ERROR,
            )
            return None

    def _build_activities_panel(self, host: wx.Window) -> wx.Panel:
        left_card, left_sizer = self._make_card("Activities", host)
        self.activity_list = wx.ListCtrl(left_card, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.activity_list.InsertColumn(0, "Activity")
        self.activity_list.InsertColumn(1, "Today")
        self.activity_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_activity_selected)
        self.activity_list.Bind(wx.EVT_CONTEXT_MENU, self.on_activity_context)
        left_sizer.Add(self.activity_list, 1, wx.EXPAND | wx.ALL, 4)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(left_card, label="Add")
        edit_btn = wx.Button(left_card, label="Edit")
        del_btn = wx.Button(left_card, label="Delete")
        for btn in (add_btn, edit_btn, del_btn):
            btn.SetBackgroundColour(ACCENT)
            btn.SetForegroundColour("white")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_activity)
        edit_btn.Bind(wx.EVT_BUTTON, self.on_edit_activity)
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_activity)
        for btn in (add_btn, edit_btn, del_btn):
            btn_sizer.Add(btn, 1, wx.ALL, 4)
        left_sizer.Add(btn_sizer, 0, wx.EXPAND)
        left_card.SetSizer(left_sizer)
        return left_card

    def _build_session_panel(self, host: wx.Window) -> wx.Panel:
        timer_card, timer_sizer = self._make_card("Focus session", host)
        self.timer_label = wx.StaticText(timer_card, label="00:00:00", style=wx.ALIGN_CENTER_HORIZONTAL)
        font = self.timer_label.GetFont()
        font.PointSize += 10
        font = font.Bold()
        self.timer_label.SetFont(font)
        self.timer_label.SetForegroundColour(TEXT_ON_DARK)
        timer_sizer.Add(self.timer_label, 0, wx.EXPAND | wx.ALL, 6)

        target_row = wx.BoxSizer(wx.HORIZONTAL)
        target_row.Add(wx.StaticText(timer_card, label="Plan (hours)"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.target_input = wx.SpinCtrlDouble(timer_card, min=0, max=24, inc=0.25, initial=1.0)
        target_row.Add(self.target_input, 0, wx.ALL, 4)
        self.progress = wx.Gauge(timer_card, range=100)
        target_row.Add(self.progress, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        timer_sizer.Add(target_row, 0, wx.EXPAND)

        today_box = wx.BoxSizer(wx.HORIZONTAL)
        self.today_hours_label = wx.StaticText(timer_card, label="Today: 0.0 h")
        self.today_hours_label.SetForegroundColour(TEXT_ON_DARK)
        today_box.Add(self.today_hours_label, 0, wx.ALL, 4)
        timer_sizer.Add(today_box, 0, wx.ALL, 2)

        btn_panel = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(timer_card, label="Start")
        self.pause_btn = wx.Button(timer_card, label="Pause")
        self.stop_btn = wx.Button(timer_card, label="Stop")
        self.reset_btn = wx.Button(timer_card, label="Reset")
        for btn in (self.start_btn, self.pause_btn, self.stop_btn, self.reset_btn):
            btn.SetBackgroundColour(ACCENT)
            btn.SetForegroundColour("white")
            btn_panel.Add(btn, 1, wx.ALL, 4)
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start)
        self.pause_btn.Bind(wx.EVT_BUTTON, self.on_pause)
        self.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        self.reset_btn.Bind(wx.EVT_BUTTON, self.on_reset)
        timer_sizer.Add(btn_panel, 0, wx.EXPAND)
        timer_card.SetSizer(timer_sizer)
        return timer_card

    def _build_objectives_panel(self, host: wx.Window) -> wx.Panel:
        objectives_card, obj_sizer = self._make_card("Objectives & notes", host)
        self.objectives = wx.TextCtrl(objectives_card, style=wx.TE_MULTILINE | wx.BORDER_NONE)
        obj_sizer.Add(self.objectives, 1, wx.EXPAND | wx.ALL, 4)
        objectives_card.SetSizer(obj_sizer)
        return objectives_card

    def _build_tabs_panel(self, host: wx.Window) -> wx.Panel:
        panel = wx.Panel(host)
        panel.SetBackgroundColour(BACKGROUND)
        sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(panel)
        today_panel = wx.Panel(notebook)
        today_panel.SetBackgroundColour(SURFACE)
        today_sizer = wx.BoxSizer(wx.VERTICAL)
        self.today_list = wx.ListCtrl(today_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Target", "%", "Objectives", "Reason"]):
            self.today_list.InsertColumn(i, heading)
        refresh_today = wx.Button(today_panel, label="Refresh Today")
        refresh_today.Bind(wx.EVT_BUTTON, lambda evt: self.refresh_today())
        today_sizer.Add(refresh_today, 0, wx.ALL, 4)
        today_sizer.Add(self.today_list, 1, wx.EXPAND | wx.ALL, 4)
        today_panel.SetSizer(today_sizer)

        self.history_tab = HistoryPanel(notebook, self.controller)
        self.history_tab.SetBackgroundColour(SURFACE)
        self.stats_tab = StatsPanel(notebook, self.controller)
        self.stats_tab.SetBackgroundColour(SURFACE)
        notebook.AddPage(today_panel, "Today")
        notebook.AddPage(self.history_tab, "History")
        notebook.AddPage(self.stats_tab, "Statistics")
        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 4)
        panel.SetSizer(sizer)
        return panel

    def refresh_today(self) -> None:
        def action() -> None:
            self.today_list.DeleteAllItems()
            for entry in self.controller.get_today_entries():
                idx = self.today_list.InsertItem(self.today_list.GetItemCount(), entry.date.isoformat())
                activity = next((a.name for a in self.controller.list_activities() if a.id == entry.activity_id), str(entry.activity_id))
                self.today_list.SetItem(idx, 1, activity)
                self.today_list.SetItem(idx, 2, f"{entry.duration_hours:.2f}")
                self.today_list.SetItem(idx, 3, f"{entry.target_hours:.2f}")
                self.today_list.SetItem(idx, 4, f"{entry.completion_percent:.0f}%")
                self.today_list.SetItem(idx, 5, entry.objectives_succeeded)
                self.today_list.SetItem(idx, 6, entry.stop_reason)
            for col in range(7):
                self.today_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)

        self._with_error_dialog("Loading today's entries", action)

    def load_activities(self) -> None:
        def action() -> None:
            activities = self.controller.list_activities()
            today_entries = {e.activity_id: e for e in self.controller.get_today_entries()}
            self.activity_list.DeleteAllItems()
            for act in activities:
                idx = self.activity_list.InsertItem(self.activity_list.GetItemCount(), act.name)
                hours = today_entries.get(act.id).duration_hours if act.id in today_entries else 0.0
                self.activity_list.SetItem(idx, 1, f"{hours:.2f}h")
                self.activity_list.SetItemData(idx, act.id)
                if self.selected_activity == act.id:
                    self.activity_list.Select(idx)
            for col in range(2):
                self.activity_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)
            self.history_tab.load_activities()
            self.refresh_today()

        self._with_error_dialog("Loading activities", action)

    def _require_selection(self) -> Optional[int]:
        item = self.activity_list.GetFirstSelected()
        if item == -1:
            wx.MessageBox("Select an activity first", "Info")
            return None
        return self.activity_list.GetItemData(item)

    def on_activity_context(self, event: wx.ContextMenuEvent) -> None:
        pos = event.GetPosition()
        if pos == wx.DefaultPosition:
            pos = wx.GetMousePosition()
        pos = self.activity_list.ScreenToClient(pos)
        item, _flags = self.activity_list.HitTest(pos)
        if item != wx.NOT_FOUND:
            self.activity_list.Select(item)
            self.selected_activity = self.activity_list.GetItemData(item)
        menu = wx.Menu()
        for label, handler in (
            ("Start", self.on_start),
            ("Pause", self.on_pause),
            ("Stop", self.on_stop),
            ("Reset", self.on_reset),
            ("Edit name", self.on_edit_activity),
            ("Delete", self.on_delete_activity),
        ):
            item_id = wx.NewId()
            menu.Append(item_id, label)
            self.Bind(wx.EVT_MENU, handler, id=item_id)
        self.activity_list.PopupMenu(menu)
        menu.Destroy()

    def on_activity_selected(self, event: wx.ListEvent) -> None:  # type: ignore[override]
        self.selected_activity = event.GetData()
        self._load_objectives()

    def _load_objectives(self) -> None:
        if self.selected_activity is None:
            self.objectives.SetValue("")
            return
        def action() -> None:
            entry = self.controller.storage.get_daily_entry(date.today(), self.selected_activity)
            self.objectives.SetValue(entry.objectives_succeeded if entry else "")
            if entry:
                self.today_hours_label.SetLabel(f"Today: {entry.duration_hours:.2f} h")
                target = entry.target_hours or self.target_input.GetValue()
                self._update_progress(entry.duration_hours, target)

        self._with_error_dialog("Loading objectives", action)

    def on_add_activity(self, event: wx.Event) -> None:
        dlg = wx.TextEntryDialog(self, "Activity name", "Add Activity")
        if dlg.ShowModal() == wx.ID_OK:
            self._with_error_dialog("Creating activity", lambda: self.controller.add_activity(dlg.GetValue()))
            self.load_activities()
        dlg.Destroy()

    def on_edit_activity(self, event: wx.Event) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        name = self.activity_list.GetItemText(self.activity_list.GetFirstSelected())
        dlg = wx.TextEntryDialog(self, "New name", "Edit Activity", value=name)
        if dlg.ShowModal() == wx.ID_OK:
            self._with_error_dialog("Renaming activity", lambda: self.controller.update_activity(activity_id, name=dlg.GetValue()))
            self.load_activities()
        dlg.Destroy()

    def on_delete_activity(self, event: wx.Event) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        if wx.MessageBox("Delete selected activity?", "Confirm", style=wx.YES_NO) == wx.YES:
            self._with_error_dialog("Deleting activity", lambda: self.controller.delete_activity(activity_id))
            self.load_activities()

    def on_start(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            wx.MessageBox("Select an activity first", "Info")
            return
        target_hours = self.target_input.GetValue()
        self.active_targets[self.selected_activity] = target_hours

        def tick_cb(elapsed: float) -> None:
            wx.CallAfter(self._update_timer_display, self.selected_activity, elapsed)

        def on_complete(elapsed: float) -> None:
            wx.CallAfter(self._handle_timer_complete, self.selected_activity, elapsed)

        self._with_error_dialog(
            "Starting timer",
            lambda: self.controller.start_timer(self.selected_activity, tick_cb, target_hours, on_complete),
        )

    def on_pause(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        self._with_error_dialog("Pausing timer", lambda: self.controller.pause_timer(self.selected_activity))

    def on_stop(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        self._complete_session(self.selected_activity, "Stop session", allow_reason=True)

    def on_reset(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        self._with_error_dialog("Resetting timer", lambda: self.controller.reset_timer(self.selected_activity))
        self.timer_label.SetLabel("00:00:00")
        self.progress.SetValue(0)

    def _update_timer_display(self, activity_id: int, elapsed_seconds: float) -> None:
        hours = int(elapsed_seconds) // 3600
        minutes = (int(elapsed_seconds) % 3600) // 60
        seconds = int(elapsed_seconds) % 60
        self.timer_label.SetLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        target = self.active_targets.get(activity_id, self.target_input.GetValue())
        self._update_progress(elapsed_seconds / 3600.0, target)

    def _update_progress(self, elapsed_hours: float, target_hours: float) -> None:
        if target_hours > 0:
            percent = min(100, int((elapsed_hours / target_hours) * 100))
            self.progress.SetValue(percent)
        else:
            self.progress.SetValue(0)

    def _handle_timer_complete(self, activity_id: int, elapsed: float) -> None:
        if activity_id != self.selected_activity:
            self.selected_activity = activity_id
        wx.MessageBox("Planned time reached. Let's wrap up!", "Time finished")
        self._complete_session(activity_id, "Time is up", allow_reason=False)

    def _complete_session(self, activity_id: int, title: str, allow_reason: bool) -> None:
        timer = self.controller.timers.ensure_timer(activity_id)
        elapsed_hours = timer.current_elapsed() / 3600.0
        target_hours = self.active_targets.get(activity_id, self.target_input.GetValue())
        early_stop = target_hours > 0 and elapsed_hours < target_hours and allow_reason
        dialog = OutcomeDialog(
            self,
            title,
            self.objectives.GetValue(),
            elapsed_hours,
            target_hours,
            early_stop=early_stop,
        )
        if dialog.ShowModal() != wx.ID_OK:
            self.controller.timers.stop(activity_id)
            return
        objectives, completion_percent, stop_reason = dialog.get_values()
        result = self._with_error_dialog(
            "Saving session",
            lambda: self.controller.finalize_timer(
                activity_id,
                objectives,
                target_hours,
                completion_percent,
                stop_reason=stop_reason,
            ),
        )
        if result is None:
            return
        elapsed = result
        hours = elapsed / 3600.0
        wx.MessageBox(f"Logged {hours:.2f} hours", "Saved")
        self.load_activities()
        self._load_objectives()
        self._maybe_start_next(activity_id)

    def _maybe_start_next(self, current_activity: int) -> None:
        activities = [a for a in self.controller.list_activities() if a.id != current_activity]
        if not activities:
            return
        labels = [a.name for a in activities]
        dlg = wx.SingleChoiceDialog(self, "Begin another task?", "Next focus", labels)
        if dlg.ShowModal() == wx.ID_OK:
            choice = dlg.GetSelection()
            next_activity = activities[choice]
            self.selected_activity = next_activity.id
            self.load_activities()
            self.on_start(wx.CommandEvent())
        dlg.Destroy()


class StudyTrackerFrame(wx.Frame):
    def __init__(self, controller: AppController, config_manager: ConfigManager):
        super().__init__(None, title="Study Tracker", size=(config_manager.config.last_window_width, config_manager.config.last_window_height))
        self.controller = controller
        self.config_manager = config_manager
        self.main_panel = MainPanel(self, controller, config_manager)
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def on_close(self, event: wx.CloseEvent) -> None:  # type: ignore[override]
        cfg = self.config_manager.config
        width, height = self.GetSize()
        cfg.last_window_width, cfg.last_window_height = width, height
        selection = self.main_panel.selected_activity
        self.controller.save_config(selection)
        if self.main_panel.mgr:
            self.main_panel.mgr.UnInit()
        event.Skip()


class StudyTrackerApp(wx.App):
    def __init__(self, controller: AppController, config_manager: ConfigManager):
        self.controller = controller
        self.config_manager = config_manager
        super().__init__(clearSigInt=True)

    def OnInit(self) -> bool:  # type: ignore[override]
        self.frame = StudyTrackerFrame(self.controller, self.config_manager)
        self.frame.Show()
        return True

    def run(self) -> None:
        self.MainLoop()
