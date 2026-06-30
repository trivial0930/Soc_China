/// 工位占用记录（API_SPEC §3.2）。entered_at/left_at 为 Unix 秒(float)。
class WorkstationRecord {
  final int id;
  final String stationId;
  final double? enteredAt; // Unix 秒
  final double? leftAt; // 或 null（仍在占用）
  final List<String> snapshots; // 图片文件名
  final String note;
  final String acceptanceHint; // '' | 合格 | 需整理 | 存在安全隐患
  final String receivedAt;

  const WorkstationRecord({
    required this.id,
    required this.stationId,
    required this.enteredAt,
    required this.leftAt,
    required this.snapshots,
    required this.note,
    required this.acceptanceHint,
    required this.receivedAt,
  });

  factory WorkstationRecord.fromJson(Map<String, dynamic> j) =>
      WorkstationRecord(
        id: (j['id'] as num?)?.toInt() ?? 0,
        stationId: (j['station_id'] as String?) ?? '',
        enteredAt: (j['entered_at'] as num?)?.toDouble(),
        leftAt: (j['left_at'] as num?)?.toDouble(),
        snapshots: ((j['snapshots'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        note: (j['note'] as String?) ?? '',
        acceptanceHint: (j['acceptance_hint'] as String?) ?? '',
        receivedAt: (j['received_at'] as String?) ?? '',
      );
}
