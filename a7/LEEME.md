# Lado Linux del «instrumento» (A7)

Programas que corren **en la placa**, en Linux, y hablan con el firmware
`instrumento.bin` del M4 (ver [`firmware-m4/`](../firmware-m4/LEEME.md) y
[`docs/M4_Instrumento_Bitacora.md`](../docs/M4_Instrumento_Bitacora.md)).
Cópialos todos al mismo directorio de la placa (por ejemplo `~`).

| Fichero | Qué hace |
|---|---|
| `visor_instrumento.py` | Visor GTK de la traza en vivo, con los eventos que detecta el M4 y botones para darle órdenes. Su segunda fila elige la fuente (sintética o ADS1220, entrada, ganancia, SPS) y el filtro de red, y reparte el SPI. La tercera navega por 5 min de historia: congelar, desplazar, zoom de tiempo y amplitud, y unidades (cuentas, µV, µm/s). Tocar la traza pone las marcas **P** y **S** y da `S−P` en segundos y kilómetros. Recuerda la configuración en `~/.config/instrumento.conf`. `--consola` lo usa sin pantalla; con `VISOR_GUARDA=fichero` registra cada muestra (`t_unix índice valor`) |
| `visor.sh` | Lanza el visor a pantalla completa en el display de la placa (`visor.sh parar` lo cierra) |
| `spi-m4`, `spi-m4.sudoers` | Ayudante que cede el ECSPI3 al M4 o lo devuelve a Linux, y la regla de `sudoers` que deja usarlo sin contraseña. Lo llama el visor |
| `instrumento.desktop`, `instrumento.svg` | Acceso directo e icono para el escritorio de la placa |
| `m4orden.py` | Envía **una** orden al M4 por `/dev/ttyRPMSG0` e imprime la respuesta (`m4orden.py "fuente adc corto 128 90"`) |
| `adc_captura.py` | Captura muestras **reales** del ADS1220 a través del M4 y da ruido (cuentas, µV), tasa real y pérdidas |
| `ads1220_prueba.py` | Prueba del ADS1220 **desde Linux** por `/dev/spidev2.0`, sin el M4: registros, corto, AVDD, temperatura |
| `ads1220_continuo.py` | Lectura continua desde Linux |
| `ads1220_drdy.py` | Prueba de un GPIO de J8 como entrada DRDY. Sirvió para descubrir que J8-36 y J8-11 **no** dejan entrar señales |

Requisitos en la placa: `python3-gi` (GTK 3) para el visor, nada más para las
pruebas desde Linux (hablan con `/dev/spidev2.0` por ioctl), y los módulos `imx_rpmsg_tty`, `rpmsg_char` y
`rpmsg_ctrl` (ver [`docs/Seccion_README_RPMsg.md`](../docs/Seccion_README_RPMsg.md)).

## Instalar el ayudante del SPI (una vez)

    sudo install -o root -g root -m 755 spi-m4 /usr/local/sbin/spi-m4
    sudo visudo -c -f spi-m4.sudoers && \
        sudo install -o root -g root -m 0440 spi-m4.sudoers /etc/sudoers.d/spi-m4

Comprueba **siempre** la regla con `visudo -c` antes de instalarla: un fichero
roto en `/etc/sudoers.d/` deja sin `sudo`. Si tu usuario no es `ubuntu`, cámbialo
en la regla.

Con el visor, el reparto del SPI es automático: cede el bus al elegir ADS1220 y
lo devuelve al volver a la sintética o al cerrarse.

**El SPI es de uno solo a la vez.** Las pruebas `ads1220_*.py` necesitan
`/dev/spidev2.0` (driver ligado); el M4 lo necesita desligado:

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/unbind   # para el M4
    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/bind     # de vuelta a Linux

Antes de devolverlo a Linux, pon el M4 en `fuente sint`.
