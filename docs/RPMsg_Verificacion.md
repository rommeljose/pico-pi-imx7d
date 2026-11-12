# RPMsg A7 ↔ M4: verificado funcionando

**2026-11-11** · placa `192.168.1.240` · kernel `5.10.72-g7966a667bd89-dirty`.

## Resultado

    TX 'hola M4, soy el A7'       -> RX 'hola M4, soy el A7'        OK 6.01 ms
    TX 'prueba RPMsg 2026-11-11'  -> RX 'prueba RPMsg 2026-11-11'   OK 6.37 ms
    104/104 ecos correctos; latencia min 4.40 · mediana 4.88 · max 14.04 ms

Mensajes de 1 a 100 bytes escritos en `/dev/ttyRPMSG0` desde Linux; el M4
(FreeRTOS, `str_echo_freertos`) los devolvió idénticos.

## Qué había ya y qué se añadió

- **Ya estaba** (no se tocó): `CONFIG_RPMSG=y`, `CONFIG_RPMSG_VIRTIO=y`,
  `CONFIG_IMX_REMOTEPROC=y`, `CONFIG_IMX_RPMSG_TTY=m`; nodo de device tree
  `/soc/bus@30800000/rpmsg` en `okay`, `reg = <0x9fff0000 0x10000>`.
- **Se añadió:** solo el firmware del M4.

Comprobación previa obligatoria: los anillos del firmware
(`platform_info.c`: `VRING0_BASE 0x9FFF0000`, `VRING1_BASE 0x9FFF8000`) coinciden
con el `reg` del device tree y quedan fuera de la RAM de Linux
(`System RAM 80000000-9fefffff`). El BSP `imx7d_pico_m4` ya viene ajustado a los
512 MB de esta placa; el de `sdb` (1 GB) usaría otras direcciones.

## Procedimiento

    # en la máquina de desarrollo
    ./scripts/build-m4.sh rpmsg/str_echo_freertos release clean
    #   → .../str_echo_freertos/armgcc/release/rpmsg_str_echo_freertos_example.bin
    #     21 372 B, TCM, entry 0x1FFF82FD
    #     sha256 dd7a635f69d405cc0ed9d82edb6bf0a360ebc8c98f4f4b3a1a149f822fb25c24
    scp …_example.bin ubuntu@192.168.1.240:/tmp/rpmsg_echo.bin

    # en la tarjeta
    sudo mount /dev/mmcblk2p1 /mnt/boot
    sudo cp /tmp/rpmsg_echo.bin /mnt/boot/
    sudo cp /mnt/boot/uEnv.txt /mnt/boot/uEnv.pre-rpmsg
    sudo sed -i 's/^m4image=.*/m4image=rpmsg_echo.bin/' /mnt/boot/uEnv.txt
    sudo sync; sudo umount /mnt/boot; sudo reboot

    # tras el arranque
    sudo modprobe imx_rpmsg_tty        # aparece /dev/ttyRPMSG0
    # abrir el tty en modo raw, escribir y leer el eco

Evidencia en `dmesg`:

    virtio_rpmsg_bus virtio0: creating channel rpmsg-openamp-demo-channel addr 0x0
    imx_rpmsg_tty virtio0.rpmsg-openamp-demo-channel.-1.0: new channel: 0x400 -> 0x0!

## Comprobar qué firmware tiene el M4, byte a byte

La TCM se lee desde Linux por `/dev/mem` en `0x7F8000` (32 KiB) y se compara con
el `.bin` de la FAT. Resultado aquí: 21 372/21 372 bytes iguales. Sirve para
confirmar un despliegue sin depender del LED. **Solo lectura**: escribir ahí
corrompe el firmware en marcha.

## Estado en que quedó la tarjeta

- `m4image=rpmsg_echo.bin`. El LED de usuario **ya no parpadea**: este firmware
  no lo toca.
- Volver al demo del LED:
  `sudo cp /mnt/boot/uEnv.pre-rpmsg /mnt/boot/uEnv.txt` y reiniciar.
- `imx_rpmsg_tty` no se carga solo al arrancar; hay que hacer `modprobe`.
- El módulo imprime cada mensaje recibido en `dmesg` (`rpmsg_tty_cb…`); con
  tráfico alto llena el log.

## Pendiente

- La salida `PRINTF` del M4 (UART6, J8 pines 8/10) no se observó.
- `imx_rpmsg_tty_file.ko` de `/home/ubuntu` tiene vermagic sin `-dirty`; no
  probado.
- Las otras dos placas no se han revisado.
