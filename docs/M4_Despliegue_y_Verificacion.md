# El Cortex-M4: cómo se le carga firmware y cómo se comprueba que corre

**2026-08-15** — Documento del primer **«verificado funcionando»** del proyecto.

---

## 0. El resultado, en una línea

El M4 ejecutó código nuestro y se pudo **demostrar desde Linux, sin consola
serie y sin cablear nada**.

```
LÍNEA BASE (firmware anterior, test_borrar.bin)
  GPIO2_IO06:  direccion=in    0 transiciones en 4 s

DESPUÉS (nuestro binario)
  GPIO2_IO06:  direccion=out   50 transiciones en 15 s
  intervalos:  900 900 900 900 900 999 1000 1000 1000 1000 1000 100 100 101 100 …
               min=100 ms   max=1000 ms   precision ±1 ms
```

Esos valores son literalmente los del código fuente: `blinkingInterval` sube en
escalones de 100 ms hasta 1000 y vuelve a `BLINKING_INTERVAL_MIN` = 100.

---

## 🆕 1. NOVEDADES — lo que no estaba documentado antes

Cinco cosas nuevas, todas comprobadas hoy. Son el verdadero contenido de este
documento.

### 🆕 1.1 Se puede observar al M4 desde Linux, por un GPIO compartido

**Este es el hallazgo más útil.** Hasta hoy se daba por sentado que verificar el
M4 exigía consola serie, porque su salida va por UART6, que Linux no ve. **No es
así.**

El `hardware_init.c` del demo contiene:

```c
RDC_SetPdapAccess(RDC, BOARD_GPIO_LED_RDC_PDAP, 0xFF, false, false);
```

El `0xFF` concede el periférico a **todos los dominios**, y el tercer parámetro
`false` significa **semáforo no requerido**. Es decir: el A7 puede leer ese GPIO
libremente, en paralelo con el M4 y sin disputarle nada.

El «USER LED» del BSP en esta placa es **GPIO2_IO06**, y en sysfs se numera:

```
30210000.gpio (GPIO2)  base=32  →  GPIO2_IO06 = 32 + 6 = 38
```

Así que `/sys/class/gpio/gpio38/value` es una ventana directa a lo que hace el
M4. **Verificación remota, sin hardware adicional.**

> ⚠️ **Al leerlo, no escribas nunca en `direction`.** Exportar y leer `value` no
> altera el hardware; escribir `direction` cambiaría el registro GDIR y le
> quitaría la salida al M4.

### 🆕 1.2 `direction` sirve como prueba por sí sola

Antes de cargar nuestro firmware el pin se leía como **`in`**; después, como
**`out`**. Ese cambio solo puede provenir de que **el M4 ejecutó
`GPIO_Ctrl_Init()`** y puso el bit GDIR. Es una comprobación instantánea de que
el firmware arrancó, incluso antes de mirar si conmuta.

### 🆕 1.3 `uEnv.txt` permite cambiar el firmware del M4 sin tocar el entorno

No hace falta `fw_setenv` (que no está instalado), ni `saveenv`, ni consola
serie. El `bootcmd` de este U-Boot hace:

```
if run loadbootenv; then run importbootenv; fi;     ← importa uEnv.txt
if test -n $uenvcmd; then run uenvcmd; fi;          ← y DESPUÉS arranca
```

`importbootenv` ejecuta `env import`, así que **cualquier variable escrita en
`uEnv.txt` sobrescribe la del entorno guardado**. Basta con añadir una línea:

```
m4image=mi_firmware.bin
```

Reversible borrando esa línea. Es la vía más segura para experimentar.

### 🆕 1.4 Linux le rompe el reloj del GPT3 al M4

El demo original **no funciona bien** en esta tarjeta, y la causa está
identificada. Usa `Hw_Timer_Delay()`, que se apoya en **GPT3**. Resultado:
intervalos erráticos de **0.5 a 36 segundos** en vez de 100–1000 ms.

Evidencia directa, de `/sys/kernel/debug/clk/clk_summary`:

```
                       enable_count  prepare_count
gpt1_root_clk                1            1        ← Linux lo usa: encendido
gpt3_root_clk                0            0        ← el del M4: apagado
```

Sustituir el retardo por `vTaskDelay()` —que usa el **SysTick del propio
Cortex-M4**, interno al núcleo— lo arregla por completo: precisión de ±1 ms.
La bisección es concluyente: el fallo **no es del M4, ni de FreeRTOS, ni del
BSP**, sino de la gestión de relojes de Linux.

