"""
Handlers package for TgVLC_Bot callback handlers.

This package contains the refactored callback handlers extracted from main.py,
organized by responsibility:
- base: Abstract base class for all handlers
- navigation: Main menu and navigation handlers
- playback: Playback control handlers
- settings: Settings and directory management handlers
- file_browse: File browsing and pagination handlers
- subtitle: Subtitle selection handlers
"""
from handlers.base import CallbackHandler
from handlers.navigation import NavigationHandler
from handlers.playback import PlaybackHandler
from handlers.settings import SettingsHandler
from handlers.file_browse import FileBrowseHandler
from handlers.subtitle import SubtitleHandler

__all__ = [
    'CallbackHandler',
    'NavigationHandler',
    'PlaybackHandler',
    'SettingsHandler',
    'FileBrowseHandler',
    'SubtitleHandler',
]
