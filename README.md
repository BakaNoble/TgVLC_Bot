# VLC 远程控制系统

基于 Telegram 的 VLC 播放器远程控制系统，允许用户通过 Telegram 消息界面控制 Windows 主机上的 VLC 播放器。

## 功能特性

### 📂 文件浏览与选择

- 可配置的视频文件目录管理
- **WebDAV 远程文件系统支持（多源配置）**
- 交互式菜单系统
- 分页机制（每页10个项目，可配置）
- 文件类型过滤（支持 mp4, avi, mkv, mov 等格式）
- 多级目录导航
- **返回上级目录功能**
- **播放历史记录（自动保存/恢复）**

### 🎮 播放器控制

- 打开/切换视频文件
- 播放/暂停/停止
- 进度控制（跳转、前进/后退，步长可调）
- 音量控制（增减步长可调、静音）
- 全屏/窗口模式切换
- 实时状态显示
- 窗口激活（点击全屏时自动激活VLC窗口）
- 上一集/下一集快速切换
- **边界控制（第一集无法上一集，最后一集无法下一集）**
- **停止后自动返回文件列表或播放历史**
- **字幕选择功能（支持内嵌字幕和外部字幕）**
- **自动选择第一个字幕轨道**
- **三种播放模式：顺序播放、单集播放、单集循环**

### ⚙️ 系统集成

- 从指定目录启动 VLC
- 实例状态监控与崩溃自动恢复
- 用户授权管理
- 代理支持（SOCKS5/HTTP）
- 配置持久化
- **WebDAV 源的在线添加/删除管理**
- **播放历史持久化**

### 🔐 权限管理

- 普通用户：浏览和播放视频
- 管理员：额外管理功能（添加/删除目录、管理用户等）

## 系统要求

- Windows 操作系统（7/8/10/11）
- VLC Media Player
- Telegram Bot Token
- 网络连接

## 快速启动（源代码版本）

### 1. 安装依赖

```bash
pip install python-telegram-bot==20.7 PyYAML==6.0.1 python-vlc
```

### 2. 配置系统

复制模板并编辑：

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`，填入你的实际配置：

```yaml
telegram:
  token: "YOUR_TELEGRAM_BOT_TOKEN"

vlc:
  path: "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"

video:
  directories:
    - "D:\\Videos"
    - "D:\\Movies"

controls:
  volume_step: 10
  seek_step: 30
  page_size: 10

security:
  allowed_user_ids: []
  admin_user_ids: []

webdav:
  - name: "我的NAS"
    url: "http://192.168.1.100:5005/dav"
    username: "admin"
    password: "password"
```

### 3. 运行程序

```bash
python main.py
```

## 二进制版本

如需使用打包后的二进制版本，请下载 `dist/TgVLC_Bot.exe`。

## 项目结构

```
TgVLC_Bot/
├── main.py                # 主程序入口、Telegram Bot 调度、Watchdog
├── config.py              # 配置管理模块
├── vlc_player.py          # VLC 播放器控制模块
├── file_browser.py        # 文件浏览模块（本地 + WebDAV）
├── webdav_client.py       # WebDAV PROPFIND 客户端（stdlib 实现）
├── session.py             # 用户会话与播放历史
├── logger.py              # 日志管理系统
├── handlers/              # Telegram 回调处理器
│   ├── __init__.py
│   ├── base.py            # 处理器基类
│   ├── callbacks.py       # 回调数据解析
│   ├── keyboards.py       # 键盘布局构建
│   ├── navigation.py      # 主菜单与导航
│   ├── playback.py        # 播放控制
│   ├── file_browse.py     # 文件浏览
│   ├── subtitle.py        # 字幕选择
│   └── settings.py        # 设置管理
├── tests/                 # 单元测试
├── docs/                  # 项目文档
├── config.yaml.example    # 配置模板（需复制为 config.yaml）
├── requirements.txt        # Python 依赖
├── build.bat              # 打包脚本
├── setup.bat              # 环境检查与启动脚本
└── README.md
```

## 代码优化

本项目已进行全面的代码优化，包括：

- **模块化设计**：清晰的模块职责划分
- **类型注解**：完整的类型提示支持
- **错误处理**：健壮的异常捕获机制
- **日志记录**：完整的日志追踪
- **性能优化**：高效的文件扫描和缓存
- **可维护性**：统一的代码风格和注释

## 技术栈

- Python 3.8+
- python-telegram-bot 20.7
- python-vlc 3.0.18121
- PyYAML 6.0.1
- psutil（进程管理）
- PyInstaller（打包）

## 许可证

MIT License
