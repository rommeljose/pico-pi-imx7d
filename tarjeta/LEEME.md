# Ficheros de configuración instalados en la tarjeta

Copias exactas de lo que se instaló en la Pico-Pi (Ubuntu 22.04 de TechNexion,
kernel 5.10.72). **Las direcciones son de ejemplo**: ajústalas a tu red.

| Fichero | Destino en la tarjeta | Para qué |
|---|---|---|
| `rescue-ip.sh` | `/usr/local/sbin/rescue-ip.sh` (755) | IP fija de rescate, vigilante: espera al enlace, da 90 s a NetworkManager y solo añade la IP si falta; se autorrepara |
| `rescue-ip.service` | `/etc/systemd/system/rescue-ip.service` | lo arranca (`systemctl enable --now rescue-ip`) |
| `50-ap-nat` | `/etc/NetworkManager/dispatcher.d/50-ap-nat` (755, root) | NAT para el punto de acceso `ap-picopi`; necesario porque el kernel no tiene tabla `filter` de iptables |
| `rpmsg.conf` | `/etc/modules-load.d/rpmsg.conf` | carga `imx_rpmsg_tty` al arrancar → `/dev/ttyRPMSG0` |
| `respaldo-emmc.sh` | en un disco **distinto** de la eMMC (p. ej. un USB) | imagen completa de la eMMC con la raíz congelada (`fsfreeze`), unos 2 min |
| `comparar-crc.sh` | en el PC | compara los CRC de `MODVERSIONS` del kernel vivo con un `Module.symvers` |

Todos están **verificados funcionando** en la tarjeta (2026-11-11), incluido un
reinicio con el cable de red desconectado. El procedimiento y las trampas de
cada uno están en:

- `rescue-ip.*` → `docs/Red_Migracion_NetworkManager.md` (final)
- `50-ap-nat`, punto de acceso → `docs/WiFi_Diagnostico.md` (final)
- `rpmsg.conf` → `docs/RPMsg_Verificacion.md`
- `respaldo-emmc.sh`, `comparar-crc.sh` → `blog/` y `docs/Kernel_Recompilacion.md`

⚠️ `respaldo-emmc.sh` produce una imagen que contiene **secretos**:
`/etc/shadow`, las claves privadas de host SSH y la clave del AP. No la publiques
tal cual.
