# Lado Linux del «instrumento» (A7)

Programas que corren **en la placa**, en Linux, y hablan con el firmware
`instrumento.bin` del M4 (ver [`firmware-m4/`](../firmware-m4/LEEME.md) y
[`docs/M4_Instrumento_Bitacora.md`](../docs/M4_Instrumento_Bitacora.md)).
Cópialos todos al mismo directorio de la placa (por ejemplo `~`).

| Fichero | Qué hace |
|---|---|
| `visor_instrumento.py` | Visor GTK de la traza en vivo, con los eventos que detecta el M4 y botones para darle órdenes. `--consola` lo usa sin pantalla; con `VISOR_GUARDA=fichero` registra cada muestra (`t_unix índice valor`) |
| `visor.sh` | Lanza el visor a pantalla completa en el display de la placa (`visor.sh parar` lo cierra) |
| `instrumento.desktop`, `instrumento.svg` | Acceso directo e icono para el escritorio de la placa |
| `m4orden.py` | Envía **una** orden al M4 por `/dev/ttyRPMSG0` e imprime la respuesta (`m4orden.py "fuente adc corto 128 90"`) |
| `adc_captura.py` | Captura muestras **reales** del ADS1220 a través del M4 y da ruido (cuentas, µV), tasa real y pérdidas |
| `ads1220_prueba.py` | Prueba del ADS1220 **desde Linux** por `/dev/spidev2.0`, sin el M4: registros, corto, AVDD, temperatura |
| `ads1220_continuo.py` | Lectura continua desde Linux |
| `ads1220_drdy.py` | Prueba de un GPIO de J8 como entrada DRDY. Sirvió para descubrir que J8-36 y J8-11 **no** dejan entrar señales |

Requisitos en la placa: `python3-gi` (GTK 3) para el visor, nada más para las
pruebas desde Linux (hablan con `/dev/spidev2.0` por ioctl), y los módulos `imx_rpmsg_tty`, `rpmsg_char` y
`rpmsg_ctrl` (ver [`docs/Seccion_README_RPMsg.md`](../docs/Seccion_README_RPMsg.md)).

**El SPI es de uno solo a la vez.** Las pruebas `ads1220_*.py` necesitan
`/dev/spidev2.0` (driver ligado); el M4 lo necesita desligado:

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/unbind   # para el M4
    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/bind     # de vuelta a Linux

Antes de devolverlo a Linux, pon el M4 en `fuente sint`.
