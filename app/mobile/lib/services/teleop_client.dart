import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../util/teleop_math.dart';

/// 雷达安全状态（GET /api/robot/teleop/status）。
class TeleopStatus {
  final String state; // clear | slow | blocked | unknown
  final double? frontDistM; // 前方最近障碍距离 m，可空
  final double ageMs; // 后端最新速度的“年龄”ms；过大视为失联
  const TeleopStatus(this.state, this.frontDistM, this.ageMs);

  static const unknown = TeleopStatus('unknown', null, double.infinity);
}

/// 遥控 HTTP 客户端：写速度 + 读安全状态。复用设置页的 baseURL + Bearer token。
/// 发送失败由调用方吞掉（遥控按 tick 重发，单次失败不阻塞）。
class TeleopClient {
  TeleopClient(this._cfg, {http.Client? client})
      : _http = client ?? http.Client();

  final AppConfig _cfg;
  final http.Client _http;
  static const _sendTimeout = Duration(milliseconds: 1500); // 10Hz，快速失败
  static const _statusTimeout = Duration(seconds: 3);

  /// POST /api/robot/teleop（需 token）。抛异常表示本次失败，调用方忽略即可。
  Future<void> sendVelocity(TeleopVelocity v) async {
    final headers = {'Content-Type': 'application/json; charset=utf-8'};
    if (_cfg.token.isNotEmpty) {
      headers['Authorization'] = 'Bearer ${_cfg.token}';
    }
    await _http
        .post(_cfg.uri('/api/robot/teleop'),
            headers: headers, body: jsonEncode(v.toJson()))
        .timeout(_sendTimeout);
  }

  /// GET /api/robot/teleop/status（读，无需 token）。任何异常返回 unknown。
  Future<TeleopStatus> getStatus() async {
    try {
      final res = await _http
          .get(_cfg.uri('/api/robot/teleop/status'))
          .timeout(_statusTimeout);
      if (res.statusCode != 200) return TeleopStatus.unknown;
      final m = jsonDecode(utf8.decode(res.bodyBytes));
      if (m is! Map) return TeleopStatus.unknown;
      final dist = m['front_dist_m'];
      final age = m['age_ms'];
      return TeleopStatus(
        (m['state'] ?? 'unknown').toString(),
        dist is num ? dist.toDouble() : null,
        age is num ? age.toDouble() : double.infinity,
      );
    } catch (_) {
      return TeleopStatus.unknown;
    }
  }
}

/// 进程内单例。
final teleopClient = TeleopClient(appConfig);
