/// 把带时间的条目分组为「日期 → 时间段(会话)」。
/// 时间段定义:同一自然日内,相邻条目时间差 ≤ [gap] 归为同一段;
/// 跨天或间隔超过 gap 则开新段。一天可有多段(取决于当天进行了几次会话)。
library;

class TimeSegment<T> {
  final DateTime start; // 段内最早时间
  final DateTime end; // 段内最晚时间
  final List<T> items; // 段内条目(按时间倒序)
  TimeSegment({required this.start, required this.end, required this.items});
}

class DateSection<T> {
  final DateTime date; // 仅日期(00:00)
  final List<TimeSegment<T>> segments; // 该日各时间段(按时间倒序)
  DateSection({required this.date, required this.segments});
}

bool _sameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;

/// 分组主函数。[timeOf] 取每条的时间;[gap] 默认 30 分钟。
List<DateSection<T>> groupByDateAndSession<T>(
  List<T> items,
  DateTime Function(T) timeOf, {
  Duration gap = const Duration(minutes: 30),
}) {
  if (items.isEmpty) return [];

  final sorted = [...items]..sort((a, b) => timeOf(b).compareTo(timeOf(a)));

  // 1) 切分会话段
  final segs = <List<T>>[];
  var cur = <T>[];
  DateTime? prev;
  for (final it in sorted) {
    final t = timeOf(it);
    final breakSeg = prev != null &&
        (!_sameDay(prev, t) || prev.difference(t).abs() > gap);
    if (breakSeg && cur.isNotEmpty) {
      segs.add(cur);
      cur = <T>[];
    }
    cur.add(it);
    prev = t;
  }
  if (cur.isNotEmpty) segs.add(cur);

  // 2) 段 → 按日期归并(保持倒序)
  final sections = <DateSection<T>>[];
  for (final seg in segs) {
    final times = seg.map(timeOf).toList();
    var start = times.first, end = times.first;
    for (final t in times) {
      if (t.isBefore(start)) start = t;
      if (t.isAfter(end)) end = t;
    }
    final d = DateTime(start.year, start.month, start.day);
    final ts = TimeSegment<T>(start: start, end: end, items: seg);
    if (sections.isNotEmpty && _sameDay(sections.last.date, d)) {
      sections.last.segments.add(ts);
    } else {
      sections.add(DateSection<T>(date: d, segments: [ts]));
    }
  }
  return sections;
}
