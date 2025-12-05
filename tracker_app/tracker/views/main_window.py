"""Main window and wxPython application wiring."""
from __future__ import annotations

import logging
import tempfile
from datetime import date, timedelta
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import wx
import wx.adv

from tracker_app.tracker.controllers import AppController, ConfigManager

LOGGER = logging.getLogger(__name__)


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
        filter_sizer.Add(wx.StaticText(self, label="Start"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        filter_sizer.Add(self.start_picker, 0, wx.ALL, 4)
        filter_sizer.Add(wx.StaticText(self, label="End"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        filter_sizer.Add(self.end_picker, 0, wx.ALL, 4)

        self.activity_choice = wx.Choice(self)
        filter_sizer.Add(wx.StaticText(self, label="Activity"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        filter_sizer.Add(self.activity_choice, 0, wx.ALL, 4)

        refresh_btn = wx.Button(self, label="Refresh")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        filter_sizer.Add(refresh_btn, 0, wx.ALL, 4)

        main_sizer.Add(filter_sizer, 0, wx.EXPAND)

        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Objectives"]):
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
        start = self.start_picker.GetValue().FormatISODate()
        end = self.end_picker.GetValue().FormatISODate()
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        entries = self.controller.get_entries_between(start_date, end_date)
        selected_idx = self.activity_choice.GetSelection()
        selected_id = self.activity_choice.GetClientData(selected_idx) if selected_idx != wx.NOT_FOUND else None
        self.list_ctrl.DeleteAllItems()
        for entry_date, activity_name, hours, objectives in entries:
            if selected_id and activity_name != self.activity_choice.GetString(selected_idx):
                continue
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), entry_date)
            self.list_ctrl.SetItem(idx, 1, activity_name)
            self.list_ctrl.SetItem(idx, 2, f"{hours:.2f}")
            self.list_ctrl.SetItem(idx, 3, objectives)
        for col in range(4):
            self.list_ctrl.SetColumnWidth(col, wx.LIST_AUTOSIZE)


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

        self.kpi_text = wx.StaticText(self, label="")
        main_sizer.Add(self.kpi_text, 0, wx.ALL, 6)

        self.chart_bitmap = wx.StaticBitmap(self)
        main_sizer.Add(self.chart_bitmap, 1, wx.EXPAND | wx.ALL, 6)

        self.SetSizer(main_sizer)

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
        start, end = self._date_range()
        stats = self.controller.get_stats(start, end)
        if not stats:
            self.kpi_text.SetLabel("No data in selected range.")
            self.chart_bitmap.SetBitmap(wx.NullBitmap)
            return
        total_hours = sum(s.total_hours for s in stats)
        days = (end - start).days + 1
        avg_hours = total_hours / days if days else 0
        top = sorted(stats, key=lambda s: s.total_hours, reverse=True)[:3]
        top_str = ", ".join(f"{s.activity_name} ({s.total_hours:.1f}h)" for s in top)
        self.kpi_text.SetLabel(
            f"Total hours: {total_hours:.1f}\nAverage per day: {avg_hours:.2f}\nTop activities: {top_str}"
        )

        fig, ax = plt.subplots(figsize=(6, 3))
        ax.bar([s.activity_name for s in stats], [s.total_hours for s in stats], color="#2563eb")
        ax.set_ylabel("Hours")
        ax.set_xlabel("Activity")
        ax.set_title("Hours by activity")
        fig.autofmt_xdate(rotation=30)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            fig.savefig(tmp.name, bbox_inches="tight")
            bitmap = wx.Bitmap(tmp.name, wx.BITMAP_TYPE_PNG)
            self.chart_bitmap.SetBitmap(bitmap)
        plt.close(fig)

    def on_export(self, event: wx.Event) -> None:
        start, end = self._date_range()
        path = self.controller.export_to_excel(start, end)
        wx.MessageBox(f"Exported statistics to {path}", "Export complete")


class MainPanel(wx.Panel):
    def __init__(self, parent: wx.Window, controller: AppController, config_manager: ConfigManager):
        super().__init__(parent)
        self.controller = controller
        self.config_manager = config_manager
        self.selected_activity: Optional[int] = config_manager.config.last_selected_activity
        self._build_ui()
        self.load_activities()

    def _build_ui(self) -> None:
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Left column for activities
        left_panel = wx.Panel(self)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        self.activity_list = wx.ListCtrl(left_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.activity_list.InsertColumn(0, "Activity")
        self.activity_list.InsertColumn(1, "Today")
        self.activity_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_activity_selected)
        left_sizer.Add(self.activity_list, 1, wx.EXPAND | wx.ALL, 4)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(left_panel, label="Add")
        edit_btn = wx.Button(left_panel, label="Edit")
        del_btn = wx.Button(left_panel, label="Delete")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_activity)
        edit_btn.Bind(wx.EVT_BUTTON, self.on_edit_activity)
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_activity)
        for btn in (add_btn, edit_btn, del_btn):
            btn_sizer.Add(btn, 1, wx.ALL, 4)
        left_sizer.Add(btn_sizer, 0, wx.EXPAND)
        left_panel.SetSizer(left_sizer)

        # Right column for timer and tabs
        right_panel = wx.Panel(self)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        self.timer_label = wx.StaticText(right_panel, label="00:00:00", style=wx.ALIGN_CENTER_HORIZONTAL)
        font = self.timer_label.GetFont()
        font.PointSize += 10
        font = font.Bold()
        self.timer_label.SetFont(font)
        right_sizer.Add(self.timer_label, 0, wx.EXPAND | wx.ALL, 6)

        today_box = wx.BoxSizer(wx.HORIZONTAL)
        self.today_hours_label = wx.StaticText(right_panel, label="Today: 0.0 h")
        today_box.Add(self.today_hours_label, 0, wx.ALL, 4)
        right_sizer.Add(today_box, 0, wx.ALL, 2)

        btn_panel = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(right_panel, label="Start")
        self.pause_btn = wx.Button(right_panel, label="Pause")
        self.stop_btn = wx.Button(right_panel, label="Stop")
        self.reset_btn = wx.Button(right_panel, label="Reset")
        for btn in (self.start_btn, self.pause_btn, self.stop_btn, self.reset_btn):
            btn_panel.Add(btn, 1, wx.ALL, 4)
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start)
        self.pause_btn.Bind(wx.EVT_BUTTON, self.on_pause)
        self.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        self.reset_btn.Bind(wx.EVT_BUTTON, self.on_reset)
        right_sizer.Add(btn_panel, 0, wx.EXPAND)

        self.objectives = wx.TextCtrl(right_panel, style=wx.TE_MULTILINE)
        right_sizer.Add(wx.StaticText(right_panel, label="Objectives succeeded"), 0, wx.ALL, 4)
        right_sizer.Add(self.objectives, 0, wx.EXPAND | wx.ALL, 4)

        notebook = wx.Notebook(right_panel)
        today_panel = wx.Panel(notebook)
        today_sizer = wx.BoxSizer(wx.VERTICAL)
        self.today_list = wx.ListCtrl(today_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Objectives"]):
            self.today_list.InsertColumn(i, heading)
        refresh_today = wx.Button(today_panel, label="Refresh Today")
        refresh_today.Bind(wx.EVT_BUTTON, lambda evt: self.refresh_today())
        today_sizer.Add(refresh_today, 0, wx.ALL, 4)
        today_sizer.Add(self.today_list, 1, wx.EXPAND | wx.ALL, 4)
        today_panel.SetSizer(today_sizer)

        self.history_tab = HistoryPanel(notebook, self.controller)
        self.stats_tab = StatsPanel(notebook, self.controller)
        notebook.AddPage(today_panel, "Today")
        notebook.AddPage(self.history_tab, "History")
        notebook.AddPage(self.stats_tab, "Statistics")
        right_sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 4)

        right_panel.SetSizer(right_sizer)

        main_sizer.Add(left_panel, 1, wx.EXPAND | wx.ALL, 6)
        main_sizer.Add(right_panel, 2, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(main_sizer)

    def refresh_today(self) -> None:
        self.today_list.DeleteAllItems()
        for entry in self.controller.get_today_entries():
            idx = self.today_list.InsertItem(self.today_list.GetItemCount(), entry.date.isoformat())
            activity = next((a.name for a in self.controller.list_activities() if a.id == entry.activity_id), str(entry.activity_id))
            self.today_list.SetItem(idx, 1, activity)
            self.today_list.SetItem(idx, 2, f"{entry.duration_hours:.2f}")
            self.today_list.SetItem(idx, 3, entry.objectives_succeeded)
        for col in range(4):
            self.today_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)

    def load_activities(self) -> None:
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

    def _require_selection(self) -> Optional[int]:
        item = self.activity_list.GetFirstSelected()
        if item == -1:
            wx.MessageBox("Select an activity first", "Info")
            return None
        return self.activity_list.GetItemData(item)

    def on_activity_selected(self, event: wx.ListEvent) -> None:  # type: ignore[override]
        self.selected_activity = event.GetData()
        self._load_objectives()

    def _load_objectives(self) -> None:
        if self.selected_activity is None:
            self.objectives.SetValue("")
            return
        entry = self.controller.storage.get_daily_entry(date.today(), self.selected_activity)
        self.objectives.SetValue(entry.objectives_succeeded if entry else "")
        if entry:
            self.today_hours_label.SetLabel(f"Today: {entry.duration_hours:.2f} h")

    def on_add_activity(self, event: wx.Event) -> None:
        dlg = wx.TextEntryDialog(self, "Activity name", "Add Activity")
        if dlg.ShowModal() == wx.ID_OK:
            self.controller.add_activity(dlg.GetValue())
            self.load_activities()
        dlg.Destroy()

    def on_edit_activity(self, event: wx.Event) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        name = self.activity_list.GetItemText(self.activity_list.GetFirstSelected())
        dlg = wx.TextEntryDialog(self, "New name", "Edit Activity", value=name)
        if dlg.ShowModal() == wx.ID_OK:
            self.controller.update_activity(activity_id, name=dlg.GetValue())
            self.load_activities()
        dlg.Destroy()

    def on_delete_activity(self, event: wx.Event) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        if wx.MessageBox("Delete selected activity?", "Confirm", style=wx.YES_NO) == wx.YES:
            self.controller.delete_activity(activity_id)
            self.load_activities()

    def on_start(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            wx.MessageBox("Select an activity first", "Info")
            return
        self.controller.start_timer(self.selected_activity, lambda e: wx.CallAfter(self.timer_label.SetLabel, self.controller.timers.ensure_timer(self.selected_activity).formatted))

    def on_pause(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        self.controller.pause_timer(self.selected_activity)

    def on_stop(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        objectives = self.objectives.GetValue()
        elapsed = self.controller.stop_timer(self.selected_activity, objectives)
        hours = elapsed / 3600.0
        wx.MessageBox(f"Logged {hours:.2f} hours", "Saved")
        self.load_activities()
        self._load_objectives()

    def on_reset(self, event: wx.Event) -> None:
        if self.selected_activity is None:
            return
        self.controller.reset_timer(self.selected_activity)
        self.timer_label.SetLabel("00:00:00")


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
