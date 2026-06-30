import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/event.dart';
import '../state/alerts_controller.dart';
import '../util/format.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import '../widgets/evidence_image.dart';
import 'event_detail_screen.dart';

/// ① 实时安全告警：列表 + SSE 实时 + 证据图 + 处理。
class AlertsScreen extends StatelessWidget {
  const AlertsScreen({super.key, required this.controller});

  final AlertsController controller;

  static const _filters = [
    MapEntry(AlertFilter.all, '全部'),
    MapEntry(AlertFilter.critical, '严重'),
    MapEntry(AlertFilter.warning, '警告'),
  ];

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        if (!appConfig.configured) {
          return const EmptyState('未设置服务器地址，请到「设置」填写 Mac IP',
              icon: Icons.dns_outlined);
        }
        final items = controller.filtered;
        return Column(
          children: [
            const SizedBox(height: 8),
            FilterChips<AlertFilter>(
              options: _filters,
              selected: controller.filter,
              onSelected: controller.setFilter,
            ),
            const SizedBox(height: 4),
            Expanded(
              child: RefreshIndicator(
                onRefresh: controller.refresh,
                child: controller.loading && items.isEmpty
                    ? const Center(child: CircularProgressIndicator())
                    : items.isEmpty
                        ? ListView(children: [
                            SizedBox(
                                height:
                                    MediaQuery.of(context).size.height * 0.5,
                                child: EmptyState(
                                    controller.error != null
                                        ? '加载失败：${controller.error}'
                                        : '暂无告警',
                                    icon: controller.error != null
                                        ? Icons.error_outline
                                        : Icons.shield_outlined)),
                          ])
                        : ListView.builder(
                            padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
                            itemCount: items.length,
                            itemBuilder: (c, i) =>
                                _AlertCard(event: items[i], controller: controller),
                          ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _AlertCard extends StatelessWidget {
  const _AlertCard({required this.event, required this.controller});
  final Event event;
  final AlertsController controller;

  @override
  Widget build(BuildContext context) {
    final e = event;
    final expl = e.brief?.explanation ?? '';
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
          builder: (_) =>
              EventDetailScreen(eventId: e.eventId, controller: controller),
        )),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                SeverityBadge(e.finalSeverity),
                const Spacer(),
                Text('${e.stationId} · ${fmtIso(e.timestamp)}',
                    style:
                        const TextStyle(color: Colors.black54, fontSize: 13)),
              ]),
              const SizedBox(height: 8),
              Text(e.summary,
                  style: const TextStyle(
                      fontSize: 15, fontWeight: FontWeight.w600)),
              if (expl.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(expl,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style:
                        const TextStyle(color: Colors.black54, fontSize: 13)),
              ],
              if (e.image.isNotEmpty) ...[
                const SizedBox(height: 10),
                EvidenceImage(e.image, height: 160),
              ],
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: OutlinedButton(
                  onPressed: () => _handle(context),
                  child: const Text('处理'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handle(BuildContext context) async {
    final c = TextEditingController(text: '已处理');
    final note = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('处理备注'),
        content: TextField(
            controller: c,
            autofocus: true,
            decoration:
                const InputDecoration(hintText: '如：已断电并提醒学生处理')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, c.text.trim()),
              child: const Text('确认')),
        ],
      ),
    );
    if (note == null) return;
    try {
      await controller.handle(event.eventId, note);
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('已标记处理')));
      }
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('处理失败：$e')));
      }
    }
  }
}
