# TgVLC_Bot 项目功能架构方案

## 一、项目概述

**项目名称**: TgVLC_Bot (Telegram VLC 远程控制系统)

**核心功能**: 基于 Telegram Bot 的 VLC 媒体播放器远程控制系统，通过 Telegram 消息界面远程控制 Windows 主机上的 VLC 播放器，实现视频文件的浏览、播放、控制和管理。

**技术栈**:
- Python 3.8+
- python-telegram-bot 20.7 (Telegram Bot API)
- python-vlc 3.0.18121 (VLC 播放器绑定)
- PyYAML 6.0.1 (配置文件解析)
- psutil (进程管理)
- PyInstaller (二进制打包)
- stdlib urllib + xml (WebDAV 客户端，零额外依赖)

---

## 二、系统架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                         TgVLC_Bot 系统                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │  Telegram   │───▶│   Main.py   │───▶│   Config    │          │
│  │   Bot API   │◀───│ (调度/Watchdog)│◀──│  (配置管理)  │          │
│  └─────────────┘    └──────┬──────┘    └─────────────┘          │
│                            │                                     │
│                    ┌───────┴───────┐                             │
│                    ▼               ▼                             │
│            ┌──────────────┐ ┌──────────────┐                    │
│            │  handlers/   │ │SessionManager│                    │
│            │ (回调处理器)  │ │ (会话/历史)   │                    │
│            └──────┬───────┘ └──────┬───────┘                    │
│                   │                │                             │
│      ┌────────────┼────────────────┼──────────┐                 │
│      ▼            ▼                ▼          ▼                 │
│ ┌──────────┐┌──────────┐  ┌──────────┐┌──────────┐             │
│ │FileBrowser││ VLCPlayer│  │  Logger  ││ Session  │             │
│ │(文件浏览) ││(播放器控制)│  │(日志管理) ││(用户会话) │             │
│ └──────────┘└─────┬────┘  └──────────┘└──────────┘             │
│                   ▼                                              │
│          ┌─────────────────┐                                    │
│          │   VLC Player    │                                    │
│          │   (外部进程)     │                                    │
│          └─────────────────┘                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详细设计

### 3.1 配置管理模块 (config.py)

**职责**: 集中管理系统所有配置参数

**配置项结构**:
```yaml
telegram:          # Telegram Bot 配置
  token: string    # Bot Token

proxy:             # 代理配置
  enabled: bool
  type: socks5|http
  host: string
  port: int
  username: string
  password: string

vlc:               # VLC 配置
  path: string     # VLC 可执行文件路径

video:             # 视频库配置
  directories: []  # 视频目录列表
  extensions: []   # 支持的视频扩展名

controls:          # 控制参数
  volume_step: int    # 音量调节步长 (1-100)
  seek_step: int      # 跳转步长秒数 (1-300)
  page_size: int      # 文件浏览每页数量 (5-50)

security:          # 安全配置
  allowed_user_ids: []  # 授权用户 ID 列表
  admin_user_ids: []    # 管理员用户 ID 列表
```

**核心类**: `Config`
- `load_config()` - 从 YAML 加载配置
- `save_config()` - 保存配置到 YAML
- `is_user_allowed(user_id)` - 检查用户权限
- `is_admin(user_id)` - 检查管理员权限
- `add_video_directory()` / `remove_video_directory()` - 管理视频目录
- `add_allowed_user()` / `remove_allowed_user()` - 管理授权用户
- `validate()` - 配置完整性校验

**特性**:
- 打包后从 exe 同目录读取配置（兼容 PyInstaller frozen 模式）
- 配置变更自动持久化
- 整数参数范围校验

---

### 3.2 文件浏览模块 (file_browser.py)

**职责**: 提供视频文件的浏览、导航和搜索功能

**核心类**: `FileBrowser`

**数据结构**:
```python
@dataclass(slots=True)
class FileItem:
    name: str           # 文件/目录名称
    path: str           # 完整路径（本地路径或 WebDAV URL）
    is_directory: bool # 是否为目录
    size: int           # 文件大小(字节)
```

**支持的数据源**:
- 本地文件系统
- WebDAV 远程服务器（通过 webdav_client.py）

**核心方法**:

