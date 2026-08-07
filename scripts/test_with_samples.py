"""
Uploads the 3 sample images through the API, polls until each finishes
processing, and writes the responses to test_output/ as submission
evidence (per the assignment's submission checklist).

Usage:
    python scripts/test_with_samples.py [BASE_URL]

    BASE_URL defaults to http://localhost:8000
"""
import sys
import time
import json
from pathlib import Path

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SAMPLES_DIR = Path(__file__).parent.parent / "seed" / "sample_images"
OUTPUT_DIR = Path(__file__).parent.parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)


def upload(path: Path) -> dict:
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "image/png")}
        resp = httpx.post(f"{BASE_URL}/api/v1/images", files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_until_done(image_id: str, timeout_s: int = 30) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = httpx.get(f"{BASE_URL}/api/v1/images/{image_id}/status", timeout=10)
        status = resp.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(1)
    results = httpx.get(f"{BASE_URL}/api/v1/images/{image_id}/results", timeout=10)
    return results.json()


def main():
    samples = sorted(SAMPLES_DIR.glob("*.png"))
    if not samples:
        print(f"No sample images found in {SAMPLES_DIR}")
        sys.exit(1)

    summary = []
    for sample_path in samples:
        print(f"Uploading {sample_path.name} ...")
        upload_resp = upload(sample_path)
        image_id = upload_resp["id"]
        print(f"  -> id={image_id}, waiting for processing...")

        result = poll_until_done(image_id)
        out_file = OUTPUT_DIR / f"{sample_path.stem}_result.json"
        out_file.write_text(json.dumps(result, indent=2))

        print(f"  -> status={result.get('status')} verdict={result.get('verdict')} "
              f"trust_score={result.get('trust_score')}")
        print(f"  -> saved to {out_file}")

        summary.append({
            "sample": sample_path.name,
            "id": image_id,
            "status": result.get("status"),
            "verdict": result.get("verdict"),
            "trust_score": result.get("trust_score"),
        })

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
