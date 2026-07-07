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

/// 命令回执（GET /api/commands/{id}）：状态 + 机器人返回的中文 result 文案。
class CommandReceipt {
  final String status; // queued | sent | done | failed | canceled
  final String result; // 机器人回执中文文案，可空
  CommandReceipt(this.status, this.result);
  bool get isDone => status == 'done';
  bool get isFailed => status == 'failed';
  bool get isTerminal => isDone || isFailed || status == 'canceled';
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

  /// 拉单条命令回执（GET /api/commands/{id}）。失败/异常返回 null。
  Future<CommandReceipt?> getReceipt(String commandId) async {
    try {
      final res =
          await _http.get(_cfg.uri('/api/commands/$commandId')).timeout(_timeout);
      if (res.statusCode != 200) return null;
      final m = jsonDecode(utf8.decode(res.bodyBytes));
      if (m is! Map) return null;
      return CommandReceipt(
          (m['status'] ?? '').toString(), (m['result'] ?? '').toString());
    } catch (_) {
      return null;
    }
  }

  /// 发命令并轮询直到出终态回执(done/failed/canceled)或超时。
  /// - 抛 [ApiException]：下发本身失败（如 401 缺 token）。
  /// - 返回 null：已受理但超时未拿到终态（调用方可用别的信号兜底，如 mode 轮询）。
  /// - notSupported：返回 failed 回执文案。
  Future<CommandReceipt?> sendAndAwait(
    String type,
    Map<String, dynamic> params, {
    Duration timeout = const Duration(seconds: 30),
    Duration poll = const Duration(milliseconds: 700),
  }) async {
    final r = await send(type, params);
    if (r.outcome == CommandOutcome.notSupported) {
      return CommandReceipt('failed', '后端暂未支持该命令');
    }
    final id = r.commandId;
    if (id == null) return null;
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(poll);
      final rec = await getReceipt(id);
      if (rec != null && rec.isTerminal) return rec;
    }
    return null; // 超时未出终态
  }
}

/// 进程内单例。
final commandClient = CommandClient(appConfig);
