from pathlib import Path
from typing import Optional

file_path = "google_api_key.txt"


def get_google_api_key() -> Optional[str]:
    try:
        with open(file_path, "r") as file:
            api_key = file.read()
            return api_key
    except FileNotFoundError:
        print(f"The file '{file_path}' does not exist, and that's ok.")
        return None


def set_google_api_key(google_api_key: str):
    if google_api_key:
        with open(file_path, "w+") as file:
            file.write(google_api_key)
            print("Google API key successfully set")
    else:  # If API key empty, remove the file.
        path_obj = Path(file_path)

        if path_obj.exists():
            path_obj.unlink()
            print(f"{file_path} successfully removed")
