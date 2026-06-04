# RK3588 Tools

RK3588 (NanoPi-M6 / Orange Pi 5 / etc.) 实用工具集。

## 工具列表

### 1. rk3588mon — 硬件监控 (htop 风格)

终端实时显示温度 / CPU / GPU / NPU / VPU 的频率和负载。

```
用法: python3 bin/rk3588mon.py
按键: q 退出, 1/2/3 切换刷新间隔
```

**数据来源**：全部读取 sysfs 节点，无需第三方 Python 包。

| 模块 | sysfs 路径 | 说明 |
|------|-----------|------|
| 温度 | `/sys/class/thermal/thermal_zone*/temp` | SoC / BigCore / Little / GPU / NPU |
| CPU 频率 | `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` | 8 核独立显示 |
| GPU 负载 | `/sys/devices/platform/fb000000.gpu/utilisation` | Mali-G610 MP4 |
| NPU 负载 | `/sys/class/devfreq/fdab0000.npu/load` | 6 TOPS NPU |
| VPU | `/sys/class/devfreq/fdbd0000.rkvenc-core/load` | 视频编码核心 |
| DMC | `/sys/class/devfreq/dmc/load` | 内存控制器 |

**坑点处理**：

- NPU/VENC/VOP 的 `devfreq/load` 在内核中始终返回 `100@freq`（即使设备已 suspend）。程序通过检查 `runtime_status` 来修正：若设备为 `suspended`，负载置 0。
- VOP（显示控制器）无有意义负载指标，直接固定显示 `--`。
- GPU 优先使用独立的 `utilisation` 节点，更准确。

### 2. rdp-display — RDP 虚拟显示器主屏切换

GNOME Remote Desktop (Wayland) 在 `extend` 模式下会创建一个虚拟显示器 `Meta-0`。
此工具自动将 `Meta-0` 设为主屏，使 Windows RDP 客户端获得最大分辨率。

```
用法: python3 bin/rdp-display.py          # 手动运行一次
      python3 bin/rdp-display.py --watch   # 后台监控（DBus 信号触发）
```

**原理**：

1. 通过 DBus 调用 `org.gnome.Mutter.DisplayConfig.GetCurrentState()` 获取当前显示器列表
2. 检测 `Meta-0` (RDP 虚拟显示器) 是否存在
3. 调用 `ApplyMonitorsConfig()` 将 `Meta-0` 设为主屏，`DSI-1` 并排放置在右侧
4. 监听 `MonitorsChanged` DBus 信号自动触发切换

**安装 systemd 用户服务**：

```bash
cp config/rdp-display.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rdp-display.service
```

### 3. ros.sh — ROS Noetic Docker 环境

一键进入 ROS Noetic Docker 容器，自动配置 X11 转发和 ROS 网络。

```
用法: ./bin/ros.sh              # 进入 bash
      ./bin/ros.sh rviz         # 直接运行 rviz
      ./bin/ros.sh rostopic list
```

**多终端支持**：首次运行创建名为 `ros-noetic` 的容器，后续再开终端自动 `docker exec` 复用同一容器。

**X11 转发原理**：

- 宿主机：Wayland + XWayland (`:0`)
- X11 认证文件：`/run/user/1000/.mutter-Xwaylandauth.*`
- 脚本自动复制认证文件到 `~/.docker.xauth`，挂载入容器
- 挂载 `/tmp/.X11-unix` 和当前目录到 `/workspace`

**Dockerfile**：`docker/Dockerfile` 基于 `ros:noetic-ros-base`，已切换阿里云镜像源。

## 一键部署

```bash
# 全部脚本赋予执行权限
chmod +x bin/*.sh bin/*.py

# RDP 显示切换开机自启
mkdir -p ~/.config/systemd/user
cp config/rdp-display.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now rdp-display.service

# 构建 ROS Docker 镜像（可选）
sudo docker build -t ros-noetic-desktop docker/
```

## 系统要求

- RK3588 平台（NanoPi M6 等）
- Ubuntu 24.04 (Noble) / arm64
- Python 3.12+ (标准库即可，无需额外包)
- GNOME 46+ on Wayland（rdp-display 需要）
- Docker（ros.sh 需要）

## 文件结构

```
rk3588-ubuntu24.04-arm64-wayland-tools/
├── README.md
├── bin/
│   ├── rk3588mon.py        # 硬件监控
│   ├── rdp-display.py      # RDP 主屏切换
│   └── ros.sh              # ROS Docker 入口
├── config/
│   └── rdp-display.service # systemd 用户服务
└── docker/
    └── Dockerfile          # ROS Noetic 桌面版
```