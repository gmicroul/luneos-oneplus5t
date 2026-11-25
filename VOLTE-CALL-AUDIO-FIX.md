# VoLTE 通话音频修复记录（OnePlus 5 / 5T，SFOS 5.3.0.10）

状态：**已修复并在真机验证**（2026-11-05：一加5 实拨 10010 双向有声；
两条刷机包均已内置本修复）。LineageOS 20 对照实验证明硬件与
modem/IMS 链路正常，问题全在 SFOS 音频软件栈。

## 1. 症状

- 电话能正常接通（VoLTE/IMS 注册、振铃、挂断都正常），但通话双方完全无声。
- 同一台机器刷 LineageOS 20，通话音频完全正常。
- 媒体播放、设置里的铃声、DTMF 按键音（下行）本身正常。

## 2. 根因（三层，互相叠加）

### 2.1 语音会话参数从未发出的“官方 NOP”

SFOS 原配的旧 Jolla 模块 `module-droid-card.so`(14.2.109-1.6.2.bso) 中，
`virtual_event()` 里调用 profile 事件回调的那条指令被官方编译成了 `nop`
（文件偏移 `0x37c0`，字节 `1f 20 03 d5`；原版 `module-old.so` 即如此）。

日志上会打印 `Virtual profile voicecall changes to enabled (calling event callback)`，
但回调根本不执行 ⇒ `vsid=…;call_state=…` 参数永远到不了 HAL。

### 2.2 没有端口就没有路由（in_call 永假）

QTI HAL 的语音会话启动条件（voice_extn.c）：

```c
session->state.new = call_state;
...
if (is_call_active || (adev->voice.in_call && adev->mode == AUDIO_MODE_IN_CALL))
    update_calls(adev);   /* → voice_start_usecase(voicemmode1-call) */
```

`adev->voice.in_call` 只有输出流发生**设备路由变化**时才会被
`voice_start_call()` 置位（audio_hw.c 的 `out_set_parameters`：
`new_dev != NONE` 且 `out == adev->primary_output`，`mode == IN_CALL`）。

模块侧的触发点是 `droid-sink.c: sink_set_port_cb() → do_routing()`
→ `pa_droid_stream_set_route()` → HAL `out_set_parameters("routing=…")`。

旧 Jolla 模块只有**没有端口**的 `sink.raw`：策略应用端口失败
（journal 可见 `failed to set sink 'sink.raw' port to 'output-earpiece'`）
⇒ 路由事件永不发生 ⇒ `in_call` 永远为 0。

### 2.3 64 位 HAL 无法加载 32 位 ACDB（+ 实例抢占）

本机只有 32 位 ACDB：`/vendor/lib/libacdbloader.so`、`libacdb-fts`、
`libacdbrtac`、`libadm`（**无** `/vendor/lib64` 版本；LineageOS 的 HAL
服务本身也是 32 位）。

SFOS 的 pulseaudio 是 64 位，HAL 以 in-process 方式经 hybris 加载，
`dlopen("libacdbloader.so")` 找不到 64 位版本 ⇒ 语音校准不可能执行。

即使加了 64 位转发垫片，还有第二个坑：容器内空闲的 32 位
`vendor.audio-hal`（`android.hardware.audio.service`）启动时先初始化了
ACDB **实例**，我们的 daemon 再调 `acdb_loader_init_v3` 一律返回 **-12**，
随后 `send_voice_cal` 打印 `ACDB -> Not correctly initialized!`，校准无效
（对比：LineageOS 同一日志为 0 次该警告）。

## 3. 最终方案（架构）

```
电话接通
  └─ call-audio-watch.service（ofono 轮询通话状态）
       └─ pactl set-card-profile droid_card.primary voicecall
            └─ module-droid-card-29.so（UBports 模块 + 3 处二进制补丁）
                 ├─ set_mode(AUDIO_MODE_IN_CALL) + 端口应用（sink.primary_output 有端口）
                 │    └─ do_routing → HAL out_set_parameters("routing=1")
                 │         └─ voice_start_call() → in_call=1
                 └─ 回调发送 "vsid=297816064;call_state=2"
                      └─ HAL adev_set_parameters
                           └─ voice_extn: update_call_states → update_calls
                                └─ voice_start_usecase(voicemmode1-call)
                                     ├─ select_devices: voice-handset(acdb 7) / voice-dmic-ef(acdb 41)
                                     └─ ACDB send_voice_cal(7,41)
                                          └─ 64 位垫片 libacdbloader.so（unix socket 转发）
                                               └─ 32 位 acdbd32 daemon（INIT=0）
                                                    └─ 真 libacdbloader → Sent VocProc Cal!

挂断：set_mode(0) → voice_stop_call → 所有会话 INACTIVE → voice_stop_usecase（自动清理）
```

