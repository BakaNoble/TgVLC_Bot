"""
Per-user session management with thread safety.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, Dict, Iterable, List, Literal, Optional, Tuple

from config import config, get_app_dir
from file_browser import FileBrowser, FileItem

if TYPE_CHECKING:
    from config import Config

BrowseSource = Literal["browse", "history"]
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PlayHistoryEntry:
    directory: str
    file_name: str


@dataclass
class UserSession:
    """Thread-safe user session state."""

    user_id: int
    config: "Config" = field(default_factory=lambda: config)
    browser: FileBrowser = field(init=False)
    play_history: List[PlayHistoryEntry] = field(default_factory=list)
    browser_source: BrowseSource = "browse"
    last_play_source: BrowseSource = "browse"
    _lock: Lock = field(default_factory=Lock)
    _max_history_items: int = 5

    def __post_init__(self) -> None:
        self.browser = FileBrowser(self.config)

    def browse_directory(
        self,
        directory: str,
        root_directories: Optional[Iterable[str]] = None,
    ) -> Tuple[bool, str]:
        with self._lock:
            return self.browser.browse_directory(directory, root_directories=root_directories)

    def next_page(self) -> Tuple[bool, str]:
        with self._lock:
            return self.browser.next_page()

    def prev_page(self) -> Tuple[bool, str]:
        with self._lock:
            return self.browser.prev_page()

    def get_page_items(self) -> List[FileItem]:
        with self._lock:
            return self.browser.get_page_items()

    def get_all_video_files(self) -> List[FileItem]:
        with self._lock:
            return self.browser.get_all_video_files()

    def get_video_file_count(self) -> int:
        with self._lock:
            return self.browser.get_video_file_count()

    def get_video_file_index(self, file_path: str) -> int:
        with self._lock:
            return self.browser.get_video_file_index(file_path)

    def get_next_video(self, current_file_path: str) -> Optional[FileItem]:
        with self._lock:
            return self.browser.get_next_video(current_file_path)

    def get_previous_video(self, current_file_path: str) -> Optional[FileItem]:
        with self._lock:
            return self.browser.get_previous_video(current_file_path)

    def get_current_directory(self) -> Optional[str]:
        with self._lock:
            return self.browser.get_current_directory()

    def get_display_list(self) -> str:
        with self._lock:
            return self.browser.get_display_list()

    def get_page_count(self) -> int:
        with self._lock:
            return self.browser.get_page_count()

    def get_current_page(self) -> int:
        with self._lock:
            return self.browser.get_current_page()

    def is_in_root_directory(self) -> bool:
        with self._lock:
            return self.browser.is_in_root_directory()

    def navigate_to_parent(self) -> Tuple[bool, str]:
        with self._lock:
            return self.browser.navigate_to_parent()

    def set_browser_source(self, source: BrowseSource) -> None:
        with self._lock:
            self.browser_source = source

    def mark_play_source_from_browser(self) -> None:
        with self._lock:
            self.last_play_source = self.browser_source

    def get_last_play_source(self) -> BrowseSource:
        with self._lock:
            return self.last_play_source

    def add_play_history(self, file_path: str) -> None:
        """Record the played file's directory and latest file name."""
        directory = os.path.normpath(os.path.dirname(file_path))
        file_name = os.path.basename(file_path)
        if not directory or not file_name:
            return

        with self._lock:
            normalized_directory = os.path.normcase(directory)
            self.play_history = [
                entry for entry in self.play_history
                if os.path.normcase(entry.directory) != normalized_directory
            ]
            self.play_history.insert(0, PlayHistoryEntry(directory=directory, file_name=file_name))
            del self.play_history[self._max_history_items:]

    def get_play_history(self) -> List[PlayHistoryEntry]:
        with self._lock:
            return list(self.play_history)

    def has_play_history(self) -> bool:
        with self._lock:
            return bool(self.play_history)

    def set_play_history(self, entries: List[PlayHistoryEntry]) -> None:
        with self._lock:
            self.play_history = list(entries[:self._max_history_items])

    def reset(self) -> None:
        with self._lock:
            self.browser.reset()
            self.browser_source = "browse"
            self.last_play_source = "browse"


