"""Shared callback handler base class."""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from config import Config
    from file_browser import FileBrowser
    from session import SessionManager
    from vlc_player import VLCPlayer


def build_standard_menu_text(title: str, body: str = "请选择操作：") -> str:
    """Build menu pages with the same width baseline as the initial main menu."""
    return (
        "🎛 VLC 远程控制系统\n\n"
        "欢迎使用 VLC 播放器远程控制机器人。\n\n"
        f"{title}\n\n"
        f"{body}"
    )


class CallbackHandler(ABC):
    """Abstract base class for callback handlers."""

    STATE_SELECTING_ACTION = 0
    STATE_BROWSING_FILES = 1
    STATE_SELECTING_FILE = 2
    STATE_SETTINGS_MENU = 3
    STATE_ADDING_DIRECTORY = 4
    STATE_WAITING_VOLUME_STEP = 5
    STATE_WAITING_SEEK_STEP = 6
    STATE_ADDING_WEBDAV = 7

    def __init__(
        self,
        config: "Config",
        vlc_player: "VLCPlayer",
        session_manager: "SessionManager",
    ):
        self.config = config
        self.vlc_player = vlc_player
        self.session_manager = session_manager

    def get_user_browser(self, user_id: int) -> "FileBrowser":
        return self.session_manager.get_session(user_id).browser

    @abstractmethod
    def handles(self, data: str) -> bool:
        pass

    @abstractmethod
    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        pass

    async def check_permission(self, update: Update) -> bool:
        user_id = update.effective_user.id
        return self.config.is_user_allowed(user_id)

    async def check_admin(self, update: Update) -> bool:
        user_id = update.effective_user.id
        return self.config.is_admin(user_id)

    async def send_permission_denied(self, update: Update) -> None:
        await update.callback_query.edit_message_text("❌ 您没有权限使用此机器人。")

    async def safe_answer(
        self,
        query,
        message: str,
        show_alert: bool = True,
    ) -> None:
        try:
            await query.answer(message, show_alert=show_alert)
        except Exception:
            pass

    async def safe_edit_message(
        self,
        query,
        text: str,
        reply_markup=None,
    ) -> None:
        last_exc = None
        for attempt in range(3):
            try:
                if attempt == 0:
                    await query.answer()
                await query.edit_message_text(text, reply_markup=reply_markup)
                return
            except Exception as exc:
                error_name = type(exc).__name__
                if error_name == "BadRequest" and "not modified" in str(exc).lower():
                    return
                last_exc = exc
                error_text = str(exc).lower()
                is_network_error = (
                    error_name in {
                        "ConnectError",
                        "NetworkError",
                        "RemoteProtocolError",
                        "TimedOut",
                    }
                    or "timed out" in error_text
                    or "disconnected" in error_text
                    or "connecterror" in error_text
                )
                if not is_network_error or attempt == 2:
                    raise
                await query.get_bot().send_chat_action(
                    chat_id=query.message.chat_id,
                    action="typing",
                )
        if last_exc is not None:
            raise last_exc

    def get_show_episode_buttons(self, user_id: int) -> bool:
        return len(self.vlc_player.video_list) > 1

    def should_show_stop_to_list(self, user_id: int) -> bool:
        return self.get_user_browser(user_id).get_current_directory() is not None

    def should_show_stop_to_history(self, user_id: int) -> bool:
        return (
            self.session_manager.get_last_play_source(user_id) == "history"
            and self.session_manager.has_play_history(user_id)
        )
