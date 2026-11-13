/*
 * Instrumento sintético — etapa 0 del proyecto «M4 instrumento, Linux analista».
 *
 * El Cortex-M4 hace el trabajo continuo, sin depender de Linux:
 *   - genera una señal sintética a fs muestras/s (ruido + seno + «sismos»
 *     con fase P y fase S);
 *   - la procesa: quita la media y aplica un detector STA/LTA;
 *   - enciende el USER LED (GPIO2_IO06) mientras dura un evento;
 *   - mide su propia carga y el jitter de su periodo de muestreo.
 *
 * Linux (A7) recibe por RPMsg (/dev/ttyRPMSG0) bloques de muestras y eventos, y
 * le envía órdenes. Protocolo de texto, una línea por mensaje (ver bitácora
 * docs/M4_Instrumento_Bitacora.md):
 *
 *   M4 -> Linux   H <nombre> <versión> fs=<fs>
 *                 D <muestra> <fs> <v1> <v2> ...          bloque de muestras
 *                 E <muestra> <ratio×100>                 inicio de evento
 *                 F <muestra> <duración en muestras> <pico>  fin de evento
 *                 S clave=valor ...                       estado
 *                 OK <orden> | ERR <orden>
 *   Linux -> M4   hola | estado | inicia | pausa | fs <Hz> | ruido <cuentas>
 *                 seno <cuentas> <mHz> | amp <cuentas> | sismo [cuentas]
 *                 auto 0|1 | umbral <on×10> <off×10>
 *
 * Basado en str_echo_freertos (BSP FreeRTOS 1.0.1 de NXP/TechNexion, BSD-3).
 * Lo nuevo: Copyright (c) 2026 rommeljose y colaboradores, licencia MIT.
 */

#include <stdint.h>
#include <string.h>
#include <math.h>

#ifdef PRUEBA_HOST          /* prueba_host.c: generador y detector en el PC */
#include "prueba_host.h"
#else
#include "rpmsg/rpmsg_rtos.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "board.h"
#include "mu_imx.h"
#include "gpio_imx.h"
#include "gpio_pins.h"
#include "debug_console_imx.h"
#endif

#define NOMBRE              "instrumento-sintetico"
#define VERSION             "0.1"

#define APP_MU_IRQ_PRIORITY 3
#define PILA_ADQ            512     /* palabras */
#define PILA_COM            512
#define PRIO_ADQ            (tskIDLE_PRIORITY + 3)
#define PRIO_COM            (tskIDLE_PRIORITY + 1)

#define BLOQUE_MAX          25      /* muestras por mensaje D */
#define COLA_LEN            16      /* mensajes M4 -> Linux en espera */

#define PI2                 6.28318531f

/* pdMS_TO_TICKS no existe en FreeRTOS V8.0.0 */
#ifndef pdMS_TO_TICKS
#define pdMS_TO_TICKS(ms)   ((TickType_t)((ms) / portTICK_PERIOD_MS))
#endif

/* ------------------------------------------------------------------------- */
/* Parámetros: los escribe la tarea de comunicación, los lee la de adquisición.
 * Son palabras alineadas: la lectura y la escritura son atómicas en el M4.   */

static volatile struct {
    int32_t fs;             /* muestras/s, divisor de 1000 (tick de 1 ms)  */
    int32_t ruido;          /* desviación típica del ruido, cuentas        */
    int32_t seno_amp;       /* amplitud del seno, cuentas                  */
    int32_t seno_mhz;       /* frecuencia del seno, milihercios            */
    int32_t sismo_amp;      /* amplitud de la fase S de un sismo, cuentas  */
    int32_t automatico;     /* 1: sismos espontáneos cada 40–100 s         */
    int32_t umbral_on;      /* STA/LTA ×10 para disparar                   */
    int32_t umbral_off;     /* STA/LTA ×10 para terminar                   */
    int32_t transmitir;     /* 1: enviar bloques y eventos a Linux         */
    int32_t sismo_pedido;   /* >0: inyectar un sismo ya, con esta amplitud */
} par = {
    .fs = 100, .ruido = 20, .seno_amp = 0, .seno_mhz = 200,
    .sismo_amp = 3000, .automatico = 1,
    .umbral_on = 30, .umbral_off = 15,
    .transmitir = 0, .sismo_pedido = 0,
};

