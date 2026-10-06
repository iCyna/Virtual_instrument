[app]

# (str) Title of your application
title = virtual_instrument

# (str) Package name
package.name = test_mobile

# (str) Package domain (needed for android/ios packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (Thêm đuôi so để nhận un4seen và mid/midi nếu cần)
source.include_exts = py,png,jpg,kv,atlas,ttf,so,mid,midi

# (list) List of directory to exclude
source.exclude_dirs = tests, bin, venv, vsSpace, dist, sf3, instrument-virtual.zip, build, bin, __pycache__, .github, .git, pyaudiogaming/lib

# (str) Application versioning
version = 0.1

# (list) Application requirements (Đã dọn sạch đồ Windows, thêm numpy, mido)
#requirements = python3, pygame, plyer, requests, urllib3, openssl, cffi, cryptography, mido
requirements = python3, pygame-ce, plyer, requests, urllib3, openssl, cffi, mido

# (list) Supported orientations
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

android.api = 33
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24
android.build_tools_version = 33.0.2
# (list) The Android archs to build for
android.archs = arm64-v8a

# (bool) enables Android auto backup feature
android.allow_backup = True

# (str) The format used to package the app for debug mode
android.debug_artifact = apk

# --- PHẦN QUAN TRỌNG CHO UN4SEEN (Thư viện .so) ---
# Bạn hãy chắc chắn đường dẫn này khớp với thư mục thực tế trong máy bạn:
android.add_libs_arm64_v8a = pyaudiogaming/lib/arm64-v8a/*.so

android.accept_sdk_license = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug)
log_level = 2

# (int) Display warning if buildozer is run as root
warn_on_root = 1