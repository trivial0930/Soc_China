import 'package:flutter/material.dart';

import '../config/theme.dart';
import '../models/event.dart';
import '../services/api_client.dart';
import '../state/alerts_controller.dart';
import '../util/format.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import '../widgets/evidence_image.dart';

/// 告警详情：拉 GET /api/events/{id}（带 brief），可处理。
class EventDetailScreen extends StatefulWidget {
  const EventDetailScreen({
    super.key,
    required this.eventId,
    required this.controller,
  });

  final String eventId;
  final AlertsController controller;

  @override
  State<EventDetailScreen> createState() => _EventDetailScreenState();
}

class _EventDetailScreenState extends State<EventDetailScreen> {
  Event? _event;
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final e = await apiClient.getEvent(widget.eventId);
      if (mounted) setState(() => _event = e);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _handle() async {
    final note = await _askNote(context);
    if (note == null) return;
    try {
      final updated = await widget.controller.handle(widget.eventId, note);
      if (mounted) setState(() => _event = updated.brief != null ? updated : _event?.copyWith(handled: true, handledAt: updated.handledAt, handledNote: updated.handledNote));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('已标记处理')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('处理失败：$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('告警详情')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? EmptyState('加载失败：$_error',
                  icon: Icons.error_outline)
              : _body(_event!),
    );
  }

  Widget _body(Event e) {
    final brief = e.brief;
    // 被「标记为未处理」移回告警的，详情也显示为待处理（后端 handled 仍为 true）。
    final effHandled = e.handled && !widget.controller.isReopened(e.eventId);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(children: [
          SeverityBadge(e.finalSeverity),
          const SizedBox(width: 8),
          Text(eventTypeLabel(e.eventType),
              style: const TextStyle(color: Colors.black54)),
          const Spacer(),
          Text('${(e.confidence * 100).round()}%',
              style: const TextStyle(color: Colors.black45)),
        ]),
        const SizedBox(height: 12),
        Text(e.summary,
            style:
                const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Text('工位 ${e.stationId} · ${e.source} · ${fmtIso(e.timestamp, full: true)}',
            style: const TextStyle(color: Colors.black54, fontSize: 13)),
        const SizedBox(height: 14),
        if (e.image.isNotEmpty) EvidenceImage(e.image, height: 240),
        if (brief != null) ...[
          const SizedBox(height: 18),
          _section('L2 本地认知简报'),
          const SizedBox(height: 6),
          Text(brief.explanation),
          const SizedBox(height: 10),
          if (brief.actions.isNotEmpty)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: brief.actions
                  .map((a) => Chip(
                        label: Text(_actionLabel(a)),
                        visualDensity: VisualDensity.compact,
                      ))
                  .toList(),
            ),
          if (brief.escalateToCloud)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('↑ 已升级云端复核',
                  style: TextStyle(color: AppColors.accent, fontSize: 13)),
            ),
        ],
        const SizedBox(height: 24),
        if (effHandled)
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
                color: AppColors.ok.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8)),
            child: Row(children: [
              const Icon(Icons.check_circle, color: AppColors.ok, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                    '已处理${e.handledNote.isNotEmpty ? '：${e.handledNote}' : ''}'
                    '${e.handledAt != null ? '\n${fmtIso(e.handledAt, full: true)}' : ''}',
                    style: const TextStyle(color: AppColors.ok)),
              ),
            ]),
          )
        else
          FilledButton.icon(
            onPressed: _handle,
            icon: const Icon(Icons.task_alt),
            label: const Text('标记已处理'),
          ),
      ],
    );
  }

  Widget _section(String t) =>
      Text(t, style: const TextStyle(fontWeight: FontWeight.w700));

  static String _actionLabel(String a) {
    const m = {
      'voice': '语音提醒',
      'recheck': '复核',
      'aim': '激光指示',
      'log': '记录',
    };
    return m[a] ?? a;
  }
}

/// 处理备注输入弹窗（共用）。
Future<String?> _askNote(BuildContext context) {
  final c = TextEditingController(text: '已处理');
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('处理备注'),
      content: TextField(
        controller: c,
        autofocus: true,
        decoration: const InputDecoration(
            hintText: '如：已断电并提醒学生处理'),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(ctx), child: const Text('取消')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, c.text.trim()),
            child: const Text('确认')),
      ],
    ),
  );
}
