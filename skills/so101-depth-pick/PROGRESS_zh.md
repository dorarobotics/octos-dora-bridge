# SO101 Depth Pick 进度记录

更新时间：2026-07-03

## 当前结论

抓取偏差的主要原因不是 IK 或机械臂执行误差，而是感知目标点本身偏了。

已实测移动到目标点后，`pinch` 的实际 FK 与命令目标的 XY 误差约为几毫米，主要误差不在运动链路。问题出在 eye-in-hand 相机视角下，`home` 位姿会让夹爪/前景遮挡方块，`open3d_geometry` 只能看到被遮挡后的可见轮廓，于是估计出的中心点不是方块真实质心。

因此不要继续用手工 XY 偏移补偿这个问题。之前调出的偏移只补偿了某一次遮挡视角下的错误质心，换位置后不泛化。

## 当前感知架构

`so101-depth-pick` 通过 `detector` 选择感知方案，统一输出 `Object3D`：

| detector | 用途 |
| --- | --- |
| `color_size` | 颜色分割 + 深度，适合颜色稳定的方块 |
| `yolo_seg` | YOLO 分割/框 + 深度，适合语义目标 |
| `prop_detector` | YOLO demo 道具标签适配 |
| `open3d_geometry` | RGB-D 点云几何，适合未知、分离的桌面物体 |

当前 5cm 大方块使用：

```json
{
  "profile": "orange_cube_5cm_open3d",
  "detector": "open3d_geometry"
}
```

后续换感知方案时，优先改 profile 里的 `detector` 和对应参数，不要在抓取流程里硬编码。

## 已完成改动

- `open3d_geometry` 支持图像 ROI 参数：
  - `open3d_image_roi_fraction`
- `locate_object_base` / `grasp_object` / `pick_yellow_to_black_box` 支持先移动到感知位姿再拍照：
  - `move_to_perception_pose`
  - `perception_pose_name`
  - `perception_pose_timeout_s`
- 抓取流程已改成先定位一次目标，再锁定该 base 坐标执行后续运动。
- 抓取流程支持 OpenCV 叠加图：
  - `show_viewer`
  - `viewer_live`
  - `viewer_save_path`
- `open3d_geometry` 叠加图可以把检测框画到 RGB 图上。

## 关键实测结果

### home 位姿

`home` 位姿下方块被夹爪/前景遮挡，检测框容易包含遮挡后的可见区域，中心点偏离真实方块中心。

典型结果：

```text
point_base_table: [0.344189, 0.023275, 0.0]
point_base:       [0.344189, 0.023275, 0.025]
approach:         [0.344189, 0.023275, 0.080]
```

### 直接移动验证

非接触移动到 open3d 给出的 approach 点时，实际 pinch FK 与目标接近：

```text
target approach:  [0.346240, 0.023759, 0.080]
actual_pinch_fk:  [0.344265, 0.026234, 0.072119]
actual_error_m:   [-0.001975, 0.002475, -0.007881]
error_norm_m:     0.008494
```

这说明运动执行链路基本可用，目标点来源更可疑。

### 更好的候选感知位姿

从手眼标定数据里选出的候选姿态：

```json
[-0.132722, -0.870747, 0.56004, 1.258939, -0.53549]
```

该姿态下叠加图：

```text
/tmp/octos_perception_pose_compare/roll_left_candidate.png
```

观察结果：

- 方块完整可见。
- 夹爪在画面下方，没有压住方块主体。
- 检测结果稳定优于 `home`。

该姿态已写入：

```text
skills/so101-depth-pick/profiles/orange_cube_5cm_open3d.json
```

当前 profile 中使用：

```json
{
  "move_to_perception_pose": true,
  "perception_joint_state": [-0.132722, -0.870747, 0.56004, 1.258939, -0.53549],
  "perception_pose_timeout_s": 35.0
}
```

## 当前中断点

正在实现 `perception_joint_state` 的完整工程化支持。

已开始做的事：

- `prepare_perception_pose()` 已准备支持关节数组。
- `move_to_joint_state()` 已准备处理 MoveIt HTTP 超时：
  - 如果接口超时，但实际关节已经接近目标，则释放 `octos` 控制锁并继续。
- `manifest.json` 已开始暴露 `perception_joint_state`。
- 测试已开始覆盖：
  - `locate_base` 可以先移动到 `perception_joint_state` 再拍照。
  - MoveIt 超时时，如果实体已到位，则恢复继续。

当前发现：

```text
实体已接近候选感知姿态，但最大关节误差约 0.026 rad。
当前通用恢复容差是 0.01 rad。
所以 locate_object_base 仍可能返回 "timed out"。
```

结论：不要放宽所有抓取运动的容差。只给“感知位姿移动”单独增加较宽容差。

## TODO

### 1. 完成感知位姿关节容差

给 `move_to_joint_state()` 增加可选参数：

```python
timeout_joint_tolerance_rad=None
```

默认继续使用严格容差：

```text
SO101_MOVE_TIMEOUT_JOINT_TOLERANCE_RAD=0.01
```

`prepare_perception_pose()` 对 `perception_joint_state` 使用：

```python
args.get("perception_joint_tolerance_rad", 0.035)
```

注意：只放宽拍照位姿，不放宽真正接触/抓取运动。

### 2. 补 profile

在 `orange_cube_5cm_open3d.json` 中加入：

```json
"perception_joint_tolerance_rad": 0.035
```

### 3. 补 manifest

三个工具都要暴露：

- `locate_object_base`
- `grasp_object`
- `pick_yellow_to_black_box`

