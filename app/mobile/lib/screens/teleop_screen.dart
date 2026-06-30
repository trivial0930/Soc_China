import 'dart:async';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/theme.dart';
import '../services/teleop_client.dart';
import '../util/teleop_math.dart';
import '../widgets/joystick.dart';

/// 遥控驾驶页：虚拟摇杆 ~10Hz 发速度 + ~3Hz 轮询雷达安全状态 + STOP 急停。
///
/// **安全底线 deadman**：松手 / 离页(dispose) / 切后台 / 触摸取消 → 立即发零并停发送循环，
/// 绝不让车卡着上一个速度继续跑。避障在机器人本地实时跑，这端只负责不“甩手不管”。
class TeleopScreen extends StatefulWidget {
  const TeleopScreen({super.key});

  @override
  State<TeleopScreen> createState() => _TeleopScreenState();
}

class _TeleopScreenState extends State<TeleopScreen>
    with WidgetsBindingObserver {
  static const _sendPeriod = Duration(milliseconds: 100); // 10Hz
  static const _statusPeriod = Duration(milliseconds: 333); // ~3Hz
  static const _staleMs = 1500.0; // 状态年龄超过此值视为失联（灰）

  TeleopVelocity _vel = TeleopVelocity.zero;
  bool _strafe = false;
  TeleopStatus _status = TeleopStatus.unknown;

  Timer? _sendTimer;
  Timer? _statusTimer;
  bool _sending = false; // 防止慢网络下 tick 堆积
  int _resetToken = 0; // STOP 时 +1，强制摇杆归中

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _statusTimer = Timer.periodic(_statusPeriod, (_) => _pollStatus());
    _pollStatus();
  }

  @override
  void dispose() {
    // deadman：离开本页务必发零（fire-and-forget，teleopClient 是单例，dispose 后仍能完成）。
    _sendTimer?.cancel();
    _statusTimer?.cancel();
    _sendZeroBurst();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // 切后台 / 不活跃 / 被遮挡 → deadman。
    if (state != AppLifecycleState.resumed) {
      _stopDriving(sendZero: true);
    }
  }

  // ---- 发送循环 ----
  void _ensureSendLoop() {
    _sendTimer ??= Timer.periodic(_sendPeriod, (_) => _tickSend());
  }

  void _tickSend() {
    if (_sending) return; // 上一帧还没回来，跳过，下一 tick 发最新值
    _sending = true;
    teleopClient
        .sendVelocity(_vel)
        .catchError((_) {/* 单次失败忽略，继续下一 tick */})
        .whenComplete(() => _sending = false);
  }

  /// 立即发若干次零（deadman 用，多发几次抗丢包）。
  void _sendZeroBurst() {
    for (var i = 0; i < 3; i++) {
      teleopClient.sendVelocity(TeleopVelocity.zero).catchError((_) {});
    }
  }

  void _stopDriving({required bool sendZero}) {
    _sendTimer?.cancel();
    _sendTimer = null;
    if (mounted) setState(() => _vel = TeleopVelocity.zero);
    if (sendZero) _sendZeroBurst();
  }

  // ---- 摇杆回调 ----
  void _onJoyChanged(double dx, double dy) {
    setState(() => _vel = mapJoystick(dx, dy, strafe: _strafe));
    _ensureSendLoop();
  }

  void _onJoyReleased() => _stopDriving(sendZero: true);

  void _stop() {
    _stopDriving(sendZero: true);
    setState(() => _resetToken++); // 摇杆拨回中心
  }

  // ---- 状态轮询 ----
  Future<void> _pollStatus() async {
    final s = await teleopClient.getStatus();
    if (mounted) setState(() => _status = s);
  }

  // ---- 显示辅助 ----
  bool get _stale =>
      _status.state == 'unknown' || _status.ageMs > _staleMs;

  Color get _statusColor {
    if (_stale) return AppColors.info;
    switch (_status.state) {
      case 'clear':
        return AppColors.ok;
      case 'slow':
        return AppColors.warning;
      case 'blocked':
        return AppColors.critical;
      default:
        return AppColors.info;
    }
  }

  String get _statusLabel {
    if (_stale) return '状态未知 / 失联';
    switch (_status.state) {
      case 'clear':
        return '前方畅通';
      case 'slow':
        return '前方接近障碍，已减速';
      case 'blocked':
        return '前方受阻，已自动停';
      default:
        return '状态未知';
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return Scaffold(
        appBar: AppBar(title: const Text('遥控驾驶')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text('未设置服务器地址，请到「设置」填写后再遥控。',
                textAlign: TextAlign.center),
          ),
        ),
      );
    }
    final noToken = appConfig.token.isEmpty;
    return Scaffold(
      appBar: AppBar(title: const Text('遥控驾驶')),
      body: SafeArea(
        child: Column(
          children: [
            _statusBar(),
            if (noToken)
              Container(
                width: double.infinity,
                color: AppColors.warning.withValues(alpha: 0.12),
                padding: const EdgeInsets.all(10),
                child: Text('遥控为写操作，需先到「设置」填 token，否则机器人不接受指令。',
                    style: TextStyle(color: AppColors.warning, fontSize: 13)),
              ),
            Expanded(child: _controls()),
          ],
        ),
      ),
    );
  }

  Widget _statusBar() {
    final dist = _status.frontDistM;
    return Container(
      width: double.infinity,
      color: _statusColor,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Icon(
            _stale
                ? Icons.help_outline
                : (_status.state == 'blocked'
                    ? Icons.block
                    : (_status.state == 'slow'
                        ? Icons.warning_amber_rounded
                        : Icons.check_circle_outline)),
            color: Colors.white,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(_statusLabel,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w700)),
          ),
          Text(
            dist == null ? '前方 —' : '前方 ${dist.toStringAsFixed(2)} m',
            style: const TextStyle(color: Colors.white),
          ),
        ],
      ),
    );
  }

  Widget _controls() {
    return LayoutBuilder(
      builder: (context, box) {
        final joySize =
            (box.maxWidth < box.maxHeight ? box.maxWidth : box.maxHeight) * 0.62;
        return Column(
          children: [
            const SizedBox(height: 8),
            // 当前速度读数
            Text(
              _strafe
                  ? 'vx ${_vel.vx.toStringAsFixed(2)} m/s   vy ${_vel.vy.toStringAsFixed(2)} m/s'
                  : 'vx ${_vel.vx.toStringAsFixed(2)} m/s   wz ${_vel.wz.toStringAsFixed(2)} rad/s',
              style: const TextStyle(
                  fontFeatures: [], color: Colors.black54, fontSize: 13),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Center(
                child: Joystick(
                  size: joySize.clamp(180.0, 360.0),
                  resetToken: _resetToken,
                  color: AppColors.accent,
                  onChanged: _onJoyChanged,
                  onReleased: _onJoyReleased,
                ),
              ),
            ),
            SwitchListTile(
              dense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 24),
              value: _strafe,
              onChanged: (v) {
                // 切模式即归零，避免残留上一模式的 vy/wz。
                _stopDriving(sendZero: true);
                setState(() {
                  _strafe = v;
                  _resetToken++;
                });
              },
              title: const Text('横移模式（左右平移）'),
              subtitle: const Text('关：左右=转向；开：左右=横移（麦轮较弱）'),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              child: SizedBox(
                width: double.infinity,
                height: 64,
                child: FilledButton.icon(
                  style: FilledButton.styleFrom(
                      backgroundColor: AppColors.critical),
                  onPressed: _stop,
                  icon: const Icon(Icons.pan_tool, size: 26),
                  label: const Text('急停 STOP',
                      style: TextStyle(
                          fontSize: 20, fontWeight: FontWeight.w800)),
                ),
              ),
            ),
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text('松手即停；离开本页 / 切后台会自动发零。避障在机器人本地实时运行。',
                  style: TextStyle(color: Colors.black45, fontSize: 12)),
            ),
          ],
        );
      },
    );
  }
}
