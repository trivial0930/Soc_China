import 'package:flutter/material.dart';

/// 虚拟摇杆：拖动返回归一化 (dx, dy)，`dx` 右为正、`dy` 上为正，范围 [-1,1]。
/// 松手 / 取消 → 摇杆归中并回调 `onReleased`（遥控用它发零速度）。
///
/// 用 [resetToken] 强制归中：父级改变它（如点 STOP）即把摇杆拨回中心。
class Joystick extends StatefulWidget {
  const Joystick({
    super.key,
    required this.size,
    required this.onChanged,
    required this.onReleased,
    this.resetToken = 0,
    this.color,
  });

  final double size;
  final void Function(double dx, double dy) onChanged;
  final VoidCallback onReleased;
  final int resetToken;
  final Color? color;

  @override
  State<Joystick> createState() => _JoystickState();
}

class _JoystickState extends State<Joystick> {
  Offset _knob = Offset.zero; // 相对中心的像素偏移，限制在 _maxR 内

  double get _radius => widget.size / 2;
  double get _knobR => widget.size * 0.18;
  double get _maxR => _radius - _knobR;

  @override
  void didUpdateWidget(covariant Joystick old) {
    super.didUpdateWidget(old);
    if (old.resetToken != widget.resetToken && _knob != Offset.zero) {
      setState(() => _knob = Offset.zero);
    }
  }

  void _update(Offset local) {
    final center = Offset(_radius, _radius);
    var d = local - center;
    if (d.distance > _maxR) d = d / d.distance * _maxR;
    setState(() => _knob = d);
    final nx = _maxR == 0 ? 0.0 : d.dx / _maxR;
    final ny = _maxR == 0 ? 0.0 : d.dy / _maxR;
    widget.onChanged(nx, -ny); // 屏幕 y 向下为正 → 取反成“上正”
  }

  void _release() {
    setState(() => _knob = Offset.zero);
    widget.onReleased();
  }

  @override
  Widget build(BuildContext context) {
    final color = widget.color ?? Theme.of(context).colorScheme.primary;
    return GestureDetector(
      onPanStart: (d) => _update(d.localPosition),
      onPanUpdate: (d) => _update(d.localPosition),
      onPanEnd: (_) => _release(),
      onPanCancel: _release,
      child: CustomPaint(
        size: Size.square(widget.size),
        painter: _JoystickPainter(_knob, _knobR, color),
      ),
    );
  }
}

class _JoystickPainter extends CustomPainter {
  _JoystickPainter(this.knob, this.knobR, this.color);
  final Offset knob;
  final double knobR;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final r = size.width / 2 - 1;
    canvas.drawCircle(
        c, r, Paint()..color = color.withValues(alpha: 0.07));
    canvas.drawCircle(
        c,
        r,
        Paint()
          ..color = color.withValues(alpha: 0.35)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2);
    // 十字准星
    final ax = Paint()
      ..color = color.withValues(alpha: 0.15)
      ..strokeWidth = 1;
    canvas.drawLine(Offset(c.dx, 10), Offset(c.dx, size.height - 10), ax);
    canvas.drawLine(Offset(10, c.dy), Offset(size.width - 10, c.dy), ax);
    // 摇杆头
    canvas.drawCircle(c + knob, knobR, Paint()..color = color);
    canvas.drawCircle(
        c + knob,
        knobR,
        Paint()
          ..color = Colors.white.withValues(alpha: 0.9)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2);
  }

  @override
  bool shouldRepaint(_JoystickPainter old) =>
      old.knob != knob || old.color != color;
}