字段：

```json
"perception_joint_state": {
  "type": "array",
  "items": { "type": "number" },
  "minItems": 5,
  "maxItems": 5
},
"perception_joint_tolerance_rad": {
  "type": "number",
  "default": 0.035
}
```

### 4. 跑测试

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .adora-hw-run/venv-python -m pytest \
  bridge/tests/test_object_perception.py \
  bridge/tests/test_so101_depth_pick_runtime.py \
  bridge/tests/test_live_open3d_geometry_viewer.py -q
```

### 5. 实机验证 locate

```bash
printf '%s' '{"profile":"orange_cube_5cm_open3d"}' | \
  skills/so101-depth-pick/main locate_object_base
```

预期：

- 自动移动到 `perception_joint_state`。
- MoveIt HTTP 超时时，如果实体已经接近感知姿态，可以恢复并释放控制锁。
- 返回 open3d 检测出的 base 坐标。
- 叠加图显示检测框包住方块主体，而不是夹爪遮挡区域。

### 6. 再做非接触移动验证

在确认检测稳定后，先只做：

- 夹爪保持打开。
- 移动到目标上方。
- 不闭合、不抓取。
- 查看实时/保存的 OpenCV overlay。

确认夹持点位于方块中心附近后，再考虑闭合抓取。

## 常用命令

查看状态：

```bash
curl -sS --fail --max-time 10 \
  -X POST http://127.0.0.1:8768/tools/get_state \
  -H 'Content-Type: application/json' \
  -d '{"args":{}}'
```

释放控制锁：

```bash
curl -sS --fail --max-time 10 \
  -X POST http://127.0.0.1:8768/tools/robot.release_control \
  -H 'Content-Type: application/json' \
  -d '{"args":{"control_source":"octos"}}'
```

打开夹爪：

```bash
curl -sS --fail --max-time 10 \
  -X POST http://127.0.0.1:8768/tools/vendor.moveit.arm.gripper.set \
  -H 'Content-Type: application/json' \
  -d '{"args":{"width":0.06}}'
```

移动回 home 关节：

```bash
curl -sS --fail --max-time 35 \
  -X POST http://127.0.0.1:8768/tools/vendor.moveit.arm.move_to_joint_state \
  -H 'Content-Type: application/json' \
  -d '{"args":{"joints":[-0.12044689782993835,-1.4676109270616056,0.3022680111146223,1.413908488538703,-0.016877909250055056],"control_source":"octos"}}'
```

注意：MoveIt HTTP 可能超时但实体已经移动到位。遇到超时后先 `get_state`，如果 `controller_holder` 是 `octos`，执行 `robot.release_control`。

## 2026-07-07 抓取误差记录

同一套 XY 补偿下，方块换位置后抓取精度明显变化：

- 使用补偿：`base_x_offset_m=-0.03`，`base_y_offset_m=+0.02`。
- 成功抓取轮：
  - 抓取目标：`[0.252405, 0.090749, 0.04]`
  - 实际 pinch：`[0.251100, 0.090098, 0.038272]`
  - 抓取误差约 `2.3mm`。
- 失败/未稳定抓取轮：
  - 抓取目标：`[0.299075, 0.016502, 0.04]`
  - 实际 pinch：`[0.293026, 0.015841, 0.031080]`
  - 抓取误差约 `10.8mm`，其中 X 方向约 `-6.0mm`，Z 方向约 `-8.9mm`。
  - 现场观察：方块在夹爪前方，夹爪末端紧贴方块。如果 X 方向没有这约 `6mm` 的短到位误差，理论上更可能让方块进入两指之间并抓住。

判断：

- 这不是单纯全局 XY 补偿问题。相同补偿在一个位置成功、换位置后失败，说明误差与机械臂姿态/工作空间位置相关。
- 官方 SO101 CAD/MJCF/URDF 几何和本地 `so101_pickplace.xml` 基本同源，但真实硬件的关节零位、回差、负载下舵机到位、夹爪 TCP 与模型仍可能存在姿态相关偏差。
- 后续不建议继续盲调一个全局补偿值；应记录多个姿态的 `target_base`、`actual_pinch_fk`、实际观察结果，用于做关节零位/TCP/base 外参或分区误差校正。

## 2026-07-07 手眼标定误差解释补充

现场观察：

- 成功抓取主要发生在方块位于底座正前方时。
- 方块偏左或偏右时，即使使用同一套补偿，夹爪更容易出现横向/前后偏差。

需要区分两类误差：

- 标定内误差：之前手眼标定计算出的约 `3mm` 以内误差，只说明标定样本自身或样本附近区域拟合较好。
- 抓取工作空间误差：方块放到左侧、右侧、远处、近处时，实际抓取误差会叠加手眼外参外推、相机深度、桌面平面假设、机械臂 FK/IK、关节零位、舵机回差/负载不到位和夹爪 TCP 误差。

结论：

- “手眼标定误差 3mm 内”不能等价理解为“全工作空间抓取误差 3mm 内”。
- 当前结果更准确的描述是：手眼标定在采样区域内可用，但左右/边缘区域没有充分验证。
- 正前方成功、左右偏差变大，符合“标定样本空间覆盖不足 + SO101 姿态相关执行误差”叠加的表现。
- 下一步应建立抓取工作空间验证表：左/中/右、近/中/远分别记录感知 base 坐标、抓取目标、`actual_pinch_fk`、现场偏差和是否抓取成功，再决定是否重采手眼标定或做分区/闭环校正。
