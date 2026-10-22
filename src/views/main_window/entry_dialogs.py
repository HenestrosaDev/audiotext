from tkinter import messagebox
from typing import Any

from controllers.history_controller import HistoryController
from controllers.transcription_queue import TranscriptionQueue
from utils.history_store import HistoryStore
from utils.i18n import P_, _
from views.widgets.confirm_dialog import ConfirmDialog
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
        if entry.is_folder:
            self._confirm_remove_folder(entry_id)
            return

        message = _("Delete “{title}” from the history?").format(title=entry.title)
        message += "\n\n" + _("Your audio, video and saved files are not deleted.")
        if not messagebox.askyesno(
            _("Delete transcription"), message, parent=self._parent.winfo_toplevel()
        ):
            return

        if entry.status.is_active:
            self._jobs.cancel_entry(entry_id)
        self._history.delete_entry(entry_id)

    def confirm_remove_entries(self, entry_ids: list[str]) -> None:
        """
        Asks to remove some files of a folder from the history. Their files and
        the files saved for them are kept.
        """
        entries = [entry for id_ in entry_ids if (entry := self._store.get(id_))]
        if not entries:
            return
        count = len(entries)
        message = (
            P_(
                "Remove {count} file from the history?",
                "Remove {count} files from the history?",
                count,
            ).format(count=count)
            + "\n\n"
            + _("Your audio, video and saved files are not deleted.")
        )
        if not messagebox.askyesno(
            _("Remove from history"), message, parent=self._parent.winfo_toplevel()
        ):
            return
        # Without cancelling the ones being transcribed, which would cancel their
        # whole folder
        self._history.delete_entries([entry.id for entry in entries])

    def _confirm_remove_folder(self, entry_id: str) -> None:
        """
        Asks to remove a folder from the history and whether to also delete the
        files saved for its files, which are kept unless the user asks for it.
        """
        entry = self._store.get(entry_id)
        if entry is None:
            return

        title = _("Remove from history")
        message = (
            _("Remove “{title}” and its files from the history?").format(
                title=entry.title
            )
            + "\n\n"
            + _("Your audio and video files are not deleted.")
        )
        transcripts = self._history.saved_transcripts(entry_id)
        if transcripts:
            count = len(transcripts)
            should_delete_transcripts = ConfirmDialog(
                self._parent,
                title,
                message,
                confirm_text=_("Remove"),
                option_text=P_(
                    "Also delete the {count} file saved for them",
                    "Also delete the {count} files saved for them",
                    count,
                ).format(count=count),
                option_hint=_("In {folder}").format(folder=entry.transcripts_dir),
            ).get_result()
            if should_delete_transcripts is None:
                return
        elif messagebox.askyesno(title, message, parent=self._parent.winfo_toplevel()):
            should_delete_transcripts = False
        else:
            return

        if entry.status.is_active:
            self._jobs.cancel_entry(entry_id)
        if not should_delete_transcripts:
            self._history.delete_entry(entry_id)
            return

        deleted, failed = self._history.delete_entry(
            entry_id, should_delete_transcripts=True
        )
        if failed:
            self._parent.show_status(
                P_(
                    "Could not delete {count} saved file.",
                    "Could not delete {count} saved files.",
                    failed,
                ).format(count=failed),
                is_error=True,
            )
        else:
            self._parent.show_status(
                P_(
                    "Deleted {count} saved file.",
                    "Deleted {count} saved files.",
                    deleted,
                ).format(count=deleted)
            )

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
