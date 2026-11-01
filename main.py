# -*- coding: utf-8 -*-
"""
Satori Power — appli Android : puissance sur Tacx Satori depuis la vitesse.
Sources : main.py (ce fichier) + buildozer.spec (voir la doc de build).

Le capteur Sigma ANT+/BLE est lu via le profil CSC (service 0x1816).
Si le capteur n'est pas disponible, mode manuel : on tape la vitesse.
"""

import asyncio
import csv
import os
import struct
import threading
import time
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout

# ---- Courbes Tacx Satori : P = pente * v(km/h) + intercept (niveaux 1-10)
SATORI = {
    1: (3.73, -28.67), 2: (5.33, -36.67), 3: (6.87, -43.33),
    4: (8.27, -47.33), 5: (10.07, -66.33), 6: (11.40, -67.00),
    7: (13.13, -83.67), 8: (14.40, -82.00), 9: (15.93, -89.67),
    10: (17.73, -114.67),
}
CSC = "00001816-0000-1000-8000-00805f9b34fb"
CSC_MEAS = "00002a5b-0000-1000-8000-00805f9b34fb"

KV = """
BoxLayout:
    orientation: 'vertical'
    padding: dp(16)
    spacing: dp(8)

    Label:
        text: 'Tacx Satori — Puissance'
        font_size: sp(22)
        bold: True
        size_hint_y: None
        height: dp(32)

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        Label:
            text: 'Niveau :'
        Spinner:
            id: sp_level
            text: '4'
            values: [str(i) for i in range(1, 11)]
            on_text: app.set_level(self.text)
        Label:
            text: 'Roue (m) :'
        TextInput:
            id: ti_circ
            text: '2.096'
            input_filter: 'float'
            multiline: False

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        ToggleButton:
            id: tb_ble
            text: 'Capteur BLE'
            group: 'src'
            on_press: app.set_source('ble')
        ToggleButton:
            id: tb_man
            text: 'Manuel'
            group: 'src'
            state: 'down'
            on_press: app.set_source('manual')
        Button:
            id: btn_run
            text: 'Démarrer'
            on_press: app.toggle_run()
        Button:
            text: 'Stats'
            on_press: app.show_stats()

    Label:
        canvas.before:
            Color:
                rgba: 0.13, 0.16, 0.2, 1
            Rectangle:
                pos: self.pos
                size: self.size
        id: lb_power
        text: '0 W'
        font_size: sp(54)
        bold: True
        size_hint_y: None
        height: dp(110)

    Label:
        id: lb_speed
        text: '0.0 km/h'
        font_size: sp(20)

    Label:
        id: lb_avg
        text: 'moy 0 W · NP 0 W · max 0 W · 0 kJ'
        font_size: sp(15)

    Label:
        id: lb_info
        text: 'Prêt.'
        font_size: sp(13)
        color: 0.7, 0.75, 0.8, 1

    TextInput:
        id: ti_manual
        hint_text: 'Vitesse manuelle (km/h) puis Entrée'
        multiline: False
        on_text_validate: app.manual_speed(self.text); self.text = ''
"""


def power(level, v):
    s, i = SATORI[level]
    return max(0.0, s * v + i)


class BleCSC:
    """Connexion bleak au capteur CSC, dans son propre thread asyncio."""

    def __init__(self, circ, on_speed):
        self.circ = circ
        self.on_speed = on_speed
        self._stop = threading.Event()
        self.thread = None

    def start(self):
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        from bleak import BleakScanner, BleakClient  # import tardif (buildozer)
        state = {}
        while not self._stop.is_set():
            try:
                dev = None
                for d in await BleakScanner.discover(timeout=8.0):
                    if CSC in (d.metadata or {}).get("uuids", []):
                        dev = d
                        break
                    if d.name and any(k in (d.name or "").lower()
                                      for k in ("speed", "sigma", "sts")):
                        dev = d
                        break
                if dev is None:
                    self.on_speed(None, "capteur non trouvé, réessai…")
                    continue
                self.on_speed(None, f"connecté : {dev.name}")
                async with BleakClient(dev) as client:
                    def handle(_, data):
                        flags = data[0]
                        idx = 1
                        if flags & 0x02:      # cadence présente → sauter
                            idx += 4
                        if flags & 0x01:      # vitesse présente
                            ev = struct.unpack("<H", data[idx:idx+2])[0]
                            rev = struct.unpack("<I", data[idx+2:idx+6])[0]
                            if "rev" in state:
                                drev = (rev - state["rev"]) & 0xFFFFFFFF
                                dt = ((ev - state["ev"]) & 0xFFFF) / 1024.0
                                if drev and dt:
                                    v = drev / dt * self.circ * 3.6
                                    self.on_speed(v, None)
                            state.update(rev=rev, ev=ev)
                    await client.start_notify(CSC_MEAS, handle)
                    while not self._stop.is_set() and client.is_connected:
                        await asyncio.sleep(0.5)
            except Exception as e:          # noqa: BLE001
                self.on_speed(None, f"erreur BLE : {e}")
                await asyncio.sleep(2)
            state.clear()


