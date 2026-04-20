"""Subtitle management handler."""
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from handlers.base import CallbackHandler
from handlers.callbacks import PREFIX_SUBTITLE, parse_index_from_callback
from handlers.keyboards import (
    build_playback_control_keyboard,
    build_subtitle_selection_keyboard,
)


class SubtitleHandler(CallbackHandler):
    """Handles subtitle selection and management callbacks."""

    HANDLED_CALLBACKS: Set[str] = {
        "subtitle_menu",
        "no_subtitle",
        "back_to_playback",
    }

    def handles(self, data: str) -> bool:
        return data in self.HANDLED_CALLBACKS or data.startswith(PREFIX_SUBTITLE)

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        show_episode = self.get_show_episode_buttons(user_id)

        if data == "subtitle_menu":
            return await self._handle_subtitle_menu(query)

        if data.startswith(PREFIX_SUBTITLE):
            return await self._handle_select_subtitle(query, data, show_episode, user_id)

        if data == "no_subtitle":
            await query.answer("当前视频未检测到字幕轨道", show_alert=True)
            return self.STATE_SELECTING_ACTION

        if data == "back_to_playback":
            await query.edit_message_text(
                self.vlc_player.get_status(),
                reply_markup=build_playback_control_keyboard(
                    show_episode,
                    show_stop_to_list=self.should_show_stop_to_list(user_id),
                    show_stop_to_history=self.should_show_stop_to_history(user_id),
                    vlc=self.vlc_player,
                ),
            )
            return self.STATE_SELECTING_ACTION

        return self.STATE_SELECTING_ACTION

    async def _handle_subtitle_menu(self, query) -> int:
        sub_tracks = self.vlc_player.get_subtitle_tracks()
        _, current_track_name = self.vlc_player.get_current_subtitle_track()

        menu_text = "🔤 字幕选择\n\n"
        if not sub_tracks:
            menu_text += "ℹ️ 未检测到字幕轨道\n\n"
            menu_text += "提示：\n"
            menu_text += "• 确保视频文件包含内嵌字幕\n"
            menu_text += "• 或在同一目录放置同名字幕文件，例如 .srt、.ass"
        else:
            menu_text += f"🎞 当前字幕：{current_track_name}\n\n"
            menu_text += f"📚 共检测到 {len(sub_tracks)} 个字幕轨道：\n\n"
            menu_text += "请选择要切换的字幕："

        await query.edit_message_text(
            menu_text,
            reply_markup=build_subtitle_selection_keyboard(vlc=self.vlc_player),
        )
        return self.STATE_SELECTING_ACTION

    async def _handle_select_subtitle(
        self,
        query,
        data: str,
        show_episode: bool,
        user_id: int,
    ) -> int:
        success, track_id = parse_index_from_callback(data, PREFIX_SUBTITLE)
        if not success:
            await query.answer("无效的字幕选择", show_alert=True)
            return self.STATE_SELECTING_ACTION

        success, message = self.vlc_player.set_subtitle_track(track_id)
        if success:
            _, track_name = self.vlc_player.get_current_subtitle_track()
            await query.answer(f"已切换至：{track_name}", show_alert=True)
            await query.edit_message_text(
                self.vlc_player.get_status(),
                reply_markup=build_playback_control_keyboard(
                    show_episode,
                    show_stop_to_list=self.should_show_stop_to_list(user_id),
                    show_stop_to_history=self.should_show_stop_to_history(user_id),
                    vlc=self.vlc_player,
                ),
            )
        else:
            await query.answer(message, show_alert=True)

        return self.STATE_SELECTING_ACTION
