# Ruta de actualización del SO de la Pico-Pi, sin romper lo existente

Diagnóstico levantado el **2026-08-15** contra la tarjeta.
El estado resultante del hardware y del software está en
[`Tarjeta_Inventario.md`](Tarjeta_Inventario.md); este documento cuenta **cómo se
llegó ahí y por qué**, que es lo que hay que releer antes de repetir la
operación.

> ⚠️ **Registro histórico: la parte de red quedó superada el 2026-08-16.**
> Todo lo que sigue describe fielmente lo que se hizo y se verificó el
> **2026-08-15**, cuando se dejó a **ifupdown como único gestor** de `eth0` con
> `managed=false`. Al día siguiente **se invirtió el reparto**: ahora el único
> gestor es **NetworkManager**, con el perfil `eth0-main`, y la dirección DHCP
> pasó de `.252` a `.251`.
>
> No se ha reescrito nada de este documento: es el registro de aquel día. Para el
> **estado actual** de la red, ver
> [`Tarjeta_Inventario.md` §7](Tarjeta_Inventario.md).
>
> Lo que sigue vigente sin matices es el **método**, que es lo que de verdad hay
> que releer: respaldos primero, reversión armada con `systemd-run --on-active`,
> el cambio desacoplado de la sesión SSH, verificar, y solo entonces cancelar la
> reversión. Ese método es el que se volvió a usar el 16.

---

## ✅ ESTADO: RUTA COMPLETADA EL 2026-08-15

Todas las fases se ejecutaron y verificaron el mismo día. Resultado:

| | Antes | Después |
|---|---|---|
| Versión | Ubuntu 22.04 LTS | **Ubuntu 22.04.5 LTS** |
| Paquetes actualizados | listas de 2023-09-13 | **446 actualizados, 5 nuevos, 0 eliminados** — de ellos **328 de seguridad** |
| Actualizables pendientes | 446 | **0** |
| Unidades fallidas | `dnsmasq` | **0** |
| Kernel | `5.10.72-…-dirty` | **sin tocar** (apt no lo gestiona) |
| Espacio libre en `/` | 1.4 G | 1.4 G (tras limpiar cachés) |

Se hizo en ~16 min con `systemd-run` para desacoplar la operación de la sesión
SSH, con `--force-confold` para conservar toda la configuración local. `EXIT=0`,
`dpkg --audit` limpio, y **toda la configuración propia sobrevivió** (incluido
el `managed=false`, los timers de apt frenados y `rescue-ip`).

Los 7 «errores» del registro resultaron benignos: dos avisos de `dpkg` por
directorios de `ubuntu-advantage` no vacíos, cuatro del `dnsmasq` ya conocido, y
un preset de `samba-ad-dc` que ya estaba enmascarado.

Reinicio posterior superado (`boot_id` `b88085ad…` → `fbbf38c2…`), con el
arranque del M4 intacto.

### Y después: la partición de arranque estaba al 100 %

Revisando el espacio de la eMMC apareció un problema que no estaba en el plan:

```
/dev/mmcblk2p1   32M   32M usados   3.0K libres   100%
```

Solo tres kilobytes. Lo ocupaba `ubuntu_22.04_All_eMMC_<usuario>.img` (23.5 MB), un
resto de flasheo. Se comprobó que **U-Boot no lo referencia**: la única variable
que carga un fichero así es `loadfit=fatload … tnrescue.itb`, y `tnrescue.itb` ni
siquiera está presente.

Se retiró junto con `test_borrar.elf` (U-Boot solo carga el `.bin`), con copia
triple verificada por MD5 —en el pendrive `/mnt/varios/respaldo-arranque/` con un
`LEEME.txt`, en `(respaldo local, fuera de este repo)`, y dentro de la imagen completa de
la partición. Resultado: **29 % usada, 23 MB libres**.

⚠️ **`test_borrar.bin` NO se puede borrar.** Es a lo que apunta `m4image`. Si
faltara, `loadm4image` falla, `mcu` queda vacío y U-Boot buscaría
`imx7d-pico-pi-qca.dtb`, que **no existe en la partición** → se rompería el
arranque de Linux.

Tercer reinicio de verificación superado (`fbbf38c2…` → `0c9d8346…`), con UART6
todavía `disabled`, o sea con el DTB `-m4` cargado y `m4boot` funcionando.

**Salud de la eMMC** (fabricada 12/2017): `life_time = 0x02 0x01` (10-20 % de
vida consumida en el primer tipo de celda, <10 % en el segundo),
`pre_eol_info = 0x01` (normal). Ayuda que el swap esté en el pendrive USB.

### Pendiente

