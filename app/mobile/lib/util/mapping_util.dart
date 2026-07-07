/// 建图模式纯逻辑（可单测，不含 UI/IO）。
library;

/// UI 呈现态。由 RDK 回报的 mode + age 推出，前端不做模式合法性判断，只做展示分流。
enum MappingUi { offline, normal, switching, mapping, error }

/// 心跳年龄超过此值视为机器人离线（ms）。
const double kModeStaleMs = 6000;

/// 把 (mode, ageMs) 映射到 UI 态。age 过大或拿不到 → offline（优先级最高）。
MappingUi mappingUiOf(String mode, double ageMs) {
  if (mode == 'offline' || ageMs > kModeStaleMs) return MappingUi.offline;
  switch (mode) {
    case 'mapping':
      return MappingUi.mapping;
    case 'switching':
      return MappingUi.switching;
    case 'mapping_error':
      return MappingUi.error;
    case 'normal':
      return MappingUi.normal;
    default:
      // 未知字符串：保守按离线（不臆测），避免误显示开关可用。
      return MappingUi.offline;
  }
}

const String kDefaultMapName = 'lab_map';

/// 净化地图名：仅保留 [A-Za-z0-9_-]；空则回退默认。与机器人侧净化一致。
String sanitizeMapName(String raw) {
  final cleaned = raw.trim().replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '');
  return cleaned.isEmpty ? kDefaultMapName : cleaned;
}
