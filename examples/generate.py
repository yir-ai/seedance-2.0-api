"""Generate one Seedance 2.0 clip through Yir and save it to ./output.

Only the standard library; Python 3.9+.
Usage: YIR_API_KEY=... python examples/generate.py "a prompt" [name=value ...] [--image URL ...]
Example: python examples/generate.py "A bike courier in an orange rain jacket weaves through rainy neon traffic at night, handheld follow camera, rain and city sounds." resolution=480p duration=4 aspect_ratio=16:9 generate_audio=true
--image URLs fill these roles in order: first_frame, last_frame (Image-to-video).
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

API = "https://gateway.yir.ai/v1"
MODEL = "bytedance/seedance-2.0"
# Sent unless overridden on the command line; the README lists every parameter.
PARAMETERS = {"resolution": "480p", "duration": 4, "aspect_ratio": "16:9", "generate_audio": True}
TYPES = {"duration": "integer", "resolution": "string", "aspect_ratio": "string", "return_last_frame": "boolean", "generate_audio": "boolean", "n": "integer"}
IMAGE_ROLES = ["first_frame", "last_frame"]
USER_AGENT = f"yir-gh/seedance-2.0-api python-urllib/{sys.version_info.major}.{sys.version_info.minor}"


def call(method, path, body=None, headers=None):
    request = urllib.request.Request(
        API + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['YIR_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {path}: {error.code} {error.read().decode()}")


def main():
    args = sys.argv[1:]
    prompt = args.pop(0) if args else "A bike courier in an orange rain jacket weaves through rainy neon traffic at night, handheld follow camera, rain and city sounds."
    parameters = dict(PARAMETERS)
    references = []
    while args:
        arg = args.pop(0)
        if arg == "--image":
            references.append({"role": IMAGE_ROLES[min(len(references), len(IMAGE_ROLES) - 1)], "url": args.pop(0)})
            continue
        name, value = arg.split("=", 1)
        kind = TYPES.get(name)
        parameters[name] = value == "true" if kind == "boolean" else int(value) if kind == "integer" else value

    payload = {
        "model": MODEL,
        "input": {"type": "image", "prompt": prompt, "references": references} if references else {"type": "text", "prompt": prompt},
        "parameters": parameters,
    }
    quote = call("POST", "/videos/quotes", payload)
    estimate = quote.get("expected_amount")
    print(f"Estimated: ${estimate}" if estimate else "Estimated: not available in advance")

    # max_cost only guards against runaway charges (3x the estimate leaves room for a pricier fallback).
    # You pay what the channel bills. Reusing the same Idempotency-Key never submits the job twice.
    if estimate:
        payload["max_cost"] = f"{float(estimate) * 3:.2f}"
    job = call("POST", "/videos/generations", payload, {"Idempotency-Key": str(uuid.uuid4())})
    print(f"Job {job['id']}")
    while job["status"] not in ("succeeded", "failed", "cancelled"):
        job = call("GET", f"/jobs/{job['id']}?wait=20")  # long-poll: returns early when the status changes
    if job["status"] != "succeeded":
        sys.exit(f"{job['status']}: {json.dumps(job.get('error'))}")

    os.makedirs("output", exist_ok=True)
    for i, file in enumerate(job["result"]["files"]):
        path = f"output/{job['id']}-{i}.{file['media_type'].split('/')[1]}"
        with urllib.request.urlopen(urllib.request.Request(file["url"], headers={"User-Agent": USER_AGENT})) as response, open(path, "wb") as out:
            out.write(response.read())
        print(f"Saved {path}")
    print(f"Charged: ${job['billing']['total_charged_by_yir']} via {job.get('final_provider')}")


if __name__ == "__main__":
    main()