La Fase H de unificar el cliente DHCP ya está hecha, pero **no se ha probado un
corte de alimentación real** — ahí se pierde el RTC, que no tiene pila. Y sigue
sin abordarse un reloj de precisión (GPS/PPS) para usos que lo necesiten.
*(El corte real se superó el 2026-11-11.)*

---

---

## 0. Corrección del punto de partida: el DNS nunca estuvo roto

La premisa era "resolver lo del DNS". Los datos decían otra cosa:

| Prueba (antes) | Resultado |
|---|---|
| `systemd-resolved` | **activo y bien configurado** — recibía `192.168.1.1` por DHCP |
| Consulta cruda a `192.168.1.1:53` | respondía, pero **rcode=2 (SERVFAIL)** |
| `ping 8.8.8.8` | `From 192.168.1.1 **Destination Net Unreachable**` |
| `ping 192.168.1.1` | **ok** desde ambas IP de la tarjeta |

El gateway respondía explícitamente que no tenía ruta: **no era resolución, era
falta de salida a Internet en la LAN**. Arreglar `systemd-resolved` no habría
cambiado nada.

**Confirmado al conectar el router a la nube (2026-08-15 ~14:00):**

```
ping 8.8.8.8 · 1.1.1.1 · 91.189.91.83   →  OK
DNS (gateway, 8.8.8.8, resolver local)  →  rcode=0, 6 respuestas
HTTP a jammy-security                   →  200
```

Sin tocar un solo fichero de la tarjeta. Queda demostrado que la pila de red y
de resolución estaban correctas desde el principio.

### `dnsmasq` es ruido, no un problema

```
dnsmasq: failed to create listening socket for port 53: Address already in use
```

Choca con `systemd-resolved`, que ya ocupa `127.0.0.53:53` y hace el trabajo.
`dnsmasq` **nunca ha llegado a arrancar** y no hace falta. Su estado `failed`
lleva años siendo cosmético.

### Efecto secundario: el reloj se corrigió solo

Estaba en `2023-03-02`. Al aparecer la red, `ntp-systemd-netif.path` disparó la
sincronización:

```
System clock synchronized: yes
RTC time: 2026-08-15 18:01:48 UTC
```

**Pero el RTC `snvs_rtc` no tiene pila**: al cortar la alimentación volverá a
1970 y dependerá de que haya red al arrancar. Ver Fase 5.

### Deuda menor: dos clientes DHCP sobre `eth0`

`eth0` tiene **dos direcciones, ambas concesiones DHCP válidas**:
`192.168.1.253/24` (primaria) y `192.168.1.252/24` (secundaria). Causa:
**NetworkManager y `networking`/ifupdown activos a la vez**, con
`/etc/network/interfaces` declarando `iface eth0 inet dhcp`.

Hoy es inofensivo. Pero conviene saberlo: **si algún día se limpia, hay que
recordar que el acceso SSH entra por la `.252`, que es la secundaria.**

---

## 1. 🔴 Urgente: hay una cuenta atrás activa

`unattended-upgrades` está habilitado y llevaba años inerte por falta de red.
Al restaurarse Internet se ejecutó de inmediato:

```
2026-08-15 14:00:37  Starting unattended upgrades script
2026-08-15 14:00:47  No packages found that can be upgraded unattended
```

No hizo nada **solo porque el `pkgcache` es del 2023-09-13**. Pero:

| Temporizador | Próximo disparo | Qué hace |
|---|---|---|
| `apt-daily.timer` | **hoy 22:24** (~8 h) | refresca las listas de paquetes |
| `apt-daily-upgrade.timer` | **mañana 06:14** (~16 h) | instala, ya con listas frescas |

Es decir: **esta noche se instalarán ~3 años de actualizaciones sin
supervisión**, sobre una raíz con 1.4 G libres y sin consola serie para
rescatar. Hay que frenarlo antes.

**Comando (pendiente de tu visto bueno):**

```bash
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
sudo systemctl mask unattended-upgrades.service
```

Riesgo nulo y reversible con `unmask` / `enable`. No corta red ni arranque.

---

## 2. Restricción que gobierna todo el plan

**Sin consola serie, un arranque roto no es recuperable en remoto.** El rescate
exigiría flasheo por USB OTG con `uuu`, que necesita `usbipd-win` desde Windows
y acceso físico. Cada fase debe: ser reversible por sí sola, no tocar la ruta de
arranque, y no cortar la red mientras se aplica.

### Buena noticia estructural

```
dpkg -l | grep linux-image   →  NO hay paquete de kernel
ls /boot                      →  VACÍO
```

El kernel (`zImage`), el DTB y U-Boot viven **solo en la partición FAT
`mmcblk2p1`**, cargados por U-Boot. **`apt` no puede romper el arranque**,
porque no gestiona ninguna de esas piezas. Esto quita de encima el riesgo
clásico de actualizar un embebido.

