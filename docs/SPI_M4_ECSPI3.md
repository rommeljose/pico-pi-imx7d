# SPI en el M4 de la Pico-Pi-i.MX7D: por qué no funcionó en 2023 y cómo funciona ahora

*Documento fuente para una entrada del blog. 2026-11-12.*

Este texto distingue tres niveles de certeza, y conviene respetarlos al
publicarlo:

- **verificado**: se ejecutó en la tarjeta y se observó;
- **comprobado en el código**: se leyó en las fuentes del BSP o del kernel, sin
  ejecutarlo;
- **hipótesis**: lo más probable, pero no demostrado.

---

## 1. En una frase

El Cortex-M4 del i.MX7D **ya puede usar el SPI que sale al conector J8
(ECSPI3)**, siempre que Linux lo **suelte** antes. Soltarlo es una orden de una
línea, sin tocar el kernel, el device tree ni U-Boot, y es reversible. Verificado
el 2026-11-12 con el lazo interno del periférico: 256 de 256 bytes correctos a
1 MHz.

---

## 2. El punto de partida: un SoC, dos sistemas, un solo SPI útil

El i.MX7D tiene dos Cortex-A7 (aquí con Linux) y un Cortex-M4 (aquí con
FreeRTOS). **Los dos núcleos ven los mismos periféricos**, en las mismas
direcciones: el SPI no "pertenece" a ninguno por diseño. Que lo use uno u otro
es una cuestión de **acuerdo**, y en ese acuerdo intervienen cuatro piezas del
SoC.

El chip tiene cuatro controladores SPI (ECSPI1 a ECSPI4), pero en la Pico-Pi
**solo ECSPI3 llega a un conector**:

| Controlador | Dónde van sus patillas en la Pico-Pi |
|---|---|
| ECSPI1 | al módulo WiFi/Bluetooth de la SOM (líneas de control) |
| ECSPI2 | a UART7, el enlace HCI del Bluetooth |
| **ECSPI3** | **a J8 y JP1**: MOSI pin 19, MISO 21, SCLK 23, **CS 26**, GND 20/25 (el CS en el 26, no en el 24 como decía el inventario: ver §9) |
| ECSPI4 | sin patillas propias en el SoC |

La serigrafía de la placa rotula esos pines como `CSPI2_…`, pero el periférico
es **ECSPI3**. ECSPI3 tampoco tiene pads con su nombre: se monta sobre los pads
llamados `I2C1_SCL`, `I2C1_SDA`, `I2C2_SCL` e `I2C2_SDA`. Son dos fuentes de
confusión antes de escribir una sola línea de código.

Y **ECSPI3 lo tiene Linux**: el device tree de fábrica lo declara activo, y el
driver `spi_imx` lo convierte en `/dev/spidev2.0`.

---

## 3. 2023: lo que se intentó

La entrada «SPI en el M4» (marzo de 2023) lleva el aviso *SUJETO A REVISIÓN; NO
SE HA PODIDO ACTIVAR EL HARDWARE*. Siguió el camino razonable:

- el BSP FreeRTOS 1.0.1 no trae ningún ejemplo de SPI para la Pico-Pi, así que
  se partió del ejemplo `ecspi_flash_demo` de la placa de evaluación **VAL** de
  NXP, que escribe y lee una flash M25P32;
- se trasladó a un proyecto propio en Arm Development Studio, enlazando
  `ecspi.c` y `uart_imx.c` del BSP;
- como memoria de prueba se usó una **93LC46B** (EEPROM Microwire de 3 hilos,
  organización de 16 bits).

Compiló, pero el hardware no respondió.

## 4. Por qué no funcionó: cinco obstáculos encadenados

Analizado en 2026 leyendo el BSP y el kernel, y comprobando en la tarjeta el
estado en que Linux deja ECSPI3. **El programa de 2023 no se ha vuelto a
ejecutar**, así que lo que sigue explica por qué no podía funcionar tal cual;
no es una reproducción del fallo.

### 4.1. El ejemplo de la VAL apunta a otro SPI — *comprobado en el código*

