# Pico-Pi-i.MX7D — inventario de la tarjeta

Levantado por SSH el **2026-08-15**. Refleja el estado **después** de la puesta a
punto de ese mismo día, cuya historia y método están en
[`Ruta_Actualizacion_SO.md`](Ruta_Actualizacion_SO.md).

Todo lo que sigue es **observado en la tarjeta**, salvo lo marcado explícitamente
como inferencia. El inventario en sí se hizo solo con lecturas; las
intervenciones están señaladas y documentadas aparte.

**Acceso:** `ssh ubuntu@192.168.1.240` — usar siempre esa IP, es fija. Ver §7.

---

## 1. Identificación

| | |
|---|---|
| Modelo (device tree) | `TechNexion PICO-IMX7D with QCA WLAN module and PI baseboard` |
| `compatible` | `fsl,pico-imx7d`, `fsl,imx7d` |
| Hostname | `technexion` |
| SoC | Freescale/NXP **i.MX7 Dual** |
| Arranque actual desde | eMMC (`bootdev=SD0`, raíz en `/dev/mmcblk2p2`) |

## 2. CPU

- **2 × ARM Cortex-A7** (ARMv7 rev 5, `CPU part 0xc07`), 20.12 BogoMIPS c/u.
- Extensiones: `neon vfpv3 vfpv4 idiva idivt vfpd32 lpae evtstrm thumb`.
- Frecuencia: **792 / 996 MHz** (solo dos puntos), gobernador `ondemand`,
  corriendo a 996 MHz.
- Temperatura: **55 °C** (`imx_thermal_zone`) en reposo con escritorio gráfico.
- **Cortex-M4F**: presente en el SoC pero *invisible para Linux*. No hay
  `remoteproc` registrado. Ver §6 y §10.

## 3. Memoria

| | |
|---|---|
| DDR3 física (device tree) | `reg = 0x80000000 + 0x20000000` → **512 MiB** |
| Visible para Linux | 499 092 kB ≈ **487 MiB** (el resto, reservado) |
| En uso en reposo | ~266 MiB usados, ~204 MiB disponibles |
| Swap zram | 121.8 MiB (prio 5), 46 MiB en uso |
| Swap en disco | `/dev/sda4`, 4.5 GiB (prio −2), sin usar |

Memorias que usa el M4 (no gestionadas por Linux): **TCM** 32 KiB en
`0x1FFF8000` (vista M4) = `0x007F8000` (vista A7), **OCRAM** `0x00910000`,
y una ventana en DDR `0x9FF00000`.

## 4. Almacenamiento

### eMMC interna — 3.56 GiB

Es el disco de arranque. `name=M62704`, `manfid=0x70`, fabricada **12/2017**.

| Partición | Tam. | FS | Montaje | Contenido |
|---|---|---|---|---|
| `mmcblk2p1` | 32 M | vfat | *(sin montar)* | **arranque**: U-Boot, `zImage`, DTB, `uEnv.txt`, firmware del M4 — **29 % usada, 23 M libres** |
| `mmcblk2p2` | 3.5 G | ext4 | `/` | raíz Ubuntu — **59 % usada, 1.4 G libres** |
| `mmcblk2boot0/1` | 2 M | — | — | particiones de arranque eMMC |

**Salud del chip** (`/sys/block/mmcblk2/device/`): `life_time = 0x02 0x01`
(10-20 % de vida consumida en el primer tipo de celda, <10 % en el segundo),
`pre_eol_info = 0x01` (normal, reservas intactas). Fabricada 12/2017. Ayuda que
el swap esté en el pendrive USB y no aquí.

> **La partición de arranque estuvo al 100 % (3 KB libres) hasta el 2026-08-15.**
> La ocupaba `ubuntu_22.04_All_eMMC_<usuario>.img` (23.5 MB), un resto de flasheo que
> **U-Boot no referencia** — se revisó el entorno entero; la única variable que
> carga algo así es `loadfit=fatload … tnrescue.itb`, y ese fichero no está.
> Se retiró junto con `test_borrar.elf` (U-Boot solo carga el `.bin`). Copias en
> `/mnt/varios/respaldo-arranque/` (con `LEEME.txt`) y en
> `(respaldo local, fuera de este repo)`, verificadas por MD5.
>
> ⚠️ **`test_borrar.bin` no se puede borrar.** Es a lo que apunta `m4image`. Si
> faltara, `loadm4image` falla, `mcu` queda vacío y U-Boot buscaría
> `imx7d-pico-pi-qca.dtb`, **que no existe en la partición** — se rompería el
> arranque de Linux. Cualquier binario propio del M4 debe *sustituirlo*
> conservando el nombre, no añadirse aparte.

### Disco externo — **no es un SSD**

Es un **pendrive USB Kingston DataTraveler 3.0** de 28.87 GiB (`0951:1666`),
colgado de un hub USB 2.0.

| Partición | Tam. | FS | Etiqueta | Montaje | Uso |
|---|---|---|---|---|---|
| `sda1` | 9.8 G | ext4 | `varios` | `/mnt/varios` | 1020 M (Processing 4.1.3 y 4.3, `Deposito_pkg`) |
| `sda2` | 9.8 G | ext4 | `otros` | `/mnt/otros` | 12 M |
| `sda3` | 4.9 G | vfat | — | *(sin montar)* | — |
| `sda4` | 4.5 G | swap | `swap-pico` | `[SWAP]` | 0 B |

