[app]
title = Satori Power
package.name = satoripower
package.domain = org.satori
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 0.1
requirements = python3,kivy,bleak,pyjnius
orientation = portrait
fullscreen = 0

# Classes Java de bleak : fournies via android.add_src (pas de Maven !)
android.add_src = java

# Permissions : Bluetooth + localisation (toutes correctement orthographiées)
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_SCAN,BLUETOOTH_CONNECT,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.api = 34
android.minapi = 26
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
