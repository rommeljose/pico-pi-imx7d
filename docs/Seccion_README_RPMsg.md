<!--
  Sección preparada para incorporarla al README.md. Se mantiene aparte hasta
  entonces; al moverla, ajustar los enlaces relativos (quitar «../»).
-->

## RPMsg en la Pico-Pi: el módulo `imx_rpmsg_tty_file` y lo que enseñó

> **Autoría.** El módulo `imx_rpmsg_tty_file` lo escribió **rommeljose**, autor de
> este repositorio, en 2023, **sin ayuda de inteligencia artificial**, y lo
> documentó en el blog [Compilando Pico-Pi i.MX7](https://compilando-pico-pi-imx7.blogspot.com).
> Esta sección resume aquel trabajo y lo que se confirmó al retomarlo en 2026.

### El punto de partida: `imx_rpmsg_tty`

RPMsg es el buzón de mensajes entre los dos mundos del i.MX7: el Cortex-M4 con
FreeRTOS y Linux en los Cortex-A7. En el lado Linux, NXP ofrece el driver
**`imx_rpmsg_tty`** (`drivers/rpmsg/imx_rpmsg_tty.c`, GPL-2.0), que presenta el
canal como un puerto serie: **`/dev/ttyRPMSG0`**. Lo que el M4 envía se lee de
ese fichero; lo que se escribe en él le llega al M4.

### El módulo `imx_rpmsg_tty_file` (2023)

**Problema que resolvía.** El driver de NXP vuelca **cada mensaje recibido** al
log del kernel en hexadecimal (`print_hex_dump(KERN_DEBUG, …)` en
`rpmsg_tty_cb()`). Si los datos se recogen de ahí, llegan mezclados con la
información de depuración y hay que limpiarlos después.

**Solución.** Un módulo derivado del de NXP que, en el *callback* de recepción
`rpmsg_tty_cb()`, **escribe cada mensaje en un fichero** desde el propio kernel:

- abre el fichero en modo añadir (lo crea si no existe) y escribe con
  `kernel_write()`;
- comprueba su tamaño con `vfs_llseek()` y, al llegar a **10 MB**, lo trunca
  (`O_TRUNC`) para no llenar la eMMC;
- sigue entregando los datos al tty (`tty_flip_buffer_push()`), así que
  `/dev/ttyRPMSG0` funciona como antes.

Los datos quedan «limpios», y el fichero se puede leer **mientras se escribe**:
con `tail -f`, o graficándolo en vivo con **Kst**. Con este esquema se capturaron
datos de un **GPS serie** y, después, de un **sensor de electrocardiografía**
conectados al M4.

**Uso** ([Guía de Inicio Rápido](https://compilando-pico-pi-imx7.blogspot.com/2026/01/guia-de-inicio-rapido.html)):

    insmod imx_rpmsg_tty_file.ko
    echo "w" > /dev/ttyRPMSG0     # el M4 empieza a enviar
    echo "s" > /dev/ttyRPMSG0     # el M4 se detiene
    rmmod imx_rpmsg_tty_file

Entradas del blog: [RPMsg](https://compilando-pico-pi-imx7.blogspot.com/2023/05/rpmsg.html) ·
[Datos RPMsg a .txt](https://compilando-pico-pi-imx7.blogspot.com/2023/05/datos-rpmsg-un-txt.html) ·
[Datos RPMsg Plus](https://compilando-pico-pi-imx7.blogspot.com/2023/06/datos-rpmsg-plus.html).

### Los problemas que tenía, tal como los documentó su autor

1. **Los logs se saturaban.** El módulo heredó del driver de NXP las salidas de
   depuración, que seguían yendo a `dmesg`. Su autor lo advirtió en 2023:
   conviene comentarlas *«para que no se saturen los logs y disminuya el espacio
   de trabajo disponible en la eMMC»*.
2. **El M4 no se detenía con Linux.** En el i.MX7 el M4 lo arranca U-Boot
   (`bootaux`) y Linux no puede pararlo: el *framework* remoteproc completo solo
   existe para el i.MX8M. Consecuencias observadas:
   - con el M4 enviando, el apagado o el reinicio de Linux podía interrumpirse:
     había que hacer `rmmod` antes;
   - si se quitaba el módulo, el M4 seguía enviando a un canal sin destinatario y
     VirtIO llenaba `dmesg` de `virtio_rpmsg_bus virtio0: msg received with no
     recipient`.

   Remedio provisional: mantener el sensor en *reset* desde un GPIO de Linux.
   Remedio de fondo (firmware v2, «Datos RPMsg Plus»): **que el M4 obedezca
   órdenes de Linux**, `w` para empezar y `s` para parar y cerrar el canal.
3. **Al rearrancar había que enviar `W` tres veces seguidas**, atribuido al uso
   de los *slots* del firmware v2.
4. **El `vermagic` ata el módulo a un kernel concreto.** La copia binaria
   conservada declara `5.10.72-g7966a667bd89`, y el kernel de fábrica de la placa
   se identifica como `5.10.72-g7966a667bd89-dirty`. El kernel rechaza un módulo
   cuyo `vermagic` no coincide, así que hay que recompilarlo contra el kernel que
   corre. Cómo hacerlo con los mismos CRC: [`docs/Kernel_Recompilacion.md`](Kernel_Recompilacion.md).

### Lo que se confirmó en 2026

**El problema 1 era real y venía del driver de NXP.** Con un firmware del M4
enviando unos 10 mensajes por segundo y el `imx_rpmsg_tty.ko` de fábrica, el log
del kernel recibió **1583 líneas en 35 s**. Cada mensaje se parte en líneas de 16
bytes, y lo guardan **a la vez** el journal de systemd y rsyslog (`kern.log`,
`syslog`), ambos en la eMMC: del orden de **cientos de MB al día**.

Corrección: cambiar una sola llamada y recompilar el módulo **dentro del árbol**
del kernel:

```diff
-	print_hex_dump(KERN_DEBUG, __func__, DUMP_PREFIX_NONE, 16, 1,
+	print_hex_dump_debug(__func__, DUMP_PREFIX_NONE, 16, 1,
 			data, len,  true);
```

`print_hex_dump_debug()` solo genera código si el kernel tiene `DEBUG` o
`DYNAMIC_DEBUG`, y el de la placa no tiene ninguno. **Verificado**: 25 s
transmitiendo a 250 muestras/s → **0 líneas nuevas** en `dmesg` y en el journal.
Parche en [`kernel/imx_rpmsg_tty-sin-volcado.patch`](../kernel/imx_rpmsg_tty-sin-volcado.patch).

Dos detalles al recompilarlo:

- Compílalo como objetivo del árbol, `make drivers/rpmsg/imx_rpmsg_tty.ko`.
  Con `make M=drivers/rpmsg` kbuild lo trata como módulo **externo** y, al
  cargarlo, el kernel queda marcado (*tainted*) hasta el siguiente reinicio.
- El `vermagic` debe ser exactamente el del kernel que corre, `-dirty` incluido.

**El problema 2 se resuelve en el protocolo, como apuntaba el firmware v2.** Si el
M4 obedece una orden de parada, Linux no necesita poder apagarlo. El trabajo de
2026 sobre el M4 sigue esa línea: el firmware arranca **sin transmitir**, empieza
con una orden y, al cerrar, el programa de Linux le envía la orden de parar antes
de soltar el tty. El M4 sigue trabajando, pero no escribe en un canal que nadie
lee.

### Más allá del tty: `/dev/rpmsg0` sobre el kernel de fábrica (2026)

El tty sirve para empezar, pero **no conserva las fronteras de los mensajes**:
lo que el M4 envía como un bloque de 120 bytes puede leerse en Linux partido o
pegado al siguiente, y por eso hay que hablar en texto, con un `\n` al final de
cada línea. Para datos binarios, la vía estándar del kernel es **`rpmsg_char`**:
cada endpoint aparece como un `/dev/rpmsgN` donde **un `read()` devuelve
exactamente un mensaje** y un `write()` envía exactamente uno.

**El kernel de fábrica no lo trae, pero lo espera.** En la configuración del
kernel vivo, `CONFIG_RPMSG_CHAR` y `CONFIG_RPMSG_CTRL` están desactivadas y
ninguno de sus símbolos aparece en `/proc/kallsyms`. Sin embargo
`virtio_rpmsg_bus` ya crea el dispositivo `virtio0.rpmsg_ctrl.0.0`, con
`modalias rpmsg:rpmsg_ctrl`, y lo deja **sin driver**:

    ls /sys/bus/rpmsg/devices/            # …rpmsg_ctrl.0.0 aparece
    readlink /sys/bus/rpmsg/devices/virtio0.rpmsg_ctrl.0.0/driver    # vacío

Basta con compilar los dos drivers **como módulos** contra el árbol del kernel de
fábrica, con el mismo método que el WiFi
([`docs/Kernel_Recompilacion.md`](Kernel_Recompilacion.md)):

    scripts/config --module RPMSG_CHAR --module RPMSG_CTRL
    make olddefconfig && make -j$(nproc)        # incremental: ~20 s
    # drivers/rpmsg/rpmsg_char.ko y rpmsg_ctrl.ko

Comprobado el 2026-11-12: `vermagic` idéntico al del kernel vivo, `intree: Y`,
y **los 94 símbolos que importan, con el mismo CRC** que el kernel vivo. Se
copian a `/lib/modules/$(uname -r)/kernel/drivers/rpmsg/`, `depmod -a`,
`modprobe rpmsg_ctrl` (carga antes `rpmsg_char`, del que depende), y aparece
**`/dev/rpmsg_ctrl0`**, sin reiniciar y sin tocar el `zImage`. Para que se cargue
al arrancar, añade `rpmsg_ctrl` a `/etc/modules-load.d/`.

> ⚠️ Si tu árbol se preparó para compilar un kernel completo, revisa estas dos
> opciones: es fácil tenerlas a `=y`. Así, `rpmsg_char` acaba dentro del
> `vmlinux` que no vas a instalar, y no obtienes el `.ko`.

**Crear un endpoint** (como root, o con una regla de udev para
`/dev/rpmsg_ctrl0`):

```python
import os, fcntl, struct
RPMSG_CREATE_EPT_IOCTL  = 0x4028b501   # _IOW(0xb5, 1, struct rpmsg_endpoint_info)
RPMSG_DESTROY_EPT_IOCTL = 0xb502       # _IO(0xb5, 2)

ctrl = os.open("/dev/rpmsg_ctrl0", os.O_RDWR)
# struct rpmsg_endpoint_info { char name[32]; u32 src; u32 dst; }
fcntl.ioctl(ctrl, RPMSG_CREATE_EPT_IOCTL,
            struct.pack("32sII", b"mi-endpoint", 0x401, 0x0))
ep = os.open("/dev/rpmsg0", os.O_RDWR)     # src 0x401 (Linux) -> dst 0x0 (M4)
os.write(ep, b"\x01\x02\x03")               # un write = un mensaje
msg = os.read(ep, 512)                     # un read = un mensaje
fcntl.ioctl(ep, RPMSG_DESTROY_EPT_IOCTL)   # /dev/rpmsg0 desaparece
```

`/sys/class/rpmsg/rpmsg0/{name,src,dst}` confirman lo creado. La dirección `dst`
del M4 sale del `dmesg` al anunciarse el canal: `new channel: 0x400 -> 0x0`
significa Linux 0x400, M4 0x0.

**La trampa de la vuelta.** Probado con un firmware que respondía siempre a la
dirección del canal (`canal->dst`, la del tty): el mensaje enviado por
`/dev/rpmsg0` **llegó** al M4, pero la respuesta salió **por el tty**. En RPMsg
cada mensaje lleva la dirección de origen. **El firmware debe responder a la
dirección origen de lo que recibe** (en el ejemplo, 0x401), no a una fija. Con el
BSP FreeRTOS de NXP, esa dirección es el argumento `src` de `rpmsg_rtos_recv()`.

**Permisos: `udev` no basta para `/dev/rpmsg_ctrl0`.** En este kernel, el nodo
de control nace **sin clase** en sysfs (`SUBSYSTEM==""`, sin enlace
`subsystem`), y `udevadm test` falla con `Failed to clone sd_device object`. Una
regla de udev sí vale para los `/dev/rpmsgN`, que tienen clase:

    # /etc/udev/rules.d/60-rpmsg.rules  (solo KERNEL: el SUBSYSTEM no ayuda)
    KERNEL=="rpmsg[0-9]*", GROUP="dialout", MODE="0660"

Para el de control funciona un servicio *oneshot* que, tras
`systemd-modules-load`, espera al nodo y le hace `chgrp dialout` y
`chmod 0660`.

**Si tu programa muere sin despedirse**, por ejemplo con un `kill -9`:

- **El M4 llena el log.** El endpoint se destruye al cerrarse el descriptor. A
  partir de ahí, cada mensaje que el M4 envía a esa dirección produce un
  `msg received with no recipient`, que en `virtio_rpmsg_bus` es un `dev_warn`
  **sin límite de frecuencia**. La solución está en el protocolo: un **latido**.
  El programa de Linux envía `bin` cada 0,5 s, y si pasan 2 s sin latido el M4
  deja de enviar a esa dirección. Medido: 19 avisos y silencio.
- **Queda un nodo huérfano.** `/dev/rpmsgN` sigue existiendo: el endpoint muere,
  pero el nodo no. Si el programa crea uno nuevo cada vez que arranca, acumula
  `/dev/rpmsg1`, `/dev/rpmsg2`… Es mejor buscar primero en
  `/sys/class/rpmsg/rpmsg*/name` uno con tu nombre y reutilizarlo, y al salir
  limpiamente destruirlo con `RPMSG_DESTROY_EPT_IOCTL`.

**Reparto recomendado**, el que se usa en este proyecto:

| Canal | Para qué | Por qué |
|---|---|---|
| `/dev/ttyRPMSG0` (texto) | órdenes y respuestas | legibles y fáciles de depurar con `echo` y `cat` |
| `/dev/rpmsg0` (binario) | bloques de datos, con cabecera fija | fronteras intactas, sin convertir números a texto y de vuelta |

### Lecciones para quien use RPMsg en el i.MX7

- **Mira el log del kernel en cuanto pongas el canal a trabajar de verdad.** Con
  el driver de fábrica, cada mensaje del M4 acaba en la eMMC, dos veces.
- **El M4 no se para desde Linux**: diseña el firmware para que obedezca un
  «para» y un «sigue» desde el primer día.
- **Abre el tty en modo crudo y sin eco** (`stty -F /dev/ttyRPMSG0 raw -echo`):
  con el eco por defecto, el tty devuelve al M4 todo lo que el M4 envía.
- **Al cargar `imx_rpmsg_tty`, Linux envía `hello world!` al M4.** Lo hace el
  propio driver; el firmware debe saber ignorarlo o tratarlo como un saludo.
- Escribir ficheros desde un módulo del kernel (`filp_open`, `kernel_write`)
  funciona en 5.10, pero la práctica habitual hoy es leer `/dev/ttyRPMSG0` desde
  un programa de usuario. Además, las versiones recientes del kernel eliminaron
  `set_fs()`/`KERNEL_DS`, que este tipo de escritura usaba.
- **`imx_rpmsg_tty` no conserva las fronteras de los mensajes.** Para datos
  binarios, compila `rpmsg_char` y `rpmsg_ctrl` como módulos (ver arriba):
  funcionan sobre el kernel de fábrica.
- **Responde a la dirección origen de cada mensaje.** Si respondes a una
  dirección fija, las respuestas pueden acabar en otro endpoint.
- **Pon un latido en el protocolo.** Si el programa de Linux muere, el M4 no se
  entera, y cada mensaje sin destinatario deja una línea en el log.
