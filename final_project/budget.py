#!/usr/bin/env python3
import argparse

HOURLY_STACK_ESTIMATE = 0.07
PROJECT_BUDGET = 2.00

parser = argparse.ArgumentParser(description="Weather Advisor cost estimate")
parser.add_argument("--hours", type=float, default=4.0,
                    help="Estimated stack runtime in hours")
parser.add_argument("--gemini-calls", type=int, default=0,
                    help="Number of Gemini calls used")
args = parser.parse_args()

infra_cost = args.hours * HOURLY_STACK_ESTIMATE
estimated_total = infra_cost
remaining = PROJECT_BUDGET - estimated_total

print("Weather Advisor Cost Estimate")
print(f"Stack runtime:      {args.hours:.2f} hours")
print(f"Gemini calls:       {args.gemini_calls}")
print(f"Estimated AWS cost: ${estimated_total:.2f}")
print(f"Project budget:     ${PROJECT_BUDGET:.2f}")
print(f"Budget remaining:   ${remaining:.2f}")

if remaining < 0:
    print("WARNING: estimated cost exceeds project budget")
else:
    print("Status: within estimated project budget")