**`/etc/fstab` está vacío**, pero los montajes **sí son persistentes**: los hace
`/etc/rc.local` (vía `rc-local.service`, habilitado). Comprobado tras el
reinicio del 2026-08-15 — vuelven solos.

```
swapon /dev/sda4
mount /dev/sda1 /mnt/varios
mount /dev/sda2 /mnt/otros
```

Conviene saberlo: quien busque en `fstab` no encontrará nada, y `mount -a` no
los recreará.

⚠️ **Hay swap sobre un pendrive USB.** Para una instalación permanente es mala
idea: desgaste de celdas y latencia alta.

## 5. Arranque y el camino del M4

`mmcblk2p1` (= `mmc 0:1` para U-Boot) contiene:

```
u-boot-dtb.img · zImage · imx7d-pico-pi-qca-m4.dtb · uEnv.txt
test_borrar.bin / test_borrar.elf    ← firmware M4 de junio 2023
ubuntu_22.04_All_eMMC_<usuario>.img       ← imagen de 23 MB
```

**Este U-Boot ya trae integrado el arranque del M4:**

```
tcm_addr=0x7F8000
m4image=<nombre del binario>
loadm4image=fatload mmc ${mmcdev}:${mmcpart} ${tcm_addr} ${m4image}
m4boot=if run loadm4image; then setenv mcu -m4; dcache flush; bootaux ${tcm_addr}; fi
mmcboot=... run m4boot; ... run setfdt; ... bootz ...
setfdt=... ${som}-${form}-${baseboard}-${wifi_module}${mcu}.dtb
```

`mmcboot` ejecuta `m4boot` **antes** de arrancar Linux. Si el binario carga,
`mcu` pasa a `-m4` y Linux usa `imx7d-pico-pi-qca-m4.dtb`. Todo va dentro de un
`if`: **si falta el binario, se salta en silencio y Linux arranca igual.**

Hay **dos bloques de entorno, ambos con CRC válido** (formato `crc+data`, 8192 B,
sin byte de flags) en `/dev/mmcblk2`:

| offset | `m4image` | `mcu` | `bootdelay` | entradas |
|---|---|---|---|---|
| 512 k | `test_borrar.bin` | `-m4` | 4 | 72 |
| 768 k | `hello_world.bin` | *(ausente)* | 2 | 63 |

**No se pudo determinar desde disco cuál lee U-Boot.** Se resuelve al instante
con consola serie (los `bootdelay` difieren).

> **Inferencia — no verificada:** el vivo es el de 512 k y el M4 lleva corriendo
> `test_borrar.bin` desde 2023. Razón: en el FAT *solo* existe el DTB `-m4`, y
> ese nombre solo se construye si `mcu=-m4`; además UART6 está deshabilitado en
> el árbol vivo (§6), justo lo que hace el DTB `-m4` para cedérselo al M4.
> No se pudo confirmar por bytes: `/dev/mem` está bloqueado (`STRICT_DEVMEM`).

## 6. Buses y periféricos — qué está libre para el M4

### SPI / ECSPI ← **lo más importante para el ADC**

| Nodo | Periférico | Alias | Estado en Linux | ¿Sirve para el M4? |
|---|---|---|---|---|
| `spi@30820000` | **ECSPI1** | spi0 | `disabled` | ❌ **sus pads los tiene el WiFi/BT** |
| `spi@30830000` | **ECSPI2** | spi1 | `disabled` | ❌ **sus pads los tiene UART7 (Bluetooth)** |
| `spi@30840000` | **ECSPI3** | spi2 | `okay` → `/dev/spidev2.0` | ⚠️ **el único que sale a J8**; hay que quitárselo a Linux |
| `spi@30630000` | **ECSPI4** | spi3 | `disabled` | ❌ el SoC no le da pads dedicados |
| `spi@30bb0000` | QSPI | — | `disabled` | — |

> ⚠️ **«`disabled` en el árbol» NO significa «disponible».** Significa que nadie
> instanció el controlador — mientras sus patillas se usaban para otra cosa. Esta
> tabla decía «✅ libre» para ECSPI1, 2 y 4 hasta el **2026-08-16**, y era
> engañoso.

#### Quién tiene realmente los pads (comprobado, 2026-08-16)

Cruzando los offsets de `fsl,pins` del árbol vivo contra el mapa de registros del
BSP (`MCIMX7D_M4.h`), pad por pad:

| Offset | Pad del SoC | Grupo de pinctrl que lo reclama | Función real |
|---|---|---|---|
| `0x168` | `ECSPI1_SCLK` | `wifi_ctrlgrp` | control del WiFi |
| `0x16C` | `ECSPI1_MOSI` | `bt_ctrlgrp` | control del Bluetooth |
| `0x170` | `ECSPI1_MISO` | `bt_ctrlgrp` | control del Bluetooth |
| `0x174` | `ECSPI1_SS0` | `wifi_ctrlgrp` | control del WiFi |
| `0x178` | `ECSPI2_SCLK` | `uart7grp` | UART7 |
| `0x17C` | `ECSPI2_MOSI` | `uart7grp` | UART7 |
| `0x180` | `ECSPI2_MISO` | `uart7grp` | UART7 |
| `0x184` | `ECSPI2_SS0` | `uart7grp` | UART7 |

**Los ocho pads de ECSPI1 y ECSPI2 están ocupados por el módulo combo QCA**:
las líneas de control de WiFi y Bluetooth, más UART7, que es el enlace HCI del
Bluetooth. El dato de WiFi va aparte, por SDIO (`usdhc3grp` → pads `SD3_*`).

