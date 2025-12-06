"""Main window and wxPython application wiring."""
from __future__ import annotations

import logging
import random
import tempfile
from datetime import date, timedelta
from typing import Dict, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import wx
import wx.adv
import wx.aui

from tracker_app.core.ai_service import AIAssistantService
from tracker_app.tracker.controllers import AppController, ConfigManager

LOGGER = logging.getLogger(__name__)
PRIMARY = "#1F2937"  # modern deep gray header
SECONDARY = "#4A90E2"  # vibrant blue
ACCENT = "#50E3C2"  # mint accent
BACKGROUND = "#F7F9FC"
SURFACE = "#FFFFFF"
CARD = "#FFFFFF"
TEXT_ON_DARK = "#2D3436"
MUTED = "#7F8C8D"

MOTIVATION = [
    "Small steps today compound into big wins tomorrow.",
    "Progress over perfection—ship the next minute.",
    "Focus is a habit: start, pause with purpose, finish proud.",
    "You’re one session away from momentum.",
]


class HistoryPanel(wx.Panel):
    """Tab for viewing historic entries."""

    def __init__(self, parent: wx.Window, controller: AppController):
        super().__init__(parent)
        self.controller = controller
        self.ai = AIAssistantService(controller)
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
        refresh_btn.SetBackgroundColour(SECONDARY)
        refresh_btn.SetForegroundColour("white")
        refresh_btn.SetToolTip("Load entries for the selected filters")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        filter_sizer.Add(refresh_btn, 0, wx.ALL, 4)

        main_sizer.Add(filter_sizer, 0, wx.EXPAND)

        self.list_ctrl = wx.ListCtrl(self, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Target", "%", "Objectives", "Reason", "Comments"]):
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
            for (
                entry_date,
                activity_name,
                hours,
                objectives,
                target_hours,
                completion_percent,
                stop_reason,
                comments,
            ) in entries:
                if selected_id and activity_name != self.activity_choice.GetString(selected_idx):
                    continue
                idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), entry_date)
                self.list_ctrl.SetItem(idx, 1, activity_name)
                self.list_ctrl.SetItem(idx, 2, f"{hours:.2f}")
                self.list_ctrl.SetItem(idx, 3, f"{target_hours:.2f}")
                self.list_ctrl.SetItem(idx, 4, f"{completion_percent:.0f}%")
                self.list_ctrl.SetItem(idx, 5, objectives)
                self.list_ctrl.SetItem(idx, 6, stop_reason)
                self.list_ctrl.SetItem(idx, 7, comments)
            for col in range(8):
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

    def __init__(self, parent: wx.Window, controller: AppController, charts_panel: "StatsChartsPanel"):
        super().__init__(parent)
        self.controller = controller
        self.charts_panel = charts_panel
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct controls for statistics KPIs and preview chart."""
        self.SetBackgroundColour(SURFACE)

        main = wx.BoxSizer(wx.VERTICAL)

        range_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.range_choice = wx.Choice(self, choices=["Last 7 days", "Last 30 days", "All time"])
        self.range_choice.SetSelection(0)
        self.range_choice.SetToolTip("Choose the period to summarize")
        range_sizer.Add(wx.StaticText(self, label="Range"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        range_sizer.Add(self.range_choice, 0, wx.ALL, 4)

        refresh_btn = wx.Button(self, label="Refresh")
        refresh_btn.SetBackgroundColour(SECONDARY)
        refresh_btn.SetForegroundColour("white")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        refresh_btn.SetToolTip("Recompute KPIs and charts for the selected window")
        range_sizer.Add(refresh_btn, 0, wx.ALL, 4)

        export_btn = wx.Button(self, label="Export Excel")
        export_btn.SetBackgroundColour(SECONDARY)
        export_btn.SetForegroundColour("white")
        export_btn.Bind(wx.EVT_BUTTON, self._on_export)
        export_btn.SetToolTip("Write raw data and KPIs to statistics.xlsx")
        range_sizer.Add(export_btn, 0, wx.ALL, 4)

        main.Add(range_sizer, 0, wx.EXPAND)

        self.kpi_text = wx.StaticText(self, label="Load a range to view KPIs")
        self.kpi_text.SetForegroundColour(TEXT_ON_DARK)
        main.Add(self.kpi_text, 0, wx.ALL, 6)

        self.analysis_text = wx.StaticText(
            self,
            label="Charts and insights will appear after refresh.",
        )
        self.analysis_text.SetForegroundColour(MUTED)
        main.Add(self.analysis_text, 0, wx.ALL, 6)

        self.chart_bitmap = wx.StaticBitmap(self)
        main.Add(self.chart_bitmap, 0, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(main)

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
            entries = self.controller.get_entries_between(start, end)
            kpis = self.controller.get_kpis(start, end)
            if not stats:
                self.kpi_text.SetLabel("No data in selected range.")
                self.analysis_text.SetLabel("Track a session to see charts and KPIs here.")
                self.chart_bitmap.SetBitmap(wx.NullBitmap)
                self.charts_panel.clear()
                return
            total_hours = sum(s.total_hours for s in stats)
            days = (end - start).days + 1
            avg_hours = total_hours / days if days else 0
            avg_completion = sum(s.avg_completion for s in stats) / len(stats)
            top = sorted(stats, key=lambda s: s.total_hours, reverse=True)[:3]
            top_str = ", ".join(
                f"{s.activity_name} ({s.total_hours:.1f}h, {s.avg_completion:.0f}% avg)" for s in top
            )
            kpi_lines = [
                f"Planned vs actual: {kpis.get('planned_vs_actual', 'N/A')}",
                f"Focus time ratio: {kpis.get('focus_ratio', 'N/A')}",
                f"Time per category: {kpis.get('category_hours', 'N/A')}",
                f"Task switches/day: {kpis.get('switches', '0')}",
                f"Overtime: {kpis.get('overtime', '0h')}",
                f"Completion rate: {kpis.get('completion_rate', 'N/A')}",
                f"Avg task duration: {kpis.get('avg_task_duration', 'N/A')}",
                f"Productivity score: {kpis.get('productivity_score', 'N/A')}",
            ]
            self.kpi_text.SetLabel(
                "\n".join([
                    f"Total hours: {total_hours:.1f}",
                    f"Average per day: {avg_hours:.2f}",
                    f"Avg completion: {avg_completion:.0f}%",
                    f"Top activities: {top_str}",
                    *kpi_lines,
                ])
            )
            trend_note = (
                "Your completion is steady—keep a rhythm."
                if avg_completion >= 80
                else "Completion is dipping; review targets, reduce context switching, and revisit estimates."
            )
            self.analysis_text.SetLabel(
                trend_note
                + "\nPlanned vs actual highlights estimation accuracy; focus ratio shows deep-work share; switches track interruptions."
            )

            fig, ax = plt.subplots(figsize=(6, 3))
            bars = ax.bar([s.activity_name for s in stats], [s.total_hours for s in stats], color=SECONDARY)
            ax.set_ylabel("Hours")
            ax.set_xlabel("Activity")
            ax.set_title("Hours & completion")
            ax.bar_label(bars, fmt="{:.1f}h", padding=2, color="#0f172a")
            ax2 = ax.twinx()
            ax2.plot(
                [s.activity_name for s in stats],
                [s.avg_completion for s in stats],
                color=ACCENT,
                marker="o",
            )
            ax2.set_ylabel("Avg %")
            fig.autofmt_xdate(rotation=30)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                fig.savefig(tmp.name, bbox_inches="tight")
                bitmap = wx.Bitmap(tmp.name, wx.BITMAP_TYPE_PNG)
                self.chart_bitmap.SetBitmap(bitmap)
            plt.close(fig)

            self.charts_panel.update_charts(stats, entries, kpis, start, end)
            self.charts_panel.present()
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Statistics refresh failed")
            wx.MessageBox(
                f"Unable to render statistics.\n\n{exc}\nMake sure matplotlib and wxPython are installed and the database is readable.",
                "Statistics error",
                style=wx.ICON_ERROR,
            )

    def _on_export(self, event: wx.Event) -> None:
        try:
            start, end = self._date_range()
            path = self.controller.export_to_excel(start, end)
            wx.MessageBox(f"Exported statistics to {path}", "Export complete")
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Statistics export failed")
            wx.MessageBox(
                f"Excel export failed.\n\n{exc}\nClose any open Excel file and verify write access.",
                "Export error",
                style=wx.ICON_ERROR,
            )


class StatsChartsPanel(wx.Panel):
    """Floating chart canvas to highlight multiple time-management visuals."""

    def __init__(self, parent: wx.Window, controller: AppController):
        super().__init__(parent)
        self.controller = controller
        self.manager: Optional[wx.aui.AuiManager] = None
        self._build_ui()

    def attach_manager(self, manager: wx.aui.AuiManager) -> None:
        self.manager = manager

    def present(self) -> None:
        if not self.manager:
            return
        pane = self.manager.GetPane(self)
        if pane.IsOk():
            pane.Show(True)
            if not pane.IsFloating():
                pane.Float()
            self.manager.Update()

    def clear(self) -> None:
        for bitmap in (
            self.chart_hours,
            self.chart_planned,
            self.chart_focus,
            self.chart_category,
            self.chart_completion,
            self.chart_on_time,
            self.chart_productivity,
            self.chart_backlog,
            self.chart_duration,
            self.chart_heatmap,
            self.chart_funnel,
        ):
            bitmap.SetBitmap(wx.NullBitmap)
        self.advice.SetLabel("No data yet. Track time and refresh statistics.")

    def _to_bitmap(self, fig) -> wx.Bitmap:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            fig.savefig(tmp.name, bbox_inches="tight")
            bitmap = wx.Bitmap(tmp.name, wx.BITMAP_TYPE_PNG)
        plt.close(fig)
        return bitmap

    def update_charts(self, stats, entries, kpis, start: date, end: date) -> None:
        if not stats:
            self.clear()
            return

        try:
            # Hours by activity
            fig1, ax1 = plt.subplots(figsize=(5, 3))
            bars = ax1.bar([s.activity_name for s in stats], [s.total_hours for s in stats], color=SECONDARY)
            ax1.set_title("Hours by activity")
            ax1.bar_label(bars, fmt="{:.1f}h")
            ax1.set_ylabel("Hours")
            ax1.set_xlabel("Activity")
            fig1.autofmt_xdate(rotation=25)
            self.chart_hours.SetBitmap(self._to_bitmap(fig1))

            # Planned vs actual per day
            per_day_actual: Dict[str, float] = {}
            per_day_planned: Dict[str, float] = {}
            for entry_date, _activity, hours, _obj, target, *_rest in entries:
                per_day_actual[entry_date] = per_day_actual.get(entry_date, 0.0) + (hours or 0.0)
                per_day_planned[entry_date] = per_day_planned.get(entry_date, 0.0) + (target or 0.0)
            days_sorted = sorted(per_day_actual.keys())
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            ax2.plot(days_sorted, [per_day_actual[d] for d in days_sorted], marker="o", color=SECONDARY, label="Actual")
            ax2.plot(days_sorted, [per_day_planned.get(d, 0.0) for d in days_sorted], marker="s", color=ACCENT, label="Planned")
            ax2.set_title("Planned vs actual")
            ax2.set_ylabel("Hours")
            ax2.legend()
            fig2.autofmt_xdate(rotation=25)
            self.chart_planned.SetBitmap(self._to_bitmap(fig2))

            # Focus trend line
            focus_by_day: Dict[str, float] = {}
            for entry_date, _activity, hours, _obj, _target, completion, *_rest in entries:
                if hours:
                    focus = hours * ((completion or 0.0) / 100)
                    focus_by_day.setdefault(entry_date, 0.0)
                    focus_by_day[entry_date] += focus
            focus_days = sorted(focus_by_day.keys())
            fig3, ax3 = plt.subplots(figsize=(5, 3))
            ratios = []
            for d in focus_days:
                actual = per_day_actual.get(d, 0.0)
                ratio = (focus_by_day[d] / actual * 100) if actual else 0
                ratios.append(ratio)
            ax3.plot(focus_days, ratios, marker="o", color="#2ecc71")
            ax3.set_title("Focus ratio")
            ax3.set_ylabel("% of deep work")
            fig3.autofmt_xdate(rotation=25)
            self.chart_focus.SetBitmap(self._to_bitmap(fig3))

            # Category distribution
            category_hours: Dict[str, float] = {}
            for _date, activity_name, hours, *_rest in entries:
                category_hours[activity_name] = category_hours.get(activity_name, 0.0) + (hours or 0.0)
            fig4, ax4 = plt.subplots(figsize=(4.5, 3))
            labels = list(category_hours.keys())
            values = list(category_hours.values())
            ax4.pie(values, labels=labels, autopct="%1.0f%%", colors=plt.cm.tab20.colors)
            ax4.set_title("Category mix")
            self.chart_category.SetBitmap(self._to_bitmap(fig4))

            # Completion rate pie
            total_tasks = len(entries)
            completed = sum(1 for _d, _a, _h, _o, _t, completion, *_r in entries if (completion or 0) >= 100)
            fig5, ax5 = plt.subplots(figsize=(4, 3))
            ax5.pie([completed, max(total_tasks - completed, 0)], labels=["Done", "Remaining"], autopct="%1.0f%%")
            ax5.set_title("Task completion rate")
            self.chart_completion.SetBitmap(self._to_bitmap(fig5))

            # On-time vs late (heuristic)
            on_time = sum(1 for _d, _a, _h, _o, target, completion, *_r in entries if target and (completion or 0) >= 100)
            late = max(total_tasks - on_time, 0)
            fig6, ax6 = plt.subplots(figsize=(4, 3))
            ax6.bar(["On time", "Late"], [on_time, late], color=[ACCENT, "#D0021B"])
            ax6.set_title("On-time vs late")
            self.chart_on_time.SetBitmap(self._to_bitmap(fig6))

            # Productivity score trend
            score_by_day: Dict[str, float] = {}
            for entry_date, _a, hours, _o, _t, completion, *_r in entries:
                focused = hours * ((completion or 0.0) / 100) if hours else 0.0
                score_by_day.setdefault(entry_date, 0.0)
                score_by_day[entry_date] += focused
            score_days = sorted(score_by_day.keys())
            fig7, ax7 = plt.subplots(figsize=(5, 3))
            ax7.plot(score_days, [score_by_day[d] for d in score_days], marker="o", color=SECONDARY)
            ax7.set_title("Daily productivity score")
            ax7.set_ylabel("Score (focused hrs)")
            fig7.autofmt_xdate(rotation=25)
            self.chart_productivity.SetBitmap(self._to_bitmap(fig7))

            # Backlog evolution (cumulative remaining)
            backlog = []
            cumulative = 0
            for day in score_days:
                daily_total = sum(1 for d, *_r in entries if d == day)
                daily_done = sum(1 for d, _a, _h, _o, _t, c, *_r in entries if d == day and (c or 0) >= 100)
                cumulative += max(daily_total - daily_done, 0)
                backlog.append((day, cumulative))
            fig8, ax8 = plt.subplots(figsize=(5, 3))
            if backlog:
                ax8.plot([d for d, _v in backlog], [v for _d, v in backlog], color=SECONDARY, marker="o")
            ax8.set_title("Backlog evolution")
            ax8.set_ylabel("Open tasks")
            fig8.autofmt_xdate(rotation=25)
            self.chart_backlog.SetBitmap(self._to_bitmap(fig8))

            # Average duration by activity
            durations: Dict[str, list] = {}
            for _date, activity_name, hours, *_r in entries:
                durations.setdefault(activity_name, []).append(hours or 0.0)
            fig9, ax9 = plt.subplots(figsize=(5, 3))
            labels = list(durations.keys())
            values = [sum(v) / len(v) if v else 0.0 for v in durations.values()]
            ax9.barh(labels, values, color=ACCENT)
            ax9.set_title("Average task duration by category")
            ax9.set_xlabel("Hours")
            self.chart_duration.SetBitmap(self._to_bitmap(fig9))

            # Heatmap placeholder
            fig10, ax10 = plt.subplots(figsize=(5, 3))
            data = [[min(1 + i + j, 10) for j in range(7)] for i in range(6)]
            cax = ax10.imshow(data, cmap="Blues")
            ax10.set_title("Productivity heatmap")
            fig10.colorbar(cax)
            self.chart_heatmap.SetBitmap(self._to_bitmap(fig10))

            # Task funnel
            fig11, ax11 = plt.subplots(figsize=(4, 3))
            todo = sum(1 for _ in entries)
            reopened = max(0, int(completed * 0.1))
            values = [max(todo - completed, 0), max(todo // 2, 1), completed, reopened]
            ax11.bar(["Todo", "In Progress", "Completed", "Reopened"], values, color=[SECONDARY, ACCENT, "#27AE60", "#F5A623"])
            ax11.set_title("Task funnel")
            self.chart_funnel.SetBitmap(self._to_bitmap(fig11))

            advice_lines = [
                f"Planned vs actual: {kpis.get('planned_vs_actual', 'N/A')}",
                f"Focus ratio: {kpis.get('focus_ratio', 'N/A')}",
                f"Switches: {kpis.get('switches', '0')} (lower is better)",
                f"Overtime: {kpis.get('overtime', '0h')}",
                f"Completion rate: {kpis.get('completion_rate', 'N/A')}",
                f"Productivity score: {kpis.get('productivity_score', 'N/A')}",
            ]
            self.advice.SetLabel("\n".join(advice_lines))
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Failed to render floating charts")
            self.advice.SetLabel(f"Charts unavailable: {exc}")
            for bitmap in (
                self.chart_hours,
                self.chart_planned,
                self.chart_focus,
                self.chart_category,
                self.chart_completion,
                self.chart_on_time,
                self.chart_productivity,
                self.chart_backlog,
                self.chart_duration,
                self.chart_heatmap,
                self.chart_funnel,
            ):
                bitmap.SetBitmap(wx.NullBitmap)

    def _date_range(self) -> tuple[date, date]:
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
            entries = self.controller.get_entries_between(start, end)
            kpis = self.controller.get_kpis(start, end)
            if not stats:
                self.clear()
                self.advice.SetLabel("No data in selected range. Track sessions to see visuals.")
                return
            self.update_charts(stats, entries, kpis, start, end)
            self.present()
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Floating stats refresh failed")
            wx.MessageBox(
                f"Unable to refresh floating charts.\n\n{exc}\nCheck matplotlib/wxPython availability and database access.",
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

    def _build_ui(self) -> None:
        self.SetBackgroundColour(SURFACE)
        main = wx.BoxSizer(wx.VERTICAL)

        # Range and actions
        range_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.range_choice = wx.Choice(self, choices=["Last 7 days", "Last 30 days", "All time"])
        self.range_choice.SetSelection(0)
        self.range_choice.SetToolTip("Choose how far back to analyze your work")
        range_sizer.Add(wx.StaticText(self, label="Range"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        range_sizer.Add(self.range_choice, 0, wx.ALL, 4)
        refresh_btn = wx.Button(self, label="Refresh charts")
        refresh_btn.SetBackgroundColour(SECONDARY)
        refresh_btn.SetForegroundColour("white")
        refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        range_sizer.Add(refresh_btn, 0, wx.ALL, 4)
        export_btn = wx.Button(self, label="Export Excel")
        export_btn.SetBackgroundColour(SECONDARY)
        export_btn.SetForegroundColour("white")
        export_btn.SetToolTip("Write raw data and KPIs to statistics.xlsx")
        export_btn.Bind(wx.EVT_BUTTON, self.on_export)
        range_sizer.Add(export_btn, 0, wx.ALL, 4)
        main.Add(range_sizer, 0, wx.EXPAND)

        header = wx.StaticText(self, label="Time management visuals")
        header.SetForegroundColour(TEXT_ON_DARK)
        main.Add(header, 0, wx.ALL, 6)

        self.chart_hours = wx.StaticBitmap(self)
        self.chart_planned = wx.StaticBitmap(self)
        self.chart_focus = wx.StaticBitmap(self)
        self.chart_category = wx.StaticBitmap(self)
        self.chart_completion = wx.StaticBitmap(self)
        self.chart_on_time = wx.StaticBitmap(self)
        self.chart_productivity = wx.StaticBitmap(self)
        self.chart_backlog = wx.StaticBitmap(self)
        self.chart_duration = wx.StaticBitmap(self)
        self.chart_heatmap = wx.StaticBitmap(self)
        self.chart_funnel = wx.StaticBitmap(self)

        for label_text, bitmap in (
            ("Hours by activity", self.chart_hours),
            ("Planned vs actual", self.chart_planned),
            ("Focus trend", self.chart_focus),
            ("Category mix", self.chart_category),
            ("Task completion rate", self.chart_completion),
            ("On-time vs late", self.chart_on_time),
            ("Productivity trend", self.chart_productivity),
            ("Backlog evolution", self.chart_backlog),
            ("Avg duration by category", self.chart_duration),
            ("Productivity heatmap", self.chart_heatmap),
            ("Task funnel", self.chart_funnel),
        ):
            box = wx.StaticBox(self, label=label_text)
            box.SetForegroundColour(TEXT_ON_DARK)
            sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
            sizer.Add(bitmap, 1, wx.EXPAND | wx.ALL, 4)
            main.Add(sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.advice = wx.StaticText(self, label="Charts will appear after refresh.")
        self.advice.SetForegroundColour(MUTED)
        main.Add(self.advice, 0, wx.ALL, 6)

        self.SetSizer(main)


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
        self.comments = ""
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

        comments_label = wx.StaticText(self, label="Comments / notes")
        comments_label.SetForegroundColour(ACCENT)
        self.comments_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(400, 80))
        self.comments_ctrl.SetToolTip("Add reflections or context that will appear in statistics exports")
        main_sizer.Add(comments_label, 0, wx.ALL, 6)
        main_sizer.Add(self.comments_ctrl, 0, wx.EXPAND | wx.ALL, 6)

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
        self.comments = self.comments_ctrl.GetValue().strip()
        self.EndModal(wx.ID_OK)

    def get_values(self) -> tuple[str, float, str, str]:
        return self.objectives, self.completion_percent, self.stop_reason, self.comments


class ActivityDialog(wx.Dialog):
    """Dialog to capture activity details including description and default plan."""

    def __init__(self, parent: wx.Window, title: str, name: str = "", description: str = "", target: float = 1.0):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        name_row = wx.BoxSizer(wx.HORIZONTAL)
        name_row.Add(wx.StaticText(self, label="Name"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        self.name_ctrl = wx.TextCtrl(self, value=name, size=(280, -1))
        self.name_ctrl.SetToolTip("Short label that will appear in lists and stats")
        name_row.Add(self.name_ctrl, 1, wx.ALL, 6)
        main_sizer.Add(name_row, 0, wx.EXPAND)

        desc_label = wx.StaticText(self, label="Description")
        desc_label.SetForegroundColour(ACCENT)
        self.desc_ctrl = wx.TextCtrl(self, value=description, style=wx.TE_MULTILINE, size=(360, 120))
        self.desc_ctrl.SetToolTip("Add context so help popovers can guide you later")
        main_sizer.Add(desc_label, 0, wx.ALL, 6)
        main_sizer.Add(self.desc_ctrl, 1, wx.EXPAND | wx.ALL, 6)

        target_row = wx.BoxSizer(wx.HORIZONTAL)
        target_row.Add(wx.StaticText(self, label="Default plan (hours)"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        self.target_ctrl = wx.SpinCtrlDouble(self, min=0, max=24, inc=0.25, initial=target)
        self.target_ctrl.SetToolTip("Pre-fill planned time when you start the timer")
        target_row.Add(self.target_ctrl, 0, wx.ALL, 6)
        main_sizer.Add(target_row, 0, wx.EXPAND)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
        self.SetSizerAndFit(main_sizer)

    def get_values(self) -> tuple[str, str, float]:
        return self.name_ctrl.GetValue(), self.desc_ctrl.GetValue(), self.target_ctrl.GetValue()


class MainPanel(wx.ScrolledWindow):
    def __init__(self, parent: wx.Window, controller: AppController, config_manager: ConfigManager):
        super().__init__(parent, style=wx.VSCROLL | wx.HSCROLL)
        self.controller = controller
        self.config_manager = config_manager
        self.selected_activity: Optional[int] = config_manager.config.last_selected_activity
        self.active_targets: Dict[int, float] = {}
        self.mgr: Optional[wx.aui.AuiManager] = None
        self.current_user_id = "default-user"
        self.task_windows: Dict[int, "TaskFrame"] = {}
        self.SetScrollRate(10, 10)
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

    def _build_ribbon(self) -> wx.ToolBar:
        """Create a toolbar-style ribbon for quick access to panes and actions."""
        ribbon = wx.ToolBar(self, style=wx.TB_HORIZONTAL | wx.TB_TEXT | wx.TB_FLAT)
        ribbon.SetToolBitmapSize((24, 24))
        ribbon.SetToolSeparation(6)

        def add_tool(label: str, art: str, handler, help_str: str) -> None:
            tool_id = wx.NewIdRef()
            bitmap = wx.ArtProvider.GetBitmap(art, wx.ART_TOOLBAR, (24, 24))
            ribbon.AddTool(tool_id, label, bitmap, help=help_str)
            self.Bind(wx.EVT_TOOL, handler, id=tool_id)

        add_tool("Activities", wx.ART_LIST_VIEW, lambda evt: self._show_pane("activities", dock=True), "Show the activities pane")
        add_tool("Timer", wx.ART_REPORT_VIEW, lambda evt: self._show_pane("session", dock=True), "Show the focus timer")
        add_tool("Insights", wx.ART_NORMAL_FILE, lambda evt: self._show_pane("insights", dock=True), "Open Today/History/Stats tab")
        add_tool("Objectives", wx.ART_TIP, lambda evt: self._show_pane("objectives", floatable=True), "Open objectives & notes")
        add_tool("Charts", wx.ART_FIND, lambda evt: self._show_pane("stats_charts", floatable=True), "Show floating charts")
        add_tool("Guide", wx.ART_HELP, lambda evt: self._show_pane("guide", floatable=True), "Open help & motivation")
        add_tool("Export", wx.ART_FILE_SAVE, self._ribbon_export, "Export Excel report for the active range")
        add_tool("AI plan", wx.ART_EXECUTABLE_FILE, self._handle_ai_assist, "Ask AI to plan and prioritize")
        add_tool("Task window", wx.ART_GO_FORWARD, self._open_task_window_from_ribbon, "Pop out the selected task as its own window")
        add_tool("Restore", wx.ART_UNDO, self._restore_layout, "Show any hidden panes")
        ribbon.Realize()
        return ribbon

    def _build_ui(self) -> None:
        self.SetBackgroundColour(BACKGROUND)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.quote_of_day = random.choice(MOTIVATION)

        header = wx.Panel(self)
        header.SetBackgroundColour(PRIMARY)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(header, label="Study Tracker")
        title.SetForegroundColour("white")
        title_font = title.GetFont()
        title_font.PointSize += 4
        title_font.MakeBold()
        title.SetFont(title_font)
        subtitle = wx.StaticText(header, label=self.quote_of_day)
        subtitle.SetForegroundColour("#e0f2fe")
        subtitle.Wrap(360)
        layout_label = wx.StaticText(header, label="Layout")
        layout_label.SetForegroundColour("white")
        self.layout_choice = wx.Choice(
            header, choices=["Balanced grid", "Focus timer", "Wide stats", "Floating tasks"]
        )
        # Default to the floating, minimal trio layout so key panes are visible side by side
        self.layout_choice.SetSelection(3)
        self.layout_choice.Bind(wx.EVT_CHOICE, self.on_layout_choice)
        self.layout_choice.SetToolTip("Switch between preset docked layouts")
        help_btn = wx.Button(header, label="Help")
        help_btn.SetBackgroundColour(SECONDARY)
        help_btn.SetForegroundColour("white")
        help_btn.Bind(wx.EVT_BUTTON, self._show_help)
        help_btn.SetToolTip("Learn how to add activities, track time, and export stats")
        ai_btn = wx.Button(header, label="AI Assist")
        ai_btn.SetBackgroundColour(ACCENT)
        ai_btn.SetForegroundColour("#0b1220")
        ai_btn.Bind(wx.EVT_BUTTON, self._handle_ai_assist)
        ai_btn.SetToolTip("Use TensorFlow helpers to suggest duration, priority, and a daily plan")
        show_btn = wx.Button(header, label="Show windows")
        show_btn.SetBackgroundColour(SECONDARY)
        show_btn.SetForegroundColour("white")
        show_btn.Bind(wx.EVT_BUTTON, self._restore_layout)
        show_btn.SetToolTip("Reveal all docked windows if they were hidden")
        reset_btn = wx.Button(header, label="Reset layout")
        reset_btn.SetBackgroundColour(SECONDARY)
        reset_btn.SetForegroundColour("white")
        reset_btn.Bind(wx.EVT_BUTTON, self._on_reset_layout)
        reset_btn.SetToolTip("Return to the default floating layout")
        header_sizer.Add(title, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        header_sizer.Add(subtitle, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        header_sizer.AddStretchSpacer()
        header_sizer.Add(layout_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(self.layout_choice, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(ai_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(show_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(reset_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header_sizer.Add(help_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        header.SetSizer(header_sizer)
        main_sizer.Add(header, 0, wx.EXPAND)

        ribbon = self._build_ribbon()
        main_sizer.Add(ribbon, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)

        dock_host = wx.Panel(self)
        dock_host.SetBackgroundColour(BACKGROUND)
        dock_host.SetMinSize((1100, 760))
        self.mgr = wx.aui.AuiManager(dock_host)

        self.activities_panel = self._build_activities_panel(dock_host)
        self.session_panel = self._build_session_panel(dock_host)
        self.objectives_panel = self._build_objectives_panel(dock_host)
        self.stats_charts_panel = StatsChartsPanel(dock_host, self.controller)
        self.tabs_panel = self._build_tabs_panel(dock_host, self.stats_charts_panel)
        self.guide_panel = self._build_guide_panel(dock_host)

        self._setup_docking()

        main_sizer.Add(dock_host, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

    def _setup_docking(self) -> None:
        assert self.mgr is not None
        self.stats_charts_panel.attach_manager(self.mgr)
        self.mgr.AddPane(
            self.activities_panel,
            wx.aui.AuiPaneInfo()
            .Name("activities")
            .Caption("Activities")
            .Left()
            .BestSize(360, 520)
            .MinSize(320, 500)
            .CloseButton(False)
            .DestroyOnClose(False)
            .Floatable(True)
            .Movable(True)
            .Float()
            .Show(True),
        )
        self.mgr.AddPane(
            self.session_panel,
            wx.aui.AuiPaneInfo()
            .Name("session")
            .Caption("Focus session")
            .CenterPane()
            .BestSize(560, 340)
            .CloseButton(False)
            .DestroyOnClose(False),
        )
        self.mgr.AddPane(
            self.objectives_panel,
            wx.aui.AuiPaneInfo()
            .Name("objectives")
            .Caption("Objectives & notes")
            .Bottom()
            .BestSize(520, 240)
            .CloseButton(False)
            .DestroyOnClose(False)
            .Floatable(True)
            .Float()
            .Show(True),
        )
        self.mgr.AddPane(
            self.tabs_panel,
            wx.aui.AuiPaneInfo()
            .Name("insights")
            .Caption("Today, history & stats")
            .Right()
            .BestSize(560, 440)
            .CloseButton(False)
            .DestroyOnClose(False)
            .Floatable(True)
            .Float()
            .Show(True),
        )
        self.mgr.AddPane(
            self.stats_charts_panel,
            wx.aui.AuiPaneInfo()
            .Name("stats_charts")
            .Caption("Floating charts")
            .Right()
            .BestSize(640, 620)
            .Floatable(True)
            .DestroyOnClose(False)
            .Float()
            .Show(True),
        )
        self.mgr.AddPane(
            self.guide_panel,
            wx.aui.AuiPaneInfo()
            .Name("guide")
            .Caption("Help & motivation")
            .Bottom()
            .BestSize(520, 220)
            .CloseButton(True)
            .DestroyOnClose(False)
            .Floatable(True)
            .Float()
            .Show(True),
        )
        self._capture_layouts()

    def _capture_layouts(self) -> None:
        """Create perspectives with a minimal floating default of three panes."""
        assert self.mgr is not None
        panes = ["activities", "session", "insights", "objectives", "stats_charts", "guide"]

        # Default: three visible panes side by side (floating-capable)
        for name in panes:
            pane = self.mgr.GetPane(name)
            if pane.IsOk():
                pane.Show(name in {"activities", "session", "insights"})
        self.mgr.GetPane("activities").Left().BestSize(320, 520)
        self.mgr.GetPane("session").CenterPane().BestSize(520, 340)
        self.mgr.GetPane("insights").Right().BestSize(520, 440)
        self.mgr.GetPane("objectives").Bottom().BestSize(480, 220)
        self.mgr.GetPane("stats_charts").Float().BestSize(640, 460)
        self.mgr.GetPane("guide").Float().BestSize(480, 180)
        self.mgr.Update()
        self.perspectives = {"Floating tasks": self.mgr.SavePerspective()}

        # Balanced grid: keep objectives visible, charts floating
        for name in panes:
            pane = self.mgr.GetPane(name)
            if pane.IsOk():
                pane.Show(name in {"activities", "session", "insights", "objectives"})
        self.mgr.GetPane("stats_charts").Float().Show(True)
        self.mgr.GetPane("guide").Bottom().Show(True)
        self.mgr.Update()
        self.perspectives["Balanced grid"] = self.mgr.SavePerspective()

        # Focused timer layout
        self.mgr.GetPane("activities").Left().BestSize(220, 500).Show(True)
        self.mgr.GetPane("insights").Bottom().BestSize(700, 260).Show(True)
        self.mgr.GetPane("objectives").Right().BestSize(360, 260).Show(True)
        self.mgr.GetPane("stats_charts").Float().BestSize(520, 420).Show(False)
        self.mgr.GetPane("guide").Show(False)
        self.mgr.Update()
        self.perspectives["Focus timer"] = self.mgr.SavePerspective()

        # Stats-heavy layout
        self.mgr.GetPane("activities").Right().BestSize(200, 400).Show(True)
        self.mgr.GetPane("insights").CenterPane().Show(True)
        self.mgr.GetPane("session").Top().BestSize(520, 220).Show(True)
        self.mgr.GetPane("objectives").Bottom().BestSize(520, 180).Show(True)
        self.mgr.GetPane("stats_charts").Right().BestSize(620, 420).Show(True)
        self.mgr.GetPane("guide").Show(False)
        self.mgr.Update()
        self.perspectives["Wide stats"] = self.mgr.SavePerspective()

        # Restore default (floating trio)
        self.mgr.LoadPerspective(self.perspectives.get("Floating tasks"))
        self.mgr.Update()

    def _restore_layout(self, event: Optional[wx.CommandEvent]) -> None:
        """Resurface any hidden panes so users can re-open closed windows."""
        if not self.mgr:
            return
        for name in ["activities", "session", "insights"]:
            self._show_pane(name, dock=True)
        for name in ["objectives", "stats_charts", "guide"]:
            self._show_pane(name, floatable=True)

    def _on_reset_layout(self, event: Optional[wx.CommandEvent]) -> None:
        if self.mgr and getattr(self, "perspectives", None):
            target = self.perspectives.get("Floating tasks") or self.perspectives.get("Balanced grid")
            if target:
                self.mgr.LoadPerspective(target)
                self.mgr.Update()
                idx = self.layout_choice.FindString("Floating tasks")
                if idx != wx.NOT_FOUND:
                    self.layout_choice.SetSelection(idx)

    def on_layout_choice(self, event: wx.CommandEvent) -> None:
        choice = self.layout_choice.GetStringSelection()
        if self.mgr and choice in getattr(self, "perspectives", {}):
            self.mgr.LoadPerspective(self.perspectives[choice])
            self.mgr.Update()

    def _show_pane(self, name: str, dock: bool = False, floatable: bool = False) -> None:
        if not self.mgr:
            return
        pane = self.mgr.GetPane(name)
        if not pane.IsOk():
            return
        pane.Show(True)
        if dock:
            pane.Dock()
        if floatable and pane.IsFloatable():
            pane.Float()
        self.mgr.Update()

    def _ribbon_export(self, event: wx.CommandEvent) -> None:
        try:
            start = date.today() - timedelta(days=29)
            end = date.today()
            path = self.controller.export_to_excel(start, end)
            wx.MessageBox(f"Exported statistics to {path}", "Export complete")
        except Exception as exc:  # pragma: no cover - UI path
            LOGGER.exception("Ribbon export failed")
            wx.MessageBox(
                f"Excel export failed.\n\n{exc}\nClose any open Excel file and verify write access.",
                "Export error",
                style=wx.ICON_ERROR,
            )

    def _open_task_window_from_ribbon(self, event: wx.CommandEvent) -> None:
        self.on_open_task_window(event)

    def _handle_ai_assist(self, event: wx.CommandEvent) -> None:
        selected = self._require_selection()
        if selected is None:
            return
        activity = next((a for a in self.controller.list_activities() if a.id == selected), None)
        if activity is None:
            wx.MessageBox("Select a valid activity to ask AI for suggestions.", "AI Assistant")
            return
        duration = self.ai.suggest_duration(activity.name, "", "General", "Medium")
        priority = self.ai.suggest_priority(activity.name, None, "General")
        plan = self.ai.generate_daily_plan(date.today())
        insights = self.ai.analyze_patterns()
        plan_lines = "\n".join(f"- {p['start']}: {p['title']}" for p in plan) if plan else "No plan available."
        insight_text = "\n".join(insights)
        wx.MessageBox(
            (
                f"AI suggestions for {activity.name}:\n\n"
                f"Estimated duration: {duration:.1f}h\n"
                f"Suggested priority: {priority}\n\n"
                f"Plan:\n{plan_lines}\n\n"
                f"Insights:\n{insight_text}"
            ),
            "AI Assistant",
        )

    def _show_help(self, event: Optional[wx.CommandEvent]) -> None:
        wx.MessageBox(
            (
                "Welcome to Study Tracker!\n\n"
                "• Add or edit activities from the left list (right-click for quick actions).\n"
                "• Select one, set a plan, and press Start. Pause/Stop anytime; you’ll be asked for objectives and completion.\n"
                "• Today tab shows what you logged; History filters by range and activity.\n"
                "• Statistics tab renders charts and exports Excel (close the file before exporting).\n"
                "• Use Layout to snap panes or drag cards like a dashboard."
            ),
            "How to use Study Tracker",
        )

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
        self.activity_list.InsertColumn(2, "Plan")
        self.activity_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_activity_selected)
        self.activity_list.Bind(wx.EVT_CONTEXT_MENU, self.on_activity_context)
        self.activity_list.SetToolTip("Select or right-click to manage activities and timers")
        left_sizer.Add(self.activity_list, 1, wx.EXPAND | wx.ALL, 4)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(left_card, label="Add")
        edit_btn = wx.Button(left_card, label="Edit")
        del_btn = wx.Button(left_card, label="Delete")
        for btn in (add_btn, edit_btn, del_btn):
            btn.SetBackgroundColour(SECONDARY)
            btn.SetForegroundColour("white")
            font = btn.GetFont()
            font.PointSize += 1
            btn.SetFont(font)
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_activity)
        edit_btn.Bind(wx.EVT_BUTTON, self.on_edit_activity)
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_activity)
        add_btn.SetToolTip("Create a new activity to track")
        edit_btn.SetToolTip("Rename the selected activity")
        del_btn.SetToolTip("Remove the selected activity")
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
        self.target_input.SetToolTip("Set your target duration for this activity")
        target_row.Add(self.target_input, 0, wx.ALL, 4)
        self.progress = wx.Gauge(timer_card, range=100)
        self.progress.SetToolTip("Progress against the planned hours")
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
            btn.SetBackgroundColour(SECONDARY)
            btn.SetForegroundColour("white")
            font = btn.GetFont()
            font.PointSize += 1
            btn.SetFont(font)
            btn_panel.Add(btn, 1, wx.ALL, 4)
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start)
        self.pause_btn.Bind(wx.EVT_BUTTON, self.on_pause)
        self.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        self.reset_btn.Bind(wx.EVT_BUTTON, self.on_reset)
        self.start_btn.SetToolTip("Begin tracking the selected activity")
        self.pause_btn.SetToolTip("Pause without logging yet")
        self.stop_btn.SetToolTip("Stop and log completion details")
        self.reset_btn.SetToolTip("Reset today’s timer for this activity")
        timer_sizer.Add(btn_panel, 0, wx.EXPAND)
        timer_card.SetSizer(timer_sizer)
        return timer_card

    def _build_objectives_panel(self, host: wx.Window) -> wx.Panel:
        objectives_card, obj_sizer = self._make_card("Objectives & notes", host)
        self.objectives = wx.TextCtrl(objectives_card, style=wx.TE_MULTILINE | wx.BORDER_NONE)
        self.objectives.SetToolTip("Capture objectives, wins, blockers, or notes for today")
        obj_sizer.Add(self.objectives, 1, wx.EXPAND | wx.ALL, 4)
        objectives_card.SetSizer(obj_sizer)
        return objectives_card

    def _build_tabs_panel(self, host: wx.Window, charts_panel: "StatsChartsPanel") -> wx.Panel:
        panel = wx.Panel(host)
        panel.SetBackgroundColour(BACKGROUND)
        sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(panel)
        today_panel = wx.Panel(notebook)
        today_panel.SetBackgroundColour(SURFACE)
        today_sizer = wx.BoxSizer(wx.VERTICAL)
        self.today_list = wx.ListCtrl(today_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        for i, heading in enumerate(["Date", "Activity", "Hours", "Target", "%", "Objectives", "Reason", "Comments"]):
            self.today_list.InsertColumn(i, heading)
        self.today_list.SetToolTip("What you tracked today including targets, objectives, and reasons")
        refresh_today = wx.Button(today_panel, label="Refresh Today")
        refresh_today.SetBackgroundColour(SECONDARY)
        refresh_today.SetForegroundColour("white")
        refresh_today.Bind(wx.EVT_BUTTON, lambda evt: self.refresh_today())
        today_sizer.Add(refresh_today, 0, wx.ALL, 4)

        ai_box = wx.BoxSizer(wx.VERTICAL)
        ai_header = wx.BoxSizer(wx.HORIZONTAL)
        ai_header.Add(wx.StaticText(today_panel, label="AI productivity score"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.productivity_label = wx.StaticText(today_panel, label="--")
        self.productivity_label.SetForegroundColour(ACCENT)
        ai_header.Add(self.productivity_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        refresh_ai = wx.Button(today_panel, label="Refresh AI")
        refresh_ai.SetBackgroundColour(SECONDARY)
        refresh_ai.SetForegroundColour("white")
        refresh_ai.SetToolTip("Predict today’s productivity and fetch insights")
        refresh_ai.Bind(wx.EVT_BUTTON, self.on_refresh_ai)
        ai_header.Add(refresh_ai, 0, wx.ALL, 4)
        ai_box.Add(ai_header, 0, wx.EXPAND)
        self.insights_ctrl = wx.TextCtrl(
            today_panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE,
            value="AI insights will appear here once available.",
            size=(-1, 80),
        )
        self.insights_ctrl.SetBackgroundColour(SURFACE)
        self.insights_ctrl.SetForegroundColour(TEXT_ON_DARK)
        ai_box.Add(self.insights_ctrl, 0, wx.EXPAND | wx.ALL, 4)
        today_sizer.Add(ai_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        today_sizer.Add(self.today_list, 1, wx.EXPAND | wx.ALL, 4)
        today_panel.SetSizer(today_sizer)

        self.history_tab = HistoryPanel(notebook, self.controller)
        self.history_tab.SetBackgroundColour(SURFACE)
        self.stats_tab = StatsPanel(notebook, self.controller, charts_panel)
        self.stats_tab.SetBackgroundColour(SURFACE)
        notebook.AddPage(today_panel, "Today")
        notebook.AddPage(self.history_tab, "History")
        notebook.AddPage(self.stats_tab, "Statistics")
        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 4)
        panel.SetSizer(sizer)
        return panel

    def _build_guide_panel(self, host: wx.Window) -> wx.Panel:
        panel, sizer = self._make_card("Guide & motivation", host)
        steps = wx.StaticText(
            panel,
            label=(
                "1) Add an activity with the Add button or right-click the list.\n"
                "2) Select an activity, set a plan, then Start to track.\n"
                "3) Stop or auto-finish to log objectives, completion %, and reasons.\n"
                "4) Browse Today/History for details and Statistics for charts.\n"
                "5) Export Excel from Statistics for sharing."
            ),
        )
        steps.SetForegroundColour(TEXT_ON_DARK)
        steps.SetToolTip("Quick how-to covering activities, timers, notes, and exports")
        sizer.Add(steps, 0, wx.ALL, 6)

        quote = wx.StaticText(panel, label=f"Motivation: {self.quote_of_day}")
        quote.SetForegroundColour(MUTED)
        sizer.Add(quote, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        help_link = wx.adv.HyperlinkCtrl(panel, id=wx.ID_ANY, label="Open detailed help", url="about:blank")
        help_link.SetNormalColour(SECONDARY)
        help_link.SetHoverColour(ACCENT)
        help_link.Bind(wx.adv.EVT_HYPERLINK, lambda evt: self._show_help(None))
        sizer.Add(help_link, 0, wx.ALL, 6)
        panel.SetSizer(sizer)
        return panel

    def refresh_today(self) -> None:
        def action() -> None:
            self.today_list.DeleteAllItems()
            for entry in self.controller.get_today_entries():
                idx = self.today_list.InsertItem(self.today_list.GetItemCount(), entry.date.isoformat())
                activity = next((a.name for a in self.controller.list_activities() if a.id == entry.activity_id), str(entry.activity_id))
                self.today_list.SetItem(idx, 1, activity)
                duration_hours = entry.duration_hours if entry.duration_hours is not None else 0.0
                target_hours = entry.target_hours if entry.target_hours is not None else 0.0
                completion_percent = entry.completion_percent if entry.completion_percent is not None else 0.0
                objectives = entry.objectives_succeeded or ""
                stop_reason = entry.stop_reason or ""
                comments = getattr(entry, "comments", "") or ""

                self.today_list.SetItem(idx, 2, f"{duration_hours:.2f}")
                self.today_list.SetItem(idx, 3, f"{target_hours:.2f}")
                self.today_list.SetItem(idx, 4, f"{completion_percent:.0f}%")
                self.today_list.SetItem(idx, 5, objectives)
                self.today_list.SetItem(idx, 6, stop_reason)
                self.today_list.SetItem(idx, 7, comments)
            for col in range(8):
                self.today_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)

        self._with_error_dialog("Loading today's entries", action)
        self.refresh_productivity()

    def refresh_productivity(self) -> None:
        def action() -> None:
            score = self.controller.predict_productivity(self.current_user_id, date.today())
            insights = self.controller.productivity_insights(
                self.current_user_id, (date.today() - timedelta(days=6), date.today())
            )
            self._update_productivity_ui(score, insights)

        self._with_error_dialog("Refreshing AI productivity", action)

    def on_refresh_ai(self, event: wx.Event) -> None:
        self.refresh_productivity()

    def _update_productivity_ui(self, score: float, insights: list[str]) -> None:
        label = f"{score:.2f}" if score is not None else "--"
        self.productivity_label.SetLabel(label)
        insight_text = "\n".join(insights) if insights else "No insights yet. Train or clone AI-Productivity-Tracker."
        self.insights_ctrl.SetValue(insight_text)

    def load_activities(self) -> None:
        def action() -> None:
            activities = self.controller.list_activities()
            today_entries = {e.activity_id: e for e in self.controller.get_today_entries()}
            self.activity_list.DeleteAllItems()
            for act in activities:
                idx = self.activity_list.InsertItem(self.activity_list.GetItemCount(), act.name)
                hours = today_entries.get(act.id).duration_hours if act.id in today_entries else 0.0
                self.activity_list.SetItem(idx, 1, f"{hours:.2f}h")
                self.activity_list.SetItem(idx, 2, f"{act.default_target_hours:.2f}h")
                self.activity_list.SetItemData(idx, act.id)
                if self.selected_activity == act.id:
                    self.activity_list.Select(idx)
            for col in range(3):
                self.activity_list.SetColumnWidth(col, wx.LIST_AUTOSIZE)
            self.history_tab.load_activities()
            self.refresh_today()

        self._with_error_dialog("Loading activities", action)

    def on_activity_selected(self, event: wx.ListEvent) -> None:
        idx = event.GetIndex()
        activity_id = self.activity_list.GetItemData(idx)
        act = next((a for a in self.controller.list_activities() if a.id == activity_id), None)
        if act:
            desc = act.description or "No description set."
            planned = f"Planned: {act.default_target_hours:.2f}h"
            self.activity_list.SetToolTip(f"{act.name}\n{desc}\n{planned}")

    def _activity_name(self, activity_id: int) -> str:
        activity = next((a.name for a in self.controller.list_activities() if a.id == activity_id), "Activity")
        return activity

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
            ("Log food break", self.on_food_break),
            ("Open task window", self.on_open_task_window),
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
        activity = next((a for a in self.controller.list_activities() if a.id == self.selected_activity), None)
        if activity and activity.default_target_hours:
            self.target_input.SetValue(activity.default_target_hours)
        self._load_objectives()

    def on_food_break(self, event: wx.CommandEvent) -> None:
        if self.selected_activity is None:
            wx.MessageBox("Select an activity to log a food break.", "Food break")
            return
        wx.MessageBox(
            "Food break logged. Remember to hydrate and return when ready!",
            "Food break",
        )

    def on_open_task_window(self, event: wx.CommandEvent) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        if activity_id in self.task_windows:
            self.task_windows[activity_id].Raise()
            return
        frame = TaskFrame(self, self.controller, self, activity_id)
        self.task_windows[activity_id] = frame
        frame.Show()

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
        dlg = ActivityDialog(self, "Add Activity")
        if dlg.ShowModal() == wx.ID_OK:
            name, desc, target = dlg.get_values()
            self._with_error_dialog(
                "Creating activity",
                lambda: self.controller.add_activity(name, description=desc, default_target_hours=target),
            )
            self.load_activities()
        dlg.Destroy()

    def on_edit_activity(self, event: wx.Event) -> None:
        activity_id = self._require_selection()
        if activity_id is None:
            return
        activity = next((a for a in self.controller.list_activities() if a.id == activity_id), None)
        if activity is None:
            return
        dlg = ActivityDialog(
            self,
            "Edit Activity",
            name=activity.name,
            description=activity.description,
            target=activity.default_target_hours,
        )
        if dlg.ShowModal() == wx.ID_OK:
            name, desc, target = dlg.get_values()
            self._with_error_dialog(
                "Updating activity",
                lambda: self.controller.update_activity(
                    activity_id, name=name, description=desc, default_target_hours=target
                ),
            )
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
        activity_name = self._activity_name(activity_id)
        target_hours = self.active_targets.get(activity_id, self.target_input.GetValue())
        dialog = wx.MessageDialog(
            self,
            (
                f"{activity_name}: planned time {target_hours:.2f}h reached.\n"
                f"You logged {elapsed / 3600.0:.2f}h. Extend or log now?\n\n"
                "• Extend keeps the timer running with +15 minutes.\n"
                "• Log now records the session with your objectives.\n"
                "• Remind later will nudge you again in 5 minutes."
            ),
            "Time finished",
            style=wx.YES_NO | wx.CANCEL | wx.ICON_INFORMATION,
        )
        dialog.SetYesNoLabels("Extend 15m", "Log now")
        choice = dialog.ShowModal()
        dialog.Destroy()

        if choice == wx.ID_YES:
            extension_hours = 0.25
            new_target = (elapsed / 3600.0) + extension_hours
            self.active_targets[activity_id] = new_target

            def tick_cb(elapsed_seconds: float) -> None:
                wx.CallAfter(self._update_timer_display, activity_id, elapsed_seconds)

            def on_complete(elapsed_seconds: float) -> None:
                wx.CallAfter(self._handle_timer_complete, activity_id, elapsed_seconds)

            self._with_error_dialog(
                "Extending timer",
                lambda: self.controller.start_timer(activity_id, tick_cb, new_target, on_complete),
            )
            return

        if choice == wx.ID_CANCEL:
            wx.CallLater(
                5 * 60 * 1000,
                lambda: wx.MessageBox(
                    f"Reminder: {activity_name} reached its plan. Log or extend when ready.",
                    "Reminder",
                ),
            )
            return

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
        objectives, completion_percent, stop_reason, comments = dialog.get_values()
        result = self._with_error_dialog(
            "Saving session",
            lambda: self.controller.finalize_timer(
                activity_id,
                objectives,
                target_hours,
                completion_percent,
                comments=comments,
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


class TaskFrame(wx.Frame):
    """Independent task window for Vector Canoe-like modular workflows."""

    def __init__(self, parent: wx.Window, controller: AppController, main_panel: MainPanel, activity_id: int):
        super().__init__(parent, title=f"Task: {main_panel._activity_name(activity_id)}", size=(420, 360))
        self.controller = controller
        self.main_panel = main_panel
        self.activity_id = activity_id
        self.SetBackgroundColour(CARD)
        self._build_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        heading = wx.StaticText(self, label=self.main_panel._activity_name(self.activity_id))
        heading_font = heading.GetFont()
        heading_font.MakeBold()
        heading_font.PointSize += 2
        heading.SetFont(heading_font)
        heading.SetForegroundColour(ACCENT)
        sizer.Add(heading, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 8)

        self.timer_label = wx.StaticText(self, label="00:00:00", style=wx.ALIGN_CENTER_HORIZONTAL)
        timer_font = self.timer_label.GetFont()
        timer_font.PointSize += 6
        self.timer_label.SetFont(timer_font)
        self.timer_label.SetForegroundColour(TEXT_ON_DARK)
        sizer.Add(self.timer_label, 0, wx.EXPAND | wx.ALL, 6)

        target_row = wx.BoxSizer(wx.HORIZONTAL)
        target_row.Add(wx.StaticText(self, label="Plan (hours)"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.target_input = wx.SpinCtrlDouble(self, min=0, max=24, inc=0.25, initial=1.0)
        target_row.Add(self.target_input, 0, wx.ALL, 4)
        self.progress = wx.Gauge(self, range=100)
        target_row.Add(self.progress, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        sizer.Add(target_row, 0, wx.EXPAND)

        btns = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (("Start", self.on_start), ("Pause", self.on_pause), ("Stop", self.on_stop)):
            btn = wx.Button(self, label=label)
            btn.SetBackgroundColour(SECONDARY)
            btn.SetForegroundColour("white")
            btn.Bind(wx.EVT_BUTTON, handler)
            btns.Add(btn, 1, wx.ALL, 4)
        sizer.Add(btns, 0, wx.EXPAND)

        hint = wx.StaticText(
            self,
            label="Floating task windows mirror the main dashboard but stay focused on a single activity.",
        )
        hint.SetForegroundColour(MUTED)
        sizer.Add(hint, 0, wx.ALL, 6)
        self.SetSizer(sizer)

    def _update_display(self, elapsed_seconds: float) -> None:
        hours = int(elapsed_seconds) // 3600
        minutes = (int(elapsed_seconds) % 3600) // 60
        seconds = int(elapsed_seconds) % 60
        self.timer_label.SetLabel(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        target = self.main_panel.active_targets.get(self.activity_id, self.target_input.GetValue())
        if target > 0:
            percent = min(100, int((elapsed_seconds / 3600.0) / target * 100))
            self.progress.SetValue(percent)
        else:
            self.progress.SetValue(0)

    def on_start(self, event: wx.CommandEvent) -> None:
        target_hours = self.target_input.GetValue()
        self.main_panel.active_targets[self.activity_id] = target_hours

        def tick_cb(elapsed: float) -> None:
            wx.CallAfter(self._update_display, elapsed)

        def on_complete(elapsed: float) -> None:
            wx.CallAfter(self.main_panel._handle_timer_complete, self.activity_id, elapsed)

        self.main_panel._with_error_dialog(
            "Starting timer",
            lambda: self.controller.start_timer(self.activity_id, tick_cb, target_hours, on_complete),
        )

    def on_pause(self, event: wx.CommandEvent) -> None:
        self.main_panel._with_error_dialog("Pausing timer", lambda: self.controller.pause_timer(self.activity_id))

    def on_stop(self, event: wx.CommandEvent) -> None:
        self.main_panel._complete_session(self.activity_id, "Stop session", allow_reason=True)

    def on_close(self, event: wx.CloseEvent) -> None:  # type: ignore[override]
        if self.activity_id in self.main_panel.task_windows:
            del self.main_panel.task_windows[self.activity_id]
        event.Skip()


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
