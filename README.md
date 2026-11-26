# LuneOS OnePlus 5T — current fixes package

This repository contains a flashable LuneOS package for OnePlus 5T (`dumpling`) built from the verified `phase4-native-desktop-repack` baseline plus the current audio, telephony and status-bar fixes.

## Included fixes

- IPA module with WRR fix, QMI request-handler Oops fix and correct 0x23 filter-rule decoding (30 rules from modem, `rule_ids[64]`).
- q6asm/q6routing audio DSP fixes and the patched PulseAudio palm-policy module.
- Audio late-start repair script and LS2 audiooutput role/service files.
- ofono enabled with online restore drop-in after telephony starts.
- Status-bar SIM dedup by ICCID (only one signal badge for one physical SIM).
- Display wake watchdog: double-tap on the touchscreen or power key with a
  failed backlight restore restarts the display manager.

VoLTE/IMS registration is still not delivered; mobile data and IMS remains a known open issue. See `STATUS.md` for verified status and known limits.

## Files

- `boot.img` — boot image from the verified baseline.
- `userdata.sparse.img` — sparse userdata image with the rootfs and overlay.
- `manifest.json`, `SHA256SUMS` — hashes and overlay file list.
- `flash.py` — strict preflight and optional fastboot flash helper.
- `build-package.py`, `export-overlay.sh` — reproducible package scripts.
- `overlay/` — files installed into the rootfs.
- `VOLTE-CALL-AUDIO-FIX.md`, `SIM-SLOT-FIX.md` — background references from the OnePlus 5/5T SailfishOS port.

## Flash

Boot the device into fastboot, then:

```
python3 flash.py --payload-only
python3 flash.py --flash
```

`--payload-only` verifies the local payload without touching the device. `--flash` verifies device identity, partition sizes and all hashes before writing `userdata` and `boot`, then reboots. Keep a backup of your current images before flashing.

## Large image

`userdata.sparse.img` is in release `v0.1-current-fixes` as 17 assets (`userdata.sparse.img.part00` ... `part16`) because it exceeds GitHub's normal repository file-size limit. Use:

```
python3 download-release.py
python3 flash.py --payload-only
```

`parts.json` has the SHA256 of every part; `download-release.py` verifies each part before reassembling into `userdata.sparse.img` and prints the final SHA256. If downloads are slow, an optional `--proxy URL` can be passed to the downloader.
