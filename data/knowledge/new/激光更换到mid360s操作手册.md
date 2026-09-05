# 激光更换到mid360s操作手册

\[zj\_humanoid\_navigation\_upgrade\_wa\_v1\.5\.0\.run\]

- 先将该包放置到机器人的/tmp目录下

```Bash
cd /tmp
chmod +x *.run
./*.run --sensor_lidar
```

- 更换entrypoint\.sh，把 dpkg \-i \-\-force\-overwrite /package/\*mid360\-\*\.deb 换成 dpkg \-i \-\-force\-overwrite /package/\*mid360s\-\*\.deb
- 更换supervisor\.conf，把 roslaunch livox\_ros\_driver2 msg\_MID360\.launch  换成 roslaunch livox\_ros\_driver2 msg\_MID360s\.launch 
- 重启sensor\_lidar

```Bash
cd ~/navi_project
docker compose down sensor_lidar
docker compose up -d sensor_lidar
```



