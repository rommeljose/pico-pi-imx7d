#!/bin/sh
# Uso: comparar-crc.sh <Module.symvers> <volcado.txt>
# volcado.txt se genera EN LA TARJETA con:
#   for m in $(lsmod | awk 'NR>1{print $1}'); do
#       modprobe --dump-modversions "$(modinfo -n $m)"; done | sort -u > volcado.txt
SYMVERS=$1; VOLCADO=$2
awk 'NR==FNR { crc[$2]=$1; next }
     { n++; if (!($2 in crc)) aus++; else if (crc[$2] != $1) dif++ }
     END { printf "símbolos usados por los módulos vivos: %d\n", n
           printf "presentes en el kernel nuevo: %d   ausentes: %d\n", n-aus, aus+0
           printf "CRC distintos: %d\n", dif+0 }' "$SYMVERS" "$VOLCADO"
