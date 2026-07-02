# Octos控制Adora机械臂抓黄色方块放到黑盒里
- Adora机械臂是so101等比例放大1.15倍
- 机械臂串口:/ttyACM0，USB相机（RGB相机）：/video4

## 启动octos和dora的bridge
```bash
cd .octos/skills/skills/octos-dora-bridge/
bash start_bridge.sh 
```

- 确认bridge状态
```bash
curl -fsS http://127.0.0.1:8768/healthz   # 输出 {"status":"ok"}
```
- 确认启动的机器人状态(robot_id)
```bash
  curl -fsS -X POST http://127.0.0.1:8768/tools/get_state \
    -H 'Content-Type: application/json' \
    -d '{"args":{}}' | python3 -m json.tool
# 输出
# {
#     "ok": true,
#     "code": "0",
#     "msg": "",
#    "data": {
#        "stream": {
#            "seq": 321,
#            "robot_id": "adora-hw-001",
#            "joint_positions": [
#                -0.10203463319351465,
#                -0.9582049387872165,
#                0.5922611791382956,
#                1.3724808931067498,
#                -0.8147427101617485
#            ],
#            "gripper_width": 0.0,
#            "estopped": false,
#            "estop_reason": null,
#            "controller_holder": null
#        },
#        "stale": false,
#        "last_age_s": 0.03592119699987961
#    },
#    "trace_id": null,
#    "request_id": ""
#}
```
## 启动octos
```bash
octos chat
# 输入自然语言指令: 执行Adora 机械臂抓取黄色方块放到黑盒
# 在LLM分解的过程中，有时候会因为llm迭代20次没完成任务，会导致退出，已经提了ISSUES。把任务拆分成多个小任务可以完成。
```

