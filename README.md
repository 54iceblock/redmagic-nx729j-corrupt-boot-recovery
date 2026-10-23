# RedMagic 8 Pro (NX729J) — Corrupt-Boot Recovery Without Unlocking

> Recover a **locked-bootloader** RedMagic 8 Pro / 8S Pro from the endless
> `Your device is corrupt` loop by switching the active A/B slot through
> `misc` → **fastbootd** → `bootctl` — **no bootloader unlock, no paid service**.
>
> 无需解锁 bootloader、不花钱，通过 `misc` → **fastbootd** → `bootctl` 切回正确的
> A/B 槽位，把卡在 `Your device is corrupt` 死循环里的红魔 8 Pro / 8S Pro 救回来。

![status](https://img.shields.io/badge/verified-NX729J-2ea44f)
![platform](https://img.shields.io/badge/SoC-Qualcomm%20SM8550-blue)
![unlock](https://img.shields.io/badge/bootloader-stays%20LOCKED-informational)

---

## TL;DR

**EN** — If AVB rejects your *current* slot (rollback index lower than the value
stored in TEE) but the *other* slot is fine, the device is stuck: `set_active`
is refused while locked, and `misc` `slot_suite` does nothing because the slot
state lives in RPMB. The trick is that `misc.command = "boot-fastboot"` still
works: the bootloader then boots **fastbootd from the good slot**, and
recovery's own `bootctl` marks that slot `successful` and makes it current.
After a normal reboot the device starts from the good slot and AVB verifies
`green`.

**中文** — 如果 AVB 拒绝**当前槽位**（回滚索引低于 TEE 中保存的值），但**另一个槽位**
是好的，设备就会卡死：locked 状态下 `set_active` 被拒，而 `misc` 的 `slot_suite`
怎么改都无效——因为槽位状态保存在 RPMB 里。突破口是：`misc.command =
"boot-fastboot"` 这个字段**仍然有效**，bootloader 会从**好槽位**启动
**fastbootd**，而 recovery 自带的 `bootctl` 会把该槽位标记为 `successful`
并设为当前槽。之后再正常重启，设备就从好槽位启动，AVB 校验 `green`。

---

## 1. Symptom / 症状

**EN**

- Device shows `Your device is corrupt. It can't be trusted and may not work
  properly`, or falls into the Qualcomm fastboot menu
  (Start / restart bootloader / recovery mode / poweroff / boot to ffbm / boot to qmmi).
- `fastboot oem device-info` reports the bootloader is **locked**.
- `fastboot --set-active=<other>` fails with
  `set_active command is not allowed on locked devices`.
- Often triggered by flashing a firmware from another region, a downgrade, or
  an interrupted flash.

**中文**

- 屏幕显示 `Your device is corrupt. It can't be trusted and may not work properly`，
  或掉进高通 fastboot 菜单（Start / restart bootloader / recovery mode / poweroff /
  boot to ffbm / boot to qmmi）。
- `fastboot oem device-info` 显示 bootloader 为 **locked**。
- `fastboot --set-active=<另一个槽>` 报
  `set_active command is not allowed on locked devices`。
- 常由跨区刷机、降级、刷机中断引起。

---

## 2. Root cause / 根因

**EN** — Each slot carries its own AVB rollback index (`vbmeta_system`'s
`rollback_index`, usually equal to the build's security patch date). The
bootloader refuses any image whose index is **lower** than the value already
recorded in TEE.

Typical chain:

```
Device was running slot B (patch 2025-12-01, TEE already recorded 2025-12-01)
   ↓  flashed an older firmware / flash failed
bootloader falls back to slot A (old build, patch 2025-11-01)
   ↓
2025-11-01 < TEE 2025-12-01  →  AVB rejects  →  corrupt loop
```

**中文** — 每个槽位有独立的 AVB 回滚索引（`vbmeta_system` 的 `rollback_index`，
通常等于该构建的安全补丁日期）。bootloader 会拒绝任何索引**低于** TEE 中已记录值的镜像。

典型链条：

```
设备原本运行 b 槽（补丁 2025-12-01，TEE 已记录 2025-12-01）
   ↓  刷了旧固件 / 刷机失败
bootloader 回落到 a 槽（旧构建，补丁 2025-11-01）
   ↓
2025-11-01 < TEE 2025-12-01  →  AVB 拒绝  →  corrupt 死循环
```

### What does NOT work / 无效的做法

| Attempt / 尝试 | Result / 结果 |
|---|---|
| Reflash the same old firmware / 重刷同一个旧固件 | ❌ still corrupt / 依旧 corrupt |
| Restore a full backup of the good slot / 回刷好槽位的全盘备份 | ❌ bootloader still boots the bad slot / bootloader 仍启动坏槽 |
| `fastboot --set-active=b` | ❌ `not allowed on locked devices` |
| Writing AOSP `slot_suite` at `misc` offset 2048 / 写 misc 偏移 2048 的 slot_suite | ❌ no effect — slot state is **not** in misc / 无效，槽位状态**不在** misc |
| Unlocking the bootloader / 解锁 bootloader | ✅ but permanently hurts attestation & warranty / 可行但会永久影响 attestation 和保修 |

**The slot state lives in RPMB**, which EDL cannot write / **槽位状态保存在 RPMB**，EDL 写不进去。

---

## 3. The key insight / 关键发现

**EN** — The `misc` partition begins with a bootloader control block (BCB). The
bootloader does **not** use its `command` field to pick a slot, but it **does**
use it to pick a *boot mode*:

**中文** — `misc` 分区开头是 bootloader control block（BCB）。bootloader **不用**
它的 `command` 字段选槽位，但**会用**它选**启动模式**：

| `misc[0:32]` | Effect / 效果 |
|---|---|
| `boot-recovery` | boot recovery / 启动 recovery |
| **`boot-fastboot`** | **boot fastbootd (userspace fastboot) / 启动 fastbootd** |
| `bootonce-bootloader` | boot bootloader / 启动 bootloader |

**EN** — Because the good slot can boot recovery, writing `boot-fastboot` makes
the bootloader launch *that slot's* fastbootd. Inside fastbootd, recovery's
`bootctl` marks the slot `successful` and sets it as current. A normal reboot
then starts the good slot and AVB reports `green`.

**中文** — 因为好槽位能启动 recovery，写入 `boot-fastboot` 会让 bootloader 启动
**好槽位的 fastbootd**。在 fastbootd 中，recovery 自带的 `bootctl` 会把该槽位标记为
`successful` 并设为当前槽。之后正常重启就会从好槽位启动，AVB 报 `green`。

> Credit / 来源：this behaviour was reverse-engineered from the `misc` images
> bundled in a third-party service tool (`misc_tofastbootd.img`, whose command
> field is exactly `boot-fastboot`).
> 该行为是通过分析某第三方维修工具内置的 `misc` 镜像（`misc_tofastbootd.img`，
> command 字段正是 `boot-fastboot`）反推出来的。

---

## 4. Requirements / 前置条件

**EN**

1. A working **Qualcomm 9008 / QDLoader** driver — **WHQL-signed only**
   (test-signed builds are rejected by Windows with `Problem Code 52 / 0xC0000428`).
   See [Appendix B](#appendix-b--the-9008-driver-must-be-whql-signed--9008-驱动必须是-whql-签名版).
2. A matching **EDL package** for your model, providing `firehose.elf` and the
   `rawprogram*/patch*` XML files.
3. `QSaharaServer.exe` and `fh_loader.exe` (shipped with QPST / QFIL).
4. **A full EDL backup of all partitions** — do this *before* anything else.
   Without it you have no way back.

**中文**

1. 可用的 **Qualcomm 9008 / QDLoader** 驱动——**必须 WHQL 签名版**
   （测试签名版会被 Windows 拒绝加载，报 `Problem Code 52 / 0xC0000428`）。
   见[附录 B](#appendix-b--the-9008-driver-must-be-whql-signed--9008-驱动必须是-whql-签名版)。
2. 与该机型匹配的 **EDL 包**，提供 `firehose.elf` 和
   `rawprogram*/patch*` XML。
3. `QSaharaServer.exe` 与 `fh_loader.exe`（QPST / QFIL 自带）。
4. **全分区 EDL 备份**——动手前必须先做，否则出事没有退路。

---

## 5. Step by step / 操作步骤

### 5.1 Enter EDL / 进入 EDL

**EN** — Either `adb reboot edl` (if the system still boots) or, from a powered-off
device, hold **Volume+ and Volume−** while plugging in USB. Confirm Windows shows
`Qualcomm HS-USB QDLoader 9008 (COMx)`.

**中文** — 可以用 `adb reboot edl`（系统还能启动时），或者关机后**同时按住
音量+ 和 音量−** 再插 USB。确认 Windows 出现
`Qualcomm HS-USB QDLoader 9008 (COMx)`。

```powershell
adb reboot edl
# or / 或者: power off, hold Vol+ & Vol-, plug USB
```

### 5.2 Upload the firehose programmer / 上传 firehose 编程器

```powershell
QSaharaServer.exe -p \\.\COM5 -s 13:C:\path\to\firehose.elf
# success / 成功: "Sahara protocol completed"
```

> Adjust the COM port to yours / 把 COM5 换成你自己的端口号。

### 5.3 Build the `boot-fastboot` misc image / 构造 misc 镜像

**EN** — The BCB sits at offset 0; the `command` field is 32 bytes. An 8 KiB
image is enough.

**中文** — BCB 在偏移 0，`command` 字段 32 字节。8 KiB 镜像就够了。

```python
data = bytearray(8192)
data[0:13] = b'boot-fastboot'
open('misc_tofastbootd.img', 'wb').write(data)
```

Or use the helper / 或直接用仓库里的脚本：

```powershell
python tools/make_misc_fastboot.py -o misc_tofastbootd.img
```

### 5.4 Write it to `misc` / 写入 misc

**EN** — Create a rawprogram XML. `start_sector` **differs per model** — take
the real value from your own GPT / `partitions.json`:

**中文** — 建一个 rawprogram XML。`start_sector` **因机型而异**，请从你自己的
GPT / `partitions.json` 里取真实值：

```xml
<?xml version="1.0" ?>
<data>
  <program SECTOR_SIZE_IN_BYTES="4096"
           file_sector_offset="0"
           filename="misc_tofastbootd.img"
           label="misc"
           num_partition_sectors="2"
           physical_partition_number="0"
           start_sector="8200" />
</data>
```

```powershell
fh_loader.exe --port=\\.\COM5 --sendxml=write_misc.xml `
  --search_path=. --noprompt --zlpawarehost=1 --memoryname=ufs
# success / 成功: "All Finished Successfully"
```

> `misc` on this family is 1 MiB, sector size 4096, normally LUN0 / sector 8200.
> Writing only the first 2 sectors leaves the rest of the partition untouched.
> 本系列的 `misc` 是 1 MiB、扇区 4096，通常在 LUN0 / sector 8200。
> 只写前 2 个扇区，分区其余内容不受影响。

### 5.5 Reset into fastbootd / 复位进入 fastbootd

```powershell
fh_loader.exe --port=\\.\COM5 --noprompt --zlpawarehost=1 --memoryname=ufs --reset
```

**EN** — The device now boots **fastbootd** and enumerates as
`VID_18D1&PID_4EE0` (`Android Bootloader Interface`). On Windows, Google's
official USB driver (`usb_driver_r13/android_winusb.inf`) already covers this
PID:

**中文** — 设备现在会启动 **fastbootd**，USB 枚举为
`VID_18D1&PID_4EE0`（`Android Bootloader Interface`）。Windows 上 Google 官方
USB 驱动（`usb_driver_r13/android_winusb.inf`）覆盖该 PID：

```powershell
# elevated / 管理员权限
pnputil /add-driver android_winusb.inf /install
```

### 5.6 Verify and reboot / 验证并重启

```powershell
fastboot devices
# xxxxxxxx    fastboot

fastboot getvar current-slot
# b            <- now the good slot / 已经是好槽位

fastboot getvar slot-successful:b
# yes          <- marked successful by bootctl / 已被 bootctl 标记成功

fastboot reboot
```

**EN** — The device now boots the good slot, AVB passes and Android starts
normally.

**中文** — 设备此刻从好槽位启动，AVB 通过，Android 正常进入系统。

---

## 6. Verify success / 验证成功

```powershell
adb shell getprop ro.boot.slot_suffix        # _b
adb shell getprop ro.boot.verifiedbootstate  # green
adb shell getprop ro.boot.flash.locked       # 1   <- still locked / 仍是 locked
adb shell getprop sys.boot_completed         # 1
```

---

## 7. Caveats / 注意事项

**EN**

1. **Make a full EDL backup first.** A wrong `misc` only changes the boot mode
   and is trivially reversible over EDL — but a corrupted partition set cannot
   be rescued by this method.
2. **This only works if the target slot's AVB actually passes.** If *both* slots
   have rollback indexes below the TEE value, no amount of slot switching will
   help — you need a firmware whose security patch is ≥ the recorded value, or
   official service tools.
3. **You may still need one Power press per boot.** If the bootloader keeps
   trying the bad slot first it will show the corrupt warning before falling
   back; that ordering is its own persistent state and misc cannot change it.
   Pressing Power once continues into the good slot.
   To remove it for good, the bad slot must also pass verification — i.e. copy
   the good slot's content onto it (`vbmeta_system` + the `super` logical
   partitions), roughly 10 GB of writes.
4. **Do not unlock the bootloader** unless you consciously give up Play
   Integrity and warranty.

**中文**

1. **务必先做全盘 EDL 备份。** misc 写错只会影响启动模式，EDL 随时改回；
   但分区数据本身被刷坏的话，这个方法救不了。
2. **本方法只在目标槽位的 AVB 能通过时有效。** 如果两个槽位的回滚索引都低于
   TEE 记录值，怎么切槽都没用——必须刷入安全补丁 ≥ 记录值的固件，或用官方工装工具。
3. **可能每次开机仍需按一次电源键。** 如果 bootloader 仍先尝试坏槽位，会先显示
   corrupt 警告再回落；这个顺序由它自己的持久状态决定，misc 改不了。按一次电源键
   即可继续进入好槽位。要彻底消除，必须让坏槽位也能通过校验——即把好槽位内容
   复制过去（`vbmeta_system` + `super` 里的逻辑分区），约 10 GB 写入量。
4. **不要解锁 bootloader**，除非你明确要放弃 Play Integrity 和保修。

---

## 8. If it doesn't work / 如果无效

**EN**

- `fastboot devices` is empty in fastbootd → the USB driver is not bound to
  `18D1:4EE0`. Install Google's USB driver (see 5.5).
- fastbootd boots but `current-slot` is still the bad slot → the good slot
  cannot boot recovery either; check whether the good slot's `vbmeta_system`
  rollback index really is ≥ the TEE value.
- Nothing enumerates at all → re-enter EDL and restore your backup.

**中文**

- fastbootd 里 `fastboot devices` 为空 → USB 驱动没绑到 `18D1:4EE0`，
  安装 Google USB 驱动（见 5.5）。
- 能进 fastbootd 但 `current-slot` 仍是坏槽 → 好槽位的 recovery 也起不来；
  确认好槽位 `vbmeta_system` 的回滚索引确实 ≥ TEE 值。
- 完全没有设备枚举 → 重新进 EDL，回滚备份。

---

## Appendix A — Fake Play Store stub in CN ROMs / 国行 ROM 的假 Play 商店

**EN** — Some China ROMs ship a placeholder under
`/system/priv-app/GooglePlayServicesUpdater/` that claims the package name
`com.android.vending` but has **no launcher activity**:

**中文** — 部分国行 ROM 在 `/system/priv-app/GooglePlayServicesUpdater/` 放了个
占位包，占用了 `com.android.vending` 这个包名，但**没有启动 Activity**：

```
package : com.android.vending
class   : com.google.android.apps.play.store.libs.fakeverifier.PackageVerificationReceiver
version : 22.7.54
launcher: none
```

**EN** — It blocks installing the real Play Store (different signature), which
manifests as "tap install, it flashes, nothing happens". Fix:

**中文** — 它会阻止安装真正的 Play Store（签名不同），表现为"点安装、跳一下、
没反应"。解决：

```bash
adb shell pm uninstall --user 0 com.android.vending      # remove stub (reversible) / 移除占位包（可恢复）
adb install -r -d "Google_Play_Store.apk"                # install the real one / 安装真实版本
```

**EN** — Afterwards GMS usually updates itself automatically. Note that a CN
build still won't pass Play certification — certification is decided server-side
by build fingerprint.

**中文** — 之后 GMS 通常会自动更新。注意 CN 构建仍然过不了 Play 认证——
认证是服务端按构建指纹判定的。

To restore the stub / 恢复占位包：

```bash
adb shell pm install-existing --user 0 com.android.vending
```

---

## Appendix B — The 9008 driver must be WHQL-signed / 9008 驱动必须是 WHQL 签名版

**EN** — The `qcser.inf` floating around forums is usually **test-signed**
(`Signer = USBHostDriver(Test003)`). Windows 10 refuses to load it and reports
`Problem Code 52 (CM_PROB_UNSIGNED_DRIVER) / 0xC0000428`. Use the signed package
from the Microsoft Update Catalog instead.

**中文** — 论坛流传的 `qcser.inf` 通常是**测试签名**版
（`Signer = USBHostDriver(Test003)`）。Windows 10 会拒绝加载，报
`Problem Code 52 (CM_PROB_UNSIGNED_DRIVER) / 0xC0000428`。改用微软更新目录里
有正式签名的版本即可。

| | |
|---|---|
| Catalog search / 目录搜索 | `Qualcomm HS-USB QDLoader 9008` |
| Result / 结果 | `Qualcomm Incorporated - Ports - 2.1.2.2` (2016-03-25, 12.1 MB) |
| Signer / 签名者 | `Microsoft Windows Hardware Compatibility Publisher` |
| Hardware ID | `USB\VID_05C6&PID_9008` |

```powershell
# elevated / 管理员权限
pnputil /add-driver qcser.inf /install
```

---

## Related notes / 相关笔记

- AVB layout on this device / 本机 AVB 结构：`vbmeta_a` verifies
  boot/dtbo/init_boot/vendor_boot (hash) and
  odm/system_dlkm/vendor/vendor_dlkm (hashtree);
  `vbmeta_system` verifies system/product/system_ext (hashtree).
- Rollback indexes observed / 实测回滚索引：
  CN 10.0.12 (b slot) = `2025-12-01`, (a slot) = `2025-11-01`;
  GB 9.5.4 = `2025-01-01`; GB 10.0.9 = `2025-06-01`; CN V2.36 = `2023-03-01`.
- A failed metadata-remap experiment reached the boot logo but panicked at
  init — copying the logical partitions physically is more reliable than
  remapping `super` metadata.
  元数据重映射实验能出 logo 但在 init 阶段 panic——物理复制逻辑分区比重映射更可靠。

---

## Disclaimer / 免责声明

**EN** — This worked on one NX729J running CN 10.0.12 with a locked bootloader.
Your device, firmware and partition layout may differ. Writing to `misc`,
`super` or any other partition can brick your device. Always make a full EDL
backup first. Use at your own risk; no warranty of any kind.

**中文** — 本方法在一台运行 CN 10.0.12、bootloader 已锁的 NX729J 上验证通过。
你的设备、固件、分区布局可能不同。写 `misc`、`super` 或任何分区都可能导致变砖。
请务必先做全盘 EDL 备份。风险自负，不提供任何担保。

## License / 许可

MIT — see [LICENSE](LICENSE).
