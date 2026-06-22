[app]
# 基础元数据
title = VideoDownloader
package.name = videodownloader
package.domain = org.rouvideo
source.dir = .
source.include_exts = py,png,jpg,json,ttf
version = 1.0

# 核心依赖（已精简，确保合包不卡死）
requirements = python3,kivy,requests,urllib3,certifi,charset_normalizer,idna,yt-dlp

# 屏幕设置
orientation = portrait
fullscreen = 0

# 安卓最高读写权限（支持网络、读写公共存储下载目录）
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, MANAGE_EXTERNAL_STORAGE

# 【终极对齐】将核心编译链与 API 完全咬合
android.api = 33
# 💡 核心修复：将 minapi 提升到 24 (Android 7.0+)，彻底解决高版本存储权限在 API 21 上引起的编译器崩溃
android.minapi = 24
android.ndk_api = 24

# 锁定最稳的 NDK 与架构
android.ndk = 25c
android.archs = arm64-v8a, armeabi-v7a

# 📢 【核心绝杀行】强行锁定 python-for-android 的稳定发行版，不让它拉取激进崩溃的 master 尝鲜分支
p4a.branch = release-2024.01.21

# 调试与构建模式限制
android.skip_byte_compile = 0
android.private_storage = 0

[buildozer]
log_level = 2
warn_on_root = 1
