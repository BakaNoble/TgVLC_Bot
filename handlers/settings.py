"""Settings management handler."""
from typing import Set

from telegram import Update
from telegram.ext import ContextTypes

from handlers.base import CallbackHandler, build_standard_menu_text
from handlers.callbacks import (
    PREFIX_BACK_TO_SETTINGS,
    PREFIX_REMOVEDIR,
    parse_index_from_callback,
)
from handlers.keyboards import (
    build_directory_management_keyboard,
    build_settings_keyboard,
    build_user_list_text,
    build_user_management_keyboard,
)


class SettingsHandler(CallbackHandler):
    """Handles settings and administration callbacks."""

    HANDLED_CALLBACKS: Set[str] = {
        "manage_directories",
        "add_directory",
        "volume_step",
        "seek_step",
        "manage_users",
        "add_current_user",
    }

    def handles(self, data: str) -> bool:
        return (
            data in self.HANDLED_CALLBACKS
            or data.startswith(PREFIX_REMOVEDIR)
            or data.startswith(PREFIX_BACK_TO_SETTINGS)
        )

    async def handle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id

        admin_only = {
            "manage_directories",
            "removedir_",
            "add_directory",
            "manage_users",
            "add_current_user",
        }
        if data.startswith(tuple(admin_only)) or data in admin_only:
            if not await self.check_admin(update):
                await query.answer("只有管理员可以执行此操作", show_alert=True)
                return self.STATE_SELECTING_ACTION

        if data == "manage_directories":
            return await self._handle_manage_directories(query, user_id)
        if data.startswith(PREFIX_REMOVEDIR):
            return await self._handle_remove_directory(query, data, user_id)
        if data == "add_directory":
            return await self._handle_add_directory(update, context)
        if data.startswith(PREFIX_BACK_TO_SETTINGS):
            await query.edit_message_text(
                build_standard_menu_text("设置菜单"),
                reply_markup=build_settings_keyboard(user_id),
            )
            return self.STATE_SETTINGS_MENU
        if data == "volume_step":
            return await self._handle_volume_step(update, context)
        if data == "seek_step":
            return await self._handle_seek_step(update, context)
        if data == "manage_users":
            return await self._handle_manage_users(query)
        if data == "add_current_user":
            return await self._handle_add_current_user(update)
        return self.STATE_SETTINGS_MENU

    async def _handle_manage_directories(self, query, user_id: int) -> int:
        await query.edit_message_text(
            build_standard_menu_text("视频目录管理", self._format_directory_list() + "\n\n请选择操作："),
            reply_markup=build_directory_management_keyboard(user_id),
        )
        return self.STATE_SETTINGS_MENU

    async def _handle_remove_directory(self, query, data: str, user_id: int) -> int:
        success, idx = parse_index_from_callback(data, PREFIX_REMOVEDIR)

        if success and 0 <= idx < len(self.config.video_directories):
            directory = self.config.video_directories[idx]
            if self.config.remove_video_directory(directory):
                await query.answer("目录已删除", show_alert=True)
            else:
                await query.answer("删除失败", show_alert=True)
        else:
            await query.answer("无效的目录", show_alert=True)

        await query.edit_message_text(
            build_standard_menu_text("视频目录管理", self._format_directory_list() + "\n\n请选择操作："),
            reply_markup=build_directory_management_keyboard(user_id),
        )
        return self.STATE_SETTINGS_MENU

    async def _handle_add_directory(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        await query.edit_message_text(
            build_standard_menu_text(
                "添加目录",
                "请发送要添加的目录路径：\n\n"
                "提示：可以输入完整路径，例如：\n"
                "D:\\Videos\n"
                "C:\\Users\\YourName\\Videos",
            )
        )
        context.user_data["current_state"] = self.STATE_ADDING_DIRECTORY
        return self.STATE_ADDING_DIRECTORY

    async def _handle_volume_step(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        await query.edit_message_text(
            build_standard_menu_text(
                "音量步长设置",
                f"当前音量步长：{self.config.volume_step}%\n\n发送数字设置新的音量步长（1-100）：",
            )
        )
        context.user_data["current_state"] = self.STATE_WAITING_VOLUME_STEP
        return self.STATE_WAITING_VOLUME_STEP

    async def _handle_seek_step(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        query = update.callback_query
        await query.edit_message_text(
            build_standard_menu_text(
                "跳转步长设置",
                f"当前跳转步长：{self.config.seek_step} 秒\n\n发送数字设置新的跳转步长（例如：10、30、120）：",
            )
        )
        context.user_data["current_state"] = self.STATE_WAITING_SEEK_STEP
        return self.STATE_WAITING_SEEK_STEP

    async def _handle_manage_users(self, query) -> int:
        await query.edit_message_text(
            build_standard_menu_text(
                "授权用户管理",
                f"当前授权用户：\n{build_user_list_text()}\n\n提示：留空表示允许所有人使用",
            ),
            reply_markup=build_user_management_keyboard(),
        )
        return self.STATE_SETTINGS_MENU

    async def _handle_add_current_user(self, update: Update) -> int:
        query = update.callback_query
        user_id = update.effective_user.id
        self.config.add_allowed_user(user_id)
        await query.answer(f"已添加用户 {user_id} 到授权列表", show_alert=True)

        await query.edit_message_text(
            build_standard_menu_text(
                "授权用户管理",
                f"当前授权用户：\n{build_user_list_text()}\n\n提示：留空表示允许所有人使用",
            ),
            reply_markup=build_user_management_keyboard(),
        )
        return self.STATE_SETTINGS_MENU

    def _format_directory_list(self) -> str:
        if not self.config.video_directories:
            return "（无）"
        return "\n".join(f"• {directory}" for directory in self.config.video_directories)