> **Consecuencia para cualquier temporización precisa en el M4** (por ejemplo,
> muestrear un ADC a intervalos fijos): **no puede depender de un GPT** mientras Linux gestione ese reloj. Hay que
> reservar el periférico en el device tree, marcar el reloj como crítico, o
> apoyarse en el SysTick.

Se probó añadir `clk_ignore_unused` a la línea de comandos del kernel. **Llegó
al kernel pero no bastó** — el pin siguió lento. Queda como vía abierta.

### 🆕 1.5 Este FreeRTOS es V8.0.0 y no tiene `pdMS_TO_TICKS`

Al modificar el demo, `pdMS_TO_TICKS` **no compila**: se introdujo después.
Con `configTICK_RATE_HZ = 1000` (1 tick = 1 ms), lo correcto aquí es:

```c
vTaskDelay(blinkingInterval / portTICK_PERIOD_MS);
```

---

## 2. Cómo llega el firmware al M4

**No hay «acceso» al M4 en el sentido habitual.** No tiene consola alcanzable ni
se le conecta un depurador. La secuencia real es:

```
U-Boot  →  lee ${m4image} de la partición FAT
        →  lo copia a la TCM (0x7F8000 vista A7 = 0x1FFF8000 vista M4)
        →  bootaux lo arranca
        →  y DESPUÉS arranca Linux
```

Las variables implicadas, ya presentes de fábrica en este U-Boot:

```
tcm_addr=0x7F8000
m4image=<nombre del fichero en la FAT>
loadm4image=fatload mmc ${mmcdev}:${mmcpart} ${tcm_addr} ${m4image}
m4boot=if run loadm4image; then setenv mcu -m4; dcache flush; bootaux ${tcm_addr}; fi
```

Por tanto **cargar firmware al M4 = poner un fichero en la FAT y apuntar
`m4image` a él**. Nada más.

El binario debe estar enlazado a TCM. Se comprueba así:

```bash
arm-none-eabi-readelf -h fichero.elf | grep Entry     # 0x1fff8xxx
arm-none-eabi-objdump -h fichero.elf | grep interrupts # VMA 1fff8000
```

---

## 3. Procedimiento manual, paso a paso

### 3.1 Compilar

```bash
source scripts/env-m4.sh
cd ~/pico-pi-imx7d
./scripts/build-m4.sh blinking_imx_demo release clean
```

> ⚠️ **El binario NO se llama como el directorio.** El objetivo de CMake es
> `blinking_imx_demo_gpt`, así que la salida es
> `armgcc/release/blinking_imx_demo_gpt.bin`. Conviene mirar el `release/` antes
> de buscar un nombre que no existe.

### 3.2 Copiar el binario y apuntar `m4image` — desde el Linux de la tarjeta

Es la vía más cómoda, y funciona por SSH sin tocar el entorno de U-Boot:

```bash
# 1. llevar el fichero a la tarjeta
scp blinking_imx_demo_gpt.bin ubuntu@192.168.1.240:/tmp/

# 2. ya en la tarjeta: montar la partición de arranque
sudo mkdir -p /mnt/boot
sudo mount /dev/mmcblk2p1 /mnt/boot

# 3. copiar el firmware
sudo cp /tmp/blinking_imx_demo_gpt.bin /mnt/boot/

# 4. apuntar m4image (respaldando uEnv.txt antes)
sudo cp -a /mnt/boot/uEnv.txt /mnt/boot/uEnv.bak
sudo sh -c 'printf "m4image=blinking_imx_demo_gpt.bin\n" >> /mnt/boot/uEnv.txt'

# 5. cerrar y reiniciar
sudo sync
sudo umount /mnt/boot
sudo reboot
```

> ⚠️ **Cuidado con los finales de línea.** El `uEnv.txt` original usa **CRLF**.
> Escribe tus líneas con **LF** (`printf "...\n"`). Si `m4image` arrastrara un
> `\r`, U-Boot buscaría un fichero con retorno de carro en el nombre, no lo
> encontraría, y el M4 se quedaría sin firmware.

Si `m4image` ya existía en `uEnv.txt`, sustitúyela en vez de añadir otra:

```bash
sudo sed -i 's/^m4image=.*/m4image=mi_nuevo.bin/' /mnt/boot/uEnv.txt
```

### 3.3 Desde la consola serie de U-Boot — totalmente manual

Con la tarjeta detenida en el prompt `=>`:

**Permanente** (queda guardado en el entorno):
```
=> setenv m4image blinking_imx_demo_gpt.bin
=> saveenv
=> boot
```

**De una sola vez** (sin guardar nada, se pierde al reiniciar):
```
=> fatload mmc 0:1 0x7F8000 blinking_imx_demo_gpt.bin
=> dcache flush
=> bootaux 0x7F8000
=> boot
```

