"""Keyboard builder helpers."""
import os
from typing import List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import config
from file_browser import FileBrowser
from session import PlayHistoryEntry, session_manager
from vlc_player import MODE_ICONS, vlc_player


MAIN_MENU_LABEL_WIDTH = 6
FULL_WIDTH_SPACE = "\u3000"


def _pad_label(text: str, min_width: int = MAIN_MENU_LABEL_WIDTH) -> str:
    """Pad labels with full-width spaces for more stable Telegram button widths."""
    padding = max(min_width - len(text), 0)
    left = padding // 2
    right = padding - left
    return f"{FULL_WIDTH_SPACE * left}{text}{FULL_WIDTH_SPACE * right}"


def _button(text: str, callback_data: str, min_width: int = MAIN_MENU_LABEL_WIDTH) -> InlineKeyboardButton:
    return InlineKeyboardButton(_pad_label(text, min_width), callback_data=callback_data)


def _history_directory_label(entry: PlayHistoryEntry) -> str:
    """Prefer the grandparent directory name for history display."""
    if entry.directory.startswith(("http://", "https://")):
        import urllib.parse
        url_path = urllib.parse.unquote(urllib.parse.urlparse(entry.directory).path)
        parts = [p for p in url_path.rstrip("/").split("/") if p]
        if len(parts) >= 2:
            return f"☁️ {parts[-2]}"
        return f"☁️ {parts[-1]}" if parts else "☁️ WebDAV"

    normalized_directory = os.path.normpath(entry.directory)
    parent_directory = os.path.dirname(normalized_directory)
    grandparent_name = os.path.basename(parent_directory)
    if grandparent_name:
        return grandparent_name

    current_name = os.path.basename(normalized_directory)
    return current_name or normalized_directory


