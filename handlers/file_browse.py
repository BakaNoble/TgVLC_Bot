"""File browsing handler."""
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from handlers.base import CallbackHandler, build_standard_menu_text
from handlers.callbacks import PREFIX_DIR, PREFIX_FILE, PREFIX_ROOTDIR, parse_index_from_callback
from handlers.keyboards import (
    build_directory_list_keyboard,
    build_file_browsing_keyboard,
    build_playback_control_keyboard,
)


DIRECTORY_PICKER_TEXT = build_standard_menu_text("浏览视频", "请选择要浏览的目录：")


class FileBrowseHandler(CallbackHandler):
    """Handles file browsing and navigation callbacks."""

    HANDLED_CALLBACKS: Set[str] = {
        "next_page",
        "prev_page",
        "parent_directory",
        "directory_list",
        "change_directory",
    }

    def handles(self, data: str) -> bool:
        return (
            data in self.HANDLED_CALLBACKS
            or data.startswith(PREFIX_ROOTDIR)
            or data.startswith(PREFIX_DIR)
            or data.startswith(PREFIX_FILE)
        )

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        browser = self.get_user_browser(user_id)

        if data.startswith(PREFIX_ROOTDIR):
            return await self._handle_rootdir(query, data, browser, user_id)
        if data.startswith(PREFIX_DIR):
            return await self._handle_dir(query, data, browser)
        if data.startswith(PREFIX_FILE):
            return await self._handle_file(query, data, browser)
        if data == "next_page":
            return await self._handle_next_page(query, browser)
        if data == "prev_page":
            return await self._handle_prev_page(query, browser)
        if data == "parent_directory":
            return await self._handle_parent_directory(query, browser)
        if data in {"directory_list", "change_directory"}:
            return await self._handle_directory_list(query, user_id)
        return self.STATE_SELECTING_FILE

    async def _handle_rootdir(self, query, data: str, browser, user_id: int) -> int:
        success, idx = parse_index_from_callback(data, PREFIX_ROOTDIR)
        if not success or idx >= len(self.config.video_directories):
            await query.answer("无效的目录", show_alert=True)
            return self.STATE_BROWSING_FILES

        browse_success, message = browser.browse_directory(self.config.video_directories[idx])
        if not browse_success:
            await query.answer(message, show_alert=True)
            return self.STATE_BROWSING_FILES

        self.session_manager.set_browser_source(user_id, "browse")
        await query.answer()
        await query.edit_message_text(
            browser.get_display_list(),
            reply_markup=build_file_browsing_keyboard(browser),
        )
        return self.STATE_SELECTING_FILE

    async def _handle_dir(self, query, data: str, browser) -> int:
        success, idx = parse_index_from_callback(data, PREFIX_DIR)
        if not success:
            await query.answer("无效的目录", show_alert=True)
            return self.STATE_SELECTING_FILE

        page_items = browser.get_page_items()
        if idx >= len(page_items) or not page_items[idx].is_directory:
            await query.answer("无效的目录", show_alert=True)
            return self.STATE_SELECTING_FILE

        browse_success, message = browser.browse_directory(page_items[idx].path)
        if not browse_success:
            await query.answer(message, show_alert=True)
            return self.STATE_SELECTING_FILE

        await query.answer()
        await query.edit_message_text(
            browser.get_display_list(),
            reply_markup=build_file_browsing_keyboard(browser),
        )
        return self.STATE_SELECTING_FILE

    async def _handle_file(self, query, data: str, browser) -> int:
        success, idx = parse_index_from_callback(data, PREFIX_FILE)
        if not success:
            await query.answer("无效的文件", show_alert=True)
            return self.STATE_SELECTING_FILE

        page_items = browser.get_page_items()
        if idx >= len(page_items) or page_items[idx].is_directory:
            await query.answer("无效的文件", show_alert=True)
            return self.STATE_SELECTING_FILE

        file_path = page_items[idx].path
        video_files = browser.get_all_video_files()
        video_list = [file.path for file in video_files]
        try:
            current_index = video_list.index(file_path)
        except ValueError:
            current_index = -1
        show_episode_buttons = len(video_files) > 1

        play_success, message = self.vlc_player.open_file(file_path, video_list, current_index)
        if not play_success:
            await query.answer(message, show_alert=True)
            return self.STATE_SELECTING_FILE

        user_id = query.from_user.id
        self.session_manager.record_playback(user_id, file_path)
        self.session_manager.mark_play_source_from_browser(user_id)
        await query.answer("正在播放...", show_alert=False)
        await self.safe_edit_message(
            query,
            build_standard_menu_text("播放控制", self.vlc_player.get_status()),
            reply_markup=build_playback_control_keyboard(
                show_episode_buttons,
                show_stop_to_list=self.should_show_stop_to_list(user_id),
                show_stop_to_history=self.should_show_stop_to_history(user_id),
                vlc=self.vlc_player,
            ),
        )
        return self.STATE_SELECTING_ACTION

    async def _handle_next_page(self, query, browser) -> int:
        success, message = browser.next_page()
        if success:
            await query.answer()
            await query.edit_message_text(
                browser.get_display_list(),
                reply_markup=build_file_browsing_keyboard(browser),
            )
        else:
            await query.answer(message, show_alert=True)
        return self.STATE_SELECTING_FILE

    async def _handle_prev_page(self, query, browser) -> int:
        success, message = browser.prev_page()
        if success:
            await query.answer()
            await query.edit_message_text(
                browser.get_display_list(),
                reply_markup=build_file_browsing_keyboard(browser),
            )
        else:
            await query.answer(message, show_alert=True)
        return self.STATE_SELECTING_FILE

    async def _handle_parent_directory(self, query, browser) -> int:
        success, message = browser.navigate_to_parent()
        if success:
            await query.answer()
            await query.edit_message_text(
                browser.get_display_list(),
                reply_markup=build_file_browsing_keyboard(browser),
            )
        else:
            await query.answer(message, show_alert=True)
        return self.STATE_SELECTING_FILE

    async def _handle_directory_list(self, query, user_id: int) -> int:
        self.session_manager.set_browser_source(user_id, "browse")
        await query.answer()
        await query.edit_message_text(
            DIRECTORY_PICKER_TEXT,
            reply_markup=build_directory_list_keyboard(user_id),
        )
        return self.STATE_BROWSING_FILES
