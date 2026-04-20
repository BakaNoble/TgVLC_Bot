"""VLC player integration and playback state management."""
import ctypes
import logging
import os
import re
import threading
import time
import urllib.parse
from ctypes import wintypes
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import psutil
import vlc

from config import config

logger = logging.getLogger(__name__)

SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_EX_DLGMODALFRAME = 0x00000001
WS_EX_CLIENTEDGE = 0x00000200
WS_EX_STATICEDGE = 0x00020000
MONITOR_DEFAULTTONEAREST = 0x00000002


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class PlayMode(Enum):
    """Playback mode enum."""

    SEQUENCE = "sequence"
    SINGLE = "single"
    SINGLE_LOOP = "single_loop"


MODE_ICONS = {
    "顺序播放": "⏭️",
    "单集播放": "▶️",
    "单集循环": "🔁",
}

MODE_NAMES = {
    PlayMode.SEQUENCE: "顺序播放",
    PlayMode.SINGLE: "单集播放",
    PlayMode.SINGLE_LOOP: "单集循环",
}

_EPISODE_PATTERNS = [
    re.compile(r"[Ss](\d{1,2})[Ee](\d{1,2})"),
    re.compile(r"(\d{1,2})[xX](\d{1,2})"),
    re.compile(r"[Ss]eason[\s._-]*(\d{1,2})[\s._-]*[Ee]p?(?:isode)?[\s._-]*(\d{1,2})"),
]
_SUBTITLE_FORMATS = {".ass", ".ssa", ".srt", ".sub", ".txt"}


def _extract_episode_token(name: str) -> Optional[str]:
    """Extract a normalized episode token like ``S01E02`` from a file name."""
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(name)
        if match:
            season = match.group(1).zfill(2)
            episode = match.group(2).zfill(2)
            return f"S{season}E{episode}"
    return None


