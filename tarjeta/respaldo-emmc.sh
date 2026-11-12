#!/bin/sh
# Respaldo completo de la eMMC (/dev/mmcblk2) con la raíz congelada.
# Vive en /mnt/otros (disco USB, NO se congela). Lanzar con systemd-run.
set -u
DST=/mnt/otros/respaldo-emmc-20261111
LOG=$DST/respaldo.log
mkdir -p $DST
exec >>$LOG 2>&1
echo "== inicio $(date -Is)  boot_id $(cat /proc/sys/kernel/random/boot_id)"
dd if=/dev/mmcblk2boot0 of=$DST/mmcblk2boot0.bin bs=1M
dd if=/dev/mmcblk2boot1 of=$DST/mmcblk2boot1.bin bs=1M
sfdisk -d /dev/mmcblk2 > $DST/particiones.sfdisk
journalctl --relinquish-var          # journald a /run mientras / está congelada
sync
systemd-run --unit=emmc-thaw-safety --on-active=480 /sbin/fsfreeze -u /
T0=$(date +%s)
fsfreeze -f / && echo "congelada / a $(date -Is)"
dd if=/dev/mmcblk2 bs=4M iflag=direct status=none | zstd -1 -T2 -c > $DST/mmcblk2.img.zst
RC_DD=$?
fsfreeze -u /; echo "descongelada / tras $(( $(date +%s) - T0 )) s (rc pipeline $RC_DD)"
systemctl stop emmc-thaw-safety.timer 2>/dev/null
journalctl --flush
sync
ls -l $DST
echo "== sha256"
( cd $DST && sha256sum mmcblk2.img.zst mmcblk2boot0.bin mmcblk2boot1.bin > SHA256SUMS && cat SHA256SUMS )
echo "== verificar zstd"
zstd -t $DST/mmcblk2.img.zst && echo "zstd íntegro"
echo "== fin $(date -Is)"
