"""
The texts of the interface follow its language: when it changes, they're shown
again in the new one, without rebuilding the window, so nothing the user typed or
chose is lost.

A text is given as a function that translates it (e.g. `lambda: _("Settings")`),
so it can be translated again:

- `localize` sets the texts of a widget (e.g. its `text` or `placeholder_text`)
  instead of `configure`. It's used both when the widget is created and when its
  text changes later (e.g. a hint that follows the state of the view).
- `on_language_change` runs a method of a view when the language changes, for
  the texts it builds from its data (e.g. the list of the history, which is built
  again) or the options of its menus (see `LocalizedOptions`).

Texts that aren't translated, such as names or messages already shown (e.g. the
error of a failed transcription), are set as usual.
"""

import itertools
import tkinter as tk
from collections.abc import Callable
from typing import Any, TypeVar

import utils.i18n as i18n

Text = Callable[[], str]

_WidgetT = TypeVar("_WidgetT")

# Below this number of updates, the ones of destroyed widgets aren't looked for
_MIN_PRUNE_SIZE = 256


class _TextUpdate:
    """An option of a widget whose value is a text in the interface language."""

    def __init__(self, widget: Any, option: str, text: Text) -> None:
        self.widget = widget
        self._option = option
        self._text = text
        self._shown = ""

    def apply(self) -> None:
        # Another text was set without `localize` (e.g. a name), which is kept
        if self._shown and _get_option(self.widget, self._option) != self._shown:
            return
        self._shown = self._text()
        _set_option(self.widget, self._option, self._shown)


class _CallbackUpdate:
    """A method of a view that shows its texts again."""

    def __init__(self, widget: Any, callback: Callable[[], None]) -> None:
        self.widget = widget
        self._callback = callback

    def apply(self) -> None:
        self._callback()


# The updates of the texts shown, in the order they were added, so the texts of a
# view are updated before the ones its methods show from them
_updates: dict[Any, _TextUpdate | _CallbackUpdate] = {}
_prune_size = _MIN_PRUNE_SIZE
_callback_ids = itertools.count()


def localize(widget: _WidgetT, **texts: Text) -> _WidgetT:
    """
    Sets options of a widget to texts in the interface language, which are
    translated again when the language changes, as long as the option isn't
    changed to another value in the meantime.

    :param texts: The text of each option, e.g. `text=lambda: _("Settings")`. A
                  toplevel window also takes its `title`.
    :return: The widget, to place it right away.
    """
    for option, text in texts.items():
        update = _TextUpdate(widget, option, text)
        update.apply()
        # A new text of the same option replaces the previous one
        _add_update((id(widget), option), update)
    return widget


def on_language_change(widget: Any, callback: Callable[[], None]) -> None:
    """
    Calls a method of a view when the interface language changes, to show its
    texts again, until the widget is destroyed.

    :param widget: The widget whose texts the method shows.
    """
    _add_update(("callback", next(_callback_ids)), _CallbackUpdate(widget, callback))


def set_interface_language(setting: str) -> None:
    """
    Changes the language of the interface and shows its texts in it.

    :param setting: A code of `UI_LANGUAGES`, or `SYSTEM_LANGUAGE`.
    """
    i18n.set_language(setting)
    _prune()
    # The updates may add others (e.g. a view rebuilt from its data), which are
    # already in the new language
    for key, update in list(_updates.items()):
        if _updates.get(key) is update and _exists(update.widget):
            update.apply()


def _add_update(key: Any, update: _TextUpdate | _CallbackUpdate) -> None:
    global _prune_size
    _updates[key] = update
    if len(_updates) > _prune_size:
        _prune()
        _prune_size = max(_MIN_PRUNE_SIZE, len(_updates) * 2)


def _prune() -> None:
    """Forgets the updates of the widgets that have been destroyed."""
    for key, update in list(_updates.items()):
        if not _exists(update.widget):
            del _updates[key]


def _exists(widget: Any) -> bool:
    try:
        return bool(widget.winfo_exists())
    except (tk.TclError, RuntimeError):  # The interpreter of Tk was destroyed
        return False


def _get_option(widget: Any, option: str) -> Any:
    if option == "title":
        return widget.title()
    return widget.cget(option)


def _set_option(widget: Any, option: str, value: str) -> None:
    if option == "title":
        widget.title(value)
    else:
        widget.configure(**{option: value})
