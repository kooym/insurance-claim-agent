# MCP 설정가이드

> **.cursor/mcp.json** 전체 예시 및 각 MCP 활용 시나리오

---

## 1. .cursor/mcp.json 전체 예시

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/Users/youngmokoo/Documents/cursor projects/지급보험금산정_agent"
      ]
    },
    "sqlite": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sqlite",
        "/Users/youngmokoo/Documents/cursor projects/지급보험금산정_agent/data/insurance.db"
      ]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-brave-search"],
      "env": {
        "BRAVE_API_KEY": "YOUR_BRAVE_API_KEY"
      }
    },
    "fetch": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-fetch"]
    }
  }
}
```

> **참고**: `insurance.db`가 없으면 SQLite MCP 사용 시 오류 가능. `data/insurance.db` 생성 후 사용.

---

## 2. 각 MCP 활용 시나리오

### 2.1 Filesystem

| 시나리오 | 용도 |
|----------|------|
| 서류 읽기 | `data/sample_docs/{claim_id}/` 내 파일 목록·내용 조회 |
| 결과 쓰기 | `outputs/{claim_id}/` 결과 파일 생성 |
| 참조 데이터 | `data/reference/*.json` 읽기 |

### 2.2 SQLite

| 시나리오 | 용도 |
|----------|------|
| 계약 조회 | contracts_db.json → insurance.db 마이그레이션 시 |
| 청구 이력 | COM-004 중복청구 체크, 연간 누적 지급액 |
| RAG 메타데이터 | 벡터 검색 결과와 청크 출처 매핑 |

### 2.3 Brave Search

| 시나리오 | 용도 |
|----------|------|
| 약관 검색 | 최신 약관 조항 확인 |
| KCD 코드 | HIRA 공개 정보 검색 |
| **API 키 필요** | [Brave Search API](https://brave.com/search/api/) 발급 |

### 2.4 Fetch

| 시나리오 | 용도 |
|----------|------|
| HIRA API | KCD 조회, 수가코드 검증 |
| 식약처 DUR | 비급여 주사료 허가 범위 |
| data.go.kr | 보험 통계·공시 데이터 |

---

## 3. 설치 및 활성화

### 3.1 Cursor MCP 설정

1. Cursor 설정 → MCP → `Edit in settings.json` 또는 `.cursor/mcp.json` 직접 편집
2. 위 JSON 내용 붙여넣기
3. `YOUR_BRAVE_API_KEY`를 실제 키로 교체 (Brave Search 사용 시)
4. Cursor 재시작

### 3.2 SQLite DB 생성 (선택)

```bash
# insurance.db가 없으면 빈 DB 생성
sqlite3 data/insurance.db "SELECT 1"
```

---

## 4. Brave Search 비활성화 (API 키 없을 때)

```json
{
  "mcpServers": {
    "filesystem": { ... },
    "sqlite": { ... },
    "fetch": { ... }
  }
}
```

`brave-search` 항목을 제거하면 API 키 없이 Filesystem, SQLite, Fetch만 사용 가능.
