#!/usr/bin/env python3
"""
rdp-display.py - 自动将 RDP 虚拟显示器 (Meta-0) 设为主屏
用法: python3 rdp-display.py           # 手动
     python3 rdp-display.py --watch    # 后台监控
"""

import dbus
import dbus.mainloop.glib
import sys
import os

BUS = 'org.gnome.Mutter.DisplayConfig'
PATH = '/org/gnome/Mutter/DisplayConfig'


def get_mode_name(monitor):
    """取第一个 preferred 或 current 模式的名称"""
    for mode_data in monitor[1]:
        flags = {}
        for k, v in mode_data[6].items():
            flags[str(k)] = v
        if flags.get('is-preferred') or flags.get('is-current'):
            return str(mode_data[0])
    # fallback: 第一个 mode
    return str(monitor[1][0][0])


def set_meta_as_primary():
    bus = dbus.SessionBus()
    obj = bus.get_object(BUS, PATH)
    iface = dbus.Interface(obj, BUS)

    serial, monitors, logical, props = iface.GetCurrentState()

    # 检查是否有 Meta-0
    meta_mon = None
    dsi_mon = None
    for m in monitors:
        conn = str(m[0][0])
        if conn == 'Meta-0':
            meta_mon = m
        elif conn == 'DSI-1':
            dsi_mon = m

    if not meta_mon:
        return False  # 没有 RDP 虚拟显示器

    # 检查是否已经是 Meta-0 主屏
    for lm in logical:
        for ms in lm[5]:
            if str(ms[0]) == 'Meta-0' and lm[4] == 1:
                return False  # 已经是了

    # 构建新配置: Meta-0 在左(主屏), DSI-1 在右
    new_logical = []

    # Meta-0
    meta_mode = get_mode_name(meta_mon)
    ms_meta = dbus.Struct((
        dbus.String('Meta-0'),
        dbus.String(meta_mode),
        dbus.Dictionary({}, signature='sv'),
    ), signature='(ssa{sv})')
    lm_meta = dbus.Struct((
        dbus.Int32(0),
        dbus.Int32(0),
        dbus.Double(1.0),
        dbus.UInt32(0),
        dbus.Boolean(True),     # primary
        dbus.Array([ms_meta], signature='(ssa{sv})'),
    ), signature='iiduba(ssa{sv})')
    new_logical.append(lm_meta)

    # DSI-1 (放在 Meta-0 右侧)
    if dsi_mon:
        dsi_mode = get_mode_name(dsi_mon)
        # Meta-0 宽度 = 1280
        ms_dsi = dbus.Struct((
            dbus.String('DSI-1'),
            dbus.String(dsi_mode),
            dbus.Dictionary({}, signature='sv'),
        ), signature='(ssa{sv})')
        lm_dsi = dbus.Struct((
            dbus.Int32(1280),
            dbus.Int32(0),
            dbus.Double(1.0),
            dbus.UInt32(0),
            dbus.Boolean(False),    # not primary
            dbus.Array([ms_dsi], signature='(ssa{sv})'),
        ), signature='iiduba(ssa{sv})')
        new_logical.append(lm_dsi)

    iface.ApplyMonitorsConfig(
        dbus.UInt32(serial),
        dbus.UInt32(2),
        new_logical,
        dbus.Dictionary({}, signature='sv'),
    )
    return True


def watch():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    def handler(*_):
        if set_meta_as_primary():
            print("Meta-0 已设为主屏")

    bus = dbus.SessionBus()
    obj = bus.get_object(BUS, PATH)
    iface = dbus.Interface(obj, BUS)
    iface.connect_to_signal("MonitorsChanged", handler)

    # 启动跑一次
    handler()

    print("监控中... (Ctrl+C 退出)")
    from gi.repository import GLib
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        loop.quit()


if __name__ == '__main__':
    if '--watch' in sys.argv:
        watch()
    else:
        if set_meta_as_primary():
            print("Meta-0 已设为主屏")
        else:
            print("无需切换")