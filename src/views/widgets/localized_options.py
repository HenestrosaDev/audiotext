from collections.abc import Callable
from typing import Any

from views.localization import on_language_change


class LocalizedOptions:
    """
    The options of an option menu or a segmented button, shown with labels in the
    interface language, while the code works with their values (e.g. "summary"
    instead of "Summary"), which don't change with the language. When it changes,
    the labels are shown in the new one, keeping the selected option.
    """

    def __init__(
        self,
        menu: Any,
        get_labels: Callable[[], dict[str, str]],
        value: str | None = None,
        *,
        values: list[str] | None = None,
        search_terms: dict[str, str] | None = None,
        command: Callable[[str], None] | None = None,
    ) -> None:
        """
        :param menu: A `CTkOptionMenu`, `CTkSegmentedButton` or
                     `CTkSearchableOptionMenu`.
        :param get_labels: Returns the label of each value, in order. Values with
                           the same label (e.g. two formats of a date that look the
                           same in a language) are shown once, as the first one.
        :param value: The value selected first, if any.
        :param values: The values shown, if not all of them (see `show_values`).
        :param search_terms: Extra text matched by the search of a
                             `CTkSearchableOptionMenu` for each value (e.g. the
                             English name of a language).
        :param command: Called with the value of the option the user chooses.
        """
        self._menu = menu
        self._get_labels = get_labels
        self._search_terms = search_terms
        self._labels: dict[str, str] = {}
        self._shown_values = values
        self._show(value)
        if command:
            menu.configure(command=lambda label: command(self.value(label)))
        on_language_change(menu, lambda: self._show(self.get()))

    @property
    def values(self) -> list[str]:
        """The values shown, in order."""
        if self._shown_values is not None:
            return list(self._shown_values)
        return list(self._labels)

    def get(self) -> str:
        """:return: The value of the selected option."""
        return self.value(self._menu.get())

    def set(self, value: str) -> None:
        self._menu.set(self.label(value))

    def show_values(self, values: list[str]) -> None:
        """Shows only some of the options, keeping the selected one if it's shown."""
        self._shown_values = values
        self._show(self.get())

    def label(self, value: str) -> str:
        return self._labels.get(value, value)

    def value(self, label: str) -> str:
        """:return: The value of a label, or the label if it isn't an option."""
        return next(
            (value for value, text in self._labels.items() if text == label), label
        )

    def _show(self, value: str | None) -> None:
        self._labels = self._get_labels()
        labels = list(dict.fromkeys(self.label(value) for value in self.values))
        options: dict[str, Any] = {"values": labels}
        if self._search_terms is not None:
            options["search_terms"] = {
                self.label(value): terms for value, terms in self._search_terms.items()
            }
        self._menu.configure(**options)
        if value is not None:
            self.set(value)
