"""
TgVLC_Bot 并发测试

测试模块的线程安全性和并发访问能力。
"""
import os
import sys
import tempfile
import shutil
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestFileBrowserConcurrency(unittest.TestCase):
    """测试 FileBrowser 并发访问"""

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

        # 设置 config
        from config import Config
        self.test_config = Config(config_file=os.path.join(self.temp_dir, '_test_config.yaml'))
        self.test_config.video_directories = [self.temp_dir]
        self.test_config.video_extensions = ['.mp4', '.mkv', '.avi']
        self.test_config.page_size = 2

        from file_browser import FileBrowser
        self.browser = FileBrowser()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_concurrent_browse(self):
        """多个线程同时浏览目录"""
        errors = []
        results = []

        def browse_and_get_items():
            try:
                success, msg = self.browser.browse_directory(self.temp_dir)
                results.append(success)
                for _ in range(5):
                    self.browser.next_page()
                    items = self.browser.get_page_items()
                    self.browser.get_page_count()
                    self.browser.get_current_page()
                    self.browser.prev_page()
                return True
            except Exception as e:
                errors.append(e)
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(browse_and_get_items)
                for _ in range(5)
            ]
            results = [f.result() for f in as_completed(futures)]

        # 不应该有错误
        self.assertEqual(len(errors), 0, f"Errors during concurrent access: {errors}")
        # 所有结果应该都是 True
        self.assertTrue(all(results))

    def test_concurrent_page_navigation(self):
        """多个线程同时翻页"""
        self.browser.browse_directory(self.temp_dir)

        errors = []
        page_counts = []

        def navigate_pages():
            try:
                for _ in range(10):
                    self.browser.next_page()
                    page_counts.append(self.browser.get_current_page())
                    self.browser.prev_page()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=navigate_pages) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Errors during page navigation: {errors}")


class TestSessionConcurrency(unittest.TestCase):
    """测试 Session 的并发访问"""

    def setUp(self):
        """创建临时目录结构"""
        self.temp_dir = tempfile.mkdtemp()
        # 创建子目录
        os.makedirs(os.path.join(self.temp_dir, "subdir1"))
        # 创建视频文件
        for name in ["video_a.mp4", "video_b.mkv"]:
            path = os.path.join(self.temp_dir, name)
            with open(path, 'w') as f:
                f.write("x" * 100)

        # 设置 config
        from config import Config
        self.test_config = Config(config_file=os.path.join(self.temp_dir, '_test_config.yaml'))
        self.test_config.video_directories = [self.temp_dir]
        self.test_config.video_extensions = ['.mp4', '.mkv', '.avi']
        self.test_config.page_size = 2

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_session_manager_isolation(self):
        """不同用户的 session 应该相互隔离"""
        from session import SessionManager

        sm = SessionManager()

        # 用户 1 浏览目录
        session1 = sm.get_session(1)
        session1.browse_directory(self.temp_dir)
        page1_items = session1.get_page_items()
        count1 = len(page1_items)

        # 用户 2 浏览同一目录（session 应该不同）
        session2 = sm.get_session(2)
        session2.browse_directory(self.temp_dir)
        # 两个 session 应该有独立的页码状态
        # 这是一个基本测试，确保没有异常

        self.assertEqual(count1, len(session1.get_page_items()))

    def test_session_manager_concurrent_access(self):
        """SessionManager 应该能处理并发访问"""
        from session import SessionManager

        sm = SessionManager()
        errors = []

        def user_browse(user_id):
            try:
                session = sm.get_session(user_id)
                session.browse_directory(self.temp_dir)
                for _ in range(5):
                    session.next_page()
                    session.get_page_items()
                    session.get_all_video_files()
                    session.prev_page()
                return True
            except Exception as e:
                errors.append(e)
                return False

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(user_browse, i)
                for i in range(10)
            ]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        self.assertTrue(all(results))

    def test_session_clear(self):
        """清除 session 应该正常工作"""
        from session import SessionManager

        sm = SessionManager()
        session1 = sm.get_session(1)
        session1.browse_directory(self.temp_dir)

        # 清除后应该能创建新的 session
        sm.clear_session(1)
        session1_new = sm.get_session(1)

        # 新 session 应该有独立的状态
        self.assertEqual(len(session1_new.get_page_items()), 0)


    def test_play_history_persistence(self):
        """播放历史应在重建 SessionManager 后恢复"""
        from session import SessionManager

        history_file = os.path.join(self.temp_dir, 'play_history.json')
        sm = SessionManager(history_file=history_file)

        same_dir_file_1 = os.path.join(self.temp_dir, "video_a.mp4")
        same_dir_file_2 = os.path.join(self.temp_dir, "video_b.mkv")

        other_dir = os.path.join(self.temp_dir, "subdir1")
        other_file = os.path.join(other_dir, "video_c.mp4")
        with open(other_file, 'w') as f:
            f.write("x" * 100)

        sm.record_playback(1, same_dir_file_1)
        sm.record_playback(1, other_file)
        sm.record_playback(1, same_dir_file_2)

        sm_reloaded = SessionManager(history_file=history_file)
        history = sm_reloaded.get_play_history(1)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].directory, self.temp_dir)
        self.assertEqual(history[0].file_name, "video_b.mkv")
        self.assertEqual(history[1].directory, other_dir)
        self.assertEqual(history[1].file_name, "video_c.mp4")


class TestConfigConcurrency(unittest.TestCase):
    """测试 Config 的并发访问"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, 'test_config.yaml')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_concurrent_user_permission_check(self):
        """并发检查用户权限"""
        from config import Config

        config_data = {
            'telegram': {'token': 'test_token'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [1, 2, 3], 'admin_user_ids': [1]}
        }

        import yaml
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f)

        config = Config(config_file=self.config_file)
        errors = []

        def check_permission(user_id):
            try:
                for _ in range(100):
                    config.is_user_allowed(user_id)
                    config.is_admin(user_id)
                return True
            except Exception as e:
                errors.append(e)
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_permission, i % 5 + 1) for i in range(5)]
            results = [f.result() for f in as_completed(futures)]

        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        self.assertTrue(all(results))


if __name__ == '__main__':
    unittest.main()
