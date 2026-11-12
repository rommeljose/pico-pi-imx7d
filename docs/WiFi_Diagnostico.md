# Diagnóstico del WiFi de la Pico-Pi — por qué no hay `wlan0` y qué falta

**Fecha:** 2026-11-11 · **Método:** solo lectura por SSH, nada modificado.

## Veredicto en una línea

El chip WiFi **funciona a nivel de hardware**; lo que falta es **software**: el
driver `brcmfmac` **no está compilado en el kernel**, y faltan el firmware
binario y (en el sistema vivo) el fichero de calibración. No es avería; es una
pieza de kernel que quedó fuera al compilar.

## El dato que corrige la documentación

Toda la documentación del proyecto llama **«QCA»** (Qualcomm Atheros) al módulo
WiFi, heredando el nombre del device tree (`TechNexion PICO-IMX7D with QCA WLAN
module`). **Es incorrecto.** El silicio real es:

- **Módulo:** AP6335 (combo WiFi + Bluetooth). Confirmado por el fichero de
  calibración: `#AP6335_NVRAM_V1.5_03112014`.
- **Chip WiFi:** **Broadcom BCM4339**, SDIO vendor `0x02d0` device `0x4335`.
- **MAC WiFi de ESTA placa:** `00:90:4c:c5:12:38` (del fichero de calibración).

Esto importa porque el driver y el firmware de Broadcom no tienen nada que ver
con los de Atheros. El único driver wireless que el kernel sí trae es `ath10k`
(Atheros), que a este chip **no le sirve**.

> Nota: la confusión «QCA» viene del nombre del DTB (`imx7d-pico-pi-qca*.dtb`).
> Tenerlo presente al leer las notas del proyecto y `Tarjeta_Inventario.md`.

## Qué se comprobó (evidencia)

| Comprobación | Resultado |
|---|---|
| Interfaces de red | `lo`, `eth0`, `can0`, `can1`. **No existe `wlan0`** |
| Chip en bus SDIO | `mmc1: new high speed SDIO card at address 0001`, vendor `0x02d0` device `0x4335` — **el hardware responde** |
| Driver que lo reclama | **NINGUNO** en los tres nodos SDIO (`mmc1:0001:1/2/3`) |
| Módulos cargados | ninguno de wifi (`ath/qca/cfg80211/mac80211`) |
| `brcmfmac` en el árbol de módulos | **no existe** (`find` sin resultados; `modinfo` → not found) |
| Config del kernel | `CONFIG_CFG80211=y`, `CONFIG_MAC80211=y`, `CONFIG_WLAN_VENDOR_BROADCOM=y`, pero **`# CONFIG_BRCMFMAC is not set`** |
| Firmware `/lib/firmware/brcm` (sistema vivo) | **no existe el directorio** |
| rfkill | solo Bluetooth; no hay bloqueo de WiFi |

La base de la pila inalámbrica (cfg80211 + mac80211) **sí está**. Solo falta el
driver de dispositivo (`brcmfmac`) que se apoya en ella.

## Las tres piezas que hacen falta

1. **Fichero de calibración por placa** — `brcmfmac4339-sdio.txt`.
   **YA SE TIENE.** Rescatado en `/media/rootfs/lib/firmware/brcm/` (un disco
   externo sda3 con un rootfs de fábrica de abril 2023). Es la pieza
   irreemplazable: lleva la calibración de radio y la MAC de esta placa
   concreta. Hay que copiarlo a `/lib/firmware/brcm/` del sistema vivo.
   **Pendiente: respaldarlo en este repo antes de que se pierda** (el disco
   externo no es fiable como única copia).

2. **Firmware binario** — `brcmfmac4339-sdio.bin` (y opcional `.clm_blob`).
   FÁCIL. Es genérico, igual para todo BCM4339; viene en el paquete
   `linux-firmware` o del repo oficial `git.kernel.org/.../linux-firmware`.

