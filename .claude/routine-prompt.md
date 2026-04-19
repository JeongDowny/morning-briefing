# DEPRECATED — Claude Code Routines 용 프롬프트

이 프로젝트는 이제 **GitHub Actions** 로 스케줄 실행됩니다.
자동 실행 로직은 `.github/workflows/daily-brief.yml` 과 `scripts/summarize.py` · `scripts/render_daily.py` 에 있습니다.

## 전환 사유

Claude Code Routines 의 샌드박스에서 외부 HTTP 요청이 403 으로 차단되어
네이버 · OpenAI · Anthropic · RSSHub 접근이 불가능했습니다 (2026-04 기준).
Routines 가 egress 허용을 공식 지원하면 다시 검토할 수 있습니다.

## 이 파일은 왜 남아있나

- `.claude/` 는 Claude Code CLI 가 읽는 설정 디렉토리입니다.
- 혹시 로컬에서 `claude` CLI 로 이 파일을 참고해 수동 작업하고 싶을 때 사용.
- `.claude/settings.json` 의 SessionStart 훅은 로컬 Claude 세션에서
  의존성을 자동 설치하는 데 여전히 유용합니다.

필요 없다고 판단되면 `.claude/routine-prompt.md` 는 삭제해도 됩니다.