## 4. 组件清单（均在刷机包 `fastboot/fixes/` 里）

| 路径 | 作用 | md5 |
|---|---|---|
| `usr/lib64/pulse-17.0/modules/module-droid-card-29.so` | 补丁版音频模块 | `395507e194d1627b261e5d1908f8b8cc` |
| `usr/lib64/libdroid-sink-29.so` | UBports 模块依赖（含软件音量补丁，见 §4.2） | `133eb155021c5b93139d1022c709a19e` |
| `usr/lib64/libdroid-source-29.so` | 同上 | `70cb626047e54c603a4a8b3e9ab656af` |
| `usr/lib64/libdroid-util-29.so` | 同上 | `870a0e07fe479e6ba3eac8821a80f654` |
| `usr/lib64/libevdev.so.2` | 模块依赖（快照缺失） | `3684cd1f5472d0b400b1312b61e2d1f9` |
| `etc/pulse/arm_droid_card_custom.pa` | `load-module module-droid-card-29 rate=48000` | — |
| `etc/pulse/xpolicy.conf.d/xvars.conf` | 输出属性映射 | — |
| `usr/local/bin/acdbd32` | 32 位 ACDB daemon | `b5e5844909ce3831192195613b408931` |
| `usr/local/bin/acdbctl32` | 调试客户端 | `914a5b1da73a519aafb6c6ef111b2183` |
| `usr/local/bin/start-acdbd.sh` | 开机：停 vendor.audio-hal → 装 daemon → 启动 | `af893d84be78cfde93e42ac1b7f97182` |
| `etc/systemd/system/acdbd-container.service` | 上述脚本 oneshot | — |
| `usr/local/bin/call-audio-watch.sh` + `.service` | 通话切 profile / 解流静音 | — |
| `usr/local/bin/unmute-daemon.sh` + `.service` | 通用流解静音（locale 无关） | — |
| `usr/local/bin/bt-fixup.sh` + `.service` | 蓝牙 board-address / rfkill | — |
| `etc/systemd/system/ipa-boot.service` | IPA 启动（modem 稳定） | — |
| `home/defaultuser/acdbstub/libacdbloader.so` | 64 位 ACDB 垫片 | `39141cf8315a51251632a520b96e71a1` |
| `home/defaultuser/.config/systemd/user/pulseaudio.service.d/acdbstub.conf` | pulse 注入 LD_LIBRARY_PATH | — |

### 4.1 模块二进制补丁

原版 UBports 模块（md5 `52bbd6d8dc4837ee82ba51dd840544f2`）→ 3 处修改：

```
0x3004: 21 02 00 37  (tbnz w1,#0,0x3048)  →  11 00 00 14  (b 0x3048)
0x3034: a1 fe 07 36  (tbz  w1,#0,0x3008)  →  f5 ff ff 17  (b 0x3008)
0x5488: "realcall=on"                      →  "vsid=297816064;call_state=2"
```

含义：进入 voicecall 时**无条件**发送
`vsid=VOICEMMODE1_VSID(0x11C05000 = 297816064)` + `call_state=2(CALL_ACTIVE)`；
退出时不发送参数（清理交给 `set_mode(0) → voice_stop_call`）。

重新生成：

```sh
python3 fastboot/fix-sources/patch-module.py <原版module-droid-card-29.so> <输出>
```

（另有更早尝试的旧 Jolla 模块 5 处补丁路线，因官方 NOP 与无端口问题放弃，
详见 `fastboot/fix-sources/` 历史记录。）

### 4.2 libdroid-sink-29.so 软件音量补丁

该设备的 vendor HAL 对 primary output 的 `set_volume` 探测返回 0（声称支持
硬件音量），但实际执行时音量不生效：UI 滑到 9% 仍以满音量播放（大音量时
失真）。补丁强制模块使用软件音量：

```
0x68cc: cset w0, eq (1a9f17e0)  →  mov w0, #0 (52800000)
        u->use_hw_volume = (probe_ret == 0)  →  恒为 0
```

效果：跳过硬件音量回调注册（`pa_sink_set_set_volume_callback`），
pulse 对 sink 做软件增益，音量滑块恢复有效。
重新生成：`python3 fastboot/fix-sources/patch-software-volume.py <原版> <输出>`。

## 5. 验收标准（日志）

