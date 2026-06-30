/// 课后桌面验收（API_SPEC §3.3）。
class Acceptance {
  final int id;
  final String stationId;
  final String verdict; // 合格 | 需整理 | 存在安全隐患
  final String severity;
  final List<String> problems;
  final int? reportId;
  final String receivedAt;

  const Acceptance({
    required this.id,
    required this.stationId,
    required this.verdict,
    required this.severity,
    required this.problems,
    required this.reportId,
    required this.receivedAt,
  });

  factory Acceptance.fromJson(Map<String, dynamic> j) => Acceptance(
        id: (j['id'] as num?)?.toInt() ?? 0,
        stationId: (j['station_id'] as String?) ?? '',
        verdict: (j['verdict'] as String?) ?? '',
        severity: (j['severity'] as String?) ?? '',
        problems: ((j['problems'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        reportId: (j['report_id'] as num?)?.toInt(),
        receivedAt: (j['received_at'] as String?) ?? '',
      );
}
