#!/bin/sh
set -eu
BASE=/home/sfos/luneos-ports/work/volte-fix-flash-20261125
O=$BASE/overlay
scp -q root@192.168.2.161:/usr/lib/modules/6.1.192/kernel/drivers/net/ipa/ipa.ko $O/usr/lib/modules/6.1.192/kernel/drivers/net/ipa/ipa.ko
scp -q root@192.168.2.161:/usr/lib/modules/6.1.192/kernel/sound/soc/qcom/qdsp6/q6asm.ko $O/usr/lib/modules/6.1.192/kernel/sound/soc/qcom/qdsp6/q6asm.ko
scp -q root@192.168.2.161:/usr/lib/modules/6.1.192/kernel/sound/soc/qcom/qdsp6/q6routing.ko $O/usr/lib/modules/6.1.192/kernel/sound/soc/qcom/qdsp6/q6routing.ko
scp -q root@192.168.2.161:/usr/lib/pulseaudio/modules/module-palm-policy.so $O/usr/lib/pulseaudio/modules/module-palm-policy.so
scp -q root@192.168.2.161:/usr/lib/qml/WebOSCompositor/qml/Connectors/MultiSimModel.qml $O/usr/lib/qml/WebOSCompositor/qml/Connectors/MultiSimModel.qml
scp -q root@192.168.2.161:/usr/local/sbin/audio-repair.sh $O/usr/local/sbin/audio-repair.sh
scp -q root@192.168.2.161:/usr/local/sbin/luneos-ofono-post-online.sh $O/usr/local/sbin/luneos-ofono-post-online.sh
scp -q root@192.168.2.161:/etc/ofono/qrtr.conf $O/etc/ofono/qrtr.conf
scp -q root@192.168.2.161:/etc/systemd/system/ofono.service.d/10-modem-online.conf $O/etc/systemd/system/ofono.service.d/10-modem-online.conf
scp -q root@192.168.2.161:/etc/systemd/system/luneos-mobile-data.service.d/60-after-ofono.conf $O/etc/systemd/system/luneos-mobile-data.service.d/60-after-ofono.conf
scp -q root@192.168.2.161:/usr/share/luna-service2/roles.d/com.webos.service.audiooutput.role.json $O/usr/share/luna-service2/roles.d/com.webos.service.audiooutput.role.json
scp -q root@192.168.2.161:/usr/share/luna-service2/services.d/com.webos.service.audiooutput.service $O/usr/share/luna-service2/services.d/com.webos.service.audiooutput.service
scp -q root@192.168.2.161:/etc/systemd/system/volume-key-daemon.service $O/etc/systemd/system/volume-key-daemon.service
scp -q root@192.168.2.161:/etc/systemd/system/remoteproc-late-start.service $O/etc/systemd/system/remoteproc-late-start.service
ln -sfn /usr/lib/systemd/system/ofono.service $O/etc/systemd/system/multi-user.target.wants/ofono.service
ln -sfn /etc/systemd/system/remoteproc-late-start.service $O/etc/systemd/system/multi-user.target.wants/remoteproc-late-start.service
echo EXPORTED
