import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import 'api_client.dart' show ApiException;

/// 命令下发结果。
enum CommandOutcome {
  queued, // 后端已受理(201/200)
  notSupported, // 后端尚未实现该通道(404/405/501)
}

class CommandResult {
  final CommandOutcome outcome;
  final String? commandId;
  CommandResult(this.outcome, {this.commandId});
}

/// 命令下行客户端：POST /api/commands（见 app/BACKEND_PROMPT_command_api.md）。
/// 后端未实现命令通道时（404/405/501）返回 notSupported，让 UI 优雅提示而不报错。
class CommandClient {
  CommandClient(this._cfg, {http.Client? client})
      : _http = client ?? http.Client();

  final AppConfig _cfg;
  final http.Client _http;
  static const _timeout = Duration(seconds: 12);

  Future<CommandResult> send(String type,
      [Map<String, dynamic> params = const {}]) async {
    if (!_cfg.configured) {
      throw ApiException(0, '未设置服务器地址，请到「设置」填写');
    }
    final headers = {'Content-Type': 'application/json; charset=utf-8'};
    if (_cfg.token.isNotEmpty) {
      headers['Authorization'] = 'Bearer ${_cfg.token}';
    }
    http.Response res;
    try {
      res = await _http
          .post(
            _cfg.uri('/api/commands'),
            headers: headers,
            body: jsonEncode(
                {'type': type, 'params': params, 'issued_by': 'app'}),
          )
          .timeout(_timeout);
    } catch (e) {
      throw ApiException(0, '网络错误，请检查服务器地址 / 同一热点');
    }

    if (res.statusCode == 200 || res.statusCode == 201) {
      String? id;
      try {
        final body = jsonDecode(utf8.decode(res.bodyBytes));
        if (body is Map) id = body['command_id']?.toString();
      } catch (_) {/* 忽略 */}
      return CommandResult(CommandOutcome.queued, commandId: id);
    }
    // 后端尚未实现命令通道
    if (res.statusCode == 404 || res.statusCode == 405 || res.statusCode == 501) {
      return CommandResult(CommandOutcome.notSupported);
    }
    // 其余错误读 {detail}
    String detail = 'HTTP ${res.statusCode}';
    try {
      final body = jsonDecode(utf8.decode(res.bodyBytes));
      if (body is Map && body['detail'] != null) detail = body['detail'].toString();
    } catch (_) {/* 忽略 */}
    throw ApiException(res.statusCode, detail);
  }
}

/// 进程内单例。
final commandClient = CommandClient(appConfig);
