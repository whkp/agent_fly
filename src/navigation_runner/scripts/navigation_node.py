#!/usr/bin/env python3

import rospy
from navigation import Navigation
import hydra
import os
import sys

FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts/cfg")

@hydra.main(config_path=FILE_PATH, config_name="train", version_base=None)
def main(cfg):
    rospy.init_node("navigation_node", anonymous=True)
    nav = Navigation(cfg)
    nav.run()
    rospy.spin()


if __name__ == "__main__":
    # 过滤掉ROS参数，避免与Hydra冲突
    # ROS参数格式: __name:=value, __log:=value 等
    filtered_argv = [arg for arg in sys.argv if not arg.startswith('__')]
    sys.argv = filtered_argv
    
    main()