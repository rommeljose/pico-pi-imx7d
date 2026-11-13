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
