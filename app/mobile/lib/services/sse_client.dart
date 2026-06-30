import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// SSE 客户端（API_SPEC §5，GET /events/stream）。
/// 手动解析 text/event-stream（event:/data: 帧），断线指数退避自动重连。
/// 轮询降级由 AlertsController 在持续断连时接管。
class SseClient {
  SseClient(this._cfg);

  final AppConfig _cfg;

  /// 收到一帧：name = hazard|handled（ping 已忽略）；payload 为 §5 的 data.payload。
  void Function(String name, Map<String, dynamic> payload)? onEvent;

  /// 连接状态变化（true=已连，false=断开/重连中）。
  void Function(bool connected)? onStatus;

  http.Client? _client;
  StreamSubscription<String>? _sub;
  Timer? _retryTimer;
  bool _stopped = false;
  int _attempt = 0;

  void start() {
    _stopped = false;
    _attempt = 0;
    _connect();
  }

  void stop() {
    _stopped = true;
    _retryTimer?.cancel();
    _sub?.cancel();
    _client?.close();
    _client = null;
  }

  Future<void> _connect() async {
    if (_stopped || !_cfg.configured) return;
    _client?.close();
    _client = http.Client();
    final req = http.Request('GET', _cfg.uri('/events/stream'))
      ..headers['Accept'] = 'text/event-stream'
      ..headers['Cache-Control'] = 'no-cache';

    String eventName = 'message';
    final dataBuf = StringBuffer();

    void dispatch() {
      final data = dataBuf.toString();
      dataBuf.clear();
      final name = eventName;
      eventName = 'message';
      if (data.isEmpty) return;
      if (name == 'ping') return; // 心跳忽略（§5）
      try {
        final obj = jsonDecode(data);
        final payload = (obj is Map && obj['payload'] is Map)
            ? Map<String, dynamic>.from(obj['payload'] as Map)
            : (obj is Map ? Map<String, dynamic>.from(obj) : null);
        if (payload != null && (name == 'hazard' || name == 'handled')) {
          onEvent?.call(name, payload);
        }
      } catch (_) {
        /* 跳过坏帧 */
      }
    }

    try {
      final resp = await _client!.send(req);
      if (resp.statusCode != 200) {
        _scheduleRetry();
        return;
      }
      _attempt = 0;
      onStatus?.call(true);
      _sub = resp.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(
        (line) {
          if (line.isEmpty) {
            dispatch(); // 空行 = 帧结束
          } else if (line.startsWith(':')) {
            // 注释行（含部分心跳），忽略
          } else if (line.startsWith('event:')) {
            eventName = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            if (dataBuf.isNotEmpty) dataBuf.write('\n');
            dataBuf.write(line.substring(5).trimLeft());
          }
        },
        onDone: () {
          onStatus?.call(false);
          _scheduleRetry();
        },
        onError: (_) {
          onStatus?.call(false);
          _scheduleRetry();
        },
        cancelOnError: true,
      );
    } catch (_) {
      onStatus?.call(false);
      _scheduleRetry();
    }
  }

  void _scheduleRetry() {
    if (_stopped) return;
    _sub?.cancel();
    _attempt++;
    // 指数退避：2,4,8…最多 30s。
    final secs = (1 << _attempt).clamp(2, 30);
    _retryTimer?.cancel();
    _retryTimer = Timer(Duration(seconds: secs), _connect);
  }

  /// 多次重连失败 → 提示上层启用轮询降级。
  bool get strugglingToConnect => _attempt >= 3;
}