/* Estadísticas: las escribe la adquisición, las lee la comunicación. */
static volatile uint32_t est_muestras, est_eventos, est_perdidos, est_sismos;
static volatile uint32_t est_carga_pm;      /* carga de la adquisición, ‰    */
static volatile uint32_t est_peor_us;       /* peor tiempo de una muestra    */
static volatile uint32_t est_jitter_us;     /* peor desvío del periodo, 1 s  */
static volatile uint32_t est_evento_activo;

/* ------------------------------------------------------------------------- */
/* Mensajes de la adquisición a la comunicación.                              */

enum { M_BLOQUE = 1, M_EVENTO_INI, M_EVENTO_FIN };

typedef struct {
    uint8_t  tipo;
    uint8_t  n;
    uint16_t fs;
    uint32_t muestra;               /* índice de la primera muestra        */
    int32_t  v[BLOQUE_MAX];         /* E: v0=ratio×100; F: v0=dur, v1=pico */
} msg_t;

static QueueHandle_t cola;

#ifndef PRUEBA_HOST
/* ------------------------------------------------------------------------- */
/* LED                                                                        */

static void led(int encendido)
{
    GPIO_WritePinOutput(BOARD_GPIO_LED_CONFIG->base, BOARD_GPIO_LED_CONFIG->pin,
                        encendido ? gpioPinSet : gpioPinClear);
}

static void led_init(void)
{
    gpio_init_config_t cfg = {
        .pin           = BOARD_GPIO_LED_CONFIG->pin,
        .direction     = gpioDigitalOutput,
        .interruptMode = gpioNoIntmode,
    };
    GPIO_Init(BOARD_GPIO_LED_CONFIG->base, &cfg);
    led(0);
}

/* Fallo irrecuperable: el LED parpadea rápido (~10 Hz) para siempre. Linux lo
 * ve leyendo /sys/class/gpio/gpio38/value varias veces.                     */
static void __attribute__((noreturn)) fallo(const char *por_que)
{
    volatile uint32_t i;
    int s = 0;
    PRINTF("\r\nFALLO: %s\r\n", por_que);
    taskDISABLE_INTERRUPTS();
    for (;;) {
        led(s ^= 1);
        for (i = 0; i < 2400000; i++) { }
    }
}

void vApplicationStackOverflowHook(TaskHandle_t xTask, char *pcTaskName)
{
    (void)xTask;
    (void)pcTaskName;
    fallo("desbordamiento de pila");
}

void vApplicationMallocFailedHook(void)
{
    fallo("sin memoria");
}

/* El BSP compila con -D__NDEBUG (no NDEBUG): los assert() de los drivers siguen
 * activos. El __assert_func de newlib arrastra fprintf, vfprintf y malloc
 * (~4 KB de los 32 KB de TCM). Este lo sustituye y además se ve en el LED. */
void __assert_func(const char *fichero, int linea, const char *func, const char *expr)
{
    (void)fichero; (void)linea; (void)func; (void)expr;
    fallo("assert");
}

/* ------------------------------------------------------------------------- */
/* Contador de ciclos del núcleo (DWT): carga y jitter, sin temporizadores    */
/* periféricos (Linux apaga el reloj del GPT3).                               */

static void ciclos_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

#define CICLOS_POR_US   (configCPU_CLOCK_HZ / 1000000u)
#endif /* !PRUEBA_HOST */

/* ------------------------------------------------------------------------- */
/* Generador de señal                                                         */

static uint32_t semilla = 2463534242u;

static uint32_t aleatorio(void)                 /* xorshift32 */
{
    semilla ^= semilla << 13;
    semilla ^= semilla >> 17;
    semilla ^= semilla << 5;
    return semilla;
}

