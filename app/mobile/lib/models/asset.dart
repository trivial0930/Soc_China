/// 物资定位（API_SPEC §3.5）。category=large 用 station/area；small 用 cabinet/drawer/box。
class Asset {
  final int id;
  final String name;
  final String category; // large | small
  final String stationId;
  final String area;
  final String cabinet;
  final String drawer;
  final String box;
  final int quantity;
  final String note;
  final String locationText; // 后端格式化好的位置串，直接显示
  final String updatedAt;

  const Asset({
    required this.id,
    required this.name,
    required this.category,
    required this.stationId,
    required this.area,
    required this.cabinet,
    required this.drawer,
    required this.box,
    required this.quantity,
    required this.note,
    required this.locationText,
    required this.updatedAt,
  });

  bool get isLarge => category == 'large';

  factory Asset.fromJson(Map<String, dynamic> j) => Asset(
        id: (j['id'] as num?)?.toInt() ?? 0,
        name: (j['name'] as String?) ?? '',
        category: (j['category'] as String?) ?? '',
        stationId: (j['station_id'] as String?) ?? '',
        area: (j['area'] as String?) ?? '',
        cabinet: (j['cabinet'] as String?) ?? '',
        drawer: (j['drawer'] as String?) ?? '',
        box: (j['box'] as String?) ?? '',
        quantity: (j['quantity'] as num?)?.toInt() ?? 0,
        note: (j['note'] as String?) ?? '',
        locationText: (j['location_text'] as String?) ?? '',
        updatedAt: (j['updated_at'] as String?) ?? '',
      );
}
