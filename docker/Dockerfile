FROM ros:noetic-ros-base

# Switch to Aliyun apt mirror for faster downloads
RUN sed -i 's|http://ports.ubuntu.com/ubuntu-ports|http://mirrors.aliyun.com/ubuntu-ports|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu|http://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list

# Install desktop packages (rviz, rqt, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ros-noetic-desktop \
    build-essential \
    cmake \
    git \
    python3-pip \
    python3-vcstool \
    net-tools \
    nano \
    xauth \
    && rm -rf /var/lib/apt/lists/*

# Source ROS setup by default
RUN echo "source /opt/ros/noetic/setup.bash" >> /root/.bashrc

CMD ["bash"]