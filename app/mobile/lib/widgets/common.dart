import 'package:flutter/material.dart';

import '../config/theme.dart';

/// 空态/错误态占位。
class EmptyState extends StatelessWidget {
  const EmptyState(this.text, {super.key, this.icon = Icons.inbox_outlined});
  final String text;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 40, color: Colors.black26),
              const SizedBox(height: 10),
              Text(text, style: const TextStyle(color: Colors.black45)),
            ],
          ),
        ),
      );
}

/// 连接状态圆点（SSE 连上=绿，断开/未配置=灰红）。
class ConnectionDot extends StatelessWidget {
  const ConnectionDot(this.connected, {super.key});
  final bool connected;

  @override
  Widget build(BuildContext context) => Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(
          color: connected ? const Color(0xFF46D27A) : Colors.white38,
          shape: BoxShape.circle,
        ),
      );
}

/// 横向滚动的筛选 chips。
class FilterChips<T> extends StatelessWidget {
  const FilterChips({
    super.key,
    required this.options,
    required this.selected,
    required this.onSelected,
  });

  final List<MapEntry<T, String>> options;
  final T selected;
  final ValueChanged<T> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 40,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        itemCount: options.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (c, i) {
          final o = options[i];
          final on = o.key == selected;
          return ChoiceChip(
            label: Text(o.value),
            selected: on,
            onSelected: (_) => onSelected(o.key),
            selectedColor: AppColors.accent,
            labelStyle: TextStyle(
                color: on ? Colors.white : Colors.black87, fontSize: 13),
            showCheckmark: false,
          );
        },
      ),
    );
  }
}
