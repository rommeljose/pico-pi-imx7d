# Pico-Pi-i.MX7D: notas para Claude Code

Repositorio **público** de documentación y herramientas generales de la TechNexion
Pico-Pi-i.MX7D (NXP i.MX7 Dual: 2× Cortex-A7 con Linux + 1× Cortex-M4F con
FreeRTOS). Lo general de la placa; no está ligado a ninguna aplicación concreta.

## Reglas

- **Distinguir siempre tres niveles** al informar: *documentado*, *compiló*,
  *verificado funcionando* (ejecutado en la placa y observado). No colapsarlos.
- **Es público**: no añadir IP, MAC, nombres de máquina o de usuario reales,
  contraseñas ni claves. Las direcciones de los documentos son de ejemplo
  (`192.168.1.240` = IP de rescate, `192.168.1.1` = router).
- Los `docs/` son bitácoras fechadas: al corregir algo, añadir una entrada nueva
  o una nota con fecha; no reescribir la historia en silencio.

## Hechos que condicionan todo

- **Placa del BSP: `examples/imx7d_pico_m4`.** `sdb` es la placa de referencia
  de NXP: enlaza, pero falla en silencio (UART2 frente a UART6, RPMsg para 1 GB).
- **U-Boot ya carga el M4**: `m4image` en `uEnv.txt` → `fatload` a TCM
  `0x7F8000` → `bootaux`, antes de Linux. La TCM es `0x1FFF8000` en la vista del
  M4. OCRAM `0x00910000`, DDR `0x9FF00000`.
- ⚠️ **En la FAT solo existe el DTB `-m4`**. Si `m4image` no carga, U-Boot pide
  un DTB sin `-m4`, que no existe, y Linux no arranca. **Sustituir** el binario
  del M4, nunca borrarlo. `uEnv.txt` de fábrica va en CRLF; las líneas nuevas, en LF.
- **No hay remoteproc completo** en i.MX7: el M4 lo arranca U-Boot y no se
  recarga desde Linux; cambiar su firmware exige reiniciar.
- **GPT3 inutilizable desde el M4**: Linux apaga su reloj
  (`gpt3_root_clk enable_count=0`). Usar `vTaskDelay` (SysTick).
- **Observar el M4 sin consola serie**: GPIO2_IO06 = sysfs **38**; leer
  `direction` (`out` = el M4 corre). **Nunca escribir en `direction`.**
- **SPI**: solo **ECSPI3** llega a J8/JP1 (`/dev/spidev2.0` en Linux). ECSPI1/2
  los ocupa el combo WiFi/BT; ECSPI4 no tiene pads.
- **Consola del M4**: UART6, 115200 8N1, J8 pin 8 = TX, pin 10 = RX, pin 9 = GND.
  La de Linux es UART5 (`ttymxc4`), por el USB de depuración.
- **RPMsg**: vrings en `0x9FFF0000`/`0x9FFF8000`, fuera de la RAM de Linux
  (`80000000-9fefffff`). `modprobe imx_rpmsg_tty` → `/dev/ttyRPMSG0`.
- **Kernel de fábrica** `5.10.72-g7966a667bd89-dirty`, `MODVERSIONS=y`. Los
  módulos compilados con `scripts/build-kernel.sh` (config `kernel/config-vivo`,
  mismo `LOCALVERSION`) tienen los mismos CRC: cargan sin cambiar el `zImage`.
- **El kernel no tiene `NF_TABLES` ni la tabla `filter`**, pero sí `nat`: el NAT
  del AP va con `iptables-legacy` y el dispatcher `tarjeta/50-ap-nat`.
- **RTC sin pila.** La hora depende de NTP al arrancar.

## Compilar

    source scripts/env-m4.sh                  # ARMGCC_DIR, PATH, BSP_DIR, BOARD_DIR
    ./scripts/build-m4.sh <app> [release|debug] [clean]
    ./scripts/build-kernel.sh prepare|build|package

- **CMake 3.x obligatorio**: CMake 4 aborta en `cmake_minimum_required(VERSION 2.6)`.
- **GCC del M4**: 10.3-2021.10 por prudencia; 13.2 también compila (`-mapcs` no
  es un problema; el mito era falso).
- **Kernel**: GCC 6.5.0 de kernel.org (`arm-linux-gnueabi`, nolibc).
  *gnueabi* frente a *gnueabihf* no importa para el kernel.
- El BSP se clona en `./freertos-tn` (ignorado por git): ver `bsp/LEEME.md`.

## Operar la placa en remoto (sin consola serie)

1. Salvavidas primero: IP fija de rescate y clave SSH, verificadas antes.
2. Cambios de red con reversión automática armada (`systemd-run --on-active=420`),
   cancelada solo tras comprobar el acceso.
3. Operaciones largas con `systemd-run`, desacopladas de la sesión SSH.
4. Reinicios verificados por `/proc/sys/kernel/random/boot_id`, no por ping.
5. Una sola herramienta gestionando cada interfaz de red (NetworkManager). Nunca dos.

## Contenido

    docs/        Tarjeta_Inventario, M4_Despliegue_y_Verificacion, RPMsg_Verificacion,
                 Kernel_Recompilacion, WiFi_Diagnostico, Ruta_Actualizacion_SO,
                 Red_Migracion_NetworkManager
    blog/        entradas HTML para Blogger
    scripts/     env-m4.sh, build-m4.sh, build-kernel.sh
    firmware-m4/ binarios del M4 con SHA256SUMS y nivel (LEEME.md)
    kernel/      config-vivo, config-wifi, Module.symvers, DTB vivo, calibración WiFi
    tarjeta/     configuración instalada en la placa (LEEME.md)
    bsp/         cómo obtener freertos-tn + el parche
    LICENSE, LICENSE-docs, LICENCIAS-TERCEROS.md   MIT, CC BY 4.0, terceros