| 方法 | 功能 |
|------|------|
| `browse_directory(dir)` | 浏览本地目录或 WebDAV URL，加载文件列表 |
| `_browse_webdav_directory(url)` | 通过 PROPFIND 浏览 WebDAV 目录 |
| `get_page_items()` | 获取当前页项目 |
| `next_page()` / `prev_page()` | 翻页控制 |
| `get_all_video_files()` | 获取当前目录所有视频 |
| `get_next_video(path)` | 获取下一个视频（循环） |
| `get_previous_video(path)` | 获取上一个视频（循环） |
| `navigate_to_parent()` | 导航到上级目录 |
| `is_in_root_directory()` | 检查是否在根目录 |
| `get_display_list()` | 生成格式化显示文本 |

**特性**:
- 文件类型过滤（通过扩展名匹配）
- 分页显示（可配置每页数量）
- 目录优先排序
- 文件大小格式化显示（KB/MB/GB）
- WebDAV 认证信息自动注入（从 config 获取）

---

### 3.3 VLC 播放器控制模块 (vlc_player.py)

**职责**: 控制 VLC 播放器的所有操作

**核心类**: `VLCPlayer`

**播放模式枚举**:
```python
class PlayMode(Enum):
    SEQUENCE = "sequence"       # 顺序播放：播完列表中所有视频
    SINGLE = "single"          # 单集播放：仅播放当前视频
    SINGLE_LOOP = "single_loop" # 单集循环：循环播放当前视频
```

**核心方法**:

| 方法 | 功能 |
|------|------|
| `initialize()` | 初始化 VLC 实例和媒体播放器 |
| `open_file(path, video_list, index)` | 打开视频文件 |
| `play()` / `pause()` / `stop()` | 播放控制 |
| `seek_forward(seconds)` / `seek_backward(seconds)` | 快进/快退 |
| `volume_up()` / `volume_down()` | 音量调节 |
| `toggle_mute()` | 静音切换 |
| `toggle_fullscreen()` | 全屏切换 |
| `get_subtitle_tracks()` | 获取字幕轨道列表 |
| `set_subtitle_track(track_id)` | 设置字幕轨道 |
| `toggle_play_mode()` | 切换播放模式 |
| `get_status()` | 获取播放状态文本 |

**播放状态监控线程**:
- 独立监控线程 `_playback_monitor_loop()`
- 自适应轮询：播放中 1s / 空闲 5s
- 检测播放卡顿（位置停滞超过10秒）
- VLC 进程存活检测（最小 10s 间隔）
- 可中断睡眠机制（`_interruptible_sleep`）

**崩溃恢复机制**:
```
检测到 VLC 无响应 → 尝试恢复（最多3次）
  → 停止监控
  → 释放旧资源
  → 重新初始化 VLC
  → 恢复之前的播放状态
```

**字幕处理**:
- 自动选择第一个字幕轨道（内嵌字幕优先）
- 支持切换任意字幕轨道
- 支持 SRT/ASS/SSA 等外部字幕文件（需与视频同名）

---

### 3.4 主程序模块 (main.py)

**职责**: Telegram Bot 核心逻辑，用户交互处理

**状态机设计**:
```
STATE_SELECTING_ACTION   - 主菜单状态
STATE_BROWSING_FILES     - 浏览文件状态
STATE_SELECTING_FILE     - 选择文件状态
STATE_SETTINGS_MENU     - 设置菜单状态
STATE_ADDING_DIRECTORY   - 添加目录状态（等待输入路径）
STATE_WAITING_VOLUME_STEP - 等待音量步长输入
STATE_WAITING_SEEK_STEP  - 等待跳转步长输入
```

**命令处理器**:

| 命令 | 处理函数 | 功能 |
|------|---------|------|
| `/start` | `start_command` | 启动机器人，显示主菜单 |
| `/help` | `help_command` | 显示帮助信息 |
| `/status` | `status_command` | 查看当前播放状态 |
| `/playmode` | `playmode_command` | 切换播放模式 |

**按钮回调处理**:

| callback_data | 功能 |
|---------------|------|
| `browse` | 进入文件浏览 |
| `playback` | 显示播放控制菜单 |
| `status` | 显示当前状态 |
| `settings` | 显示设置菜单 |
| `play_pause` | 播放/暂停切换 |
| `seek_forward` / `seek_backward` | 快进/快退 |
| `volume_up` / `volume_down` | 音量调节 |
| `mute` | 静音切换 |
| `fullscreen` | 全屏切换 |
| `prev_episode` / `next_episode` | 上一集/下一集 |
| `toggle_playmode` | 切换播放模式 |
| `subtitle_menu` | 字幕选择菜单 |
| `stop_to_list` | 停止并返回列表 |
| `prev_page` / `next_page` | 文件列表翻页 |
| `parent_directory` | 返回上级目录 |
| `file_N` | 选择第 N 个文件播放 |