**El audio no interviene**: SAI1 usa pads `ENET1_*` (`0x25C`–`0x268`) y SAI2 los
suyos (`0x21C`–`0x228`). Ninguno toca ECSPI.

**ECSPI3 no tiene pads propios**: se muxea sobre los pads *llamados* `I2C1_SCL`,
`I2C1_SDA`, `I2C2_SCL` e `I2C2_SDA` (`0x148`–`0x154`). De ahí la confusión de
nombres — y es lo que explica que la serigrafía rotule esos pines como `CSPI2`
cuando el periférico es ECSPI3.

**ECSPI4 no tiene pads dedicados en el SoC**, así que solo existiría muxeado
sobre pads de otro, y todo lo aprovechable ya está tomado.

> **Conclusión operativa:** liberar ECSPI1 o ECSPI2 apagando WiFi y Bluetooth
> **no serviría de nada**, porque esas pistas van al módulo QCA de la SOM, no a
> ningún conector. **ECSPI3 es la única vía posible hacia el ADC.**

#### Mapa del conector J8 — dónde pinchar

De la tabla *EXPANSION CONN MAPPING* corregida sobre el esquemático de
TechNexion. J8 es de 40 pines: **fila inferior = impares** (el 1 en el extremo
del `3V`), **fila superior = pares**; los pines `2n−1` y `2n` comparten columna.

| Señal | Pin J8 | Fila | Bola i.MX7 | También en |
|---|---|---|---|---|
| `ECSPI3.MOSI` | **19** | inferior | K1 | JP1 pin 6 |
| `ECSPI3.MISO` | **21** | inferior | J2 | JP1 pin 5 |
| `ECSPI3.SCLK` | **23** | inferior | K2 | JP1 pin 4 |
| ~~`ECSPI3.SS0`~~ | ~~24~~ | superior | K3 | JP1 pin 3 |
| **CS del SPI de Linux** (`GPIO4_IO11`, pad `I2C2_SDA`, gpio 107) | **26** | superior | — | — |
| `GPIO2_IO00` (pad `EPDC_DATA00`, gpio 32, nombre DT `GPIO_P24`) — **solo salida** | **36** | superior | — | — |

> ⚠️ **J8-36 y J8-11 no dejan entrar señales** (medido 2026-11-13). J8-36 sigue
> a gpio 32 hacia fuera (parpadeo visible), pero con la línea en entrada y el
> DRDY del ADS1220 unido, el nodo se queda en **3,3 V** y Linux lee 1 fijo: algo
> de la placa base lo empuja con fuerza (hipótesis: un buffer o traductor de
> sentido fijo SoC→J8; el pull-up del pad, de 47 kΩ, no podría). J8-11
> (`EPDC_DATA11`, CTS de UART6) se comporta igual. Los pads de ECSPI3, que son
> pads I2C, sí son bidireccionales: MISO entra por J8-21. **Antes de usar un
> pin de J8 como entrada, comprobarlo con una señal real.**
| `GND` | **20** o **25** | 20 arriba, 25 abajo | — | JP1 pin 8 |
| `UART6.RTS` | 7 | inferior | L24 | — |
| **`UART6.TX`** | **8** | superior | L25 | JP2 pin 4 |
| **`UART6.RX`** | **10** | superior | M23 | JP2 pin 3 |
| `UART6.CTS` | 11 | inferior | L23 | — |

> ⚠️ **Corregido el 2026-11-13, medido con multímetro.** Esta tabla daba el chip
> select en el **24**, y es falso. Con `spi_imx` desligado se puso el gpio 107
> (el `cs-gpios` del device tree, pad `I2C2_SDA`) en bajo: **J8-24 siguió a
> 3,3 V**. Haciéndolo parpadear a 1 Hz, la señal apareció en **J8-26**, que la
> serigrafía rotula `CSPI2_CS1`. Qué hay en J8-24 sigue sin saberse: da 3,3 V
> fijos. MOSI 19, MISO 21 y SCLK 23 quedaron **verificados funcionando** ese
> mismo día con un ADS1220 (escritura y lectura de registros correctas).

⚠️ **La serigrafía miente**: esos pines de SPI están rotulados `CSPI2_MOSI_3V`,
`CSPI2_SCLK_3V`, `CSPI2_CS1_3V`… pero el periférico es **ECSPI3**. Guiarse por el
rótulo lleva a buscar el controlador equivocado.

🔎 **UART6 sale a J8 pines 8 y 10** — la incógnita que este documento daba por
«sin confirmar». El cabo que quedaba (si el BSP muxeaba UART6 sobre otros pads)
**se resolvió el mismo 2026-08-16**: el BSP y el DTS usan los mismos pads
`EPDC_DATA08/09` en ALT3. Ver la tabla de la consola del M4 más abajo.

Reconfirmado el 2026-08-16. Los grupos de pinctrl definidos en el árbol son
**solo `ecspi3grp` y `ecspi3_cs_grp`**: Linux no muxea pines para ECSPI1, 2 ni 4,
así que el M4 no le disputaría los pads a nadie.

#### El `enable_count = 0` de los relojes ECSPI **no** es el caso del GPT3

Conviene dejarlo escrito, porque induce a un diagnóstico equivocado. En
`clk_summary` los cuatro aparecen así:

