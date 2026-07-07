# 07 安全与故障恢复 — ⚠️ 机制齐全,缺定量统计

已实现并有定性验证+单测:IWDG看门狗、USB断链自愈、断网补传(tests/test_uplink.py)、teleop松手deadman+雷达门控(tests/test_teleop_gate.py)+App遥控deadman(19测)。**缺 USB/看门狗/断网/雷达/App松手 各≥10次的停车/恢复时间/丢失重复/残留速度统计**。详见 ../INDEX.md 第7条。
