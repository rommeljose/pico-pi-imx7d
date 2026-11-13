# Guía práctica: tu propio firmware en el M4, con RPMsg, datos binarios y SPI

**Para quién es.** Para quien tiene una **TechNexion Pico-Pi-i.MX7D** con la
imagen de fábrica en la eMMC (Ubuntu 22.04 de TechNexion, kernel
`5.10.72-g7966a667bd89-dirty`) y quiere usar **los dos mundos del chip**:

- el **Cortex-M4** con FreeRTOS, para lo que debe ser puntual y no depender de
  Linux, como leer un sensor a ritmo fijo;
- los **Cortex-A7** con Linux, para analizar, guardar, mostrar y comunicar.

También explica cómo pasar datos entre ambos (**RPMsg**, en texto y en binario)
y cómo usar el **SPI** del conector, desde Linux o desde el M4.

No hace falta saber nada del proyecto «instrumento» de este repositorio. Ese
proyecto es la **implementación de referencia**: todo lo que aquí se cuenta
salió de él, y al final hay un mapa de dónde está cada pieza en su código.

**Niveles**, como en todo el repositorio:

- ✅ **verificado**: se ejecutó en la placa y se observó el resultado;
- ⚙️ **compiló**: se generó el binario, sin probarlo en la placa;
- 📄 **documentado**: solo está escrito.

Todo lo marcado ✅ se probó en una placa con esa imagen, entre agosto y
noviembre de 2026.

---

## 0. El mapa

```
 PC de compilación (Linux)                     Pico-Pi-i.MX7D
 ┌──────────────────────────┐   .bin   ┌───────────────────────────────────────────┐
 │ GNU Arm 10.3 + CMake 3.x │ ───────▶ │ partición FAT de arranque (mmcblk2p1)     │
 │ BSP FreeRTOS (freertos-tn)│  (scp)   │   uEnv.txt: m4image=mi_app.bin            │
 └──────────────────────────┘          │        │ U-Boot lo carga en la TCM y      │
                                       │        ▼ arranca el M4 ANTES que Linux     │
                                       │  ┌──────────────┐   RPMsg   ┌─────────────┐ │
                                       │  │ Cortex-M4    │ ◀───────▶ │ Cortex-A7   │ │
                                       │  │ FreeRTOS     │ texto:    │ Linux       │ │
                                       │  │ tu firmware  │ ttyRPMSG0 │ tus         │ │
                                       │  │              │ binario:  │ programas   │ │
                                       │  │              │ rpmsgN    │             │ │
                                       │  └──────┬───────┘           └──────┬──────┘ │
                                       │         └──── ECSPI3 (un dueño a la vez) ──┘ │
                                       │                    │                         │
                                       └────────────────────┼─────────────────────────┘
                                                            ▼
                                                  J8: MOSI 19, MISO 21,
                                                  SCLK 23, CS 26 → tu módulo SPI
```

| Pieza | Nivel | Sección |
|---|---|---|
| Firmware propio en el M4, cargado por U-Boot en cada arranque | ✅ | §3 |
| Ver desde Linux que el M4 está corriendo, sin consola serie | ✅ | §3.3 |
| RPMsg en texto (`/dev/ttyRPMSG0`) | ✅ 104/104 ecos, ~5 ms | §5 |
| RPMsg binario (`/dev/rpmsgN`, un `read()` = un mensaje) | ✅ | §6 |
| SPI desde Linux (`/dev/spidev2.0`) | ✅ con un ADS1220 | §7 |
| SPI desde el M4 (ECSPI3), quitándoselo a Linux en caliente | ✅ con un ADS1220, 20–600 SPS | §8 |
| Plantilla para un firmware nuevo (copiar y renombrar) | ⚙️ | §4 |
| Mensajes RPMsg de hasta 496 bytes de datos | 📄 (probado hasta 112) | §6 |

---

## 1. Qué trae la imagen de fábrica y qué hay que añadir

| Necesitas | ¿Lo trae la fábrica? | Qué hacer |
|---|---|---|
| Que U-Boot cargue el M4 | ✅ sí: `m4image`, `loadm4image` y `m4boot` ya están en su entorno | Copiar tu `.bin` a la FAT y apuntar `m4image` en `uEnv.txt` (§3) |
| Device tree con el M4 y RPMsg | ✅ sí: `imx7d-pico-pi-qca-m4.dtb` (el único de la FAT) | Nada |
| `/dev/ttyRPMSG0` | ✅ sí: módulo `imx_rpmsg_tty` | `modprobe imx_rpmsg_tty`; para cada arranque, `/etc/modules-load.d/` |
| Un log que no se llene con cada mensaje | ❌ el `imx_rpmsg_tty` de fábrica **vuelca cada mensaje** al log del kernel | Sustituir el módulo: **precompilado** en [`kernel/modulos/`](../kernel/modulos/LEEME.md) (§5.3) |
| `/dev/rpmsg_ctrl0` y `/dev/rpmsgN` (binario) | ❌ el kernel los espera pero no trae los drivers | Instalar `rpmsg_char` y `rpmsg_ctrl`: **precompilados** en [`kernel/modulos/`](../kernel/modulos/LEEME.md) (§6.1) |
| `/dev/spidev2.0` | ✅ sí: ECSPI3 con `spidev`, que no usa nadie | Nada, para usarlo desde Linux |
| SPI para el M4 | — | Desligar el driver en caliente, sin tocar el device tree (§8) |

