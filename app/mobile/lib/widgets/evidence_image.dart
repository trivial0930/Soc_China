import 'package:flutter/material.dart';

import '../config/app_config.dart';

/// 证据图/快照（API_SPEC §4.5 /img/{filename}）。
/// 懒加载 + 加载中占位 + 失败占位；无文件名时显示占位块。
class EvidenceImage extends StatelessWidget {
  const EvidenceImage(
    this.filename, {
    super.key,
    this.height = 180,
    this.width,
    this.radius = 8,
  });

  final String filename;
  final double height;
  final double? width;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final url = appConfig.imgUrl(filename);
    final placeholder = _box(const Icon(Icons.image_not_supported_outlined,
        color: Colors.black26, size: 28));
    Widget child;
    if (url == null) {
      child = placeholder;
    } else {
      child = Image.network(
        url,
        height: height,
        width: width ?? double.infinity,
        fit: BoxFit.cover,
        loadingBuilder: (c, w, p) =>
            p == null ? w : _box(const CupertinoLikeSpinner()),
        errorBuilder: (c, e, s) => placeholder,
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: child,
    );
  }

  Widget _box(Widget child) => Container(
        height: height,
        width: width ?? double.infinity,
        color: const Color(0xFFEDEFF2),
        alignment: Alignment.center,
        child: child,
      );
}

class CupertinoLikeSpinner extends StatelessWidget {
  const CupertinoLikeSpinner({super.key});
  @override
  Widget build(BuildContext context) => const SizedBox(
        width: 22,
        height: 22,
        child: CircularProgressIndicator(strokeWidth: 2),
      );
}
