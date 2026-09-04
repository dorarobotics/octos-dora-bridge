# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

### Bug Fixes

- Restore graceful e2e skip when AGIBOT_REPO_TOKEN absent ([ed6d8db](https://github.com/dorarobotics/octos-dora-bridge/commit/ed6d8db507a4cd498731c23b74b967e5057c7fe9))
- Correct fake-node paths in nav-base-bridge + add timer ([7ba0fd4](https://github.com/dorarobotics/octos-dora-bridge/commit/7ba0fd4fa065021b8660290f22838d5556f6a5a1))
- Correct ur5e-mujoco-bridge wiring to real dora-moveit2 topology ([15db46a](https://github.com/dorarobotics/octos-dora-bridge/commit/15db46add5ebd21eb55a6ce39a43cb4836a1969b))
- Disable heartbeat watchdog in ur5e-mujoco sim dataflow ([8878ece](https://github.com/dorarobotics/octos-dora-bridge/commit/8878ece486d801787e6c48b9cf0219a6eeade563))
- Decode joint_commands as a full float vector ([a663798](https://github.com/dorarobotics/octos-dora-bridge/commit/a6637984f4c296e6314247401133aabda76dbd8a))
- Seed the grasp orientation from the approach pose, not HOME ([e0b2c7a](https://github.com/dorarobotics/octos-dora-bridge/commit/e0b2c7ab7256417d844731dc654e6eb8e9f492a8))

### Documentation

- Clean-PC runbook for the octos-agent pick-and-place + harden launcher ([f8f6b0d](https://github.com/dorarobotics/octos-dora-bridge/commit/f8f6b0d0dff63e2f99009f90c756574f52c9a773))
- Record live-validation results + the actuator-stiffen fix ([d9a28e1](https://github.com/dorarobotics/octos-dora-bridge/commit/d9a28e1b0f9a1c3e134c8d0d40d2665c4c45d112))
- Nav-base setup.md — no-hardware sim run as octos skill + Rerun visualization ([8bdeb68](https://github.com/dorarobotics/octos-dora-bridge/commit/8bdeb68581a48e05158e0e6ebef671f4c7f8b772))
- Correct map/waypoints claims in SKILL.md ([865c8e0](https://github.com/dorarobotics/octos-dora-bridge/commit/865c8e04f9f27dde5a769ac9180586c8df24841c))
- Add manual_nav_viz.md — hand-run commands for the asus nav-base visual demo ([533bab1](https://github.com/dorarobotics/octos-dora-bridge/commit/533bab1e19d0aa5df5598857c95c8b1293286b5d))

### Features

- Wire moveit-arm-dora-node (UR5e) into octos-dora-bridge ([b2ac42d](https://github.com/dorarobotics/octos-dora-bridge/commit/b2ac42d4263be8451beab143439d87458e2ad469))
- Wire nav-base-dora-node into octos-dora-bridge ([47e316b](https://github.com/dorarobotics/octos-dora-bridge/commit/47e316b5c6b5de8c863d3898cb6ffc5482970547))
- Add gripper_merge node + pure merge_control logic ([65e971a](https://github.com/dorarobotics/octos-dora-bridge/commit/65e971a7fd01433d349bf935fb4d67614fe5bfba))
- Add ur5e-mujoco-bridge dataflow; retire in-process ur5e-bridge ([0bbe993](https://github.com/dorarobotics/octos-dora-bridge/commit/0bbe9937a659909c34c113c2aef380adb19f01b8))
- Visual sim demos + UR5e pick-and-place, driven over octos HTTP ([643e2a0](https://github.com/dorarobotics/octos-dora-bridge/commit/643e2a0b393d760aac535801541d84d9b39440d7))
- Full-orientation IK, radial place, robust grasp tuning ([f4f9f19](https://github.com/dorarobotics/octos-dora-bridge/commit/f4f9f19ce11c7fd29d971c387c98e313f433ba5f))
- Octos LLM agent drives UR5e pick-and-place from a sentence ([59f0a5a](https://github.com/dorarobotics/octos-dora-bridge/commit/59f0a5abf05776af159560cb42314b402accb460))
- Octos skill demo for reBotArm B601-DM ([78d5238](https://github.com/dorarobotics/octos-dora-bridge/commit/78d5238406fe406e4300b3634ca4e378d25b47a8))
- Declarative octos skill descriptor for SO-101 ([1bfb993](https://github.com/dorarobotics/octos-dora-bridge/commit/1bfb9930ecfbbc4dd3111caa60bb293f0e8f30dc))
- SO-101 MuJoCo dataflow (gripper jaw at actuator #5) ([98b6e06](https://github.com/dorarobotics/octos-dora-bridge/commit/98b6e060b2351e6aa687209f53dfa9d2bb8a3e4c))
- Offline MP4 renderer for nav-base viz (headless, no dora/rerun) ([e5e6824](https://github.com/dorarobotics/octos-dora-bridge/commit/e5e6824271b0427a7637019957c0e17277c3d260))

### Other

- Initial commit: SPEC-VENDOR-NODE-V1 to octos HTTP bridge ([05add1f](https://github.com/dorarobotics/octos-dora-bridge/commit/05add1fed643c67d982b7e68f1cf3b0047382293))
- Remove broken docs/ link from README ([d23e413](https://github.com/dorarobotics/octos-dora-bridge/commit/d23e413c745809bef2dd2b6809557091308e9182))
- So101 dataflow: 50 Hz trajectory executor for brisk viewer motion ([1adc451](https://github.com/dorarobotics/octos-dora-bridge/commit/1adc4511c3a79ee8c3aff1d8f48b8e9bd10baaa0))
- So101 dataflow: enable grasp weld on mujoco_sim ([7fa7c97](https://github.com/dorarobotics/octos-dora-bridge/commit/7fa7c97f10a9d7e7faf68e4bae6cffdd9570d7a2))
- Public-ready demo — portable launcher + quickstart + fix dataflow yaml ([a0eb081](https://github.com/dorarobotics/octos-dora-bridge/commit/a0eb081e20352b7645c65b08b9acf68c8255b956))
- Fix teardown to kill the real 'dora daemon'/'dora coordinator' ([dc1ac50](https://github.com/dorarobotics/octos-dora-bridge/commit/dc1ac504aceafe9260c422f505c60fa474055106))
- Kill real dora daemon/coordinator names in teardown ([921543c](https://github.com/dorarobotics/octos-dora-bridge/commit/921543c535570b848702ee00486fbfc03fdef74f))
- Default EXEC_INTERP_SPEED=0.5; poll-only dora up ([a1cbac6](https://github.com/dorarobotics/octos-dora-bridge/commit/a1cbac647b62c1a82fedea2ad2b4e0ee26f9ef2c))
- Add setup.sh + RUNNING_SO101 agent notes (octos_py vendored, no external clone) ([662d495](https://github.com/dorarobotics/octos-dora-bridge/commit/662d495f2d016be681f8b52f636f3f11edc138cd))
- Make so101/rebot runnable octos app-skills (manifest.json + main) ([cf039c7](https://github.com/dorarobotics/octos-dora-bridge/commit/cf039c779c7c041c4f3bf78037369345cf91a84e))
- Add 'Run it as an octos skill' section ([da7b498](https://github.com/dorarobotics/octos-dora-bridge/commit/da7b498b12966b49ef09b513366d2d3ddc950ce6))
- Add DEPLOYMENT.md: fresh-box install guide + validated findings ([2b0390f](https://github.com/dorarobotics/octos-dora-bridge/commit/2b0390ff2257d6d998da608f2dc6a2c3f63ae8b1))
- Make the SO-101 dora dataflow reproducible off-epyc + add isolated-daemon runner ([23151f2](https://github.com/dorarobotics/octos-dora-bridge/commit/23151f2b46f3b6e99da7407037b25dd3f531dba0))
- Fix rebot/ur5e dataflow node paths to the nested move_group_demo package dir ([1baacd6](https://github.com/dorarobotics/octos-dora-bridge/commit/1baacd6768089cf8cdb382ac2bc033fd55d191dc))
- Ur5e dataflow: disable nav base-spring + enable sim grasp weld ([b20b2f5](https://github.com/dorarobotics/octos-dora-bridge/commit/b20b2f5af1d6d51a9618ba384333c84523b5b54e))
- Enable GRASP_SNAP_AXIAL so the off-centre grasp places accurately ([ab25cf5](https://github.com/dorarobotics/octos-dora-bridge/commit/ab25cf50679a964077d14ebf3ec8ad32870929f7))
- Add stock-dora event shim + remote-desktop-safe matplotlib viewer ([56b4dcd](https://github.com/dorarobotics/octos-dora-bridge/commit/56b4dcdb09f65da97c58f0b7562583cdea6ad6a6))
- Add asus reference launcher for the visual nav-base demo ([e6ecebc](https://github.com/dorarobotics/octos-dora-bridge/commit/e6ecebca489d0ad6e6b4dda9da36c2f9310219f9))
- Allow dora-rs 0.3/0.4 (loosen pin to <0.5) ([438d55b](https://github.com/dorarobotics/octos-dora-bridge/commit/438d55badc75218e965c4ad58312a3130f63684b))
- Run-nav-viz.sh auto-delegates to the asus variant on the asus box ([5bdadab](https://github.com/dorarobotics/octos-dora-bridge/commit/5bdadab61b226f2526eae1fda70536138c87bd71))
- Dora 1.0-rc.1: unpin dora-rs, add from-source build harness + validation note ([72ca355](https://github.com/dorarobotics/octos-dora-bridge/commit/72ca355a1a08ebe0787292bf9efed66a7d3541d2))
- Dora 1.0.1: pin the formal release, drop the from-source rc.1 harness ([2754471](https://github.com/dorarobotics/octos-dora-bridge/commit/2754471c833d5be4b04fbdbb1931219252a1cc10))

### Refactoring

- Extract imperative arm skill code to the vendor node; keep bridge generic ([72905cd](https://github.com/dorarobotics/octos-dora-bridge/commit/72905cd46e6a1b84b13a9bd3708621b0e8153d30))

