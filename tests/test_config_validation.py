"""
TgVLC_Bot 配置验证测试

测试增强的配置验证和类型处理功能。
"""
import os
import sys
import tempfile
import shutil
import unittest

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestConfigTypeValidation(unittest.TestCase):
    """测试配置类型验证"""

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

    def test_user_ids_string_conversion(self):
        """字符串形式的用户 ID 应该被正确转换"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': ['123', '456'], 'admin_user_ids': ['123']}
        }
        config = self._create_config(config_data)
        self.assertEqual(config.allowed_user_ids, [123, 456])
        self.assertEqual(config.admin_user_ids, [123])

    def test_user_ids_mixed_types(self):
        """混合类型的用户 ID 应该被正确处理"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [100, '200', 300], 'admin_user_ids': [100]}
        }
        config = self._create_config(config_data)
        self.assertEqual(config.allowed_user_ids, [100, 200, 300])

    def test_invalid_user_ids_filtered(self):
        """无效的用户 ID 应该被过滤"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [100, 'invalid', None, 200], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        # 无效值应该被过滤掉
        self.assertEqual(config.allowed_user_ids, [100, 200])

    def test_proxy_port_range_validation(self):
        """代理端口应该被限制在有效范围内"""
        # 端口超出范围
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': True, 'type': 'socks5', 'host': '127.0.0.1', 'port': 70000},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        # 端口应该被限制在 65535
        self.assertLessEqual(config.proxy_port, 65535)

        # 端口为负数
        config_data['proxy']['port'] = -1
        config = self._create_config(config_data)
        # 端口应该被限制在 1
        self.assertGreaterEqual(config.proxy_port, 1)

    def test_proxy_type_validation(self):
        """无效的代理类型应该使用默认值"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': True, 'type': 'invalid_proxy', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        # 无效类型应该被保存（作为字符串），验证时会被检测
        self.assertEqual(config.proxy_type, 'invalid_proxy')

    def test_video_directories_type_validation(self):
        """视频目录列表类型应该被验证"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': 'not_a_list', 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        # 非列表应该被转换为空列表
        self.assertEqual(config.video_directories, [])

    def test_validate_detects_invalid_directories(self):
        """validate() 应该检测不存在的目录"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [r'D:\nonexistent_directory_12345'], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        errors = config.validate()
        self.assertTrue(any('does not exist' in e for e in errors))

    def test_validate_detects_invalid_proxy(self):
        """validate() 应该检测无效的代理配置"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': True, 'type': 'invalid', 'host': '', 'port': 99999},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [], 'admin_user_ids': []}
        }
        config = self._create_config(config_data)
        errors = config.validate()
        self.assertTrue(any('proxy' in e.lower() for e in errors))


class TestConfigAdminDemotion(unittest.TestCase):
    """测试管理员降权功能"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, 'test_config.yaml')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _create_config(self, config_data=None):
        from config import Config
        if config_data:
            import yaml
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config_data, f, allow_unicode=True, sort_keys=False)
        return Config(config_file=self.config_file)

    def test_remove_admin_keeps_in_allowed(self):
        """移除管理员应该保留用户在 allowed_user_ids 中"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [999], 'admin_user_ids': [999]}
        }
        config = self._create_config(config_data)
        self.assertIn(999, config.admin_user_ids)
        self.assertIn(999, config.allowed_user_ids)

        config.remove_admin_user(999)

        self.assertNotIn(999, config.admin_user_ids)
        # 降权后应该仍在 allowed_user_ids 中
        self.assertIn(999, config.allowed_user_ids)

    def test_admin_demotion_persists(self):
        """管理员降权应该持久化"""
        config_data = {
            'telegram': {'token': '123456:ABC'},
            'proxy': {'enabled': False, 'type': 'socks5', 'host': '127.0.0.1', 'port': 1080},
            'vlc': {'path': ''},
            'video': {'directories': [], 'extensions': ['.mp4']},
            'controls': {'volume_step': 10, 'seek_step': 30, 'page_size': 10},
            'security': {'allowed_user_ids': [888], 'admin_user_ids': [888]}
        }
        config = self._create_config(config_data)
        config.remove_admin_user(888)
        config.save_config()

        # 重新加载
        config2 = self._create_config()
        self.assertNotIn(888, config2.admin_user_ids)
        self.assertIn(888, config2.allowed_user_ids)


if __name__ == '__main__':
    unittest.main()
