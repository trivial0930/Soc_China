import 'package:flutter/material.dart';

import 'config/app_config.dart';
import 'config/theme.dart';
import 'screens/home_shell.dart';
import 'state/alerts_controller.dart';
import 'state/report_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await appConfig.load();
  await reportStore.load();
  final alerts = AlertsController(appConfig);
  // 启动即拉初始列表 + 起 SSE（地址未配置时静默等待设置）。
  alerts.init();
  runApp(LabAdminApp(alerts: alerts));
}

class LabAdminApp extends StatelessWidget {
  const LabAdminApp({super.key, required this.alerts});
  final AlertsController alerts;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '实验室巡检 · 管理端',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: HomeShell(controller: alerts),
    );
  }
}
