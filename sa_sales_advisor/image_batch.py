#!/usr/bin/env python3
"""Prepare local screenshots for lossless, unattended batch recognition.

This utility deliberately does not call a remote OCR service. It creates clear,
overlapping tiles that an agent can inspect one by one without asking the user
to upload each image. Recognition results remain pending until the user confirms
the customer and extracted facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MANIFEST_VERSION = 1
PILLOW_VERSION = "11.3.0"
LOCAL_DEPS = Path(__file__).resolve().parent.parent / ".deps"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("manifest_version") != MANIFEST_VERSION:
        raise SystemExit(f"unsupported manifest version: {data.get('manifest_version')}")
    return data


def require_pillow():
    if LOCAL_DEPS.is_dir() and str(LOCAL_DEPS) not in sys.path:
        sys.path.insert(0, str(LOCAL_DEPS))
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except ImportError:
        print(
            json.dumps(
                {
                    "status": "missing_dependency",
                    "dependency": "Pillow",
                    "message": "批量截图切片需要 Pillow。请在当前 Python 环境安装 Pillow 后重试。",
                    "install_command": f'"{sys.executable}" "{Path(__file__).resolve()}" setup',
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(4)
    return Image, ImageEnhance, ImageFilter, ImageOps


def setup(_args: argparse.Namespace) -> int:
    LOCAL_DEPS.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--target",
        str(LOCAL_DEPS),
        f"Pillow=={PILLOW_VERSION}",
    ]
    result = subprocess.run(command, check=False)
    if result.returncode:
        return result.returncode
    print(json.dumps({"status": "ready", "dependency": "Pillow", "version": PILLOW_VERSION, "path": str(LOCAL_DEPS)}, ensure_ascii=False, indent=2))
    return 0


def discover_images(input_path: Path, recursive: bool) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.casefold() in SUPPORTED_SUFFIXES else []
    if not input_path.is_dir():
        raise SystemExit(f"input path not found: {input_path}")
    iterator = input_path.rglob("*") if recursive else input_path.glob("*")
    return sorted(
        (item for item in iterator if item.is_file() and not item.is_symlink() and item.suffix.casefold() in SUPPORTED_SUFFIXES),
        key=natural_key,
    )


def tile_starts(height: int, tile_height: int, overlap: int) -> list[int]:
    if height <= tile_height:
        return [0]
    step = tile_height - overlap
    starts = list(range(0, max(height - tile_height + 1, 1), step))
    final = height - tile_height
    if not starts or starts[-1] != final:
        starts.append(final)
    return starts


def prepare(args: argparse.Namespace) -> int:
    Image, ImageEnhance, ImageFilter, ImageOps = require_pillow()
    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output == source or source in output.parents:
        raise SystemExit("output must not be inside the source folder")
    images = discover_images(source, args.recursive)
    if not images:
        raise SystemExit("no supported images found")

    batch_id = args.batch_id or datetime.now().strftime("images-%Y%m%d-%H%M%S")
    batch_dir = output / batch_id
    if batch_dir.exists() and any(batch_dir.iterdir()):
        raise SystemExit(f"batch already exists and is not empty: {batch_dir}")
    tile_dir = batch_dir / "tiles"
    ocr_dir = batch_dir / "ocr"
    tile_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "batch_id": batch_id,
        "created_at": now_iso(),
        "input_path": str(source),
        "batch_path": str(batch_dir),
        "customer_hint": args.customer_hint or "",
        "confirmation_status": "pending",
        "settings": {
            "recursive": args.recursive,
            "tile_height": args.tile_height,
            "overlap": args.overlap,
            "target_width": args.target_width,
            "enhance": not args.no_enhance,
        },
        "sources": [],
        "tiles": [],
    }

    for source_index, image_path in enumerate(images, start=1):
        source_id = f"source-{source_index:03d}"
        with Image.open(image_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        original_width, original_height = image.size
        scale = max(1.0, min(2.5, args.target_width / max(original_width, 1)))
        if scale > 1.01:
            image = image.resize(
                (round(original_width * scale), round(original_height * scale)),
                Image.Resampling.LANCZOS,
            )
        if not args.no_enhance:
            image = ImageEnhance.Contrast(image).enhance(1.12)
            image = image.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=3))
        width, height = image.size
        starts = tile_starts(height, args.tile_height, args.overlap)
        source_record = {
            "source_id": source_id,
            "source_file": str(image_path),
            "source_sha256": sha256_file(image_path),
            "original_size": [original_width, original_height],
            "prepared_size": [width, height],
            "scale": round(scale, 3),
            "tile_count": len(starts),
        }
        manifest["sources"].append(source_record)
        for tile_index, top in enumerate(starts, start=1):
            bottom = min(top + args.tile_height, height)
            tile_id = f"{source_index:03d}-{tile_index:03d}"
            tile_path = tile_dir / f"{tile_id}.png"
            image.crop((0, top, width, bottom)).save(tile_path, format="PNG", optimize=True)
            manifest["tiles"].append(
                {
                    "tile_id": tile_id,
                    "source_id": source_id,
                    "source_file": str(image_path),
                    "tile_file": str(tile_path),
                    "crop": [0, top, width, bottom],
                    "status": "pending",
                    "quality": None,
                    "ocr_file": None,
                    "notes": "",
                }
            )

    manifest_path = batch_dir / "manifest.json"
    atomic_json(manifest_path, manifest)
    queue_lines = [
        "# 批量截图识别队列",
        "",
        f"- 批次：`{batch_id}`",
        f"- 客户提示：{args.customer_hint or '未指定'}",
        f"- 原图：{len(manifest['sources'])} 张",
        f"- 待识别切片：{len(manifest['tiles'])} 张",
        "- 正式入库：等待用户统一确认",
        "",
        "逐张读取 `manifest.json` 中 `status=pending` 的 `tile_file`。只转录可见内容，不补写模糊文字；无法辨认处写 `[无法辨认]`。不要逐张询问用户。",
        "",
    ]
    (batch_dir / "QUEUE.md").write_text("\n".join(queue_lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "prepared",
                "batch_id": batch_id,
                "manifest": str(manifest_path),
                "source_count": len(manifest["sources"]),
                "tile_count": len(manifest["tiles"]),
                "customer_hint": manifest["customer_hint"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def record(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    item = next((tile for tile in manifest["tiles"] if tile["tile_id"] == args.tile_id), None)
    if item is None:
        raise SystemExit(f"unknown tile id: {args.tile_id}")
    text_path = Path(args.text_file).expanduser().resolve()
    if not text_path.is_file():
        raise SystemExit(f"OCR text file not found: {text_path}")
    text = text_path.read_text(encoding="utf-8").strip()
    destination = manifest_path.parent / "ocr" / f"{args.tile_id}.md"
    destination.write_text(text + "\n", encoding="utf-8")
    item.update(
        {
            "status": "completed" if args.quality != "unreadable" else "unreadable",
            "quality": args.quality,
            "ocr_file": str(destination),
            "notes": args.notes or "",
            "recognized_at": now_iso(),
        }
    )
    atomic_json(manifest_path, manifest)
    print(json.dumps({"status": item["status"], "tile_id": args.tile_id, "ocr_file": str(destination)}, ensure_ascii=False))
    return 0


def normalized_line(line: str) -> str:
    return re.sub(r"\s+", "", line).casefold()


def merge_overlap(existing: list[str], incoming: list[str], maximum: int = 30) -> list[str]:
    if not existing:
        return incoming
    upper = min(maximum, len(existing), len(incoming))
    for size in range(upper, 0, -1):
        left = [normalized_line(line) for line in existing[-size:]]
        right = [normalized_line(line) for line in incoming[:size]]
        if left == right and any(left):
            return existing + incoming[size:]
    return existing + incoming


def finalize(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    pending = [tile["tile_id"] for tile in manifest["tiles"] if tile["status"] == "pending"]
    if pending and not args.allow_pending:
        print(json.dumps({"status": "pending", "pending_tiles": pending}, ensure_ascii=False, indent=2))
        return 3

    output_lines = [
        "---",
        f"batch_id: {manifest['batch_id']}",
        f"customer_hint: {json.dumps(manifest.get('customer_hint', ''), ensure_ascii=False)}",
        f"created_at: {json.dumps(manifest['created_at'], ensure_ascii=False)}",
        "confirmation_status: pending",
        "material_type: batch_chat_screenshots",
        "---",
        "",
        "# 批量截图识别草稿",
        "",
        "> 本文由本地原图切片后逐块识别生成。内容尚未写入正式客户档案，需用户统一确认。",
        "",
    ]
    unreadable: list[str] = []
    for source in manifest["sources"]:
        output_lines.extend([f"## {Path(source['source_file']).name}", "", f"- 来源 SHA-256：`{source['source_sha256']}`", ""])
        merged: list[str] = []
        for tile in (item for item in manifest["tiles"] if item["source_id"] == source["source_id"]):
            if tile["status"] == "unreadable":
                unreadable.append(tile["tile_id"])
            if tile.get("ocr_file") and Path(tile["ocr_file"]).is_file():
                lines = Path(tile["ocr_file"]).read_text(encoding="utf-8").strip().splitlines()
                merged = merge_overlap(merged, lines)
        output_lines.extend(merged or ["[未获得可用识别文字]"])
        output_lines.append("")
    if unreadable or pending:
        output_lines.extend(["## 待人工确认", ""])
        if unreadable:
            output_lines.append(f"- 无法辨认切片：{', '.join(unreadable)}")
        if pending:
            output_lines.append(f"- 尚未处理切片：{', '.join(pending)}")
        output_lines.append("")
    combined = manifest_path.parent / "combined-ocr.md"
    combined.write_text("\n".join(output_lines), encoding="utf-8")
    manifest["combined_ocr_file"] = str(combined)
    manifest["finalized_at"] = now_iso()
    atomic_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "status": "finalized",
                "combined_ocr_file": str(combined),
                "pending_count": len(pending),
                "unreadable_count": len(unreadable),
                "confirmation_status": "pending",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def status(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest).expanduser().resolve())
    counts: dict[str, int] = {}
    for item in manifest["tiles"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print(
        json.dumps(
            {
                "status": "ok",
                "batch_id": manifest["batch_id"],
                "customer_hint": manifest.get("customer_hint", ""),
                "source_count": len(manifest["sources"]),
                "tile_count": len(manifest["tiles"]),
                "tile_status": counts,
                "confirmation_status": manifest["confirmation_status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Batch-prepare chat screenshots for recognition")
    sub = root.add_subparsers(dest="command", required=True)

    setup_parser = sub.add_parser("setup")
    setup_parser.set_defaults(func=setup)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--input", required=True, help="Explicit image or folder path")
    prepare_parser.add_argument("--output", required=True, help="Batch output parent folder")
    prepare_parser.add_argument("--batch-id")
    prepare_parser.add_argument("--customer-hint", default="")
    prepare_parser.add_argument("--recursive", action="store_true")
    prepare_parser.add_argument("--tile-height", type=int, default=1600)
    prepare_parser.add_argument("--overlap", type=int, default=180)
    prepare_parser.add_argument("--target-width", type=int, default=1400)
    prepare_parser.add_argument("--no-enhance", action="store_true")
    prepare_parser.set_defaults(func=prepare)

    record_parser = sub.add_parser("record")
    record_parser.add_argument("--manifest", required=True)
    record_parser.add_argument("--tile-id", required=True)
    record_parser.add_argument("--text-file", required=True)
    record_parser.add_argument("--quality", choices=["high", "medium", "low", "unreadable"], required=True)
    record_parser.add_argument("--notes", default="")
    record_parser.set_defaults(func=record)

    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--manifest", required=True)
    finalize_parser.add_argument("--allow-pending", action="store_true")
    finalize_parser.set_defaults(func=finalize)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--manifest", required=True)
    status_parser.set_defaults(func=status)
    return root


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "tile_height", 1) <= 0:
        raise SystemExit("tile height must be positive")
    if getattr(args, "overlap", 0) < 0 or getattr(args, "overlap", 0) >= getattr(args, "tile_height", 1):
        raise SystemExit("overlap must be at least 0 and smaller than tile height")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
