#!/bin/sh
# IP de rescate 192.168.1.240 en eth0, como salvavidas de NetworkManager.
# No se adelanta a NM: espera a que haya enlace y le da GRACIA segundos para
# activar eth0-main (que ya trae la .240). Solo la añade si falta, y vigila
# siempre: se autorrepara si algo la quita con la máquina en marcha.
IP=192.168.1.240/24   # AJUSTA a tu red: una IP libre, fuera del rango DHCP
IF=eth0
GRACIA=90      # s con enlace antes de intervenir
PASO=30        # s entre comprobaciones
con_enlace=0
while :; do
    if [ "$(cat /sys/class/net/$IF/carrier 2>/dev/null)" = 1 ]; then
        con_enlace=$((con_enlace + PASO))
        if [ $con_enlace -ge $GRACIA ] && ! ip -4 addr show dev $IF | grep -q " ${IP%/*}/"; then
            ip addr add $IP dev $IF && logger -t rescue-ip "faltaba ${IP}: añadida a $IF"
        fi
    else
        con_enlace=0
    fi
    sleep $PASO
done
