#!/bin/sh
sleep 10
/usr/bin/qmicli -pd qrtr://0 --dms-set-operating-mode=online >/dev/null 2>&1 || true
for m in /qrtrsoc_0 /dumpling; do
    dbus-send --system --dest=org.ofono --type=method_call "$m" \
        org.ofono.Modem.SetProperty string:Online variant:boolean:true >/dev/null 2>&1 || true
done
