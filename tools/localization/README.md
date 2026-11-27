# 차분화 우주 한국어 화면 점검

현재 화면의 한국어 OCR과 판정 결과를 확인할 수 있습니다. 버튼 클릭과 게임 입력은 전송하지 않습니다. 차분화 우주 메인 또는 `안정적 배열`을 열고, 명령 실행 후 15초 안에 게임을 맨 앞으로 가져오세요.

수집기의 Python 환경을 이미 설치한 경우, 저장소 루트에서 PowerShell로 실행합니다.

```powershell
& 'C:\Share\Samchili-DU-Collector\.venv\Scripts\python.exe' -m tools.localization.du_probe --model-dir 'C:\Share\Samchili-DU-Collector\.ocr-models'
```

수집기를 별도 경로에 설치했다면 위 경로를 맞춰 주세요. 결과는 `localization/reports/du-probe.json`에 저장됩니다. `candidate`는 확인 후보, `low_confidence`는 신뢰도가 부족한 문구입니다. 둘 다 이 점검 도구에서 자동 클릭을 실행하지 않습니다.

기존 Windows 수집본의 검은 여백을 포함한 녹화는 아래처럼 재생할 수 있습니다. 예시 뷰포트는 N150의 1024×1280 캡처 안에 있는 1024×768 게임 영역에 해당합니다.

```powershell
& 'C:\Share\Samchili-DU-Collector\.venv\Scripts\python.exe' -m tools.localization.du_replay 'C:\Share\Samchili-DU-Collector\du-captures\세션\recordings\ko_KR' --viewport 0 0.2 1 0.6
```

주간 점수의 상한, 미완료 미션, 실제 보상 지급은 서로 다른 상태입니다. `안정적 배열`의 `진행 중` 줄에서 방정식 전개와 가면 착용 후 클리어 조건을 후보로 표시합니다. 한국어 전체 탐사와 보상 수령을 활성화하기 전에는 실제 성공 정산, 수령 버튼 및 수령 결과를 대조해야 합니다.
