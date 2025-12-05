"""Statistics tab with chart rendering."""
from __future__ import annotations

import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from gi.repository import GdkPixbuf, Gtk


class StatsView(Gtk.Box):
    def __init__(self, controller):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.controller = controller
        self.add_css_class("card")

        range_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        range_box.add_css_class("range-box")
        self.range_combo = Gtk.ComboBoxText()
        for label in ["Last 7 days", "Last 30 days", "All time"]:
            self.range_combo.append_text(label)
        self.range_combo.set_active(0)
        self.range_combo.connect("changed", self.on_range_changed)
        range_box.append(Gtk.Label(label="Range:"))
        range_box.append(self.range_combo)
        self.append(range_box)

        self.kpi_label = Gtk.Label(label="")
        self.kpi_label.set_xalign(0)
        self.kpi_label.add_css_class("kpi-label")
        self.append(self.kpi_label)

        self.chart_image = Gtk.Image()
        self.chart_image.set_hexpand(True)
        self.chart_image.set_vexpand(True)
        self.append(self.chart_image)
        self.refresh()

    def _get_range(self):
        selection = self.range_combo.get_active_text()
        end_date = date.today()
        if selection == "Last 30 days":
            start_date = end_date - timedelta(days=30)
        elif selection == "All time":
            start_date = date(2000, 1, 1)
        else:
            start_date = end_date - timedelta(days=7)
        return start_date, end_date

    def refresh(self) -> None:
        start, end = self._get_range()
        stats = self.controller.get_stats(start, end)
        if not stats:
            self.kpi_label.set_text("No data available for selected range.")
            self.chart_image.clear()
            return
        total_hours = sum(item[1] for item in stats)
        avg_per_day = total_hours / max(1, (end - start).days + 1)
        top_three = ", ".join([name for name, *_ in stats[:3]])
        self.kpi_label.set_text(
            f"Total hours: {total_hours:.2f} | Avg per day: {avg_per_day:.2f} | Top: {top_three}"
        )
        self._render_chart(stats)

    def _render_chart(self, stats) -> None:
        activities = [row[0] for row in stats]
        totals = [row[1] for row in stats]
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.bar(activities, totals, color="#4c6ef5")
        ax.set_ylabel("Hours")
        ax.set_title("Hours by activity")
        ax.tick_params(axis="x", rotation=30)
        buf = io.BytesIO()
        fig.tight_layout()
        plt.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(buf.getvalue())
        loader.close()
        pixbuf = loader.get_pixbuf()
        self.chart_image.set_from_pixbuf(pixbuf)

    def on_range_changed(self, _combo) -> None:
        self.refresh()