### Intocables

- `mmcblk2p1`: `u-boot-dtb.img`, `zImage`, `imx7d-pico-pi-qca-m4.dtb`,
  `uEnv.txt`, `test_borrar.bin`.
- Los dos bloques de entorno de U-Boot (offsets 512 k y 768 k de `/dev/mmcblk2`).
- El kernel del fabricante `5.10.72-g7966a667bd89-dirty` y su `/lib/modules`.
- **Nunca instalar `linux-image-*` de Ubuntu.** Ocuparía espacio, no se usaría
  (U-Boot no lee `/boot`) y arrastraría dependencias.

---

## 3. Orden de las fases

```
frenar unattended  →  respaldos  →  espacio  →  IPv4 forzado
                   →  arreglar sources.list  →  actualizar por tandas  →  reiniciar
```

---

## Fase A — Frenar la actualización automática

Ver §1. **Es lo primero y tiene plazo: hoy antes de las 22:24.**

## Fase B — Seguro

Barato, y es lo único que separa un error de un ladrillo.

1. **Imagen de la partición de arranque** (32 MB: U-Boot, kernel, DTB y firmware
   del M4). Se copia al PC por SSH.
2. **Los dos bloques de entorno de U-Boot** (8 KB cada uno). Ya extraídos y
   validados por CRC.
3. **`tar` de `/etc`** completo.

> Aviso honesto: estos respaldos solo sirven si existe una vía de flasheo. Sin
> `usbipd-win` y acceso físico, no hay forma de restaurarlos si cae el arranque.

## Fase C — Espacio

Raíz de 3.4 G al **57 %**, **1.4 G libres**, sobre una eMMC de 2017.

Recuperable de inmediato, sin decisiones:

| | |
|---|---|
| `/var/lib/apt/lists` (listas de 2023, se van a regenerar igualmente) | 103 M |
| `/var/cache/apt` | 73 M |
| `/var/log` | 53 M |
| **Total** | **~230 M** |

Recuperable **si tú lo decides** (es decisión de producto, no técnica): la
tarjeta corre un **escritorio gráfico completo** — `slim`, Fluxbox, X11 — más
Apache, Samba, Bluetooth y ModemManager. Consume **266 MiB de los 487 MiB** en
reposo. Quitarlo libera disco y RAM y reduce superficie de ataque, pero elimina
el uso del LCD.

## Fase D — Forzar IPv4 en apt

`getent hosts ports.ubuntu.com` devuelve **solo direcciones IPv6**, y la tarjeta
**no tiene ruta IPv6 de salida** (comprobado: `ping6` falla). Si `apt` intenta
IPv6 primero, se comerá tiempos de espera largos o fallará.

```
Acquire::ForceIPv4 "true";
```

en `/etc/apt/apt.conf.d/`. Riesgo nulo, reversible borrando el fichero.

## Fase E — Arreglar `sources.list` antes de actualizar

El actual está incompleto:

```
deb http://ports.ubuntu.com/ubuntu-ports/ jammy main
deb http://ports.ubuntu.com/ubuntu-ports/ jammy universe
deb http://ports.ubuntu.com/ubuntu-ports/ jammy multiverse
deb http://ports.ubuntu.com/ubuntu-ports/ jammy-backports main
deb http://ports.ubuntu.com/ubuntu-ports/ jammy-security main
```

Dos carencias importantes:

- **No está `jammy-updates` en absoluto** → nunca ha llegado ninguna corrección
  de errores publicada tras la salida de 22.04.
- **`jammy-security` solo trae `main`** → los parches de seguridad de paquetes
  de `universe` nunca han llegado.

Añadir `jammy-updates` y extender `jammy-security` a `universe multiverse`
**aumentará mucho** el número de paquetes a actualizar. Es lo correcto, pero
explica por qué la Fase C (espacio) va antes.

## Fase F — Actualizar, conservador

### No hacer `do-release-upgrade`

**Jammy tiene soporte estándar hasta abril de 2027.** Un salto de versión sobre
una tarjeta con kernel de fabricante, 1.4 G libres y sin consola serie es la
forma de perderla. Cuando llegue 2027, la vía sensata no es actualizar en vivo,
sino **construir una imagen nueva y flashearla** con acceso físico.

### Secuencia

1. `apt update`.
2. `apt list --upgradable` y **revisar la lista antes de aplicar nada**. Con tres
   años de retraso y los repos completos, serán muchos paquetes.
3. `apt-mark hold` sobre cualquier paquete específico de TechNexion o del BSP.
4. Aplicar **primero solo seguridad**; comprobar que el sistema sigue en pie y
   que SSH sobrevive.