3. **Driver `brcmfmac`** — EL OBSTÁCULO REAL. No se resuelve copiando un
   fichero: el kernel se construyó con `# CONFIG_BRCMFMAC is not set`. Hay que
   compilarlo contra ESالتE kernel exacto.

## El kernel: quién lo compiló y dónde está la fuente

Cadena de versión del kernel vivo:

    Linux version 5.10.72-g7966a667bd89-dirty (usuario@pc)
    (Linaro GCC 6.5-2018.12) #7 SMP PREEMPT Tue Jun 20 20:05:48 -04 2023

- **Se compiló**, en esta misma máquina, el **20-jun-2023**,
  con cross-compilador Linaro ARM `arm-linux-gnueabihf` 6.5.
- El sufijo `-dirty` indica que el árbol tenía cambios locales sin commit al
  compilar.
- **El árbol de fuentes NO está** ni en este WSL (`/home`, `/opt`,
  `/usr/local`, `/root`) ni en `D:\PROGRAMAS_VARIOS` (buscado 2026-11-11:
  `ARM_source` solo tiene el BSP de FreeRTOS del M4; no hay `linux-tn-imx`,
  `brcmfmac.ko`, `Module.symvers` ni `zImage` en todo `D:`). Tampoco el
  toolchain Linaro `gnueabihf`. Probablemente se borró tras compilar o estaba
  en una instalación WSL anterior. El WSL actual es más nuevo que junio 2023.
- **Consecuencia:** hay que **re-clonar** el kernel desde GitHub; no se recupera
  el árbol original `-dirty`, así que los parches locales de entonces (si los
  hubo) no se conocen. Se parte de la rama oficial.

## Repositorio oficial del kernel (encontrado)

- **Repo:** `github.com/TechNexion/linux-tn-imx` (NO `linux-fslc`).
- **Rama que corresponde a 5.10.72:** **`tn-imx_5.10.72_2.2.0-stable`**
  (commit `a9f88b2…`). Existe también `-next` y los tags
  `tn-hardknott_5.10.72-2.2.0_20220207` / `_20221202`.
- El commit exacto del kernel vivo es `7966a667bd89`; hay que ver si cae en esa
  rama o en los cambios locales `-dirty`.

## Plan recomendado (de menor a mayor riesgo)

**Camino limpio: compilar `brcmfmac` como módulo suelto, sin tocar el kernel
arrancable.**

1. Clonar `TechNexion/linux-tn-imx` rama `tn-imx_5.10.72_2.2.0-stable`.
2. Reproducir el `.config` del kernel vivo (está en `/proc/config.gz` de la
   tarjeta) y cambiar solo `CONFIG_BRCMFMAC=m` (+ `CONFIG_BRCMFMAC_SDIO=y`).
3. `make modules_prepare` + compilar solo `drivers/net/wireless/broadcom/brcm80211/`
   con el toolchain cruzado (mismo flujo que el M4, pero para ARM Linux: se
   necesita `arm-linux-gnueabihf-`, no el bare-metal del M4).
4. Copiar a la tarjeta: el `.ko` a `/lib/modules/$(uname -r)/…` + `depmod`, y el
   firmware `.bin` + `.txt` a `/lib/firmware/brcm/`.
5. `modprobe brcmfmac` y ver si aparece `wlan0`. Reversible: `rmmod` y borrar.

**Riesgo del módulo suelto:** si el commit `-dirty` tenía parches que cambian la
ABI, el `.ko` podría no cargar (`invalid module format`). Mitigación: el
`.config` y `Module.symvers` deben ser los del kernel vivo. Sin
`Module.symvers` original, la compatibilidad de símbolos no está garantizada.

**Camino alternativo (más riesgo):** recompilar el kernel entero con
`CONFIG_BRCMFMAC=y`. Mala idea sin consola serie: un kernel defectuoso deja la
tarjeta inarrancable y no hay rescate. **No hacerlo hasta tener `usbipd-win`.**

## Modo punto de acceso

