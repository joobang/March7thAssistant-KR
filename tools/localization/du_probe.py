"""Read one live Windows DU frame with Korean OCR without sending game input."""

import argparse
import ctypes
from ctypes import wintypes
import sys
import time
from pathlib import Path

from .common import DATA, save_json
from .du_recognition import korean_viewport
from .du_missions import mission_rows
from .du_replay import diagnose_frame
from .runtime import normalize


def capture(window_title, delay):
    if sys.platform != "win32":
        raise RuntimeError("Live capture requires Windows; pass --image to inspect a saved frame.")

    from mss import MSS
    from PIL import Image

    print(f"{delay}초 안에 게임 창을 맨 앞으로 가져오세요.", flush=True)
    time.sleep(delay)
    with MSS() as mss:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]

        window = user32.GetForegroundWindow()
        title = ctypes.create_unicode_buffer(1024)
        if not window or not user32.GetWindowTextW(window, title, len(title)):
            raise RuntimeError("전면 창 제목을 읽지 못했습니다.")
        if normalize(title.value) != normalize(window_title):
            raise RuntimeError(f"전면 창은 {title.value!r}입니다. 게임 창을 맨 앞으로 가져오세요.")

        rect, position = wintypes.RECT(), wintypes.POINT()
        if not user32.GetClientRect(window, ctypes.byref(rect)) or not user32.ClientToScreen(
            window, ctypes.byref(position)
        ):
            raise RuntimeError("게임 창의 화면 영역을 읽지 못했습니다.")
        region = {"left": position.x, "top": position.y,
                  "width": rect.right - rect.left, "height": rect.bottom - rect.top}
        if min(region["width"], region["height"]) <= 0:
            raise RuntimeError("게임 창의 크기가 올바르지 않습니다.")
        shot = mss.grab(region)
        if user32.GetForegroundWindow() != window:
            raise RuntimeError("캡처하는 동안 전면 창이 바뀌었습니다.")
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        if max(high for _, high in image.getextrema()) <= 8:
            raise RuntimeError("게임 창이 검은색으로 캡처됐습니다.")
        return image


def recognize(image, model_dir):
    from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR

    model_dir.mkdir(parents=True, exist_ok=True)
    engine = RapidOCR(params={
        "Global.model_root_dir": str(model_dir),
        "Det.ocr_version": OCRVersion.PPOCRV4,
        "Cls.ocr_version": OCRVersion.PPOCRV4,
        "Rec.ocr_version": OCRVersion.PPOCRV4,
        "Rec.lang_type": LangRec.KOREAN,
        "Rec.model_type": ModelType.MOBILE,
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Cls.engine_type": EngineType.ONNXRUNTIME,
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })
    result = engine(image, use_cls=False, text_score=0.35)
    if result.boxes is None or result.txts is None or result.scores is None:
        return []
    return [(box.tolist(), (text, float(score)))
            for box, text, score in zip(result.boxes, result.txts, result.scores, strict=True)]


def inspect(image, rows):
    viewport = korean_viewport(image)
    return {
        "resolution": image.size,
        "viewport": viewport,
        "ocr_results": [
            {"box": box, "text": text, "confidence": score}
            for box, (text, score) in rows
        ],
        "decisions": diagnose_frame(rows, image.size, {}, viewport=viewport),
        "missions": mission_rows(rows, image.size, viewport),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-title", default="붕괴: 스타레일")
    parser.add_argument("--delay", type=int, choices=range(0, 61), default=15, metavar="0-60")
    parser.add_argument("--image", type=Path, help="Use a saved capture in place of the foreground window.")
    parser.add_argument("--model-dir", type=Path, default=DATA / "models")
    parser.add_argument("--output", type=Path, default=DATA / "reports/du-probe.json")
    args = parser.parse_args()

    try:
        if args.image:
            from PIL import Image
            with Image.open(args.image) as source:
                image = source.convert("RGB")
        else:
            image = capture(args.window_title, args.delay)
        print("한국어 OCR로 화면을 읽고 있습니다.", flush=True)
        report = inspect(image, recognize(image, args.model_dir))
        save_json(args.output, report)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(f"OCR {len(report['ocr_results'])}줄 → {args.output}")
    for probe, result in report["decisions"].items():
        if result["hits"]:
            print(f"{probe}: {result['status']}")
    for mission in report["missions"]:
        print(f"미완료 후보: {mission['objective']} ({mission['confidence_status']})")


if __name__ == "__main__":
    main()
