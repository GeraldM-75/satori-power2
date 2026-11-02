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

# --- La correction pour l'erreur onScanCallback : bibliothèque Java de bleak
android.gradle_dependencies = com.github.hbldh:bleak:1.2.0

# --- Permissions : Bluetooth + localisation (obligatoire pour scanner le BLE)
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,BLETOOTH_SCAN,BLUTOOTH_CONNECT,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

# --- Versions Android : moderne, mais compatible capteurs BLE
android.api = 34
android.minapi = 26
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1 