Si `wlan0` arranca, el BCM4339 soporta **modo AP** (punto de acceso): una «isla
WiFi» a la que cualquiera se conecta con su teléfono sin instalar nada. Verificar
`iw list` → *Supported interface modes: AP* una vez cargado el driver.
(Verificado el 2026-11-11: ver más abajo.)

## Siguiente acción concreta

1. **Respaldar `brcmfmac4339-sdio.txt`** (la pieza irreemplazable) en este repo.
2. Decidir si se clona el kernel y se intenta el módulo suelto, o se espera a
   tener consola serie (`usbipd-win`) como red de seguridad antes de compilar.

---

## Requisito añadido (2026-11-11): si se recompila el kernel, habilitar RPMsg

Si se llega al **camino B** (recompilar el kernel entero para el WiFi), hay que
aprovechar y **dejar activado el soporte RPMsg** en la misma compilación, porque
es un pendiente de fondo del proyecto y recompilar dos veces no tiene sentido.

Config a verificar/activar en el `.config` antes de compilar:

    CONFIG_RPMSG=y
    CONFIG_RPMSG_CHAR=y          # /dev/rpmsgN en espacio de usuario
    CONFIG_RPMSG_VIRTIO=y
    CONFIG_IMX_REMOTEPROC=y      # remoteproc del i.MX7 para el M4
    CONFIG_REMOTEPROC=y
    # y, para el canal tty que se usa hoy:
    CONFIG_RPMSG_TTY=y           # si existe en 5.10; si no, el módulo imx_rpmsg_tty

**Ojo:** RPMsg no es solo kernel. Falta también el trabajo de **device tree**
(nodos m4/rpmsg y la memoria reservada), que es lo que las notas del proyecto marca como
pendiente. El kernel habilitado es condición necesaria, no suficiente.

**Contexto:** RPMsg es la vía M4↔A7; si hubiera que recompilar el kernel para el
WiFi, perderlo sería un retroceso.

---

## Lo que confirma el blog del proyecto (revisado 2026-11-11)

Leído el feed completo (70 posts, 2022-10 → 2026-01) de
`compilando-pico-pi-imx7.blogspot.com`. Autor: Ing. Rommel Contreras, tesis
«Electrocardiógrafo Portátil». Resumen de lo que **se usó** y lo que **no se
pudo lograr**, filtrado a lo que afecta nuestra recompilación de kernel.

### RPMsg NO es «solo documentado»: estuvo VERIFICADO FUNCIONANDO

El post más reciente, **«Guía de Inicio Rápido» (2026-01-22)**, es un manual de
operación de una plataforma ECG real sobre esta placa. El flujo probado:

    su                              # (contraseña root)
    insmod imx_rpmsg_tty_file.ko    # módulo Linux del canal RPMsg
    echo "w" > /dev/ttyRPMSG0       # el M4 arranca y envía datos del sensor
    echo "s" > /dev/ttyRPMSG0       # detiene el envío
    # los datos caen en /samba/public/datos_rpmsg.txt, se grafican con Kst

Es decir: canal A7↔M4 por RPMsg, con un módulo propio
(`imx_rpmsg_tty_file.c`, derivado de `imx_rpmsg_tty.c`) que escribe los mensajes
a un archivo «limpio». También funcionaron los ejemplos `rpmsg_pingpong` y
`str_echo` (string echo). Esto **matiza** el estado de las notas del proyecto («RPMsg solo
documentado»): en la plataforma del blog quedó operativo. La diferencia probable
es la **imagen/kernel**: el del blog se recompiló con remoteproc activado; el que
describe las notas del proyecto puede ser otra imagen. Hay que confirmar en cuál de las tres
placas está cada cosa.

### Cómo se habilitó (lo que usó)

- **Recompilar el kernel con remoteproc.** Viene **desactivado por defecto**. Se
  activa en `menuconfig` → **Device Drivers ⇒ Remote proc drivers**. Implica
  compilar kernel + módulos + **árbol de dispositivos** e instalar cada uno.
