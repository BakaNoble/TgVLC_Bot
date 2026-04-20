# 项目结构

```
TgVLC_Bot/
├── main.py                # 主程序入口、Telegram Bot 调度、Watchdog
├── config.py              # 配置管理模块（YAML 读写、校验）
├── vlc_player.py          # VLC 播放器控制（播放、监控、崩溃恢复）
├── file_browser.py        # 文件浏览模块（目录导航、分页、排序）
├── session.py             # 用户会话管理与播放历史持久化
├── logger.py              # 高级日志系统（JSON 行日志、归档、清理）
│
├── handlers/              # Telegram 回调处理器（按职责拆分）
│   ├── __init__.py        # 包导出
│   ├── base.py            # CallbackHandler 抽象基类
│   ├── callbacks.py       # 回调数据前缀定义与解析工具
│   ├── keyboards.py       # 所有 InlineKeyboard 布局构建
│   ├── navigation.py      # 主菜单、播放历史导航
│   ├── playback.py        # 播放控制回调
│   ├── file_browse.py     # 文件浏览与分页回调
│   ├── subtitle.py        # 字幕选择回调
│   └── settings.py        # 设置、目录管理、用户管理
│
├── tests/                 # 单元测试
│   ├── test_core.py       # 核心模块测试（57 项）
│   ├── test_concurrency.py
│   └── test_config_validation.py
│
├── docs/                  # 项目文档
│
├── config.yaml.example    # 配置模板（复制为 config.yaml 后使用）
├── requirements.txt       # Python 依赖
├── TgVLC_Bot.spec         # PyInstaller 打包配置（onedir 模式）
├── build.bat              # 一键打包脚本
├── setup.bat              # 环境检查与启动脚本
├── .gitignore
└── README.md
```

## 模块说明

### config.py
配置管理模块，负责从 config.yaml 读取和保存系统配置。

**主要功能：**
- 配置加载和保存（线程安全，原子写入）
- 视频目录管理
- 用户权限管理
- 代理配置
- 整数参数范围校验

### file_browser.py
文件浏览器模块，提供视频文件的浏览和导航功能。支持依赖注入配置实例和根目录边界覆盖。

**主要功能：**
- 目录浏览（可配置根目录边界）
- 分页显示
- 视频文件过滤
- 层级导航（单次遍历优化）

### vlc_player.py
VLC 播放器控制模块，管理 VLC 播放器的运行和控制。

**主要功能：**
- 播放器初始化与进程管理
- 播放/暂停/停止/快进快退
- 音量控制与静音
- 全屏切换（窗口句柄缓存）
- 字幕选择（内嵌轨道 API 验证，跳过文件扫描）
- 自适应轮询监控（播放中 1s / 空闲 5s）
- 崩溃检测与自动恢复
- 批量状态查询（单线程 4 合 1）

### session.py
用户会话管理模块。

**主要功能：**
- 每用户独立会话（线程安全）
- 播放历史持久化（JSON 文件）
- 配置实例依赖注入

### logger.py
高级日志管理系统。

**主要功能：**
- JSON 行格式日志（O(1) 追加写入）
- 每日自动归档
- 按时间/大小自动清理
- 有界 LRU logger 缓存

### main.py
Telegram 机器人主程序。

**主要功能：**
- 命令处理与状态机调度
- Watchdog 健康监控（指数退避重启）
- 优雅关闭（SIGINT/SIGTERM）
- ResilientHTTPXRequest 代理稳定性

### handlers/
按职责拆分的 Telegram 回调处理器包。

| 模块 | 职责 |
|------|------|
| `base.py` | 权限检查、消息安全发送、回调路由基类 |
| `keyboards.py` | 所有 InlineKeyboard 布局（统一宽度） |
| `navigation.py` | 主菜单、播放历史目录导航 |
| `playback.py` | 播放控制回调 |
| `file_browse.py` | 文件浏览、分页、目录切换 |
| `subtitle.py` | 字幕轨道选择 |
| `settings.py` | 设置、目录管理、用户管理 |

## 启动流程

1. 安装依赖：`pip install -r requirements.txt`
2. 复制配置模板：`cp config.yaml.example config.yaml`
3. 编辑 `config.yaml` 填入 Token、VLC 路径、视频目录
4. 运行程序：`python main.py` 或双击 `setup.bat`
