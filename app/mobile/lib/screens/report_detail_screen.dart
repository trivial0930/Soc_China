import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../models/report.dart';
import '../services/api_client.dart';
import '../state/report_store.dart';
import '../widgets/common.dart';

/// 报告详情(API_SPEC §4.3 GET /api/reports/{id}):优先本地缓存正文(离线可读),
/// 同时后台拉取最新并回写缓存。
class ReportDetailScreen extends StatefulWidget {
  const ReportDetailScreen({super.key, required this.id, required this.title});
  final int id;
  final String title;

  @override
  State<ReportDetailScreen> createState() => _ReportDetailScreenState();
}

class _ReportDetailScreenState extends State<ReportDetailScreen> {
  Report? _report;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    // 1) 先用本地缓存(若有正文)立即显示。
    final cached = reportStore.get(widget.id);
    if (cached != null && cached.hasBody) {
      _report = cached;
      _loading = false;
    }
    if (mounted) setState(() {});
    // 2) 后台拉最新正文并回写缓存。
    try {
      final fresh = await apiClient.getReport(widget.id);
      await reportStore.upsertDetail(fresh);
      if (mounted) {
        setState(() {
          _report = fresh;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && _report == null) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: _report != null
          ? Markdown(
              data: _report!.bodyMarkdown.isEmpty
                  ? '(报告无正文)'
                  : _report!.bodyMarkdown,
              padding: const EdgeInsets.all(16),
              selectable: true,
            )
          : _loading
              ? const Center(child: CircularProgressIndicator())
              : EmptyState('加载失败:$_error', icon: Icons.error_outline),
    );
  }
}
