import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../services/api_client.dart';
import '../state/report_store.dart';
import '../util/format.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import 'report_detail_screen.dart';

/// ③ 巡检报告:拉取后存本地缓存(可离线),长按可删除。
class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  Object? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    if (!appConfig.configured) return;
    try {
      final p = await apiClient.getReports(limit: 100);
      await reportStore.mergeList(p.items);
      _error = null;
    } catch (e) {
      _error = e; // 拉取失败保留本地缓存
    }
    if (mounted) setState(() {});
  }

  Future<void> _confirmDelete(int id, String title) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除报告'),
        content: Text('从本地删除「$title」?删除后不再显示。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFD63B3B)),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await reportStore.delete(id);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('已从本地删除')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return const EmptyState('未设置服务器地址,请到「设置」填写 Mac IP',
          icon: Icons.dns_outlined);
    }
    return ListenableBuilder(
      listenable: reportStore,
      builder: (context, _) {
        final items = reportStore.list;
        if (items.isEmpty) {
          return RefreshIndicator(
            onRefresh: _refresh,
            child: ListView(children: [
              SizedBox(
                height: MediaQuery.of(context).size.height * 0.5,
                child: EmptyState(
                    _error != null ? '暂无缓存,且拉取失败:$_error' : '暂无报告',
                    icon: _error != null
                        ? Icons.error_outline
                        : Icons.description_outlined),
              ),
            ]),
          );
        }
        return RefreshIndicator(
          onRefresh: _refresh,
          child: ListView(
            padding: const EdgeInsets.all(12),
            children: [
              if (_error != null)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('· 离线/拉取失败,显示本地缓存 ·',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.black45, fontSize: 12)),
                ),
              ...items.map((r) => Card(
                    child: InkWell(
                      borderRadius: BorderRadius.circular(12),
                      onTap: () => Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) =>
                              ReportDetailScreen(id: r.id, title: r.title))),
                      onLongPress: () => _confirmDelete(r.id, r.title),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(children: [
                              Expanded(
                                child: Text(r.title,
                                    style: const TextStyle(
                                        fontSize: 15,
                                        fontWeight: FontWeight.w700)),
                              ),
                              const SizedBox(width: 8),
                              VerdictBadge(r.verdict),
                            ]),
                            const SizedBox(height: 6),
                            Text(
                                '${r.typeLabel} · ${fmtIso(r.createdAt)} · ${r.eventIds.length} 个事件'
                                '${r.hasBody ? ' · 已缓存' : ''}',
                                style: const TextStyle(
                                    color: Colors.black54, fontSize: 13)),
                          ],
                        ),
                      ),
                    ),
                  )),
            ],
          ),
        );
      },
    );
  }
}
