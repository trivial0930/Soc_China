import 'package:intl/intl.dart';

/// 时间格式化（API_SPEC §8）：
/// - timestamp/received_at 是 ISO8601 带时区，直接 parse；
/// - entered_at/left_at 是 Unix 秒(float)，需 ×1000 转毫秒。
final DateFormat _fmt = DateFormat('MM-dd HH:mm');
final DateFormat _fmtFull = DateFormat('yyyy-MM-dd HH:mm:ss');

String fmtIso(String? iso, {bool full = false}) {
  if (iso == null || iso.isEmpty) return '—';
  try {
    final dt = DateTime.parse(iso).toLocal();
    return (full ? _fmtFull : _fmt).format(dt);
  } catch (_) {
    return iso;
  }
}

String fmtUnix(double? sec, {bool full = false}) {
  if (sec == null) return '—';
  try {
    final dt = DateTime.fromMillisecondsSinceEpoch((sec * 1000).round())
        .toLocal();
    return (full ? _fmtFull : _fmt).format(dt);
  } catch (_) {
    return sec.toString();
  }
}

const _weekdayCn = ['一', '二', '三', '四', '五', '六', '日'];

/// 日期分组大标题：如「6月19日 周五」（今/昨用相对词）。
String fmtDateHeader(DateTime d) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final diff = today.difference(DateTime(d.year, d.month, d.day)).inDays;
  final base = '${d.month}月${d.day}日 周${_weekdayCn[d.weekday - 1]}';
  if (diff == 0) return '今天 · $base';
  if (diff == 1) return '昨天 · $base';
  return base;
}

/// 时间段小标题用的 HH:mm。
String fmtHm(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// 时间段时间范围：起止同分钟显示单点，否则「HH:mm–HH:mm」。
String fmtSegmentRange(DateTime start, DateTime end) {
  final s = fmtHm(start), e = fmtHm(end);
  return s == e ? s : '$s–$e';
}
