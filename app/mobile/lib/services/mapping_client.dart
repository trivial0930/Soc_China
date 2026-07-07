import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// 机器人真实模式（GET /api/robot/mode）。`mode` 一切以 RDK 回报为准，
/// 前端不做合法性推断。取不到（未配置/404/网络错）→ 视为离线 [offline]。
class RobotMode {
  final String mode; // normal | switching | mapping | mapping_error | offline
  final double ageMs; // 心跳年龄；过大视为离线
  const RobotMode(this.mode, this.ageMs);

  /// 取不到时的离线哨兵（mode + 巨大 age，UI 一律按离线处理）。
  static const offline = RobotMode('offline', double.infinity);
}

/// 建图模式状态读取客户端。写操作（set_mode/save_map）复用 commandClient.sendAndAwait。
class MappingClient {
  MappingClient(this._cfg, {http.Client? client})
      : _http = client ?? http.Client();

  final AppConfig _cfg;
  final http.Client _http;
  static const _timeout = Duration(seconds: 3);

  /// GET /api/robot/mode（读，无需 token）。任何异常/非 200 → offline。
  Future<RobotMode> getMode() async {
    if (!_cfg.configured) return RobotMode.offline;
    try {
      final res =
          await _http.get(_cfg.uri('/api/robot/mode')).timeout(_timeout);
      if (res.statusCode != 200) return RobotMode.offline;
      final m = jsonDecode(utf8.decode(res.bodyBytes));
      if (m is! Map || m['mode'] == null) return RobotMode.offline;
      final age = m['age_ms'];
      return RobotMode(
        m['mode'].toString(),
        age is num ? age.toDouble() : double.infinity,
      );
    } catch (_) {
      return RobotMode.offline;
    }
  }
}

/// 进程内单例。
final mappingClient = MappingClient(appConfig);