```
ecspi1_root_clk   enable_count = 0    60 MHz
ecspi2_root_clk   enable_count = 0    60 MHz
ecspi3_root_clk   enable_count = 0    60 MHz   ← y este SÍ lo usa Linux
ecspi4_root_clk   enable_count = 0    60 MHz
gpt3_root_clk     enable_count = 0   392 MHz   ← el que sí está roto
```

**`ecspi3` marca cero y sin embargo es `/dev/spidev2.0`, funcional.** El driver
enciende el reloj solo mientras dura cada transferencia, así que **en ECSPI el
cero es el estado normal en reposo**, no señal de que Linux lo tenga bloqueado.
Fíjate además en los 60 MHz limpios de los cuatro frente a los 392 MHz sin
sentido del GPT3: el árbol de relojes de ECSPI está bien configurado.

⚠️ **La incógnita real no es el reloj, es el enrutado.** Que un ECSPI esté libre
no significa que sus pines lleguen al conector de expansión. El único del que
consta que sale al exterior es **ECSPI3**, precisamente el que usa Linux — y
`lsof` confirma que **ningún proceso lo tiene abierto**. Resolver esto exige el
esquemático, la misma laguna que hay con UART6 (§6, UART).

### UART

| Nodo | Periférico | Estado | Nota |
|---|---|---|---|
| `serial@30860000` | UART1 | `disabled` | |
| `serial@30880000` | UART3 | `disabled` | |
| `serial@30890000` | UART2 | `disabled` | |
| `serial@30a60000` | UART4 | `disabled` | |
| `serial@30a70000` | UART5 | `okay` | `/dev/ttymxc4` — **consola de Linux**, con getty |
| `serial@30a80000` | UART6 | **`disabled`** | **la usa el M4** (`board.h:104` del BSP) |
| `serial@30a90000` | UART7 | `okay` | `/dev/ttymxc6` |

Comprobado de nuevo tras el reinicio del 2026-08-15: sigue igual.

> Consecuencia: **el M4 y Linux no se pisan el puerto serie.** La salida de
> `hello_world` sale por UART6, que Linux no toca — y que por lo mismo **no se
> puede leer por SSH**.
>
> Ojo: en `imx7d_sdb_m4` el debug UART del BSP es **UART2**, no UART6. Una razón
> más para no compilar contra la placa equivocada.

#### Configuración de la consola auxiliar del M4

Fijada en código, en `examples/imx7d_pico_m4/board.c:93`
(`DbgConsole_Init(...)`) y en `platform/utilities/src/debug_console_imx.c`. **No
es un parámetro de arranque: cambiarla exige recompilar.**

| | |
|---|---|
| Puerto | **UART6**, base `0x30A80000` |
| Velocidad | **115200 baudios** |
| Trama | **8 bits de datos, sin paridad, 1 bit de parada** (8N1) |
| Control de flujo | **ninguno** — el driver desactiva RTS explícitamente |
| Sentido | TX y RX (`uartDirectionTxRx`) |
| Reloj de referencia | **OSC 24 MHz** (`ccmRootmuxUartOsc24m`, divisores 1/1) |
| Pines | **EPDC_DATA08** y **EPDC_DATA09**, ambos en **ALT 3** |
| Pads | *pull* activado (`PS(3)`), histéresis Schmitt, fuerza `DSE(1)` |
| Niveles | **TTL 3.3 V** — hace falta adaptador USB-serie de 3.3 V |

```c
uart_init_config_t uart_init_str = {.clockRate  = clockRate,
                                    .baudRate   = baudRate,      // 115200
                                    .wordLength = uartWordLength8Bits,
                                    .stopBitNum = uartStopBitNumOne,
                                    .parity     = uartParityDisable,
                                    .direction  = uartDirectionTxRx};
```

**Dos detalles del código que explican comportamientos observables:**

1. `dbg_uart_init()` reserva el puerto **solo para el dominio del M4**:
   `RDC_SetPdapAccess(RDC, rdcPdapUart6, 3 << (BOARD_DOMAIN_ID * 2), false, false)`.
   Por eso `serial@30a80000` sale `disabled` en el árbol vivo y no existe
   `/dev/ttymxc5`: no es un olvido del DTB, es deliberado.

2. La puerta de reloj queda abierta a propósito, con este comentario en el BSP:
   *«IC Limitation — M4 stop will cause A7 UART lose functionality, so we need
   UART clock all the time»* (`ccmClockNeededAll`). Errata del silicio: cortar el
   reloj del UART del M4 se lleva por delante el del A7.

#### ✅ Resuelto el 2026-08-16 — y la convención supuesta estaba invertida

| Pad | Señal | Ball | Pin J8 |
|---|---|---|---|
| `EPDC_DATA08` | **UART6_RX** | M23 | **10** |
| `EPDC_DATA09` | **UART6_TX** | L25 | **8** |
| `EPDC_DATA10` | UART6_RTS | L24 | 7 |
| `EPDC_DATA11` | UART6_CTS | L23 | 11 |
| — | GND | — | **9** |

Este documento suponía «por convención de NXP» que `EPDC_DATA08` sería TX.
**Es al revés.** La prueba está en el `fsl,pins` del `uart6grp` del árbol vivo:

```
mux_reg   conf_reg  input_reg  mux_mode
0x0054    0x02c4    0x071c        3      <- EPDC_DATA08, con select input
0x0058    0x02c8    0x0000        3      <- EPDC_DATA09, sin select input
0x005c    0x02cc    0x0718        3
0x0060    0x02d0    0x0000        3
```

