cmake_minimum_required(VERSION 3.5)
project(netravis_carter_navigation)

find_package(ament_cmake REQUIRED)

install(DIRECTORY
  launch
  params
  maps
  rviz2
  config
  DESTINATION share/${PROJECT_NAME})

ament_package()