- **Toolchain: Linaro GCC 6.5-2018.12, variante `arm-linux-gnueabihf`**
  (hard-float). ⚠️ **Ojo con esto para el WiFi:** el crosstool que bajé de
  kernel.org es `…-nolibc-arm-linux-gnueabi` (**soft-float**, otra variante). El
  kernel vivo se construyó con **gnueabihf**. Antes de compilar el módulo
  `brcmfmac` conviene usar el mismo `gnueabihf` que usó él, para no arriesgar un
  desajuste de ABI. Revisar antes de dar por bueno el toolchain actual.
- **Imagen base:** `rescue-2020.12.a.0.xz` (04-feb-2023), kernel **5.10.72**, con
  **U-Boot 2018.03** (no el 2021.04). Esto coincide con nuestro kernel vivo.

### Lo que NO se pudo lograr (límite real del i.MX7, no error nuestro)

- **El framework RPROC completo no existe para el i.MX7.** NXP/TechNexion solo
  desarrollaron los drivers ampliados de remoteproc para el **i.MX8M (64 bits)**.
  En el i.MX7 **no** se puede «arrancar el firmware del M4 automáticamente desde
  un remoteproc de Linux»: hay que arrancarlo **desde U-Boot con `bootaux`**
  (que es justo lo que ya hace nuestro U-Boot). RPMsg sí; arranque/parada del M4
  gobernados por remoteproc, no.
- **No se logró parar el M4 limpiamente desde el A7.** Si se hace `rmmod` del
  módulo con el M4 aún emitiendo, VirtIO suelta en `dmesg`
  `virtio_rpmsg_bus virtio0: msg received with no recipient`. Workaround que
  usaron: resetear el sensor por GPIO. Lo ideal (parar el firmware del M4 por un
  mensaje RPMsg del A7) quedó pendiente.
- Las imágenes Ubuntu nuevas (`ubuntu-22.04.xz`, 07-jun-2023) **no botean tras
  instalar firmware en el M4**; por eso se quedó en la `rescue-2020.12.a.0`.

### Lección que afecta DIRECTAMENTE el camino A del WiFi (módulo suelto)

El post **«Módulos externos en Linux» (2023-05-02)** lo dice explícito:

> `make modules_prepare` **NO** compila `Module.symvers` aunque esté
> `CONFIG_MODVERSIONS`; por tanto hay que ejecutar **siempre una compilación
> completa del kernel** para que funcione el control de versiones del módulo.

Esto **confirma el riesgo** que ya anotamos para el `brcmfmac.ko` suelto: sin el
`Module.symvers` del kernel vivo (que se perdió con el árbol `-dirty`), un módulo
suelto puede ser rechazado. **Refuerza preferir el camino B** (compilación
completa del kernel) — que además es el que nos deja activar RPMsg + remoteproc
de una sola vez. Con consola serie ya disponible, el camino B es viable.

---

## RPMsg en el kernel vivo: YA ESTÁ (comprobado 2026-11-11, solo lectura)

Placa `192.168.1.240`, kernel `5.10.72-g7966a667bd89-dirty #7`.

| Comprobación | Resultado |
|---|---|
| Config | `CONFIG_RPMSG=y`, `CONFIG_RPMSG_VIRTIO=y`, `CONFIG_RPMSG_NS=y`, `CONFIG_REMOTEPROC=y`, `CONFIG_IMX_REMOTEPROC=y`, `CONFIG_HAVE_IMX_RPMSG=y` |
| Módulos de canal | `CONFIG_IMX_RPMSG_TTY=m` y `CONFIG_IMX_RPMSG_PINGPONG=m`; ambos `.ko` están en `/lib/modules/$(uname -r)/kernel/drivers/rpmsg/` |
| Device tree | nodo `/soc/bus@30800000/rpmsg`, `compatible = fsl,imx7d-rpmsg`, **`status = okay`** |
| Arranque | `imx rpmsg driver is registered.` y `virtio_rpmsg_bus virtio0: rpmsg host is online` |
| Bus | `virtio0` presente, con `rpmsg_ns` y `rpmsg_ctrl` |
| `/dev/ttyRPMSG0` | **no existe ahora**: ningún módulo tty cargado y el firmware actual del M4 (demo del LED) no anuncia canal RPMsg |
| No activados | `CONFIG_RPMSG_CHAR`, `CONFIG_RPMSG_CTRL`, `CONFIG_REMOTEPROC_CDEV` (no hay `/dev/rpmsgN` genérico; se usa el tty) |