5. Después el resto **por tandas**, vigilando el espacio libre entre tandas.
6. `apt autoremove` y `apt clean` al final.

## Fase G — El reloj, a largo plazo

Ahora está en hora, pero **el RTC no tiene pila**: al cortar la alimentación
vuelve a 1970 y depende de que haya red al arrancar.

- **`fake-hwclock`**: guarda la hora al apagar y la restaura al arrancar. Da una
  hora *aproximada*, suficiente para que TLS y `apt` funcionen antes de
  sincronizar. Barato y recomendable.
- **Para usos que necesiten hora precisa esto no basta.** NTP por red da decenas
  de milisegundos en el mejor caso. Hace falta **GPS con PPS**, o como
  mínimo un RTC con pila. Es un requisito de hardware pendiente, no de software.

## Fase H — Limpieza opcional (riesgo bajo–medio)

Solo cuando lo anterior esté estable, y **nunca en el mismo paso**.

1. **`dnsmasq`**: `systemctl disable --now dnsmasq` y enmascararlo. Nunca ha
   funcionado y no se usa. Riesgo nulo, quita ruido del arranque.
2. **Doble cliente DHCP**: dejar un solo gestor de `eth0`. Es el paso que puede
   costar el acceso remoto, porque **SSH entra por la `.252`, que es la
   dirección secundaria**.

   **Red de seguridad obligatoria**: antes de aplicarlo, programar una reversión
   automática que restaure la configuración anterior a los N minutos. Si se
   pierde la sesión, la tarjeta se recupera sola. El temporizador solo se
   cancela tras confirmar que el acceso sigue vivo.

3. `resolvconf` + `systemd-resolved` conviven hoy sin síntomas. **No tocar.**

## Fase I — Reinicio: ✅ HECHO Y SUPERADO (2026-08-15 14:29)

Se reinició con los respaldos de la Fase B ya hechos. Confirmado por cambio de
`boot_id` (`9746eac5…` → `b88085ad…`); volvió en ~90 s.

Todo lo aplicado sobrevivió:

| Comprobación | Resultado |
|---|---|
| SSH por la IP de rescate `.240` | ✅ `rescue-ip.service` enabled + active |
| Dirección DHCP | ✅ `.252`, **un solo `dhclient`**, sin oscilación |
| NetworkManager | ✅ `eth0 unmanaged` |
| Ruta por defecto | ✅ presente, ahora **sin** `proto dhcp metric 100` → la pone ifupdown, confirmando que es el único gestor |
| Internet y DNS | ✅ ambos OK |
| Freno de apt | ✅ los dos timers `disabled`, `unattended-upgrades` `masked` |
| Hora | ✅ correcta y `NTPSynchronized=yes` |
| Arranque del M4 | ✅ UART6 sigue `disabled` → se cargó el DTB `-m4` → `m4boot` tuvo éxito |
| Montajes `/mnt/*` y swap | ✅ volvieron (los hace `/etc/rc.local`, no `fstab`) |
| Unidades fallidas | solo `dnsmasq` (conocido, cosmético) |

**Corrección:** en la versión anterior de este documento se advertía de que los
montajes de `/mnt/*` y el swap de `sda4` no volverían por tener el `fstab`
vacío. **Es falso**: los hace `/etc/rc.local` y sí son persistentes.

Queda pendiente probar un **corte de alimentación real** (no un reinicio en
caliente): ahí sí se pierde el RTC, que no tiene pila, y la hora dependerá de
que NTP sincronice al arrancar.

---

## Resumen del riesgo por fase

| Fase | Riesgo | Reversible en remoto |
|---|---|---|
| A · Frenar unattended | ninguno | sí |
| B · Respaldos | ninguno | — |
| C · Limpiar caché | ninguno | no hace falta |
| C · Quitar escritorio | bajo (técnico) | reinstalable, pero lento |
| D · Forzar IPv4 | ninguno | sí |
| E · `sources.list` | ninguno en sí | sí |
| F · `apt upgrade` | bajo (no toca el arranque) | parcialmente |
| G · `fake-hwclock` | ninguno | sí |
| H · `dnsmasq` | ninguno | sí |
| H · DHCP único | **medio-alto** | solo con reversión programada |
| I · Reinicio | **alto** | **no** |

---

## Nivel de confianza

**Verificado en la tarjeta:** el estado de la red antes y después de conectar el
router, la sincronización del reloj, la ejecución y los próximos disparos de
`unattended-upgrades`, la ausencia de paquete de kernel y de `/boot`, el
contenido de `sources.list`, el espacio libre, y la falta de salida IPv6.

**No verificado:** el resultado real de `apt upgrade` (no se ha ejecutado
`apt update`), y si la tarjeta sobrevive a un reinicio.
