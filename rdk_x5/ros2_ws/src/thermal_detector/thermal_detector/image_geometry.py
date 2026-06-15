"""Map detection boxes from a rotated inference frame back to the camera's native
pixel frame.

The gimbal-mounted RGB feed is rotated for YOLO (which needs an upright image), so
YOLO boxes come out in the rotated frame. Downstream visual servoing needs boxes in
the camera's NATIVE orientation (so image-x -> pan, image-y -> tilt holds). This
un-rotates a box accordingly. Pure stdlib; unit-tested.

``rotate_deg`` is the clockwise rotation that was applied to the image before
inference (0/90/180/270). ``orig_w``/``orig_h`` are the NATIVE (pre-rotation) frame
width/height. Boxes are ``(x1, y1, x2, y2)`` with x=column, y=row.
"""

from __future__ import annotations

from typing import Sequence, Tuple

Box = Tuple[float, float, float, float]


def unrotate_box(box: Sequence[float], rotate_deg: int, orig_w: int, orig_h: int) -> Box:
    x1, y1, x2, y2 = (float(v) for v in box)
    r = int(rotate_deg) % 360
    if r == 0:
        return (x1, y1, x2, y2)
    if r == 90:  # image was rotated 90 deg clockwise for inference
        return (y1, orig_h - 1 - x2, y2, orig_h - 1 - x1)
    if r == 180:
        return (orig_w - 1 - x2, orig_h - 1 - y2, orig_w - 1 - x1, orig_h - 1 - y1)
    if r == 270:
        return (orig_w - 1 - y2, x1, orig_w - 1 - y1, x2)
    raise ValueError(f"unsupported rotate_deg: {rotate_deg} (use 0/90/180/270)")
