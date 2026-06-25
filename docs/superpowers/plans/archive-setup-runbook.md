# 아카이브 webhook 1회 셋업 런북

## 1. GitHub fine-grained PAT 발급
- Settings → Developer settings → Fine-grained tokens → Generate
- Repository access: 이 repo 하나만
- Permissions: **Contents = Read and write** (그 외 전부 No access)
- 토큰 복사 → `GITHUB_TOKEN`

## 2. webhook secret 생성
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
→ 출력값을 `WEBHOOK_SECRET` 으로 사용.

## 3. Vercel 배포
```bash
npm i -g vercel   # 최초 1회
vercel link       # 이 repo 를 Vercel 프로젝트에 연결
vercel env add WEBHOOK_SECRET production       # 위 secret
vercel env add TELEGRAM_BOT_TOKEN production    # 기존 봇 토큰
vercel env add GITHUB_TOKEN production          # 1번 PAT
vercel env add GITHUB_REPO production           # 예: jeongdowny/morning-briefing
vercel --prod
```
→ 배포 URL 확인 (예 `https://morning-briefing-xxxx.vercel.app`). 엔드포인트는 `/api/telegram`.

## 4. 텔레그램 webhook 등록 (secret 동봉)
```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<배포도메인>/api/telegram" \
  -d "secret_token=<WEBHOOK_SECRET>" \
  -d 'allowed_updates=["callback_query"]'
```
→ `{"ok":true,...}` 확인.

## 5. 검증
- `python scripts/build_manifest.py && git add data/ && git commit -m test && git push`
- 텔레그램에서 아무 메시지에 버튼이 오도록 `python scripts/send_telegram.py` 수동 실행
  (TELEGRAM_BOT_TOKEN/CHAT_ID 환경변수 필요)
- 버튼 탭 → 몇 초 뒤 repo `Archive/` 에 노트 커밋 + 버튼이 ✅ 로 바뀌는지 확인
- 같은 버튼 다시 탭 → "이미 저장됨" 응답(멱등) 확인

## 롤백
- 텔레그램 webhook 해제: `curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"`
- 버튼 없는 기존 발송으로 되돌리려면 send_telegram 변경 revert.
