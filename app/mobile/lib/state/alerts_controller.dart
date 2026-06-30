import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/app_config.dart';
import '../models/event.dart';
import '../services/api_client.dart';
import '../services/sse_client.dart';

enum AlertFilter { all, critical, warning }

/// 历史保留窗口：已处理告警超过此时长不再在「历史」展示（仅 App 内隐藏，后端数据不动）。
const Duration kHistoryRetention = Duration(days: 30);

/// 告警屏状态：初始列表 + SSE 实时 + 轮询降级 + 角标 + critical 通知钩子。
/// 全局单例，与当前所在 Tab 无关地维护告警与角标（HomeShell 在启动时 init）。
class AlertsController extends ChangeNotifier {
  AlertsController(this._cfg) : _sse = SseClient(_cfg) {
    _sse
      ..onEvent = _onSse
      ..onStatus = _onStatus;
  }

  final AppConfig _cfg;
  final SseClient _sse;

  final List<Event> _events = [];
  bool _connected = false;
  bool _loading = false;
  Object? _error;
  AlertFilter _filter = AlertFilter.all;
  Timer? _pollTimer;

  // 本地覆盖（持久化）：删除的历史 id（彻底隐藏）、被「标记为未处理」移回告警的 id。
  static const _kDeleted = 'mgmt_deleted_ids';
  static const _kReopened = 'mgmt_reopened_ids';
  final Set<String> _deleted = {};
  final Set<String> _reopened = {};

  /// 生效的已处理状态：被移回告警的视为未处理。
  bool _effHandled(Event e) => !_reopened.contains(e.eventId) && e.handled;

  /// 该事件是否被「标记为未处理」移回告警（详情页据此显示待处理）。
  bool isReopened(String id) => _reopened.contains(id);

  /// 新 critical 告警回调（UI 弹横幅/通知）。
  void Function(Event)? onCritical;

  List<Event> get events => List.unmodifiable(_events);
  bool get connected => _connected;
  bool get loading => _loading;
  Object? get error => _error;
  AlertFilter get filter => _filter;

  /// 未处理且非 info 的数量（底栏角标）。
  int get badgeCount => _events
      .where((e) =>
          !_deleted.contains(e.eventId) &&
          !_effHandled(e) &&
          e.finalSeverity != 'info')
      .length;

  /// 告警屏只显示**未处理**（含被移回的）；已处理的归入 [history]；删除的全程隐藏。
  List<Event> get filtered {
    final live = _events.where(
        (e) => !_deleted.contains(e.eventId) && !_effHandled(e));
    switch (_filter) {
      case AlertFilter.critical:
        return live.where((e) => e.finalSeverity == 'critical').toList();
      case AlertFilter.warning:
        return live.where((e) => e.finalSeverity == 'warning').toList();
      case AlertFilter.all:
        return live.toList();
    }
  }

  /// 历史：已处理且 handled_at 在保留窗口内，按处理时间倒序。
  /// 超窗的不返回（“满一个月自动消失”）；删除/移回的不返回（仅 App 内隐藏，后端数据不动）。
  List<Event> get history {
    final cutoff = DateTime.now().subtract(kHistoryRetention);
    final list = _events.where((e) {
      if (_deleted.contains(e.eventId)) return false;
      if (!_effHandled(e)) return false;
      final at = _handledAt(e);
      return at == null || at.isAfter(cutoff); // 无处理时间视为刚处理，保留
    }).toList();
    list.sort((a, b) {
      final ta = _handledAt(a);
      final tb = _handledAt(b);
      if (ta == null && tb == null) return 0;
      if (ta == null) return -1; // 无时间者置顶
      if (tb == null) return 1;
      return tb.compareTo(ta); // 倒序
    });
    return list;
  }

  static DateTime? _handledAt(Event e) =>
      e.handledAt == null ? null : DateTime.tryParse(e.handledAt!);

  void setFilter(AlertFilter f) {
    _filter = f;
    notifyListeners();
  }

