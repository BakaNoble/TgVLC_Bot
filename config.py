"""
Configuration management for TgVLC_Bot.

Loads and persists runtime settings from ``config.yaml``.
"""
import copy
import logging
import os
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)


def get_app_dir() -> str:
    """Return the application directory for source and frozen builds."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


@dataclass
class WebDAVSource:
    """A single WebDAV mount configuration."""
    name: str
    url: str
    username: str = ""
    password: str = ""


class Config:
    """Centralized configuration object."""

    DEFAULT_VIDEO_EXTENSIONS = [
        '.mp4', '.avi', '.mkv', '.mov', '.wmv',
        '.flv', '.webm', '.m4v', '.mpg', '.mpeg'
    ]

    DEFAULT_CONFIG = {
        'telegram': {
            'token': 'YOUR_TELEGRAM_BOT_TOKEN'
        },
        'proxy': {
            'enabled': False,
            'type': 'socks5',
            'host': '127.0.0.1',
            'port': 1080,
            'username': '',
            'password': ''
        },
        'vlc': {
            'path': r'C:\Program Files\VideoLAN\VLC\vlc.exe'
        },
        'video': {
            'directories': [],
            'extensions': DEFAULT_VIDEO_EXTENSIONS.copy()
        },
        'controls': {
            'volume_step': 10,
            'seek_step': 30,
            'page_size': 10
        },
        'security': {
            'allowed_user_ids': [],
            'admin_user_ids': []
        },
        'webdav': []
    }

    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or os.path.join(get_app_dir(), "config.yaml")
        self.config_data: dict = {}
        self._lock = threading.RLock()
        self._init_config()
        self.load_config()

    def _init_config(self) -> None:
        self.telegram_token: str = ""
        self.vlc_path: str = ""
        self.video_directories: List[str] = []
        self.video_extensions: List[str] = self.DEFAULT_VIDEO_EXTENSIONS.copy()

        self.volume_step: int = 10
        self.seek_step: int = 30
        self.page_size: int = 10

        self.proxy_enabled: bool = False
        self.proxy_type: str = "socks5"
        self.proxy_host: str = "127.0.0.1"
        self.proxy_port: int = 1080
        self.proxy_username: str = ""
        self.proxy_password: str = ""

        self.allowed_user_ids: List[int] = []
        self.admin_user_ids: List[int] = []

        self.webdav_sources: List['WebDAVSource'] = []

    def load_config(self) -> bool:
        """Load settings from YAML, creating defaults when needed."""
        with self._lock:
            if not os.path.exists(self.config_file):
                logger.warning(f"Config file not found: {self.config_file}, creating default config")
                self._create_default_config()
                return False

            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = yaml.safe_load(f)

                if not loaded_config:
                    logger.warning("Empty config file, creating default config")
                    self._create_default_config()
                    return False

                self.config_data = loaded_config
                self._parse_config()
                logger.info("Configuration loaded successfully")
                return True

            except yaml.YAMLError as e:
                logger.error(f"YAML parse error: {e}")
                self._create_default_config()
                return False
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self._create_default_config()
                return False

    def _parse_config(self) -> None:
        """Parse loaded configuration into typed attributes."""
        try:
            telegram_config = self.config_data.get('telegram', {})
            self.telegram_token = str(telegram_config.get('token', ''))

            proxy_config = self.config_data.get('proxy', {})
            self.proxy_enabled = bool(proxy_config.get('enabled', False))
            self.proxy_type = str(proxy_config.get('type', 'socks5'))
            self.proxy_host = str(proxy_config.get('host', '127.0.0.1'))
            self.proxy_port = self._validate_int(
                proxy_config.get('port', 1080), 1, 65535, 1080
            )
            self.proxy_username = str(proxy_config.get('username', ''))
            self.proxy_password = str(proxy_config.get('password', ''))

            vlc_config = self.config_data.get('vlc', {})
            self.vlc_path = str(
                vlc_config.get('path', r'C:\Program Files\VideoLAN\VLC\vlc.exe')
            )

            video_config = self.config_data.get('video', {})
            directories = video_config.get('directories', [])
            self.video_directories = (
                [os.path.normpath(str(directory)) for directory in directories]
                if isinstance(directories, list) else []
            )

            extensions = video_config.get('extensions', self.DEFAULT_VIDEO_EXTENSIONS.copy())
            self.video_extensions = (
                [str(extension) for extension in extensions]
                if isinstance(extensions, list) else self.DEFAULT_VIDEO_EXTENSIONS.copy()
            )

            controls_config = self.config_data.get('controls', {})
            self.volume_step = self._validate_int(
                controls_config.get('volume_step', 10), 1, 100, 10
            )
            self.seek_step = self._validate_int(
                controls_config.get('seek_step', 30), 1, 300, 30
            )
            self.page_size = self._validate_int(
                controls_config.get('page_size', 10), 5, 50, 10
            )

            security_config = self.config_data.get('security', {})
            self.allowed_user_ids = self._parse_user_ids(
                security_config.get('allowed_user_ids', [])
            )
            self.admin_user_ids = self._parse_user_ids(
                security_config.get('admin_user_ids', [])
            )

            self.webdav_sources = self._parse_webdav_sources(
                self.config_data.get('webdav', [])
            )

        except Exception as e:
            logger.error(f"Config parse error: {e}")
            self._create_default_config()

    def _parse_user_ids(self, user_ids: any) -> List[int]:
        """Parse a list of user IDs into integers."""
        if not user_ids:
            return []

        if not isinstance(user_ids, list):
            logger.warning(f"user_ids should be a list, got {type(user_ids).__name__}")
            return []

        result: List[int] = []
        for uid in user_ids:
            try:
                result.append(int(uid))
            except (ValueError, TypeError):
                logger.warning(f"Invalid user_id value: {uid!r}, skipping")
        return result

    @staticmethod
    def _validate_int(value: any, min_val: int, max_val: int, default: int) -> int:
        """Clamp an integer value into the allowed range."""
        try:
            result = int(value)
            return max(min_val, min(max_val, result))
        except (ValueError, TypeError):
            return default

    def _create_default_config(self) -> None:
        """Create and persist the default config."""
        try:
            default_config = copy.deepcopy(self.DEFAULT_CONFIG)
            self._write_config_file(default_config)
            logger.info(f"Default config file created: {self.config_file}")
            self.config_data = default_config
            self._parse_config()
        except Exception as e:
            logger.error(f"Failed to create default config: {e}")

    def _build_config_data(self) -> dict:
        return {
            'telegram': {
                'token': self.telegram_token
            },
            'proxy': {
                'enabled': self.proxy_enabled,
                'type': self.proxy_type,
                'host': self.proxy_host,
                'port': self.proxy_port,
                'username': self.proxy_username,
                'password': self.proxy_password
            },
            'vlc': {
                'path': self.vlc_path
            },
            'video': {
                'directories': list(self.video_directories),
                'extensions': list(self.video_extensions)
            },
            'controls': {
                'volume_step': self.volume_step,
                'seek_step': self.seek_step,
                'page_size': self.page_size
            },
            'security': {
                'allowed_user_ids': list(self.allowed_user_ids),
                'admin_user_ids': list(self.admin_user_ids)
            },
            'webdav': [
                {
                    'name': src.name,
                    'url': src.url,
                    'username': src.username,
                    'password': src.password,
                }
                for src in self.webdav_sources
            ]
        }

    def _write_config_file(self, config_data: dict) -> None:
        """Atomically persist YAML to avoid partial writes."""
        config_dir = os.path.dirname(os.path.abspath(self.config_file)) or "."
        os.makedirs(config_dir, exist_ok=True)
        temp_file = f"{self.config_file}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, self.config_file)

    def save_config(self) -> bool:
        """Save current settings to YAML."""
        with self._lock:
            try:
                self.config_data = self._build_config_data()
                self._write_config_file(self.config_data)
                logger.info("Configuration saved successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to save config: {e}")
                return False

    def add_video_directory(self, directory: str) -> bool:
        """Add a video directory if it exists."""
        normalized_directory = os.path.normpath(directory)
        if not os.path.isdir(normalized_directory):
            logger.warning(f"Directory does not exist: {normalized_directory}")
            return False

        with self._lock:
            known_directories = {os.path.normpath(path) for path in self.video_directories}
            if normalized_directory not in known_directories:
                self.video_directories.append(normalized_directory)
                self.save_config()
                logger.info(f"Video directory added: {normalized_directory}")
            return True

    def remove_video_directory(self, directory: str) -> bool:
        """Remove a configured video directory."""
        normalized_directory = os.path.normpath(directory)
        with self._lock:
            for existing in list(self.video_directories):
                if os.path.normpath(existing) == normalized_directory:
                    self.video_directories.remove(existing)
                    self.save_config()
                    logger.info(f"Video directory removed: {existing}")
                    return True
            return False

    def add_webdav_source(self, name: str, url: str, username: str = "", password: str = "") -> bool:
        """Add a new WebDAV source."""
        url = url.rstrip("/")
        with self._lock:
            for src in self.webdav_sources:
                if src.url.rstrip("/") == url:
                    logger.warning(f"WebDAV source already exists: {url}")
                    return False
            self.webdav_sources.append(WebDAVSource(
                name=name or url,
                url=url,
                username=username,
                password=password,
            ))
            self.save_config()
            logger.info(f"WebDAV source added: {name} ({url})")
            return True

    def remove_webdav_source(self, index: int) -> bool:
        """Remove a WebDAV source by index."""
        with self._lock:
            if 0 <= index < len(self.webdav_sources):
                removed = self.webdav_sources.pop(index)
                self.save_config()
                logger.info(f"WebDAV source removed: {removed.name} ({removed.url})")
                return True
            return False

    def add_allowed_user(self, user_id: int) -> bool:
        """Grant access to a user."""
        with self._lock:
            if user_id not in self.allowed_user_ids:
                self.allowed_user_ids.append(user_id)
                self.save_config()
                logger.info(f"User {user_id} granted access")
                return True
            return False

    def remove_allowed_user(self, user_id: int) -> bool:
        """Revoke access from a user."""
        with self._lock:
            if user_id in self.allowed_user_ids:
                self.allowed_user_ids.remove(user_id)
                self.save_config()
                logger.info(f"User {user_id} access revoked")
                return True
            return False

    def is_user_allowed(self, user_id: int) -> bool:
        """Return whether the user is authorized."""
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids

    def is_admin(self, user_id: int) -> bool:
        """Return whether the user is an admin."""
        return user_id in self.admin_user_ids

    def add_admin_user(self, user_id: int) -> bool:
        """Promote a user to admin, also ensuring access."""
        with self._lock:
            if user_id not in self.admin_user_ids:
                self.admin_user_ids.append(user_id)
                if user_id not in self.allowed_user_ids:
                    self.allowed_user_ids.append(user_id)
                self.save_config()
                logger.info(f"User {user_id} promoted to admin")
                return True
            return False

    def remove_admin_user(self, user_id: int) -> bool:
        """Demote an admin user while preserving allowed-user state."""
        with self._lock:
            if user_id in self.admin_user_ids:
                self.admin_user_ids.remove(user_id)
                self.save_config()
                logger.info(f"User {user_id} demoted from admin")
                return True
            return False

    def reload(self) -> bool:
        """Reload the config from disk."""
        logger.info("Reloading configuration...")
        return self.load_config()

    def validate(self) -> List[str]:
        """Validate current configuration and return error messages."""
        errors: List[str] = []

        if not self.telegram_token or self.telegram_token == 'YOUR_TELEGRAM_BOT_TOKEN':
            errors.append("Telegram token not configured")

        if not os.path.isfile(self.vlc_path):
            errors.append(f"VLC path not valid: {self.vlc_path}")

        if not self.video_directories:
            errors.append("No video directories configured")
        else:
            for directory in self.video_directories:
                if not os.path.isdir(directory):
                    errors.append(f"Video directory does not exist: {directory}")

        if self.volume_step < 1 or self.volume_step > 100:
            errors.append(f"Invalid volume step: {self.volume_step} (must be 1-100)")

        if self.seek_step < 1 or self.seek_step > 300:
            errors.append(f"Invalid seek step: {self.seek_step} (must be 1-300)")

        if self.proxy_enabled:
            if self.proxy_type not in ('socks5', 'http'):
                errors.append(
                    f"Invalid proxy type: {self.proxy_type} (must be 'socks5' or 'http')"
                )
            if not self.proxy_host:
                errors.append("Proxy host is empty")
            if self.proxy_port < 1 or self.proxy_port > 65535:
                errors.append(f"Invalid proxy port: {self.proxy_port} (must be 1-65535)")

        return errors

    @staticmethod
    def _parse_webdav_sources(raw: any) -> List[WebDAVSource]:
        """Parse the ``webdav`` list from YAML into typed objects."""
        if not isinstance(raw, list):
            return []

        sources: List[WebDAVSource] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get('url', '')).rstrip('/')
            if not url:
                continue
            sources.append(WebDAVSource(
                name=str(item.get('name', '') or url),
                url=url,
                username=str(item.get('username', '')),
                password=str(item.get('password', '')),
            ))
        return sources

    def get_webdav_credentials(self, file_url: str) -> Optional[WebDAVSource]:
        """Return the WebDAV source whose URL is a prefix of *file_url*."""
        for src in self.webdav_sources:
            if file_url.startswith(src.url):
                return src
        return None


config = Config()
