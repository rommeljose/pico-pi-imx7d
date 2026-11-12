#!/bin/bash
# Compila un ejemplo del BSP para el M4 de la Pico-Pi-i.MX7D.
#
#   ./build-m4.sh                  -> hello_world, Release
#   ./build-m4.sh rpmsg            -> examples/imx7d_pico_m4/demo_apps/rpmsg
#   ./build-m4.sh hello_world debug
#   ./build-m4.sh hello_world release clean
#
set -euo pipefail

source "$(dirname "$0")/env-m4.sh" >/dev/null

APP="${1:-hello_world}"
CFG="${2:-release}"
ARMGCC="$BOARD_DIR/demo_apps/$APP/armgcc"

[ -d "$ARMGCC" ] || {
    echo "No existe $ARMGCC" >&2
    echo "Ejemplos disponibles:" >&2
    ls "$BOARD_DIR/demo_apps" >&2
    exit 1
}

cd "$ARMGCC"
if [ "${3:-}" = "clean" ]; then
    sh ./clean.sh
fi
sh "./build_${CFG}.sh"

OUT="$ARMGCC/$CFG"
echo
echo "=== Artefactos en $OUT ==="
ls -la "$OUT"/${APP}.bin "$OUT"/${APP}.elf 2>/dev/null || true
arm-none-eabi-size "$OUT/${APP}.elf"
echo
echo "Entry: $(arm-none-eabi-readelf -h "$OUT/${APP}.elf" | awk '/Entry point/{print $4}')  (vista M4)"
echo
echo "Para arrancarlo desde U-Boot (binario enlazado a TCM):"
echo "  fatload mmc 0 0x7F8000 ${APP}.bin"
echo "  dcache flush"
echo "  bootaux 0x7F8000"
