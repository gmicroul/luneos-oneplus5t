#!/usr/bin/env python3
import select
import struct
import subprocess
import time

TOUCH = '/dev/input/event1'
POWER = '/dev/input/event2'
BRIGHTNESS = '/sys/class/backlight/c994000.dsi.0/brightness'
FMT = 'llHHi'
SIZE = struct.calcsize(FMT)
BTN_TOUCH = 330
KEY_POWER = 116
DOUBLE_MS = 350
COOLDOWN = 3.0


def brightness():
    try:
        with open(BRIGHTNESS) as source:
            return int(source.read().strip())
    except (OSError, ValueError):
        return -1


def wake(reason):
    jobs = subprocess.run(['systemctl', 'list-jobs', '--no-legend'],
                          capture_output=True, text=True).stdout
    if any(name in jobs for name in ('shutdown.target', 'reboot.target', 'poweroff.target')):
        return
    subprocess.run(['systemctl', 'restart', 'luna-displaymanager'], check=False)
    for _ in range(20):
        if brightness() > 0:
            print('wake restored: ' + reason, flush=True)
            return
        time.sleep(0.25)
    print('wake failed: ' + reason, flush=True)


def watch_touch():
    last = 0.0
    last_wake = 0.0
    with open(TOUCH, 'rb') as stream:
        while True:
            ready, _, _ = select.select([stream], [], [], 1.0)
            if not ready:
                continue
            data = stream.read(SIZE)
            if len(data) != SIZE:
                continue
            _, _, etype, code, value = struct.unpack(FMT, data)
            if etype != 1 or code != BTN_TOUCH or value != 1:
                continue
            now = time.monotonic()
            if brightness() != 0 or now - last_wake < COOLDOWN:
                last = now
                continue
            if last and now - last <= DOUBLE_MS / 1000.0:
                last = 0.0
                last_wake = now
                wake('double tap')
            else:
                last = now


def watch_power():
    last_wake = 0.0
    with open(POWER, 'rb') as stream:
        while True:
            ready, _, _ = select.select([stream], [], [], 1.0)
            if not ready:
                continue
            data = stream.read(SIZE)
            if len(data) != SIZE:
                continue
            _, _, etype, code, value = struct.unpack(FMT, data)
            if etype != 1 or code != KEY_POWER or value != 1:
                continue
            now = time.monotonic()
            if now - last_wake < COOLDOWN:
                continue
            last_wake = now
            time.sleep(2.0)
            if brightness() == 0:
                wake('power key did not restore display')


if __name__ == '__main__':
    import threading

    threading.Thread(target=watch_power, daemon=True).start()
    watch_touch()