`examples/imx7d_val_m4/board.h` fija `BOARD_ECSPI_BASEADDR = ECSPI1`, y su
`configure_ecspi_pins()` solo sabe configurar pads de **ECSPI1 y ECSPI2**. En la
Pico-Pi esos pads van al módulo WiFi/BT (§2): aunque todo lo demás estuviera
bien, las señales no saldrían a J8. Además, el BSP de la Pico-Pi
(`examples/imx7d_pico_m4/pin_mux.c`) **no tiene ninguna función de pines para
ECSPI**: no hay de dónde copiarla.

### 4.2. El cálculo del reloj devuelve 0 para ECSPI3 — *comprobado en el código*

El ejemplo obtiene la frecuencia con `get_ecspi_clock_freq()`. En el
`clock_freq.c` de la Pico-Pi esa función solo contempla ECSPI1 y ECSPI2; para
ECSPI3 **devuelve 0**. Con un reloj de 0 Hz, `ECSPI_SetBaudRate()` entra en su
primer caso (`sourceClockInHz <= bitsPerSec`) y pone los divisores a cero: el
SPI saldría al reloj completo del periférico, 60 MHz, en vez de los cientos de
kHz pedidos.

### 4.3. Linux era el dueño del SPI — *verificado en la tarjeta*

Mientras `spi_imx` esté ligado a ECSPI3, Linux:

- **enciende y apaga el reloj raíz de ECSPI3 en cada transferencia**. En
  reposo, `clk_summary` muestra `ecspi3_root_clk` con `enable_count 0`. El bit
  que lo enciende (`CCM_TARGET_ROOT104`, bit 28) **es único y compartido** por
  los dos núcleos: si Linux lo apaga, el SPI del M4 se queda sin reloj;
- **retiene el chip select**, que en el device tree es un GPIO
  (`cs-gpios = <&gpio4 11 …>`, gpio 107, visible en `/sys/kernel/debug/gpio`
  como `spi2 CS0`).

Es el mismo patrón que ya rompió el temporizador GPT3 en este proyecto: un
periférico al que Linux le gestiona el reloj no es fiable para el M4.

### 4.4. El ejemplo cierra el periférico al otro núcleo — *comprobado en el código*

El `hardware_init.c` del ejemplo hace
`RDC_SetPdapAccess(RDC, …, 3 << (BOARD_DOMAIN_ID * 2), false, false)`: da acceso
**solo al dominio del M4**. Con ECSPI3 eso es peligroso: si Linux arranca y su
driver sondea el periférico, lee registros que el RDC le prohíbe. El ejemplo
además **cambia la fuente del reloj** a 24 MHz, lo que deja desfasado lo que
Linux cree tener.

### 4.5. La EEPROM elegida no es un SPI corriente — *hipótesis*

La 93LC46B es **Microwire**: un bit de arranque, códigos de operación de longitud
rara y, según su hoja de datos, chip select **activo en alto**, al revés que el
SS habitual. Se puede hablar con ella desde un SPI, pero exige ajustar polaridad
y longitud de ráfaga. Para una primera prueba añadía otra incógnita. No se ha
comprobado si fue un factor.

**Conclusión:** en 2023 el problema no era un error de programación. Eran cinco
obstáculos a la vez, y cualquiera de los tres primeros bastaba para que no
saliera nada por J8.

---

## 5. Cómo se comparte un periférico entre el A7 y el M4

No hay un interruptor de "este SPI es del M4". Hay **cuatro piezas** que deben
quedar de acuerdo, y conviene entender cada una:

| Pieza | Qué controla | ¿Compartida? | Qué se hizo |
|---|---|---|---|
| **El driver de Linux** (`spi_imx`) | Si Linux usa el periférico | — | Se **desliga** en caliente (§6) |
| **RDC** (Resource Domain Controller) | Qué dominio (A7 = 0, M4 = 1) puede acceder a cada periférico | Configurable | Acceso **para todos** (`0xFF`), nunca exclusivo |
| **CCM** (relojes) | Que el periférico tenga reloj | La fuente y el bit de encendido del *target root*: **una sola copia**. La puerta CCGR: **un bit por dominio** | El M4 enciende el *target root* y la puerta de **todos** los dominios; **no cambia la fuente** |
| **IOMUXC** (pads) | Qué señal sale por cada patilla | **Una sola copia**: gana el último que escribe | Para el lazo interno no hace falta tocarlo. Linux deja los pads ya en modo ECSPI3 |