Comandos útiles para inspeccionar:
```
=> printenv m4image
=> printenv mcu
=> mmc list                 → FSL_SDHC: 0 (eMMC)
=> fatls mmc 0:1            → contenido de la partición de arranque
```

### 3.4 Si Linux no arranca: copiar el fichero por USB

Con la tarjeta en U-Boot:
```
=> ums 0 mmc 0
```
La eMMC aparece como memoria USB en el ordenador conectado; se copia el `.bin` y
se edita `uEnv.txt` como ficheros normales. `Ctrl+C` para salir.

---

## 4. Cómo comprobar que el M4 está corriendo

Todo desde el Linux de la tarjeta, sin hardware extra.

### 4.1 Comprobación rápida — ¿arrancó el firmware?

```bash
echo 38 | sudo tee /sys/class/gpio/export
cat /sys/class/gpio/gpio38/direction
```

- `in`  → el M4 **no** ha configurado el pin: su firmware no arrancó.
- `out` → el M4 ejecutó `GPIO_Ctrl_Init()`. **Ya está corriendo.**

### 4.2 Ver el parpadeo a ojo

```bash
watch -n 0.1 cat /sys/class/gpio/gpio38/value
```

### 4.3 Medición precisa de intervalos

```bash
sudo python3 - <<'PY'
import time
f = open("/sys/class/gpio/gpio38/value", "rb", buffering=0)
def rd():
    f.seek(0); return f.read(1)
prev = rd(); t0 = time.time(); trans = []
while time.time() - t0 < 15.0:
    v = rd()
    if v != prev:
        trans.append(time.time() - t0); prev = v
    time.sleep(0.001)
print(f"transiciones: {len(trans)}")
iv = [round((trans[i+1]-trans[i])*1000) for i in range(len(trans)-1)]
print("intervalos (ms):", iv)
PY
```

Con el demo correcto debe salir la serie 100 → 1000 → 100 en escalones de 100 ms.

### 4.4 Comprobar que se cargó el device tree del M4

```bash
ls /dev/ttymxc*      # deben salir ttymxc4 y ttymxc6, NUNCA ttymxc5
```

`ttymxc5` sería UART6, que el firmware del M4 se reserva vía RDC. Si aparece, el
DTB `-m4` no se cargó.

---

## 5. Volver atrás

Todo lo de este documento es reversible:

```bash
sudo mount /dev/mmcblk2p1 /mnt/boot
sudo cp -a /mnt/boot/uEnv.bak /mnt/boot/uEnv.txt   # restaura el uEnv original
sudo sync; sudo umount /mnt/boot; sudo reboot
```

Los binarios anteriores siguen en la FAT (`test_borrar.bin`,
`blinking_imx_demo_gpt.bin`), así que basta con reapuntar `m4image`.

**El código fuente** también: `main.c.orig` conserva el original del demo, y la
modificación está comentada en `main.c` explicando el porqué.

> **Nota sobre el riesgo:** un `m4image` erróneo **no rompe el arranque de
> Linux**. `mcu=-m4` está guardado en el entorno de U-Boot, así que el DTB
> correcto se elige aunque `loadm4image` falle. El peor caso es que el M4 se
> quede sin firmware.

---

## 6. Estado y datos de referencia

| | |
|---|---|
| Firmware activo | `blink_tick.bin` (13 896 B), demo con `vTaskDelay` |
| También en la FAT | `blinking_imx_demo_gpt.bin` (14 996 B, versión GPT, **funciona mal**), `test_borrar.bin` (17 184 B, firmware de 2023) |
| Enlace | TCM, entry `0x1FFF82FD`, `.interrupts` en `0x1FFF8000` |
| Entorno de U-Boot vivo | el del offset **512 k** (`m4image`, `mcu=-m4`, `bootdelay=4`) |
| GPIO observado | GPIO2_IO06 = sysfs **38** (`30210000.gpio`, base 32) |
| GPT del demo | **GPT3** (`0x302F0000`), `disabled` en el DT de Linux |
| FreeRTOS | **V8.0.0** (2014) |
| `configTICK_RATE_HZ` | 1000 (1 tick = 1 ms) |

### Lo que sigue sin resolverse

- **El reloj del GPT3.** `clk_ignore_unused` no fue suficiente. Mientras tanto,
  usar `vTaskDelay`.
- **La salida por UART6 del M4** sigue sin poder leerse: hace falta un segundo
  adaptador serie de 3.3 V sobre el conector de expansión. Sin confirmar cuál
  pad es TX y cuál RX.
