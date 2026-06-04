#!/bin/bash
# ros.sh - 一键进入 ROS Noetic Docker 环境
# 用法: ./ros.sh [可选: 容器内命令]
#       首次运行会创建容器，之后新终端自动复用已有容器
# 直接运行，不要加 sudo

XAUTH=/home/pi/.docker.xauth
XAUTH_SRC=/run/user/1000/.mutter-Xwaylandauth.SVGAH3

# 准备 X11 认证
if [ -f "$XAUTH_SRC" ]; then
    cp "$XAUTH_SRC" "$XAUTH" 2>/dev/null
    chmod 644 "$XAUTH" 2>/dev/null
fi

# 容器名
NAME=ros-noetic

# 检查容器是否已在运行
RUNNING=$(sudo docker inspect -f '{{.State.Running}}' $NAME 2>/dev/null)

if [ "$RUNNING" = "true" ]; then
    # 已有容器 → 新开一个终端
    CMD="${@:-bash}"
    sudo docker exec -it $NAME bash -c "source /opt/ros/noetic/setup.bash && $CMD"
else
    # 无容器 → 创建新容器
    if [ $# -eq 0 ]; then
        CMD="bash"
    else
        CMD="$@"
    fi
    sudo docker run -it --rm \
        --name $NAME \
        -e DISPLAY=:0 \
        -v /tmp/.X11-unix:/tmp/.X11-unix \
        -v $XAUTH:$XAUTH:ro \
        -e XAUTHORITY=$XAUTH \
        --net=host \
        -v "$(pwd):/workspace" \
        -w /workspace \
        ros-noetic-desktop \
        bash -c "source /opt/ros/noetic/setup.bash && $CMD"
fi