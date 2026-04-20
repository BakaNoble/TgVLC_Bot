# TgVLC_Bot 打包版使用说明

## 📦 文件夹结构

```
dist\TgVLC_Bot\
│
├── 📄 TgVLC_Bot.exe          # 主程序（双击运行）
├── � config.yaml            # 配置文件（需修改）
│
└── � _internal/             # 程序依赖（请勿修改）
    ├── 📄 python3.dll         # Python运行时
    └── 📦 ...                 # 其他依赖文件
```

## 🚀 快速开始

### 第一步：配置程序

1. 用文本编辑器打开 `TgVLC_Bot.exe` **同目录**下的 `config.yaml`
3. 修改以下配置：

```yaml
# Telegram Bot Token（必须）
telegram:
  token: "你的Bot_Token"

# VLC安装路径（必须）
vlc:
  path: "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe"

# 视频目录（根据需要修改）
video:
  directories:
    - "D:\\Movies"
    - "E:\\Videos"

# 管理员用户ID（可选）
security:
  admin_user_ids:
    - 你的Telegram用户ID
```

### 第二步：确保VLC已安装

确保目标电脑已安装 VLC Media Player，并记下安装路径。

### 第三步：运行程序

双击 `TgVLC_Bot.exe` 启动程序。

## ⚙️ 配置说明

### 必须配置

- **telegram.token**: 你的 Telegram Bot Token
- **vlc.path**: VLC 可执行文件路径

### 可选配置

- **video.directories**: 视频文件夹路径列表
- **security.admin_user_ids**: 管理员用户ID

### 代理配置（可选）

如果无法直接访问 Telegram：

```yaml
proxy:
  enabled: true
  type: "socks5"
  host: "127.0.0.1"
  port: 1080
```

## 📋 系统要求

- Windows 7/8/10/11
- VLC Media Player 已安装
- 网络连接（Telegram访问或代理）

## 🔧 常见问题

### 1. 提示 "VLC 初始化失败"
- 检查 config.yaml 中的 vlc.path 是否正确
- 确保 VLC 已正确安装

### 2. 提示 "无法连接 Telegram"
- 检查 telegram.token 是否正确
- 检查网络连接或配置代理

### 3. 配置文件无法保存
- 确保对 config.yaml 所在文件夹有写入权限

## 📞 获取帮助

如遇问题，请检查：
1. config.yaml 格式是否正确
2. 所有路径是否使用双反斜杠 \\
3. VLC 是否可以正常启动

---

**版本**: 1.0.0
**打包工具**: PyInstaller
