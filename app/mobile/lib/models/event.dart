/// 安全告警事件（API_SPEC §3.1）。
class EventAction {
  final String robotTask;
  final String voicePrompt;
  final bool reportedToAdmin;

  const EventAction({
    this.robotTask = '',
    this.voicePrompt = '',
    this.reportedToAdmin = false,
  });

  factory EventAction.fromJson(Map<String, dynamic>? j) {
    j ??= const {};
    return EventAction(
      robotTask: (j['robot_task'] as String?) ?? '',
      voicePrompt: (j['voice_prompt'] as String?) ?? '',
      reportedToAdmin: j['reported_to_admin'] == true,
    );
  }
}

/// L2 本地认知简报，可能为 null（异步到达；列表接口通常省略）。
class Brief {
  final String explanation;
  final String confirmedSeverity;
  final List<String> actions;
  final bool escalateToCloud;

  const Brief({
    this.explanation = '',
    this.confirmedSeverity = '',
    this.actions = const [],
    this.escalateToCloud = false,
  });

  factory Brief.fromJson(Map<String, dynamic> j) => Brief(
        explanation: (j['explanation'] as String?) ?? '',
        confirmedSeverity: (j['confirmed_severity'] as String?) ?? '',
        actions: ((j['actions'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        escalateToCloud: j['escalate_to_cloud'] == true,
      );
}

class Event {
  final String eventId;
  final String timestamp; // ISO8601 带时区
  final String receivedAt;
  final String stationId;
  final String source;
  final String eventType;
  final String severity; // info|warning|critical（初筛）
  final double confidence; // 0~1
  final String summary;
  final String image; // 证据图文件名，'' 为无图
  final EventAction action;
  final bool handled;
  final String? handledAt;
  final String handledNote;
  final Brief? brief;

  const Event({
    required this.eventId,
    required this.timestamp,
    required this.receivedAt,
    required this.stationId,
    required this.source,
    required this.eventType,
    required this.severity,
    required this.confidence,
    required this.summary,
    required this.image,
    required this.action,
    required this.handled,
    required this.handledAt,
    required this.handledNote,
    required this.brief,
  });

  factory Event.fromJson(Map<String, dynamic> j) => Event(
        eventId: (j['event_id'] ?? '').toString(),
        timestamp: (j['timestamp'] as String?) ?? '',
        receivedAt: (j['received_at'] as String?) ?? '',
        stationId: (j['station_id'] as String?) ?? '',
        source: (j['source'] as String?) ?? '',
        eventType: (j['event_type'] as String?) ?? '',
        severity: (j['severity'] as String?) ?? 'info',
        confidence: (j['confidence'] as num?)?.toDouble() ?? 0.0,
        summary: (j['summary'] as String?) ?? '',
        image: (j['image'] as String?) ?? '',
        action: EventAction.fromJson(j['action'] as Map<String, dynamic>?),
        handled: j['handled'] == true,
        handledAt: j['handled_at'] as String?,
        handledNote: (j['handled_note'] as String?) ?? '',
        brief: j['brief'] is Map<String, dynamic>
            ? Brief.fromJson(j['brief'] as Map<String, dynamic>)
            : null,
      );

  /// 最终严重度：L2 复核值优先（API_SPEC §3.1 注）。
  String get finalSeverity {
    final c = brief?.confirmedSeverity ?? '';
    return c.isNotEmpty ? c : severity;
  }

  /// 用 SSE/handle 增量更新后返回新对象（不可变）。
  Event copyWith({
    bool? handled,
    String? handledAt,
    String? handledNote,
  }) =>
      Event(
        eventId: eventId,
        timestamp: timestamp,
        receivedAt: receivedAt,
        stationId: stationId,
        source: source,
        eventType: eventType,
        severity: severity,
        confidence: confidence,
        summary: summary,
        image: image,
        action: action,
        handled: handled ?? this.handled,
        handledAt: handledAt ?? this.handledAt,
        handledNote: handledNote ?? this.handledNote,
        brief: brief,
      );
}