**Solo `EPDC_DATA08` lleva registro de selección de entrada** (`0x71c`, el de
`UART6_RX_DATA`), y esa selección solo hace falta para un pad que actúa de
entrada. Luego `EPDC_DATA08` es **RX**. El BSP concuerda: pone
`IOMUXC_UART6_RX_DATA_SELECT_INPUT = DAISY(0)`.

**El BSP no necesita cambios.** El DTS de Linux y el `pin_mux.c` del BSP usan los
**mismos cuatro pads con el mismo `MUX_MODE(3)`**. La sospecha de que el BSP
muxeaba UART6 sobre pads que no llegan a J8 era **falsa**: TechNexion usa los
mismos en su Linux y en su FreeRTOS.

**Cableado para ver el M4** — adaptador USB-serie **de 3,3 V**:

| Adaptador | Pin J8 |
|---|---|
| RX | **8** (UART6.TX) |
| TX | 10 (UART6.RX) — solo si quieres enviar |
| GND | **9** |

⚠️ **No conectes el VCC del adaptador.** 115200 · 8N1 · sin control de flujo.

### Otros buses

- **I²C**: `i2c-0` (`30a20000`), `i2c-1` (`30a30000`), `i2c-3` (`30a50000`).
- **GPIO**: 7 controladores, `30200000`–`30260000`.
- **PWM**: `pwmchip0`–`pwmchip3`.
- **CAN**: `can0` y `can1` existen, ambos **DOWN**.
- **IIO**: sin dispositivos — no hay ningún ADC expuesto a Linux hoy.
- **USB**: hub 2.0 + pendrive Kingston + receptor inalámbrico 2.4 G (`25a7:fa70`).
- **Cámara**: módulos `mx6s_capture`, `mxc_mipi_csi`, `ov5640_camera_mipi_v2`.

## 7. Red

> **Actualizado el 2026-08-16: `eth0` pasó de ifupdown a NetworkManager.**
> Lo que sigue es el estado actual, verificado tras un reinicio real.

| | |
|---|---|
| `eth0` — dirección fija de rescate | **`192.168.1.240/24`**, `valid_lft forever`. **Usar esta para administrar.** La sirven dos fuentes: el perfil `eth0-main` de NM y `rescue-ip.service` |
| `eth0` — dirección DHCP | `192.168.1.251/24` (dinámica, puede cambiar). Era la `.252` con ifupdown; cambió al migrar porque NM pide la concesión con otro client-id |
| MAC | `00:1f:7b:xx:xx:xx` |
| Gateway | `192.168.1.1` (DHCP) |
| WiFi | **no hay interfaz `wlan0`**, pese al módulo QCA y a `wpa_supplicant` activo |
| DNS | **funciona** (`rcode=0`). Nunca estuvo roto: faltaba salida a Internet en la LAN, resuelta en el router el 2026-08-15 |
| Gestor de red | **NetworkManager**, perfil **`eth0-main`**: `ipv4.method auto` **más** `ipv4.addresses 192.168.1.240/24`. `eth0` está comentada en `/etc/network/interfaces`, ifupdown ya no la toca |

### Acceso independiente de la red

⚠️ **La `.240` está atada a `192.168.1.0/24`** — la subred del router de casa — y aparece clavada en **dos sitios**: `ipv4.addresses` del perfil
`eth0-main` y el `ExecStart` de `rescue-ip.service`. Si la tarjeta se conecta a
un router con otra subred, el DHCP le dará dirección y habrá conectividad, pero
**la `.240` no responderá**. Riesgo añadido: en otro router del mismo modelo, de fábrica, podría
chocar con un equipo al que su DHCP ya asignó la `.240`.

Existen **tres vías que no dependen de la subred**, y las tres están ya activas
sin haber configurado nada:

| Vía | Comando | Depende de |
|---|---|---|
| **mDNS / Avahi** | `ssh ubuntu@technexion.local` | que el cliente hable mDNS y comparta LAN |
| **IPv6 link-local** | `ssh ubuntu@fe80::xxxx:xxxx:xxxx:xxxx%eth0` | **solo del cable**: ni router, ni DHCP, ni DNS |
| Pantalla y teclado locales | `ip -4 -br addr show eth0` | nada |

En el segundo comando, `%eth0` es la interfaz **del equipo cliente**, no la de la
tarjeta.

**La vía IPv6 link-local es la relevante para despliegue en campo**: es capa 2 y
funciona con un cable directo entre un portátil y la tarjeta, sin infraestructura
de ningún tipo. Para una placa que acabará en sitios sin router, ese es el
camino que siempre estará.

Requisitos comprobados el 2026-08-16:

| | |
|---|---|
| `avahi-daemon` | `active` + `enabled`; `publish-addresses` sin descomentar → por defecto `yes` |
| Resolución `.local` en la tarjeta | `nsswitch.conf`: `hosts: files mdns4_minimal [NOTFOUND=return] dns` |
| `sshd` en IPv6 | escucha en `0.0.0.0:22` **y en `[::]:22`**, sin `AddressFamily` restringido |
| Dirección `fe80::` | presente en `eth0` |

A esas tres vías hay que sumar una cuarta que apareció por el camino:

| Vía | Comando | Estado |
|---|---|---|
| **NetBIOS (Samba)** | `ssh ubuntu@technexion` | `nmbd` **active**, anunciando `TECHNEXION <00>`, `<03>` y `<20>` en 137/138 |

#### Nivel: el lado de la tarjeta está verificado; el del cliente, no

