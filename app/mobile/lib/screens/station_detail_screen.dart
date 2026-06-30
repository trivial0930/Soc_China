import 'package:flutter/material.dart';

import '../models/acceptance.dart';
import '../models/event.dart';
import '../models/paged.dart';
import '../models/record.dart';
import '../services/api_client.dart';
import '../util/format.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import '../widgets/evidence_image.dart';
import 'stations_screen.dart' show kStationRetention;

/// 工位详情:该工位的占用记录(近 30 天,时间倒序) + 最近验收 + 近期告警。
class StationDetailScreen extends StatefulWidget {
  const StationDetailScreen({super.key, required this.stationId});
  final String stationId;

  @override
  State<StationDetailScreen> createState() => _StationDetailScreenState();
}

class _StationDetailScreenState extends State<StationDetailScreen> {
  Acceptance? _acceptance;
  List<Event> _events = [];
  List<WorkstationRecord> _records = [];
  Object? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  static DateTime _recTime(WorkstationRecord r) => r.enteredAt != null
      ? DateTime.fromMillisecondsSinceEpoch((r.enteredAt! * 1000).round())
      : (DateTime.tryParse(r.receivedAt) ??
          DateTime.fromMillisecondsSinceEpoch(0));

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        apiClient.getStation(widget.stationId),
        apiClient.getRecords(station: widget.stationId, limit: 200),
      ]);
      final summary = results[0] as StationSummary;
      final recPage = results[1] as Paged<WorkstationRecord>;
      final cutoff = DateTime.now().subtract(kStationRetention);
      final recs = recPage.items
          .where((r) => _recTime(r).isAfter(cutoff))
          .toList()
        ..sort((a, b) => _recTime(b).compareTo(_recTime(a)));
      if (mounted) {
        setState(() {
          _acceptance = summary.latestAcceptance;
          _events = summary.recentEvents;
          _records = recs;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('工位 ${widget.stationId}')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? EmptyState('加载失败:$_error', icon: Icons.error_outline)
              : RefreshIndicator(onRefresh: _load, child: _body()),
    );
  }

  Widget _body() {
    final acc = _acceptance;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (acc != null) ...[
          const Text('课后验收', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    VerdictBadge(acc.verdict),
                    const Spacer(),
                    Text(fmtIso(acc.receivedAt),
                        style: const TextStyle(
                            color: Colors.black45, fontSize: 13)),
                  ]),
                  if (acc.problems.isNotEmpty) ...[
                    const SizedBox(height: 10),
                    ...acc.problems.map((p) => Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Text('• $p'),
                        )),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
        ],

        // 该工位的占用记录(近 30 天,时间倒序)
        Text('工位记录（近 30 天 · ${_records.length} 条）',
            style: const TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 8),
        if (_records.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('近 30 天无记录', style: TextStyle(color: Colors.black54)),
          )
        else
          ..._records.map(_recordCard),

        if (_events.isNotEmpty) ...[
          const SizedBox(height: 16),
          const Text('近期告警', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          ..._events.map((e) => Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        SeverityBadge(e.finalSeverity),
                        const Spacer(),
                        Text(fmtIso(e.timestamp),
                            style: const TextStyle(
                                color: Colors.black45, fontSize: 13)),
                      ]),
                      const SizedBox(height: 6),
                      Text(e.summary),
                    ],
                  ),
                ),
              )),
        ],
      ],
    );
  }

  Widget _recordCard(WorkstationRecord r) => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Text('进入 ${fmtUnix(r.enteredAt)}',
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                const Spacer(),
                VerdictBadge(r.acceptanceHint),
              ]),
              const SizedBox(height: 2),
              Text('离开 ${fmtUnix(r.leftAt)}',
                  style: const TextStyle(color: Colors.black54, fontSize: 13)),
              if (r.note.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(r.note,
                    style:
                        const TextStyle(color: Colors.black54, fontSize: 13)),
              ],
              if (r.snapshots.isNotEmpty) ...[
                const SizedBox(height: 10),
                SizedBox(
                  height: 90,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: r.snapshots.length,
                    separatorBuilder: (_, _) => const SizedBox(width: 8),
                    itemBuilder: (c, i) =>
                        EvidenceImage(r.snapshots[i], height: 90, width: 120),
                  ),
                ),
              ],
            ],
          ),
        ),
      );
}
