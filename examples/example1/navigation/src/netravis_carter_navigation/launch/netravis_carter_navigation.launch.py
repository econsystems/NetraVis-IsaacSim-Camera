# Based on NVIDIA's carter_navigation launch (Isaac Sim ROS workspaces), Apache-2.0.
#
# Nav2 + nvblox for Nova Carter with four e-con NetraVis6L_USB cameras, compact warehouse:
#   - nvblox fuses the four cameras' ground-truth depth into a 3D map and publishes a 2D slice
#     that the Nav2 costmaps use for obstacles (nvblox_layer); each camera's colour image of the
#     same view (same camera_info) only colours the mesh;
#   - the 3D lidar, flattened to /scan, drives AMCL localisation on the warehouse map.

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer, Node
from launch_ros.descriptions import ComposableNode

PKG = "netravis_carter_navigation"
CAMERAS = ("front", "back", "left", "right")      # nvblox camera_0..3
TOPIC_ROOT = "/netravis"


def generate_launch_description():
    share = get_package_share_directory(PKG)
    nav2_launch = os.path.join(get_package_share_directory("nav2_bringup"), "launch")
    use_sim_time = LaunchConfiguration("use_sim_time", default="True")
    map_file = LaunchConfiguration(
        "map", default=os.path.join(share, "maps", "carter_warehouse_navigation.yaml"))
    params_file = LaunchConfiguration(
        "params_file", default=os.path.join(share, "params", "netravis_carter_navigation_params.yaml"))

    remappings = []
    for i, side in enumerate(CAMERAS):
        remappings += [(f"camera_{i}/depth/image", f"{TOPIC_ROOT}/{side}/depth"),
                       (f"camera_{i}/depth/camera_info", f"{TOPIC_ROOT}/{side}/camera_info"),
                       (f"camera_{i}/color/image", f"{TOPIC_ROOT}/{side}/color"),
                       (f"camera_{i}/color/camera_info", f"{TOPIC_ROOT}/{side}/camera_info")]

    nvblox = ComposableNodeContainer(
        name="nvblox_container",
        namespace="",
        package="rclcpp_components",
        executable="component_container_mt",
        composable_node_descriptions=[ComposableNode(
            name="nvblox_node",
            package="nvblox_ros",
            plugin="nvblox::NvbloxNode",
            remappings=remappings,
            parameters=[os.path.join(share, "config", "nvblox_netravis.yaml"),
                        {"use_sim_time": True}],
        )],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("map", default_value=map_file, description="Full path to the map file"),
        DeclareLaunchArgument("params_file", default_value=params_file, description="Full path to the Nav2 params file"),
        DeclareLaunchArgument("use_sim_time", default_value="true", description="Use the Isaac Sim clock"),
        DeclareLaunchArgument("rviz", default_value="true", description="Start RViz"),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(nav2_launch, "rviz_launch.py")),
            condition=IfCondition(LaunchConfiguration("rviz")),
            launch_arguments={"namespace": "", "use_namespace": "False",
                              "rviz_config": os.path.join(share, "rviz2", "netravis_carter_navigation.rviz")}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(nav2_launch, "bringup_launch.py")),
            launch_arguments={"map": map_file, "use_sim_time": use_sim_time, "params_file": params_file}.items(),
        ),
        nvblox,
        Node(
            package="pointcloud_to_laserscan", executable="pointcloud_to_laserscan_node",
            name="pointcloud_to_laserscan",
            remappings=[("cloud_in", "/front_3d_lidar/lidar_points"), ("scan", "/scan")],
            parameters=[{
                "target_frame": "front_3d_lidar",
                "transform_tolerance": 0.01,
                "min_height": -0.4,
                "max_height": 1.5,
                "angle_min": -3.14159,           # full 360 deg for localisation
                "angle_max": 3.14159,
                "angle_increment": 0.0087,
                "scan_time": 0.3333,
                "range_min": 0.05,
                "range_max": 100.0,
                "use_inf": True,
                "inf_epsilon": 1.0,
                "concurrency_level": 4,
            }],
        ),
    ])
