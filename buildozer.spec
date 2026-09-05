[app]
title = SOS 69069
package.name = sos69069
package.domain = org.sos69069
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.main = main.py
version = 0.9.1
requirements = python3,kivy,requests,urllib3,certifi,chardet,idna
orientation = portrait
fullscreen = 0
presplash.filename = %(source.dir)s/presplash.png
icon.filename = %(source.dir)s/icon.png
android.archs = arm64-v8a, armeabi-v7a
android.permissions = INTERNET
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
