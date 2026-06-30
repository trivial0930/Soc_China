import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 全局配置：后端地址 + 写接口 token，持久化到 shared_preferences。
/// 演示现场 Mac IP 会变，故服务器地址做成可配置（API_SPEC §8）。
class AppConfig extends ChangeNotifier {
  static const _kBase = 'mgmt_base_url';
  static const _kToken = 'mgmt_token';
  static const _kVoiceEnabled = 'mgmt_voice_enabled';
  static const _kTtsVolume = 'mgmt_tts_volume';

  String _baseUrl = '';
  String _token = '';
  bool _voiceEnabled = true;
  int _ttsVolume = 80;

  String get baseUrl => _baseUrl;
  String get token => _token;
  bool get configured => _baseUrl.isNotEmpty;

  /// 机器人语音开关的本地（乐观）状态。权威源在机器人，这里只记上次从本 App 设置的值。
  bool get voiceEnabled => _voiceEnabled;

  /// 机器人 TTS 播报音量本地（乐观）值,0-100。权威源在机器人。
  int get ttsVolume => _ttsVolume;

  Future<void> load() async {
    final sp = await SharedPreferences.getInstance();
    _baseUrl = sp.getString(_kBase) ?? '';
    _token = sp.getString(_kToken) ?? '';
    _voiceEnabled = sp.getBool(_kVoiceEnabled) ?? true;
    _ttsVolume = sp.getInt(_kTtsVolume) ?? 80;
    notifyListeners();
  }

  Future<void> setVoiceEnabled(bool v) async {
    _voiceEnabled = v;
    final sp = await SharedPreferences.getInstance();
    await sp.setBool(_kVoiceEnabled, v);
    notifyListeners();
  }

  Future<void> setTtsVolume(int v) async {
    _ttsVolume = v.clamp(0, 100);
    final sp = await SharedPreferences.getInstance();
    await sp.setInt(_kTtsVolume, _ttsVolume);
    notifyListeners();
  }

  Future<void> setBaseUrl(String v) async {
    _baseUrl = _normalize(v);
    final sp = await SharedPreferences.getInstance();
    await sp.setString(_kBase, _baseUrl);
    notifyListeners();
  }

  Future<void> setToken(String v) async {
    _token = v.trim();
    final sp = await SharedPreferences.getInstance();
    await sp.setString(_kToken, _token);
    notifyListeners();
  }

  /// 归一化：补 http://、去尾部斜杠、去首尾空格。
  static String _normalize(String v) {
    var s = v.trim();
    if (s.isEmpty) return '';
    if (!s.startsWith('http://') && !s.startsWith('https://')) {
      s = 'http://$s';
    }
    return s.replaceAll(RegExp(r'/+$'), '');
  }

  /// 拼接 API 路径 → 完整 URI。
  Uri uri(String path, [Map<String, String>? query]) {
    final base = Uri.parse('$_baseUrl$path');
    if (query == null || query.isEmpty) return base;
    final q = <String, String>{...base.queryParameters};
    query.forEach((k, v) {
      if (v.isNotEmpty) q[k] = v;
    });
    return base.replace(queryParameters: q.isEmpty ? null : q);
  }

  /// 证据图地址（API_SPEC §4.5）。无文件名返回 null。
  String? imgUrl(String filename) =>
      filename.isEmpty ? null : '$_baseUrl/img/$filename';
}

/// 进程内单例（main 中 load 后注入）。
final appConfig = AppConfig();
