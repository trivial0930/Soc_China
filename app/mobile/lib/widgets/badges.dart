import 'package:flutter/material.dart';

import '../config/theme.dart';

class _Pill extends StatelessWidget {
  const _Pill(this.text, this.color);
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}

/// 严重度徽章（critical/warning/info）。
class SeverityBadge extends StatelessWidget {
  const SeverityBadge(this.severity, {super.key});
  final String severity;

  @override
  Widget build(BuildContext context) =>
      _Pill(severityLabel(severity), AppColors.severity(severity));
}

/// 验收结论徽章（合格/需整理/存在安全隐患）。
class VerdictBadge extends StatelessWidget {
  const VerdictBadge(this.verdict, {super.key});
  final String verdict;

  @override
  Widget build(BuildContext context) {
    if (verdict.isEmpty) return const SizedBox.shrink();
    return _Pill(verdict, AppColors.verdict(verdict));
  }
}
