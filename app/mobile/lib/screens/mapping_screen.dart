import 'dart:async';

import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/theme.dart';
import '../services/api_client.dart' show ApiException;
import '../services/command_client.dart';
import '../services/mapping_client.dart';
import '../util/mapping_util.dart';
import '../widgets/teleop_control.dart';

/// 建图模式页：开关一键进/退建图（机器人腾资源 + 起建图栈）。
/// 开关态**以 GET /api/robot/mode 回报的真实 mode 为准**（~2s 轮询），前端不臆测。
/// 建图中露出遥控摇杆开车绕图 + 一键存图。
class MappingScreen extends StatefulWidget {
  const MappingScreen({super.key});

  @override
  State<MappingScreen> createState() => _MappingScreenState();
}

class _MappingScreenState extends State<MappingScreen> {
  static const _pollPeriod = Duration(seconds: 2);
  static const _resendAfter = Duration(seconds: 10);

  RobotMode _mode = RobotMode.offline;
  Timer? _poll;
  bool _switchBusy = false; // 下发 set_mode 到 RDK 报 switching 之间的短暂窗口

  // 自动重发一次：请求了某模式但持续没到位
  String? _pendingMode;
  DateTime? _pendingAt;
  bool _resent = false;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(_pollPeriod, (_) => _refresh());
    _refresh();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    final m = await mappingClient.getMode();
    if (!mounted) return;
    setState(() => _mode = m);
    _maybeResend(m);
  }

  void _maybeResend(RobotMode m) {
    final p = _pendingMode;
    if (p == null || _pendingAt == null) return;
    if (m.mode == p) {
      _pendingMode = null; // 已到位
      return;
    }
    // 仅在“稳定但不一致”时重发一次；切换中/离线/错误不动。
    if (!_resent &&
        m.mode != 'switching' &&
        m.mode != 'offline' &&
        m.mode != 'mapping_error' &&
        DateTime.now().difference(_pendingAt!) > _resendAfter) {
      _resent = true;
      commandClient
          .sendAndAwait('set_mode', {'mode': p})
          .then((rec) {
            if (mounted && rec != null && rec.result.isNotEmpty) _toast(rec.result);
          })
          .catchError((_) {});
    }
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  void _onSwitch(bool on) => _sendMode(on ? 'mapping' : 'normal');

  Future<void> _sendMode(String target) async {
    setState(() {
      _switchBusy = true;
      _pendingMode = target;
      _pendingAt = DateTime.now();
      _resent = false;
    });
    CommandReceipt? rec;
    try {
      rec = await commandClient
          .sendAndAwait('set_mode', {'mode': target}, timeout: const Duration(seconds: 35));
    } on ApiException catch (e) {
      _toast(e.isAuth ? '需要 token，请到「设置」填写后重试' : '切换失败：${e.message}');
      return;
    } finally {
      if (mounted) setState(() => _switchBusy = false);
    }
    if (rec != null) {
      _toast(rec.result.isNotEmpty ? rec.result : (rec.isDone ? '已切换' : '切换失败'));
    }
    // rec==null（超时）不弹：mode 轮询会反映真实态。
  }

  Future<void> _saveMap() async {
    final ctrl = TextEditingController(text: kDefaultMapName);
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('存图'),
        content: TextField(
          controller: ctrl,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: '地图名',
            hintText: 'lab_map（字母数字/下划线/连字符）',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, ctrl.text),
              child: const Text('存图')),
        ],
      ),
    );
    if (name == null) return;
    final clean = sanitizeMapName(name);
    CommandReceipt? rec;
    try {
      rec = await commandClient
          .sendAndAwait('save_map', {'name': clean}, timeout: const Duration(seconds: 25));
    } on ApiException catch (e) {
      _toast(e.isAuth ? '需要 token，请到「设置」填写后重试' : '存图失败：${e.message}');
      return;
    }
    if (rec != null) {
      _toast(rec.result.isNotEmpty
          ? rec.result
          : (rec.isDone ? '已存图：$clean' : '存图失败'));
    } else {
      _toast('存图已下发：$clean（结果稍后确认）');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return Scaffold(
        appBar: AppBar(title: const Text('建图模式')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text('未设置服务器地址，请到「设置」填写后再使用建图模式。',
                textAlign: TextAlign.center),
          ),
        ),
      );
    }
    final ui = mappingUiOf(_mode.mode, _mode.ageMs);
    return Scaffold(
      appBar: AppBar(title: const Text('建图模式')),
      body: SafeArea(
        child: Column(
          children: [
            _header(ui),
            if (ui == MappingUi.mapping) ...[
              const Expanded(child: TeleopControlPanel()),
              _saveBar(),
            ] else
              Expanded(child: _placeholder(ui)),
          ],
        ),
      ),
    );
  }

  Widget _header(MappingUi ui) {
    if (ui == MappingUi.error) {
      return Container(
        width: double.infinity,
        color: AppColors.critical.withValues(alpha: 0.12),
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.error_outline, color: AppColors.critical),
              const SizedBox(width: 8),
              Expanded(
                child: Text('进入建图失败，已停在安全态',
                    style: TextStyle(
                        color: AppColors.critical, fontWeight: FontWeight.w700)),
              ),
            ]),
            const SizedBox(height: 8),
            Row(children: [
              FilledButton.icon(
                onPressed: _switchBusy ? null : () => _sendMode('mapping'),
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('重试'),
              ),
              const SizedBox(width: 10),
              OutlinedButton.icon(
                onPressed: _switchBusy ? null : () => _sendMode('normal'),
                icon: const Icon(Icons.logout, size: 18),
                label: const Text('退出（恢复语音）'),
              ),
            ]),
          ],
        ),
      );
    }

    final offline = ui == MappingUi.offline;
    final switching = ui == MappingUi.switching;
    final mapping = ui == MappingUi.mapping;
    final enabled = (ui == MappingUi.normal || mapping) && !_switchBusy;

    final String subtitle;
    if (offline) {
      subtitle = '机器人离线（检查网络 / 机器人是否在线）';
    } else if (switching) {
      subtitle = '切换中…（起建图栈 + 校验，约十几秒）';
    } else if (mapping) {
      subtitle = '建图中：可遥控开车绕图，完成后点存图';
    } else {
      subtitle = '打开后机器人停语音栈腾资源并启动建图栈（约十几秒）';
    }

    return Container(
      color: mapping ? AppColors.ok.withValues(alpha: 0.10) : null,
      child: SwitchListTile(
        value: mapping,
        onChanged: enabled ? _onSwitch : null,
        secondary: (switching || _switchBusy)
            ? const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2))
            : Icon(
                offline
                    ? Icons.cloud_off
                    : (mapping ? Icons.map : Icons.map_outlined),
                color: offline
                    ? Colors.black38
                    : (mapping ? AppColors.ok : AppColors.accent),
              ),
        title: Text(
          offline
              ? '机器人离线'
              : (mapping ? '建图中' : (switching ? '切换中…' : '建图模式')),
          style: TextStyle(
              fontWeight: FontWeight.w700,
              color: mapping ? AppColors.ok : null),
        ),
        subtitle: Text(subtitle),
      ),
    );
  }

  Widget _saveBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: SizedBox(
        width: double.infinity,
        height: 52,
        child: FilledButton.icon(
          onPressed: _saveMap,
          icon: const Icon(Icons.save_alt),
          label: const Text('存图', style: TextStyle(fontSize: 16)),
        ),
      ),
    );
  }

  Widget _placeholder(MappingUi ui) {
    final IconData icon;
    final String text;
    switch (ui) {
      case MappingUi.offline:
        icon = Icons.cloud_off;
        text = '机器人离线，无法进入建图模式。';
        break;
      case MappingUi.switching:
        icon = Icons.sync;
        text = '正在切换模式，请稍候…';
        break;
      default: // normal
        icon = Icons.map_outlined;
        text = '打开上方开关进入建图模式，即可遥控开车建图。';
    }
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: Colors.black26),
            const SizedBox(height: 12),
            Text(text,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.black54)),
          ],
        ),
      ),
    );
  }
}
