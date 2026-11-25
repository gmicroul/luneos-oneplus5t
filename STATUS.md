# Verified status

- Device: OnePlus 5T (`dumpling`), LuneOS mainline kernel 6.1.192.
- Audio: speaker and volume keys working; PulseAudio hardware sink `pcm_output`.
- Status bar: one signal badge after SIM dedup by ICCID.
- Telephony: ofono enabled, modem online restored after boot, LTE registered and PS attached.
- Mobile data: not delivered. IPA UL still misses routing (`rt_rule_id=1023`); writing AP SRAM/IMEM tables or issuing UC MEMCPY causes device hangs. Do not retry those paths.
- VoLTE/IMS: not registered; Voice service unavailable. IMS PDN can be established but IPA assert occurs on IMSA/P-CSCF path. No safe software-only fix is known from this work.

This package preserves the verified fixes; it does not claim VoLTE is complete.
