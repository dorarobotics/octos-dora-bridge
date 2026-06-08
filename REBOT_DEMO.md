# reBotArm B601-DM pick-and-place — same octos skill architecture as UR5e

This branch (`feat/rebot-arm`) adds a **reBotArm B601-DM** pick-and-place demo that
reuses the *entire* octos skill stack from the UR5e demo (bridge ➜ moveit_arm_node
➜ dora-moveit2 MoveGroup nodes ➜ MuJoCo), swapping only the robot. Both demos run
side-by-side; nothing UR5e changes.

> Robot model source: `reBotArm_develop_hjx/mujoco/xml/rebot_gripper/reBot-DevArm_gripper.xml`
> (6-DOF Damiao-motor arm + a single-actuator parallel gripper grasping a red cube).

## What a robot swap actually touches (only 4 things)

| # | Binding | UR5e | reBotArm |
|---|---------|------|----------|
| 1 | MuJoCo scene (`MODEL_NAME`) | `models/ur5e.xml` | `models/rebot_pickplace.xml` (new) |
| 2 | Config module (`ROBOT_CONFIG_MODULE`) | `…config.ur5e` (`UR5eConfig`) | `…config.rebot` (`RebotConfig`, new) |
| 3 | Gripper width➜ctrl mapping | Robotiq: high ctrl = closed | reBot: **inverted** — `gripper_merge` env `CTRL_MIN=0.05 CTRL_MAX=0.001` |
| 4 | `ROBOT_ID` | `ur5e-001` | `rebot-001` |

**Everything else transfers verbatim** — the skill code (`arm_skills.py`,
`arm_agent.py`, `skill_pickplace.py`), `ball_state.py`, the moveit_arm node, the
bridge, and the MoveGroup nodes are unchanged.

## The key invariant: identical qpos layout

The skill IK and `ball_state` rely on fixed qpos slices. The reBot scene XML
declares the **free object first** (as the UR5e scene does) so the layout matches
exactly — no code re-indexing:

```
object freejoint = qpos[0:7]      arm joint1..6 = qpos[7:13]      gripper = qpos[13:15]
arm qvel = qvel[6:12]             RebotConfig.ARM_QPOS_START = 7
```

(reBot's stock XML had the box *last*; `rebot_pickplace.xml` moves it first.)

## Files added / changed

**dora-moveit2** (`feat/rebot-arm`, off `feat/injectable-node`):
- `examples/move_group_demo/models/rebot_pickplace.xml` — scene: object-first, plus
  an added `pinch` site (grasp/IK reference) and a green `place_target` site.
- `examples/move_group_demo/models/rebot_assets/` — vendored reBot meshes/textures.
- `examples/move_group_demo/move_group_demo/config/rebot.py` — `RebotConfig`.

**octos-dora-bridge** (`feat/rebot-arm`, off `main`):
- `dataflows/rebot-mujoco-bridge.yaml` — canonical wiring (the 4 swaps applied).
- `examples/arm_skills.py`, `examples/arm_agent.py` — now env-parametrized
  (`ARM_HOME`, `GRASP_Z/PLACE_Z/APPROACH_Z`, `LIFT_ZS`, `GRIP_OPEN_W/CLOSE_W`,
  `OBJECT_NOUN`, `ROBOT_NAME`); UR5e defaults preserved.
- `examples/skill_pickplace.py` — deterministic skill-level driver (no LLM), for tuning.
- `scripts/run-rebot-agent.sh` — turnkey launcher (`DRIVER=agent` LLM / `DRIVER=skill`).
- `scripts/run-rebot-pickplace.sh` — thin `DRIVER=skill` wrapper.

## Bring-up on epyc

> Live dataflows run on epyc only. Sync the laptop branches over (rsync, **not**
> gh clone), then derive the live dataflow.

1. **Sync** the two repos to `~/dorarobotics-test/` (octos-dora-bridge) and
   `~/Public/github_dora_nav_moveit/dora-moveit2` on their `feat/rebot-arm` branches.
   The reBot config lives inside the dora-moveit2 editable install — already covered
   by the existing `pip install -e` of `examples/move_group_demo`.
2. **Derive `~/dorarobotics-test/rebot-mujoco-live.yml`** from the working
   `ur5e-mujoco-live.yml` by applying the 4 swaps (use the committed
   `dataflows/rebot-mujoco-bridge.yaml` as the diff guide): `MODEL_NAME`, the
   `ROBOT_CONFIG_MODULE` (×5), `ROBOT_ID` (×2), and the `gripper_merge` env block.
3. **First run — deterministic, for tuning** (watch the MuJoCo viewer):
   ```bash
   bash ~/dorarobotics-test/run-rebot-pickplace.sh
   ```
4. **Full agentic demo** (LLM plans from the sentence):
   ```bash
   bash ~/dorarobotics-test/run-rebot-agent.sh "put the red block on the green plate"
   ```

## Live-tuning checklist (expected during first bring-up)

These were set from the MJCF geometry and **need validation against the live FK**:
- **`pinch` site z** in `rebot_pickplace.xml` (initial `0 0 0.165` in link6 frame) —
  must land at the closed-finger grasp center. Adjust until a down-pointing IK
  solution has the fingers straddling the cube.
- **`ARM_HOME`** / keyframe arm pose — must be a non-singular seed from which the IK
  reaches the workspace. Override per-run with `ARM_HOME="j1,…,j6"`.
- **`GRASP_Z` / `APPROACH_Z` / `LIFT_ZS`** — cube center rests at z≈0.02; defaults
  `0.02 / 0.18 / 0.06,0.10,0.18`.
- **Object & plate XY** — `red_box` at (0.35,0), `place_target` at (0.25,0); move
  both into reBot's comfortable reach if needed.
- **Gripper close width / force** — `GRIP_CLOSE_W=0.0` drives fingers onto the cube;
  if it slips, lower the close target or raise the `gripper` actuator force.
