import 'package:flutter_test/flutter_test.dart';
import 'package:lab_admin/util/teleop_math.dart';

void main() {
  group('mapJoystick 转向模式（默认）', () {
    test('满推向上 = 最大前进 vx，wz/vy 为 0', () {
      final v = mapJoystick(0, 1);
      expect(v.vx, TeleopLimits.vxMax);
      expect(v.wz, 0);
      expect(v.vy, 0);
    });

    test('满推向下 = 最大后退', () {
      expect(mapJoystick(0, -1).vx, -TeleopLimits.vxMax);
    });

    test('满推向右 = 最大转向 wz，vy 为 0', () {
      final v = mapJoystick(1, 0);
      expect(v.wz, TeleopLimits.wzMax);
      expect(v.vy, 0);
    });

    test('满推向左 = 反向转向', () {
      expect(mapJoystick(-1, 0).wz, -TeleopLimits.wzMax);
    });

    test('越界输入被夹在范围内', () {
      final v = mapJoystick(5, 5); // dx,dy 远超 1
      expect(v.vx, TeleopLimits.vxMax);
      expect(v.wz, TeleopLimits.wzMax);
      expect(v.vx <= TeleopLimits.vxMax, isTrue);
      expect(v.wz <= TeleopLimits.wzMax, isTrue);
    });

    test('居中 = 零速度', () {
      expect(mapJoystick(0, 0).isZero, isTrue);
    });

    test('半推线性缩放', () {
      final v = mapJoystick(0, 0.5);
      expect(v.vx, closeTo(TeleopLimits.vxMax * 0.5, 1e-9));
    });
  });

  group('mapJoystick 横移模式', () {
    test('开启横移：左右 → vy，wz 恒为 0', () {
      final v = mapJoystick(1, 0, strafe: true);
      expect(v.vy, TeleopLimits.vyMax);
      expect(v.wz, 0);
    });

    test('横移模式仍保留前后 vx', () {
      final v = mapJoystick(-1, 1, strafe: true);
      expect(v.vx, TeleopLimits.vxMax);
      expect(v.vy, -TeleopLimits.vyMax);
      expect(v.wz, 0);
    });
  });

  group('TeleopVelocity', () {
    test('zero.isZero 且 toJson 三字段齐全', () {
      expect(TeleopVelocity.zero.isZero, isTrue);
      expect(TeleopVelocity.zero.toJson(), {'vx': 0.0, 'vy': 0.0, 'wz': 0.0});
    });

    test('非零不是 isZero', () {
      expect(const TeleopVelocity(0.1, 0, 0).isZero, isFalse);
    });
  });
}