static float uniforme(void)                     /* [0, 1) */
{
    return (aleatorio() >> 8) * (1.0f / 16777216.0f);
}

static float gauss(void)                        /* media 0, desviación 1 (aprox.) */
{
    return (uniforme() + uniforme() + uniforme() + uniforme() - 2.0f) * 1.7320508f;
}

/* Envolvente de una fase: sube con constante r y decae con constante d (s). */
static float envolvente(float t, float r, float d)
{
    if (t <= 0.0f) return 0.0f;
    return (1.0f - expf(-t / r)) * expf(-t / d);
}

/* Seno propio: el sinf de libm trae la reducción de argumento de precisión
 * completa (~2,4 KB). Error < 1e-4, de sobra para una señal sintética. */
static float seno(float x)
{
    float x2;
    x -= PI2 * (float)(int32_t)(x * (1.0f / PI2));      /* (-2π, 2π) */
    if (x >  3.14159265f) x -= PI2;
    if (x < -3.14159265f) x += PI2;                     /* [-π, π]  */
    if (x >  1.57079633f) x =  3.14159265f - x;
    if (x < -1.57079633f) x = -3.14159265f - x;         /* [-π/2, π/2] */
    x2 = x * x;
    return x * (1.0f - x2 / 6.0f * (1.0f - x2 / 20.0f * (1.0f - x2 / 42.0f)));
}

static float limita_f(float f, int32_t fs)      /* evita el aliasing */
{
    float max = 0.4f * fs;
    return f < max ? f : max;
}

static struct {
    int   activo;
    float t;            /* s desde la llegada de la P */
    float ts;           /* retraso S–P, s: «distancia» del sismo */
    float a;            /* amplitud de la S */
    float fase;
} sismo;

static uint32_t proximo_auto;
static float    fase_seno;      /* acumulador de fase del seno, [0, 2π) */   /* muestras hasta el siguiente sismo espontáneo */

static void sismo_inicia(float a)
{
    sismo.activo = 1;
    sismo.t      = 0.0f;
    sismo.ts     = 1.5f + 3.5f * uniforme();
    sismo.a      = a;
    sismo.fase   = PI2 * uniforme();
    est_sismos++;
}

static float genera(int32_t fs)
{
    float dt = 1.0f / fs;
    float x  = par.ruido * gauss();

    fase_seno += PI2 * (par.seno_mhz * 0.001f) * dt;
    if (fase_seno >= PI2) fase_seno -= PI2;
    if (par.seno_amp)
        x += par.seno_amp * seno(fase_seno);

    if (par.sismo_pedido > 0) {
        sismo_inicia((float)par.sismo_pedido);
        par.sismo_pedido = 0;
    } else if (par.automatico && !sismo.activo) {
        if (proximo_auto == 0) {
            sismo_inicia(par.sismo_amp * (0.3f + 0.7f * uniforme()));
            proximo_auto = (uint32_t)((40.0f + 60.0f * uniforme()) * fs);
        } else {
            proximo_auto--;
        }
    }

    if (sismo.activo) {
        float ts = sismo.t - sismo.ts;
        float fp = limita_f(7.0f, fs), fsw = limita_f(2.5f, fs);
        x += 0.35f * sismo.a * envolvente(sismo.t, 0.15f, 1.2f) * seno(PI2 * fp * sismo.t);
        x += sismo.a * envolvente(ts, 0.3f, 3.0f) *
             (0.7f * seno(PI2 * fsw * sismo.t + sismo.fase) + 0.3f * gauss());
        sismo.t += dt;
        if (sismo.t > sismo.ts + 20.0f)
            sismo.activo = 0;
    }
    return x;
}

/* ------------------------------------------------------------------------- */
/* Detector STA/LTA recursivo                                                 */