La regla que se desprende: **un solo dueño a la vez**, y el traspaso lo hace
quien suelta (Linux, desligando su driver) antes de que tome el otro (el M4, por
orden expresa). Ninguno de los dos núcleos impone la exclusividad por hardware.
Si los dos escribieran a la vez en ECSPI3, se pisarían sin que nada lo impidiera.

### Por qué el RDC no se pone en exclusiva para el M4

Sería lo "limpio", y es lo que hace el ejemplo de NXP. Pero en esta tarjeta el
M4 arranca **antes** que Linux, porque lo carga U-Boot. Si el M4 cerrara ECSPI3
a su dominio, el driver de Linux, que sigue en el device tree, chocaría con el
RDC al sondearlo durante el arranque. Sin consola serie, un arranque roto es una
tarjeta inaccesible. Con el RDC compartido, Linux arranca exactamente como
siempre, y el traspaso se hace después, en caliente.

### Por qué el M4 no cambia la fuente del reloj

Linux deja ECSPI3 en `pll_sys_main_240m_clk` ÷ 4 = **60 MHz**. Si el M4 cambiara
la fuente, el árbol de relojes de Linux quedaría desfasado: si luego se vuelve a
ligar `spi_imx`, calcularía mal sus velocidades. El M4 **lee** la fuente y los
divisores y calcula la frecuencia.

---

## 6. Cómo se hace: tomar y soltar el SPI

### 6.1. Linux suelta ECSPI3

En la tarjeta, como root:

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/unbind

`30840000` es la dirección de ECSPI3. Efecto inmediato:

- `/dev/spidev2.0` desaparece;
- el GPIO del chip select queda libre (`spi2 CS0` ya no figura en
  `/sys/kernel/debug/gpio`);
- **Linux deja de tocar los relojes de ECSPI3**.

`spi_imx` está compilado dentro del kernel, no es un módulo: no se puede
descargar con `rmmod`, pero sí desligar del dispositivo. **No es persistente**:
tras reiniciar, Linux vuelve a ser el dueño.

### 6.2. El M4 toma ECSPI3

El M4 no toca ECSPI3 al arrancar: espera una orden por RPMsg (`/dev/ttyRPMSG0`).
La orden de prueba es `spi lazo`:

    echo "spi lazo" > /dev/ttyRPMSG0
    # respuesta:
    OK spi lazo bytes=256 bien=256 mux=1 reloj_hz=60000000 baud=1000000 us=3328

Lo que hace el M4 al recibirla (`instrumento.c`, función `ecspi3_toma()`):

```c
RDC_SetPdapAccess(RDC, rdcPdapEcspi3, 0xFF, false, false);  /* compartido     */
CCM_EnableRoot(CCM, ccmRootEcspi3);                         /* target root on */
CCM_ControlGate(CCM, ccmCcgrGateEcspi3, ccmClockNeededAll); /* puerta: todos  */
spi_hz = ecspi3_reloj();          /* lee mux y divisores; no los cambia      */
ECSPI_Init(ECSPI3, &c);           /* maestro, modo SPI 1, 8 bits, canal 0    */
spi_baud = ECSPI_SetBaudRate(ECSPI3, spi_hz, 1000000);
```

`ecspi3_reloj()` traduce la fuente del reloj a una frecuencia. La tabla de
fuentes del BSP coincide en orden con la de Linux (`ecspi3_sel[]` en
`drivers/clk/imx/clk-imx7d.c`). La primera versión solo contemplaba el
oscilador de 24 MHz y PFD4, y respondió `ERR spi reloj desconocido`: así se
descubrió que Linux usa la salida de 240 MHz de la PLL del sistema.

