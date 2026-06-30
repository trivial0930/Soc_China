/// 遥控速度范围与摇杆→速度映射（纯函数，可单测）。
/// 范围与底盘限速一致（见 app/FRONTEND_PROMPT_teleop.md）。
library;

class TeleopLimits {
  static const double vxMax = 0.4; // m/s 前进/后退
  static const double vyMax = 0.4; // m/s 横移（麦轮，弱，默认关）
  static const double wzMax = 1.5; // rad/s 转向
}

double clampD(double v, double lo, double hi) =>
    v < lo ? lo : (v > hi ? hi : v);

/// 一帧遥控速度。`vx`/`vy` m/s，`wz` rad/s。
class TeleopVelocity {
  final double vx, vy, wz;
  const TeleopVelocity(this.vx, this.vy, this.wz);
  static const zero = TeleopVelocity(0, 0, 0);

  bool get isZero => vx == 0 && vy == 0 && wz == 0;

  Map<String, dynamic> toJson() => {'vx': vx, 'vy': vy, 'wz': wz};

  @override
  String toString() =>
      'vx=${vx.toStringAsFixed(2)} vy=${vy.toStringAsFixed(2)} wz=${wz.toStringAsFixed(2)}';
}

/// 摇杆归一化输入 → 速度。
/// `dx` 右为正、`dy` 上为正，均期望在 [-1,1]（越界会被夹住）。
/// - 上下 → vx（向上=前进）。
/// - strafe=false：左右 → wz（转向）；strafe=true：左右 → vy（横移），wz=0。
///
/// 约定：正 dx 映射为正 wz / 正 vy；左右转向的物理方向由底盘侧定义，
/// 如标定时方向反了，在此一处取负即可。
TeleopVelocity mapJoystick(double dx, double dy, {bool strafe = false}) {
  final cx = clampD(dx, -1, 1);
  final cy = clampD(dy, -1, 1);
  final vx = clampD(cy * TeleopLimits.vxMax, -TeleopLimits.vxMax, TeleopLimits.vxMax);
  if (strafe) {
    final vy = clampD(cx * TeleopLimits.vyMax, -TeleopLimits.vyMax, TeleopLimits.vyMax);
    return TeleopVelocity(vx, vy, 0);
  }
  final wz = clampD(cx * TeleopLimits.wzMax, -TeleopLimits.wzMax, TeleopLimits.wzMax);
  return TeleopVelocity(vx, 0, wz);
}
