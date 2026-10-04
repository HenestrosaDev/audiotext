from utils.errors import format_error


def test_format_error_hides_the_type_of_validation_errors() -> None:
    assert format_error(ValueError("Select a file.")) == "Select a file."
    assert format_error(OSError("Disk full")) == "OSError: Disk full"
