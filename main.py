# -*- coding: utf-8 -*-
"""Telegram VLC remote control entrypoint."""
import asyncio
import logging
import os
import sys
import signal
import time
import atexit
import traceback
from logging.handlers import RotatingFileHandler
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram.request import HTTPXRequest
import httpx

from config import config
from vlc_player import vlc_player
from session import session_manager

# Import handlers
from handlers import (
    NavigationHandler,
    PlaybackHandler,
    FileBrowseHandler,
    SettingsHandler,
    SubtitleHandler,
)
from handlers.keyboards import build_main_menu_keyboard

try:
    import socksio
    SOCKS_AVAILABLE = True
except ImportError:
    SOCKS_AVAILABLE = False
    print("WARNING: socksio not installed. SOCKS5 proxy will not work.")
    print("   Install with: pip install httpx[socks]")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# =============================================================================
# Logging Configuration
# =============================================================================

def _get_log_dir() -> str:
    # Return the log directory.
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'logs')

_log_dir = _get_log_dir()
os.makedirs(_log_dir, exist_ok=True)

# Root logger: output to both console and rotating file.
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)

# Console handler
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
_root_logger.addHandler(_console_handler)

# File handler: 10MB rotation with 5 backups.
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, 'bot.log'),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding='utf-8',
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
_root_logger.addHandler(_file_handler)

logger = logging.getLogger(__name__)


def _is_windows_drive_path(text: str) -> bool:
    # Removed docstring
    return len(text) >= 2 and text[1] == ':' and text[0].upper() in 'CDEFGHIJKLMNOPQRSTUVWXYZ'


# =============================================================================
# Conversation States
# =============================================================================

(
    STATE_SELECTING_ACTION,
    STATE_BROWSING_FILES,
    STATE_SELECTING_FILE,
    STATE_SETTINGS_MENU,
    STATE_ADDING_DIRECTORY,
    STATE_WAITING_VOLUME_STEP,
    STATE_WAITING_SEEK_STEP
) = range(7)


# =============================================================================
# Handler Registry
# =============================================================================

