#!/bin/sh
# Lanza el visor del instrumento en la pantalla de la Pico-Pi (o lo para).
#   visor.sh          arranca (pantalla completa) en el display :0
#   visor.sh parar    lo cierra (el visor deja al M4 en «pausa» al salir)
DIR=$(dirname "$(readlink -f "$0")")
pkill -TERM -f "^python3 $DIR/visor_instrumento.py" 2>/dev/null && sleep 1
[ "$1" = parar ] && exit 0
export DISPLAY=:0 XAUTHORITY="$HOME/.Xauthority"
setsid python3 "$DIR/visor_instrumento.py" "$@" >/tmp/visor.log 2>&1 </dev/null &