static struct {
    float    a_sta, a_lta, a_med;
    float    sta, lta, media;
    uint32_t desde;     /* muestras desde el último reinicio */
    int      activo;
    uint32_t ini;
    uint32_t bajo;      /* muestras seguidas por debajo de umbral_off */
    float    pico;
} det;

#define RETENCION_S 3   /* s bajo umbral_off antes de cerrar: P y S, un evento */

static void detector_reinicia(int32_t fs)
{
    det.a_sta  = 1.0f / (0.5f * fs);    /* ventana corta: 0,5 s */
    det.a_lta  = 1.0f / (10.0f * fs);   /* ventana larga: 10 s  */
    det.a_med  = 1.0f / (30.0f * fs);   /* media: 30 s          */
    det.sta    = det.lta = 0.0f;
    det.desde  = 0;
    if (det.activo) led(0);
    det.activo = 0;
    est_evento_activo = 0;
}

static void detecta(float x, uint32_t n, int32_t fs)
{
    float a, y, ratio;
    msg_t m;

    /* Al arrancar, la media y la LTA convergen como un promedio simple */
    a = 1.0f / (det.desde + 1);
    det.media += (x - det.media) * (a > det.a_med ? a : det.a_med);
    y = fabsf(x - det.media);
    det.sta += (y - det.sta) * (a > det.a_sta ? a : det.a_sta);
    if (!det.activo)                    /* la LTA se congela durante el evento */
        det.lta += (y - det.lta) * (a > det.a_lta ? a : det.a_lta);
    det.desde++;

    if (det.desde < (uint32_t)(10 * fs))  /* calentamiento: una ventana larga */
        return;

    ratio = det.sta / (det.lta + 1e-3f);

    if (!det.activo) {
        if (ratio * 10.0f >= par.umbral_on) {
            det.activo = 1;
            det.ini    = n;
            det.pico   = y;
            det.bajo   = 0;
            est_eventos++;
            est_evento_activo = 1;
            led(1);
            if (par.transmitir) {
                m.tipo = M_EVENTO_INI; m.n = 1; m.fs = fs; m.muestra = n;
                m.v[0] = (int32_t)(ratio * 100.0f);
                if (xQueueSend(cola, &m, 0) != pdPASS) est_perdidos++;
            }
        }
    } else {
        if (y > det.pico) det.pico = y;
        det.bajo = ratio * 10.0f < par.umbral_off ? det.bajo + 1 : 0;
        if (det.bajo >= (uint32_t)(RETENCION_S * fs) || n - det.ini > (uint32_t)(120 * fs)) {
            det.activo = 0;
            est_evento_activo = 0;
            led(0);
            if (par.transmitir) {
                m.tipo = M_EVENTO_FIN; m.n = 2; m.fs = fs; m.muestra = n;
                m.v[0] = (int32_t)(n - det.ini);
                m.v[1] = (int32_t)det.pico;
                if (xQueueSend(cola, &m, 0) != pdPASS) est_perdidos++;
            }
        }
    }
}

#ifndef PRUEBA_HOST
/* ------------------------------------------------------------------------- */
/* Tarea de adquisición: el trabajo continuo. Nunca espera a Linux.           */

static int32_t muestras_por_bloque(int32_t fs)
{
    int32_t n = fs / 10;                /* ~10 mensajes por segundo */
    if (n < 1) n = 1;
    if (n > BLOQUE_MAX) n = BLOQUE_MAX;
    return n;
}

