# Entorno de compilación para el Cortex-M4 de la Pico-Pi-i.MX7D
# Uso:  source scripts/env-m4.sh
#
# CMake fijado a la serie 3.x: NECESARIO Y COMPROBADO. Con CMake 4.0.3 la
# configuración aborta en CMakeLists.txt:5 (cmake_minimum_required VERSION 2.6)
# y no se genera binario.
#
# GCC fijado a GNU Arm Embedded 10.3-2021.10: por conservadurismo, NO por una
# rotura demostrada. Comprobado el 2026-08-15: GCC 13.2.Rel1 también compila
# hello_world sin errores (acepta -mapcs; solo avisa de stubs nosys y de un
# segmento LOAD con permisos RWX). Se mantiene 10.3 como referencia por ser
# más cercano a la época del BSP (2015-2016) y porque ningún binario se ha
# verificado aún en la tarjeta. Si algún día conviene subir, 13.2 es candidato
# real, pero revalidar en hardware.

# Raíz de este repositorio (el script se carga con «source»).
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export ARMGCC_DIR="${ARMGCC_DIR:-$HOME/opt/gcc-arm-none-eabi-10.3-2021.10}"
# CMake 3.x: el del sistema si es 3.x (Ubuntu 24.04 trae 3.28.3); si no, uno
# descomprimido en ~/opt, que se antepone al PATH.
export CMAKE_DIR="${CMAKE_DIR:-$HOME/opt/cmake-3.28.3-linux-x86_64}"
[ -d "$CMAKE_DIR/bin" ] && PATH="$CMAKE_DIR/bin:$PATH"
export PATH="$ARMGCC_DIR/bin:$PATH"

# BSP de TechNexion clonado dentro del repo (ver bsp/LEEME.md).
export BSP_DIR="${BSP_DIR:-$REPO_DIR/freertos-tn}"
# Placa correcta para la Pico-Pi. NO usar imx7d_sdb_m4 (ese es el SDB de NXP).
export BOARD_DIR=$BSP_DIR/examples/imx7d_pico_m4

echo "ARMGCC_DIR = $ARMGCC_DIR"
echo "cmake      = $(cmake --version | head -1)"
echo "arm-gcc    = $(arm-none-eabi-gcc -dumpversion)"
echo "BOARD_DIR  = $BOARD_DIR"
