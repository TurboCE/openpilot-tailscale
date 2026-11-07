# openpilot Tailscale — 부팅 90초 후 시작

AGNOS 기반 openpilot/CarrotPilot/FrogPilot 기기에 Tailscale을 설치하는 독립 스크립트입니다. `/data`에 공식 ARM64 바이너리와 로그인 상태를 보관하고, systemd **OnBootSec=90s** 타이머로 자동 시작합니다. openpilot 시작은 백그라운드 훅으로 분리합니다.

## 설치

기기가 정차·offroad 상태일 때 SSH/터미널에서 실행합니다.

```sh
curl -fsSL https://raw.githubusercontent.com/TurboCE/openpilot-tailscale/main/install.sh | sudo -n bash
```

계정 인증은 최초 한 번 필요합니다. 표시되는 URL을 브라우저에서 열어 본인의 Tailscale 계정으로 로그인합니다.

```sh
sudo /data/tailscale/login.sh trailblazer
```

30초 안에 로그인이 끝나지 않아 명령이 timeout으로 종료돼도, 표시된 로그인 링크에서 인증 후 다시 상태를 확인할 수 있습니다. 기존 로그인 상태는 재설치 시 유지합니다. API 키나 Tailscale 로그인 키는 이 저장소에 포함하지 않습니다.

## Tailscale 기기 목록 · 이전 기기 삭제