**错误处理**:
- 网络/代理错误：python-telegram-bot 内部自动重试（指数退避）
- 消息未变化错误：忽略（防止快速重复操作报错）
- 其他错误：记录日志

**优雅关闭**:
- 捕获 SIGINT/SIGTERM 信号
- 停止 VLC 播放器
- 关闭 Telegram 应用
- 清理资源后退出

**自定义轮询机制**:
```
启动轮询 → 异常退出 → 指数退避延迟(1s→2s→4s→...→30s) → 重连
```

---

### 3.5 日志管理模块 (logger.py)

**职责**: 完整的日志记录、归档和管理功能

**核心类**: `AdvancedLogger`

**日志文件**:
- `logs/bot_logs.json` - 当前日志（行格式 JSON）
- `logs/archive/logs_YYYYMMDD.json` - 每日归档日志

**日志格式**:
```json
{
  "timestamp": "2026-04-11T10:30:00.123456",
  "level": "INFO",
  "module": "main",
  "message": "User 88029460 started bot",
  "user_id": 88029460,
  "chat_id": 123456789,
  "details": null
}
```

**核心方法**:

| 方法 | 功能 |
|------|------|
| `log(level, module, message)` | 记录日志到文件和 JSON |
| `get_logs(filters)` | 分页查询日志 |
| `get_stats()` | 获取日志统计 |
| `get_archived_logs(date)` | 查询归档日志 |
| `export_logs(format)` | 导出日志（JSON/CSV） |
| `clear_logs()` | 清空日志 |
| `_compact_logs()` | 当日志超过10000条时压缩 |

**自动清理策略**:
- 按时间：默认保留30天
- 按大小：默认最大500MB
- 按行数：当前日志超过10000条时压缩保留最新10000条

---

## 四、功能流程图

### 4.1 用户启动流程
```
用户发送 /start
    │
    ▼
验证用户权限 (is_user_allowed)
    │
    ├─ 无权限 ──▶ 显示"无权限"消息
    │
    └─ 有权限 ──▶ 显示主菜单键盘
                      │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
[浏览视频]         [播放控制]         [当前状态]
    │                  │                  │
    ▼                  ▼                  ▼
选择目录 ──────── 显示播放控制 ──── 显示播放状态
    │                  │
    ▼                  ▼
浏览文件列表      ├─ 播放/暂停
    │              ├─ 快进/快退
选择视频文件 ────▶播放视频
    │                  │
    ▼            ┌─────┴─────┐
返回播放控制 ◀───┤           │
                ▼           ▼
            字幕选择    上一集/下一集
```

### 4.2 播放控制流程
```
用户点击播放控制按钮
    │
    ▼
调用 vlc_player 对应方法
    │
    ├── play() / pause()
    ├── seek_forward() / seek_backward()
    ├── volume_up() / volume_down()
    ├── toggle_mute()
    ├── toggle_fullscreen()
    ├── set_subtitle_track()
    └── toggle_play_mode()
    │
    ▼
返回操作结果
    │
    ▼
更新 Telegram 消息界面
```

### 4.3 文件浏览流程
```
用户点击"浏览视频"
    │
    ▼
显示目录列表键盘
    │
    ▼
用户选择目录 / dir_N
    │
    ▼
调用 file_browser.browse_directory()
    │
    ▼
加载目录文件列表
（目录优先，文件按名称排序）
    │
    ▼
分页显示文件列表 + 导航按钮
    │
    ├── 用户选择 file_N ──▶ open_file() 播放
    ├── 用户选择 dir_N ──▶ browse_directory() 进入子目录
    ├── prev_page ──▶ 上一页
    ├── next_page ──▶ 下一页
    └── parent_directory ──▶ 返回上级
```

---

## 五、用户界面结构

### 5.1 主菜单
```
🎬 VLC 远程控制系统

请选择操作：

[📂 浏览视频]
[▶️ 播放控制]
[📊 当前状态]
[⚙️ 设置]
```

### 5.2 播放控制菜单
```
🎮 播放控制：

[⬅️ 上一集] [下一集 ➡️]  （仅多个视频时显示）

[⏯️ 播放/暂停]
[⏪ 后退] [前进 ⏩]
[🔊 增大音量] [减小音量 🔉]
[🔇 静音] [全屏 🖥️]
[📝 字幕选择]
[⏹️ 停止并返回列表]
[◀️ 返回主菜单]
```

