cmake_minimum_required(VERSION 3.0.2)
project(agent)

## Override Python executable to use conda environment
set(PYTHON_EXECUTABLE "/home/namy/anaconda3/envs/agent_uav/bin/python3")

## Find catkin and required components
find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  geometry_msgs
  nav_msgs
  sensor_msgs
  cv_bridge
  tf
  mavros
  mavros_msgs
) 

## Python setup
catkin_python_setup()

## Declare a catkin package
catkin_package(
  CATKIN_DEPENDS
    rospy
    std_msgs
    geometry_msgs
    nav_msgs
    sensor_msgs
    cv_bridge
    tf
    mavros
    mavros_msgs
)

## Install Python scripts
catkin_install_python(PROGRAMS
  agent.py
  vision.py
  tools.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

## Install launch files
install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch
  FILES_MATCHING PATTERN "*.launch"
)

## Install config files
install(DIRECTORY cfg/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/cfg
  FILES_MATCHING PATTERN "*.json" PATTERN "*.yaml"
)

install(DIRECTORY config/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/config
  FILES_MATCHING PATTERN "*.rviz"
)

## Install Python scripts in scripts/
catkin_install_python(PROGRAMS
  scripts/vision_bridge.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

## Install shell scripts
install(PROGRAMS
  scripts/vision_bridge.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

## Install model files (optional, can be large)
# install(DIRECTORY pth/
#   DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/pth
# )
