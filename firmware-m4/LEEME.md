# Firmwares del M4 compilados localmente — 2026-11-11 (instrumento: 2026-11-13)

Compilados en el PC de compilación con GNU Arm Embedded 10.3-2021.10, perfil `release`,
placa `imx7d_pico_m4`. Cada uno trae `.bin` (lo que se carga), `.elf` (símbolos)
y `.map`. Sumas en `SHA256SUMS`.

**Nivel:** todos **compilaron**. Solo los marcados están verificados en la tarjeta.

| Binario | Memoria | Nivel | Qué hace / cómo se observa |
|---|---|---|---|
| `instrumento.bin` | TCM | ✅ **verificado** 2026-11-13 (en la FAT, `m4image=instrumento.bin`) | **v0.5, etapa 2 paso 4b**: `fuente adc [corto|ain01|avdd|temp] [pga] [sps]` / `fuente sint`. El ADS1220 marca el ritmo (20–600 SPS) y sus muestras van por el mismo camino que las sintéticas: STA/LTA, bloques binarios, visor. Lado Linux: `a7/adc_captura.py`. Ver `docs/M4_Instrumento_Bitacora.md` |
| `instrumento-e2p4a.bin` | TCM | ✅ **verificado** 2026-11-13 ; en la FAT como `instrumento-e2p4a.bin` | v0.4, etapa 2 paso 4a: `adc prueba` (lectura del ADS1220 por DRDYM) |
| `instrumento-e2p2.bin` | TCM | ✅ **verificado** 2026-11-12 ; en la FAT como `instrumento-e2p2.bin` | v0.3, etapa 2 paso 2: `spi lazo` / `spi suelta` (lazo interno del ECSPI3) |
| `instrumento-e1.bin` | TCM | ✅ **verificado** 2026-11-12 ; en la FAT como `instrumento-e1.bin` | Instrumento sintético, etapa 1 (v0.2): como la etapa 0, más bloques **binarios** por `/dev/rpmsgN` (`rpmsg_char`) con `seq` y flags, latido de 2 s, respuesta al origen. Lado Linux: `a7/visor_instrumento.py`. Ver `docs/M4_Instrumento_Bitacora.md` |
| `instrumento-e0.bin` | TCM | ✅ **verificado** 2026-11-12; también en la FAT como `instrumento-e0.bin` | Etapa 0 (v0.1), todo en texto por el tty. Fuente congelado en `instrumento-e0.c` |
| `rpmsg_str_echo_freertos_example.bin` | TCM | ✅ **verificado** 2026-11-11 (en la FAT como `rpmsg_echo.bin`) | Eco de cadenas por RPMsg. `modprobe imx_rpmsg_tty`, escribir/leer `/dev/ttyRPMSG0` |
| `blinking_imx_demo_gpt.bin` | TCM | ✅ **verificado** 2026-08-15 (idéntico byte a byte a `blink_tick.bin` de la FAT) | LED GPIO2_IO06 con `vTaskDelay`. Pese al nombre **no** usa GPT: es el fuente ya modificado |
| `rpmsg_pingpong_freertos_example.bin` | TCM | compiló | Ping-pong de enteros. Lado Linux: `modprobe imx_rpmsg_pingpong`, resultado en `dmesg` |
| `rpmsg_str_echo_bm_example.bin` | TCM | compiló | Eco sin RTOS (bare-metal). Mismo lado Linux que el eco FreeRTOS |
| `rpmsg_pingpong_bm_example.bin` | TCM | compiló | Ping-pong sin RTOS |
| `hello_world.bin` | TCM | compiló | Solo imprime por UART6 (J8 pin 8). Sin adaptador serie no se observa |
| `hello_world_ocram.bin` | OCRAM `0x20210000` (A7: `0x00910000`) | compiló | Igual, enlazado a OCRAM. **No vale `tcm_addr`**: hay que cargarlo a mano en U-Boot |
| `hello_world_ddr.bin` | DDR `0x9FF00000` | compiló | Igual, enlazado a DDR. Carga manual. Ojo: Linux usa RAM hasta `0x9FEFFFFF` |
| `sema4_demo.bin` | TCM | compiló | Semáforo hardware SEMA4 compartido con el A7 |
| `rand_wfi_imx7d.bin` | TCM | compiló | Demo de bajo consumo (`low_power_imx7d/rand_wfi`). **Usa GPT**: Linux le apaga ese reloj, esperar comportamiento errático |

**No compiló:** `sensor_demo` — pide `BOARD_I2C_FXAS21002_ADDR`,
`BOARD_I2C_FXOS8700_ADDR` y `BOARD_GPIO_SENSOR_*`, que el `board.h` de la Pico no
define (son sensores de la placa SDB de NXP; aquí no existen).

## Probar uno

    scp firmware-m4/<fichero>.bin ubuntu@192.168.1.240:/tmp/
    # en la tarjeta
    sudo mount /dev/mmcblk2p1 /mnt/boot
    sudo cp /tmp/<fichero>.bin /mnt/boot/<nombre-corto>.bin     # FAT: nombre corto
    sudo sed -i 's/^m4image=.*/m4image=<nombre-corto>.bin/' /mnt/boot/uEnv.txt
    sudo sync; sudo umount /mnt/boot; sudo reboot

Solo los enlazados a **TCM** sirven con este flujo. Comprobar la carga leyendo la
TCM por `/dev/mem` (ver `docs/RPMsg_Verificacion.md`). Ojo: solo la TCM; leer
registros de periféricos (el CCM, por ejemplo) por `/dev/mem` **colgó la placa**.

## El instrumento (`instrumento*.bin`)

Firmware propio, no un ejemplo del BSP: el M4 adquiere (señal sintética o el ADC
**ADS1220** por ECSPI3), detecta eventos con STA/LTA y manda bloques binarios a
Linux por RPMsg. Su fuente entra con el parche de [`bsp/`](../bsp/LEEME.md)
(`examples/imx7d_pico_m4/demo_apps/instrumento/`); el lado Linux está en
[`a7/`](../a7/LEEME.md). Historia y medidas en
[`docs/M4_Instrumento_Bitacora.md`](../docs/M4_Instrumento_Bitacora.md).

Compilado desde un clon nuevo con el parche aplicado, sale **el mismo código**;
el `.bin` difiere solo en las rutas absolutas de los ficheros fuente que guardan
los `assert` del BSP.