### 5.3 文件浏览界面
```
📂 F:\115open\影视库
📋 第 1/3 页
──────────────────

1. 📁 子文件夹
2. 🎬 视频文件1.mp4 (1.2 GB)
3. 🎬 视频文件2.mkv (800 MB)

──────────────────

[◀️ 上一页] [下一页 ▶️]
[⬆️ 返回上级目录]
[📋 目录列表]
[◀️ 返回主菜单]
```

---

## 六、安全机制

### 6.1 用户权限控制
```python
# 普通用户权限
- 浏览视频目录
- 播放/暂停控制
- 音量/进度控制
- 查看状态

# 管理员额外权限
- 添加/删除视频目录
- 管理授权用户
```

### 6.2 配置校验
```python
validate() 检查:
├── Telegram Token 已配置
├── VLC 路径有效
├── 至少配置一个视频目录
├── volume_step 在 1-100 范围
└── seek_step 在 1-300 范围
```

---

## 七、配置持久化

**配置文件位置**:
- 源码运行: `config.yaml` (与 `main.py` 同目录)
- PyInstaller 打包: `TgVLC_Bot.exe` 同目录下的 `config.yaml`

**自动保存时机**:
- 添加/删除视频目录后
- 添加/删除授权用户后
- 管理员修改设置后

---

## 八、数据流总结

```
Telegram 用户
     │
     ▼ 消息/按钮
┌─────────────────┐
│   Telegram Bot  │
│   (main.py)     │
└────────┬────────┘
         │
         ▼ 命令/查询
┌─────────────────────────────────────────┐
│              业务逻辑层                   │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │ FileBrowser│ │ VLCPlayer│ │ Config  │  │
│  └────┬─────┘ └────┬─────┘ └────┬────┘  │
└───────┼───────────┼───────────┼────────┘
        │           │           │
        ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ 文件系统  │ │ VLC 进程  │ │ YAML 配置 │
│           │ │ (远程控制) │ │           │
└──────────┘ └──────────┘ └──────────┘
```

---

## 九、项目文件结构

```
TgVLC_Bot/
├── main.py                # 主程序入口、Telegram Bot 调度、Watchdog
├── config.py              # 配置管理模块
├── vlc_player.py          # VLC 播放器控制
├── file_browser.py        # 文件浏览模块（本地 + WebDAV）
├── webdav_client.py       # WebDAV PROPFIND 客户端（stdlib 实现）
├── session.py             # 用户会话管理与播放历史
├── logger.py              # 高级日志系统
├── handlers/              # Telegram 回调处理器
│   ├── __init__.py
│   ├── base.py            # CallbackHandler 抽象基类
│   ├── callbacks.py       # 回调数据前缀定义与解析工具
│   ├── keyboards.py       # 所有 InlineKeyboard 布局构建
│   ├── navigation.py      # 主菜单、播放历史导航
│   ├── playback.py        # 播放控制回调
│   ├── file_browse.py     # 文件浏览与分页回调
│   ├── subtitle.py        # 字幕选择回调
│   └── settings.py        # 设置、目录管理、用户管理
├── tests/                 # 单元测试
│   ├── test_core.py
│   ├── test_concurrency.py
│   └── test_config_validation.py
├── docs/                  # 项目文档
├── config.yaml.example    # 配置模板
├── requirements.txt       # Python 依赖
├── TgVLC_Bot.spec         # PyInstaller 打包配置（onedir 模式）
├── build.bat              # 一键打包脚本
├── setup.bat              # 环境检查与启动脚本
└── README.md
```

---

## 十、关键技术特性

| 特性 | 实现方式 |
|------|---------|
| 状态管理 | `ConversationHandler` 状态机 |
| 并发控制 | `threading.Lock` 保护共享状态 |
| 超时保护 | 辅助线程 + `join(timeout)` |
| 崩溃恢复 | 监控线程检测 + 最多3次重试 |
| 日志轮转 | `RotatingFileHandler` (10MB/文件) |
| 代理支持 | SOCKS5 / HTTP 代理 |
| 窗口控制 | `ctypes.windll.user32` Win32 API |
| 配置热更新 | 自动重新加载 `config.yaml` |

---

## 十一、版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0.0 | 2026-03 | 基础功能：文件浏览、播放控制 |
| v1.1.0 | 2026-03-30 | 新增字幕选择、上一集/下一集、循环播放 |
| v1.2.0 | 2026-04 | 增强崩溃恢复、日志管理优化 |
| v1.3.0 | 2026-04 | handlers 模块拆分、会话管理、性能优化、Watchdog 退避 |
