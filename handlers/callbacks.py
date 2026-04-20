"""
Centralized callback data definitions and parsing utilities.

This module provides:
- Named constants for all callback data strings (avoiding magic strings)
- Safe parsing functions with error handling
"""
from typing import Tuple


# =============================================================================
# Callback Prefixes (used with underscore and index suffix)
# =============================================================================

PREFIX_ROOTDIR = "rootdir_"
PREFIX_DIR = "dir_"
PREFIX_FILE = "file_"
PREFIX_HISTORY = "history_"
PREFIX_REMOVEDIR = "removedir_"
PREFIX_SUBTITLE = "select_sub_"
PREFIX_BACK_TO_SETTINGS = "back_to_settings_"


# =============================================================================
# Safe Parsing Utilities
# =============================================================================

def parse_index_from_callback(data: str, prefix: str) -> Tuple[bool, int]:
    """Safely parse index from callback data.

    Args:
        data: The full callback data string (e.g., "file_5").
        prefix: The prefix to strip before parsing (e.g., "file_").

    Returns:
        Tuple of (success, index) where:
        - success is True if parsing succeeded and index is valid
        - index is -1 if parsing fails

    Examples:
        >>> parse_index_from_callback("file_5", "file_")
        (True, 5)
        >>> parse_index_from_callback("file_abc", "file_")
        (False, -1)
        >>> parse_index_from_callback("dir_0", "file_")
        (False, -1)  # Wrong prefix
    """
    if not data.startswith(prefix):
        return False, -1
    try:
        index = int(data[len(prefix):])
        return True, index
    except ValueError:
        return False, -1
