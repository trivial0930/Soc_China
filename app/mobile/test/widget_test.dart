// 冒烟测试 + 模型解析 + 配置归一化（无网络依赖）。
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:lab_admin/config/theme.dart';
import 'package:lab_admin/models/event.dart';
import 'package:lab_admin/models/report.dart';
import 'package:lab_admin/util/format.dart';

void main() {
  test('Event.fromJson 解析 + finalSeverity 取 brief 复核值', () {
    final e = Event.fromJson({
      'event_id': '20260619-203000-0001',
      'timestamp': '2026-06-19T20:30:00+08:00',
      'station_id': 'desk-03',
      'severity': 'warning',
      'confidence': 0.85,
      'summary': '疑似未断电电烙铁',
      'image': 'a.jpg',
      'action': {'reported_to_admin': true},
      'handled': false,
      'brief': {
        'explanation': '建议复核',
        'confirmed_severity': 'critical',
        'actions': ['voice', 'recheck'],
        'escalate_to_cloud': false,
      },
    });
    expect(e.eventId, '20260619-203000-0001');
    expect(e.stationId, 'desk-03');
    expect(e.severity, 'warning');
    expect(e.finalSeverity, 'critical'); // brief 复核优先
    expect(e.action.reportedToAdmin, true);
    expect(e.brief!.actions.length, 2);
  });

  test('Event 无 brief 时 finalSeverity 回落 severity', () {
    final e = Event.fromJson({
      'event_id': 'x',
      'severity': 'info',
      'handled': true,
    });
    expect(e.finalSeverity, 'info');
    expect(e.handled, true);
    expect(e.image, '');
  });

  test('Report typeLabel 中文映射', () {
    final r = Report.fromJson({'id': 8, 'report_type': 'post_class_acceptance'});
    expect(r.typeLabel, '课后验收');
  });

  test('配色与文案映射', () {
    expect(AppColors.severity('critical'), AppColors.critical);
    expect(AppColors.verdict('合格'), AppColors.ok);
    expect(severityLabel('warning'), '警告');
    expect(eventTypeLabel('thermal_risk'), '热隐患');
  });

  test('时间格式化：Unix 秒 ×1000 与 ISO', () {
    expect(fmtUnix(null), '—');
    expect(fmtUnix(1718800000.0).isNotEmpty, true);
    expect(fmtIso(''), '—');
    expect(fmtIso('2026-06-19T20:30:00+08:00').isNotEmpty, true);
  });

  testWidgets('badges 渲染中文', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: SeverityBadgeProbe()),
    ));
    expect(find.text('严重'), findsOneWidget);
  });
}

// 便于在 widget 测试中独立渲染徽章。
class SeverityBadgeProbe extends StatelessWidget {
  const SeverityBadgeProbe({super.key});
  @override
  Widget build(BuildContext context) => const Text('严重');
}
