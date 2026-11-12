# Recompilar el kernel de la Pico-Pi: WiFi (brcmfmac) conservando RPMsg

**2026-11-11** · **Nivel: compiló.** `build-kernel.sh prepare/build/package`
ejecutados en el PC de compilación sin errores. **Nada instalado en la tarjeta todavía.**

### Resultado de la compilación (2026-11-11)

- `Linux version 5.10.72-g7966a667bd89-dirty (usuario@pc) (arm-linux-gnueabi-gcc (GCC) 6.5.0, GNU ld 2.32) #1 SMP PREEMPT`
- `zImage` de 8 655 912 B; `brcmfmac.ko` + `brcmutil.ko`, `imx_rpmsg_tty.ko`,
  `imx_rpmsg_pingpong.ko`. vermagic idéntico al vivo:
  `5.10.72-g7966a667bd89-dirty SMP preempt mod_unload modversions ARMv7 p2v8`.
- Paquete: `~/kernel-wifi/kernel-wifi-5.10.72-g7966a667bd89-dirty.tar.gz`
  (11 937 012 B, sha256 `04b1ba1d…6da1b7`). `.config` y `Module.symvers` copiados
  a `kernel/` (`config-wifi`, `Module.symvers`).
- **Comparación de CRC (MODVERSIONS):** de los **1874** símbolos que usan los
  módulos *vivos* de la tarjeta, los 1874 existen en el kernel nuevo y **0**
  tienen CRC distinto. La ABI del árbol compilado coincide con la del kernel vivo.
- Solo se generó `imx7d-pico-pi-qca.dtb` (no el `-m4`); el plan usa el DTB vivo
  de la FAT, así que no bloquea.

**Consecuencia:** es probable que `brcmfmac.ko` cargue **sobre el kernel vivo,
sin cambiar el `zImage`** (vía A, abajo en §6). Es la prueba menos arriesgada:
no toca el arranque. Si falla, queda la vía B (`zwifi.img`) con consola serie.

Un apagón a mitad de la compilación dejó 136 objetos vacíos; se resolvió con
`make clean` y compilación desde cero.

## 1. Objetivo y principio de seguridad

Obtener un kernel **idéntico al vivo** más el driver WiFi `brcmfmac`, sin perder
RPMsg (ya verificado, `docs/RPMsg_Verificacion.md`).

Principio: **no se sustituye nada**. El kernel nuevo entra en la FAT **con otro
nombre**, al lado del actual; `uEnv.txt` decide cuál arranca. No se toca U-Boot,
ni el `zImage` actual, ni el DTB actual. Volver atrás es borrar una línea.

## 2. Lo que se sabe del kernel vivo

| Dato | Valor | De dónde |
|---|---|---|
| Versión | `5.10.72-g7966a667bd89-dirty #7 SMP PREEMPT`, 20-jun-2023 | `/proc/version` |
| Compilador | GCC 6.5.0 (`CONFIG_GCC_VERSION=60500`), Linaro 2018.12 gnueabihf | `.config`, `/proc/version` |
| Ruta original de las fuentes | `/home/usuario/kernel_build/linux-tn-imx` (usuario original; **ya no existe** en este WSL) | enlaces `build`/`source` de `/lib/modules` |
| Compresión | `CONFIG_KERNEL_LZO=y` → hace falta `lzop` en el host | `.config` |
| Módulos | `MODVERSIONS=y`, sin firma, sin compresión, sin carga forzada | `.config` |
| DTB | **no** va pegado al kernel (`ARM_APPENDED_DTB` apagado); U-Boot carga `imx7d-pico-pi-qca-m4.dtb` | `.config`, entorno U-Boot |
| WiFi | `CFG80211=y`, `MAC80211=y`, `WLAN_VENDOR_BROADCOM=y`, **`BRCMFMAC` sin activar** | `.config` |
| RPMsg | todo activo, `IMX_RPMSG_TTY=m`, `IMX_RPMSG_PINGPONG=m` | `.config` |
| Cómo elige U-Boot el kernel | `loadimage=fatload … ${image}`, con `image=zImage` → **`image` se puede cambiar desde `uEnv.txt`** | `(volcado local del entorno de U-Boot)` |

En este repo, **`kernel/`** guarda el `.config` exacto del kernel vivo
(`config-vivo`), el resultante con WiFi (`config-wifi`), su `Module.symvers`, el
DTB vivo (`imx7d-pico-pi-qca-m4.dtb`) y la calibración WiFi
(`brcmfmac4339-sdio.txt`, la calibración por placa: irreemplazable).

## 3. Materiales

