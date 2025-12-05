"""History tab showing daily entries."""
from __future__ import annotations

from datetime import date
from typing import Optional

from gi.repository import Gtk


class HistoryView(Gtk.Box):
    def __init__(self, controller):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.controller = controller
        self.add_css_class("card")

        filter_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        filter_box.add_css_class("range-box")
        self.start_entry = Gtk.Entry()
        self.start_entry.set_placeholder_text("Start YYYY-MM-DD")
        self.end_entry = Gtk.Entry()
        self.end_entry.set_placeholder_text("End YYYY-MM-DD")
        refresh_btn = Gtk.Button.new_with_label("Refresh")
        refresh_btn.set_icon_name("view-refresh-symbolic")
        refresh_btn.connect("clicked", self.on_refresh)

        for widget in (self.start_entry, self.end_entry, refresh_btn):
            filter_box.append(widget)
        self.append(filter_box)

        self.store = Gtk.ListStore(str, str, float, str)
        self.tree = Gtk.TreeView(model=self.store)
        for i, title in enumerate(["Date", "Activity", "Hours", "Objectives"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            column.set_resizable(True)
            self.tree.append_column(column)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self.tree)
        scrolled.add_css_class("tree-wrapper")
        self.append(scrolled)
        self.populate()

    def _parse_date(self, text: str) -> Optional[date]:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    def populate(self, start: Optional[date] = None, end: Optional[date] = None) -> None:
        self.store.clear()
        start_date = start or date.today().replace(day=1)
        end_date = end or date.today()
        for entry in self.controller.get_entries_between(start_date, end_date):
            self.store.append(list(entry))

    def on_refresh(self, _button) -> None:
        start = self._parse_date(self.start_entry.get_text())
        end = self._parse_date(self.end_entry.get_text())
        self.populate(start, end)
