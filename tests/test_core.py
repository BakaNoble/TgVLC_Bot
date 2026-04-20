"""
TgVLC_Bot 单元测试
覆盖 config、file_browser、vlc_player、logger 模块的核心逻辑
"""
import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestConfig(unittest.TestCase):
    """配置管理模块测试"""

    def setUp(self):
        """创建临时配置文件"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, 'test_config.yaml')

    def tearDown(self):
        """清理临时文件"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_config(self, config_data=None):
        """辅助方法：创建 Config 实例"""
        from config import Config
        if config_data:
            import yaml
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
        return Config(config_file=self.config_file)

    def test_default_config_created_when_file_missing(self):
        """配置文件不存在时应创建默认配置"""
        config = self._create_config()
        self.assertTrue(os.path.exists(self.config_file))
        self.assertEqual(config.volume_step, 10)
        self.assertEqual(config.seek_step, 30)
        self.assertEqual(config.page_size, 10)

    def test_deepcopy_prevents_mutation(self):
        """验证 DEFAULT_CONFIG 使用深拷贝，不会互相影响"""
        from config import Config
        config1 = self._create_config()
        # 默认 token 是 'YOUR_TELEGRAM_BOT_TOKEN'
        default_token = config1.telegram_token

        # 修改 config1 的 config_data 嵌套结构
        config1.config_data['telegram']['token'] = 'MUTATED_TOKEN'
        config1.telegram_token = 'MUTATED_TOKEN'

        # 创建新实例，使用不同的配置文件避免文件复用
        config_file2 = os.path.join(self.temp_dir, 'test_config2.yaml')
        config2 = Config(config_file=config_file2)

        # 新实例的默认值不应受 config1 对 DEFAULT_CONFIG 嵌套字典的影响
        self.assertEqual(config2.telegram_token, default_token)

    def test_load_valid_config(self):
        """加载有效配置"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1',
                      'port': 1080, 'username': '', 'password': ''},
            'vlc': {'path': r'C:\VLC\vlc.exe'},
            'video': {'directories': [r'D:\Videos'], 'extensions': ['.mp4', '.mkv']},
            'controls': {'volume_step': 20, 'seek_step': 60, 'page_size': 15},
            'security': {'allowed_user_ids': [123, 456], 'admin_user_ids': [123]}
        }
        config = self._create_config(config_data)
        self.assertEqual(config.telegram_token, '123456:ABC')
        self.assertEqual(config.volume_step, 20)
        self.assertEqual(config.seek_step, 60)
        self.assertEqual(config.page_size, 15)
        self.assertEqual(config.allowed_user_ids, [123, 456])
        self.assertTrue(config.is_admin(123))
        self.assertFalse(config.is_admin(456))

    def test_validate_int_clamping(self):
        """整数验证应正确限制范围"""
        from config import Config
        config = self._create_config()
        # 下限
        self.assertEqual(config._validate_int(0, 1, 100, 10), 1)
        # 上限
        self.assertEqual(config._validate_int(200, 1, 100, 10), 100)
        # 无效值返回默认
        self.assertEqual(config._validate_int("abc", 1, 100, 10), 10)
        self.assertEqual(config._validate_int(None, 1, 100, 10), 10)

    def test_user_permission_open_access(self):
        """空 allowed_user_ids 表示允许所有人"""
        config = self._create_config()
        # allowed_user_ids 为空时，任何人都有权限
        self.assertTrue(config.is_user_allowed(99999))
        self.assertTrue(config.is_user_allowed(1))

    def test_user_permission_restricted(self):
        """限制模式下只有授权用户可以访问"""
        config_data = {
            'telegram': {'token': 'test'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1',
                      'port': 1080, 'username': '', 'password': ''},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [100, 200], 'admin_user_ids': [100]}
        }
        config = self._create_config(config_data)
        self.assertTrue(config.is_user_allowed(100))
        self.assertTrue(config.is_user_allowed(200))
        self.assertFalse(config.is_user_allowed(300))

    def test_add_remove_video_directory(self):
        """测试添加和删除视频目录"""
        config = self._create_config()
        # 创建临时目录用于测试
        test_dir = os.path.join(self.temp_dir, "videos")
        os.makedirs(test_dir)

        self.assertTrue(config.add_video_directory(test_dir))
        self.assertIn(test_dir, config.video_directories)

        # 重复添加不应报错
        self.assertTrue(config.add_video_directory(test_dir))

        # 删除
        self.assertTrue(config.remove_video_directory(test_dir))
        self.assertNotIn(test_dir, config.video_directories)

    def test_add_remove_allowed_user(self):
        """测试添加和移除授权用户"""
        config = self._create_config()
        self.assertTrue(config.add_allowed_user(111))
        self.assertIn(111, config.allowed_user_ids)

        # 重复添加
        self.assertFalse(config.add_allowed_user(111))

        # 移除
        self.assertTrue(config.remove_allowed_user(111))
        self.assertNotIn(111, config.allowed_user_ids)

    def test_add_admin_also_adds_to_allowed(self):
        """添加管理员时应同时添加到授权用户列表"""
        config = self._create_config()
        config.add_admin_user(555)
        self.assertIn(555, config.admin_user_ids)
        self.assertIn(555, config.allowed_user_ids)

    def test_save_and_reload(self):
        """测试配置保存和重新加载"""
        config = self._create_config()
        config.telegram_token = "saved_token"
        config.volume_step = 50
        config.save_config()

        # 重新加载
        config2 = self._create_config()
        self.assertEqual(config2.telegram_token, "saved_token")
        self.assertEqual(config2.volume_step, 50)

    def test_validate_returns_errors(self):
        """验证配置完整性"""
        config = self._create_config()  # 默认配置，token 为空
        errors = config.validate()
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("Telegram token" in e for e in errors))


class TestFileBrowser(unittest.TestCase):
    """文件浏览模块测试"""

    def setUp(self):
        """创建临时目录结构"""
        self.temp_dir = tempfile.mkdtemp()
        # 创建子目录
        os.makedirs(os.path.join(self.temp_dir, "subdir1"))
        os.makedirs(os.path.join(self.temp_dir, "subdir2"))
        # 创建视频文件
        for name in ["video_a.mp4", "video_b.mkv", "video_c.avi"]:
            path = os.path.join(self.temp_dir, name)
            with open(path, 'w') as f:
                f.write("x" * 100)
        # 创建非视频文件
        with open(os.path.join(self.temp_dir, "readme.txt"), 'w') as f:
            f.write("not a video")

        # 必须在导入 file_browser 前设置 config 的 video_directories
        from config import Config
        self.test_config = Config(config_file=os.path.join(self.temp_dir, '_test_config.yaml'))
        self.test_config.video_directories = [self.temp_dir]
        self.test_config.video_extensions = ['.mp4', '.mkv', '.avi']
        self.test_config.page_size = 2  # 小页size方便测试分页

        from file_browser import FileBrowser
        self.browser = FileBrowser()
        self.browser.page_size = 2

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_browse_directory(self):
        """浏览目录应返回正确的文件和目录列表"""
        success, msg = self.browser.browse_directory(self.temp_dir)
        self.assertTrue(success)
        # 应有 2 个子目录 + 3 个视频文件 = 5 个项目
        self.assertEqual(len(self.browser.items), 5)
        # 目录应排在前面
        self.assertTrue(self.browser.items[0].is_directory)
        self.assertTrue(self.browser.items[1].is_directory)

    def test_pagination(self):
        """分页功能测试"""
        self.browser.browse_directory(self.temp_dir)
        self.assertEqual(self.browser.get_page_count(), 3)  # 5项, page_size=2

        # 第一页有2项
        page1 = self.browser.get_page_items()
        self.assertEqual(len(page1), 2)

        # 下一页
        success, _ = self.browser.next_page()
        self.assertTrue(success)
        page2 = self.browser.get_page_items()
        self.assertEqual(len(page2), 2)

        # 最后一页只有1项
        success, _ = self.browser.next_page()
        self.assertTrue(success)
        page3 = self.browser.get_page_items()
        self.assertEqual(len(page3), 1)

        # 已经是最后一页
        success, _ = self.browser.next_page()
        self.assertFalse(success)

    def test_video_file_operations(self):
        """视频文件操作测试"""
        self.browser.browse_directory(self.temp_dir)

        videos = self.browser.get_all_video_files()
        self.assertEqual(len(videos), 3)

        # 获取索引
        first_video = videos[0]
        idx = self.browser.get_video_file_index(first_video.path)
        self.assertEqual(idx, 0)

        # 下一集
        next_vid = self.browser.get_next_video(first_video.path)
        self.assertIsNotNone(next_vid)
        self.assertEqual(next_vid.path, videos[1].path)

        # 上一集（第一个视频无上一集）
        prev_vid = self.browser.get_previous_video(first_video.path)
        self.assertIsNone(prev_vid)

        # 最后一集无下一集
        last_vid = videos[-1]
        next_vid = self.browser.get_next_video(last_vid.path)
        self.assertIsNone(next_vid)

    def test_parent_directory_navigation(self):
        """上级目录导航测试"""
        # 必须修改全局 config 的 video_directories，因为 file_browser 使用全局单例
        import config as config_module
        original_dirs = config_module.config.video_directories
        config_module.config.video_directories = [self.temp_dir]

        try:
            self.browser.browse_directory(self.temp_dir)
            # 在配置的根目录下，不能向上导航
            self.assertTrue(self.browser.is_in_root_directory())
            self.assertIsNone(self.browser.get_parent_directory())

            # 进入子目录后可以向上导航
            subdir = os.path.join(self.temp_dir, "subdir1")
            self.browser.browse_directory(subdir)
            self.assertFalse(self.browser.is_in_root_directory())
            parent = self.browser.get_parent_directory()
            self.assertEqual(parent, self.temp_dir)
        finally:
            config_module.config.video_directories = original_dirs

    def test_browse_nonexistent_directory(self):
        """浏览不存在的目录应失败"""
        success, msg = self.browser.browse_directory("/nonexistent/path")
        self.assertFalse(success)

    def test_format_file_size(self):
        """文件大小格式化测试"""
        from file_browser import FileBrowser
        self.assertEqual(FileBrowser.format_file_size(500), "500 B")
        self.assertEqual(FileBrowser.format_file_size(1500), "1.5 KB")
        self.assertEqual(FileBrowser.format_file_size(1500000), "1.4 MB")
        self.assertEqual(FileBrowser.format_file_size(1500000000), "1.40 GB")
        self.assertEqual(FileBrowser.format_file_size(-1), "未知大小")

    def test_non_video_files_excluded(self):
        """非视频文件应被排除"""
        self.browser.browse_directory(self.temp_dir)
        video_files = self.browser.get_all_video_files()
        video_names = [v.name for v in video_files]
        self.assertNotIn("readme.txt", video_names)


class TestVLCPlayer(unittest.TestCase):
    """VLC 播放器模块测试（使用 Mock）"""

    def setUp(self):
        from vlc_player import VLCPlayer
        self.player = VLCPlayer()

    def test_format_time(self):
        """时间格式化测试"""
        self.assertEqual(self.player._format_time(0), "00:00")
        self.assertEqual(self.player._format_time(65000), "01:05")
        self.assertEqual(self.player._format_time(3661000), "01:01:01")
        self.assertEqual(self.player._format_time(-1), "00:00:00")

    def test_play_mode_cycle(self):
        """播放模式循环切换"""
        from vlc_player import PlayMode
        self.assertEqual(self.player.play_mode, PlayMode.SEQUENCE)

        success, msg = self.player.toggle_play_mode()
        self.assertEqual(self.player.play_mode, PlayMode.SINGLE)
        self.assertIn("单集播放", msg)

        success, msg = self.player.toggle_play_mode()
        self.assertEqual(self.player.play_mode, PlayMode.SINGLE_LOOP)
        self.assertIn("单集循环", msg)

        success, msg = self.player.toggle_play_mode()
        self.assertEqual(self.player.play_mode, PlayMode.SEQUENCE)
        self.assertIn("顺序播放", msg)

    def test_get_status_without_init(self):
        """未初始化时应返回提示"""
        status = self.player.get_status()
        self.assertEqual(status, "播放器未初始化")

    def test_play_without_file(self):
        """未加载文件时播放应失败"""
        self.player.player = MagicMock()
        self.player.current_file = None
        success, msg = self.player.play()
        self.assertFalse(success)

    def test_set_volume_range(self):
        """音量范围验证"""
        self.player.player = MagicMock()
        success, _ = self.player.set_volume(-1)
        self.assertFalse(success)
        success, _ = self.player.set_volume(50)
        self.assertTrue(success)
        success, _ = self.player.set_volume(101)
        self.assertFalse(success)

    def test_seek_range(self):
        """跳转范围验证"""
        self.player.player = MagicMock()
        success, _ = self.player.seek(-1)
        self.assertFalse(success)
        success, _ = self.player.seek(101)
        self.assertFalse(success)
        # 有效范围但 get_length 返回 0
        self.player.player.get_length.return_value = 0
        success, _ = self.player.seek(50)
        self.assertFalse(success)  # 无法获取媒体长度

    def test_state_lock_protection(self):
        """线程安全锁保护状态变量"""
        import threading

        results = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    status = self.player.get_status()
                    results.append(status)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    with self.player._state_lock:
                        self.player._is_playing = i % 2 == 0
                        self.player.current_file = f"test_{i}.mp4" if i % 2 == 0 else None
            except Exception as e:
                errors.append(e)

        # 并发读写不应产生异常
        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Thread safety errors: {errors}")

    def test_safe_vlc_call_timeout(self):
        """VLC API 超时保护"""
        import time

        def blocking_call():
            time.sleep(10)  # 模拟 VLC 卡死

        # 3 秒超时应返回 None
        result = self.player._safe_vlc_call(blocking_call, timeout=0.5)
        self.assertIsNone(result)

    def test_consecutive_error_tracking(self):
        """连续错误计数和健康检查"""
        self.player._consecutive_errors = 0
        self.player._max_consecutive_errors = 3

        # 模拟连续错误
        self.player._consecutive_errors = 2
        self.assertTrue(self.player._check_vlc_health())

        # 超过阈值应触发恢复（但不实际执行恢复，因为无 VLC 环境）
        self.player._consecutive_errors = 3
        # _try_recover_vlc 会因 player=None 而安全退出
        self.player.player = None
        self.player.instance = None
        result = self.player._check_vlc_health()
        # 恢复尝试后计数应被重置
        self.assertLessEqual(self.player._consecutive_errors, 1)

    def test_stop_clears_state_atomically(self):
        """stop() 应在锁内原子清除状态"""
        self.player.player = MagicMock()
        self.player.current_file = "test.mp4"
        self.player._is_playing = True

        success, msg = self.player.stop()
        self.assertTrue(success)
        self.assertIsNone(self.player.current_file)
        self.assertFalse(self.player._is_playing)


class TestLogger(unittest.TestCase):
    """日志模块测试"""

    def setUp(self):
        """创建临时日志目录"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        # 关闭日志 handler 以释放文件锁
        # 这里的 al 是各测试中创建的 AdvancedLogger 实例
        if hasattr(self, '_logger_instance'):
            for module_logger in self._logger_instance.loggers.values():
                for handler in module_logger.handlers[:]:
                    handler.close()
                    module_logger.removeHandler(handler)
            self._logger_instance.loggers.clear()

        # Windows 下需要重试删除（文件锁释放可能需要时间）
        for attempt in range(5):
            try:
                shutil.rmtree(self.temp_dir)
                break
            except PermissionError:
                import time
                time.sleep(0.2)

    def _create_logger(self):
        from logger import AdvancedLogger
        al = AdvancedLogger(log_dir=self.temp_dir)
        self._logger_instance = al
        return al

    def test_log_creates_entry(self):
        """记录日志应创建条目"""
        al = self._create_logger()
        entry = al.info("test_module", "test message")
        self.assertEqual(entry['level'], 'INFO')
        self.assertEqual(entry['module'], 'test_module')
        self.assertEqual(entry['message'], 'test message')

    def test_log_with_user_id(self):
        """带用户ID的日志"""
        al = self._create_logger()
        entry = al.log('WARNING', 'main', 'user action', user_id=12345)
        self.assertEqual(entry['user_id'], 12345)

    def test_get_logs_pagination(self):
        """日志分页查询"""
        al = self._create_logger()
        for i in range(25):
            al.info("test", f"message {i}")

        result = al.get_logs(page=1, limit=10)
        self.assertEqual(result['total'], 25)
        self.assertEqual(len(result['logs']), 10)
        self.assertEqual(result['totalPages'], 3)

    def test_get_logs_filter_by_level(self):
        """按级别过滤日志"""
        al = self._create_logger()
        al.info("test", "info msg")
        al.error("test", "error msg")
        al.warning("test", "warning msg")

        result = al.get_logs(level='ERROR')
        self.assertEqual(result['total'], 1)

    def test_get_logs_search(self):
        """搜索日志"""
        al = self._create_logger()
        al.info("test", "hello world")
        al.info("test", "foo bar")

        result = al.get_logs(search="hello")
        self.assertEqual(result['total'], 1)

    def test_get_stats(self):
        """日志统计"""
        al = self._create_logger()
        al.info("main", "msg1")
        al.error("vlc", "msg2", user_id=123)

        stats = al.get_stats()
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['levelCounts']['INFO'], 1)
        self.assertEqual(stats['levelCounts']['ERROR'], 1)
        self.assertEqual(stats['userOperations'], 1)
        self.assertEqual(stats['scriptOperations'], 1)

    def test_daily_archive(self):
        """每日归档"""
        al = self._create_logger()
        al.info("test", "archived message")

        # 强制触发归档（通过设置 last_archive_date 为昨天）
        from datetime import datetime, timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        al.last_archive_date = yesterday
        al._check_daily_archive()

        # 归档后 JSON 文件应被清空
        result = al.get_logs()
        self.assertEqual(result['total'], 0)

    def test_compact_logs(self):
        """日志压缩"""
        al = self._create_logger()
        # 写入超过 10000 条（模拟）
        for i in range(10050):
            al.info("test", f"message {i}")

        al._compact_logs()

        # 验证只剩 10000 条
        json_file = al.json_log_file
        with open(json_file, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        self.assertLessEqual(len(lines), 10000)

    def test_export_json(self):
        """JSON 导出"""
        al = self._create_logger()
        al.info("test", "export me")
        export_path = al.export_logs(format='json')
        self.assertTrue(os.path.exists(export_path))

        with open(export_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_export_csv(self):
        """CSV 导出"""
        al = self._create_logger()
        al.info("test", "export me")
        export_path = al.export_logs(format='csv')
        self.assertTrue(os.path.exists(export_path))

    def test_clear_logs(self):
        """清空日志"""
        al = self._create_logger()
        al.info("test", "to be cleared")
        al.clear_logs()

        result = al.get_logs()
        self.assertEqual(result['total'], 0)


class TestTextUtils(unittest.TestCase):
    """通用文本工具测试"""

    def test_windows_drive_letter_detection(self):
        """Windows 盘符检测逻辑（对应 handle_text_input 中的路径识别）"""
        valid_paths = ["C:\\Users", "D:\\Videos", "E:\\media", "F:\\", "Z:\\test"]
        invalid_paths = ["abc", "C", "1:\\test", ""]

        for path in valid_paths:
            if len(path) >= 2:
                self.assertTrue(
                    path[1] == ':' and path[0].upper() in 'CDEFGHIJKLMNOPQRSTUVWXYZ',
                    f"Should detect {path} as Windows path"
                )

        for path in invalid_paths:
            if len(path) >= 2:
                is_drive = path[1] == ':' and path[0].upper() in 'CDEFGHIJKLMNOPQRSTUVWXYZ'
                self.assertFalse(is_drive, f"Should NOT detect {path} as Windows path")


if __name__ == '__main__':
    unittest.main()
