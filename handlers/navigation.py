"""Navigation handler for main menu and sub-menus."""
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from handlers.base import CallbackHandler, build_standard_menu_text
from handlers.callbacks import PREFIX_HISTORY, parse_index_from_callback
from handlers.keyboards import (
    build_directory_list_keyboard,
    build_file_browsing_keyboard,
    build_main_menu_keyboard,
    build_play_history_keyboard,
    build_playback_control_keyboard,
    build_settings_keyboard,
)


MAIN_MENU_TEXT = build_standard_menu_text("主菜单")


class NavigationHandler(CallbackHandler):
    """Handles top-level navigation callbacks."""

    HANDLED_CALLBACKS: Set[str] = {
        "browse",
        "playback",
        "status",
        "history",
        "settings",
        "back_main",
    }

    def handles(self, data: str) -> bool:
        return data in self.HANDLED_CALLBACKS or data.startswith(PREFIX_HISTORY)

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id

        if data == "browse":
            self.session_manager.set_browser_source(user_id, "browse")
            await query.answer()
            await query.edit_message_text(
                build_standard_menu_text("浏览视频", "请选择要浏览的目录："),
                reply_markup=build_directory_list_keyboard(user_id),
            )
            return self.STATE_BROWSING_FILES

        if data == "playback":
            show_episode = self.get_show_episode_buttons(user_id)
            await query.answer()
            await query.edit_message_text(
                build_standard_menu_text("播放控制", self.vlc_player.get_status()),
                reply_markup=build_playback_control_keyboard(
                    show_episode,
                    show_stop_to_list=self.should_show_stop_to_list(user_id),
                    show_stop_to_history=self.should_show_stop_to_history(user_id),
                    vlc=self.vlc_player,
                ),
            )
            return self.STATE_SELECTING_ACTION

        if data == "status":
            await query.answer()
            await query.edit_message_text(
                build_standard_menu_text("当前状态", self.vlc_player.get_status()),
                reply_markup=build_main_menu_keyboard(user_id),
            )
            return self.STATE_SELECTING_ACTION

        if data == "history":
            if not self.session_manager.has_play_history(user_id):
                await query.answer("当前没有播放历史", show_alert=False)
                return self.STATE_SELECTING_ACTION
            await query.answer()
            await query.edit_message_text(
                self._build_play_history_text(user_id),
                reply_markup=build_play_history_keyboard(user_id),
            )
            return self.STATE_BROWSING_FILES

        if data.startswith(PREFIX_HISTORY):
            return await self._handle_history_directory(query, data, user_id)

        if data == "settings":
            await query.answer()
            await query.edit_message_text(
                build_standard_menu_text("设置菜单"),
                reply_markup=build_settings_keyboard(user_id),
            )
            return self.STATE_SETTINGS_MENU

        if data == "back_main":
            await query.answer()
            await query.edit_message_text(
                MAIN_MENU_TEXT,
                reply_markup=build_main_menu_keyboard(user_id),
            )
            return self.STATE_SELECTING_ACTION

        return self.STATE_SELECTING_ACTION

    async def _handle_history_directory(self, query, data: str, user_id: int) -> int:
        success, idx = parse_index_from_callback(data, PREFIX_HISTORY)
        history_entries = self.session_manager.get_play_history(user_id)
        if not success or idx >= len(history_entries):
            await query.answer("无效的历史目录", show_alert=True)
            return self.STATE_BROWSING_FILES

        entry = history_entries[idx]
        browser = self.get_user_browser(user_id)
        browse_success, message = browser.browse_directory(
            entry.directory,
            root_directories=[entry.directory],
        )
        if not browse_success:
            await query.answer(message, show_alert=True)
            return self.STATE_BROWSING_FILES

        self.session_manager.set_browser_source(user_id, "history")
        await query.answer()
        await query.edit_message_text(
            browser.get_display_list(),
            reply_markup=build_file_browsing_keyboard(browser),
        )
        return self.STATE_SELECTING_FILE

    def _build_play_history_text(self, user_id: int) -> str:
        entries = self.session_manager.get_play_history(user_id)
        lines = [build_standard_menu_text("播放历史", "最近播放文件："), ""]
        for index, entry in enumerate(entries, start=1):
            lines.append(f"{index}. {entry.file_name}")
        return "\n".join(lines).strip()