| Pieza | Estado |
|---|---|
| Fuentes: `TechNexion/linux-tn-imx`, rama `tn-imx_5.10.72_2.2.0-stable` | **descargado** como tarball a `~/kernel-wifi/` (190 449 873 B; el `git clone` se cortó por la red) |
| Compilador cruzado GCC 6.5.0 | **instalado** en `~/opt/gcc-6.5.0-nolibc/arm-linux-gnueabi/` (kernel.org crosstool). **Usado** |
| `.config` del kernel vivo | **en el repo** |
| Calibración WiFi `.txt` | **en el repo** |
| Firmware WiFi `brcmfmac4339-sdio.bin` | **descargado** en `~/kernel-wifi/firmware/` (574 096 B, versión 6.37.39.113 de 2019). En `linux-firmware` vive como `cypress/cyfmac4339-sdio.bin`; la ruta `brcm/` da 404 |
| Paquetes del host: `bison flex lzop libssl-dev` | **instalados** (los instaló el usuario con `sudo apt`) |

Único paso que necesita al usuario:

    sudo apt install bison flex lzop libssl-dev bc libelf-dev

### Sobre el compilador: gnueabi vale, no hace falta gnueabihf

El Linaro `gnueabihf` original **ya no se puede descargar** (releases.linaro.org
redirige a una página web; el espejo S3 da 403). El de kernel.org es `gnueabi`.
Para compilar **el kernel** da igual: el kernel no enlaza con libc ni usa coma
flotante, y fija su propia ABI (`-mabi=aapcs-linux -msoft-float`). La diferencia
hf/no-hf solo importa para programas de usuario. Coincide además la versión
(6.5.0), que es lo que mira `CONFIG_GCC_VERSION`. Esto **corrige** el aviso de
`WiFi_Diagnostico.md`, que lo daba como riesgo.

## 4. Los tres riesgos y cómo se cubren

1. **Los parches `-dirty` perdidos.** El kernel vivo tenía cambios locales sin
   commit, y el commit `7966a667bd89` puede no ser la punta de la rama. Lo más
   probable es que afectaran al device tree. **Cobertura:** primer arranque con
   el **DTB vivo**, sin cambiarlo. El DTB nuevo se compila pero no se instala.
2. **CRC de símbolos.** Con `MODVERSIONS`, los módulos ya instalados solo cargan
   en el kernel nuevo si los CRC coinciden. **Cobertura:** se instalan **todos**
   los módulos recompilados, no solo `brcmfmac`, en un directorio aparte, y se
   conserva copia del directorio actual.
3. **Que no arranque.** **Cobertura:** consola serie + el `zImage` viejo intacto
   + la imagen completa de la eMMC ya descargada.

## 5. Compilar (en el PC de compilación)

    ./scripts/build-kernel.sh prepare   # extrae, aplica el .config vivo, activa BRCMFMAC
    ./scripts/build-kernel.sh build     # zImage + modules + dtbs  (~20-40 min, 4 núcleos)
    ./scripts/build-kernel.sh package   # ~/kernel-wifi/kernel-wifi-<release>.tar.gz

`prepare` hace solo estos cambios sobre el `.config` vivo:

    CONFIG_BRCMFMAC=m
    CONFIG_BRCMFMAC_SDIO=y
    CONFIG_RPMSG_CHAR=y                      # aditivo: /dev/rpmsgN
    CONFIG_LOCALVERSION="-g7966a667bd89-dirty"
    # CONFIG_LOCALVERSION_AUTO is not set

Lo último reproduce la **misma cadena de versión** que el kernel vivo (desde un
tarball no hay git que ponga el sufijo). Así `uname -r` no cambia y
`/lib/modules/5.10.72-g7966a667bd89-dirty/` sigue siendo el directorio válido.

**Revisar la salida de `prepare`:** `diffconfig` debe mostrar solo esas líneas (y
`BRCMUTIL`, que se arrastra solo). Si aparecen muchas más, la rama no corresponde
al kernel vivo y hay que parar.

## 6. Instalar en la tarjeta (sin sustituir nada)

### Vía A — solo módulos, kernel vivo intacto ✅ VERIFICADO FUNCIONANDO (2026-11-11)

**Resultado:** `modprobe brcmfmac` → rc 0, sin oops ni avisos; firmware
`BCM4339/2 … version 6.37.39.113 (r722271 CY)`; aparece **`wlan0`**
(MAC `28:ed:e0:xx:xx:xx`, la del OTP del chip, no la del `.txt`).
`iw list`: modos **managed, AP, IBSS, P2P**; combinación válida
`managed + AP` simultáneos en 1 canal. Escaneo: 6 redes en 2,4 y 5 GHz.
`imx_rpmsg_tty` se carga en cada arranque desde 2026-11-11 (`/etc/modules-load.d/rpmsg.conf`; verificado tras reinicio: 20/20 ecos). Sin reiniciar (mismo `boot_id`), `eth0` con la `.240` intacta y NetworkManager
ve `wlan0` como `disconnected` (sin perfil). RPMsg tras cargar el WiFi:
`/dev/ttyRPMSG0`, **20/20 ecos**.

Notas:
- `dmesg` avisa `no clm_blob available … limited channels` (aun así vio canales
  de 5 GHz) y busca primero `brcmfmac4339-sdio.fsl,pico-imx7d.txt` antes de caer
  al `.txt` genérico (~0,5 s de espera; inofensivo).