class SatoriApp(App):
    level = NumericProperty(4)
    running = BooleanProperty(False)
    source = StringProperty("manual")

    def build(self):
        self.samples = []          # (t, v, w)
        self.t0 = None
        self.ble = None
        return Builder.load_string(KV)

    # ----- réglages
    def set_level(self, text):
        self.level = int(text)

    def set_source(self, src):
        self.source = src

    def circ(self):
        try:
            return float(self.root.ids.ti_circ.text.replace(",", ".")) or 2.096
        except ValueError:
            return 2.096

    # ----- session
    def toggle_run(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        self.samples = []
        self.t0 = time.time()
        self.running = True
        self.info("Séance démarrée.")
        if self.source == "ble":
            self.ble = BleCSC(self.circ(), self._on_speed)
            self.ble.start()

    def stop(self):
        self.running = False
        if self.ble:
            self.ble.stop()
            self.ble = None
        self.info("Séance arrêtée. " + self.stats_text())
        self.export_csv()

    def _on_speed(self, v, msg):
        # callback venant du thread BLE → repasser sur l'UI
        Clock.schedule_once(lambda *_: self._ui_speed(v, msg), 0)

    def _ui_speed(self, v, msg):
        if msg:
            self.info(msg)
            return
        if not self.running:
            return
        t = time.time() - self.t0
        w = power(self.level, v)
        self.samples.append((t, v, w))
        self.root.ids.lb_power.text = f"{w:.0f} W"
        self.root.ids.lb_speed.text = f"{v:.1f} km/h"
        self.root.ids.lb_avg.text = self.stats_text(short=True)

    def manual_speed(self, text):
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            return
        if self.running:
            self._ui_speed(v, None)

    # ----- stats / export
    def stats_text(self, short=False):
        if not self.samples:
            return "moy 0 W · NP 0 W · max 0 W · 0 kJ"
        watts = [w for _, _, w in self.samples if w > 0]
        if not watts:
            return "moy 0 W · NP 0 W · max 0 W · 0 kJ"
        avg = sum(watts) / len(watts)
        mx = max(watts)
        t = self.samples[-1][0]
        kJ = sum(w for _, _, w in self.samples) / 1000.0
        mov = []
        for tt, _, _ in self.samples:
            win = [x[2] for x in self.samples
                   if 0 <= tt - x[0] <= 30 and x[2] > 0]
            if win:
                mov.append(sum(win) / len(win))
        np_ = (sum(m**4 for m in mov) / len(mov)) ** 0.25 if mov else 0
        if short:
            return f"moy {avg:.0f} W · NP {np_:.0f} W · max {mx:.0f} W · {kJ:.0f} kJ"
        return (f"Durée {t:.0f}s · moyenne {avg:.0f} W · NP {np_:.0f} W · "
                f"max {mx:.0f} W · {kJ:.0f} kJ")

    def show_stats(self):
        self.info(self.stats_text())

    def export_csv(self):
        if not self.samples:
            return
        path = os.path.join(
            os.environ.get("ANDROID_APP_DATA", os.getcwd()),
            f"satori_{datetime.now():%Y%m%d_%H%M%S}.csv")
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["elapsed_s", "speed_kmh", "watts"])
                w.writerows(self.samples)
            self.info(f"Exporté : {path}")
        except OSError as e:
            self.info(f"Export impossible : {e}")

    def info(self, msg):
        self.root.ids.lb_info.text = msg


if __name__ == "__main__":
    SatoriApp().run()