  // ---- 本地覆盖状态（删除 / 移回告警），shared_preferences 持久化 ----
  Future<void> loadLocalState() async {
    final sp = await SharedPreferences.getInstance();
    _deleted
      ..clear()
      ..addAll(_decodeIds(sp.getString(_kDeleted)));
    _reopened
      ..clear()
      ..addAll(_decodeIds(sp.getString(_kReopened)));
    notifyListeners();
  }

  static List<String> _decodeIds(String? s) {
    if (s == null || s.isEmpty) return const [];
    try {
      return (jsonDecode(s) as List).map((e) => e.toString()).toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> _persist() async {
    final sp = await SharedPreferences.getInstance();
    await sp.setString(_kDeleted, jsonEncode(_deleted.toList()));
    await sp.setString(_kReopened, jsonEncode(_reopened.toList()));
  }

  /// 从历史中删除（仅本地隐藏；后端数据不动）。
  Future<void> deleteFromHistory(String id) async {
    _deleted.add(id);
    _reopened.remove(id);
    notifyListeners();
    await _persist();
  }

  /// 撤销删除。
  Future<void> undoDelete(String id) async {
    if (_deleted.remove(id)) {
      notifyListeners();
      await _persist();
    }
  }

  /// 标记为未处理：把该历史移回告警（本地覆盖，后端 handled 仍为 true）。
  Future<void> reopen(String id) async {
    _reopened.add(id);
    notifyListeners();
    await _persist();
  }

  /// 首次进入或服务器地址变更后调用。
  Future<void> init() async {
    _sse.stop();
    await loadLocalState();
    if (!_cfg.configured) {
      _events.clear();
      _connected = false;
      notifyListeners();
      return;
    }
    await refresh();
    _sse.start();
  }

  Future<void> refresh() async {
    if (!_cfg.configured) return;
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      final page = await apiClient.getEvents(limit: 100);
      _events
        ..clear()
        ..addAll(page.items);
    } catch (e) {
      _error = e;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<Event> handle(String id, String note) async {
    final updated = await apiClient.handleEvent(id, note);
    _upsert(updated);
    if (_reopened.remove(id)) _persist(); // 重新处理后回归历史
    notifyListeners();
    return updated;
  }

  // ---- SSE / 轮询 ----
  void _onSse(String name, Map<String, dynamic> payload) {
    if (name == 'hazard') {
      final ev = Event.fromJson(payload);
      final isNew = _events.indexWhere((x) => x.eventId == ev.eventId) < 0;
      _upsert(ev);
      if (isNew && ev.finalSeverity == 'critical') onCritical?.call(ev);
    } else if (name == 'handled') {
      final id = (payload['event_id'] ?? '').toString();
      final i = _events.indexWhere((x) => x.eventId == id);
      if (i >= 0) {
        _events[i] = _events[i].copyWith(
          handled: payload['handled'] == true,
          handledAt: payload['handled_at'] as String?,
          handledNote: (payload['handled_note'] as String?) ?? '',
        );
      }
    }
    notifyListeners();
  }

  void _onStatus(bool up) {
    _connected = up;
    if (up) {
      _pollTimer?.cancel();
      _pollTimer = null;
    } else {
      _startPolling(); // SSE 断开 → 轮询降级（§5）
    }
    notifyListeners();
  }

  void _startPolling() {
    _pollTimer ??= Timer.periodic(const Duration(seconds: 7), (_) async {
      if (_connected || !_cfg.configured) return;
      try {
        final since = _events.isNotEmpty ? _events.first.timestamp : null;
        final page = await apiClient.getEvents(
            since: since, handled: false, limit: 100);
        for (final e in page.items) {
          _upsert(e);
        }
        notifyListeners();
      } catch (_) {
        /* 静默重试 */
      }
    });
  }

  /// 插入或合并（按 event_id），新事件置顶并按时间排序。
  void _upsert(Event e) {
    final i = _events.indexWhere((x) => x.eventId == e.eventId);
    if (i >= 0) {
      _events[i] = e;
    } else {
      _events.insert(0, e);
    }
    _events.sort((a, b) => b.timestamp.compareTo(a.timestamp));
  }

  @override
  void dispose() {
    _sse.stop();
    _pollTimer?.cancel();
    super.dispose();
  }
}
