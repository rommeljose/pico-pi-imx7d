# Licencias de terceros

Lo propio de este repositorio va bajo **MIT** (código y scripts, `LICENSE`) y
**CC BY 4.0** (documentación, `LICENSE-docs`). Algunas piezas derivan de
software ajeno y conservan **su** licencia:

## `firmware-m4/` (binarios del Cortex-M4)

Compilados desde el BSP `TechNexion/freertos-tn`, rama `freertos_1.0.1_imx7d`,
commit `3f714904420b9eca36d43ee3b2a3ebb629d02e93`, con el parche de
`bsp/freertos-tn-cambios-locales.patch`. Contienen:

| Componente | Licencia | Titulares |
|---|---|---|
| Drivers, plataforma y ejemplos del BSP | BSD-3-Clause | Freescale Semiconductor, Inc. / NXP |
| CMSIS | BSD-3-Clause | ARM Limited |
| OpenAMP / RPMsg (solo los `rpmsg_*`) | BSD-3-Clause | Mentor Graphics Corporation, Freescale Semiconductor, Inc. |
| **FreeRTOS V8.0.0** (los que usan FreeRTOS) | GPLv2 modificada con la *FreeRTOS exception* | Real Time Engineers Ltd. |

**Aviso de FreeRTOS** (lo exige su excepción): estos binarios usan
**FreeRTOS V8.0.0**, sin modificar. Su código fuente completo está en el commit
del BSP citado arriba, en `rtos/FreeRTOS/`, y lo proporcionaremos a quien lo
pida abriendo un *issue* en este repositorio.

**Aviso BSD-3-Clause** (lo exige la redistribución binaria):

    Copyright (c) 2015, Freescale Semiconductor, Inc.
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:

    o Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.

    o Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.

    o Neither the name of Freescale Semiconductor, Inc. nor the names of its
      contributors may be used to endorse or promote products derived from this
      software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
    LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

Los avisos de ARM (CMSIS) y Mentor Graphics (OpenAMP) son del mismo tipo
BSD-3-Clause y están en la cabecera de sus fuentes, en el mismo commit del BSP.

## `bsp/freertos-tn-cambios-locales.patch`

Modifica un fichero de NXP (`blinking_imx_demo/main.c`): queda bajo
**BSD-3-Clause**, como el original.

## `kernel/`

`config-vivo`, `config-wifi`, `Module.symvers` y `imx7d-pico-pi-qca-m4.dtb`
derivan del kernel Linux de TechNexion (`TechNexion/linux-tn-imx`, rama
`tn-imx_5.10.72_2.2.0-stable`), bajo **GPL-2.0**. Las fuentes están en ese
repositorio.

`brcmfmac4339-sdio.txt` es el fichero de calibración del fabricante del módulo
WiFi, extraído de la placa. Se incluye solo como referencia técnica; sus
derechos son de su titular.