**Conclusión:** el lado Linux de RPMsg está completo, kernel y device tree. El
«falta trabajo de device tree» de las notas del proyecto está superado en esta placa. Lo que
falta para verlo funcionar es cargar en el M4 un firmware RPMsg (`str_echo` o
`pingpong`) y hacer `modprobe imx_rpmsg_tty`. **No verificado funcionando hoy.**

**Aviso sobre `/home/ubuntu/imx_rpmsg_tty_file.ko`:** su vermagic es
`5.10.72-g7966a667bd89` y el kernel vivo es `…-dirty`. Esa diferencia normalmente
hace que `insmod` lo rechace. No se probó. Si falla, hay que recompilarlo.

**Para la recompilación:** partir del `/proc/config.gz` de la tarjeta ya conserva
todo RPMsg; basta añadir `CONFIG_BRCMFMAC=m` + `CONFIG_BRCMFMAC_SDIO=y`.
Opcional: `CONFIG_RPMSG_CHAR=y`.

## Resuelto (2026-11-11)

`brcmfmac.ko` + `brcmutil.ko` compilados en el PC de compilación desde `linux-tn-imx`
5.10.72 con el `.config` vivo, más el firmware `brcmfmac4339-sdio.bin`, cargaron
**sobre el kernel vivo** sin reiniciar. Aparece `wlan0`, escanea y soporta AP.
Detalle en `docs/Kernel_Recompilacion.md` §6, vía A.

## AP de prueba `PicoPi-AP` (2026-11-11)

Perfil NM **`ap-picopi`**: SSID `PicoPi-AP`, 2,4 GHz canal 6, WPA2-PSK (CCMP),
`ipv4.method shared` → `wlan0` = `10.42.0.1/24`, dnsmasq de NM sirve DHCP
`10.42.0.10–254`. La clave
está solo en el perfil de la tarjeta, no aquí. `eth0`/`.240` intactos.

- **Nivel:** el lado de la tarjeta está verificado (`iw` → `type AP`, `ssid PicoPi-AP`; dnsmasq
  activo). **Cliente verificado (2026-11-11):** un teléfono (Android) se conectó y recibió `10.42.0.216` por DHCP; enlace de 65 Mbit/s en ambos sentidos y 3/3 pings desde la tarjeta, **sin antena instalada**.
- **NAT (2026-11-11):** NM no consigue poner sus propias reglas, por dos razones:
  - El kernel vivo no tiene `NF_TABLES`, así que `iptables-nft` falla.
  - Tampoco tiene la tabla `filter` (`# CONFIG_IP_NF_FILTER is not set`), así que la variante legacy también falla a medias. Sí tiene `nat` y `MASQUERADE`.

  Arreglo aplicado:
  1. `update-alternatives --set iptables|ip6tables …-legacy`. Vuelta atrás: `--auto`.
  2. El dispatcher `/etc/NetworkManager/dispatcher.d/50-ap-nat`, que pone el `MASQUERADE` de `10.42.0.0/24` al subir `ap-picopi` y lo quita al bajar.

  Sin tabla `filter` no hay nada que bloquee el FORWARD, y `ip_forward=1` lo pone NM.
  **Ojo:** los clientes del AP también alcanzan la LAN de casa.
- **Arranque:** `autoconnect yes` desde 2026-11-11, **verificado en un reinicio**. El AP subió sin cable de red, el teléfono se reconectó solo y el `MASQUERADE` contó 32 paquetes y 6,4 kB de su tráfico. **Internet en el teléfono a través de `PicoPi-AP`: confirmado por el usuario.**
- Quitarlo: `nmcli connection delete ap-picopi`.
