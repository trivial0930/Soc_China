import 'package:flutter_test/flutter_test.dart';
import 'package:lab_admin/util/grouping.dart';

void main() {
  DateTime t(int day, int h, int m) => DateTime(2026, 6, day, h, m);
  List<DateSection<DateTime>> group(List<DateTime> xs) =>
      groupByDateAndSession<DateTime>(xs, (x) => x);

  test('空列表返回空', () {
    expect(group([]), isEmpty);
  });

  test('同一天、间隔小于阈值 → 一个时间段', () {
    final s = group([t(19, 21, 5), t(19, 21, 20), t(19, 21, 0)]);
    expect(s.length, 1); // 一个日期
    expect(s.first.segments.length, 1); // 一段
    expect(s.first.segments.first.items.length, 3);
  });

  test('同一天、间隔超过 30 分钟 → 拆成两段', () {
    final s = group([t(19, 20, 30), t(19, 21, 5), t(19, 21, 10)]);
    expect(s.length, 1);
    expect(s.first.segments.length, 2); // 20:30 一段,21:05~21:10 一段
    // 倒序:第一段是较晚的 21:05~21:10
    expect(s.first.segments.first.items.length, 2);
    expect(s.first.segments.last.items.length, 1);
  });

  test('跨天 → 两个日期分组,日期倒序', () {
    final s = group([t(18, 9, 0), t(19, 21, 0)]);
    expect(s.length, 2);
    expect(s.first.date.day, 19); // 最近的在前
    expect(s.last.date.day, 18);
  });

  test('时间段记录起止范围', () {
    final s = group([t(19, 21, 0), t(19, 21, 25)]);
    final seg = s.first.segments.first;
    expect(seg.start, t(19, 21, 0));
    expect(seg.end, t(19, 21, 25));
  });

  test('自定义 gap', () {
    final s = group([t(19, 21, 0), t(19, 21, 3)]);
    expect(s.first.segments.length, 1); // 默认 30min 内
    final s2 = groupByDateAndSession<DateTime>(
        [t(19, 21, 0), t(19, 21, 3)], (x) => x,
        gap: const Duration(minutes: 2));
    expect(s2.first.segments.length, 2); // 2min 阈值下拆开
  });
}