**Verificado en la tarjeta el 2026-08-16** — publica correctamente:

    getent ahostsv4 technexion.local  ->  192.168.1.240
    getent ahosts    technexion.local  ->  192.168.1.251
    nmblookup -A 192.168.1.240        ->  TECHNEXION <00> <03> <20> ACTIVE

**No verificado desde un cliente externo.** No se pudo, y por dos motivos
distintos que conviene no confundir:

1. **Desde WSL2 es imposible por diseño**: está tras su propio NAT
   (`172.x.x.x/20`, saliendo por la puerta de enlace de WSL, que es el propio Windows).
   No le llega mDNS ni tiene adyacencia de capa 2 con la tarjeta. Alcanza la
   `.240` por IP y punto.
2. **Desde el Windows anfitrión lo impide el cliente, no la tarjeta.**

> ⚠️ **Si algún día `ssh technexion.local` falla, sospecha del cliente antes que
> de la tarjeta.** El 2026-08-16, desde Windows, fallaban a la vez el ping, el
> mDNS y el NetBIOS. La causa **no** estaba en la Pico-Pi:
>
> | Síntoma | Lo que significa |
> |---|---|
> | `ping` → **`General failure`** | Windows **no pudo ni emitir** el paquete. Un bloqueo de perfil daría `Request timed out` |
> | `ssh` → **`Permission denied`** al conectar | Lo bloqueó un filtro **local** (WFP). Si viniera de la tarjeta sería `Connection refused` o `timed out` |
>
> Ambas huellas apuntaban a un **kill-switch de VPN** (adaptador `ProTUN`) que
> captura la ruta por defecto y bloquea la LAN. Se sumaba el adaptador Ethernet
> con `NetworkCategory: Public`, que además tumba mDNS (5353) y NetBIOS (137/138).
>
> Y explica la aparente contradicción de que **WSL sí llegue**: su tráfico sale
> NATeado por el conmutador virtual de Hyper-V, un camino que el kill-switch no
> captura.
>
> Arreglo del lado cliente, sin desconectar la VPN: activar *«Allow LAN traffic»*
> en el cliente VPN, y
> `Set-NetConnectionProfile -InterfaceIndex <n> -NetworkCategory Private`.

#### Cómo desatar del todo la `.240` (pendiente de decidir)

Tres caminos, de menos a más correcto:

- **(a) Dejarla como está.** En otra red es una dirección huérfana e inofensiva,
  y al volver al router de origen funciona sola. Es lo que hay hoy.
- **(b) Añadir IPv4 link-local** (`169.254.240.240/16`) como segunda dirección
  estática del perfil. Válida por definición en cualquier segmento Ethernet;
  garantiza un camino IPv4 aunque no haya DHCP. No interfiere con el DHCP.
- **(c) Reserva DHCP en el router por MAC** (`00:1f:7b:xx:xx:xx`). **La más
  correcta**: la IP fija la decide el router y la tarjeta no lleva clavada
  ninguna suposición sobre la red.

### Historia: por qué esto no es una regresión

**Hasta el 2026-08-15 había dos clientes DHCP** peleando por `eth0`
(NetworkManager por un lado e ifupdown por otro), lo que hacía **oscilar la
dirección entre `.252` y `.253`** según caducaban las concesiones — y llegó a
cortar el acceso SSH en mitad de una sesión. Se resolvió poniendo
`managed=false` en `[ifupdown]` de `/etc/NetworkManager/NetworkManager.conf`,
dejando a **ifupdown como único gestor**.

**El 2026-08-16 se invirtió el reparto**: ahora el único gestor es
**NetworkManager**. El motivo fue que `nm-applet` mostraba *«No valid active
connection found!»* — decía la verdad, porque NM no gestionaba nada.

Lo que importa entender: **el fallo antiguo no era «quién gestiona», era «que
gestionen dos a la vez»**. Se comprobó tras el reinicio que no queda ningún
`dhclient` huérfano. Con un solo gestor, cualquiera de las dos configuraciones es
estable. **Lo que nunca debe volver a haber es las dos activas.**

Revertir a ifupdown: `sudo /usr/local/sbin/net-rollback.sh` (restaura y
reinicia). Respaldos en `/root/net-backup/`.

## 8. Sistema operativo y software

| | |
|---|---|
| SO | **Ubuntu 22.04.5 LTS** (jammy), arquitectura **armhf** — actualizado el 2026-08-15 |
| Kernel | **5.10.72-g7966a667bd89-dirty**, `#7 SMP PREEMPT`, compilado 2023-06-20. **apt no lo gestiona** (no hay paquete de kernel y `/boot` está vacío), así que las actualizaciones no lo tocan |
| cmdline | `console=ttymxc4,115200 root=/dev/mmcblk2p2 rootwait rw` |
| Módulos cargados | solo **5** (los 3 de cámara, `zram`, `binfmt_misc`) |
| Paquetes dpkg | **1189** |
| Zona horaria | `America/Caracas` (−04) |
| Repositorios | `jammy`, `jammy-updates`, `jammy-security`, `jammy-backports`, los cuatro con `main restricted universe multiverse`. **Antes faltaba `jammy-updates` entero** y `security` solo traía `main` |
| Automatismos de apt | **desactivados a propósito**: `apt-daily.timer` y `apt-daily-upgrade.timer` `disabled`, `unattended-upgrades` `masked`. Actualizar es una operación supervisada en esta tarjeta |

