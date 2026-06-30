import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/theme.dart';
import '../models/asset.dart';
import '../models/report.dart';
import '../services/api_client.dart';
import '../services/command_client.dart';
import '../widgets/common.dart';
import 'teleop_screen.dart';

/// ④ 操作：从 App 主动下发机器人动作（命令走 POST /api/commands，
/// 见 app/BACKEND_PROMPT_command_api.md）。后端未实现时按钮优雅提示"待支持"。
class OperationsScreen extends StatelessWidget {
  const OperationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return const EmptyState('未设置服务器地址，请到「设置」填写 Mac IP',
          icon: Icons.dns_outlined);
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        _section('遥控驾驶', Icons.sports_esports_outlined, [
          _ActionTile(
            icon: Icons.gamepad_outlined,
            title: '虚拟摇杆开车',
            subtitle: '摇杆遥控 + 雷达避障状态；松手即停',
            onTap: (c) => Navigator.of(c).push(
                MaterialPageRoute(builder: (_) => const TeleopScreen())),
          ),
        ]),
        _section('巡检 / 复核', Icons.travel_explore, [
          _ActionTile(
            icon: Icons.radar,
            title: '发起综合巡检',
            subtitle: '机器人对各工位走一圈',
            onTap: (c) => _run(c, '综合巡检', 'inspection_round'),
          ),
          _ActionTile(
            icon: Icons.my_location,
            title: '到指定工位复核',
            subtitle: '派机器人导航到工位近距复核',
            onTap: (c) => _withStation(c, '到点复核',
                (s) => _run(c, '复核 $s', 'recheck_station', {'station_id': s})),
          ),
        ]),
        _section('课后验收', Icons.fact_check_outlined, [
          _ActionTile(
            icon: Icons.checklist,
            title: '全部工位验收',
            subtitle: '依次验收所有工位',
            onTap: (c) => _run(c, '全部验收', 'acceptance'),
          ),
          _ActionTile(
            icon: Icons.rule,
            title: '指定工位验收',
            onTap: (c) => _withStation(c, '指定工位验收',
                (s) => _run(c, '验收 $s', 'acceptance', {'station_id': s})),
          ),
        ]),
        _section('寻找物品', Icons.search, [
          _ActionTile(
            icon: Icons.travel_explore,
            title: '查物资并带路 / 激光指示',
            subtitle: '查位置(现成)＋让机器人导航或激光指示',
            onTap: (c) => Navigator.of(c).push(
                MaterialPageRoute(builder: (_) => const FindItemScreen())),
          ),
        ]),
        _section('辅助动作', Icons.build_outlined, [
          _ActionTile(
            icon: Icons.campaign_outlined,
            title: '语音提醒',
            onTap: _voiceDialog,
          ),
          _ActionTile(
            icon: Icons.highlight,
            title: '激光指示',
            onTap: (c) => _withStation(c, '激光指示',
                (s) => _run(c, '激光指示 $s', 'laser_point', {'station_id': s})),
          ),
          _ActionTile(
            icon: Icons.summarize_outlined,
            title: '生成巡检报告',
            onTap: _reportDialog,
          ),
        ]),
        const SizedBox(height: 8),
        const Padding(
          padding: EdgeInsets.all(12),
          child: Text(
              '提示：命令通过 POST /api/commands 下发。后端命令通道尚在对接中（见 INTEGRATION），'
              '未实现时会提示"待支持"，不影响其它功能。',
              style: TextStyle(color: Colors.black45, fontSize: 12)),
        ),
      ],
    );
  }

  Widget _section(String title, IconData icon, List<Widget> children) => Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
                child: Row(children: [
                  Icon(icon, size: 18, color: AppColors.accent),
                  const SizedBox(width: 8),
                  Text(title,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 15)),
                ]),
              ),
              ...children,
            ],
          ),
        ),
      );
}

/// 执行命令 + SnackBar 反馈（顶层复用）。
Future<void> _run(BuildContext context, String label, String type,
    [Map<String, dynamic> params = const {}]) async {
  final messenger = ScaffoldMessenger.of(context);
  try {
    final r = await commandClient.send(type, params);
    final msg = r.outcome == CommandOutcome.queued
        ? '$label：已下发${r.commandId != null ? '（${r.commandId}）' : ''}'
        : '$label：后端暂未支持该命令（待落地）';
    messenger.showSnackBar(SnackBar(content: Text(msg)));
  } on ApiException catch (e) {
    final msg = e.isAuth
        ? '$label 失败：需要 token，请到「设置」填写写接口 token'
        : '$label 失败：${e.message}';
    messenger.showSnackBar(SnackBar(content: Text(msg)));
  } catch (e) {
    messenger.showSnackBar(SnackBar(content: Text('$label 失败：$e')));
  }
}

/// 弹窗输入工位号后执行。
Future<void> _withStation(
    BuildContext context, String title, Future<void> Function(String) onOk) async {
  final c = TextEditingController();
  final s = await showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: c,
        autofocus: true,
        decoration: const InputDecoration(
            labelText: '工位号', hintText: '如 desk-03'),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, c.text.trim()),
            child: const Text('下发')),
      ],
    ),
  );
  if (s != null && s.isNotEmpty) await onOk(s);
}

