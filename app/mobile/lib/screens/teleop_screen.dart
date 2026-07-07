import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../widgets/teleop_control.dart';

/// 遥控驾驶页：薄壳，承载可复用的 [TeleopControlPanel]（摇杆 + 安全状态条 + STOP）。
/// deadman 等安全逻辑都在面板内（详见 TeleopControlPanel）。
class TeleopScreen extends StatelessWidget {
  const TeleopScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (!appConfig.configured) {
      return Scaffold(
        appBar: AppBar(title: const Text('遥控驾驶')),
        body: const Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text('未设置服务器地址，请到「设置」填写后再遥控。',
                textAlign: TextAlign.center),
          ),
        ),
      );
    }
    return Scaffold(
      appBar: AppBar(title: const Text('遥控驾驶')),
      body: const SafeArea(child: TeleopControlPanel()),
    );
  }
}
