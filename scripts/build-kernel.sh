#!/bin/bash
# Recompila el kernel 5.10.72 de la Pico-Pi-i.MX7D añadiendo el WiFi (brcmfmac)
# y conservando RPMsg. Ver docs/Kernel_Recompilacion.md.
#
#   ./build-kernel.sh prepare    -> extrae fuentes, aplica el .config de la tarjeta
#   ./build-kernel.sh build      -> zImage + módulos + dtbs
#   ./build-kernel.sh package    -> empaqueta en ~/kernel-wifi/salida/
#
# NO instala nada en la tarjeta. Eso es manual y está en el documento.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-$HOME/kernel-wifi}"
TARBALL=$WORK/linux-tn-imx-5.10.72.tar.gz
SRC=$WORK/linux-tn-imx
OUT=$WORK/salida
CFG_VIVO=$REPO/kernel/config-vivo     # el /proc/config.gz de la tarjeta

export ARCH=arm
export CROSS_COMPILE="${CROSS_COMPILE:-$HOME/opt/gcc-6.5.0-nolibc/arm-linux-gnueabi/bin/arm-linux-gnueabi-}"
# Reproducir EXACTAMENTE la cadena de versión del kernel vivo, para que el
# directorio /lib/modules y los módulos ya instalados sigan valiendo.
RELEASE_SUFFIX="-g7966a667bd89-dirty"
J=$(nproc)

need() { command -v "$1" >/dev/null || { echo "FALTA: $1  (sudo apt install $2)" >&2; MISSING=1; }; }
check_host() {
    MISSING=0
    need bison bison; need flex flex; need lzop lzop; need bc bc
    [ -f /usr/include/openssl/ssl.h ] || { echo "FALTA: libssl-dev" >&2; MISSING=1; }
    [ -x "${CROSS_COMPILE}gcc" ] || { echo "FALTA el compilador cruzado: ${CROSS_COMPILE}gcc" >&2; MISSING=1; }
    [ "$MISSING" = 0 ] || exit 1
}

case "${1:-}" in
prepare)
    check_host
    [ -d "$SRC" ] || { mkdir -p "$SRC"; tar xzf "$TARBALL" -C "$SRC" --strip-components=1; }
    cd "$SRC"
    cp "$CFG_VIVO" .config
    # Único cambio funcional: el driver WiFi como módulo.
    scripts/config --module BRCMFMAC --enable BRCMFMAC_SDIO
    # Opcional y aditivo: /dev/rpmsgN genérico además del tty.
    scripts/config --enable RPMSG_CHAR
    # Versión fija: sin git no hay sufijo automático, se pone a mano.
    scripts/config --disable LOCALVERSION_AUTO --set-str LOCALVERSION "$RELEASE_SUFFIX"
    make olddefconfig
    echo; echo "== release que saldrá =="; make -s kernelrelease
    echo "== diferencias contra el kernel vivo =="
    scripts/diffconfig "$CFG_VIVO" .config || true
    echo "== RPMsg sigue activo? =="
    grep -E "^CONFIG_(RPMSG|RPMSG_VIRTIO|IMX_REMOTEPROC|HAVE_IMX_RPMSG|IMX_RPMSG_TTY|IMX_RPMSG_PINGPONG|BRCMFMAC|BRCMFMAC_SDIO|BRCMUTIL)=" .config
    ;;
build)
    check_host
    cd "$SRC"
    make -j"$J" zImage modules dtbs 2>&1 | tee "$WORK/build.log" | tail -30
    ls -la arch/arm/boot/zImage arch/arm/boot/dts/imx7d-pico-pi*.dtb Module.symvers
    ;;
package)
    cd "$SRC"
    REL=$(make -s kernelrelease)
    rm -rf "$OUT"; mkdir -p "$OUT/modules" "$OUT/boot"
    make -s modules_install INSTALL_MOD_PATH="$OUT/modules" INSTALL_MOD_STRIP=1
    rm -f "$OUT/modules/lib/modules/$REL/build" "$OUT/modules/lib/modules/$REL/source"
    cp arch/arm/boot/zImage "$OUT/boot/zImage-wifi"
    cp arch/arm/boot/dts/imx7d-pico-pi*.dtb "$OUT/boot/" 2>/dev/null || true
    cp .config "$OUT/config-$REL-wifi"; cp Module.symvers System.map "$OUT/"
    ( cd "$OUT" && sha256sum boot/* > SHA256SUMS && tar czf "$WORK/kernel-wifi-$REL.tar.gz" . )
    echo "Paquete: $WORK/kernel-wifi-$REL.tar.gz"; ls -la "$OUT/boot"
    find "$OUT/modules" -name "brcm*.ko" -o -name "imx_rpmsg*.ko"
    ;;
*)
    sed -n 2,10p "$0"; exit 1 ;;
esac
