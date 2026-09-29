"""Normalize edilmiş çokgen ROI doğrulama ve kare maskeleme."""

from __future__ import annotations

import math


def validate_polygon(value: object) -> list[tuple[float, float]]:
    if not isinstance(value, list) or not 3 <= len(value) <= 100:
        raise ValueError("ROI için 3 ila 100 köşe seç")
    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("ROI köşeleri [x, y] biçiminde olmalı")
        x, y = point
        if (type(x) not in (int, float) or type(y) not in (int, float)
                or not math.isfinite(x) or not math.isfinite(y)
                or not 0 <= x <= 1 or not 0 <= y <= 1):
            raise ValueError("ROI koordinatları 0 ile 1 arasında olmalı")
        points.append((float(x), float(y)))
    if len(set(points)) != len(points):
        raise ValueError("ROI köşeleri tekrar edemez")
    xs, ys = zip(*points)
    if max(xs) - min(xs) < 0.01 or max(ys) - min(ys) < 0.01:
        raise ValueError("ROI çok küçük")
    area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1]
                   - points[(i + 1) % len(points)][0] * points[i][1]
                   for i in range(len(points)))) / 2
    if area < 0.0001:
        raise ValueError("ROI alanı çok küçük")

    def crosses(a, b, c, d):
        def side(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0

    count = len(points)
    for i in range(count):
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue
            if crosses(points[i], points[(i + 1) % count],
                       points[j], points[(j + 1) % count]):
                raise ValueError("ROI çizgileri kesişemez")
    return points


def mask_frame(image, points: list[tuple[float, float]]):
    """Çokgenin sınırlayıcı kutusunu kırpıp dışını siyaha boyar."""
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    pixels = np.array([(round(x * (width - 1)), round(y * (height - 1)))
                       for x, y in points], dtype=np.int32)
    left, top = pixels.min(axis=0)
    right, bottom = pixels.max(axis=0) + 1
    crop = image[top:bottom, left:right]
    local = pixels - np.array([left, top], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [local], 255)
    return cv2.bitwise_and(crop, crop, mask=mask), local
