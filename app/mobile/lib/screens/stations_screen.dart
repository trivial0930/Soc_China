import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../models/acceptance.dart';
import '../models/record.dart';
import '../services/api_client.dart';
import '../util/format.dart';
import '../util/grouping.dart';
import '../widgets/badges.dart';
import '../widgets/common.dart';
import 'station_detail_screen.dart';

/// 近 30 天保留窗口。
const Duration kStationRetention = Duration(days: 30);

/// ② 工位记录(按工位分类) + 课后验收(按时间段)。均只保留近 30 天。
class StationsScreen extends StatelessWidget {
  const StationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return const EmptyState('未设置服务器地址,请到「设置」填写 Mac IP',
          icon: Icons.dns_outlined);
    }
    return DefaultTabController(
      length: 2,
      child: Column(
        children: [
          Container(
            color: Colors.white,
            child: const TabBar(
              tabs: [Tab(text: '工位'), Tab(text: '课后验收')],
            ),
          ),
          const Expanded(
            child: TabBarView(
              children: [_StationsTab(), _AcceptanceTab()],
            ),
          ),
        ],
      ),
    );
  }
}

DateTime _recordTime(WorkstationRecord r) {
  if (r.enteredAt != null) {
    return DateTime.fromMillisecondsSinceEpoch((r.enteredAt! * 1000).round());
  }
  return DateTime.tryParse(r.receivedAt) ??
      DateTime.fromMillisecondsSinceEpoch(0);
}

DateTime _acceptanceTime(Acceptance a) =>
    DateTime.tryParse(a.receivedAt) ?? DateTime.fromMillisecondsSinceEpoch(0);

// ====================== 工位(按工位分类) ======================
class _StationsTab extends StatefulWidget {
  const _StationsTab();
  @override
  State<_StationsTab> createState() => _StationsTabState();
}

class _StationsTabState extends State<_StationsTab>
    with AutomaticKeepAliveClientMixin {
  late Future<List<WorkstationRecord>> _future = _load();
  Future<List<WorkstationRecord>> _load() async =>
      (await apiClient.getRecords(limit: 200)).items;

  @override
  bool get wantKeepAlive => true;

  /// 近 30 天的记录按 station_id 分组,每组按时间倒序;组按最近记录时间倒序。
  List<MapEntry<String, List<WorkstationRecord>>> _byStation(
      List<WorkstationRecord> items) {
    final cutoff = DateTime.now().subtract(kStationRetention);
    final recent =
        items.where((r) => _recordTime(r).isAfter(cutoff)).toList();
    final map = <String, List<WorkstationRecord>>{};
    for (final r in recent) {
      (map[r.stationId] ??= []).add(r);
    }
    for (final list in map.values) {
      list.sort((a, b) => _recordTime(b).compareTo(_recordTime(a)));
    }
    final entries = map.entries.toList();
    entries.sort((a, b) =>
        _recordTime(b.value.first).compareTo(_recordTime(a.value.first)));
    return entries;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() => _future = _load()),
      child: FutureBuilder<List<WorkstationRecord>>(
        future: _future,
        builder: (c, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return _scrollEmpty('加载失败:${snap.error}', Icons.error_outline);
          }
          final stations = _byStation(snap.data ?? []);
          if (stations.isEmpty) {
            return _scrollEmpty('近 30 天暂无工位记录', Icons.inbox_outlined);
          }
          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: stations.length,
            itemBuilder: (c, i) => _stationCard(context, stations[i]),
          );
        },
      ),
    );
  }

  Widget _stationCard(
      BuildContext context, MapEntry<String, List<WorkstationRecord>> e) {
    final latest = e.value.first;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => StationDetailScreen(stationId: e.key))),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.desk_outlined, color: Colors.black38),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(e.key,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text('${e.value.length} 条记录 · 最近 ${fmtUnix(latest.enteredAt)}',
                        style: const TextStyle(
                            color: Colors.black54, fontSize: 13)),
                  ],
                ),
              ),
              VerdictBadge(latest.acceptanceHint),
              const SizedBox(width: 4),
              const Icon(Icons.chevron_right, color: Colors.black26),
            ],
          ),
        ),
      ),
    );
  }
}

// ====================== 课后验收(时间段分组 + 30 天) ======================
class _AcceptanceTab extends StatefulWidget {
  const _AcceptanceTab();
  @override
  State<_AcceptanceTab> createState() => _AcceptanceTabState();
}

class _AcceptanceTabState extends State<_AcceptanceTab>
    with AutomaticKeepAliveClientMixin {
  late Future<List<Acceptance>> _future = _load();
  Future<List<Acceptance>> _load() async =>
      (await apiClient.getAcceptance(limit: 200)).items;

  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return RefreshIndicator(
      onRefresh: () async => setState(() => _future = _load()),
      child: FutureBuilder<List<Acceptance>>(
        future: _future,
        builder: (c, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return _scrollEmpty('加载失败:${snap.error}', Icons.error_outline);
          }
          final cutoff = DateTime.now().subtract(kStationRetention);
          final recent = (snap.data ?? [])
              .where((a) => _acceptanceTime(a).isAfter(cutoff))
              .toList();
          if (recent.isEmpty) {
            return _scrollEmpty('近 30 天暂无验收记录', Icons.inbox_outlined);
          }
          final sections = groupByDateAndSession(recent, _acceptanceTime);
          return ListView(
            padding: const EdgeInsets.only(bottom: 12),
            children: _groupedChildren(
                sections, (a) => _acceptanceCard(context, a)),
          );
        },
      ),
    );
  }

  Widget _acceptanceCard(BuildContext context, Acceptance a) => Card(
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) => StationDetailScreen(stationId: a.stationId))),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Text(a.stationId,
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
                  const Spacer(),
                  VerdictBadge(a.verdict),
                ]),
                if (a.problems.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  ...a.problems.map((p) => Padding(
                        padding: const EdgeInsets.only(bottom: 2),
                        child:
                            Text('• $p', style: const TextStyle(fontSize: 14)),
                      )),
                ],
                const SizedBox(height: 6),
                Text(fmtIso(a.receivedAt),
                    style:
                        const TextStyle(color: Colors.black45, fontSize: 12)),
              ],
            ),
          ),
        ),
      );
}

// ---- 时间段分组的扁平渲染(验收用) ----
Widget _dateHeader(DateTime d) => Padding(
      padding: const EdgeInsets.fromLTRB(14, 16, 14, 6),
      child: Text(fmtDateHeader(d),
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
    );

Widget _segmentHeader(DateTime start, DateTime end, int n) => Padding(
      padding: const EdgeInsets.fromLTRB(14, 2, 14, 6),
      child: Row(children: [
        const Icon(Icons.schedule, size: 14, color: Colors.black38),
        const SizedBox(width: 4),
        Text('${fmtSegmentRange(start, end)} · $n 条',
            style: const TextStyle(color: Colors.black54, fontSize: 13)),
      ]),
    );

List<Widget> _groupedChildren<T>(
  List<DateSection<T>> sections,
  Widget Function(T) itemBuilder,
) {
  final out = <Widget>[];
  for (final sec in sections) {
    out.add(_dateHeader(sec.date));
    for (final seg in sec.segments) {
      out.add(_segmentHeader(seg.start, seg.end, seg.items.length));
      for (final it in seg.items) {
        out.add(Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: itemBuilder(it),
        ));
      }
    }
  }
  out.add(const SizedBox(height: 16));
  return out;
}

Widget _scrollEmpty(String text, IconData icon) => ListView(
      children: [
        const SizedBox(height: 120),
        EmptyState(text, icon: icon),
      ],
    );