static void TareaAdq(void *pv)
{
    TickType_t prox;
    int32_t    fs = 0, periodo = 1, nb = 1;
    uint32_t   n = 0, c_ant = 0, c0, c1, dc;
    uint32_t   acc = 0, peor = 0, jit = 0, seg = 0;
    msg_t      b;
    float      x;
    (void)pv;

    b.n = 0;
    prox = xTaskGetTickCount();

    for (;;) {
        if (par.fs != fs) {             /* arranque o cambio de fs */
            fs      = par.fs;
            periodo = 1000 / fs;
            nb      = muestras_por_bloque(fs);
            detector_reinicia(fs);
            proximo_auto = (uint32_t)(15 * fs);  /* tras el calentamiento */
            b.n     = 0;
            prox    = xTaskGetTickCount();
            c_ant   = 0;
        }

        vTaskDelayUntil(&prox, periodo);
        c0 = DWT->CYCCNT;

        /* Jitter: desvío entre despertares consecutivos y el periodo nominal */
        if (c_ant) {
            int32_t d = (int32_t)(c0 - c_ant) - (int32_t)(periodo * 1000u * CICLOS_POR_US);
            if (d < 0) d = -d;
            if ((uint32_t)d > jit) jit = (uint32_t)d;
        }
        c_ant = c0;

        x = genera(fs);
        detecta(x, n, fs);

        if (par.transmitir) {
            if (b.n == 0) b.muestra = n;
            b.v[b.n++] = (int32_t)(x >= 0.0f ? x + 0.5f : x - 0.5f);
            if (b.n >= nb) {
                b.tipo = M_BLOQUE;
                b.fs   = (uint16_t)fs;
                if (xQueueSend(cola, &b, 0) != pdPASS) est_perdidos++;
                b.n = 0;
            }
        } else {
            b.n = 0;
        }

        n++;
        est_muestras = n;

        c1 = DWT->CYCCNT;
        dc = c1 - c0;
        acc += dc;
        if (dc > peor) peor = dc;

        if (++seg >= (uint32_t)fs) {    /* cada segundo */
            est_carga_pm  = acc / (configCPU_CLOCK_HZ / 1000u);   /* sin división de 64 bits */
            est_peor_us   = peor / CICLOS_POR_US;
            est_jitter_us = jit / CICLOS_POR_US;
            acc = peor = jit = seg = 0;
        }
    }
}

/* ------------------------------------------------------------------------- */
/* Formato de texto, sin printf (newlib-nano + malloc: mejor no).            */

static char *pon_txt(char *p, const char *s)
{
    while (*s) *p++ = *s++;
    return p;
}

static char *pon_int(char *p, int32_t v)
{
    char t[11];
    int i = 0;
    uint32_t u = v < 0 ? (uint32_t)(-(v + 1)) + 1u : (uint32_t)v;
    if (v < 0) *p++ = '-';
    do { t[i++] = (char)('0' + u % 10u); u /= 10u; } while (u);
    while (i) *p++ = t[--i];
    return p;
}

static char *pon_par(char *p, const char *clave, int32_t v)
{
    *p++ = ' ';
    p = pon_txt(p, clave);
    *p++ = '=';
    return pon_int(p, v);
}

/* ------------------------------------------------------------------------- */
/* Tarea de comunicación: dueña única del canal RPMsg.                        */

static struct rpmsg_channel *canal;
static char tx[RPMSG_BUFFER_SIZE];
static char rx[RPMSG_BUFFER_SIZE];   /* rpmsg_rtos_recv copia maxlen bytes */

static void envia(char *ini, char *fin)
{
    *fin++ = '\n';
    if (rpmsg_rtos_send(canal->rp_ept, ini, (int)(fin - ini), canal->dst) != 0)
        est_perdidos++;
}

static void envia_hola(void)
{
    char *p = pon_txt(tx, "H " NOMBRE " " VERSION);
    p = pon_par(p, "fs", par.fs);
    envia(tx, p);
}

