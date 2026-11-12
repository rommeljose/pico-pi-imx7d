# Migración de `eth0` a NetworkManager — 2026-08-16

Registro de cómo se hizo y qué se aprendió. El **estado resultante** está en
[`Tarjeta_Inventario.md`](Tarjeta_Inventario.md) §7.

## Por qué

El applet de red de la tarjeta mostraba, al abrir *Connection Information*:

    Error displaying connection information
    No valid active connection found!

**El mensaje era cierto, no un fallo de despliegue.** `nm-applet` arrancaba desde
`/etc/xdg/autostart/`, pero NetworkManager no gestionaba nada: `managed=false` en
`[ifupdown]`, `eth0` en estado `unmanaged` y **cero perfiles definidos**. La red
la llevaba ifupdown. El applet preguntaba por la conexión activa y no había
ninguna que dar.

La red **funcionaba perfectamente**. Lo único roto era el applet.

## Estado antes y después

| | Antes (2026-08-15) | Después (2026-08-16) |
|---|---|---|
| Gestor de `eth0` | ifupdown (`networking.service`) | **NetworkManager**, perfil `eth0-main` |
| `/etc/network/interfaces` | `auto eth0` + `iface eth0 inet dhcp` | ambas líneas **comentadas** |
| Dirección DHCP | `.252` | **`.251`** — NM pide la concesión con otro client-id |
| IP de rescate `.240` | solo `rescue-ip.service` | **el perfil de NM y además** `rescue-ip.service` |
| Clientes DHCP | 1 (`dhclient` de ifupdown) | 1 (el interno de NM) |

## El riesgo, y cómo se acotó

La tarjeta **no tiene consola serie**: si SSH cae, no hay rescate remoto. Y el
salvavidas resultó más frágil de lo que parecía —

> `rescue-ip.service` es `Type=oneshot` con `RemainAfterExit=yes`. Pone la `.240`
> **una sola vez al arrancar** y systemd ya lo da por hecho. **Si algo vacía las
> direcciones con la máquina en marcha, la `.240` no vuelve sola.**

Por eso la `.240` se metió **dentro del perfil de NetworkManager**
(`ipv4.addresses 192.168.1.240/24` junto a `ipv4.method auto`), para que la
sirva el propio NM y no dependa de un servicio que ya se ejecutó.

Cuatro capas de seguridad, y las cuatro se usaron o quedaron listas:

1. La `.240` dentro del perfil de NM.
2. Autorreparación en el script del salto: a los 15 s, si la `.240` no está,
   `ip addr replace`.
3. **Reversión armada** a 7 minutos con `systemd-run --on-active=420`, que
   restaura los ficheros y reinicia. Se cancela solo tras verificar acceso.
4. Teclado y pantalla conectados a la tarjeta — el factor que hizo aceptable la
   operación. Sin ellos habría convenido esperar a la consola serie.

## La trampa que costó un intento

El primer intento **falló sin dañar nada**. El log lo dijo claro:

    Connection activation failed: No suitable device found for this connection

> ⚠️ **`nmcli general reload` NO hace que el plugin `ifupdown` relea
> `/etc/network/interfaces`.** Aunque `eth0` ya estaba comentada, NM seguía
> teniéndola por `unmanaged` desde su arranque. Hace falta
> **`systemctl restart NetworkManager`**.

El segundo intento, con reinicio del servicio, funcionó a la primera. Fallo
limpio, red intacta, y el diagnóstico salió del propio registro — que es
exactamente para lo que se lanza con `systemd-run` y se mira el journal.

## Verificación

Tras un **reinicio real** de la tarjeta:

| Comprobación | Resultado |
|---|---|
| `eth0` | ✅ `192.168.1.240` + `192.168.1.251` |
| NetworkManager | ✅ `eth0:connected:eth0-main` · `activated` |
| Ruta por defecto | ✅ vía DHCP de NM, `metric 100` |
| `nm-applet` | ✅ arrancó solo |
| `rescue-ip.service` | ✅ `active` |
| `dhclient` huérfano | ✅ **ninguno** |
| **Arranque del M4** | ✅ `gpio38/direction = out` → el M4 sigue arrancando |

## Esto no es la regresión del fallo antiguo

Conviene dejarlo escrito, porque leído de pasada parece que se deshizo el arreglo
del 15:

