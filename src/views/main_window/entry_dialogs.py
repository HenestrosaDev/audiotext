from tkinter import messagebox
from typing import Any

from controllers.history_controller import HistoryController
from controllers.transcription_queue import TranscriptionQueue
from utils.history_store import HistoryStore
from utils.i18n import _
from views.widgets.text_dialog import TextDialog


class EntryDialogs:
    """
    The actions on the entries and the groups of the history that ask the user
    for something first, a name, a note or a confirmation, and then pass it on to
    the controllers. It implements the `EntryPrompts` and the `GroupPrompts` of the
    views.
    """

    def __init__(
        self,
        parent: Any,
        store: HistoryStore,
        history: HistoryController,
        jobs: TranscriptionQueue,
    ) -> None:
        """:param parent: The widget the dialogs are shown over."""
        self._parent = parent
        self._store = store
        self._history = history
        self._jobs = jobs

    # ENTRIES

    def ask_to_rename_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        title = TextDialog(
            self._parent,
            _("Rename"),
            _("Name of the transcription:"),
            entry.title,
            allow_empty=False,
        ).get_input()
        if title:
            self._history.rename_entry(entry_id, title)

    def ask_for_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        note = TextDialog(
            self._parent,
            _("Note"),
            _("A note about “{title}”:").format(title=entry.title),
            entry.note,
            is_multiline=True,
        ).get_input()
        if note is not None:
            self._history.set_note(entry_id, note)

    def confirm_delete_note(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None or not entry.note:
            return
        if messagebox.askyesno(
            _("Delete note"),
            _("Delete the note of “{title}”?").format(title=entry.title),
            icon=messagebox.WARNING,
            parent=self._parent.winfo_toplevel(),
        ):
            self._history.set_note(entry_id, "")

    def ask_for_tag(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return
        tag = TextDialog(
            self._parent,
            _("Tag"),
            _("Tag of “{title}”. Leave it empty to show the kind of source.").format(
                title=entry.title
            ),
            entry.tag,
            suggestions=self._store.tags(),
        ).get_input()
        if tag is not None:
            self._history.set_tag(entry_id, tag)

    def confirm_delete_entry(self, entry_id: str) -> None:
        entry = self._store.get(entry_id)
        if entry is None:
            return

        message = _("Delete “{title}” from the history?").format(title=entry.title)
        if entry.is_folder:
            message += "\n\n" + _("The transcriptions of its files are deleted too.")
        message += "\n\n" + _("Your audio, video and saved files are not deleted.")
        if not messagebox.askyesno(
            _("Delete transcription"), message, parent=self._parent.winfo_toplevel()
        ):
            return

        if entry.status.is_active:
            self._jobs.cancel_entry(entry_id)
        self._history.delete_entry(entry_id)

    # GROUPS

    def ask_to_create_group(self) -> str | None:
        """:return: The ID of the new group, or None if the user cancelled."""
        name = TextDialog(
            self._parent,
            _("New group"),
            _("Name of the group:"),
            ok_text=_("Create"),
            allow_empty=False,
        ).get_input()
        return self._history.create_group(name) if name else None

    def ask_to_move_to_new_group(self, entry_id: str) -> None:
        if group_id := self.ask_to_create_group():
            self._history.move_to_group(entry_id, group_id)

    def ask_to_rename_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        name = TextDialog(
            self._parent,
            _("Rename group"),
            _("Name of the group:"),
            group.name,
            allow_empty=False,
        ).get_input()
        if name:
            self._history.rename_group(group_id, name)

    def confirm_delete_group(self, group_id: str) -> None:
        group = self._store.get_group(group_id)
        if group is None:
            return
        if messagebox.askyesno(
            _("Delete group"),
            _(
                "Delete the group “{name}”? Its transcriptions are kept, without a group."
            ).format(name=group.name),
            parent=self._parent.winfo_toplevel(),
        ):
            self._history.delete_group(group_id)
