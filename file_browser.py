"""
File browsing helpers for local video directories.
"""
import logging
import os
import urllib.parse
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, List, Optional, Tuple

from config import config
import webdav_client

if TYPE_CHECKING:
    from config import Config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FileItem:
    """A directory or file entry shown in the browser."""

    name: str
    path: str
    is_directory: bool
    size: int = 0

    def __str__(self) -> str:
        icon = "📁" if self.is_directory else "🎬"
        return f"{icon} {self.name}"


class FileBrowser:
    """Browse configured directories and paginate file listings."""

    def __init__(self, app_config: Optional['Config'] = None):
        self.config = app_config or config
        self.current_path: Optional[str] = None
        self.items: List[FileItem] = []
        self.current_page: int = 0
        self.page_size: int = self.config.page_size
        self._video_extensions_set: set[str] = set()
        self._normalized_root_dirs: tuple[str, ...] = tuple()

    @staticmethod
    def _is_webdav_path(path: str) -> bool:
        return path.startswith(("http://", "https://"))

    def browse_directory(
        self,
        directory: str,
        root_directories: Optional[Iterable[str]] = None,
    ) -> Tuple[bool, str]:
        """Browse a local directory or WebDAV URL."""
        if self._is_webdav_path(directory):
            return self._browse_webdav_directory(directory, root_directories)

        if not os.path.isdir(directory):
            logger.error("Directory not found: %s", directory)
            return False, "目录不存在"

        old_path = self.current_path
        old_items = list(self.items)
        old_page = self.current_page

        try:
            self.current_path = directory
            self.items = []
            self.current_page = 0
            self._video_extensions_set = {
                ext.lower() for ext in self.config.video_extensions
            }
            configured_root_dirs = (
                self.config.video_directories if root_directories is None else root_directories
            )
            self._normalized_root_dirs = tuple(
                os.path.normcase(os.path.normpath(path))
                for path in configured_root_dirs
            )

            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            self.items.append(FileItem(entry.name, entry.path, True))
                        elif self._is_video_file(entry.name):
                            stat = entry.stat(follow_symlinks=False)
                            self.items.append(
                                FileItem(entry.name, entry.path, False, stat.st_size)
                            )
                    except (OSError, PermissionError) as exc:
                        logger.warning("Cannot access %s: %s", entry.path, exc)

            self._sort_items()
            item_count = len(self.items)
            logger.info("Browsed directory: %s, found %s items", directory, item_count)
            return True, f"已加载 {item_count} 个项目"

        except PermissionError:
            logger.error("Permission denied: %s", directory)
            self._restore_state(old_path, old_items, old_page)
            return False, "没有权限访问该目录"
        except OSError as exc:
            logger.error("Failed to browse directory %s: %s", directory, exc)
            self._restore_state(old_path, old_items, old_page)
            return False, f"浏览目录失败: {exc}"
        except Exception as exc:
            logger.error("Failed to browse directory %s: %s", directory, exc)
            self._restore_state(old_path, old_items, old_page)
            return False, f"浏览目录失败: {exc}"

    def _restore_state(self, path: Optional[str], items: List[FileItem], page: int) -> None:
        self.current_path = path
        self.items = items
        self.current_page = page

    def _is_video_file(self, filename: str) -> bool:
        ext = os.path.splitext(filename)[1].lower()
        return ext in self._video_extensions_set

    def _sort_items(self) -> None:
        self.items.sort(key=lambda item: (not item.is_directory, item.name.lower()))

    def get_page_count(self) -> int:
        if not self.items:
            return 1
        return (len(self.items) + self.page_size - 1) // self.page_size

    def get_current_page(self) -> int:
        return self.current_page + 1

    def get_page_items(self) -> List[FileItem]:
        start = self.current_page * self.page_size
        end = start + self.page_size
        return self.items[start:end]

    def next_page(self) -> Tuple[bool, str]:
        if self.current_page < self.get_page_count() - 1:
            self.current_page += 1
            return True, f"已切换到第 {self.get_current_page()} 页"
        return False, "已经是最后一页"

    def prev_page(self) -> Tuple[bool, str]:
        if self.current_page > 0:
            self.current_page -= 1
            return True, f"已切换到第 {self.get_current_page()} 页"
        return False, "已经是第一页"

    def get_current_directory(self) -> Optional[str]:
        return self.current_path

    def get_all_video_files(self) -> List[FileItem]:
        return [item for item in self.items if not item.is_directory]

    def get_video_file_count(self) -> int:
        return sum(1 for item in self.items if not item.is_directory)

    def get_video_file_index(self, file_path: str) -> int:
        video_index = 0
        for item in self.items:
            if item.is_directory:
                continue
            if item.path == file_path:
                return video_index
            video_index += 1
        return -1

    def get_next_video(self, current_file_path: str) -> Optional[FileItem]:
        first_video: Optional[FileItem] = None
        found = False
        for item in self.items:
            if item.is_directory:
                continue
            if first_video is None:
                first_video = item
            if found:
                return item
            if item.path == current_file_path:
                found = True
        if not found:
            return first_video
        return None

    def get_previous_video(self, current_file_path: str) -> Optional[FileItem]:
        prev_video: Optional[FileItem] = None
        for item in self.items:
            if item.is_directory:
                continue
            if item.path == current_file_path:
                return prev_video
            prev_video = item
        return prev_video

    @staticmethod
    def format_file_size(size: int) -> str:
        if size < 0:
            return "未知大小"
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

    def get_display_list(self) -> str:
        if not self.items:
            return "📂 当前目录为空"

        page_items = self.get_page_items()
        if self._is_webdav_path(self.current_path or ""):
            display_path = urllib.parse.unquote(
                urllib.parse.urlparse(self.current_path).path
            )
            display_path = f"☁️ WebDAV: {display_path}"
        else:
            display_path = f"📂 {self.current_path}"
        lines = [
            display_path,
            f"📄 第 {self.get_current_page()}/{self.get_page_count()} 页",
            "━" * 30,
            "",
        ]

        for index, item in enumerate(page_items, start=1):
            display_index = self.current_page * self.page_size + index
            if item.is_directory:
                lines.append(f"{display_index}. 📁 {item.name}")
            else:
                lines.append(
                    f"{display_index}. 🎬 {item.name} ({self.format_file_size(item.size)})"
                )

        lines.append("━" * 30)
        if self.get_page_count() > 1:
            lines.append("\n💡 使用翻页按钮进行导航")
        return "\n".join(lines)

    def is_in_root_directory(self) -> bool:
        if not self.current_path:
            return False
        if self._is_webdav_path(self.current_path):
            current_stripped = self.current_path.rstrip("/")
            return any(
                current_stripped == src.url.rstrip("/")
                for src in self.config.webdav_sources
            )
        current_normalized = os.path.normcase(os.path.normpath(self.current_path))
        return current_normalized in self._normalized_root_dirs

    def get_parent_directory(self) -> Optional[str]:
        if not self.current_path or self.is_in_root_directory():
            return None
        if self._is_webdav_path(self.current_path):
            trimmed = self.current_path.rstrip("/")
            parent = trimmed.rsplit("/", 1)[0] + "/"
            return parent
        parent = os.path.dirname(self.current_path)
        return parent if parent != self.current_path else None

    def navigate_to_parent(self) -> Tuple[bool, str]:
        parent = self.get_parent_directory()
        if not parent:
            logger.info("Already at root directory, cannot go up")
            return False, "已经在根目录"

        logger.info("Navigating to parent directory: %s", parent)
        return self.browse_directory(parent)

    def _browse_webdav_directory(
        self,
        url: str,
        root_directories: Optional[Iterable[str]] = None,
    ) -> Tuple[bool, str]:
        """Browse a WebDAV directory via PROPFIND."""
        old_path = self.current_path
        old_items = list(self.items)
        old_page = self.current_page

        try:
            self.current_path = url
            self.items = []
            self.current_page = 0
            self._video_extensions_set = {
                ext.lower() for ext in self.config.video_extensions
            }

            src = self.config.get_webdav_credentials(url)
            username = src.username if src else ""
            password = src.password if src else ""
            base_url = src.url if src else url.rstrip("/")

            success, entries, message = webdav_client.list_directory(
                url,
                username=username,
                password=password,
                video_extensions=self._video_extensions_set,
            )
            if not success:
                self._restore_state(old_path, old_items, old_page)
                return False, message
            for entry in entries:
                full_url = webdav_client.build_full_url(base_url, entry.href)
                self.items.append(
                    FileItem(
                        name=urllib.parse.unquote(entry.name),
                        path=full_url,
                        is_directory=entry.is_directory,
                        size=entry.size,
                    )
                )

            logger.info("Browsed WebDAV directory: %s, found %s items", url, len(self.items))
            return True, f"已加载 {len(self.items)} 个项目"

        except Exception as exc:
            logger.error("Failed to browse WebDAV directory %s: %s", url, exc)
            self._restore_state(old_path, old_items, old_page)
            return False, f"WebDAV 浏览失败: {exc}"

    def reset(self) -> None:
        self.current_path = None
        self.items = []
        self.current_page = 0
        self._normalized_root_dirs = tuple()
        logger.info("File browser reset")


file_browser = FileBrowser()
