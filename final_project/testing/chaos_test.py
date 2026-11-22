#!/usr/bin/env python3
"""
Terminates the running instance behind one tier's Auto Scaling Group and
measures how long the ALB takes to serve healthy traffic again, then
checks that against a recovery-time SLO.
"""

import argparse
import csv
import sys
import time

from aws_helpers import get_inservice_instance_id, terminate_instance_via_asg
from http_probe import probe_once, wait_for_state


def load_env(path: str) -> dict:
    values = {}

    with open(path) as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()

    return values


def main():
    parser = argparse.ArgumentParser(
        description="Measure recovery time after killing one instance."
    )

    parser.add_argument(
        "--tier",
        choices=["uploader", "viewer"],
        required=True,
    )

    parser.add_argument(
        "--slo-seconds",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--max-wait",
        type=float,
        default=600.0,
    )

    args = parser.parse_args()

    env = {
        **load_env(".env"),
        **load_env("stack_outputs.env"),
    }

    region = env.get("AWS_REGION", "us-east-2")
    alb_dns = env.get("ALB_DNS_NAME")

    if not alb_dns:
        sys.exit(
            "ALB_DNS_NAME not found — run create_app_stack.sh first."
        )

    slo_seconds = (
        args.slo_seconds
        if args.slo_seconds is not None
        else float(env.get("RECOVERY_SLO_SECONDS", 180))
    )

    if args.tier == "uploader":
        port = env.get("UPLOADER_LISTENER_PORT", "8080")
        asg_name = env.get("UPLOADER_ASG_NAME")
    else:
        port = env.get("VIEWER_LISTENER_PORT", "8081")
        asg_name = env.get("VIEWER_ASG_NAME")

    url = f"http://{alb_dns}:{port}/"

    print(f"Target: {args.tier} tier at {url}")

    print("Confirming the endpoint is healthy before we start...")

    if not probe_once(url):
        sys.exit(
            "Endpoint is not responding now — fix that before "
            "running a chaos test against it."
        )

    instance_id = get_inservice_instance_id(asg_name, region)

    if not instance_id:
        sys.exit(
            f"No InService instance found in {asg_name}."
        )

    print(
        f"Terminating {instance_id} via the Auto Scaling Group..."
    )

    log_rows = []
    t0 = time.monotonic()

    terminate_instance_via_asg(instance_id, region)

    print("Waiting for the endpoint to go down...")

    down_at = wait_for_state(
        url,
        want_up=False,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        log_rows=log_rows,
    )

    if down_at is None:
        print(
            "Endpoint never went down within max-wait — "
            "the target group may have already had a healthy standby, "
            "or the termination didn't take effect."
        )

    print("Waiting for the endpoint to come back up...")

    recovered_at = wait_for_state(
        url,
        want_up=True,
        poll_interval=args.poll_interval,
        max_wait=args.max_wait,
        log_rows=log_rows,
    )

    log_path = f"chaos_test_{args.tier}_{int(t0)}.csv"

    with open(log_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["elapsed_seconds", "is_up"])
        writer.writerows(log_rows)

    print(f"Poll log written to {log_path}")

    if recovered_at is None:
        print(
            f"FAIL: endpoint did not recover within max-wait "
            f"({args.max_wait:.0f}s)."
        )
        sys.exit(1)

    print(
        f"Recovery time: {recovered_at:.1f}s "
        f"(SLO: {slo_seconds:.0f}s)"
    )

    if recovered_at <= slo_seconds:
        print("PASS: recovery time met the SLO.")
        sys.exit(0)
    else:
        print("FAIL: recovery time exceeded the SLO.")
        sys.exit(1)


if __name__ == "__main__":
    main()
