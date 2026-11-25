#!/bin/sh
# Repair the audio subsystem: the ADSP/SLPI firmware load fails during the
# early-boot remoteproc probe (the rootfs is not yet available), so the
# processors are started late and the audio driver chain is loaded AFTER
# the ADSP has fully settled.  The modules are blacklisted at boot and
# loaded only here, so no unload/reload cycle is ever needed.
set -u

REMOTEPROC_ADSP=/sys/class/remoteproc/remoteproc2/state
REMOTEPROC_SLPI=/sys/class/remoteproc/remoteproc1/state

# 1. Start the audio DSP.
if ! grep -q running "$REMOTEPROC_ADSP" 2>/dev/null; then
    echo start > "$REMOTEPROC_ADSP"
fi

# 2. Give the ADSP time to bring up its audio/SLIM services.
sleep 15

if ! grep -q running "$REMOTEPROC_SLPI" 2>/dev/null; then
    echo start > "$REMOTEPROC_SLPI"
fi
sleep 2

# 3. Load the audio driver chain: the SLIMbus controller first (its QMI
#    handshake runs against the now-ready ADSP), then the codec, then the
#    machine driver and the speaker amplifier.
modprobe slim_qcom_ngd_ctrl
sleep 5
modprobe snd_soc_wcd9335
sleep 4
modprobe soundwire_bus
modprobe snd_soc_qcom_common
modprobe snd_soc_msm8998
sleep 2
modprobe snd_soc_tfa989x
# Bind the speaker amplifier (tfa989x) to its I2C device if not bound
if [ ! -e /sys/bus/i2c/devices/3-0036/driver/bind ]; then
    echo 3-0036 > /sys/bus/i2c/drivers/tfa989x/bind 2>/dev/null || true
fi
sleep 3

# 4. Wait for the ALSA card, then restart the audio services.  PulseAudio's
#    ExecStartPre (dumpling-audio-setup) fails if the card is not present yet,
#    and systemd then gives up on the unit before this repair can recover it.
for i in $(seq 1 30); do
    grep -q "dumpling" /proc/asound/cards 2>/dev/null && break
    sleep 1
done
systemctl restart pulseaudio     2>/dev/null || true
sleep 2
systemctl start audiooutputd     2>/dev/null || true
sleep 2

# 5. Let audiod own the hardware sink (pcm_output).  Loading a competing
#    module-alsa-sink here occupies hw:0 and makes audiod's own sink fail,
#    leaving every output disconnected and master volume unsupported.
#    audiod may have started before the card existed, so restart it now.
systemctl restart audiod 2>/dev/null || true
sleep 3

# Select audiod's hardware sink.  Retain the old direct sink only as an
# emergency fallback if audiod could not create pcm_output.
sink=pcm_output
if ! pactl list short sinks 2>/dev/null | grep -q '[[:space:]]pcm_output[[:space:]]'; then
    pactl load-module module-alsa-sink device_id=0 2>/dev/null || true
    sink=alsa_output.0.stereo-fallback
fi
pactl set-default-sink "$sink" 2>/dev/null || true
pactl set-sink-volume "$sink" 50% 2>/dev/null || true
pactl set-sink-mute "$sink" 0 2>/dev/null || true

# audiod's policy module can restore pdefaultapp just after we set the
# default sink.  Re-apply once the routing callbacks have settled.
sleep 4
pactl set-default-sink "$sink" 2>/dev/null || true

echo "audio-repair: sound subsystem rebuilt"
