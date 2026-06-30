import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../config/theme.dart';
import '../models/event.dart';
import '../state/alerts_controller.dart';
import '../util/format.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import 'event_detail_screen.dart';

/// ⑤ 历史：已处理告警（handled_at 30 天内），单行紧凑列表。
/// 单击看详情；长按可「删除（本地）」或「标记为未处理」移回告警。
/// 满保留期或被删除/移回的不再显示（仅 App 内隐藏，后端数据保留）。
class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key, required this.controller});

  final AlertsController controller;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        if (!appConfig.configured) {
          return const EmptyState('未设置服务器地址，请到「设置」填写 Mac IP',
              icon: Icons.dns_outlined);
        }
        final items = controller.history;
        if (items.isEmpty) {
          return RefreshIndicator(
            onRefresh: controller.refresh,
            child: ListView(children: [
              SizedBox(
                height: MediaQuery.of(context).size.height * 0.5,
                child: const EmptyState('暂无历史（已处理告警归到这里，保留 30 天）',
                    icon: Icons.history),
              ),
            ]),
          );
        }
        return RefreshIndicator(
          onRefresh: controller.refresh,
          child: ListView.separated(
            itemCount: items.length,
            separatorBuilder: (_, _) =>
                const Divider(height: 1, indent: 12, endIndent: 12),
            itemBuilder: (c, i) =>
                _HistoryRow(event: items[i], controller: controller),
          ),
        );
      },
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.event, required this.controller});
  final Event event;
  final AlertsController controller;

  void _openDetail(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(
      builder: (_) =>
          EventDetailScreen(eventId: event.eventId, controller: controller),
    ));
  }

  Future<void> _longPress(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    final action = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 6),
              child: Text(event.summary,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      color: Colors.black54, fontSize: 13)),
            ),
            ListTile(
              leading: const Icon(Icons.undo, color: AppColors.accent),
              title: const Text('标记为未处理（移回告警）'),
              onTap: () => Navigator.pop(ctx, 'reopen'),
            ),
            ListTile(
              leading: const Icon(Icons.delete_outline,
                  color: AppColors.critical),
              title: const Text('删除', style: TextStyle(color: AppColors.critical)),
              onTap: () => Navigator.pop(ctx, 'delete'),
            ),
          ],
        ),
      ),
    );
    if (action == 'delete') {
      await controller.deleteFromHistory(event.eventId);
      messenger.showSnackBar(SnackBar(
        content: const Text('已删除'),
        action: SnackBarAction(
          label: '撤销',
          onPressed: () => controller.undoDelete(event.eventId),
        ),
      ));
    } else if (action == 'reopen') {
      await controller.reopen(event.eventId);
      messenger.showSnackBar(
          const SnackBar(content: Text('已移回告警')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final e = event;
    final timeStr = fmtIso(e.handledAt != null && e.handledAt!.isNotEmpty
        ? e.handledAt
        : e.timestamp);
    return InkWell(
      onTap: () => _openDetail(context),
      onLongPress: () => _longPress(context),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        child: Row(
          children: [
            // 左：时间
            SizedBox(
              width: 84,
              child: Text(timeStr,
                  style: const TextStyle(
                      color: Colors.black54, fontSize: 12.5)),
            ),
            const SizedBox(width: 8),
            // 中：严重度
            SeverityBadge(e.finalSeverity),
            const SizedBox(width: 10),
            // 右：内容（单行，溢出省略号）
            Expanded(
              child: Text(e.summary,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 14)),
            ),
          ],
        ),
      ),
    );
  }
}