El fallo original era **NetworkManager e ifupdown gestionando `eth0` a la vez**,
con la dirección oscilando entre `.252` y `.253` según caducaban las concesiones,
hasta cortar una sesión SSH en marcha.

**El problema nunca fue quién gestionaba, sino que gestionaran dos.** Con un solo
gestor, cualquiera de las dos configuraciones es estable. Lo que no debe volver a
haber es las dos activas — y se comprobó que no queda ningún `dhclient` huérfano.

## Revertir

Desde la propia tarjeta, un comando:

    sudo /usr/local/sbin/net-rollback.sh    # restaura ifupdown y reinicia

Restaura `/root/net-backup/{NetworkManager.conf,interfaces}`, borra el perfil
`eth0-main` y reinicia. Deja la tarjeta como estaba el 2026-08-15.

## Efecto secundario: la `.240` quedó atada a la subred del router

Meter la `.240` dentro del perfil resolvió el problema del salvavidas, pero
**clavó `192.168.1.0/24` en la configuración de la tarjeta** — y esa es la
subred de ese router. Si la Pico-Pi se lleva a otro router con otra
subred, habrá conectividad por DHCP pero la `.240` no responderá.

No es un fallo de esta migración: la `.240` ya estaba clavada antes en
`rescue-ip.service`. Lo que hace la migración es **duplicar** el sitio donde
aparece.

Vías de acceso que **no** dependen de la subred (mDNS `technexion.local` e IPv6
link-local), y las tres opciones para desatarla del todo, en
[`Tarjeta_Inventario.md` §7](Tarjeta_Inventario.md).

## Incidente 2026-11-11: el enlace tardó y NM se quedó sin `eth0-main`

Tras un `poweroff` y encendido, el enlace de `eth0` subió **1 min 45 s** después
del arranque (`09:43:14 fec … Link is Up`). Mientras tanto `rescue-ip.service`
ya había puesto la `.240`. NetworkManager vio una dirección puesta por otro,
la **asumió** como conexión externa en memoria llamada `eth0` (`connected
(externally)`), y cuando llegó el carrier **no activó `eth0-main`**. El resultado:
solo la `.240`, **sin DHCP, sin ruta por defecto, sin Internet ni NTP**, y el reloj
quedó en 2026-07-29.

La tarjeta **seguía accesible** por la `.240`, que es para lo que está la IP de
rescate, así que el salvavidas funcionó. Se arregló en caliente con
`nmcli connection up eth0-main`, con la reversión armada. Después hubo DHCP
`.251`, ruta por defecto vía `.1`, ping a Internet y la hora corregida.

**Arreglo aplicado (2026-11-11):** `rescue-ip.service` pasó a ser un vigilante,
`/usr/local/sbin/rescue-ip.sh` (`Type=simple`, `Restart=always`, `After=NetworkManager.service`):

- **Espera al enlace:** cuenta los segundos con carrier en `eth0` y no actúa hasta 90 s después.
- **No se adelanta a NM:** solo añade la `.240` si falta, y lo deja escrito en el journal (`journalctl -t rescue-ip`).
- **Se autorrepara:** comprueba cada 30 s.
- **Sin `ExecStop`:** la versión vieja borraba la `.240` al pararse, y por eso el cambio se lanzó con `systemd-run` y se vigiló entrando por la `.251`.

Se aplicó con el método de siempre: respaldo en `/root/net-backup/rescue-20261111/`, reversión a 7 min, el cambio lanzado con `systemd-run` y verificación antes de cancelar la reversión.

**Verificado:** se quitó la `.240` a mano y volvió a los 10 s (`faltaba 192.168.1.240/24: añadida a eth0`), con `eth0-main` activo en todo momento.

**Verificado en un arranque real (2026-11-11):** la tarjeta arrancó con el cable desconectado, y el cable se conectó unos 2 min después. `Link is Up` a las 21:33:10, y `eth0-main` empezó a activarse en el mismo segundo, con DHCP `.251`, la `.240` y la ruta por defecto. `rescue-ip` no tuvo que actuar: no dejó ninguna entrada en el journal. Para volver a la versión anterior, copiar la unidad del respaldo, ejecutar `daemon-reload` y reiniciar el servicio.

Para entrar por la `.251` sin tocar `known_hosts`: `ssh -o HostKeyAlias=192.168.1.240 ubuntu@192.168.1.251`.
