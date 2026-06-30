/// 分页响应：{items:[...], total, limit, offset}（API_SPEC §2）。
class Paged<T> {
  final List<T> items;
  final int total;
  final int limit;
  final int offset;

  const Paged({
    required this.items,
    required this.total,
    required this.limit,
    required this.offset,
  });

  factory Paged.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) parse,
  ) {
    final raw = (json['items'] as List?) ?? const [];
    return Paged<T>(
      items: raw
          .whereType<Map<String, dynamic>>()
          .map(parse)
          .toList(growable: true),
      total: (json['total'] as num?)?.toInt() ?? raw.length,
      limit: (json['limit'] as num?)?.toInt() ?? raw.length,
      offset: (json['offset'] as num?)?.toInt() ?? 0,
    );
  }
}
