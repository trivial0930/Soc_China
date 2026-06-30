import 'package:flutter/material.dart';

/// 配色与文案（API_SPEC §8）：
/// severity: critical=红 / warning=橙 / info=灰蓝
/// verdict:  合格=绿 / 需整理=橙 / 存在安全隐患=红
class AppColors {
  static const info = Color(0xFF5B6B7B);
  static const warning = Color(0xFFE8853A);
  static const critical = Color(0xFFD63B3B);
  static const ok = Color(0xFF2E9B5B);
  static const accent = Color(0xFF2B6CB0);
  static const ink = Color(0xFF1F2933);
  static const bg = Color(0xFFF2F4F7);

  static Color severity(String s) {
    switch (s) {
      case 'critical':
        return critical;
      case 'warning':
        return warning;
      default:
        return info;
    }
  }

  static Color verdict(String v) {
    switch (v) {
      case '合格':
        return ok;
      case '需整理':
        return warning;
      case '存在安全隐患':
        return critical;
      default:
        return info;
    }
  }
}

const Map<String, String> severityLabels = {
  'info': '信息',
  'warning': '警告',
  'critical': '严重',
};

const Map<String, String> eventTypeLabels = {
  'thermal_risk': '热隐患',
  'desk_messy': '桌面待整理',
  'device_missing': '设备缺失',
  'estop': '急停',
  'fault': '故障',
};

String severityLabel(String s) => severityLabels[s] ?? s;
String eventTypeLabel(String t) => eventTypeLabels[t] ?? t;

ThemeData buildTheme() {
  final base = ThemeData(
    colorSchemeSeed: AppColors.accent,
    useMaterial3: true,
    scaffoldBackgroundColor: AppColors.bg,
    brightness: Brightness.light,
  );
  return base.copyWith(
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.ink,
      foregroundColor: Colors.white,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}