Nada de esta guía toca **U-Boot**, el **device tree** ni el `zImage`. Los
módulos que se añaden tienen los mismos CRC que el kernel de fábrica y cargan
sin reemplazarlo. El método está en [`Kernel_Recompilacion.md`](Kernel_Recompilacion.md).

---

## 2. El PC de compilación

Un Linux x86-64 (se usó Ubuntu 24.04, también dentro de WSL2):

    sudo apt install cmake            # 3.28 en Ubuntu 24.04. CMake 4.x NO sirve
    # GNU Arm Embedded 10.3-2021.10, descomprimido en ~/opt:
    #   https://developer.arm.com/downloads/-/gnu-rm
    git clone -b freertos_1.0.1_imx7d https://github.com/TechNexion/freertos-tn.git
    git -C freertos-tn checkout 3f714904420b9eca36d43ee3b2a3ebb629d02e93
    git -C freertos-tn apply ../bsp/freertos-tn-cambios-locales.patch
    source scripts/env-m4.sh          # ARMGCC_DIR, PATH, BSP_DIR, BOARD_DIR
    ./scripts/build-m4.sh blinking_imx_demo release clean

- **CMake 4 aborta** en el `cmake_minimum_required(VERSION 2.6)` del BSP. Usa 3.x.
- **GCC 13.2 también compila**, pero todo lo verificado en la placa se compiló
  con 10.3. Si cambias de compilador, vuelve a probar en la placa.
- **La placa del BSP es `examples/imx7d_pico_m4`.** Las otras (`sdb`, `val`,
  `edm1`) enlazan sin quejarse y fallan en silencio: otro UART de depuración,
  otro mux de pines, otra memoria para RPMsg.
- Cada compilación deja en `<app>/armgcc/release/` el `.bin` (lo que se carga),
  el `.elf` (con símbolos) y el `.map`.

---

## 3. Cargar un firmware en el M4 y saber que corre ✅

### 3.1 Cómo arranca el M4

U-Boot lee `uEnv.txt` de la partición FAT, carga el fichero que dice `m4image`
en la **TCM** (dirección `0x7F8000` vista desde el A7, `0x1FFF8000` vista desde
el M4) y arranca el M4 con `bootaux`. Después arranca Linux con el device tree
`-m4`. **El M4 arranca antes que Linux** y no se puede recargar desde Linux: el
i.MX7 no tiene remoteproc completo. **Cambiar el firmware exige reiniciar.**

### 3.2 Desplegar

Desde el PC (`<ip>` es la de tu placa):

    scp freertos-tn/examples/imx7d_pico_m4/demo_apps/mi_app/armgcc/release/mi_app.bin ubuntu@<ip>:/tmp/

En la placa:

    sudo mount /dev/mmcblk2p1 /mnt
    sudo cp /tmp/mi_app.bin /mnt/mi_app.bin
    grep -a '^m4image' /mnt/uEnv.txt        # ¿hay ya una línea?
    # si la hay:
    sudo sed -i 's/^m4image=.*/m4image=mi_app.bin/' /mnt/uEnv.txt
    # si no la hay (el uEnv.txt de fábrica va en CRLF; la línea nueva, en LF):
    printf 'm4image=mi_app.bin\n' | sudo tee -a /mnt/uEnv.txt
    sync; sudo umount /mnt; sudo reboot

> ⚠️ **La trampa que deja la placa sin arrancar.** En la FAT **solo existe el
> DTB `imx7d-pico-pi-qca-m4.dtb`**. Si el fichero que dice `m4image` no existe,
> U-Boot se salta el M4, construye el nombre del DTB **sin** `-m4`, no lo
> encuentra y **Linux no arranca**. Nunca borres el binario al que apunta
> `m4image`: sustitúyelo. Usa nombres cortos, sin espacios.

**Volver atrás:** apunta `m4image` al binario anterior (guárdalo con otro
nombre en la FAT antes de sustituirlo) y reinicia.

### 3.3 ¿Está corriendo? Sin consola serie

La salida `PRINTF` del M4 va a **UART6** (J8: pin 8 TX, pin 10 RX, pin 9 GND;
115200 8N1, 3,3 V), que necesita un adaptador USB-serie. Sin él hay dos vías:

- **El LED de usuario.** Si tu firmware configura GPIO2_IO06 con el RDC abierto
  a todos los dominios (`RDC_SetPdapAccess(RDC, BOARD_GPIO_LED_RDC_PDAP, 0xFF,
  false, false)`, como el `blinking_imx_demo`), Linux lo ve como **gpio 38**:

      echo 38 | sudo tee /sys/class/gpio/export
      cat /sys/class/gpio/gpio38/direction     # «out» = el M4 lo configuró: arrancó

  **Solo lee.** Escribir en `direction` le quita la salida al M4.
