# BSP de FreeRTOS para el Cortex-M4

El BSP **no se copia** en este repositorio (92 MB). Se clona de TechNexion y se
le aplica un único parche:

    git clone -b freertos_1.0.1_imx7d https://github.com/TechNexion/freertos-tn.git
    cd freertos-tn
    git checkout 3f714904420b9eca36d43ee3b2a3ebb629d02e93      # 2021-11-11
    git apply ../bsp/freertos-tn-cambios-locales.patch

Clónalo **dentro de la raíz de este repo** (`./freertos-tn`), que es donde lo
busca `scripts/env-m4.sh`. Si lo pones en otro sitio, exporta `BSP_DIR` antes de
cargar el entorno.

Comprobado el 2026-11-12: la copia con la que se compiló y verificó todo es
**idéntica** a ese commit salvo el fichero que toca el parche, y el parche aplica
limpio sobre un clon nuevo.

## Qué cambia el parche

Un solo fichero: `examples/imx7d_pico_m4/demo_apps/blinking_imx_demo/main.c`.

Sustituye `Hw_Timer_Delay()` (temporizador **GPT3**) por `vTaskDelay()` (SysTick
del propio M4). Con el original, el LED parpadea con intervalos erráticos de 0,5
a 36 s porque **Linux mantiene apagado el reloj del GPT3**. Con el parche, la
precisión medida desde Linux es de ±1 ms. Detalle en
`docs/M4_Despliegue_y_Verificacion.md`.

## Placa

Usa **`examples/imx7d_pico_m4`**. Las otras tres (`edm1`, `sdb`, `val`) son
otras placas: enlazan sin quejarse, pero dejan mal el pin mux, los relojes y la
memoria de RPMsg.
