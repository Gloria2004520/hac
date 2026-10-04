#!/usr/bin/env python3
"""生成演示用二维码：手机相机（iOS / Android）直接扫码即可打开链接。

用法::

    # 默认：生成演示地址的 PNG + SVG，输出到 scripts/qr/demo.{png,svg}
    python scripts/make-qr.py

    # 指定链接
    python scripts/make-qr.py --url https://example.com/some/path

    # 自定义输出前缀 / 尺寸 / 只要 PNG
    python scripts/make-qr.py --out docs/qr/hac --size 1600 --no-svg

说明：
- 纠错等级固定 H（约 30% 冗余），屏幕反光、打印偏色都还能扫出来；
- 白色静默区（border）按规范留 4 个模块，贴着别的元素也不影响识别；
- SVG 是矢量，放大到投影仪尺寸也不会糊，适合放进 slides；
- 生成的 PNG 会做一次解码回读自检（装了 opencv 时），确认真的能扫。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import qrcode
from qrcode.image.svg import SvgPathImage

# DEFAULT_URL = "https://hac-production-6b51.up.railway.app/"
DEFAULT_URL = "https://hac-production-c11e.up.railway.app/"
DEFAULT_OUT = "scripts/qr/demo"
BORDER = 4  # 静默区宽度（模块数）


def make_qr(url: str, box_size: int = 10) -> qrcode.QRCode:
    qr = qrcode.QRCode(
        version=None,  # 自动选能装下数据的最小版本
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=BORDER,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr


def write_png(url: str, path: Path, target_size: int) -> None:
    """按目标边长反推 box_size，保证输出尺寸接近 target_size 且为整数模块。"""
    probe = make_qr(url, box_size=1)
    modules = probe.modules_count + BORDER * 2
    box_size = max(1, round(target_size / modules))
    make_qr(url, box_size=box_size).make_image(fill_color="black", back_color="white").save(path)
    print(f"  PNG  {path}  ({box_size * modules}x{box_size * modules}px, box={box_size})")


def write_svg(url: str, path: Path) -> None:
    make_qr(url, box_size=BORDER).make_image(image_factory=SvgPathImage).save(path)
    print(f"  SVG  {path}  (矢量，可无损放大)")


def verify(path: Path, url: str) -> bool:
    """用 OpenCV 解码回读，确认二维码真的能被相机扫出来（没装就跳过）。"""
    try:
        import cv2  # type: ignore
    except ImportError:
        print("  [跳过解码自检] 未安装 opencv-python-headless")
        return True
    img = cv2.imread(str(path))
    if img is None:
        print("  [自检失败] 读不到图片")
        return False
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(img)
    ok = decoded.strip() == url.strip()
    print(f"  [解码自检] {'通过：' + decoded if ok else '失败，解出=' + repr(decoded)}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="生成可被手机相机直接扫描的二维码")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"要编码的地址（默认 {DEFAULT_URL}）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出前缀，不含扩展名")
    ap.add_argument("--size", type=int, default=1024, help="PNG 目标边长（像素，默认 1024）")
    ap.add_argument("--no-svg", action="store_true", help="只生成 PNG")
    args = ap.parse_args()

    url = args.url
    prefix = Path(args.out)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    print(f"编码内容: {url}")
    png_path = prefix.with_suffix(".png")
    write_png(url, png_path, args.size)

    if not args.no_svg:
        write_svg(url, prefix.with_suffix(".svg"))

    if not verify(png_path, url):
        print("二维码自检未通过，别拿去用。", file=sys.stderr)
        return 1
    print("完成：把它投到大屏上，手机相机对着扫即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