- **RPMsg.** Si tu firmware responde por RPMsg (§5), un `hola` y su respuesta
  bastan.

---

## 4. Tu propio proyecto en el M4 ⚙️

### 4.1 Partir de una plantilla

El ejemplo `instrumento` (que trae el parche del BSP) ya tiene FreeRTOS, RPMsg,
el driver del ECSPI y el LED en su `CMakeLists.txt`. Copiarlo y renombrarlo
**compila** (comprobado el 2026-11-13 sobre un clon limpio del BSP):

    cd freertos-tn/examples/imx7d_pico_m4/demo_apps
    cp -r instrumento mi_app && cd mi_app
    rm -rf armgcc/release armgcc/debug armgcc/CMakeFiles armgcc/CMakeCache.txt \
           armgcc/Makefile armgcc/cmake_install.cmake prueba_host.*
    mv instrumento.c mi_app.c
    sed -i 's/instrumento/mi_app/g' armgcc/CMakeLists.txt
    cd ../../../../.. && ./scripts/build-m4.sh mi_app release

Después, reduce `mi_app.c` a lo que necesites. Lo mínimo que conviene
conservar está en §5.1 (RPMsg) y §8.2 (SPI). Si partes de un ejemplo del BSP
de otra profundidad de directorios (los de `rpmsg/` están un nivel más abajo),
las rutas `../../../../../` del `CMakeLists.txt` cambian.

**`hardware_init.c`** es el sitio del RDC y de los relojes de arranque. El de la
plantilla abre el MU (el buzón que usa RPMsg) y el LED.

### 4.2 Las reglas del M4 en esta placa

| Regla | Por qué |
|---|---|
| **Código ≤ ~31 KB, datos ≤ 32 KB** | Va enlazado a la TCM: `m_text` 0x7DC0 B, `m_data` 0x8000 B. El montón de FreeRTOS (`configTOTAL_HEAP_SIZE`) se lleva 20 KB de los datos. La plantilla usa ~25 KB de código |
| **No uses los GPT** para medir tiempo | Linux mantiene apagado su reloj (`gpt3_root_clk enable_count=0`): intervalos de 0,5 a 36 s en vez de 100 ms. Usa `vTaskDelay`/`vTaskDelayUntil` (SysTick, 1 ms) |
| **Para medir en µs, el contador de ciclos DWT** | Es del propio núcleo, a 240 MHz; da la vuelta cada 17,9 s. Ver `ciclos_init()` en la plantilla |
| **No hay `pdMS_TO_TICKS`** | Es FreeRTOS V8.0.0. Con `configTICK_RATE_HZ` = 1000, 1 tick = 1 ms |
| **Evita `printf`, `sprintf` y `sinf`** | Arrastran KB de newlib que no caben bien en la TCM. La plantilla formatea a mano (`pon_int`, `pon_par`) |
| **El `assert` de newlib cuesta ~4 KB** | El BSP deja los `assert` activos. La plantilla define un `__assert_func` propio que hace parpadear el LED |
| **No esperes a Linux** | El M4 arranca antes. Haz que trabaje solo y que hable cuando Linux aparezca (`rpmsg_rtos_init` bloquea hasta entonces: ponlo en su propia tarea) |
| **Linux no puede pararlo** | Diseña órdenes de «empieza» y «para» desde el primer día (§9) |

---

## 5. RPMsg en texto: `/dev/ttyRPMSG0` ✅

### 5.1 Lado M4

Una tarea de comunicación, como en la plantilla (`TareaCom`):

```c
static struct rpmsg_channel *canal;
static char rx[RPMSG_BUFFER_SIZE], tx[RPMSG_BUFFER_SIZE];

static void TareaCom(void *pv)
{
    struct remote_device *rdev = NULL;
    unsigned long src;
    int len;
    /* bloquea hasta que Linux carga su lado */
    if (rpmsg_rtos_init(0, &rdev, RPMSG_MASTER, &canal) != 0) for (;;) { }
    for (;;) {
        /* sin bloquear (último argumento 0): así la tarea puede hacer más cosas */
        while (rpmsg_rtos_recv(canal->rp_ept, rx, &len, sizeof(rx) - 1, &src, 0)
               == RPMSG_SUCCESS) {
            rx[len] = '\0';
            /* ... interpretar la orden ... y responder A QUIEN LA ENVIÓ: */
            rpmsg_rtos_send(canal->rp_ept, "OK\n", 3, src);
        }
        vTaskDelay(20);
    }
}
```

Y en `main()`, antes de `vTaskStartScheduler()`, el buzón:

```c
MU_Init(BOARD_MU_BASE_ADDR);
NVIC_SetPriority(BOARD_MU_IRQ_NUM, 3);
NVIC_EnableIRQ(BOARD_MU_IRQ_NUM);
/* y el manejador: */
void BOARD_MU_HANDLER(void) { rpmsg_handler(); }
```

