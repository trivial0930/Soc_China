import 'dart:convert';
import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/acceptance.dart';
import '../models/asset.dart';
import '../models/event.dart';
import '../models/paged.dart';
import '../models/record.dart';
import '../models/report.dart';

/// 工位聚合（API_SPEC §4.2 GET /api/stations/{id}）。
class StationSummary {
  final String stationId;
  final WorkstationRecord? latestRecord;
  final Acceptance? latestAcceptance;
  final List<Event> recentEvents;

  const StationSummary({
    required this.stationId,
    required this.latestRecord,
    required this.latestAcceptance,
    required this.recentEvents,
  });

  factory StationSummary.fromJson(Map<String, dynamic> j) => StationSummary(
        stationId: (j['station_id'] as String?) ?? '',
        latestRecord: j['latest_record'] is Map<String, dynamic>
            ? WorkstationRecord.fromJson(
                j['latest_record'] as Map<String, dynamic>)
            : null,
        latestAcceptance: j['latest_acceptance'] is Map<String, dynamic>
            ? Acceptance.fromJson(j['latest_acceptance'] as Map<String, dynamic>)
            : null,
        recentEvents: ((j['recent_events'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(Event.fromJson)
            .toList(),
      );
}

/// 统一错误（API_SPEC §9，错误体 {"detail":"..."}）。
class ApiException implements Exception {
  final int status; // 0 = 网络层错误
  final String message;
  ApiException(this.status, this.message);

  bool get isAuth => status == 401;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient(this._cfg, {http.Client? client})
      : _http = client ?? http.Client();

  final AppConfig _cfg;
  final http.Client _http;
  static const _timeout = Duration(seconds: 12);

  Map<String, String> _headers({bool auth = false, bool json = false}) {
    final h = <String, String>{};
    if (json) h['Content-Type'] = 'application/json; charset=utf-8';
    if (auth && _cfg.token.isNotEmpty) {
      h['Authorization'] = 'Bearer ${_cfg.token}';
    }
    return h;
  }

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    if (!_cfg.configured) {
      throw ApiException(0, '未设置服务器地址，请到「设置」填写');
    }
    http.Response res;
    try {
      res = await _http
          .get(_cfg.uri(path, query), headers: _headers())
          .timeout(_timeout);
    } catch (e) {
      throw ApiException(0, '网络错误，请检查服务器地址 / 同一热点');
    }
    return _decode(res);
  }

  dynamic _decode(http.Response res) {
    dynamic body;
    if (res.bodyBytes.isNotEmpty) {
      try {
        body = jsonDecode(utf8.decode(res.bodyBytes));
      } catch (_) {
        body = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return body;
    final detail = (body is Map && body['detail'] != null)
        ? body['detail'].toString()
        : 'HTTP ${res.statusCode}';
    throw ApiException(res.statusCode, detail);
  }

  // ---- §4.1 安全告警 ----
  Future<Map<String, dynamic>> health() async =>
      (await _get('/api/health')) as Map<String, dynamic>;

  Future<Paged<Event>> getEvents({
    String? station,
    String? severity,
    String? type,
    String? since,
    String? until,
    bool? handled,
    int limit = 50,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'station': ?station,
      'severity': ?severity,
      'type': ?type,
      'since': ?since,
      'until': ?until,
      'handled': ?handled?.toString(),
      'limit': '$limit',
      'offset': '$offset',
    };
    return Paged.fromJson(
        (await _get('/api/events', q)) as Map<String, dynamic>, Event.fromJson);
  }

  Future<Event> getEvent(String id) async => Event.fromJson(
      (await _get('/api/events/$id')) as Map<String, dynamic>);

  /// 标记已处理（需 token；§4.1）。后端不设 APP_INGEST_TOKEN 时写接口开放。
  Future<Event> handleEvent(String id, String note) async {
    if (!_cfg.configured) {
      throw ApiException(0, '未设置服务器地址');
    }
    http.Response res;
    try {
      res = await _http
          .post(
            _cfg.uri('/api/events/$id/handle'),
            headers: _headers(auth: true, json: true),
            body: jsonEncode({'note': note}),
          )
          .timeout(_timeout);
    } catch (e) {
      throw ApiException(0, '网络错误，请检查服务器地址');
    }
    final body = _decode(res);
    return Event.fromJson(body as Map<String, dynamic>);
  }

  // ---- §4.2 工位 + 验收 ----
  Future<Paged<WorkstationRecord>> getRecords({
    String? station,
    int limit = 50,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'station': ?station,
      'limit': '$limit',
      'offset': '$offset',
    };
    return Paged.fromJson((await _get('/api/records', q)) as Map<String, dynamic>,
        WorkstationRecord.fromJson);
  }

  Future<Paged<Acceptance>> getAcceptance({
    String? station,
    String? verdict,
    int limit = 50,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'station': ?station,
      'verdict': ?verdict,
      'limit': '$limit',
      'offset': '$offset',
    };
    return Paged.fromJson(
        (await _get('/api/acceptance', q)) as Map<String, dynamic>,
        Acceptance.fromJson);
  }

  Future<StationSummary> getStation(String id) async => StationSummary.fromJson(
      (await _get('/api/stations/$id')) as Map<String, dynamic>);

  // ---- §4.3 报告 ----
  Future<Paged<Report>> getReports({
    String? type,
    String? verdict,
    int limit = 50,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'type': ?type,
      'verdict': ?verdict,
      'limit': '$limit',
      'offset': '$offset',
    };
    return Paged.fromJson((await _get('/api/reports', q)) as Map<String, dynamic>,
        Report.fromJson);
  }

  Future<Report> getReport(int id) async =>
      Report.fromJson((await _get('/api/reports/$id')) as Map<String, dynamic>);

  // ---- §4.4 物资 ----
  Future<Paged<Asset>> getAssets({
    String? name,
    String? category,
    String? station,
    int limit = 50,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'name': ?name,
      'category': ?category,
      'station': ?station,
      'limit': '$limit',
      'offset': '$offset',
    };
    return Paged.fromJson((await _get('/api/assets', q)) as Map<String, dynamic>,
        Asset.fromJson);
  }

  void close() => _http.close();
}

/// 进程内单例（注入全局 appConfig）。
final apiClient = ApiClient(appConfig);