static void envia_estado(void)
{
    char *p = pon_txt(tx, "S");
    p = pon_par(p, "fs", par.fs);
    p = pon_par(p, "ruido", par.ruido);
    p = pon_par(p, "seno", par.seno_amp);
    p = pon_par(p, "seno_mhz", par.seno_mhz);
    p = pon_par(p, "amp", par.sismo_amp);
    p = pon_par(p, "auto", par.automatico);
    p = pon_par(p, "umbral_on", par.umbral_on);
    p = pon_par(p, "umbral_off", par.umbral_off);
    p = pon_par(p, "tx", par.transmitir);
    p = pon_par(p, "muestras", (int32_t)est_muestras);
    p = pon_par(p, "sismos", (int32_t)est_sismos);
    p = pon_par(p, "eventos", (int32_t)est_eventos);
    p = pon_par(p, "evento", (int32_t)est_evento_activo);
    p = pon_par(p, "perdidos", (int32_t)est_perdidos);
    p = pon_par(p, "carga_pm", (int32_t)est_carga_pm);
    p = pon_par(p, "peor_us", (int32_t)est_peor_us);
    p = pon_par(p, "jitter_us", (int32_t)est_jitter_us);
    p = pon_par(p, "heap", (int32_t)xPortGetFreeHeapSize());
    envia(tx, p);
}

static void envia_msg(const msg_t *m)
{
    char *p = tx;
    int i;
    switch (m->tipo) {
    case M_BLOQUE:
        p = pon_txt(p, "D ");
        p = pon_int(p, (int32_t)m->muestra);
        *p++ = ' ';
        p = pon_int(p, m->fs);
        for (i = 0; i < m->n; i++) { *p++ = ' '; p = pon_int(p, m->v[i]); }
        break;
    case M_EVENTO_INI:
        p = pon_txt(p, "E ");
        p = pon_int(p, (int32_t)m->muestra);
        *p++ = ' ';
        p = pon_int(p, m->v[0]);
        break;
    case M_EVENTO_FIN:
        p = pon_txt(p, "F ");
        p = pon_int(p, (int32_t)m->muestra);
        *p++ = ' ';
        p = pon_int(p, m->v[0]);
        *p++ = ' ';
        p = pon_int(p, m->v[1]);
        break;
    default:
        return;
    }
    envia(tx, p);
}

static void responde(const char *pref, const char *orden)
{
    char *p = pon_txt(tx, pref);
    int i;
    *p++ = ' ';
    for (i = 0; orden[i] && i < 60; i++) *p++ = orden[i];
    envia(tx, p);
}

/* Lee un entero tras los espacios; devuelve 0 si no hay. */
static int lee_int(const char **s, int32_t *v)
{
    const char *p = *s;
    int neg = 0, hay = 0;
    int32_t r = 0;
    while (*p == ' ' || *p == '\t') p++;
    if (*p == '-') { neg = 1; p++; }
    while (*p >= '0' && *p <= '9') { r = r * 10 + (*p++ - '0'); hay = 1; }
    if (!hay) return 0;
    *v = neg ? -r : r;
    *s = p;
    return 1;
}

static int empieza(const char *s, const char *pal, const char **resto)
{
    size_t n = strlen(pal);
    if (strncmp(s, pal, n) != 0) return 0;
    if (s[n] != '\0' && s[n] != ' ') return 0;
    *resto = s + n;
    return 1;
}

static void orden(const char *s)
{
    const char *r;
    int32_t a, b;

    if (empieza(s, "hola", &r) || strncmp(s, "hello", 5) == 0) {
        envia_hola();                   /* «hello world!» lo envía Linux al cargar */
        return;
    }
    if (empieza(s, "estado", &r)) { envia_estado(); return; }
    if (empieza(s, "inicia", &r)) { par.transmitir = 1; responde("OK", s); return; }
    if (empieza(s, "pausa", &r))  { par.transmitir = 0; responde("OK", s); return; }
    if (empieza(s, "fs", &r) && lee_int(&r, &a) &&
        a >= 10 && a <= 250 && 1000 % a == 0) {
        par.fs = a; responde("OK", s); return;
    }
    if (empieza(s, "ruido", &r) && lee_int(&r, &a) && a >= 0 && a <= 1000000) {
        par.ruido = a; responde("OK", s); return;
    }
    if (empieza(s, "seno", &r) && lee_int(&r, &a) && lee_int(&r, &b) &&
        a >= 0 && a <= 1000000 && b >= 1 && b <= 125000) {
        par.seno_amp = a; par.seno_mhz = b; responde("OK", s); return;
    }
    if (empieza(s, "amp", &r) && lee_int(&r, &a) && a > 0 && a <= 1000000) {
        par.sismo_amp = a; responde("OK", s); return;
    }
    if (empieza(s, "sismo", &r)) {
        if (!lee_int(&r, &a)) a = par.sismo_amp;
        if (a > 0 && a <= 1000000) { par.sismo_pedido = a; responde("OK", s); return; }
    }
    if (empieza(s, "auto", &r) && lee_int(&r, &a) && (a == 0 || a == 1)) {
        par.automatico = a; responde("OK", s); return;
    }
    if (empieza(s, "umbral", &r) && lee_int(&r, &a) && lee_int(&r, &b) &&
        a >= 11 && a <= 500 && b >= 10 && b < a) {
        par.umbral_on = a; par.umbral_off = b; responde("OK", s); return;
    }
    responde("ERR", s);
}