Para la prueba, `spi_lazo()` activa el **lazo interno** del ECSPI
(`TESTREG.LBC`): lo que sale por el registro de transmisión vuelve por el de
recepción **dentro del periférico, sin pasar por las patillas**. Envía 256
bytes y compara. Prueba que el M4 tiene reloj, permisos y control de los
registros, sin conectar nada y sin riesgo para el hardware. Los 3328 µs medidos
con el contador de ciclos (DWT) son 13 µs por byte: 8 µs de bits a 1 MHz más el
sondeo del FIFO. El reloj SPI es el pedido.

### 6.3. El M4 suelta ECSPI3

    echo "spi suelta" > /dev/ttyRPMSG0      # responde: OK spi suelta

Pone `CONREG = 0`: el módulo queda apagado. Los relojes se dejan como estén.

### 6.4. Linux lo recupera

    echo 30840000.spi | sudo tee /sys/bus/platform/drivers/spi_imx/bind

`/dev/spidev2.0` reaparece. En la prueba del 2026-11-12, `dmesg` no registró
**ninguna** línea en todo el ciclo de desligar, probar, soltar y religar.

**El orden importa**: el M4 suelta antes de que Linux religue. Si no, los dos
manejarían el mismo periférico a la vez.

---

## 7. Qué se modificó, y qué no

| Dónde | Cambio |
|---|---|
| Firmware del M4 (`freertos-tn/…/demo_apps/instrumento/instrumento.c`, v0.3) | Funciones `ecspi3_reloj()`, `ecspi3_toma()`, `ecspi3_byte()`, `spi_lazo()`, y las órdenes `spi lazo` y `spi suelta` |
| `…/instrumento/armgcc/CMakeLists.txt` | Añadido `platform/drivers/src/ecspi.c` (y su cabecera) |
| Linux | **Nada permanente.** `unbind`/`bind` por sysfs, en caliente |
| Kernel, device tree, U-Boot | **Nada** |
| BSP compartido (`platform/`) | **Nada**: `get_ecspi_clock_freq()` sigue sin conocer ECSPI3; el firmware no la usa |

El firmware está en la partición de arranque como `instrumento.bin`. Las
versiones anteriores siguen ahí, como `instrumento-e1.bin` y
`instrumento-e0.bin`.

---

## 8. Un tropiezo que conviene contar

Para averiguar qué fuente de reloj usaba ECSPI3 se intentó leer el registro del
CCM **desde Linux**, con `/dev/mem`. La dirección estaba mal calculada:
`0x30388340` en lugar de `0x3038B400`, que es
`TARGET_ROOT104 = 0x30380000 + 0x8000 + 104 × 0x80`. **La tarjeta se colgó por
completo**: sin red, sin ratón, sin consola UART. Hubo que resetearla a mano, y
volvió sin daños.

En el i.MX7, una lectura a una zona reservada o sin reloj del bus de periféricos
puede bloquear el bus entero, y con él a todo el sistema. La lección: **los
registros del SoC, que los lea el M4 y los mande por RPMsg**. Si falla, se
cuelga solo el M4. En el firmware, la respuesta `mux=1` de `spi lazo` es
exactamente eso.

---

## 9. Lo que falta

| Paso | Estado |
|---|---|
| El M4 toma ECSPI3, lazo interno | ✅ verificado (2026-11-12) |
| El ADC, un **ADS1220** (módulo CJMCU-1220; sustituye al AD7705 previsto), probado **desde Linux** con `/dev/spidev2.0` | ✅ verificado (2026-11-13): registros, entradas en corto 1,5 µV, AVDD 3,334 V, 24,7 °C |
| El ADS1220 **desde el M4** (v0.4, `adc prueba`): CS como GPIO4_IO11 fijo en bajo, dato listo por **DRDYM** sobre MISO | ✅ verificado (2026-11-13): 20 SPS, periodo 50,0–51,0 ms, 23,7 °C; Linux recupera el bus después |
| Muestras reales del ADS1220 en la adquisición del M4 (paso 4b, v0.5, `fuente adc`) | ✅ verificado (2026-11-13): 20–600 SPS sin pérdidas; ruido en corto de 0,19 µV rms a ×128 y 90 SPS |
| Un geófono real (SM-6) conectado directo, con interfaz pasiva | ✅ verificado (2026-11-13): golpes en el visor; reposo ~3,3 µm/s. Esquema en `docs/img/geofono-ads1220-directo.png` |
| Soltar ECSPI3 automáticamente al arrancar (un servicio) | pendiente |
| Quitar ECSPI3 del device tree de Linux | solo cuando haya consola serie: un error ahí deja la tarjeta sin arrancar |