**Herramientas presentes:** `gcc` / `g++` **11.4.0**, `make` 4.3, `python3`
**3.10.12**, `perl`, `openssl`, **`minicom` 2.8**, `build-essential`, `gpiod` +
`libgpiod2`, `ntp` / `ntpdate` / `sntp`, servidor y cliente SSH.

**Ausentes:** `cmake`, `git`, `pip3`, `dtc`, `fw_printenv` / `fw_setenv`,
`i2cdetect`, `devmem2`, `docker`, `node`. **Nada de análisis sísmico**: ni
SeisComP, ni ObsPy, ni NumPy, ni SciPy.

**Hallazgo relevante:** en el home está `imx_rpmsg_tty_file.ko` (10 636 B,
"iMX virtio remote processor messaging tty driver"), compilado contra
`vermagic 5.10.72-g7966a667bd89` — **coincide con el kernel en ejecución**, así
que es cargable. El historial muestra `insmod` usado ~13 veces.

## 9. Servicios y usuarios

**Corriendo:** `apache2`, `smbd` + `nmbd` (Samba), `slim` (gestor de sesión
gráfica) con **escritorio Fluxbox sobre X11**, `bluetooth`, `ModemManager`,
`NetworkManager`, `wpa_supplicant`, `avahi-daemon`, `colord`, `upower`,
`udisks2`, `ntp`, `cron`, `ssh`, `serial-getty@ttymxc4`, `unattended-upgrades`.

**Fallidas:** **ninguna**. `dnsmasq` está ahora `masked` — nunca llegó a
arrancar, porque `systemd-resolved` ya ocupa el puerto 53 y hace el trabajo.

**Usuarios:** `ubuntu` (uid 1000, en el grupo `sudo`, **`sudo` sin contraseña**)
y `samba` (uid 1001). Clave SSH instalada; ya no hace falta contraseña.

### Pantalla acoplada — 800×480, y por qué se queda corta

