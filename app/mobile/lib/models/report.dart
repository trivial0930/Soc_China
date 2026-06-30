/// 巡检报告（API_SPEC §3.4）。列表省略 body_markdown，详情才带。
class Report {
  final int id;
  final String title;
  final String reportType;
  final String verdict;
  final String severity;
  final List<String> eventIds;
  final String bodyMarkdown; // 仅详情接口带
  final String createdAt;
  final String receivedAt;

  const Report({
    required this.id,
    required this.title,
    required this.reportType,
    required this.verdict,
    required this.severity,
    required this.eventIds,
    required this.bodyMarkdown,
    required this.createdAt,
    required this.receivedAt,
  });

  factory Report.fromJson(Map<String, dynamic> j) => Report(
        id: (j['id'] as num?)?.toInt() ?? 0,
        title: (j['title'] as String?) ?? '',
        reportType: (j['report_type'] as String?) ?? '',
        verdict: (j['verdict'] as String?) ?? '',
        severity: (j['severity'] as String?) ?? '',
        eventIds: ((j['event_ids'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        bodyMarkdown: (j['body_markdown'] as String?) ?? '',
        createdAt: (j['created_at'] as String?) ?? '',
        receivedAt: (j['received_at'] as String?) ?? '',
      );

  /// 序列化(本地缓存用)。
  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'report_type': reportType,
        'verdict': verdict,
        'severity': severity,
        'event_ids': eventIds,
        'body_markdown': bodyMarkdown,
        'created_at': createdAt,
        'received_at': receivedAt,
      };

  Report withBody(String body) => Report(
        id: id,
        title: title,
        reportType: reportType,
        verdict: verdict,
        severity: severity,
        eventIds: eventIds,
        bodyMarkdown: body,
        createdAt: createdAt,
        receivedAt: receivedAt,
      );

  bool get hasBody => bodyMarkdown.isNotEmpty;

  /// report_type 枚举 → 中文标签（API_SPEC §3 枚举）。
  static const Map<String, String> typeLabels = {
    'post_class_acceptance': '课后验收',
    'multi_image_synthesis': '多图综合',
    'uncertain_followup': '不确定追问',
    'periodic_summary': '周期汇总',
  };

  String get typeLabel => typeLabels[reportType] ?? reportType;
}