El ADS1220 se alimenta a **3,3 V** (pin 1 de J8), el nivel de los pads del
i.MX7, así que la conexión es directa. Habla SPI modo 1, el que ya usa la
prueba.

### El chip select no estaba donde decía el inventario

La primera prueba del ADS1220 leyó **todo `FF`**: el chip no contestaba. La
alimentación (3,3 V) y el cableado estaban bien, y en Linux los pads tenían el
modo correcto. La pista vino de medir. Con el driver desligado, se puso el GPIO
del chip select (gpio 107) en bajo, y **J8-24 seguía a 3,3 V**. Haciéndolo
parpadear a 1 Hz, el multímetro lo encontró en **J8-26** (~1,56 V de media), el
pin que la serigrafía rotula `CSPI2_CS1`. Movido el cable al 26, el ADS1220
contestó a la primera.

**Cableado verificado:**

| ADS1220 (CJMCU-1220) | J8 |
|---|---|
| MOSI (DIN) | 19 |
| MISO (DOUT/DRDY) | 21 |
| SCLK | 23 |
| **CS** | **26** |
| DVDD y AVDD | 1 (3,3 V) |
| DGND y AGND, unidas en el módulo | 20 o 25 |
| CLK | a DGND, en el módulo (oscilador interno) |
| DRDY, REFP0/REFN0, AIN0–3 | sin conectar para la prueba |

La lección para el blog: **con el driver desligado, cualquier pin del SPI se
puede convertir en GPIO y hacerlo parpadear**. Un multímetro basta para saber
por dónde sale de verdad cada señal.

### Sin pin DRDY: el aviso viaja por MISO

El plan era llevar el DRDY del módulo a un GPIO libre de J8. Fallaron los dos
probados:

- **J8-36** (gpio 32): sacaba bien el parpadeo hacia fuera. Con el DRDY unido,
  el nodo se quedaba en **3,3 V** y Linux leía 1 fijo.
- **J8-11** (el CTS de UART6): igual.

Algo de la placa base empuja esos pines hacia fuera; la hipótesis es un buffer
de sentido fijo. Los pads de ECSPI3, que son pads I2C, sí son bidireccionales:
MISO entra sin problema por J8-21.

La salida está en el propio ADS1220, que tiene un modo **DRDYM**: con el CS
bajo, **DOUT/DRDY baja cuando hay dato nuevo**. El M4 deja el CS fijo en bajo,
y cada milisegundo:

1. conmuta el pad de MISO (`I2C1_SCL`) a GPIO (`GPIO4_IO08`, ALT5);
2. lee su nivel en `PSR`;
3. lo devuelve a `ECSPI3_MISO` (ALT3).

En cada flanco de bajada lee el dato. **No hace falta ningún cable más.**

Al soltar el bus, el M4 deja todo como lo espera Linux: el ADS1220 en reset, el
CS alto y el pad en ECSPI3.

Sobre GPIO4: lo usa también Linux, para reguladores, el `wlreg_on` y el
`shutdown`. Por eso el M4 solo toca sus bits y lee `PSR`. Nunca toca los
registros de interrupción, que son del driver de Linux.

---

## Referencias

- Bitácora del proyecto: `docs/M4_Instrumento_Bitacora.md` (etapa 2, pasos 1 a 4b).
- Pines y buses de la tarjeta: `docs/Tarjeta_Inventario.md` §6.
- Entrada de 2023: <https://compilando-pico-pi-imx7.blogspot.com> → «SPI en el M4».
- Kernel: `drivers/spi/spi-imx.c`, `drivers/clk/imx/clk-imx7d.c` (`ecspi3_sel[]`).
- BSP: `platform/drivers/src/ecspi.c`, `examples/imx7d_val_m4/demo_apps/ecspi_flash_demo/`.