### 5.1 摘机瞬间（容器 logcat）

```
audio_hw_primary: adev_set_mode: mode 2
audio_hw_primary: out_set_parameters: ... kvpairs: routing=1;
voice_extn: update_call_states is_call_active:0 in_call:1, mode:2
voice_extn: update_calls: INACTIVE -> ACTIVE vsid:11c05000
voice   : voice_start_usecase: enter usecase:voicemmode1-call
audio_hw_primary: select_devices: ... (20: voice-handset, acdb 7) / (152: voice-dmic-ef, acdb 41)
ACDB-LOADER: ACDB -> send_voice_cal, acdb_rx = 7, acdb_tx = 41, feature_set = 0
ACDB-LOADER: ACDB -> Sent VocProc Cal!
voice   : voice_start_usecase: exit: status(0)
```

与 LineageOS 20 黄金日志逐行一致（LOS 对照：`los-golden/`，含
`voice_start_usecase` / `update_call_states in_call:1` / `send_voice_cal 7 41`）。

### 5.2 daemon 日志（容器内 `/data/local/tmp/acdbd32.log`）

```
DLOPEN OK
INIT result=0
LISTENING on /data/local/tmp/acdb.sock (0777)
VOICE_CAL 7 41 done
```

### 5.3 挂断

```
audio_hw_primary: adev_set_mode: mode 0
voice_extn: update_calls: ACTIVE/HOLD/LOCAL_HOLD -> INACTIVE vsid:11c05000
voice   : voice_stop_usecase: enter usecase:voicemmode1-call
```

## 6. 排障清单

| 现象 | 检查 |
|---|---|
| 完全无声 | `journalctl --user-unit=pulseaudio -b \| grep -E "droid-sink\|set_parameters"` 是否见回调与 vsid 参数 |
| 无 `update_call_states` | 模块是否补丁版（md5 `395507e1…`）；`arm_droid_card_custom.pa` 是否指向 `-29` |
| usecase 启动但无声/杂音 | `acdbd32.log`：`INIT result` 是否 0；出现 `Not correctly initialized` ⇒ 容器 `vendor.audio-hal` 又占用了 ACDB：`setprop ctl.stop vendor.audio-hal` 后 `systemctl restart acdbd-container` |
| 挂断后 usecase 不结束 | `/home/defaultuser/callwatch.log`（watcher）与 `adev_set_mode: mode 0` |
| 媒体/铃声无声 | `systemctl status unmute-daemon`；`pactl list sink-inputs` 是否被静音 |
| 重启后无声 | `systemctl status acdbd-container`；`tail /data/local/tmp/acdbd32.log`（需存在 `INIT result=0`） |

常用命令：

```sh
# 进入容器（任选一个存活容器进程做命名空间入口）
PIN=$(pgrep -f "/system/bin/logd" | head -n1)
nsenter -t $PIN -m -p -u -i -n -- /bin/busybox chroot /proc/$PIN/root /system/bin/sh -c \
    'logcat -d -t 800 | grep -iE "voice|acdb|update_call"'
```

## 7. 与刷机包的集成

- 全部文件位于 `fastboot/fixes/`（overlay 树）。构建时由
  `build-userdata.sh`（root/CI 路径）或 `build-userdata-noroot.sh`
  （本地免 root：fakeroot + mke2fs -d）在个人数据清扫**之后**覆盖进
  rootfs，属主/权限按路径自动设置。
- 服务自启通过 `etc/systemd/system/multi-user.target.wants/` 符号链接。
- `start-acdbd.sh` 启动时会把 `acdbd32`/`acdbctl32` 从 `/usr/local/bin`
  安装进容器 `/data/local/tmp`，因此刷机后无需任何手工部署。
- `boot/boot.img` 为含 8 个 DTB 的 5/5T 共享内核
  （sha256 `c2f17566567de2936701da9229010f4891013e349a0106dfbca1b3e285f5f97a`，
  内核配置含 `CONFIG_BT_HCIVHCI`）。

## 8. 可复现来源（fastboot/fix-sources/）

| 文件 | 说明 |
|---|---|
| `patch-module.py` | 从原版 UBports 模块生成补丁版 |
| `acdbd2.c` | 32 位 ACDB daemon 源码（`armv7a-linux-androideabi29-clang`） |
| `acdbstub.c` | 64 位垫片源码（`aarch64-linux-android29-clang`，`-shared -fPIC`） |
| `acdbctl.c` | socket 测试客户端 |
| `acdbtest.c` | ACDB 初始化参数矩阵测试工具（排障用） |
