#!/bin/bash
# ab.sh <installed-jar> <label> <variant.jar|--orig>... -- [bench args...]
# Runs the bench once per variant (labels <label>-A, -B, ...) from the same template world,
# then restores the pack's original jar.
set -eu
T=/root/mcopt/tools; jar=$1; label=$2; shift 2
variants=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do variants+=("$1"); shift; done
[ $# -gt 0 ] && shift
letters=(A B C D E F)
for i in "${!variants[@]}"; do
  v=${variants[$i]}
  python3 $T/bench.py stop
  if [ "$v" = --orig ]; then $T/swapjar.sh "$jar" --restore; else $T/swapjar.sh "$jar" "$v"; fi
  echo "== ${letters[$i]}: $v"
  python3 $T/bench.py run --label "$label-${letters[$i]}" "$@"
done
python3 $T/bench.py stop
$T/swapjar.sh "$jar" --restore