| | |
|---|---|
| Resolución | **800×480**, único modo disponible |
| Tamaño físico medido | **110 × 65 mm** (~12,7 cm de diagonal, panel de 5") |
| Framebuffer | `mxs-lcdif` |
| Driver X | **fbdev**. `modesetting` falla: **no existe `/dev/dri`** |
| Escritorio | XFCE (`xfce4-session`, `xfce4-panel` de 26 px) con **fluxbox** de gestor de ventanas, bajo `slim` |
| Teclado y ratón | conectados por USB — **es el rescate local si SSH cae** |

**Los 480 px de alto son el techo del hardware.** Sin `/dev/dri` no hay DRM/KMS,
así que `xrandr` no puede escalar ni hacer *panning*: la salida es un `default`
tonto con un solo modo fijo.

**El panel no reporta EDID** (`0mm x 0mm`), así que X se inventa 212×127 mm para
que la cuenta dé unos 96 DPI limpios. Pero el tamaño real son 110 mm de ancho, o
sea **≈185 DPI**: X cree que la pantalla mide el doble de lo que mide.

De ahí la tensión que hay que entender antes de tocar las fuentes:

- a `Sans 10` el texto sale de ~1,8 mm de altura de em — físicamente diminuto;
- a `Sans 15` se lee bien, pero los diálogos crecen ~50 % y **los botones de la
  parte inferior se salen de la pantalla**.

La imagen venía con `Sans 15`. El **2026-08-16** se bajó a `Sans 12` como
compromiso:

    xfconf-query -c xsettings -p /Gtk/FontName -s "Sans 12"

Se aplica en caliente (`xfsettingsd` lo propaga por XSETTINGS). El valor anterior
quedó anotado en `~/.fuente-anterior.txt` en la tarjeta.

> **Truco imprescindible en esta pantalla:** si un diálogo es más alto que los
> 480 px y no ves sus botones, **`Alt` + arrastrar con el botón izquierdo** mueve
> la ventana desde cualquier punto, aunque el borde esté fuera. Está en
> `/etc/X11/fluxbox/keys`: `OnWindow Mod1 Mouse1 :{Raise} {Focus} {StartMoving}`.
> `Alt` + botón derecho redimensiona. Y en casi cualquier diálogo GTK, `Enter`
> acepta y `Esc` cancela sin necesidad de ver los botones.

## 10. Problemas: resueltos y pendientes

### ✅ Resueltos el 2026-08-15

| Problema | Resolución |
|---|---|
| Sistema en `2023-03-02`, NTP sin sincronizar nunca | Se corrigió **solo** al restaurar Internet: `ntp-systemd-netif.path` disparó la sincronización. `NTPSynchronized=yes` |
| «DNS roto» | **No lo estaba.** `systemd-resolved` era correcto; faltaba salida a Internet en la LAN. Resuelto en el router |
| `dnsmasq` en `failed` | Enmascarado. Era ruido: conflicto de puerto 53 con `resolved` |
| Dirección IP inestable | Había **dos clientes DHCP** peleando por `eth0`. Unificado en **un solo gestor** + IP fija de rescate. Fue ifupdown el 2026-08-15; es NetworkManager (perfil `eth0-main`) desde el 2026-08-16 — ver §7 |
| ~3 años sin actualizar, `jammy-updates` ausente | 446 paquetes actualizados, repositorios completados |
| Partición de arranque al 100 % (3 KB libres) | 23 MB liberados |
| Actualización automática sin supervisión | Timers de apt `disabled`, `unattended-upgrades` `masked` |

### ✅ Resueltos el 2026-08-16

| Problema | Resolución |
|---|---|
| `nm-applet`: *«No valid active connection found!»* | **El mensaje era cierto**, no un fallo de despliegue: NetworkManager no gestionaba nada. Resuelto migrando `eth0` a NM — ver [`Red_Migracion_NetworkManager.md`](Red_Migracion_NetworkManager.md) |
| Menús que no dejan ver sus propios botones | Fuente de la interfaz de `Sans 15` a `Sans 12`. La causa de fondo son los 480 px de alto, que **no tienen arreglo** — ver §9 |
| `nameserver 8.8.8.8` dentro de `/etc/hosts` | **Línea eliminada.** Era sintaxis de `/etc/resolv.conf` pegada en el fichero equivocado, y por tanto **inerte**: el parser de `hosts` espera una IP en la primera columna y la descartaba. Alguien intentó arreglar el DNS ahí y no surtió efecto. Comprobado que la resolución sigue bien tras quitarla (`systemd-resolved` en `127.0.0.53`). Respaldo en `/root/net-backup/hosts.bak-20260816` |

### 🔴 Pendiente y crítico: el tiempo

El RTC `snvs_rtc` **no tiene pila**: al cortar la alimentación vuelve a 1970 y
la hora depende de que NTP sincronice al arrancar. NTP por red da decenas de
milisegundos en el mejor caso.

**Para cualquier aplicación que necesite hora precisa** (registro de datos con
marca de tiempo, sincronizar varias placas) esto no basta. Hace falta **GPS con
PPS**, o como mínimo un RTC con pila. Es un requisito de hardware, no de software, y es el que
de verdad condiciona el proyecto.

### 🟠 Otros pendientes

- **Swap sobre pendrive USB** (`sda4`, 4.5 G) → desgaste de celdas y latencia.
  Mala idea para una instalación permanente.
- **Escritorio gráfico + Apache + Samba + Bluetooth + ModemManager** en 487 MiB:
  ~266 MiB consumidos en reposo para una máquina destinada a adquirir datos.
- **Credenciales por defecto** `ubuntu`/`ubuntu` con `sudo` sin contraseña.
- **Kernel `-dirty`**: compilado desde un árbol con modificaciones sin registrar.
  Y **apt no lo gestiona**, así que actualizarlo exige tocar la FAT a mano.
- **Corte de alimentación real: superado una vez** (2026-11-11, apagón
  doméstico): ext4 hizo `recovery complete` y todo volvió solo. Un solo corte no
  prueba robustez.

## 11. Qué significa para quien use esta placa

> Sección reescrita con lo aprendido después del inventario inicial
> (2026-08-16 a 2026-11-11). Donde el resto del documento discrepe, manda esto.

1. **SPI: solo ECSPI3 es utilizable.** ECSPI1, ECSPI2 y ECSPI4 aparecen
   `disabled` en Linux, pero eso solo dice que nadie instanció el controlador:
   los pads de ECSPI1 y ECSPI2 los usa el combo WiFi/Bluetooth, y ECSPI4 no tiene
   pads dedicados. ECSPI3 sale a J8 y JP1 y Linux lo expone como
   `/dev/spidev2.0`. Ver §6.
2. **El camino de carga del M4 ya existe y es seguro.** No hay que inventar
   secuencias de U-Boot: basta con poner el binario donde apunta `m4image`
   (`M4_Despliegue_y_Verificacion.md`).
3. **RPMsg funciona con el kernel y el device tree de fábrica**: solo hacía falta
   un firmware en el M4 (`RPMsg_Verificacion.md`).
4. **El M4 se puede observar desde Linux sin consola serie**, a través del
   «USER LED» **GPIO2_IO06** (número global **38** en sysfs): `blinking_imx_demo`
   le da acceso a todos los dominios (`RDC_SetPdapAccess(..., 0xFF, ...)`) y
   Linux puede leer si alterna.
5. **WiFi y punto de acceso**: funcionan añadiendo `brcmfmac.ko` al kernel de
   fábrica (`Kernel_Recompilacion.md`, `WiFi_Diagnostico.md`).
6. **El tiempo es el límite real** para cualquier uso que dependa de la hora:
   el RTC no tiene pila.

## 12. Cómo se obtuvo

Acceso: `ssh ubuntu@192.168.1.240` (IP fija de rescate; ver §7). El
reconocimiento inicial se hizo con contraseña vía `SSH_ASKPASS` +
`SSH_ASKPASS_REQUIRE=force` bajo `setsid -w`, porque el cliente local no tiene
`sshpass`; después se instaló clave.

El inventario fue **todo de lectura**: `/proc`, `/sys`, `lsblk`, `dpkg -l`,
`systemctl`, montajes con `-o ro` (desmontados después) y `dd` de solo lectura
sobre `/dev/mmcblk2` para los bloques de entorno de U-Boot, cuyos CRC se
validaron fuera de la tarjeta. Las intervenciones posteriores están en
`Ruta_Actualizacion_SO.md`.

**No verificado, por falta de medios:** cuál de los dos entornos de U-Boot está
activo, y si el M4 está ejecutando firmware ahora mismo — `/dev/mem` está
bloqueado por `STRICT_DEVMEM`, así que no se pudo volcar la TCM para comparar
bytes. *(Más tarde sí se leyó la TCM por `/dev/mem`: ver `RPMsg_Verificacion.md`.)* La evidencia de que `m4boot` funciona es **indirecta**: UART6 aparece
`disabled` en el árbol vivo, y ese DTB solo se carga si `mcu=-m4`, que solo se
pone si `loadm4image` tuvo éxito. Reproducido en tres arranques distintos.
