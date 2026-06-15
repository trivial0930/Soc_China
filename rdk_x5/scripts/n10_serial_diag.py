#!/usr/bin/env python3
"""N10 激光雷达串口一次性诊断 (在 RDK X5 上运行)。

用途：固定雷达后 /dev/ttyACM0 仍枚举但 /scan 无数据时，从底层确认是否
真的有原始字节进来。把交接文档 Step 1 的零散检查合并成一次运行：

  1. 设备节点与 by-id 软链是否存在
  2. USB 是否枚举 (lsusb 找 1a86:55d4 QinHeng / CH34x)
  3. dmesg 里该设备最近的内核日志
  4. 多波特率原始字节探测，重点看 230400 下是否出现 N10 帧头 a5 5a
  5. (可选) 用 pyserial 切换 DTR/RTS 后再读一次

判读：
  - 在 230400 看到 `a5 5a ...` 周期帧头  -> 雷达本体在出数据，问题在 ROS 层，去重启驱动。
  - 所有波特率都 0 字节                  -> 硬件侧：雷达供电 / 数据线 / 固定后插头受力 / 雷达未上电输出。

只读诊断，不写雷达、不动 ROS。先停掉占用串口的 ROS 驱动再跑本脚本。

用法:
  python3 n10_serial_diag.py
  python3 n10_serial_diag.py --port /dev/ttyACM0 --seconds 3
"""

import argparse
import os
import subprocess
import sys
import time

DEFAULT_PORT = "/dev/ttyACM0"
BY_ID = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B8E669875-if00"
# 230400 是 N10 实测正确波特率，放第一个；其余作为兜底排查。
BAUDS = [230400, 115200, 256000, 460800]
FRAME_HEADER = b"\xa5\x5a"


def run(cmd):
    try:
        out = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        return (out.stdout or "") + (out.stderr or "")
    except Exception as exc:  # noqa: BLE001 - 诊断脚本，吞掉异常只报告
        return f"<command failed: {exc}>"


def hexdump(data):
    return " ".join(f"{b:02x}" for b in data)


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def check_devices(port):
    section("1. 设备节点 / by-id 软链")
    for path in (port, BY_ID):
        if os.path.exists(path):
            real = os.path.realpath(path)
            print(f"  [OK]   {path}" + (f"  -> {real}" if real != path else ""))
        else:
            print(f"  [MISS] {path}  不存在")
    print("\n  ls -l /dev/ttyACM* /dev/ttyUSB*:")
    print("  " + run("ls -l /dev/ttyACM* /dev/ttyUSB* 2>&1").replace("\n", "\n  ").rstrip())


def check_usb():
    section("2. USB 枚举 (期望看到 1a86:55d4 QinHeng / CH34x)")
    lsusb = run("lsusb 2>&1")
    print("  " + lsusb.replace("\n", "\n  ").rstrip())
    if "1a86" in lsusb:
        print("\n  [OK]   找到 1a86 (QinHeng/CH34x) 设备，USB 枚举正常。")
    else:
        print("\n  [WARN] 没看到 1a86，雷达 USB 可能没枚举上 —— 先查 USB 线和供电。")


def check_dmesg():
    section("3. dmesg 最近 ttyACM / ch34x / usb 日志")
    out = run("dmesg 2>/dev/null | grep -iE 'ttyACM|ch34|cdc_acm|usb .*1a86|disconnect' | tail -n 20")
    out = out.strip()
    print("  " + (out.replace("\n", "\n  ") if out else "(无匹配行，可能需要 sudo dmesg)"))