**[Tailscale 기기 목록 열기](https://login.tailscale.com/admin/machines)**

로그인 후 사용하지 않는 기기의 이름·IP·마지막 접속 시간을 확인하고, 해당 항목의 **⋯ → Remove → 확인**으로 삭제합니다. 현재 사용 중인 기기와 혼동하지 마세요. 초기화 후 재등록했다면 이전 항목만 삭제하면 됩니다.

## 팩토리리셋 후 재설치와 기기 중복 등록

팩토리리셋 후 openpilot을 설치하고 인터넷에 연결한 다음, 위 설치 한 줄을 다시 실행하면 됩니다. `/data/tailscale/state`가 남아 있다면 기존 인증 정보를 재사용합니다. 이 폴더까지 삭제됐다면 `sudo /data/tailscale/login.sh trailblazer`로 다시 인증해야 합니다.

상태가 삭제된 뒤 재인증하면 새 기기로 등록될 수 있습니다. 같은 `trailblazer` 이름을 지정해도 기존 기기를 자동으로 대체하지 않습니다. 기존 기기는 초기화나 앱 제거만으로 Tailscale 관리 화면에서 자동 삭제되지 않으므로, 반복하면 사용하지 않는 기기가 남을 수 있습니다.

중복 등록을 정리하려면 [Tailscale Machines](https://login.tailscale.com/admin/machines)에서 기존 IP·마지막 연결 시각을 확인하고, 초기화 전의 사용하지 않는 항목만 Remove하세요. 현재 접속 중인 새 기기와 혼동하지 마세요. 초기화 전에 기존 기기를 지워도 됩니다. 이 설치 스크립트는 관리 API 자격 증명을 요구하거나 다른 기기를 자동 삭제하지 않습니다.

같은 기기 신원을 재사용하려면 초기화 전에 서비스가 정지한 상태의 `/data/tailscale/state`를 기기 밖의 비공개 위치에 백업하고, 재설치 후 서비스가 정지한 상태에서 원래 위치로 복원하는 방법이 있습니다. 키·인증 정보가 포함되므로 GitHub에 올리거나 다른 기기에 복제하지 마세요. 원래 기기가 관리 화면에서 삭제되거나 키가 무효화된 경우에는 복원해도 재인증이 필요할 수 있습니다. 이 저장소의 한 줄 설치는 백업·복원을 자동 수행하지 않습니다.

참고: [공식 기기 삭제 안내](https://tailscale.com/docs/features/access-control/device-management/how-to/remove), [공식 상태 초기화 안내](https://tailscale.com/docs/features/client/uninstall).

## 동작

- 고정 Tailscale 버전: **1.104.5**, 공식 다운로드 `dl.tailscale.com`, 고정 SHA-256으로 검증. ARM64 AGNOS 기기 대상입니다.
- `/data/continue.sh`의 기존 내용을 보존하고 식별 가능한 백그라운드 훅 한 개만 추가합니다. 재실행해도 중복되지 않습니다.
- systemd 유닛은 부팅할 때 `/run`에 연결합니다. 루트 파일시스템을 쓰기 가능하게 바꾸거나 `/etc/fstab`, 커널, 차량 제어 코드를 수정하지 않습니다.
- **90초는 기기 부팅 기준**이며 설치/재로그인 시점 기준이 아닙니다. 이미 90초가 지난 기기에서 설치하면 현재 부팅에서는 바로 시작할 수 있습니다.
- 타이머의 1초 정확도와 실제 스케줄링·네트워크 연결 시간이 더해질 수 있습니다. 부팅 후 약 90초 동안 Tailscale로 접속되지 않는 것은 정상입니다.
- 서비스는 `Nice=10`으로 실행합니다. CPUWeight/cgroup 강제 설정, 토크·가감속·조향 변경은 없습니다.
- 로그인 시 `accept-dns=false`, `accept-routes=false`를 명시합니다. exit node·서브넷 라우팅·Tailscale SSH 서버는 활성화하지 않습니다. 기존 OpenSSH로 Tailscale IP에 접속합니다.
- 이미 실행 중인 이 설치 방식의 tailscaled를 재설치 때문에 강제로 재시작하지 않습니다. 별도로 설치한 다른 tailscaled 서비스는 덮어쓰지 않습니다.
- 과거에 식별자 없이 추가한 Tailscale 시작 훅이 있으면 중복 실행 방지를 위해 설치를 중단합니다. 기존 훅을 먼저 검토·이관해야 합니다.

## 상태 확인

```sh
sudo /data/tailscale/bin/tailscale status
sudo /data/tailscale/bin/tailscale ip -4
systemctl status tailscaled-delay.timer tailscaled.service --no-pager
systemctl show tailscaled.service -p ExecMainStartTimestampMonotonic
journalctl -b -u tailscaled.service -o short-monotonic --no-pager
```

정상 부팅에서 `ExecMainStartTimestampMonotonic`은 대략 **90,000,000 µs 이상**입니다. 수동으로 `systemctl start tailscaled`를 실행하면 자동 시작 지연을 직접 건너뛸 수 있습니다.

## 패치·복구·제거

- `patches/continue.sh.patch`: 기본 CarrotPilot 시작 파일에 대한 예시 패치입니다. 다른 시작 파일에는 맹목적으로 적용하지 말고 설치 스크립트를 사용하세요.
- 설치할 때마다 원본 시작 파일과 **해당 기기에 정확히 대응하는 패치**를 `/data/tailscale/backups/<시간-식별자>/`에 보관합니다. 다른 사용자 훅은 보존합니다.
- 자동 시작 제거:

```sh
curl -fsSL https://raw.githubusercontent.com/TurboCE/openpilot-tailscale/main/install.sh | sudo -n bash -s -- --uninstall
```

제거하면 Tailscale 연결이 끊길 수 있으므로 LAN/현장 접속으로 실행하세요. 로그인 상태와 바이너리는 보존하며 저장장치 데이터는 삭제하지 않습니다.

## 개발·검증

```sh
python3 build_installer.py
python3 -m unittest discover -s tests -v
for f in install.sh files/start.sh files/login.sh; do bash -n "$f" || exit; done
```

`installer.py`와 `files/`가 원본이며 `install.sh`는 이들을 내장한 단일 배포 파일입니다. `curl` 설치 과정에서 이 저장소의 다른 파일을 추가로 내려받지 않습니다. 바이너리만 공식 Tailscale 서버에서 받습니다. 수정 후에는 `build_installer.py`를 실행하세요.

90초 지연은 부팅 시 부하를 분산하기 위한 설정입니다. NVMe 전원·접촉·장치 고장을 해결하거나 Tailscale이 NVMe 오류 원인임을 입증하는 기능은 아닙니다.

공식 자료: [Linux/static 설치](https://tailscale.com/docs/install/linux), [공식 패키지·체크섬](https://dl.tailscale.com/stable/), [tailscale up 옵션](https://tailscale.com/docs/reference/tailscale-cli/up).

실기 확인: AGNOS 18.4 / CarrotPilot `bb454a2`에서 설치 성공, 서비스 active 및 `OnBootUSec=1min 30s` 확인. 시작 훅 보존·중복 방지 등 단위 테스트 5개 통과. 실제 재부팅 후 시작 시각 검증은 아직 수행하지 않았습니다.

AGNOS의 nft 프런트엔드가 커널과 호환되지 않을 경우 읽기 전용 검사로 확인한 뒤, Tailscale 서비스의 PATH에만 동작하는 iptables-legacy/ip6tables-legacy를 연결합니다. 시스템 alternatives 및 기존 방화벽 정책은 변경하지 않습니다. 이미 실행 중인 서비스를 이 변경으로 갱신하려면 LAN에서 `sudo systemctl restart tailscaled.service`를 실행하거나 다음 부팅을 기다리세요.