class SessionManager:
    """Manages per-user sessions with lazy initialization."""

    def __init__(self, history_file: Optional[str] = None, app_config: Optional["Config"] = None):
        self.config = app_config or config
        self._sessions: Dict[int, UserSession] = {}
        self._sessions_lock = Lock()
        self._history_file = history_file or os.path.join(get_app_dir(), "play_history.json")
        self._history_lock = Lock()
        self._history_cache: Dict[int, List[PlayHistoryEntry]] = self._load_history_cache()

    def _load_history_cache(self) -> Dict[int, List[PlayHistoryEntry]]:
        if not os.path.exists(self._history_file):
            return {}

        try:
            with open(self._history_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Failed to load play history file: %s", self._history_file)
            return {}

        if not isinstance(raw_data, dict):
            return {}

        history_cache: Dict[int, List[PlayHistoryEntry]] = {}
        for raw_user_id, raw_entries in raw_data.items():
            try:
                user_id = int(raw_user_id)
            except (TypeError, ValueError):
                continue

            if not isinstance(raw_entries, list):
                continue

            entries: List[PlayHistoryEntry] = []
            seen_directories = set()
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    continue

                directory = raw_entry.get("directory")
                file_name = raw_entry.get("file_name")
                if not isinstance(directory, str) or not isinstance(file_name, str):
                    continue

                normalized_directory = os.path.normpath(directory)
                normalized_key = os.path.normcase(normalized_directory)
                if not normalized_directory or not file_name or normalized_key in seen_directories:
                    continue

                seen_directories.add(normalized_key)
                entries.append(
                    PlayHistoryEntry(directory=normalized_directory, file_name=file_name)
                )
                if len(entries) >= 5:
                    break

            if entries:
                history_cache[user_id] = entries

        return history_cache

    def _save_history_cache(self) -> bool:
        history_dir = os.path.dirname(os.path.abspath(self._history_file)) or "."
        temp_file = f"{self._history_file}.tmp"
        serializable_data = {
            str(user_id): [
                {"directory": entry.directory, "file_name": entry.file_name}
                for entry in entries
            ]
            for user_id, entries in self._history_cache.items()
            if entries
        }

        try:
            os.makedirs(history_dir, exist_ok=True)
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self._history_file)
            return True
        except OSError:
            logger.warning("Failed to save play history file: %s", self._history_file)
            return False

    def get_session(self, user_id: int) -> UserSession:
        with self._sessions_lock:
            session = self._sessions.get(user_id)
            if session is None:
                session = UserSession(user_id=user_id, config=self.config)
                cached_history = self._history_cache.get(user_id)
                if cached_history:
                    session.set_play_history(cached_history)
                self._sessions[user_id] = session
            return session

    def set_browser_source(self, user_id: int, source: BrowseSource) -> None:
        self.get_session(user_id).set_browser_source(source)

    def mark_play_source_from_browser(self, user_id: int) -> None:
        self.get_session(user_id).mark_play_source_from_browser()

    def get_last_play_source(self, user_id: int) -> BrowseSource:
        return self.get_session(user_id).get_last_play_source()

    def record_playback(self, user_id: int, file_path: str) -> None:
        session = self.get_session(user_id)
        session.add_play_history(file_path)
        with self._history_lock:
            self._history_cache[user_id] = session.get_play_history()
            self._save_history_cache()

    def get_play_history(self, user_id: int) -> List[PlayHistoryEntry]:
        return self.get_session(user_id).get_play_history()

    def has_play_history(self, user_id: int) -> bool:
        return self.get_session(user_id).has_play_history()

    def clear_session(self, user_id: int) -> None:
        with self._sessions_lock:
            if user_id in self._sessions:
                del self._sessions[user_id]

    def clear_all_sessions(self) -> None:
        with self._sessions_lock:
            self._sessions.clear()

    def get_active_session_count(self) -> int:
        with self._sessions_lock:
            return len(self._sessions)


session_manager = SessionManager()