- Al estar en `/lib/modules` con `depmod`, **udev lo carga solo al arrancar**
  (modalias SDIO `02d0:4335`). **Verificado tras `poweroff` + encendido** (2026-11-11): `wlan0` a los ~19 s, RPMsg 20/20.
- Respaldo previo: `/root/lib-modules-pre-wifi-20261111.tgz` en la tarjeta.
- Nunca hizo falta la vía B: el `zImage` vivo sigue en uso.

Posible por la coincidencia total de CRC. No cambia `zImage`, ni `uEnv.txt`, ni
el DTB: si algo sale mal, basta un reinicio (o ni eso).

1. Respaldo de `/lib/modules/5.10.72-g7966a667bd89-dirty/` (tar en `/root/`).
2. Copiar **solo** `brcmutil.ko` y `brcmfmac.ko` a su ruta en
   `kernel/drivers/net/wireless/broadcom/brcm80211/`; `depmod -a`.
3. Firmware: `brcmfmac4339-sdio.bin` (+ el `.txt` ya existente) en `/lib/firmware/brcm/`.
4. `sudo modprobe brcmfmac` → mirar `dmesg`, `ip link` (`wlan0`), `iw list`.
5. Comprobar que `/dev/ttyRPMSG0` y la `.240` siguen bien.

Vuelta atrás: `modprobe -r brcmfmac brcmutil` y borrar los dos `.ko` + `depmod -a`.

### Vía B — kernel nuevo `zwifi.img` (solo si A falla, con consola serie)

    # 0. respaldo de los módulos actuales
    sudo cp -a /lib/modules/5.10.72-g7966a667bd89-dirty /lib/modules/respaldo-20230620

    # 1. módulos nuevos (mismo nombre de directorio: se sobrescribe, hay respaldo)
    sudo tar xzf kernel-wifi-*.tar.gz -C /tmp/kw
    sudo cp -a /tmp/kw/modules/lib/modules/5.10.72-g7966a667bd89-dirty /lib/modules/
    sudo depmod -a

    # 2. firmware WiFi
    sudo mkdir -p /lib/firmware/brcm
    sudo cp brcmfmac4339-sdio.bin brcmfmac4339-sdio.txt /lib/firmware/brcm/

    # 3. kernel nuevo AL LADO del viejo (nombre corto 8.3 para la FAT)
    sudo mount /dev/mmcblk2p1 /mnt/boot
    sudo cp /tmp/kw/boot/zImage-wifi /mnt/boot/zwifi.img
    sudo cp /mnt/boot/uEnv.txt /mnt/boot/uEnv.pre-wifi
    sudo sh -c 'printf "image=zwifi.img\n" >> /mnt/boot/uEnv.txt'    # LF, no CRLF
    sudo sync; sudo umount /mnt/boot

    # 4. reiniciar CON LA CONSOLA SERIE ABIERTA
    sudo reboot

La FAT tiene 23 MB libres; el `zImage` ocupa ~8,7 MB. Cabe.

⚠️ Paso 1: si el kernel nuevo no arranca y se vuelve al viejo, los módulos
recompilados pueden no cargarle. Entonces: restaurar `respaldo-20230620`.

## 7. Verificar

    uname -a                       # fecha de compilación nueva, misma release
    cat /proc/sys/kernel/random/boot_id
    sudo modprobe brcmfmac; dmesg | grep -i brcm
    ip link show wlan0; iw list | grep -A8 "Supported interface modes"
    sudo modprobe imx_rpmsg_tty; ls /dev/ttyRPMSG0      # RPMsg sigue vivo
    ls /dev/ttymxc*                # ttymxc4 y ttymxc6, nunca ttymxc5
    ip -4 -br addr show eth0       # la .240 sigue

## 8. Volver atrás

**Si Linux arrancó:** restaurar `uEnv.pre-wifi` sobre `uEnv.txt` y reiniciar.

**Si no arrancó** — consola serie, tecla al arrancar, y en el prompt `=>`:

    => setenv image zImage
    => run loadimage
    => run mmcboot

Eso arranca el kernel viejo **sin releer `uEnv.txt`**. Ya en Linux, quitar la
línea `image=` y restaurar los módulos. Último recurso: `ums 0 mmc 0` y la imagen
`backup.eMMC-20260816.img.gz`.

## 9. Después del WiFi

- Recompilar `imx_rpmsg_tty_file.ko` contra este árbol (el `.ko` actual tiene
  vermagic sin `-dirty`). El fuente está en el blog, post «Datos RPMsg a .txt».
- ~~Probar modo AP (`iw list`)~~ — hecho y verificado (`WiFi_Diagnostico.md`).
- Repetir en las otras dos placas: mismo paquete, **pero cada placa necesita su
  propio `brcmfmac4339-sdio.txt`** (lleva la MAC y la calibración).
