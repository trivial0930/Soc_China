import 'package:flutter_test/flutter_test.dart';
import 'package:lab_admin/util/mapping_util.dart';

void main() {
  group('mappingUiOf', () {
    test('age 过大 → offline（优先级最高，即使 mode=mapping）', () {
      expect(mappingUiOf('mapping', kModeStaleMs + 1), MappingUi.offline);
      expect(mappingUiOf('normal', 99999), MappingUi.offline);
    });

    test('offline 哨兵 → offline', () {
      expect(mappingUiOf('offline', double.infinity), MappingUi.offline);
    });

    test('各真实 mode 在新鲜心跳下正确分流', () {
      expect(mappingUiOf('normal', 100), MappingUi.normal);
      expect(mappingUiOf('switching', 100), MappingUi.switching);
      expect(mappingUiOf('mapping', 100), MappingUi.mapping);
      expect(mappingUiOf('mapping_error', 100), MappingUi.error);
    });

    test('未知 mode 保守按 offline（不臆测）', () {
      expect(mappingUiOf('weird_state', 100), MappingUi.offline);
    });
  });

  group('sanitizeMapName', () {
    test('保留字母数字下划线连字符', () {
      expect(sanitizeMapName('Lab_Map-01'), 'Lab_Map-01');
    });

    test('剔除非法字符（空格/中文/斜杠/点）', () {
      expect(sanitizeMapName('lab map/2026.今天'), 'labmap2026');
    });

    test('空或全非法 → 默认 lab_map', () {
      expect(sanitizeMapName(''), kDefaultMapName);
      expect(sanitizeMapName('  /// 中文 '), kDefaultMapName);
      expect(sanitizeMapName('   '), kDefaultMapName);
    });

    test('默认名常量为 lab_map', () {
      expect(kDefaultMapName, 'lab_map');
    });
  });
}
