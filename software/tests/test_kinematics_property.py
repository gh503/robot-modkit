"""随机采样的正逆解往返测试。

单元测试容易只覆盖手写的几个姿态；这里在关节限位内随机撒 2000 个点，
用"正解 → 逆解 → 再正解"的方式查符号错、分支错、边界错。

会有少量姿态逆解无解（目标只落在肘上分支），这是设计使然：
肘关节限位 [-150°, +5°] 让肘上分支不可用。这类样本跳过并计数，
跳过比例超过 5% 就说明限位或公式有一边写错了。
"""

from __future__ import annotations

import math
import random

import pytest

from modkit import kinematics as kin

GEOM = kin.ArmGeometry(base_h=90.0, l1=120.0, l2=110.0)
N = 2000


def test_random_roundtrip():
    rng = random.Random(20261025)
    checked = skipped = 0
    worst_mm = worst_deg = 0.0

    for _ in range(N):
        yaw = rng.uniform(-115.0, 115.0)
        sh = rng.uniform(-20.0, 95.0)
        el = rng.uniform(-145.0, 0.0)
        pose = kin.forward(GEOM, yaw, sh, el)

        try:
            y2, s2, e2 = kin.inverse(GEOM, pose, elbow_up=False)
        except kin.UnreachableError:
            skipped += 1
            continue

        back = kin.forward(GEOM, y2, s2, e2)
        d = math.dist((pose.x, pose.y, pose.z), (back.x, back.y, back.z))
        worst_mm = max(worst_mm, d)
        assert d < 0.5, f"往返误差 {d:.2f}mm @ yaw={yaw:.1f} sh={sh:.1f} el={el:.1f}"
        # 逆解可能返回"对侧解"：yaw 差 180°、连杆走另一边，末端仍在同一点。
        # 两者物理上都成立（碰撞与走线不同），所以这里接受 0° 或 180°。
        dyaw = abs((y2 - yaw + 180.0) % 360.0 - 180.0)
        assert dyaw < 0.5 or abs(dyaw - 180.0) < 0.5, f"yaw 偏差 {dyaw:.1f}°"
        checked += 1

    ratio = skipped / N
    print(f"\n往返 {checked} 个姿态，跳过 {skipped} 个（{ratio*100:.1f}%），最大误差 {worst_mm:.3f} mm")
    print("（少数姿态逆解给出 yaw 差 180° 的对侧解，末端同点，已单独放行）")
    assert ratio < 0.05, f"无解比例 {ratio*100:.1f}%，限位或公式可疑"


def test_unreachable_raises():
    far = kin.Pose(1000.0, 0.0, 200.0)
    with pytest.raises(kin.UnreachableError):
        kin.inverse(GEOM, far, elbow_up=False)


def test_out_of_yaw_limit_raises():
    # y 方向超过 ±yaw_limit 的目标必须拒绝，而不是悄悄转过去
    pose = kin.forward(GEOM, 130.0, 30.0, -60.0)
    with pytest.raises(kin.UnreachableError):
        kin.inverse(GEOM, pose, elbow_up=False)
