import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../config/theme.dart';
import '../models/event.dart';
import '../state/alerts_controller.dart';
import '../widgets/common.dart';
import 'alerts_screen.dart';
import 'history_screen.dart';
import 'operations_screen.dart';
import 'reports_screen.dart';
import 'settings_screen.dart';
import 'stations_screen.dart';

/// 主壳：底部五 Tab + 顶栏连接点/设置 + critical 实时横幅。
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.controller});
  final AlertsController controller;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _titles = ['实时告警', '工位 / 验收', '巡检报告', '操作', '历史告警'];

  @override
  void initState() {
    super.initState();
    widget.controller.onCritical = _onCritical;
  }

  void _onCritical(Event e) {
    if (!mounted) return;
    HapticFeedback.heavyImpact();
    final messenger = ScaffoldMessenger.of(context);
    messenger.clearMaterialBanners();
    messenger.showMaterialBanner(
      MaterialBanner(
        backgroundColor: AppColors.critical,
        content: Text('严重告警 · ${e.stationId}\n${e.summary}',
            style: const TextStyle(color: Colors.white)),
        leading: const Icon(Icons.warning_amber_rounded, color: Colors.white),
        actions: [
          TextButton(
            onPressed: () {
              messenger.hideCurrentMaterialBanner();
              setState(() => _index = 0);
            },
            child: const Text('查看', style: TextStyle(color: Colors.white)),
          ),
          TextButton(
            onPressed: messenger.hideCurrentMaterialBanner,
            child: const Text('忽略', style: TextStyle(color: Colors.white70)),
          ),
        ],
      ),
    );
  }

  void _reinit() => widget.controller.init();

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final pages = [
      AlertsScreen(controller: c),
      const StationsScreen(),
      const ReportsScreen(),
      const OperationsScreen(),
      HistoryScreen(controller: c),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_index]),
        actions: [
          // 连接状态点（仅告警 Tab 有 SSE 意义，但全局展示）
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: ListenableBuilder(
              listenable: c,
              builder: (_, _) => Center(
                child: Tooltip(
                  message: c.connected ? 'SSE 已连接' : '未连接 / 轮询中',
                  child: ConnectionDot(c.connected),
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => SettingsScreen(onChanged: _reinit),
            )),
          ),
        ],
      ),
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: ListenableBuilder(
        listenable: c,
        builder: (_, _) => NavigationBar(
          selectedIndex: _index,
          onDestinationSelected: (i) => setState(() => _index = i),
          destinations: [
            NavigationDestination(
              icon: _badged(const Icon(Icons.warning_amber_outlined),
                  c.badgeCount),
              selectedIcon:
                  _badged(const Icon(Icons.warning_amber), c.badgeCount),
              label: '告警',
            ),
            const NavigationDestination(
                icon: Icon(Icons.groups_outlined), label: '工位'),
            const NavigationDestination(
                icon: Icon(Icons.description_outlined), label: '报告'),
            const NavigationDestination(
                icon: Icon(Icons.handyman_outlined),
                selectedIcon: Icon(Icons.handyman),
                label: '操作'),
            const NavigationDestination(
                icon: Icon(Icons.history), label: '历史'),
          ],
        ),
      ),
    );
  }

  Widget _badged(Widget icon, int count) {
    if (count <= 0) return icon;
    return Badge(label: Text('$count'), child: icon);
  }
}
