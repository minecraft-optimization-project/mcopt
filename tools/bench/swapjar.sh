#!/bin/bash
# swapjar.sh <installed-jar-basename> <replacement.jar|--restore>
# Moves the pack jar to /root/mcopt/mods-orig once, then installs the replacement.
set -eu
M=/root/mcopt/testserver/mods; O=/root/mcopt/mods-orig
name=${1:?jar name}; rep=${2:?replacement}
[ -f "$O/$name" ] || mv "$M/$name" "$O/$name"
rm -f "${M:?}/${name:?}" "${M:?}/mcopt-swap-${name:?}"
if [ "$rep" = --restore ]; then cp "$O/$name" "$M/$name"; else cp "$rep" "$M/mcopt-swap-$name"; fi
ls "$M" | grep -F -e "$name" -e mcopt-swap