def probe_baud(port, baud, seconds):
    """用已验证可用的 stty + 原始读法，在指定波特率下抓字节。"""
    cfg = run(f"stty -F {port} {baud} raw -echo -crtscts 2>&1").strip()
    if cfg:
        print(f"  stty {baud}: {cfg}")
    collected = bytearray()
    fd = None
    try:
        fd = os.open(port, os.O_RDONLY | os.O_NONBLOCK)
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                chunk = os.read(fd, 4096)
                if chunk:
                    collected += chunk
                    if len(collected) >= 4096:
                        break
                else:
                    time.sleep(0.02)
            except BlockingIOError:
                time.sleep(0.02)
            except OSError as exc:
                print(f"  [ERR]  读 {port} @ {baud} 出错: {exc}")
                break
    except OSError as exc:
        print(f"  [ERR]  打开 {port} @ {baud} 失败: {exc}")
    finally:
        if fd is not None:
            os.close(fd)
    return bytes(collected)


def check_raw(port, seconds):
    section(f"4. 原始字节探测 (每个波特率约 {seconds}s)")
    any_bytes = False
    header_baud = None
    for baud in BAUDS:
        print(f"\n  --- {baud} ---")
        data = probe_baud(port, baud, seconds)
        n = len(data)
        print(f"  读到 {n} 字节")
        if n:
            any_bytes = True
            print("  前 64 字节: " + hexdump(data[:64]))
            if FRAME_HEADER in data:
                idx = data.find(FRAME_HEADER)
                print(f"  [OK]   找到 N10 帧头 a5 5a (偏移 {idx})")
                if header_baud is None:
                    header_baud = baud
    return any_bytes, header_baud


def check_control_lines(port, seconds):
    section("5. (可选) pyserial 切换 DTR/RTS 后再读")
    try:
        import serial  # type: ignore
    except ImportError:
        print("  (pyserial 未安装，跳过)")
        return None
    found = False
    for dtr, rts in ((False, False), (True, True), (True, False), (False, True)):
        try:
            sp = serial.Serial(port, 230400, timeout=0.3)
            sp.dtr = dtr
            sp.rts = rts
            time.sleep(0.2)
            data = sp.read(2048)
            sp.close()
            print(f"  DTR={int(dtr)} RTS={int(rts)} -> {len(data)} 字节"
                  + (f"  (a5 5a! @off {data.find(FRAME_HEADER)})"
                     if FRAME_HEADER in data else ""))
            if FRAME_HEADER in data:
                found = True
        except Exception as exc:  # noqa: BLE001
            print(f"  DTR={int(dtr)} RTS={int(rts)} -> 出错: {exc}")
    return found


def verdict(any_bytes, header_baud):
    section("判读")
    if header_baud:
        print(f"  [PASS] 在 {header_baud} 看到 N10 帧头 a5 5a —— 雷达本体在出数据。")
        print("         问题在 ROS 层。下一步：按交接文档 Step 2 重启 lslidar 驱动，")
        print("         然后 ros2 topic hz /scan + echo --once 验证。")
    elif any_bytes:
        print("  [WARN] 有字节但没看到 a5 5a 帧头。")
        print("         确认波特率与 lsx10.yaml 一致 (应 230400)；也可能是别的设备占了这个口。")
    else:
        print("  [FAIL] 所有波特率都 0 字节 —— 优先怀疑硬件侧，不要继续 ROS 调试。")
        print("         现场检查：雷达指示灯/旋转声、固定后插头是否半插/被铜柱顶住、")
        print("         USB 线、雷达供电线是否松动或压线；给雷达断电再上电后重跑本脚本。")


def main():
    ap = argparse.ArgumentParser(description="N10 串口一次性诊断")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--seconds", type=float, default=3.0, help="每个波特率抓取时长")
    args = ap.parse_args()

    print(f"N10 串口诊断  port={args.port}  time={time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("提示：先停掉占用串口的 ROS 驱动再跑（否则会抢不到串口）。")

    check_devices(args.port)
    check_usb()
    check_dmesg()
    any_bytes, header_baud = check_raw(args.port, args.seconds)
    ctrl = check_control_lines(args.port, args.seconds)
    if ctrl:
        header_baud = header_baud or 230400
        any_bytes = True
    verdict(any_bytes, header_baud)
    return 0 if header_baud else 1


if __name__ == "__main__":
    sys.exit(main())
