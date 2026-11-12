# ICN Flight Monitor

4시간마다 인천국제공항(ICN) 국제선 여객기 출발·도착 데이터를 공식 인천국제공항공사 API에서 수집합니다.

## Setup
1. 공공데이터포털에서 [인천국제공항공사 항공기 운항 현황 상세 조회](https://www.data.go.kr/data/15140153/openapi.do)를 활용 신청합니다.
2. Repository → Settings → Secrets and variables → Actions에 \`DATA_GO_KR_SERVICE_KEY\` 이름으로 **디코딩된 서비스키**를 저장합니다. 키를 코드, 이슈, 커밋에 올리지 마세요.
3. Actions 탭에서 \`ICN international passenger flights - 4-hour collection\`을 선택하고 \`Run workflow\`를 눌러 최초 실행합니다.

## Schedule
GitHub Actions cron: UTC 03:05, 07:05, 11:05, 15:05, 19:05, 23:05 = KST 12:05, 16:05, 20:05, 00:05, 04:05, 08:05. GitHub 예약 실행은 지연될 수 있습니다.

## Metrics and guardrails
- 예정 시간 기준 직전 4시간 구간의 계획편 수, 공식 상태에 명시된 출발/도착 확인편, 결항, 지연/미확정 편수를 출발·도착별 집계합니다.
- 국내선은 상대 공항 IATA 코드 목록으로 제외합니다. 코드셰어는 마스터편명과 예정시각 기준으로 중복을 줄입니다.
- \`completed_confirmed\`는 API에 명시된 \`출발\`/\`도착\` 상태이며 레이더·관제 실측 이착륙 수와 동일하지 않습니다.
- API 필드가 예상과 다르거나 일부 페이지가 누락되면 성공한 것처럼 0편을 기록하지 않고 워크플로를 실패시킵니다.
- \`data/latest.json\`, \`data/latest.md\`, \`data/history.json\`에 결과를 저장합니다. 7일 동일 시간대 비교는 7일의 정상 기록이 쌓인 후에만 표시합니다.
- 개발계정 기본 호출량은 일 500회이며, 이 워크플로는 통상 하루 12회 이내입니다. 운영계정 별도 승인·트래픽 조건은 공공데이터포털에서 확인하세요.

## Limitations
최초 실제 실행에서 공식 API의 JSON 필드와 상태값을 검증해야 합니다. \`planned\`는 API가 반환한 예정편 수, \`completed_confirmed\`는 상태가 명시된 편수입니다. 전쟁 위험을 단독으로 판정하는 지표가 아니며 기상·파업·정비·시즌별 스케줄 변동을 함께 확인해야 합니다.
