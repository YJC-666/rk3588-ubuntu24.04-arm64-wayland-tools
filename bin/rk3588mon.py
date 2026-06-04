#!/usr/bin/env python3
"""
rk3588mon - htop 风格 RK3588 硬件监控
用法: ./rk3588mon.py
按键: q 退出, 1/2/3 切换刷新间隔(1/2/3s)
"""

import curses
import time
import os

# ── sysfs 路径 ──────────────────────────────────────────────
THERMAL_ZONES = [
    (0, "SoC"),
    (1, "Big0"),
    (2, "Big1"),
    (3, "Little"),
    (4, "Center"),
    (5, "GPU"),
    (6, "NPU"),
]
CPU_CORES = 8
DEVICES = {
    "GPU":   "fb000000.gpu",
    "NPU":   "fdab0000.npu",
    "VENC0": "fdbd0000.rkvenc-core",
    "VENC1": "fdbe0000.rkvenc-core",
    "VOP":   "fdd90000.vop",
    "DMC":   "dmc",
}

# ── 数据读取 ────────────────────────────────────────────────
def read_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return 0

def read_str(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return "N/A"

def parse_load(s):
    try:
        parts = s.split("@")
        return int(parts[0]), int(parts[1].replace("Hz", ""))
    except Exception:
        return 0, 0

def collect():
    data = {}

    # temps
    temps = {}
    for idx, name in THERMAL_ZONES:
        temps[name] = read_int(f"/sys/class/thermal/thermal_zone{idx}/temp") / 1000.0
    data["temps"] = temps

    # cpu freqs
    data["cpu_freqs"] = [read_int(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq") // 1000 for i in range(CPU_CORES)]

    # cpu gov
    govs = []
    for i in range(CPU_CORES):
        govs.append(read_str(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_governor"))
    data["cpu_govs"] = govs

    # load
    with open("/proc/loadavg") as f:
        parts = f.read().strip().split()
    data["load1"], data["load5"], data["load15"] = parts[0], parts[1], parts[2]
    data["procs"] = parts[3]

    # mem
    with open("/proc/meminfo") as f:
        m = {}
        for line in f:
            k, v = line.split(":")
            m[k.strip()] = int(v.strip().split()[0])
    data["mem_total"] = m["MemTotal"] // 1024
    data["mem_free"] = m["MemFree"] // 1024
    data["mem_buffers"] = m["Buffers"] // 1024
    data["mem_cached"] = m["Cached"] // 1024
    data["mem_available"] = m["MemAvailable"] // 1024
    data["mem_used"] = data["mem_total"] - data["mem_free"] - data["mem_buffers"] - data["mem_cached"]

    # swap
    data["swap_total"] = m.get("SwapTotal", 0) // 1024
    data["swap_free"] = m.get("SwapFree", 0) // 1024
    data["swap_used"] = data["swap_total"] - data["swap_free"]

    # uptime
    with open("/proc/uptime") as f:
        uptime_sec = float(f.read().split()[0])
    d = int(uptime_sec // 86400)
    h = int((uptime_sec % 86400) // 3600)
    mi = int((uptime_sec % 3600) // 60)
    if d > 0:
        data["uptime"] = f"{d}d {h:02d}:{mi:02d}"
    else:
        data["uptime"] = f"{h:02d}:{mi:02d}"

    # devfreq
    devs = {}
    for label, devpath in DEVICES.items():
        s = read_str(f"/sys/class/devfreq/{devpath}/load")
        lp, fhz = parse_load(s)
        if fhz == 0:
            fhz = read_int(f"/sys/class/devfreq/{devpath}/cur_freq")

        # NPU/VENC 的 devfreq load 在空闲时仍返回 100，用 runtime PM 修正
        if label in ("NPU", "VENC0", "VENC1") and lp >= 100:
            pm = read_str(f"/sys/devices/platform/{devpath}/power/runtime_status")
            if pm == "suspended":
                lp = 0
        # VOP 是显示控制器，无有意义负载指标
        if label == "VOP":
            lp = 0
        # GPU 有独立 utilisation 节点更准确
        if label == "GPU":
            util = read_int(f"/sys/devices/platform/{devpath}/utilisation")
            if util >= 0:
                lp = min(util, 100)

        devs[label] = (lp, fhz // 1_000_000)
    data["devices"] = devs

    return data

# ── 工具函数 ────────────────────────────────────────────────
def fmt_freq(mhz):
    return f"{mhz/1000:.1f}G" if mhz >= 1000 else f"{mhz}M"

def meter_bar(win, y, x, w, pct, rev=False):
    """htop 渐变色条，返回结束 x"""
    pct = max(0, min(pct, 100))
    ratio = pct / 100.0
    cw = max(2, w)

    fill = int(round(ratio * cw))
    fill = max(0, min(fill, cw))

    # 三段: 绿 0-50%, 黄 50-80%, 红 80-100%
    segs = [
        (int(cw * 0.50), 2),
        (int(cw * 0.30), 3),
        (cw - int(cw * 0.50) - int(cw * 0.30), 4),
    ]
    pos = 0
    drawn_fill = False
    for seg_len, color_id in segs:
        chunk = max(0, min(fill - pos, seg_len))
        if chunk > 0:
            attr = curses.color_pair(color_id) | (curses.A_REVERSE if rev else 0)
            win.addstr(y, x + pos, "█" * chunk, attr)
            drawn_fill = True
        pos += seg_len

    remaining = cw - fill
    if remaining > 0:
        attr = curses.color_pair(1) | (curses.A_REVERSE if rev else 0)
        win.addstr(y, x + fill, "░" * remaining, attr)

    return x + cw


# ── 主循环 ────────────────────────────────────────────────
def main(stdscr):
    curses.curs_set(0)
    curses.use_default_colors()

    curses.init_pair(1, -1, -1)
    curses.init_pair(2, 2, -1)    # green
    curses.init_pair(3, 3, -1)    # yellow
    curses.init_pair(4, 1, -1)    # red
    curses.init_pair(5, 4, -1)    # blue
    curses.init_pair(10, 2, -1)   # green text

    # header bar: black on blue
    curses.init_pair(20, 0, 5)

    interval = 1.0
    prev = time.time()

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        if h < 14 or w < 72:
            stdscr.addstr(0, 0, "Terminal too small, need at least 72x14")
            stdscr.refresh()
            time.sleep(2)
            continue

        data = collect()
        row = 0

        # ───── 顶部标题栏 ─────
        title = f" rk3588mon  -  {data['uptime']}  "
        load_str = f"Load: {data['load1']} {data['load5']} {data['load15']}  Procs: {data['procs']}"
        timestr = time.strftime("%Y-%m-%d %H:%M:%S")
        space = w - len(title) - len(timestr) - 1
        if space < 0:
            title = title[:max(0, space)]
            space = 0
        header = title + " " * space + timestr
        stdscr.addstr(row, 0, header[:w], curses.color_pair(20) | curses.A_BOLD)
        row += 1

        # 第二行: 任务数 + 内存概要
        mem_str = f"Mem: {fmt_size(data['mem_used'])}/{fmt_size(data['mem_total'])}"
        sw_str = f"  Swap: {fmt_size(data['swap_used'])}/{fmt_size(data['swap_total'])}" if data['swap_total'] > 0 else ""
        info = f" Tasks: {data['procs'].split('/')[-1] if '/' in data['procs'] else data['procs']}  {mem_str}{sw_str}"
        stdscr.addstr(row, 0, info[:w], curses.A_BOLD)
        row += 2

        # ───── CPU ─────
        stdscr.addstr(row, 0, "CPU", curses.A_BOLD | curses.color_pair(5))
        row += 1

        # 两列布局: 左侧 A55#0-3, 右侧 A76#0-3
        col_w = (w - 3) // 2  # 3 = " │ " divider
        for i in range(4):
            if row >= h:
                break
            # 左列
            freq_l = data["cpu_freqs"][i]
            pct_l = min(100, freq_l / 18)  # A55 max 1800 MHz → /18
            bar_l = col_w - 20
            if bar_l < 4:
                bar_l = 4
            stdscr.addstr(row, 0, f" {i}", curses.A_BOLD)
            meter_bar(stdscr, row, 3, bar_l, pct_l)
            x = 3 + bar_l + 1
            stdscr.addstr(row, x, f"{pct_l:5.1f}% {fmt_freq(freq_l):>5s}", curses.A_BOLD)

            # 分隔
            stdscr.addstr(row, col_w + 1, "│")

            # 右列
            idx_r = i + 4
            freq_r = data["cpu_freqs"][idx_r]
            gov_r = data["cpu_govs"][idx_r][:4]
            pct_r = min(100, freq_r / 24)  # A76 max 2400 MHz → /24
            bar_r = w - col_w - 22
            if bar_r < 4:
                bar_r = 4
            stdscr.addstr(row, col_w + 4, f"{idx_r}", curses.A_BOLD)
            meter_bar(stdscr, row, col_w + 7, bar_r, pct_r)
            x2 = col_w + 7 + bar_r + 1
            stdscr.addstr(row, x2, f"{pct_r:5.1f}% {fmt_freq(freq_r):>5s}", curses.A_BOLD)
            row += 1

        row += 1

        # ───── 加速器 (GPU / NPU) ─────
        if row < h:
            stdscr.addstr(row, 0, "GPU/NPU", curses.A_BOLD | curses.color_pair(5))
            row += 1
            piece = (w - 6) // 2
            bar_w = piece - 18
            if bar_w < 3:
                bar_w = 3
            for label, x_off in [("GPU", 0), ("NPU", piece + 3)]:
                lp, f_mhz = data["devices"].get(label, (0, 0))
                freq_s = fmt_freq(f_mhz)
                stdscr.addstr(row, x_off, f" {label}")
                meter_bar(stdscr, row, x_off + 5, bar_w, lp)
                x = x_off + 5 + bar_w + 1
                stdscr.addstr(row, x, f" {lp:3d}% {freq_s:>5s}")
            row += 1

        # ───── VPU / 其他 (VENC, VOP, DMC) ─────
        if row < h:
            # VENC 合并显示
            venc_lp0, venc_f0 = data["devices"].get("VENC0", (0, 0))
            venc_lp1, venc_f1 = data["devices"].get("VENC1", (0, 0))
            vop_lp, vop_f = data["devices"].get("VOP", (0, 0))
            dmc_lp, dmc_f = data["devices"].get("DMC", (0, 0))

            parts = []
            # VENC
            parts.append(f"VENC {venc_lp0:3d}% {fmt_freq(venc_f0):>5s}")
            # VOP - 无负载指标
            parts.append(f"VOP  --  {fmt_freq(vop_f):>5s}")
            # DMC
            parts.append(f"DMC {dmc_lp:3d}% {fmt_freq(dmc_f):>5s}")

            line = "   " + "  ".join(parts)
            stdscr.addstr(row, 0, "VPU/Other")
            stdscr.addstr(row, 10, line[:w - 10])
            row += 1

        row += 1

        # ───── 温度 (全在一行) ─────
        if row < h:
            stdscr.addstr(row, 0, "Thermals", curses.A_BOLD | curses.color_pair(5))
            row += 1
            parts = []
            for name, temp_c in data["temps"].items():
                color_id = 2 if temp_c < 50 else (3 if temp_c < 70 else 4)
                tag = f" {name}:{temp_c:.0f}°C"
                parts.append((tag, color_id))

            x = 0
            for tag, color_id in parts:
                if x + len(tag) >= w:
                    break
                stdscr.addstr(row, x, tag, curses.color_pair(color_id) | curses.A_BOLD)
                x += len(tag)
            row += 2

        # ───── 内存条 ─────
        if row < h:
            stdscr.addstr(row, 0, "Memory", curses.A_BOLD | curses.color_pair(5))
            row += 1
            mem_used_pct = data["mem_used"] / data["mem_total"] * 100 if data["mem_total"] else 0
            mem_buf_pct = data["mem_buffers"] / data["mem_total"] * 100 if data["mem_total"] else 0
            mem_cached_pct = data["mem_cached"] / data["mem_total"] * 100 if data["mem_total"] else 0

            bar_w = w - 32
            if bar_w < 8:
                bar_w = 8

            n_used = int(round(bar_w * mem_used_pct / 100))
            n_buf = int(round(bar_w * mem_buf_pct / 100))
            n_cache = int(round(bar_w * mem_cached_pct / 100))
            n_free = max(0, bar_w - n_used - n_buf - n_cache)

            pos = 0
            if n_used > 0:
                stdscr.addstr(row, pos, "█" * min(n_used, bar_w - pos), curses.color_pair(2))
                pos += n_used
            if n_buf > 0:
                stdscr.addstr(row, pos, "█" * min(n_buf, bar_w - pos), curses.color_pair(5))
                pos += n_buf
            if n_cache > 0:
                stdscr.addstr(row, pos, "█" * min(n_cache, bar_w - pos), curses.color_pair(3))
                pos += n_cache
            if n_free > 0:
                stdscr.addstr(row, pos, "░" * min(n_free, bar_w - pos), curses.color_pair(1))
                pos += n_free

            m_detail = f"  {fmt_size(data['mem_used'])}/{fmt_size(data['mem_total'])}  {mem_used_pct:.0f}%"
            stdscr.addstr(row, bar_w + 1, m_detail, curses.A_BOLD)
            row += 2

        # ───── 底部 ─────
        if row < h - 1:
            row = h - 1
            help_text = f" Q:quit  1/2/3:interval({interval:.0f}s)  rk3588mon"
            stdscr.addstr(row, 0, help_text[:w], curses.A_REVERSE | curses.A_DIM)

        stdscr.refresh()

        # ── 按键 ──
        stdscr.nodelay(1)
        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            break
        elif key == ord("1"):
            interval = 1.0
        elif key == ord("2"):
            interval = 2.0
        elif key == ord("3"):
            interval = 3.0

        wait = max(0.05, interval - (time.time() - prev))
        if wait > 0:
            time.sleep(wait)
        prev = time.time()


def fmt_size(kb):
    if kb >= 1024 * 1024:
        return f"{kb/1024/1024:.1f}T"
    elif kb >= 1024:
        return f"{kb/1024:.1f}G"
    elif kb >= 1:
        return f"{kb}M"
    return "0M"


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass