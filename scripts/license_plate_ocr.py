#!/usr/bin/env python3
"""Standalone license plate OCR utility.

Not wired into the live camera pipeline (backend/app/cv) -- run manually
against a single image or video frame you supply. See README.md's "What
this doesn't do, on purpose" section for why automated plate reading isn't
attached to the public DDOT/VDOT feeds.

Usage:
    python scripts/license_plate_ocr.py --image path/to/photo.jpg
    python scripts/license_plate_ocr.py --video path/to/clip.mp4 --frame 30
"""

from __future__ import annotations

import argparse
import re
import sys

import cv2
import numpy as np
import pytesseract

PLATE_MIN_ASPECT_RATIO = 2.0
PLATE_MAX_ASPECT_RATIO = 5.5
PLATE_MIN_AREA = 1500
TESSERACT_CONFIG = (
    "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


def load_image_from_file(image_path: str) -> np.ndarray:
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")
    return image


def load_frame_from_video(video_path: str, frame_index: int = 0) -> np.ndarray:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    success, frame = capture.read()
    capture.release()

    if not success:
        raise ValueError(f"Could not read frame {frame_index} from video: {video_path}")
    return frame


def preprocess_for_contours(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    edges = cv2.Canny(gray, 30, 200)
    return edges


def find_plate_contour(image: np.ndarray) -> np.ndarray | None:
    edges = preprocess_for_contours(image)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

        if len(approx) != 4:
            continue

        x, y, w, h = cv2.boundingRect(approx)
        area = w * h
        aspect_ratio = w / float(h)

        if area < PLATE_MIN_AREA:
            continue
        if not (PLATE_MIN_ASPECT_RATIO <= aspect_ratio <= PLATE_MAX_ASPECT_RATIO):
            continue

        return approx

    return None


def crop_plate(image: np.ndarray, contour: np.ndarray) -> np.ndarray:
    x, y, w, h = cv2.boundingRect(contour)
    return image[y : y + h, x : x + w]


def prepare_plate_for_ocr(plate_image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(plate_image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    _, thresholded = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return thresholded


def ocr_plate_text(plate_image: np.ndarray) -> str:
    prepared = prepare_plate_for_ocr(plate_image)
    raw_text = pytesseract.image_to_string(prepared, config=TESSERACT_CONFIG)
    return re.sub(r"[^A-Z0-9]", "", raw_text.upper())


def detect_plate_text(image: np.ndarray) -> str | None:
    contour = find_plate_contour(image)
    if contour is None:
        return None

    plate_image = crop_plate(image, contour)
    plate_text = ocr_plate_text(plate_image)
    return plate_text or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and OCR a license plate.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=str, help="Path to a static image file.")
    source.add_argument("--video", type=str, help="Path to a video file.")
    parser.add_argument(
        "--frame",
        type=int,
        default=0,
        help="Frame index to read when using --video (default: 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.image:
            image = load_image_from_file(args.image)
        else:
            image = load_frame_from_video(args.video, args.frame)
    except (FileNotFoundError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    plate_text = detect_plate_text(image)

    if plate_text:
        print(plate_text)
    else:
        print("No license plate detected.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
