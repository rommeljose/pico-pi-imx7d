# Firmwares del M4 compilados localmente — 2026-11-11

Compilados en el PC de compilación con GNU Arm Embedded 10.3-2021.10, perfil `release`,
placa `imx7d_pico_m4`. Cada uno trae `.bin` (lo que se carga), `.elf` (símbolos)
y `.map`. Sumas en `SHA256SUMS`.

**Nivel:** todos **compilaron**. Solo los marcados están verificados en la tarjeta.

| Binario | Memoria | Nivel | Qué hace / cómo se observa |
|---|---|---|---|
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
TCM por `/dev/mem` (ver `docs/RPMsg_Verificacion.md`).
