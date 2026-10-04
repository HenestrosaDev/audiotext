import customtkinter as ctk


def add_placeholder(entry: ctk.CTkEntry, variable: ctk.StringVar, text: str) -> None:
    """
    Shows a placeholder in the entry while it's empty. CustomTkinter ignores the
    `placeholder_text` of the entries with a `textvariable`, so it's drawn as a
    label over the text field instead.

    :param entry: The entry to show the placeholder in.
    :param variable: The text variable of the entry.
    :param text: The text of the placeholder.
    """
    entry_theme = ctk.ThemeManager.theme["CTkEntry"]
    text_field = entry._entry  # The tkinter entry inside the CustomTkinter one
    lbl_placeholder = ctk.CTkLabel(
        entry,
        text=text,
        height=1,
        corner_radius=0,
        font=entry.cget("font"),
        fg_color=entry.cget("fg_color"),
        text_color=entry_theme["placeholder_text_color"],
        cursor="xterm",
    )
    lbl_placeholder.bind("<Button-1>", lambda _event: entry.focus_set())

    def refresh() -> None:
        if variable.get():
            lbl_placeholder.place_forget()
        else:
            # Same position as the text, which starts at the left of the field
            lbl_placeholder.place(in_=text_field, x=1, rely=0.5, anchor=ctk.W)

    variable.trace_add("write", lambda *_args: refresh())
    refresh()
