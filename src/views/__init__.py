from typing import Any

from customtkinter import CTkBaseClass


def _grid_remove(self: Any) -> None:
    """
    Hides a widget, keeping its options of the grid to show it again with `grid()`.

    CustomTkinter places the widgets again when the scaling changes (e.g. on
    Windows, when the app starts or the window is moved to a screen with another
    scaling), but it only forgets the place of the ones hidden with `grid_forget`,
    so the ones hidden with `grid_remove` were shown again.
    """
    self._last_geometry_manager_call = None
    super(CTkBaseClass, self).grid_remove()


CTkBaseClass.grid_remove = _grid_remove
