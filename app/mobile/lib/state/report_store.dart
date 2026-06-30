import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/report.dart';

/// 报告本地缓存：拉取后存本地(列表 + 已打开过的 Markdown 正文),可离线查看;
/// 长按删除从本地移除(持久化,不再出现)。均用 shared_preferences。
class ReportStore extends ChangeNotifier {
  static const _kCache = 'mgmt_reports_cache';
  static const _kDeleted = 'mgmt_reports_deleted';

  final Map<int, Report> _cache = {};
  final Set<int> _deleted = {};

  Future<void> load() async {
    final sp = await SharedPreferences.getInstance();
    _cache.clear();
    final raw = sp.getString(_kCache);
    if (raw != null && raw.isNotEmpty) {
      try {
        for (final m in (jsonDecode(raw) as List)) {
          final r = Report.fromJson(Map<String, dynamic>.from(m as Map));
          _cache[r.id] = r;
        }
      } catch (_) {/* 忽略坏缓存 */}
    }
    _deleted
      ..clear()
      ..addAll(_decodeInts(sp.getString(_kDeleted)));
    notifyListeners();
  }

  static List<int> _decodeInts(String? s) {
    if (s == null || s.isEmpty) return const [];
    try {
      return (jsonDecode(s) as List).map((e) => (e as num).toInt()).toList();
    } catch (_) {
      return const [];
    }
  }

  /// 列表:缓存内未删除的,按创建时间倒序。
  List<Report> get list {
    final xs = _cache.values.where((r) => !_deleted.contains(r.id)).toList();
    xs.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return xs;
  }

  Report? get(int id) => _deleted.contains(id) ? null : _cache[id];

  /// 合并后端列表;列表接口无正文,若本地已缓存正文则保留。
  Future<void> mergeList(List<Report> fresh) async {
    for (final r in fresh) {
      if (_deleted.contains(r.id)) continue;
      final old = _cache[r.id];
      _cache[r.id] = (old != null && old.hasBody && !r.hasBody)
          ? r.withBody(old.bodyMarkdown) // 更新元数据,保留已缓存正文
          : r;
    }
    await _persist();
    notifyListeners();
  }

  /// 详情拉到正文后缓存(离线可读)。
  Future<void> upsertDetail(Report full) async {
    if (_deleted.contains(full.id)) return;
    _cache[full.id] = full;
    await _persist();
    notifyListeners();
  }

  /// 从本地删除(持久化隐藏)。
  Future<void> delete(int id) async {
    _deleted.add(id);
    _cache.remove(id);
    await _persist();
    notifyListeners();
  }

  Future<void> _persist() async {
    final sp = await SharedPreferences.getInstance();
    await sp.setString(
        _kCache, jsonEncode(_cache.values.map((r) => r.toJson()).toList()));
    await sp.setString(_kDeleted, jsonEncode(_deleted.toList()));
  }
}

final reportStore = ReportStore();
