#!/usr/bin/env bash
# Copy the generated demo artifacts into the frontend so they get bundled.
#
# These are committed rather than built on CI: Vercel has no Anthropic key,
# no SQLite cache and no pipeline, so it cannot regenerate them. Run this
# after demo/run_pipeline.py or demo/build_cards.py changes the output.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p frontend/src/demo
cp output/people.json output/insights.json demo/config.json frontend/src/demo/
echo "baked $(ls frontend/src/demo | tr '\n' ' ')into frontend/src/demo/"
