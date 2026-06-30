import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/theme.dart';
import '../services/api_client.dart';
import '../services/command_client.dart';

/// 设置页：服务器地址 + 写接口 token，可配置（API_SPEC §8，演示现场 IP 会变）。
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.onChanged});

  /// 地址/token 变更后回调（触发告警重新初始化、SSE 重连）。
  final VoidCallback onChanged;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _base =
      TextEditingController(text: appConfig.baseUrl);
  late final TextEditingController _token =
      TextEditingController(text: appConfig.token);
  String? _checkMsg;
  bool? _checkOk;
  bool _checking = false;
  bool _voiceBusy = false;
  double? _volDrag; // 拖动中的临时音量值（释放后提交）

  @override
  void dispose() {
    _base.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await appConfig.setBaseUrl(_base.text);
    await appConfig.setToken(_token.text);
    _base.text = appConfig.baseUrl; // 回显归一化后的地址
    widget.onChanged();
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('已保存')));
    }
  }

  Future<void> _check() async {
    await _save();
    setState(() {
      _checking = true;
      _checkMsg = null;
    });
    try {
      final h = await apiClient.health();
      setState(() {
        _checkOk = true;
        _checkMsg = '连接成功：${h['status']} · ${h['version']}';
      });
    } catch (e) {
      setState(() {
        _checkOk = false;
        _checkMsg = '连接失败：$e';
      });
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  /// 远程开/关机器人语音：乐观更新本地状态 → 发 voice_control 命令 → 失败回滚。
  Future<void> _toggleVoice(bool want) async {
    setState(() => _voiceBusy = true);
    await appConfig.setVoiceEnabled(want); // 乐观更新（立即翻转开关）
    try {
      final r = await commandClient.send('voice_control', {'enabled': want});
      if (!mounted) return;
      if (r.outcome == CommandOutcome.queued) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(want ? '已开启机器人语音' : '已关闭机器人语音监听')));
      } else {
        await appConfig.setVoiceEnabled(!want); // 后端未支持 → 回滚
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('机器人暂不支持语音开关')));
        }
      }
    } on ApiException catch (e) {
      await appConfig.setVoiceEnabled(!want); // 失败 → 回滚
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(
                e.isAuth ? '需要 token，请在上方填写后重试' : '下发失败：${e.message}')));
      }
    } finally {
      if (mounted) setState(() => _voiceBusy = false);
    }
  }

  /// 调节机器人 TTS 播报音量:乐观更新本地值 → 发 set_volume 命令(滑块释放时调用)。
  Future<void> _commitVolume(int level) async {
    await appConfig.setTtsVolume(level); // 乐观更新（持久化 + notify）
    if (mounted) setState(() => _volDrag = null);
    try {
      final r = await commandClient.send('set_volume', {'level': level});
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(r.outcome == CommandOutcome.queued
              ? '播报音量已设为 $level'
              : '机器人暂不支持音量调节')));
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(
                e.isAuth ? '需要 token，请在上方填写后重试' : '下发失败：${e.message}')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('设置')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('服务器地址',
              style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          TextField(
            controller: _base,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              hintText: '如 192.168.1.10:8000 或 http://…:8000',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.dns_outlined),
            ),
          ),
          const SizedBox(height: 6),
          const Text('演示现场连同一热点，填 Mac 局域网 IP，端口 8000。',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 20),
          const Text('写接口 Token（可选）',
              style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          TextField(
            controller: _token,
            autocorrect: false,
            obscureText: false,
            decoration: const InputDecoration(
              hintText: '处理告警等写操作需要；后端未设则留空',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.key_outlined),
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _checking ? null : _check,
                  icon: _checking
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.wifi_tethering),
                  label: const Text('保存并测试连接'),
                ),
              ),
              const SizedBox(width: 12),
              OutlinedButton(onPressed: _save, child: const Text('保存')),
            ],
          ),
          if (_checkMsg != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: (_checkOk == true ? AppColors.ok : AppColors.critical)
                    .withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(_checkMsg!,
                  style: TextStyle(
                      color:
                          _checkOk == true ? AppColors.ok : AppColors.critical)),
            ),
          ],
          const SizedBox(height: 28),
          const Divider(height: 1),
          const SizedBox(height: 16),
          const Text('机器人语音',
              style: TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 6),
          ListenableBuilder(
            listenable: appConfig,
            builder: (_, _) => SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: appConfig.voiceEnabled,
              onChanged: _voiceBusy ? null : _toggleVoice,
              secondary: _voiceBusy
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.record_voice_over_outlined),
              title: const Text('唤醒词与语音交互'),
              subtitle: Text(appConfig.voiceEnabled
                  ? '机器人正在监听「小巡 / 巡检助手」'
                  : '已关闭：机器人停止唤醒监听与语音播报'),
            ),
          ),
          const Text('远程开关；机器人为权威源，此处显示上次设置值。',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 12),
          ListenableBuilder(
            listenable: appConfig,
            builder: (_, _) {
              final vol = _volDrag ?? appConfig.ttsVolume.toDouble();
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.volume_up_outlined,
                          color: Colors.black54),
                      const SizedBox(width: 8),
                      const Text('播报音量'),
                      const Spacer(),
                      Text('${vol.round()}',
                          style:
                              const TextStyle(fontWeight: FontWeight.w600)),
                    ],
                  ),
                  Slider(
                    value: vol.clamp(0, 100).toDouble(),
                    min: 0,
                    max: 100,
                    divisions: 20,
                    label: '${vol.round()}',
                    onChanged: (v) => setState(() => _volDrag = v),
                    onChangeEnd: (v) => _commitVolume(v.round()),
                  ),
                ],
              );
            },
          ),
          const Text('拖动调节机器人 TTS 播报音量(0 静音 ~ 100 最响),松手即下发。',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
        ],
      ),
    );
  }
}