- **Responde a `src`**, la dirección de origen de lo que recibes, no a
  `canal->dst`. Si no, las respuestas a un endpoint binario (§6) acaban en el tty.
- **Termina cada mensaje de texto en `\n`**: el tty no conserva las fronteras de
  los mensajes.
- Al cargar `imx_rpmsg_tty`, **Linux envía `hello world!`** al M4. Ignóralo o
  trátalo como un saludo.

### 5.2 Lado Linux

    sudo modprobe imx_rpmsg_tty                     # aparece /dev/ttyRPMSG0
    sudo stty -F /dev/ttyRPMSG0 raw -echo           # IMPRESCINDIBLE: sin eco
    cat /dev/ttyRPMSG0 &
    echo "hola" | sudo tee /dev/ttyRPMSG0

**Sin `raw -echo`, el tty devuelve al M4 todo lo que el M4 envía**, y el M4 lo
toma por órdenes. En Python:

```python
import os, termios, tty
fd = os.open("/dev/ttyRPMSG0", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
tty.setraw(fd)
a = termios.tcgetattr(fd)
a[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON)
termios.tcsetattr(fd, termios.TCSANOW, a)
os.write(fd, b"hola\n")
```

Para que se cargue en cada arranque: `echo imx_rpmsg_tty | sudo tee
/etc/modules-load.d/rpmsg.conf`. Para usarlo sin `sudo`, añade tu usuario al
grupo `dialout`.

### 5.3 El log: corrígelo antes de enviar datos de verdad

El `imx_rpmsg_tty` de fábrica escribe **cada mensaje recibido** en el log del
kernel, en hexadecimal. A 10 mensajes por segundo fueron **1583 líneas en
35 s**, guardadas dos veces (journal y syslog) en la eMMC. La corrección es una
línea ([`kernel/imx_rpmsg_tty-sin-volcado.patch`](../kernel/imx_rpmsg_tty-sin-volcado.patch)).
**El módulo ya corregido está en [`kernel/modulos/`](../kernel/modulos/LEEME.md)**,
listo para el kernel de fábrica. Si tienes otro kernel, se recompila dentro del árbol del kernel de fábrica
([`Seccion_README_RPMsg.md`](Seccion_README_RPMsg.md),
[`Kernel_Recompilacion.md`](Kernel_Recompilacion.md)). Verificado: 25 s a 250
muestras/s, **0 líneas** en el log.

---

## 6. RPMsg binario: `/dev/rpmsgN` ✅

El tty sirve para órdenes. Para **datos**, mejor un endpoint de `rpmsg_char`: un
`write()` es exactamente un mensaje y un `read()` devuelve exactamente uno, con
sus bytes tal cual. Así no se convierten números a texto y de vuelta.

### 6.1 Los dos módulos que faltan

> **Atajo:** si `uname -r` da `5.10.72-g7966a667bd89-dirty`, el kernel de
> fábrica, están **precompilados** en [`kernel/modulos/`](../kernel/modulos/LEEME.md),
> junto con el `imx_rpmsg_tty` corregido y las instrucciones para instalarlos.
> Son los mismos que corren en la placa de este proyecto. Lo que sigue es para
> compilarlos tú.

El kernel de fábrica ya crea el dispositivo `virtio0.rpmsg_ctrl.0.0`, pero lo
deja sin driver. Hay que compilar `rpmsg_char` y `rpmsg_ctrl` como módulos
contra el árbol del kernel de fábrica, con el mismo `.config` y el mismo
`LOCALVERSION`:

    scripts/config --module RPMSG_CHAR --module RPMSG_CTRL   # o usa kernel/config-modulos-rpmsg
    make olddefconfig && make -j$(nproc)     # → drivers/rpmsg/rpmsg_char.ko, rpmsg_ctrl.ko

Comprobado: `vermagic` idéntico al del kernel vivo, y **los 94 símbolos que
importan, con el mismo CRC**. Se instalan sin reiniciar:

    sudo cp rpmsg_char.ko rpmsg_ctrl.ko /lib/modules/$(uname -r)/kernel/drivers/rpmsg/
    sudo depmod -a
    sudo modprobe rpmsg_ctrl                 # carga antes rpmsg_char → /dev/rpmsg_ctrl0
    echo rpmsg_ctrl | sudo tee -a /etc/modules-load.d/rpmsg.conf

Cómo preparar el árbol del kernel: [`Kernel_Recompilacion.md`](Kernel_Recompilacion.md).

### 6.2 Permisos

Para usarlos sin `root`:

- **Los `/dev/rpmsgN`** se resuelven con una regla de udev,
  `/etc/udev/rules.d/60-rpmsg.rules`:

      KERNEL=="rpmsg[0-9]*", GROUP="dialout", MODE="0660"