class CallbackRouter:
    # Routes callback queries to registered handlers.

    def __init__(self):
        self._handlers = []

    def register(self, handler):
        self._handlers.append(handler)

    async def route(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        # Route callback to the first matching handler.
        query = update.callback_query
        data = query.data

        # Check permission first
        user_id = update.effective_user.id
        if not config.is_user_allowed(user_id):
            await query.edit_message_text("❌ 您没有权限使用此机器人。")
            return ConversationHandler.END

        # Find first handler that handles this callback
        for handler in self._handlers:
            if handler.handles(data):
                return await handler.handle(update, context)

        # No handler found - return to main menu
        logger.warning(f"No handler found for callback: {data}")
        context.user_data.pop('current_state', None)
        return STATE_SELECTING_ACTION


# Create global router and register handlers
_callback_router = CallbackRouter()
_callback_router.register(NavigationHandler(config, vlc_player, session_manager))
_callback_router.register(PlaybackHandler(config, vlc_player, session_manager))
_callback_router.register(FileBrowseHandler(config, vlc_player, session_manager))
_callback_router.register(SettingsHandler(config, vlc_player, session_manager))
_callback_router.register(SubtitleHandler(config, vlc_player, session_manager))


# =============================================================================
# Command Handlers
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /start command.
    user_id = update.effective_user.id

    if not config.is_user_allowed(user_id):
        await update.message.reply_text(
            "❌ 您没有权限使用此机器人。\n请联系管理员添加您的用户 ID。"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🎬 VLC 远程控制系统\n\n"
        "欢迎使用 VLC 播放器远程控制机器人。\n\n"
        "请选择操作：",
        reply_markup=build_main_menu_keyboard(user_id)
    )
    return STATE_SELECTING_ACTION


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /help command.
    user_id = update.effective_user.id
    if not config.is_user_allowed(user_id):
        await update.message.reply_text("❌ 您没有权限使用此机器人。")
        return

    help_text = (
        "VLC 远程控制 - 帮助\n\n"
        "可用命令：\n"
        "/start - 启动机器人\n"
        "/help - 显示帮助信息\n"
        "/status - 查看当前播放状态\n"
        "/playmode - 切换播放模式\n\n"
        "播放控制：\n"
        "• 播放/暂停 - 切换播放状态\n"
        "• 前进/后退 - 跳转指定时间\n"
        "• 音量控制 - 调整音量\n"
        "• 全屏 - 切换显示模式\n"
        "• /playmode - 切换播放模式\n\n"
        "播放模式说明：\n"
        "顺序播放 - 按列表顺序播放所有视频\n"
        "单集播放 - 仅播放当前选中的视频\n"
        "单集循环 - 循环播放当前视频\n\n"
        "文件浏览：\n"
        "• 浏览视频目录\n"
        "• 选择要播放的文件\n"
        "• 分页导航\n\n"
        "设置：\n"
        "• 管理视频目录\n"
        "• 设置音量/跳转步长\n"
        "• 管理授权用户\n\n"
        "如需帮助，请联系管理员。"
    )
    await update.message.reply_text(help_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /status command.
    user_id = update.effective_user.id
    if not config.is_user_allowed(user_id):
        await update.message.reply_text("❌ 您没有权限使用此机器人。")
        return

    await update.message.reply_text(vlc_player.get_status())


async def playmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle /playmode command.
    user_id = update.effective_user.id
    if not config.is_user_allowed(user_id):
        await update.message.reply_text("❌ 您没有权限使用此机器人。")
        return

    success, message = vlc_player.toggle_play_mode()
    if success:
        await update.message.reply_text(f"✅ {message}")
        mode_info = (
            "当前支持的播放模式：\n"
            "顺序播放 - 按列表顺序播放所有视频\n"
            "单集播放 - 仅播放当前选中的视频\n"
            "单集循环 - 循环播放当前视频\n\n"
            "再次发送 /playmode 可以切换到下一个模式。"
        )
        await update.message.reply_text(mode_info)
    else:
        await update.message.reply_text(f"❌ {message}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle button callbacks.
    return await _callback_router.route(update, context)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle text input.
    user_id = update.effective_user.id
    if not config.is_user_allowed(user_id):
        await update.message.reply_text("❌ 您没有权限使用此机器人。")
        return ConversationHandler.END

    text = update.message.text.strip()
    current_state = context.user_data.get('current_state', STATE_SELECTING_ACTION)

    if current_state == STATE_WAITING_VOLUME_STEP:
        if text.isdigit():
            num = int(text)
            if 1 <= num <= 100:
                config.volume_step = num
                config.save_config()
                await update.message.reply_text(f"✅ 音量步长已设置为 {num}%")
            else:
                await update.message.reply_text("❌ 音量步长必须在 1-100 之间")
        else:
            await update.message.reply_text("❌ 请输入有效数字（1-100）")
        context.user_data.pop('current_state', None)
        return STATE_SELECTING_ACTION

    if current_state == STATE_WAITING_SEEK_STEP:
        if text.isdigit():
            num = int(text)
            if 1 <= num <= 300:
                config.seek_step = num
                config.save_config()
                await update.message.reply_text(f"✅ 跳转步长已设置为 {num} 秒")
            else:
                await update.message.reply_text("❌ 跳转步长必须在 1-300 之间")
        else:
            await update.message.reply_text("❌ 请输入有效数字（1-300）")
        context.user_data.pop('current_state', None)
        return STATE_SELECTING_ACTION

    if current_state == STATE_ADDING_DIRECTORY:
        if config.is_admin(user_id):
            if config.add_video_directory(text):
                await update.message.reply_text(f"✅ 已添加目录：{text}")
            else:
                await update.message.reply_text("❌ 添加失败：目录不存在或已存在")
        else:
            await update.message.reply_text("❌ 只有管理员可以添加目录")
        context.user_data.pop('current_state', None)
        return STATE_SETTINGS_MENU

    if _is_windows_drive_path(text):
        if config.is_admin(user_id):
            if config.add_video_directory(text):
                await update.message.reply_text(f"✅ 已添加目录：{text}")
            else:
                await update.message.reply_text("❌ 添加失败：目录不存在或已存在")
        else:
            await update.message.reply_text("❌ 只有管理员可以添加目录")
        return STATE_SELECTING_ACTION

    await update.message.reply_text("❌ 无法识别的输入\n\n请使用按钮菜单操作。")
    return STATE_SELECTING_ACTION

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Error handler.
    error = context.error
    error_name = type(error).__name__ if error else 'Unknown'
    error_str = str(error).lower() if error else ''

    if error_name == 'BadRequest' and 'not modified' in error_str:
        logger.debug("Message not modified, ignoring")
        return

    network_errors = (
        'RemoteProtocolError', 'ConnectionError', 'TimeoutError',
        'ConnectTimeout', 'ReadTimeout', 'PoolTimeout',
        'SSLError', 'ProxyError', 'NetworkError',
    )
    if error_name in network_errors or 'disconnected' in error_str or 'timed out' in error_str:
        logger.warning(f"Network error, library will auto-retry: {error}")
        return

    logger.error(f"Error: {error}", exc_info=True)


# =============================================================================
# Graceful Shutdown
# =============================================================================

_application = None
_shutdown_in_progress = False
_resources_cleaned = False


def _cleanup_resources_once():
    global _resources_cleaned
    if _resources_cleaned:
        return
    _resources_cleaned = True

    try:
        vlc_player.cleanup()
    except Exception as e:
        print(f"VLC cleanup error: {e}", flush=True)
        logger.error(f"VLC cleanup error: {e}")


def _graceful_shutdown(signum=None, frame=None):
    # Removed docstring
    global _shutdown_in_progress

    if _shutdown_in_progress:
        return
    _shutdown_in_progress = True

    print("\n\nReceived shutdown signal, cleaning up...", flush=True)
    logger.info(f"Shutdown initiated (signal: {signum if signum else 'program exit'})")

    if _application is None:
        _cleanup_resources_once()
        print("Cleanup complete, exiting...", flush=True)
        logger.info("Shutdown complete")


# =============================================================================
# Resilient HTTPXRequest for SOCKS5 proxy stability
# =============================================================================

class ResilientHTTPXRequest(HTTPXRequest):
    # HTTPX request wrapper that disables keepalive for proxy stability.

    def __init__(self, *args, **kwargs):
        self._last_request_time = time.time()
        self._last_success_time = 0.0
        self._last_error_time = 0.0
        self._consecutive_failures = 0
        self._last_error_repr = ""
        super().__init__(*args, **kwargs)
        old_limits = self._client_kwargs.get('limits')
        if old_limits:
            self._client_kwargs['limits'] = httpx.Limits(
                max_connections=old_limits.max_connections,
                max_keepalive_connections=0,
            )
        else:
            self._client_kwargs['limits'] = httpx.Limits(max_keepalive_connections=0)
        self._client = self._build_client()

    async def do_request(self, *args, **kwargs):
        self._last_request_time = time.time()
        try:
            result = await super().do_request(*args, **kwargs)
            self._last_success_time = time.time()
            self._consecutive_failures = 0
            self._last_error_repr = ""
            return result
        except Exception as exc:
            self._last_error_time = time.time()
            self._consecutive_failures += 1
            self._last_error_repr = f"{type(exc).__name__}: {exc}"
            raise

    async def shutdown(self) -> None:
        # Removed docstring
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.aclose(), timeout=5.0)
            except Exception:
                pass
            self._client = None

    async def reinitialize(self) -> None:
        # Removed docstring
        if self._client is not None and not self._client.is_closed:
            try:
                await asyncio.wait_for(self._client.aclose(), timeout=5.0)
            except Exception:
                pass
        self._client = self._build_client()
        self._consecutive_failures = 0
        self._last_error_repr = ""

    def get_health_snapshot(self) -> dict:
        return {
            "last_request_time": self._last_request_time,
            "last_success_time": self._last_success_time,
            "last_error_time": self._last_error_time,
            "consecutive_failures": self._consecutive_failures,
            "last_error_repr": self._last_error_repr,
        }


def main():
    # Main entry point.
    if config.telegram_token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("[ERROR] 请先在 config.yaml 中配置 Telegram Bot Token")
        print("   1. 在 Telegram 中搜索 @BotFather")
        print("   2. 发送 /newbot 创建一个新机器人")
        print("   3. 获取 Bot Token")
        print("   4. 将 Token 填入 config.yaml 的 telegram.token 字段")
        return

    if not vlc_player.initialize():
        print("WARNING: VLC initialization failed")
        print("   Please ensure VLC is installed and path is correct")
        print("   You can modify vlc path in config.yaml")

    def on_vlc_crash(message: str):
        logger.error(f"VLC Crash: {message}")
    vlc_player.set_crash_callback(on_vlc_crash)

    print("=" * 50)
    print("VLC Remote Control System")
    print("=" * 50)
    print(f"Telegram Bot Token: {'Configured' if config.telegram_token != 'YOUR_TELEGRAM_BOT_TOKEN' else 'Not configured'}")
    print(f"VLC Path: {config.vlc_path}")
    print(f"Video Directories: {len(config.video_directories)}")
    print(f"Authorized Users: {'Unlimited' if len(config.allowed_user_ids) == 0 else f'{len(config.allowed_user_ids)} users'}")

    if config.proxy_enabled:
        proxy_type_str = "SOCKS5" if config.proxy_type == "socks5" else "HTTP"
        auth_str = f"{config.proxy_username}@" if config.proxy_username else ""
        print(f"Proxy: {proxy_type_str} ({auth_str}{config.proxy_host}:{config.proxy_port})")
    else:
        print("Proxy: Disabled")

    print("=" * 50)
    print("Starting Telegram Bot...")
    print("Press Ctrl+C to stop")
    print("=" * 50)

    proxy_url = None
    if config.proxy_enabled:
        if config.proxy_type == "socks5":
            if not SOCKS_AVAILABLE:
                print("ERROR: socksio is required for SOCKS5 proxy")
                print("   Install with: pip install httpx[socks]")
                return
            proxy_url = f"socks5://{config.proxy_host}:{config.proxy_port}"
            if config.proxy_username and config.proxy_password:
                proxy_url = f"socks5://{config.proxy_username}:{config.proxy_password}@{config.proxy_host}:{config.proxy_port}"
            print(f"Using SOCKS5 proxy: {config.proxy_host}:{config.proxy_port}")
        elif config.proxy_type == "http":
            proxy_url = f"http://{config.proxy_host}:{config.proxy_port}"
            if config.proxy_username and config.proxy_password:
                proxy_url = f"http://{config.proxy_username}:{config.proxy_password}@{config.proxy_host}:{config.proxy_port}"
            print(f"Using HTTP proxy: {config.proxy_host}:{config.proxy_port}")

    main_request = ResilientHTTPXRequest(
        connection_pool_size=8,
        proxy=proxy_url,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=15,
        pool_timeout=30,
    )
    get_updates_request = ResilientHTTPXRequest(
        connection_pool_size=2,
        proxy=proxy_url,
        read_timeout=60,
        write_timeout=30,
        connect_timeout=15,
        pool_timeout=30,
    )

    builder = (
        Application.builder()
        .token(config.telegram_token)
        .request(main_request)
        .get_updates_request(get_updates_request)
    )

    application = builder.build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            STATE_SELECTING_ACTION: [CallbackQueryHandler(button_callback)],
            STATE_BROWSING_FILES: [CallbackQueryHandler(button_callback)],
            STATE_SELECTING_FILE: [CallbackQueryHandler(button_callback)],
            STATE_SETTINGS_MENU: [CallbackQueryHandler(button_callback)],
            STATE_ADDING_DIRECTORY: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
            ],
            STATE_WAITING_VOLUME_STEP: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
            ],
            STATE_WAITING_SEEK_STEP: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
            ]
        },
        fallbacks=[
            CommandHandler('start', start_command),
            CommandHandler('help', help_command),
            CommandHandler('status', status_command),
            CommandHandler('playmode', playmode_command)
        ]
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('playmode', playmode_command))
    application.add_error_handler(error_handler)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    atexit.register(_graceful_shutdown)

    global _application
    _application = application

    async def run_bot():
        # Start polling and watchdog.
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=False,
        )

        async def watchdog():
            idle_threshold = 180
            success_stale_threshold = 120
            failure_threshold = 3
            check_interval = 30
            # Exponential backoff to avoid frequent restarts under flapping networks.
            backoff_base = 60.0     # first cooldown after a restart (seconds)
            backoff_cap = 1800.0    # maximum cooldown (30 minutes)
            restart_attempts = 0
            next_restart_allowed_at = 0.0
            last_restart_at = 0.0
            while True:
                await asyncio.sleep(check_interval)
                if _shutdown_in_progress:
                    break
                try:
                    now = time.time()
                    get_updates_health = get_updates_request.get_health_snapshot()
                    main_health = main_request.get_health_snapshot()

                    # Reset backoff once a post-restart success is observed.
                    if restart_attempts > 0 and last_restart_at > 0:
                        recovered = (
                            get_updates_health["last_success_time"] > last_restart_at
                            and get_updates_health["consecutive_failures"] == 0
                        )
                        if recovered:
                            logger.info(
                                "Watchdog: network recovered after %d restart(s), resetting backoff",
                                restart_attempts,
                            )
                            restart_attempts = 0
                            next_restart_allowed_at = 0.0

                    get_updates_idle = now - get_updates_health["last_request_time"]
                    get_updates_success_stale = (
                        now - get_updates_health["last_success_time"]
                        if get_updates_health["last_success_time"] > 0
                        else float("inf")
                    )
                    transport_stalled = get_updates_idle > idle_threshold
                    get_updates_failing = (
                        get_updates_health["consecutive_failures"] >= failure_threshold
                        and get_updates_success_stale > success_stale_threshold
                    )
                    main_failing = main_health["consecutive_failures"] >= failure_threshold

                    if transport_stalled or get_updates_failing or main_failing:
                        if now < next_restart_allowed_at:
                            logger.info(
                                "Watchdog: unhealthy signals detected but restart is in cooldown "
                                "(%.0fs remaining, attempt=%d)",
                                next_restart_allowed_at - now,
                                restart_attempts,
                            )
                            continue

                        reasons = []
                        if transport_stalled:
                            reasons.append(f"getUpdates idle {get_updates_idle:.0f}s")
                        if get_updates_failing:
                            reasons.append(
                                "getUpdates failures="
                                f"{get_updates_health['consecutive_failures']}"
                            )
                        if main_failing:
                            reasons.append(
                                "main request failures="
                                f"{main_health['consecutive_failures']}"
                            )

                        restart_attempts += 1
                        logger.warning(
                            "Watchdog: network appears unhealthy (%s), restarting updater and "
                            "requests (attempt=%d)",
                            ", ".join(reasons),
                            restart_attempts,
                        )
                        try:
                            await asyncio.wait_for(application.updater.stop(), timeout=10.0)
                        except Exception:
                            pass
                        try:
                            await asyncio.gather(
                                main_request.reinitialize(),
                                get_updates_request.reinitialize(),
                            )
                        except Exception as exc:
                            logger.error(f"Watchdog reinitialize failed: {exc}")
                        await application.updater.start_polling(
                            allowed_updates=Update.ALL_TYPES,
                            drop_pending_updates=False,
                        )
                        last_restart_at = time.time()
                        cooldown = min(
                            backoff_base * (2 ** (restart_attempts - 1)),
                            backoff_cap,
                        )
                        next_restart_allowed_at = last_restart_at + cooldown
                        logger.info(
                            "Watchdog: updater restarted successfully "
                            "(attempt=%d, next restart allowed in %.0fs)",
                            restart_attempts,
                            cooldown,
                        )
                except Exception as e:
                    logger.error(f"Watchdog error: {e}")

        watchdog_task = asyncio.create_task(watchdog())

        try:
            while not _shutdown_in_progress:
                await asyncio.sleep(1)
        finally:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
            for cleanup in (application.updater.stop, application.stop, application.shutdown):
                try:
                    await asyncio.wait_for(cleanup(), timeout=10.0)
                except Exception:
                    pass
            _cleanup_resources_once()
            logger.info("Shutdown complete")

    asyncio.run(run_bot())


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        _graceful_shutdown()
    except Exception as e:
        error_msg = traceback.format_exc()
        print(f"\n{'=' * 50}")
        print("  FATAL ERROR - 程序遇到无法恢复的错误")
        print(f"{'=' * 50}")
        print(error_msg)
        print(f"{'=' * 50}")
        print(f"  日志目录: {_log_dir}")
        print("  请检查上方错误信息，修复后重新启动")
        print(f"{'=' * 50}")
        try:
            logger.critical(f"Fatal error: {e}\n{error_msg}")
        except Exception:
            pass
        _graceful_shutdown()
        input("\n按回车键退出...")