def build_main_menu_keyboard(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    keyboard = [
        [_button("浏览视频", "browse", MAIN_MENU_LABEL_WIDTH)],
        [_button("播放控制", "playback", MAIN_MENU_LABEL_WIDTH)],
        [_button("当前状态", "status", MAIN_MENU_LABEL_WIDTH)],
    ]

    if user_id is not None and session_manager.has_play_history(user_id):
        keyboard.append([_button("播放历史", "history", MAIN_MENU_LABEL_WIDTH)])

    keyboard.append([_button("设置", "settings", MAIN_MENU_LABEL_WIDTH)])
    return InlineKeyboardMarkup(keyboard)


def build_playback_control_keyboard(
    show_episode_buttons: bool = False,
    show_stop_to_list: bool = True,
    show_stop_to_history: bool = False,
    vlc: Optional["vlc_player.__class__"] = None,
) -> InlineKeyboardMarkup:
    vlc = vlc or vlc_player
    keyboard: List[List[InlineKeyboardButton]] = []

    _, current_mode_name = vlc.get_play_mode()
    mode_icon = MODE_ICONS.get(current_mode_name, "🔁")
    mode_button_text = f"{mode_icon} 播放模式: {current_mode_name}"

    if show_episode_buttons:
        keyboard.append([
            _button("上一集", "prev_episode"),
            _button("下一集", "next_episode"),
        ])

    keyboard.append([_button("播放/暂停", "play_pause")])
    keyboard.append([
        _button("后退", "seek_backward"),
        _button("前进", "seek_forward"),
    ])
    keyboard.append([
        _button("增大音量", "volume_up"),
        _button("减小音量", "volume_down"),
    ])
    keyboard.append([
        _button("静音", "mute"),
        _button("全屏", "fullscreen"),
    ])
    keyboard.append([_button(mode_button_text, "toggle_playmode")])
    keyboard.append([_button("字幕选择", "subtitle_menu")])

    if show_stop_to_list:
        keyboard.append([_button("停止并返回列表", "stop_to_list")])
    if show_stop_to_history:
        keyboard.append([_button("停止并返回播放历史", "stop_to_history")])

    keyboard.append([_button("返回主菜单", "back_main")])
    return InlineKeyboardMarkup(keyboard)


def build_subtitle_selection_keyboard(
    vlc: Optional["vlc_player.__class__"] = None,
) -> InlineKeyboardMarkup:
    vlc = vlc or vlc_player
    keyboard: List[List[InlineKeyboardButton]] = []
    sub_tracks = vlc.get_subtitle_tracks()

    if not sub_tracks:
        keyboard.append([
            _button("未检测到字幕轨道", "no_subtitle")
        ])

    for track_id, track_name in sub_tracks:
        track_label = f"字幕 {track_name}"
        keyboard.append([
            _button(track_label, f"select_sub_{track_id}")
        ])

    keyboard.append([
        _button("返回播放控制", "back_to_playback")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_directory_list_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    for i, directory in enumerate(config.video_directories):
        dir_name = os.path.basename(directory) or directory
        keyboard.append([
            _button(dir_name, f"rootdir_{i}", MAIN_MENU_LABEL_WIDTH)
        ])

    for i, src in enumerate(config.webdav_sources):
        keyboard.append([
            _button(f"☁️ {src.name}", f"webdav_root_{i}", MAIN_MENU_LABEL_WIDTH)
        ])

    keyboard.append([
        _button("返回主菜单", "back_main", MAIN_MENU_LABEL_WIDTH)
    ])
    return InlineKeyboardMarkup(keyboard)


def build_play_history_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []
    history_entries = session_manager.get_play_history(user_id)

    for index, entry in enumerate(history_entries):
        keyboard.append([
            _button(_history_directory_label(entry), f"history_{index}", MAIN_MENU_LABEL_WIDTH)
        ])

    keyboard.append([
        _button("返回主菜单", "back_main")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_file_navigation_keyboard(
    browser: FileBrowser,
    show_parent_button: bool = False,
) -> InlineKeyboardMarkup:
    page_count = browser.get_page_count()
    current_page = browser.get_current_page()
    keyboard: List[List[InlineKeyboardButton]] = []

    if page_count > 1:
        nav_row: List[InlineKeyboardButton] = []
        if current_page > 1:
            nav_row.append(_button("上一页", "prev_page"))
        if current_page < page_count:
            nav_row.append(_button("下一页", "next_page"))
        if nav_row:
            keyboard.append(nav_row)

    if show_parent_button:
        keyboard.append([
            _button("返回上级目录", "parent_directory")
        ])

    keyboard.append([_button("目录列表", "directory_list")])
    keyboard.append([_button("返回主菜单", "back_main")])
    return InlineKeyboardMarkup(keyboard)


def build_file_list_keyboard(items) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    for i, item in enumerate(items):
        callback_data = f"dir_{i}" if item.is_directory else f"file_{i}"
        keyboard.append([
            _button(item.name, callback_data, MAIN_MENU_LABEL_WIDTH)
        ])

    return InlineKeyboardMarkup(keyboard)


def build_file_browsing_keyboard(browser: FileBrowser) -> InlineKeyboardMarkup:
    page_items = browser.get_page_items()
    show_parent = not browser.is_in_root_directory()
    nav_keyboard = build_file_navigation_keyboard(browser, show_parent)
    file_keyboard = build_file_list_keyboard(page_items)
    combined = list(file_keyboard.inline_keyboard)
    combined.extend(list(nav_keyboard.inline_keyboard))
    return InlineKeyboardMarkup(combined)


def build_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    if config.is_admin(user_id):
        keyboard.append([
            _button("管理视频目录", "manage_directories")
        ])

    keyboard.append([
        _button("音量步长设置", "volume_step")
    ])
    keyboard.append([
        _button("跳转步长设置", "seek_step")
    ])

    if config.is_admin(user_id):
        keyboard.append([
            _button("管理授权用户", "manage_users")
        ])

    keyboard.append([
        _button("返回主菜单", "back_main")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_directory_management_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = []

    for i, directory in enumerate(config.video_directories):
        dir_name = os.path.basename(directory) or directory
        keyboard.append([
            _button(f"删除 {dir_name}", f"removedir_{i}"),
            _button("浏览", f"rootdir_{i}"),
        ])

    for i, src in enumerate(config.webdav_sources):
        keyboard.append([
            _button(f"删除 ☁️ {src.name}", f"remove_webdav_{i}"),
        ])

    keyboard.append([_button("添加本地目录", "add_directory")])
    keyboard.append([_button("添加 WebDAV", "add_webdav")])
    keyboard.append([
        _button("返回设置", f"back_to_settings_{user_id}")
    ])
    return InlineKeyboardMarkup(keyboard)


def build_user_management_keyboard() -> InlineKeyboardMarkup:
    keyboard: List[List[InlineKeyboardButton]] = [
        [_button("添加当前用户", "add_current_user")],
        [_button("返回设置", "settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_user_list_text() -> str:
    return (
        "\n".join([f"- {uid}" for uid in config.allowed_user_ids])
        if config.allowed_user_ids else "（无限制）"
    )