- **`/dev/rpmsg_ctrl0` no**: nace **sin clase** en sysfs y udev no le aplica
  reglas. Hace falta un servicio *oneshot*,
  `/etc/systemd/system/rpmsg-permisos.service`:

  ```ini
  [Unit]
  Description=Permisos de /dev/rpmsg_ctrl0 para el grupo dialout
  After=systemd-modules-load.service
  Wants=systemd-modules-load.service

  [Service]
  Type=oneshot
  ExecStart=/bin/sh -c "for i in $(seq 60); do [ -c /dev/rpmsg_ctrl0 ] && break; sleep 1; done; chgrp dialout /dev/rpmsg_ctrl0 && chmod 0660 /dev/rpmsg_ctrl0"
  RemainAfterExit=yes

  [Install]
  WantedBy=multi-user.target
  ```

      sudo systemctl daemon-reload && sudo systemctl enable --now rpmsg-permisos

### 6.3 Lado Linux: crear el endpoint, enviar y recibir

```python
import fcntl, glob, os, struct, time
RPMSG_CREATE_EPT_IOCTL  = 0x4028b501     # _IOW(0xb5, 1, struct rpmsg_endpoint_info)
RPMSG_DESTROY_EPT_IOCTL = 0xb502         # _IO(0xb5, 2)
NOMBRE = b"mi-app-bin"

def busca():                             # reutiliza uno huérfano con tu nombre
    for d in sorted(glob.glob("/sys/class/rpmsg/rpmsg[0-9]*")):
        if open(d + "/name").read().strip().encode() == NOMBRE:
            return "/dev/" + os.path.basename(d)

ruta = busca()
if not ruta:
    ctrl = os.open("/dev/rpmsg_ctrl0", os.O_RDWR)
    # struct rpmsg_endpoint_info { char name[32]; u32 src; u32 dst; }
    # src = cualquiera (0xFFFFFFFF); dst = 0, el endpoint del M4 en este BSP
    fcntl.ioctl(ctrl, RPMSG_CREATE_EPT_IOCTL, struct.pack("32sII", NOMBRE, 0xFFFFFFFF, 0))
    os.close(ctrl)
    for _ in range(50):                  # udev tarda un poco en crear el nodo
        ruta = busca()
        if ruta: break
        time.sleep(0.05)
ep = os.open(ruta, os.O_RDWR)
os.write(ep, b"bin")                     # alta: el M4 aprende esta dirección
msg = os.read(ep, 512)                   # un read = un mensaje del M4
# ... al terminar:
os.write(ep, b"bin 0")                   # baja
fcntl.ioctl(ep, RPMSG_DESTROY_EPT_IOCTL)
os.close(ep)
```

### 6.4 Lado M4: enviar a quien se dio de alta

El M4 no sabe de antemano la dirección del endpoint de Linux. La **aprende** del
primer mensaje que recibe por él: es el `src` de `rpmsg_rtos_recv()`. A partir
de ahí le envía los bloques:

```c
static unsigned long dst_bin;            /* 0 = nadie suscrito */
static TickType_t    ult_latido;

/* al recibir «bin» por cualquier endpoint: */
dst_bin = src; ult_latido = xTaskGetTickCount();
/* al recibir «bin 0»: */
dst_bin = 0;

/* en el bucle: sin latido en 2 s, se deja de enviar */
if (dst_bin && xTaskGetTickCount() - ult_latido > 2000) dst_bin = 0;

/* enviar un bloque binario */
if (dst_bin) rpmsg_rtos_send(canal->rp_ept, buf, len, dst_bin);
```

**Formato.** Define una **cabecera fija** con un primer byte que no sea ASCII,
para que no se confunda con texto. Incluye un contador de secuencia, para
detectar bloques perdidos, y el índice de la primera muestra. El del ejemplo
(little-endian, 12 B + `n` × `int32`):

| Byte | Tipo | Campo |
|---|---|---|
| 0 | u8 | `0xB1` (bloque, formato 1) |
| 1 | u8 | `n`, número de muestras |
| 2 | u8 | indicadores |
| 3 | u8 | reservado |
| 4 | u16 | muestras/s |
| 6 | u16 | `seq` (se incrementa en cada bloque) |
| 8 | u32 | índice de la primera muestra |
| 12 | i32 × n | muestras |

En Linux: `n, flags, fs, seq, ini = struct.unpack_from("<xBBxHHI", msg)` y
`array.array("i", msg[12:])`.

**Tamaño.** El búfer de RPMsg es de 512 B, con 16 de cabecera: caben **496 B de
datos por mensaje** (📄; el ejemplo usa 112 B por bloque). Agrupa las muestras:
unos 10 mensajes por segundo funcionan bien.

### 6.5 Si el programa de Linux muere sin despedirse

- **El log se llena.** El endpoint muere con el descriptor, y cada mensaje que
  el M4 siga enviando a esa dirección produce un `msg received with no
  recipient`, sin límite de frecuencia. **Remedio: el latido.** Linux envía `bin`
  cada 0,5 s y el M4 deja de enviar tras 2 s sin latido. Medido: 19 avisos y
  silencio.