class VLCPlayer:
    """Central VLC controller with thread-safe playback state."""

    MODE_NAMES = MODE_NAMES

    def __init__(self):
        self.instance: Optional[vlc.Instance] = None
        self.player: Optional[vlc.MediaPlayer] = None
        self.current_file: Optional[str] = None
        self.video_list: List[str] = []
        self.current_video_index: int = -1
        self.play_mode: PlayMode = PlayMode.SEQUENCE
        self.is_fullscreen: bool = False

        self._is_playing: bool = False
        self._last_check_time: float = 0.0
        self._last_status_text: str = "播放器未初始化"
        self._last_playback_position: int = 0
        self._playback_stalled_counter: int = 0
        self._playback_end_pending: bool = False

        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running: bool = False
        self._end_handling_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self._vlc_call_timeout: float = 5.0
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 5
        self._recovery_attempts: int = 0
        self._max_recovery_attempts: int = 3
        self._recovery_lock = threading.Lock()

        self._vlc_was_playing: bool = False
        self._vlc_process: Optional[psutil.Process] = None
        self._on_crash_callback: Optional[Callable[[str], None]] = None

        self._external_subtitle_paths: Dict[int, str] = {}
        self._current_external_subtitle: Optional[str] = None

        self._windowed_rect: Optional[Tuple[int, int, int, int]] = None
        self._windowed_style: Optional[int] = None
        self._windowed_ex_style: Optional[int] = None
        self._vlc_hwnd = None

    def initialize(self) -> bool:
        """Initialize VLC and attach playback event handlers."""
        if not os.path.exists(config.vlc_path):
            logger.error("VLC not found: %s", config.vlc_path)
            return False

        try:
            vlc_args = [
                "--no-video-title-show",
                "--no-osd",
                "--play-and-pause",
                "--verbose=0",
                "--subsdec-encoding=UTF-8",
            ]
            self.instance = vlc.Instance(vlc_args)
            if self.instance is None:
                logger.error("Failed to create VLC instance")
                return False

            self.player = self.instance.media_player_new()
            if self.player is None:
                logger.error("Failed to create VLC media player")
                return False

            event_manager = self.player.event_manager()
            event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_media_end)
            event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_play)
            event_manager.event_attach(vlc.EventType.MediaPlayerPaused, self._on_pause)
            event_manager.event_attach(vlc.EventType.MediaPlayerStopped, self._on_stop)

            self._start_playback_monitor()
            self._track_vlc_process()
            self._last_status_text = "播放器已就绪，等待播放"
            logger.info("VLC player initialized successfully")
            return True
        except Exception as exc:
            logger.error("VLC initialization failed: %s", exc)
            return False

    def set_crash_callback(self, callback: Callable[[str], None]) -> None:
        self._on_crash_callback = callback

    def _on_media_end(self, event) -> None:
        logger.info("VLC event: playback ended")
        with self._state_lock:
            self._playback_end_pending = True
            self._is_playing = False

    def _on_play(self, event) -> None:
        with self._state_lock:
            self._is_playing = True
            self._consecutive_errors = 0
            self._vlc_was_playing = True

    def _on_pause(self, event) -> None:
        with self._state_lock:
            self._is_playing = False

    def _on_stop(self, event) -> None:
        with self._state_lock:
            self._is_playing = False

    def _track_vlc_process(self) -> None:
        if not config.vlc_path:
            return
        try:
            vlc_exe_name = os.path.basename(config.vlc_path).lower()
            current_pid = os.getpid()
            for proc in psutil.process_iter(["name", "pid"]):
                try:
                    proc_name = (proc.info["name"] or "").lower()
                    if proc_name == vlc_exe_name and proc.info["pid"] != current_pid:
                        self._vlc_process = psutil.Process(proc.info["pid"])
                        logger.info("Tracking VLC process: PID=%s", proc.info["pid"])
                        return
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:
            logger.warning("Failed to track VLC process: %s", exc)

    def _is_vlc_process_alive(self) -> bool:
        if not self._vlc_was_playing:
            return True
        if self._vlc_process is None:
            self._track_vlc_process()
            return True if self._vlc_process is None else self._is_vlc_process_alive()
        try:
            return self._vlc_process.is_running() and self._vlc_process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self._vlc_process = None
            return False

    def _safe_vlc_call(self, func, *args, timeout: Optional[float] = None):
        """Run a VLC API call in a short-lived helper thread with timeout protection."""
        timeout = self._vlc_call_timeout if timeout is None else timeout
        result = [None]
        error = [None]

        def _call() -> None:
            try:
                result[0] = func(*args)
            except Exception as exc:
                error[0] = exc

        thread = threading.Thread(target=_call, daemon=True)
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            logger.warning("VLC API call timed out after %.2fs: %s", timeout, getattr(func, "__name__", func))
            with self._state_lock:
                self._consecutive_errors += 1
            return None

        if error[0] is not None:
            raise error[0]
        return result[0]

    def _check_vlc_health(self) -> bool:
        if not self._is_vlc_process_alive():
            logger.error("VLC process is not alive, attempting recovery")
            self._try_recover_vlc()
            return False

        with self._state_lock:
            too_many_errors = self._consecutive_errors >= self._max_consecutive_errors

        if too_many_errors:
            logger.error("VLC appears unresponsive, attempting recovery")
            self._try_recover_vlc()
            return False
        return True

    def _try_recover_vlc(self) -> None:
        if not self._recovery_lock.acquire(timeout=1.0):
            logger.warning("Recovery already in progress, skipping duplicate attempt")
            return

        try:
            if self._recovery_attempts >= self._max_recovery_attempts:
                message = (
                    f"VLC 恢复失败，已达到最大尝试次数（{self._max_recovery_attempts} 次）。"
                    "请检查 VLC 或重启程序。"
                )
                logger.error(message)
                self._notify_crash(message)
                return

            self._recovery_attempts += 1
            logger.info("VLC recovery attempt %s/%s", self._recovery_attempts, self._max_recovery_attempts)

            with self._state_lock:
                saved_file = self.current_file
                saved_video_list = list(self.video_list)
                saved_index = self.current_video_index
                saved_mode = self.play_mode

            self._stop_playback_monitor()

            try:
                if self.player is not None:
                    self.player.stop()
                    self.player.release()
            except Exception:
                pass

            try:
                if self.instance is not None:
                    self.instance.release()
            except Exception:
                pass

            self.player = None
            self.instance = None
            self._vlc_process = None
            self._vlc_hwnd = None

            with self._state_lock:
                self._is_playing = False
                self.current_file = None
                self._playback_end_pending = False

            time.sleep(1.0)

            if not self.initialize():
                logger.error("VLC recovery failed during reinitialization")
                return

            with self._state_lock:
                self.video_list = saved_video_list
                self.current_video_index = saved_index
                self.play_mode = saved_mode
                self._consecutive_errors = 0
                self._recovery_attempts = 0

            if saved_file and (self._is_url(saved_file) or os.path.exists(saved_file)):
                success, _ = self.open_file(saved_file, saved_video_list, saved_index)
                if success:
                    logger.info("Recovered playback: %s", os.path.basename(saved_file))
        except Exception as exc:
            logger.error("VLC recovery attempt failed: %s", exc)
            with self._state_lock:
                self._consecutive_errors = 0
        finally:
            self._recovery_lock.release()

    def _notify_crash(self, message: str) -> None:
        if self._on_crash_callback is None:
            return
        try:
            self._on_crash_callback(message)
        except Exception as exc:
            logger.error("Crash callback failed: %s", exc)

    def _find_external_subtitles(self, video_path: str) -> List[Tuple[int, str]]:
        """Return subtitle candidates, preferring exact same-episode matches."""
        self._external_subtitle_paths.clear()
        if not video_path:
            return []

        video_dir = os.path.dirname(video_path)
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        if not video_dir or not os.path.isdir(video_dir):
            return []

        logger.info("Scanning for external subtitles in: %s", video_dir)
        logger.info("Video name: %s", video_name)

        video_episode = _extract_episode_token(video_name)
        logger.info("Video episode token: %s", video_episode or "none")

        matched: List[Tuple[str, str]] = []
        all_subtitles: List[Tuple[str, str]] = []

        try:
            for entry in os.scandir(video_dir):
                if not entry.is_file():
                    continue
                name, ext = os.path.splitext(entry.name)
                if ext.lower() not in _SUBTITLE_FORMATS:
                    continue

                all_subtitles.append((entry.path, entry.name))
                subtitle_episode = _extract_episode_token(name)
                if video_episode and subtitle_episode == video_episode:
                    matched.append((entry.path, entry.name))
                    logger.info("Matched subtitle: %s (episode: %s)", entry.name, video_episode)
        except Exception as exc:
            logger.warning("Failed to scan subtitles for %s: %s", video_path, exc)
            return []

        selected = matched if matched else all_subtitles
        if not selected:
            return []

        selected = sorted(selected, key=lambda item: item[1].lower())

        results: List[Tuple[int, str]] = []
        for index, (subtitle_path, subtitle_name) in enumerate(selected, start=1):
            track_id = -index
            self._external_subtitle_paths[track_id] = subtitle_path
            results.append((track_id, f"外挂字幕 {subtitle_name}"))

        logger.info(
            "Found %s external subtitles (%s mode)",
            len(results),
            "episode-matched" if matched else "fallback-all",
        )
        return results

    def _select_first_subtitle(self) -> None:
        """Auto-load the best matching external subtitle when available."""
        if not self.current_file:
            return
        external_tracks = self._find_external_subtitles(self.current_file)
        if external_tracks:
            self.set_subtitle_track(external_tracks[0][0])

    def get_subtitle_tracks(self) -> List[Tuple[int, str]]:
        """Get external subtitles first, then embedded subtitle tracks."""
        try:
            tracks: List[Tuple[int, str]] = []

            if self.current_file:
                tracks.extend(self._find_external_subtitles(self.current_file))

            if self.player is None:
                return tracks

            descriptions = self.player.video_get_spu_description()
            if not descriptions:
                return tracks

            for track_id, name in descriptions:
                if track_id == -1:
                    continue
                if isinstance(name, bytes):
                    label = name.decode("utf-8", errors="ignore")
                else:
                    label = str(name)
                tracks.append((track_id, label))
            return tracks
        except Exception as exc:
            logger.error("Failed to get subtitle tracks: %s", exc)
            return []

    def set_subtitle_track(self, track_id: int) -> Tuple[bool, str]:
        """Switch to an embedded or external subtitle track."""
        if self.player is None:
            return False, "播放器未初始化"

        try:
            if track_id < 0:
                subtitle_path = self._external_subtitle_paths.get(track_id)
                if not subtitle_path:
                    return False, "无效的外挂字幕"
                if not os.path.exists(subtitle_path):
                    return False, "字幕文件不存在"

                self.player.video_set_spu(-1)
                time.sleep(0.05)
                self.player.video_set_subtitle_file(subtitle_path)
                self._current_external_subtitle = subtitle_path
                logger.info("External subtitle loaded: %s", subtitle_path)
                return True, "外挂字幕已加载"

            descriptions = self.player.video_get_spu_description()
            available_track_ids = {
                tid for tid, _ in (descriptions or []) if tid >= 0
            }
            if track_id not in available_track_ids:
                return False, "无效的字幕轨道"

            result = self._safe_vlc_call(self.player.video_set_spu, track_id, timeout=3.0)
            if result is None:
                return False, "字幕切换失败：VLC 无响应"
            self._current_external_subtitle = None
            return True, "字幕已切换"
        except Exception as exc:
            logger.error("Failed to set subtitle track %s: %s", track_id, exc)
            return False, f"字幕切换失败: {exc}"

    def get_current_subtitle_track(self) -> Tuple[int, str]:
        """Return the active subtitle track identifier and display name."""
        if self._current_external_subtitle:
            return -1, f"外挂字幕 {os.path.basename(self._current_external_subtitle)}"

        if self.player is None:
            return -1, "无字幕"

        try:
            current_spu = self._safe_vlc_call(self.player.video_get_spu, timeout=3.0)
            if current_spu is None or current_spu < 0:
                return -1, "无字幕"

            for track_id, track_name in self.get_subtitle_tracks():
                if track_id == current_spu:
                    return track_id, track_name
        except Exception as exc:
            logger.error("Failed to get current subtitle track: %s", exc)

        return -1, "无字幕"

    def has_multiple_subtitles(self) -> bool:
        return len(self.get_subtitle_tracks()) > 1

    @staticmethod
    def _is_url(path: str) -> bool:
        return path.startswith(("http://", "https://"))

    def open_file(
        self,
        file_path: str,
        video_list: Optional[List[str]] = None,
        current_index: int = -1,
    ) -> Tuple[bool, str]:
        """Open a local file or HTTP URL and start playback immediately."""
        if self.instance is None or self.player is None:
            return False, "播放器未初始化"

        is_url = self._is_url(file_path)
        if not is_url and not os.path.isfile(file_path):
            return False, "视频文件不存在"

        normalized_path = file_path if is_url else os.path.normpath(file_path)

        try:
            self.stop()

            play_url = normalized_path
            if is_url:
                webdav_src = config.get_webdav_credentials(normalized_path)
                if webdav_src and webdav_src.username:
                    parsed = urllib.parse.urlparse(normalized_path)
                    userinfo = f"{urllib.parse.quote(webdav_src.username, safe='')}:{urllib.parse.quote(webdav_src.password, safe='')}"
                    authed = parsed._replace(netloc=f"{userinfo}@{parsed.hostname}" + (f":{parsed.port}" if parsed.port else ""))
                    play_url = urllib.parse.urlunparse(authed)
            media = self.instance.media_new(play_url)
            self.player.set_media(media)
            media.release()

            with self._state_lock:
                self.current_file = normalized_path
                self._is_playing = False
                self._playback_end_pending = False
                self._last_playback_position = 0
                self._playback_stalled_counter = 0
                self._external_subtitle_paths.clear()
                self._current_external_subtitle = None
                if video_list is not None:
                    self.video_list = [
                        p if self._is_url(p) else os.path.normpath(p)
                        for p in video_list
                    ]
                    self.current_video_index = current_index

            result = self._safe_vlc_call(self.player.play, timeout=3.0)
            if result is None:
                return False, "播放失败：VLC 无响应"
            if result == -1:
                return False, "打开文件失败"

            self._track_vlc_process()
            time.sleep(0.5)
            self._select_first_subtitle()

            display_name = urllib.parse.unquote(normalized_path.rsplit("/", 1)[-1]) if is_url else os.path.basename(normalized_path)
            logger.info("Now playing: %s", display_name)
            return True, f"正在播放: {display_name}"
        except Exception as exc:
            logger.error("Failed to open file %s: %s", normalized_path, exc)
            return False, f"打开文件失败: {exc}"

    def play(self) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        with self._state_lock:
            if self.current_file is None:
                return False, "没有加载文件"

        result = self._safe_vlc_call(self.player.play, timeout=3.0)
        if result is None:
            return False, "播放失败：VLC 无响应"
        if result == -1:
            return False, "播放失败"
        return True, "正在播放"

    def pause(self) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        self._safe_vlc_call(self.player.pause, timeout=3.0)
        return True, "已暂停"

    def stop(self) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        try:
            self._safe_vlc_call(self.player.stop, timeout=3.0)
            with self._state_lock:
                self._is_playing = False
                self.current_file = None
                self._playback_end_pending = False
                self._external_subtitle_paths.clear()
                self._current_external_subtitle = None
            return True, "已停止"
        except Exception as exc:
            logger.error("Failed to stop playback: %s", exc)
            return False, f"停止失败: {exc}"

    def seek(self, position: float) -> Tuple[bool, str]:
        """Seek by percentage, 0-100."""
        if self.player is None:
            return False, "播放器未初始化"
        if position < 0 or position > 100:
            return False, "跳转位置必须在 0-100 之间"

        total_time = self._safe_vlc_call(self.player.get_length, timeout=3.0)
        if total_time is None or total_time <= 0:
            return False, "无法获取媒体总时长"

        try:
            target_time = int(total_time * (position / 100.0))
            self._safe_vlc_call(self.player.set_time, target_time, timeout=3.0)
            return True, f"已跳转到 {position:.0f}%"
        except Exception as exc:
            logger.error("Seek failed: %s", exc)
            return False, f"跳转失败: {exc}"

    def seek_forward(self, seconds: Optional[int] = None) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        seconds = config.seek_step if seconds is None else seconds
        try:
            current_time = self._safe_vlc_call(self.player.get_time, timeout=3.0)
            total_time = self._safe_vlc_call(self.player.get_length, timeout=3.0)
            if current_time is None or total_time is None:
                return False, "无法获取播放时间：VLC 无响应"
            if current_time < 0 or total_time <= 0:
                return False, "无法获取播放时间"

            new_time = min(current_time + seconds * 1000, total_time)
            self._safe_vlc_call(self.player.set_time, new_time, timeout=3.0)
            return True, f"已前进 {seconds} 秒"
        except Exception as exc:
            logger.error("Seek forward failed: %s", exc)
            return False, f"快进失败: {exc}"

    def seek_backward(self, seconds: Optional[int] = None) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        seconds = config.seek_step if seconds is None else seconds
        try:
            current_time = self._safe_vlc_call(self.player.get_time, timeout=3.0)
            if current_time is None:
                return False, "无法获取播放时间：VLC 无响应"
            if current_time < 0:
                return False, "无法获取播放时间"

            new_time = max(current_time - seconds * 1000, 0)
            self._safe_vlc_call(self.player.set_time, new_time, timeout=3.0)
            return True, f"已后退 {seconds} 秒"
        except Exception as exc:
            logger.error("Seek backward failed: %s", exc)
            return False, f"后退失败: {exc}"

    def set_volume(self, volume: int) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        if volume < 0 or volume > 100:
            return False, "音量必须在 0-100 之间"
        try:
            self._safe_vlc_call(self.player.audio_set_volume, volume, timeout=3.0)
            return True, f"音量已设置为 {volume}%"
        except Exception as exc:
            logger.error("Set volume failed: %s", exc)
            return False, f"音量设置失败: {exc}"

    def volume_up(self, step: Optional[int] = None) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        step = config.volume_step if step is None else step
        try:
            current_volume = self._safe_vlc_call(self.player.audio_get_volume, timeout=3.0)
            if current_volume is None:
                return False, "音量调整失败：VLC 无响应"
            new_volume = min(int(current_volume) + step, 100)
            self._safe_vlc_call(self.player.audio_set_volume, new_volume, timeout=3.0)
            return True, f"音量已提高到 {new_volume}%"
        except Exception as exc:
            logger.error("Volume up failed: %s", exc)
            return False, f"音量调整失败: {exc}"

    def volume_down(self, step: Optional[int] = None) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        step = config.volume_step if step is None else step
        try:
            current_volume = self._safe_vlc_call(self.player.audio_get_volume, timeout=3.0)
            if current_volume is None:
                return False, "音量调整失败：VLC 无响应"
            new_volume = max(int(current_volume) - step, 0)
            self._safe_vlc_call(self.player.audio_set_volume, new_volume, timeout=3.0)
            return True, f"音量已降低到 {new_volume}%"
        except Exception as exc:
            logger.error("Volume down failed: %s", exc)
            return False, f"音量调整失败: {exc}"

    def toggle_mute(self) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        try:
            self._safe_vlc_call(self.player.audio_toggle_mute, timeout=3.0)
            is_muted = self._safe_vlc_call(self.player.audio_get_mute, timeout=3.0)
            if is_muted is None:
                return False, "静音切换失败：VLC 无响应"
            return True, "已静音" if is_muted else "已取消静音"
        except Exception as exc:
            logger.error("Mute toggle failed: %s", exc)
            return False, f"静音切换失败: {exc}"

    def toggle_fullscreen(self) -> Tuple[bool, str]:
        if self.player is None:
            return False, "播放器未初始化"
        try:
            self.is_fullscreen = not self.is_fullscreen
            self._safe_vlc_call(self.player.set_fullscreen, self.is_fullscreen, timeout=3.0)
            if self.is_fullscreen:
                self._activate_vlc_window()
                time.sleep(0.2)
                self._force_true_fullscreen()
            else:
                self._restore_windowed_mode()
            return True, "全屏模式" if self.is_fullscreen else "窗口模式"
        except Exception as exc:
            logger.error("Fullscreen toggle failed: %s", exc)
            return False, f"全屏切换失败: {exc}"

    def _force_true_fullscreen(self) -> None:
        """Make the VLC window topmost and borderless on the current monitor."""
        try:
            user32 = ctypes.windll.user32
            hwnd = self._find_vlc_window()
            if not hwnd:
                return

            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            self._windowed_rect = (rect.left, rect.top, rect.right, rect.bottom)
            self._windowed_style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            self._windowed_ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            if not monitor:
                return

            monitor_info = MONITORINFO()
            monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
            if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
                return

            fullscreen_style = self._windowed_style & ~(
                WS_CAPTION | WS_THICKFRAME | WS_MINIMIZE | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU
            )
            fullscreen_ex_style = self._windowed_ex_style & ~(
                WS_EX_DLGMODALFRAME | WS_EX_CLIENTEDGE | WS_EX_STATICEDGE
            )

            user32.SetWindowLongW(hwnd, GWL_STYLE, fullscreen_style)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, fullscreen_ex_style)

            left = monitor_info.rcMonitor.left
            top = monitor_info.rcMonitor.top
            width = monitor_info.rcMonitor.right - monitor_info.rcMonitor.left
            height = monitor_info.rcMonitor.bottom - monitor_info.rcMonitor.top

            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                left,
                top,
                width,
                height,
                SWP_FRAMECHANGED | SWP_SHOWWINDOW,
            )
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
        except Exception as exc:
            logger.warning("Failed to force true fullscreen: %s", exc)

    def _restore_windowed_mode(self) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = self._find_vlc_window()
            if not hwnd:
                return

            if self._windowed_style is not None:
                user32.SetWindowLongW(hwnd, GWL_STYLE, self._windowed_style)
            if self._windowed_ex_style is not None:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, self._windowed_ex_style)

            if self._windowed_rect is not None:
                left, top, right, bottom = self._windowed_rect
                user32.SetWindowPos(
                    hwnd,
                    HWND_NOTOPMOST,
                    left,
                    top,
                    max(right - left, 0),
                    max(bottom - top, 0),
                    SWP_FRAMECHANGED | SWP_SHOWWINDOW,
                )
            else:
                user32.SetWindowPos(
                    hwnd,
                    HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
                )
        except Exception as exc:
            logger.warning("Failed to restore windowed mode: %s", exc)

    def _activate_vlc_window(self) -> None:
        try:
            user32 = ctypes.windll.user32
            hwnd = self._find_vlc_window()
            if not hwnd:
                return
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
        except Exception as exc:
            logger.warning("Failed to activate VLC window: %s", exc)

    def _find_vlc_window(self):
        try:
            user32 = ctypes.windll.user32
            if self._vlc_hwnd is not None:
                if user32.IsWindow(self._vlc_hwnd):
                    return self._vlc_hwnd
                self._vlc_hwnd = None

            windows = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            def callback(hwnd, lparam):
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    title = buffer.value
                    if "VLC" in title:
                        windows.append(hwnd)
                except Exception:
                    pass
                return True

            user32.EnumWindows(callback, 0)
            self._vlc_hwnd = windows[0] if windows else None
            return self._vlc_hwnd
        except Exception as exc:
            logger.warning("Failed to find VLC window: %s", exc)
            return None

    def get_status(self) -> str:
        """Return a stable human-readable playback status string."""
        if self.player is None:
            return "播放器未初始化"

        now = time.time()
        if now - self._last_check_time < 0.5:
            return self._last_status_text

        self._last_check_time = now

        try:
            with self._state_lock:
                current_file = self.current_file
                is_playing = self._is_playing
                mode_name = self.MODE_NAMES[self.play_mode]

            if not current_file:
                self._last_status_text = (
                    "播放器状态\n\n"
                    "文件: 未加载\n"
                    f"模式: {mode_name}\n"
                    "状态: 空闲"
                )
                return self._last_status_text

            player = self.player
            def _batch_status():
                return (
                    player.get_time(),
                    player.get_length(),
                    player.audio_get_volume(),
                    player.audio_get_mute(),
                )
            batch = self._safe_vlc_call(_batch_status, timeout=5.0)
            if batch is not None:
                current_time, total_time, volume, muted = batch
            else:
                current_time = total_time = volume = muted = None

            status_label = "播放中" if is_playing else "已暂停"
            self._last_status_text = (
                "播放器状态\n\n"
                f"文件: {urllib.parse.unquote(current_file.rsplit('/', 1)[-1]) if self._is_url(current_file) else os.path.basename(current_file)}\n"
                f"状态: {status_label}\n"
                f"模式: {mode_name}\n"
                f"进度: {self._format_time(current_time if isinstance(current_time, int) else -1)}"
                f" / {self._format_time(total_time if isinstance(total_time, int) else -1)}\n"
                f"音量: {int(volume) if isinstance(volume, int) and volume >= 0 else 0}%"
                f"{'（静音）' if muted else ''}\n"
                f"显示: {'全屏' if self.is_fullscreen else '窗口'}"
            )
            return self._last_status_text
        except Exception as exc:
            logger.error("Failed to build playback status: %s", exc)
            return "播放器状态获取失败"

    def cleanup(self) -> None:
        try:
            self._stop_playback_monitor()
            if self.player is not None:
                self.player.stop()
                self.player.release()
                self.player = None
            if self.instance is not None:
                self.instance.release()
                self.instance = None
            self._vlc_hwnd = None
            logger.info("VLC player resources cleaned up")
        except Exception as exc:
            logger.error("Failed to cleanup VLC resources: %s", exc)

    def _start_playback_monitor(self) -> None:
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._playback_monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Playback monitor thread started")

    def _stop_playback_monitor(self) -> None:
        self._monitor_running = False
        if self._monitor_thread is not None and self._monitor_thread is not threading.current_thread():
            self._monitor_thread.join(timeout=2.0)
        self._monitor_thread = None

    def _playback_monitor_loop(self) -> None:
        logger.info("Playback monitor loop started")
        # Adaptive polling: high frequency when playing, low frequency when idle.
        playing_interval = 1.0      # s, active playback polling
        idle_interval = 5.0         # s, no active playback
        process_check_interval = 10.0  # s, minimum interval between process alive checks
        last_process_check = 0.0

        while self._monitor_running:
            try:
                with self._state_lock:
                    pending = self._playback_end_pending
                    should_check = self.player is not None and self._is_playing

                if pending:
                    self._handle_playback_end()
                    time.sleep(0.2)
                    continue

                now = time.time()
                # Run process-alive check on a time interval (not per-iteration),
                # so idle mode doesn't trigger it every loop.
                if now - last_process_check >= process_check_interval:
                    last_process_check = now
                    if not self._is_vlc_process_alive():
                        self._try_recover_vlc()
                        self._interruptible_sleep(1.0)
                        continue

                if should_check and self.player is not None:
                    current_time = self._safe_vlc_call(self.player.get_time, timeout=3.0)
                    total_time = self._safe_vlc_call(self.player.get_length, timeout=3.0)

                    if current_time is None or total_time is None:
                        with self._state_lock:
                            self._consecutive_errors += 1
                        self._check_vlc_health()
                        self._interruptible_sleep(1.0)
                        continue

                    with self._state_lock:
                        self._consecutive_errors = 0

                    if total_time > 0 and current_time >= total_time - 500:
                        with self._state_lock:
                            self._playback_end_pending = True
                            self._is_playing = False
                    elif current_time > 0 and current_time == self._last_playback_position:
                        self._playback_stalled_counter += 1
                        if self._playback_stalled_counter > 10:
                            logger.warning("Playback appears stalled")
                            self._playback_stalled_counter = 0
                    else:
                        self._playback_stalled_counter = 0

                    self._last_playback_position = current_time
                    self._interruptible_sleep(playing_interval)
                else:
                    # Idle: reset stall counter and sleep longer to reduce CPU load.
                    self._playback_stalled_counter = 0
                    self._last_playback_position = 0
                    self._interruptible_sleep(idle_interval)
            except Exception as exc:
                logger.error("Error in playback monitor loop: %s", exc)
                self._interruptible_sleep(1.0)

        logger.info("Playback monitor loop ended")

    def _interruptible_sleep(self, duration: float) -> None:
        """Sleep in small slices so shutdown can interrupt long idle waits."""
        slice_size = 0.5
        remaining = duration
        while remaining > 0 and self._monitor_running:
            step = slice_size if remaining > slice_size else remaining
            time.sleep(step)
            remaining -= step

    def _handle_playback_end(self) -> None:
        if not self._end_handling_lock.acquire(timeout=1.0):
            return

        try:
            with self._state_lock:
                if not self._playback_end_pending:
                    return
                self._playback_end_pending = False
                current_index = self.current_video_index
                current_file = self.current_file
                playlist = list(self.video_list)
                mode = self.play_mode

            if not playlist or self.instance is None or self.player is None:
                return

            if mode == PlayMode.SEQUENCE:
                if 0 <= current_index < len(playlist) - 1:
                    next_index = current_index + 1
                    next_file = playlist[next_index]
                    if self._is_url(next_file) or os.path.exists(next_file):
                        logger.info("Auto-playing next file: %s", os.path.basename(next_file))
                        self.open_file(next_file, playlist, next_index)
            elif mode == PlayMode.SINGLE_LOOP:
                if current_file and (self._is_url(current_file) or os.path.exists(current_file)):
                    logger.info("Replaying current file in single-loop mode")
                    self.open_file(current_file, playlist, current_index)
        finally:
            self._end_handling_lock.release()

    @staticmethod
    def _format_time(ms: int) -> str:
        """Format milliseconds into ``HH:MM:SS`` or ``MM:SS``."""
        if ms is None or ms < 0:
            return "00:00:00"

        total_seconds = ms // 1000
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def set_play_mode(self, mode: PlayMode) -> Tuple[bool, str]:
        self.play_mode = mode
        logger.info("Play mode changed to: %s", self.MODE_NAMES[mode])
        return True, f"播放模式已切换为: {self.MODE_NAMES[mode]}"

    def toggle_play_mode(self) -> Tuple[bool, str]:
        modes = [PlayMode.SEQUENCE, PlayMode.SINGLE, PlayMode.SINGLE_LOOP]
        next_index = (modes.index(self.play_mode) + 1) % len(modes)
        return self.set_play_mode(modes[next_index])

    def get_play_mode(self) -> Tuple[str, str]:
        return self.play_mode.value, self.MODE_NAMES[self.play_mode]

    def is_player_running(self) -> bool:
        return self.player is not None


vlc_player = VLCPlayer()
