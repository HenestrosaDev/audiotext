def format_error(e: Exception) -> str:
    """
    Formats an exception to be shown to the user. Validation errors (`ValueError`)
    already have user-friendly messages, so their type is omitted.
    """
    if isinstance(e, ValueError):
        return str(e)

    return f"{type(e).__name__}: {e}"