- **Queda un nodo huérfano.** `/dev/rpmsgN` sigue existiendo aunque su endpoint
  haya muerto. Por eso el ejemplo de §6.3 busca primero uno con su nombre y lo
  reutiliza.

### 6.6 Reparto recomendado

| Canal | Para qué |
|---|---|
| `/dev/ttyRPMSG0` (texto) | Órdenes y respuestas: legibles, depurables con `echo` y `cat` |
| `/dev/rpmsgN` (binario) | Bloques de datos con cabecera fija |

---

## 7. SPI desde Linux: `/dev/spidev2.0` ✅

### 7.1 Conexión al J8

| Señal | Pin J8 | Notas |
|---|---|---|
| 3,3 V | 1 | alimenta el módulo. **Nada de 5 V en las señales** |
| GND | 20 o 25 | |
| MOSI (ECSPI3) | 19 | |
| MISO (ECSPI3) | 21 | |
| SCLK (ECSPI3) | 23 | |
| **CS** | **26** | `GPIO4_IO11`, gpio 107 de Linux. Medido: **no** sale por el 24, aunque tablas antiguas lo digan |

> ⚠️ **No todos los pines de J8 aceptan entradas.** Los 36 y 11 (probados con un
> DRDY real) **solo funcionan como salida**: la placa base empuja esas líneas.
> Los cuatro de ECSPI3 sí son bidireccionales. Antes de leer una señal por otro
> pin de J8, compruébalo con una señal real.

ECSPI1 y ECSPI2 no sirven: sus pads los usa el combo WiFi/Bluetooth. ECSPI4 no
tiene pads. **ECSPI3 es el único SPI que llega al conector.**

### 7.2 Desde Python, sin dependencias

`python3-spidev` es opcional. Con `ioctl` basta:

```python
import array, fcntl, os, struct
SPI_IOC_WR_MODE         = 0x40016B01     # _IOW('k', 1, u8)
SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04     # _IOW('k', 4, u32)
SPI_IOC_MESSAGE_1       = 0x40206B00     # _IOW('k', 0, struct spi_ioc_transfer[1])
HZ = 1_000_000

fd = os.open("/dev/spidev2.0", os.O_RDWR)
fcntl.ioctl(fd, SPI_IOC_WR_MODE, struct.pack("B", 1))          # modo SPI de tu módulo
fcntl.ioctl(fd, SPI_IOC_WR_MAX_SPEED_HZ, struct.pack("I", HZ))

def xfer(datos):
    """Full-duplex, con CS bajo durante todo el bloque."""
    tx = array.array("B", datos); rx = array.array("B", bytes(len(tx)))
    t = struct.pack("QQIIHBBBBBB", tx.buffer_info()[0], rx.buffer_info()[0],
                    len(tx), HZ, 0, 8, 0, 0, 0, 0, 0)
    fcntl.ioctl(fd, SPI_IOC_MESSAGE_1, t)
    return bytes(rx)
```

El ejemplo completo con un ADS1220 está en [`a7/ads1220_prueba.py`](../a7/ads1220_prueba.py).

> ⚠️ **No leas registros del SoC con `/dev/mem` desde Linux.** Una lectura del
> CCM colgó la placa. Si necesitas ver un registro, que lo lea el M4 y lo cuente
> por RPMsg.

---

## 8. SPI desde el M4 ✅

Si el SPI tiene que ir a ritmo fijo (un ADC, por ejemplo), mejor desde el M4.
Linux es el dueño de ECSPI3 al arrancar; **se le quita en caliente** y se le
devuelve igual, sin tocar el device tree.

### 8.1 Las cuatro piezas que deben estar de acuerdo

| Pieza | Qué controla | Qué se hace |
|---|---|---|
| Driver de Linux (`spi_imx`) | si Linux usa el periférico | se **desliga** (`unbind`) y se religa (`bind`) |
| **RDC** | qué dominio puede tocar el periférico | acceso **para todos** (`0xFF`), nunca exclusivo: el M4 arranca antes que Linux, y un RDC cerrado rompería el arranque del driver |
| **CCM** (reloj) | que el periférico tenga reloj | el M4 enciende el *root* y la puerta para todos los dominios. **No cambia la fuente** (Linux deja 60 MHz): la lee |
| IOMUXC (pads) | qué señal sale por cada patilla | nada: Linux ya deja los pads en modo ECSPI3, y el CS como GPIO |

**Un solo dueño a la vez.** Nada en el hardware impide que los dos escriban a la
vez: el orden lo pones tú.

### 8.2 El traspaso, paso a paso

**1. Linux suelta** (`root`):

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/unbind
    # /dev/spidev2.0 desaparece. No es persistente: al reiniciar, vuelve a Linux.

**2. El M4 toma ECSPI3** (al recibir una orden por RPMsg, nunca al arrancar):

