# Telegram 봇 생성 및 토큰/chat_id 취득 가이드

프로젝트 공통 레퍼런스. Telegram으로 알림 보내는 모든 프로젝트에서 재사용 가능.

## 1. 봇 생성 (BotFather)

1. 텔레그램 앱에서 `@BotFather` 검색해 대화 시작
2. `/newbot` 입력
3. 봇 이름(표시 이름, 아무거나) 입력
4. 봇 username 입력 — **반드시 `bot`으로 끝나야 함** (예: `my_alert_bot`)
5. 완료되면 BotFather가 토큰을 줌 — `123456789:AAH...` 형태. 이게 `TELEGRAM_BOT_TOKEN`

## 2. 봇 신원 재확인 (헷갈림 방지)

검색 결과에 비슷한 이름의 봇이 여러 개 뜨는 경우가 흔해서, 토큰과 실제로 대화한 봇이 다를 수
있다. 아래로 토큰이 진짜 어떤 봇인지 먼저 확인하는 걸 권장:

```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getMe"
```

응답의 `"username"`이 텔레그램 앱에서 메시지 보낼 그 봇과 정확히 같은지 대조.

## 3. chat_id 취득

봇은 사용자에게 먼저 말을 걸 수 없음 — **사용자가 먼저 메시지를 보내야** chat_id를 얻을 수 있다.

1. 1번에서 만든 봇을 텔레그램에서 검색해 들어가서 아무 메시지나 전송 (예: "안녕")
2. 아래 명령으로 업데이트 조회:

```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getUpdates"
```

3. 응답에서 `result[].message.chat.id` 값을 찾으면 그게 `TELEGRAM_CHAT_ID`
   (개인 DM이면 양수, 그룹이면 음수로 나옴)

```json
{
  "result": [
    { "message": { "chat": { "id": 123456789 } } }
  ]
}
```

## 4. 트러블슈팅

### `{"ok":true,"result":[]}` — 메시지 보냈는데도 빈 배열

원인 후보 순서대로 확인:

1. **다른 봇에 메시지 보냈을 가능성** — 2번(`getMe`)으로 토큰의 실제 봇 username과 대조
2. **타이밍 문제** — 메시지 보낸 직후 바로 호출하면 서버 반영 전일 수 있음. 1~2초 뒤 재호출
3. **대기열 꼬임** — `getWebhookInfo`로 `pending_update_count`가 1 이상인데 `getUpdates`가
   계속 빈 배열이면, 아래로 한 번 리셋 후 메시지 다시 보내고 재시도:

```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getUpdates?offset=-1"
```

## 5. 메시지 발송 (코드 예시)

별도 SDK 없이 `requests` 한 줄로 충분 — `python-telegram-bot` 같은 무거운 라이브러리는
사실상 과함 (비동기 전제라 단순 발송용으로는 불필요).

```python
import requests

def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    resp = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    return resp.ok
```

## 6. 보안 주의

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 둘 다 `.env`에만 보관, 저장소에 커밋 금지
  (`.gitignore`에 `.env` 등록 확인)
- 토큰 유출 시 BotFather에서 `/revoke` 또는 `/token`으로 재발급 가능
