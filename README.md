# LuneOS OnePlus 5T — current fixes package

This repository contains a flashable LuneOS package for OnePlus 5T (`dumpling`) built from the verified `phase4-native-desktop-repack` baseline plus the current audio, telephony and status-bar fixes.

## Included fixes

- IPA module with WRR fix, QMI request-handler Oops fix and correct 0x23 filter-rule decoding (30 rules from modem, `rule_ids[64]`).
- q6asm/q6routing audio DSP fixes and the patched PulseAudio palm-policy module.
- Audio late-start repair script and LS2 audiooutput role/service files.
- ofono enabled with online restore drop-in after telephony starts.
- Status-bar SIM dedup by ICCID (only one signal badge for one physical SIM).

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

The large sparse image may be distributed as a release asset instead of a Git object if repository file-size limits apply; `manifest.json` and `SHA256SUMS` are authoritative for its hashes.