```c
#include "ecspi.h"          /* y añade platform/drivers/src/ecspi.c al CMakeLists */

static uint32_t ecspi3_reloj(void)          /* lee la fuente que dejó Linux */
{
    uint32_t pre, post, hz;
    CCM_GetRootDivider(CCM, ccmRootEcspi3, &pre, &post);
    switch (CCM_GetRootMux(CCM, ccmRootEcspi3)) {
    case ccmRootmuxEcspiOsc24m:     hz =  24000000u; break;
    case ccmRootmuxEcspiSysPllDiv2: hz = 240000000u; break;   /* la de Linux */
    case ccmRootmuxEcspiSysPllDiv4: hz = 120000000u; break;
    case ccmRootmuxEcspiSysPllDiv1: hz = 480000000u; break;
    case ccmRootmuxEcspiSysPllPfd4: hz = CCM_ANALOG_GetPfdFreq(CCM_ANALOG, ccmAnalogPfd4Frac); break;
    default: return 0;
    }
    return hz / (pre + 1) / (post + 1);     /* con Linux: 60 MHz */
}

static int ecspi3_toma(uint32_t baudios)
{
    ecspi_init_config_t c;
    uint32_t hz;
    RDC_SetPdapAccess(RDC, rdcPdapEcspi3, 0xFF, false, false);
    CCM_EnableRoot(CCM, ccmRootEcspi3);
    CCM_ControlGate(CCM, ccmCcgrGateEcspi3, ccmClockNeededAll);
    if (!(hz = ecspi3_reloj())) return 0;
    memset(&c, 0, sizeof(c));
    c.clockRate      = hz;
    c.baudRate       = baudios;
    c.channelSelect  = ecspiSelectChannel0;
    c.mode           = ecspiMasterMode;
    c.burstLength    = 7;                           /* 8 bits */
    c.clockPhase     = ecspiClockPhaseSecondEdge;   /* CPHA=1 ... */
    c.clockPolarity  = ecspiClockPolarityActiveHigh;/* ... CPOL=0: modo SPI 1 */
    c.ecspiAutoStart = false;
    ECSPI_Init(ECSPI3, &c);
    ECSPI_SetBaudRate(ECSPI3, hz, baudios);
    while (ECSPI_GetRxfifoCounter(ECSPI3)) (void)ECSPI_ReceiveData(ECSPI3);
    /* CS: GPIO4_IO11, manejado a mano. GPIO4 lo comparte Linux: solo su bit. */
    RDC_SetPdapAccess(RDC, rdcPdapGpio4, 0xFF, false, false);
    GPIO_DR_REG(GPIO4)   |= (1u << 11);             /* alto antes de ser salida */
    GPIO_GDIR_REG(GPIO4) |= (1u << 11);
    return 1;
}

static int ecspi3_byte(uint8_t sale, uint8_t *entra)    /* con plazo de 1 ms */
{
    uint32_t t0 = DWT->CYCCNT;
    ECSPI_SendData(ECSPI3, sale);
    ECSPI_StartBurst(ECSPI3);
    while (!ECSPI_GetStatusFlag(ECSPI3, ecspiFlagRxfifoReady))
        if (DWT->CYCCNT - t0 > 240000u) return 0;
    *entra = (uint8_t)ECSPI_ReceiveData(ECSPI3);
    return 1;
}

#define CS_BAJO()  (GPIO_DR_REG(GPIO4) &= ~(1u << 11))
#define CS_ALTO()  (GPIO_DR_REG(GPIO4) |=  (1u << 11))
/* una transacción: CS_BAJO(); ecspi3_byte(...) por cada byte; CS_ALTO(); */
```

- **Primera prueba sin cables:** el lazo interno (`ECSPI_TESTREG_REG(ECSPI3) |=
  ECSPI_TESTREG_LBC_MASK`) devuelve por RX lo que sale por TX dentro del
  periférico. Si 256 bytes vuelven iguales, el M4 tiene reloj, permisos y
  registros. Resultado medido: 256/256 a 1 MHz.
- **GPIO4 es compartido**: Linux usa otros bits de ese banco (reguladores, WiFi).
  Toca solo tus bits, con lectura-modificación-escritura en `DR` y `GDIR`, y
  nunca los registros de interrupción (`IMR`, `ISR`).
- El modo SPI se elige con `clockPhase` y `clockPolarity`. Consulta la hoja de
  datos de tu módulo.

**3. El M4 suelta** (también por orden):

```c
CS_ALTO();
ECSPI_CONREG_REG(ECSPI3) = 0;       /* módulo apagado; relojes y pads como estaban */
```

**4. Linux recupera:**

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/bind

**El orden no es negociable:** primero suelta Linux y después toma el M4; al
volver, primero suelta el M4 y después liga Linux. En el ciclo completo,
`dmesg` no registró ni una línea.

**Para automatizarlo sin `root`** hay un ayudante,
[`a7/spi-m4`](../a7/spi-m4) (`ceder`, `devolver`, `estado`), con una regla de
`sudoers` que permite ejecutar solo ese script
([`a7/LEEME.md`](../a7/LEEME.md)).

### 8.3 Si tu módulo tiene una línea de «dato listo»