/* Un mensaje RPMsg puede traer varias líneas; también se acepta sin '\n'. */
static void procesa(char *buf, int len)
{
    char *ini = buf, *p;
    buf[len] = '\0';
    for (p = buf; ; p++) {
        if (*p == '\n' || *p == '\r' || *p == '\0') {
            char fin = *p;
            *p = '\0';
            while (*ini == ' ') ini++;
            if (*ini) orden(ini);
            if (fin == '\0') break;
            ini = p + 1;
        }
    }
}

static void TareaCom(void *pv)
{
    struct remote_device *rdev = NULL;
    TickType_t ult_estado;
    unsigned long src;
    msg_t m;
    int len, r;
    (void)pv;

    PRINTF("\r\n" NOMBRE " " VERSION ": esperando a Linux (RPMsg)...\r\n");
    r = rpmsg_rtos_init(0 /*REMOTE_CPU_ID*/, &rdev, RPMSG_MASTER, &canal);
    if (r != 0) fallo("rpmsg_rtos_init");
    PRINTF("Canal RPMsg [%d ---> %d]\r\n", canal->src, canal->dst);

    ult_estado = xTaskGetTickCount();
    for (;;) {
        /* 1. Lo que manda la adquisición (espera corta) */
        if (xQueueReceive(cola, &m, pdMS_TO_TICKS(20)) == pdPASS) {
            envia_msg(&m);
            while (xQueueReceive(cola, &m, 0) == pdPASS)
                envia_msg(&m);
        }

        /* 2. Órdenes de Linux, sin bloquear */
        while (rpmsg_rtos_recv(canal->rp_ept, rx, &len, sizeof(rx) - 1, &src, 0) == RPMSG_SUCCESS)
            if (len > 0 && len < (int)sizeof(rx)) procesa(rx, len);

        /* 3. Estado una vez por segundo mientras se transmite */
        if (par.transmitir && xTaskGetTickCount() - ult_estado >= pdMS_TO_TICKS(1000)) {
            ult_estado = xTaskGetTickCount();
            envia_estado();
        }
    }
}

/* ------------------------------------------------------------------------- */

void BOARD_MU_HANDLER(void)
{
    rpmsg_handler();
}

int main(void)
{
    hardware_init();
    led_init();
    ciclos_init();

    MU_Init(BOARD_MU_BASE_ADDR);
    NVIC_SetPriority(BOARD_MU_IRQ_NUM, APP_MU_IRQ_PRIORITY);
    NVIC_EnableIRQ(BOARD_MU_IRQ_NUM);

    cola = xQueueCreate(COLA_LEN, sizeof(msg_t));
    if (!cola) fallo("xQueueCreate");

    /* La adquisición arranca ya, aunque Linux todavía no haya cargado nada */
    xTaskCreate(TareaAdq, "adq", PILA_ADQ, NULL, PRIO_ADQ, NULL);
    xTaskCreate(TareaCom, "com", PILA_COM, NULL, PRIO_COM, NULL);

    vTaskStartScheduler();
    for (;;) { }
}
#endif /* !PRUEBA_HOST */
