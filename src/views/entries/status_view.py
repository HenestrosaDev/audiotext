from typing import Any

import customtkinter as ctk

from models.history import HistoryEntry
from views.entries.delegates import EntryDelegate
from views.entries.entry_header import EntryHeader
from views.entries.progress_card import ProgressCard


class StatusView(ctk.CTkFrame):  # type: ignore[misc]
    """An entry that is waiting, being transcribed, or has failed."""

    def __init__(
        self, master: Any, entry: HistoryEntry, delegate: EntryDelegate
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.entry_id = entry.id
        self.grid_columnconfigure(0, weight=1)

        self.header = EntryHeader(self, entry, delegate)
        self.header.grid(row=0, column=0, padx=28, pady=(22, 0), sticky=ctk.EW)
        self.card = ProgressCard(self, entry, delegate)
        self.card.grid(row=1, column=0, padx=28, pady=24, sticky=ctk.EW)

    def update_entry(self, entry: HistoryEntry) -> None:
        self.header.update_entry(entry)
        self.card.update_entry(entry)

    def update_progress(self) -> None:
        self.card.update_progress()