Un ADC suele avisar con un pin DRDY. En esta placa **no hay un pin de entrada
probado en J8** fuera de los de ECSPI3 (§7.1). El ADS1220 lo resolvió con su
modo **DRDYM**: avisa por la propia línea MISO, y el M4 la lee cambiando un
momento el pad de MISO a GPIO. Detalle en [`SPI_M4_ECSPI3.md`](SPI_M4_ECSPI3.md).
Si tu módulo no tiene nada parecido, sondea a tiempo fijo con `vTaskDelayUntil`.

---

## 9. Repartir el trabajo entre el M4 y los A7

Lo que funcionó:

- **El M4 hace lo continuo y puntual:** leer el periférico, filtrar, detectar.
  Lo pone en una **cola de FreeRTOS** y otra tarea, de menor prioridad, lo envía
  por RPMsg. La tarea de adquisición **nunca espera a Linux**: si la cola se
  llena, cuenta el mensaje como perdido y sigue.
- **Linux hace lo pesado:** mostrar, guardar, analizar, la red.
- **El protocolo tiene, desde el primer día:**
  - órdenes de **empezar y parar**: el M4 arranca **sin transmitir**;
  - un **saludo** con nombre y versión del firmware;
  - una **línea de estado** periódica (`clave=valor`) con contadores: muestras,
    perdidos, carga;
  - **número de secuencia** en cada bloque, para que Linux detecte huecos;
  - **latido** si hay canal binario (§6.5).
- **Mide el tiempo con el M4.** El oscilador de un ADC puede desviarse más del
  1 %: el ejemplo midió 88,08 muestras/s a 90 nominales, contando muestras
  durante 10 s del contador de ciclos. Un filtro calculado con la tasa nominal
  falla: el notch de red pasa de más de 100 dB a solo 1,4 dB.

---

## 10. Trampas, en una lista

1. Placa del BSP: **`imx7d_pico_m4`**, no `sdb`.
2. **Nunca dejes `m4image` apuntando a un fichero que no existe**: Linux no
   arranca.
3. `uEnv.txt` de fábrica en CRLF; tus líneas, en LF.
4. **CMake 3.x**, no 4.
5. **Ni GPT ni `/dev/mem`.**
6. Cambiar el firmware del M4 **exige reiniciar**.
7. Tty sin `raw -echo` = eco de vuelta al M4.
8. El `imx_rpmsg_tty` de fábrica **llena el log**.
9. **Responde al `src`** de cada mensaje.
10. **Latido** en el canal binario, y reutiliza los `/dev/rpmsgN` huérfanos.
11. **CS en J8-26**, y los pines 36 y 11 de J8 **solo como salida**.
12. ECSPI3, **un dueño a la vez**: `unbind` → M4 → suelta → `bind`.
13. Sin RTC con pila, la hora de Linux depende de NTP: no confíes en ella para
    fechar muestras sin GPS.

---

## 11. Dónde está cada pieza en la implementación de referencia

El firmware `instrumento` (fuente en el parche de [`bsp/`](../bsp/LEEME.md),
`examples/imx7d_pico_m4/demo_apps/instrumento/instrumento.c`) y su lado Linux
en [`a7/`](../a7/LEEME.md):

| Pieza | Dónde |
|---|---|
| Arranque, buzón MU, tareas | `instrumento.c`: `main()`, `BOARD_MU_HANDLER()` |
| RPMsg: recibir, responder a `src`, latido | `instrumento.c`: `TareaCom()`, `orden()` |
| Bloque binario | `instrumento.c`: `envia_bin()` |
| Adquisición a ritmo fijo, sin esperar a Linux | `instrumento.c`: `TareaAdq()` |
| ECSPI3: reloj, toma, byte, lazo interno | `instrumento.c`: `ecspi3_reloj()`, `ecspi3_toma()`, `ecspi3_byte()`, `spi_lazo()` |
| Un dispositivo SPI concreto (ADS1220) | `instrumento.c`: `ads_toma()`, `ads_lee()`, `ads_suelta()`, `ads_drdy_alto()` |
| Contador de ciclos, carga, jitter | `instrumento.c`: `ciclos_init()`, final de `TareaAdq()` |
| Filtro digital en el M4 (notch IIR) y tasa real | `instrumento.c`: `notch_prepara()`, `notch_aplica()`, `TareaAdq()` |
| Probar la lógica en el PC, sin placa | `prueba_host.c` |
| Tty en Linux (crudo, sin eco) | `a7/visor_instrumento.py`: clase `Canal` |
| Endpoint binario (crear, reutilizar, latido, cerrar) | `a7/visor_instrumento.py`: clase `CanalBin` |
| Una orden suelta desde la terminal | `a7/m4orden.py` |
| SPI desde Linux con `ioctl` | `a7/ads1220_prueba.py` |
| Ceder y devolver el SPI | `a7/spi-m4` |

Historia y medidas: [`M4_Instrumento_Bitacora.md`](M4_Instrumento_Bitacora.md)
y [`SPI_M4_ECSPI3.md`](SPI_M4_ECSPI3.md).