Future<void> _voiceDialog(BuildContext context) async {
  final station = TextEditingController();
  final text = TextEditingController(text: '请整理实验桌');
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('语音提醒'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: station,
            decoration: const InputDecoration(
                labelText: '工位号（可空=就地播报）', hintText: 'desk-03'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: text,
            decoration: const InputDecoration(labelText: '播报内容'),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
        FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('下发')),
      ],
    ),
  );
  if (ok == true && text.text.trim().isNotEmpty && context.mounted) {
    await _run(context, '语音提醒', 'voice_prompt', {
      if (station.text.trim().isNotEmpty) 'station_id': station.text.trim(),
      'text': text.text.trim(),
    });
  }
}

Future<void> _reportDialog(BuildContext context) async {
  final type = await showDialog<String>(
    context: context,
    builder: (ctx) => SimpleDialog(
      title: const Text('生成巡检报告'),
      children: Report.typeLabels.entries
          .map((e) => SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, e.key),
                child: Text(e.value),
              ))
          .toList(),
    ),
  );
  if (type != null && context.mounted) {
    await _run(context, '生成报告', 'generate_report', {'report_type': type});
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.icon,
    required this.title,
    this.subtitle,
    required this.onTap,
  });
  final IconData icon;
  final String title;
  final String? subtitle;
  final Future<void> Function(BuildContext) onTap;

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon, color: AppColors.accent),
        title: Text(title),
        subtitle: subtitle != null ? Text(subtitle!) : null,
        trailing: const Icon(Icons.chevron_right, color: Colors.black26),
        onTap: () => onTap(context),
      );
}

// ====================== 寻找物品子屏 ======================
class FindItemScreen extends StatefulWidget {
  const FindItemScreen({super.key});
  @override
  State<FindItemScreen> createState() => _FindItemScreenState();
}

class _FindItemScreenState extends State<FindItemScreen> {
  final _q = TextEditingController();
  String _cat = '';
  Future<List<Asset>>? _future;

  static const _cats = [
    MapEntry('', '全部'),
    MapEntry('large', '大型设备'),
    MapEntry('small', '小型耗材'),
  ];

  void _search() {
    setState(() {
      _future = apiClient
          .getAssets(
            name: _q.text.trim().isEmpty ? null : _q.text.trim(),
            category: _cat.isEmpty ? null : _cat,
            limit: 100,
          )
          .then((p) => p.items);
    });
  }

  @override
  void dispose() {
    _q.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('寻找物品')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _q,
                  textInputAction: TextInputAction.search,
                  onSubmitted: (_) => _search(),
                  decoration: const InputDecoration(
                    hintText: '搜设备/耗材名，如 示波器、电阻',
                    isDense: true,
                    border: OutlineInputBorder(),
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(onPressed: _search, child: const Text('查询')),
            ]),
          ),
          FilterChips<String>(
            options: _cats,
            selected: _cat,
            onSelected: (c) {
              _cat = c;
              _search();
            },
          ),
          const SizedBox(height: 4),
          Expanded(
            child: _future == null
                ? const EmptyState('查询后可让机器人导航带路 / 激光指示',
                    icon: Icons.inventory_2_outlined)
                : FutureBuilder<List<Asset>>(
                    future: _future,
                    builder: (c, snap) {
                      if (snap.connectionState == ConnectionState.waiting) {
                        return const Center(child: CircularProgressIndicator());
                      }
                      if (snap.hasError) {
                        return EmptyState('查询失败：${snap.error}',
                            icon: Icons.error_outline);
                      }
                      final items = snap.data ?? [];
                      if (items.isEmpty) {
                        return const EmptyState('未找到物资', icon: Icons.search_off);
                      }
                      return ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: items.length,
                        itemBuilder: (c, i) => _assetCard(context, items[i]),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _assetCard(BuildContext context, Asset a) => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Expanded(
                  child: Text(a.name,
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: a.isLarge ? AppColors.info : AppColors.ok,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(a.isLarge ? '设备' : '耗材',
                      style: const TextStyle(color: Colors.white, fontSize: 12)),
                ),
              ]),
              const SizedBox(height: 6),
              Row(children: [
                const Icon(Icons.place_outlined, size: 16, color: Colors.black45),
                const SizedBox(width: 4),
                Expanded(child: Text(a.locationText)),
                if (a.quantity > 0)
                  Text('×${a.quantity}',
                      style: const TextStyle(color: Colors.black54)),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                OutlinedButton.icon(
                  onPressed: () => _run(context, '导航带路', 'find_item',
                      {'asset_id': a.id, 'name': a.name, 'mode': 'navigate'}),
                  icon: const Icon(Icons.navigation_outlined, size: 16),
                  label: const Text('导航带路'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: () => _run(context, '激光指示', 'find_item',
                      {'asset_id': a.id, 'name': a.name, 'mode': 'laser'}),
                  icon: const Icon(Icons.highlight, size: 16),
                  label: const Text('激光指示'),
                ),
              ]),
            ],
          ),
        ),
      );
}
