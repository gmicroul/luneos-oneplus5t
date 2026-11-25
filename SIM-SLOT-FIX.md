# ofono 槽位 / SIM 识别修复（OnePlus 5 / 5T）

## 症状

5T 刷机后不识 SIM：`ofono` 只出现 `/ril_1`（槽2）且 `Present=false`，
槽1 的 modem 对象（`/ril_0`）完全不存在。

## 根因

基础快照（2026-10-30 取自一加5）里还是旧的 ofono 槽位配置组合：

- `/etc/ofono/binder.conf` = 未配置（只有注释样例，无 `[Settings]`）
- `/etc/ofono/ril_subscription.conf` = **启用**（指定 slot1/slot2 binder 传输）
- `/etc/ofono/binder.d/dual-sim.conf` = **启用**（`ExpectSlots+=slot2` 且
  把 slot2 重映射为 `/ril_1`）⇒ ofono 只创建槽2的 modem。

一加5 在 11/2 的调试中已修好（自定义 `binder.conf` + 两个旧配置改名
`.disabled`），但 **该修复未包含进 10/30 的快照**，因此 5T 镜像缺失。

## 修复（已内置 fastboot/fixes/）

- `etc/ofono/binder.conf` = 双卡版：
  `ExpectSlots = slot1,slot2`；`slot1 -> /ril_0`、`slot2 -> /ril_1`
- `etc/ofono/ril_subscription.conf` = **置空**（旧机制失效）
- `etc/ofono/binder.d/dual-sim.conf` = **置空**（旧的槽位重映射失效）
- 一加5 包由 `make-cheeseburger.sh` 自动改写为单卡版
  （`ExpectSlots = slot1`），与其上已实测稳定的状态一致。

## 验证

```sh
dbus-send --system --print-reply --dest=org.ofono / org.ofono.Manager.GetModems
# 期望（5T）：/ril_0 与 /ril_1 同时出现

dbus-send --system --print-reply --dest=org.ofono /ril_0 org.ofono.SimManager.GetProperties
# 期望：Present=true，MobileCountryCode/MobileNetworkCode 为运营商代码

dbus-send --system --print-reply --dest=org.ofono /ril_0 org.ofono.NetworkRegistration.GetProperties
# 期望：Status 从 searching -> registered
```

实测记录（5T，SIM 在槽1）：修复后 `/ril_0 Present=true`、
MCC=460 MNC=01（中国联通），状态经过 denied → searching → 正常注册。

## 附：全新 modem 的"首次配置"问题（重要经验）

在一台**从未被 Android 电话栈完整初始化过**的设备上（例：二手机首次插卡），
SFOS/ofono 单独可能无法完成注册——状态一直停在 `denied`，而同样的卡插到
已初始化过的机器（或刷一次 LineageOS 并打一通电话）后一切正常。

原因：modem 的部分持久配置（SIM 槽位激活、订阅等）由完整 Android
telephony 栈首次写入 modem NV；ofono 的 binder 插件只做常规 RIL 会话，
不替代该首次配置流程。

**处理办法**：全新设备刷 SFOS 前，先刷一次 LineageOS（或原厂系统），
插卡完成注册/拨打一次电话，再刷回 SFOS——此后注册即稳定。
本移植的两台设备（一加5/一加5T）均已如此处理。
