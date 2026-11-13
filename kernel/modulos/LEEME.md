# Módulos RPMsg precompilados para el kernel de fábrica

Tres módulos para el kernel **`5.10.72-g7966a667bd89-dirty`**, el de la imagen
de fábrica de TechNexion para la Pico-Pi-i.MX7D (Ubuntu 22.04). Con ellos se
evita compilar el kernel para seguir la
[guía](../../docs/Guia_M4_RPMsg_SPI.md) (§5.3 y §6.1).

| Módulo | Qué aporta | ¿Lo trae la fábrica? |
|---|---|---|
| `rpmsg_char.ko` | `/dev/rpmsgN`: un endpoint RPMsg por nodo; un `read()` = un mensaje | **no** |
| `rpmsg_ctrl.ko` | `/dev/rpmsg_ctrl0`: crea esos endpoints por `ioctl`. Depende de `rpmsg_char` | **no** |
| `imx_rpmsg_tty.ko` | `/dev/ttyRPMSG0`, **sin volcar cada mensaje al log del kernel** | sí, pero **lo vuelca**: 1583 líneas en 35 s a 10 mensajes/s |

**Nivel: ✅ verificado.** Estos tres ficheros son, byte a byte, los que corren
en la placa de este proyecto desde el 2026-11-12 (mismas SHA-256). Allí se han
cargado en cada arranque, con el canal binario del instrumento a 10 bloques/s.

## Compatibilidad

    $ modinfo -F vermagic rpmsg_char.ko
    5.10.72-g7966a667bd89-dirty SMP preempt mod_unload modversions ARMv7 p2v8

- Solo sirven si `uname -r` da **exactamente** `5.10.72-g7966a667bd89-dirty`.
  Con otro kernel, `modprobe` los rechaza: compílalos tú
  ([`Kernel_Recompilacion.md`](../../docs/Kernel_Recompilacion.md)).
- El kernel usa `modversions`. Los 94 símbolos que importan `rpmsg_char` y
  `rpmsg_ctrl` tienen el mismo CRC que en el kernel de fábrica, comprobados
  contra su `Module.symvers`. Por eso cargan **sin cambiar el `zImage` ni el
  device tree, y sin reiniciar**.
- El device tree de fábrica (`imx7d-pico-pi-qca-m4.dtb`) ya declara el canal.
  El kernel crea `virtio0.rpmsg_ctrl.0.0` aunque no tenga driver, y
  `rpmsg_ctrl` es ese driver.

## Instalar

Comprueba la descarga y el kernel:

    sha256sum -c SHA256SUMS
    uname -r                    # 5.10.72-g7966a667bd89-dirty

Instala, guardando antes el `imx_rpmsg_tty.ko` de fábrica:

    D=/lib/modules/$(uname -r)/kernel/drivers/rpmsg
    sudo cp -n $D/imx_rpmsg_tty.ko /root/imx_rpmsg_tty.ko.fabrica
    sudo cp rpmsg_char.ko rpmsg_ctrl.ko imx_rpmsg_tty.ko $D/
    sudo depmod -a

Que carguen en cada arranque:

    printf 'imx_rpmsg_tty\nrpmsg_ctrl\n' | sudo tee /etc/modules-load.d/rpmsg.conf

Para usarlos ya, sin reiniciar:

    sudo modprobe rpmsg_ctrl                  # carga también rpmsg_char
    ls -l /dev/rpmsg_ctrl0

Si `imx_rpmsg_tty` ya estaba cargado, el cambio del log se nota en el
siguiente arranque. También se puede recargar en caliente con
`sudo modprobe -r imx_rpmsg_tty && sudo modprobe imx_rpmsg_tty`, siempre que
nada tenga abierto `/dev/ttyRPMSG0`.

Los **permisos**, para usarlos sin `root`, son una regla de udev y un servicio.
Ver §6.2 de la [guía](../../docs/Guia_M4_RPMsg_SPI.md).

**Deshacer:** borra `rpmsg_char.ko` y `rpmsg_ctrl.ko` de `$D` y devuelve
`/root/imx_rpmsg_tty.ko.fabrica` a su sitio. Después, `sudo depmod -a`, quita
`rpmsg_ctrl` de `/etc/modules-load.d/rpmsg.conf` y reinicia.

## De dónde salen (GPL v2)

Son módulos del kernel Linux, licencia **GPL v2**. Para reproducirlos o
modificarlos:

| Pieza | Dónde |
|---|---|
| Fuente | [`TechNexion/linux-tn-imx`](https://github.com/TechNexion/linux-tn-imx), rama `tn-imx_5.10.72_2.2.0-stable`, sin cambios en `rpmsg_char.c` ni `rpmsg_ctrl.c` |
| Único cambio en `imx_rpmsg_tty.c` | [`../imx_rpmsg_tty-sin-volcado.patch`](../imx_rpmsg_tty-sin-volcado.patch): `print_hex_dump` → `print_hex_dump_debug` |
| Configuración exacta | [`../config-modulos-rpmsg`](../config-modulos-rpmsg): la de fábrica con `CONFIG_RPMSG_CHAR=m` y `CONFIG_RPMSG_CTRL=m` |
| `Module.symvers` del kernel de fábrica | [`../Module.symvers`](../Module.symvers) |
| Compilador | GCC 6.5.0 `arm-linux-gnueabi` de kernel.org (crosstool), la misma versión con la que TechNexion compiló el kernel (`GCC: (GNU) 6.5.0` en los `.ko`) |
| Método | [`Kernel_Recompilacion.md`](../../docs/Kernel_Recompilacion.md) y [`Seccion_README_RPMsg.md`](../../docs/Seccion_README_RPMsg.md) |

> **Ojo con `config-wifi`**: esa es la del WiFi y tiene las dos opciones a `=y`.
> Con ella, `rpmsg_char` acabaría **dentro del `zImage`** y no saldría ningún
> `.ko`. Para estos módulos, usa `config-modulos-rpmsg`.
