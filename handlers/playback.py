"""Playback control handler."""
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from handlers.base import CallbackHandler, build_standard_menu_text
from handlers.keyboards import (
    MODE_ICONS,
    build_file_browsing_keyboard,
    build_main_menu_keyboard,
    build_play_history_keyboard,
    build_playback_control_keyboard,
)


class PlaybackHandler(CallbackHandler):
    """Handles playback-related callback actions."""

    HANDLED_CALLBACKS: Set[str] = {
        "play_pause",
        "seek_forward",
        "seek_backward",
        "volume_up",
        "volume_down",
        "mute",
        "fullscreen",
        "stop",
        "stop_to_list",
        "stop_to_history",
        "prev_episode",
        "next_episode",
        "toggle_playmode",
    }

    def handles(self, data: str) -> bool:
        return data in self.HANDLED_CALLBACKS

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        show_episode = self.get_show_episode_buttons(user_id)

        if data == "play_pause":
            return await self._handle_play_pause(query, show_episode, user_id)
        if data == "seek_forward":
            return await self._handle_seek(query, show_episode, user_id, forward=True)
        if data == "seek_backward":
            return await self._handle_seek(query, show_episode, user_id, forward=False)
        if data == "volume_up":
            return await self._handle_volume(query, show_episode, user_id, up=True)
        if data == "volume_down":
            return await self._handle_volume(query, show_episode, user_id, up=False)
        if data == "mute":
            return await self._handle_mute(query, show_episode, user_id)
        if data == "fullscreen":
            return await self._handle_fullscreen(query, show_episode, user_id)
        if data == "stop":
            return await self._handle_stop(query, user_id)
        if data == "stop_to_list":
            return await self._handle_stop_to_list(query)
        if data == "stop_to_history":
            return await self._handle_stop_to_history(query)
        if data == "prev_episode":
            return await self._handle_prev_episode(query, show_episode, user_id)
        if data == "next_episode":
            return await self._handle_next_episode(query, show_episode, user_id)
        if data == "toggle_playmode":
            return await self._handle_toggle_playmode(query, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_play_pause(self, query, show_episode: bool, user_id: int) -> int:
        if self.vlc_player.player and self.vlc_player.player.is_playing():
            _, message = self.vlc_player.pause()
        else:
            _, message = self.vlc_player.play()
        await self._answer_and_refresh(query, message, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_seek(self, query, show_episode: bool, user_id: int, forward: bool) -> int:
        if forward:
            _, message = self.vlc_player.seek_forward()
        else:
            _, message = self.vlc_player.seek_backward()
        await self._answer_and_refresh(query, message, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_volume(self, query, show_episode: bool, user_id: int, up: bool) -> int:
        if up:
            _, message = self.vlc_player.volume_up()
        else:
            _, message = self.vlc_player.volume_down()
        await self._answer_and_refresh(query, message, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_mute(self, query, show_episode: bool, user_id: int) -> int:
        _, message = self.vlc_player.toggle_mute()
        await self._answer_and_refresh(query, message, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_fullscreen(self, query, show_episode: bool, user_id: int) -> int:
        _, message = self.vlc_player.toggle_fullscreen()
        await self._answer_and_refresh(query, message, show_episode, user_id)
        return self.STATE_SELECTING_ACTION

    async def _handle_stop(self, query, user_id: int) -> int:
        _, message = self.vlc_player.stop()
        await query.answer(message, show_alert=False)
        await query.edit_message_text(
            build_standard_menu_text("主菜单", message),
            reply_markup=build_main_menu_keyboard(user_id),
        )
        return self.STATE_SELECTING_ACTION

    async def _handle_stop_to_list(self, query) -> int:
        _, message = self.vlc_player.stop()
        await query.answer(message, show_alert=False)

        user_id = query.from_user.id
        browser = self.get_user_browser(user_id)
        if browser.get_current_directory():
            await query.edit_message_text(
                browser.get_display_list(),
                reply_markup=build_file_browsing_keyboard(browser),
            )
            return self.STATE_SELECTING_FILE

        await query.edit_message_text(
            build_standard_menu_text("主菜单", message + "\n\n请先选择视频目录"),
            reply_markup=build_main_menu_keyboard(user_id),
        )
        return self.STATE_SELECTING_ACTION

    async def _handle_stop_to_history(self, query) -> int:
        _, message = self.vlc_player.stop()
        await query.answer(message, show_alert=False)

        user_id = query.from_user.id
        history_entries = self.session_manager.get_play_history(user_id)
        if not history_entries:
            await query.edit_message_text(
                build_standard_menu_text("主菜单", message),
                reply_markup=build_main_menu_keyboard(user_id),
            )
            return self.STATE_SELECTING_ACTION

        lines = [build_standard_menu_text("播放历史", "最近播放文件："), ""]
        for index, entry in enumerate(history_entries, start=1):
            lines.append(f"{index}. {entry.file_name}")

        await query.edit_message_text(
            "\n".join(lines).strip(),
            reply_markup=build_play_history_keyboard(user_id),
        )
        return self.STATE_BROWSING_FILES

    async def _handle_prev_episode(self, query, show_episode: bool, user_id: int) -> int:
        video_list, current_index = self._get_active_playlist()
        if not video_list:
            await query.answer("当前没有可用的播放列表", show_alert=False)
            return self.STATE_SELECTING_ACTION

        if current_index <= 0:
            total = len(video_list)
            current_display = max(current_index + 1, 1)
            await query.answer(
                f"已经到达列表起始位置，当前第 {current_display}/{total} 集",
                show_alert=False,
            )
            return self.STATE_SELECTING_ACTION

        success, message = self._open_playlist_index(current_index - 1, video_list)
        if success:
            await query.answer("正在播放上一集...", show_alert=False)
            await query.edit_message_text(
                build_standard_menu_text("播放控制", self.vlc_player.get_status()),
                reply_markup=self._build_playback_keyboard(show_episode, user_id),
            )
        else:
            await query.answer(message, show_alert=False)
        return self.STATE_SELECTING_ACTION

    async def _handle_next_episode(self, query, show_episode: bool, user_id: int) -> int:
        video_list, current_index = self._get_active_playlist()
        if not video_list:
            await query.answer("当前没有可用的播放列表", show_alert=False)
            return self.STATE_SELECTING_ACTION

        if current_index < 0:
            current_index = 0

        if current_index >= len(video_list) - 1:
            total = len(video_list)
            await query.answer(
                f"已经到达列表结束位置，当前第 {total}/{total} 集",
                show_alert=False,
            )
            return self.STATE_SELECTING_ACTION

        success, message = self._open_playlist_index(current_index + 1, video_list)
        if success:
            await query.answer("正在播放下一集...", show_alert=False)
            await query.edit_message_text(
                build_standard_menu_text("播放控制", self.vlc_player.get_status()),
                reply_markup=self._build_playback_keyboard(show_episode, user_id),
            )
        else:
            await query.answer(message, show_alert=False)
        return self.STATE_SELECTING_ACTION

    async def _handle_toggle_playmode(self, query, show_episode: bool, user_id: int) -> int:
        success, message = self.vlc_player.toggle_play_mode()
        if success:
            _, new_mode_name = self.vlc_player.get_play_mode()
            new_icon = MODE_ICONS.get(new_mode_name, "🔁")
            await query.answer(f"{new_icon} 当前模式: {new_mode_name}", show_alert=False)
        else:
            await query.answer(message, show_alert=False)

        await query.edit_message_text(
            build_standard_menu_text("播放控制", self.vlc_player.get_status()),
            reply_markup=self._build_playback_keyboard(show_episode, user_id),
        )
        return self.STATE_SELECTING_ACTION

    def _get_active_playlist(self) -> tuple[list[str], int]:
        if not self.vlc_player.video_list:
            return [], -1

        video_list = list(self.vlc_player.video_list)
        current_index = self.vlc_player.current_video_index
        if current_index < 0 and self.vlc_player.current_file:
            try:
                current_index = video_list.index(self.vlc_player.current_file)
            except ValueError:
                current_index = -1
        return video_list, current_index

    def _open_playlist_index(self, target_index: int, video_list: list[str]) -> tuple[bool, str]:
        if target_index < 0 or target_index >= len(video_list):
            return False, "无效的播放目标"
        return self.vlc_player.open_file(video_list[target_index], video_list, target_index)

    def _build_playback_keyboard(self, show_episode: bool, user_id: int):
        return build_playback_control_keyboard(
            show_episode,
            show_stop_to_list=self.should_show_stop_to_list(user_id),
            show_stop_to_history=self.should_show_stop_to_history(user_id),
            vlc=self.vlc_player,
        )

    async def _answer_and_refresh(
        self,
        query,
        message: str,
        show_episode: bool,
        user_id: int,
    ) -> None:
        await query.answer(message, show_alert=False)
        await query.edit_message_text(
            build_standard_menu_text("播放控制", self.vlc_player.get_status()),
            reply_markup=self._build_playback_keyboard(show_episode, user_id),
        )
