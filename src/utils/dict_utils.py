from typing import Any, Optional


def find_key_by_value(dictionary: dict[Any, Any], target_value: Any) -> Optional[Any]:
    """
    Searches for the first key in the dictionary that has the specified target value.

    :param dictionary: The dictionary to search through.
    :type dictionary: Dict[Any, Any]
    :param target_value: The value to search for.
    :type target_value: Any
    :return: The key associated with the target value, or None if not found.
    :rtype: Optional[Any]
    """
    for key, value in dictionary.items():
        if value == target_value:
            return key

    return None
