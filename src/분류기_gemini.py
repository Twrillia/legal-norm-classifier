# =====================================================
# 법조항 분류기 (Gemini LLM 기반)
# 정규식 분류기의 샘플 300개를 Gemini로 재분류하여 비교
# =====================================================

import csv
import json
import time
import requests

# ── 설정 ──────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyC3wMF6qMf0NQnk01iYMQ_Y1305NZuQA_E"
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

INPUT_CSV = "샘플300_정규식.csv"       # 정규식 분류기가 만든 샘플
OUTPUT_CSV = "샘플300_gemini.csv"      # Gemini 분류 결과
COMPARE_CSV = "비교결과.csv"           # 정규식 vs Gemini 비교

BATCH_SIZE = 5    # 한번에 몇 개씩 보낼지 (토큰 절약)
SLEEP_SEC = 8     # API 호출 간 대기 (무료 tier rate limit 대응)
MAX_RETRIES = 5   # 429 에러 시 최대 재시도 횟수
# ─────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════
# 1. 프롬프트 설계
# ══════════════════════════════════════════════════════

SYSTEM_PROMPT = """당신은 한국 법학 전문가입니다. 김도균 교수의 법규범 이론에 따라 법조항을 분류합니다.

## 분류 기준

### 규칙 (확정적 법규범, legal rules)
- 구성요건과 법률효과가 비교적 명확하게 확정되어 있는 법규범
- 효력 발생 방식이 '전부 아니면 무'(all-or-nothing)
- 구성요건 충족 시 반드시 법률효과 발생, 미충족 시 불발생
- 예: "~하는 경우에는 ~하여야 한다", "~한 자는 ~에 처한다"
- 구체적 수치, 기한, 절차, 자격요건이 포함된 조항
- "~할 수 있다" (재량권 부여이나 법률효과가 특정되어 있으면 규칙)

### 원칙 (법원리, legal principles)  
- 구성요건이나 법률효과가 확정적이지 않은 법규범
- '가능한 한 최대한 실현되는 형식'(최적화 명령, optimization)
- 다양한 '정도'로 실현될 수 있는 성격
- 예: 기본권 규정, 신의성실 원칙, 비례의 원칙, 공평부담 원칙
- "~을 고려하여" (형량/재량 판단), "~을 존중하여야", "노력하여야"
- 추상적 가치나 이념을 담고 있는 규정 (정의, 공익, 인권, 민주 등)
- 국가의 시책 수립 책무, 기본이념 규정

### 해당없음
- 규범적 명령이 아닌 조항
- 정의 규정 ("~를 말한다", "~과 같다"), 목적 규정, 부칙
- 장/절 제목, 약칭 규정, 업무 분장, 삭제된 조항
- 단순 위임 ("필요한 사항은 대통령령으로 정한다")
- 적용 범위만 규정하는 조항

## 출력 형식
각 조항에 대해 반드시 아래 JSON 배열 형식으로만 답하세요. 설명 없이 JSON만 출력하세요.
[
  {"id": 1, "분류": "규칙", "근거": "조건부 의무 부과"},
  {"id": 2, "분류": "원칙", "근거": "추상적 가치 실현 요청"},
  ...
]
"""


# ══════════════════════════════════════════════════════
# 2. Gemini API 호출
# ══════════════════════════════════════════════════════

def call_gemini(prompt):
    """Gemini API 호출 (429 자동 재시도)"""
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 4096,
        }
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(GEMINI_URL, json=payload, timeout=60)

            if resp.status_code == 429:
                wait = 10 * (attempt + 1)  # 10초, 20초, 30초... 점점 늘림
                print(f"    ⏳ Rate limit, {wait}초 대기 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text

        except requests.exceptions.HTTPError as e:
            if "429" in str(e):
                wait = 10 * (attempt + 1)
                print(f"    ⏳ Rate limit, {wait}초 대기 후 재시도 ({attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            print(f"  ❌ API 에러: {e}")
            return None
        except Exception as e:
            print(f"  ❌ 에러: {e}")
            return None

    print(f"  ❌ {MAX_RETRIES}회 재시도 후에도 실패")
    return None


def parse_gemini_response(text):
    """Gemini 응답에서 JSON 파싱"""
    if not text:
        return []

    # JSON 블록 추출 (```json ... ``` 형태 대응)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        results = json.loads(text)
        return results
    except json.JSONDecodeError:
        # 부분 파싱 시도
        try:
            # 첫 번째 [ 부터 마지막 ] 까지
            start = text.index("[")
            end = text.rindex("]") + 1
            results = json.loads(text[start:end])
            return results
        except:
            print(f"  ⚠️ JSON 파싱 실패: {text[:200]}")
            return []


# ══════════════════════════════════════════════════════
# 3. 배치 분류
# ══════════════════════════════════════════════════════

def classify_batch(items):
    """여러 조항을 한 번에 분류"""
    prompt_lines = ["다음 법조항들을 각각 규칙/원칙/해당없음으로 분류하세요.\n"]

    for i, item in enumerate(items):
        text = item["분류텍스트"][:300]  # 토큰 절약
        law = item["법령명"]
        title = item.get("조문제목", "")
        prompt_lines.append(f"[{i+1}] 법령: {law} | 조문제목: {title}")
        prompt_lines.append(f"    내용: {text}")
        prompt_lines.append("")

    prompt = "\n".join(prompt_lines)
    response_text = call_gemini(prompt)
    results = parse_gemini_response(response_text)

    return results


# ══════════════════════════════════════════════════════
# 4. 메인 실행
# ══════════════════════════════════════════════════════

def main():
    # 샘플 로드
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        samples = list(reader)

    print(f"샘플 {len(samples)}건 로드 완료")
    print(f"배치 크기: {BATCH_SIZE}, 예상 API 호출: {len(samples) // BATCH_SIZE + 1}회\n")

    # Gemini 분류 결과 저장용
    gemini_results = {}  # index -> {"분류": ..., "근거": ...}

    # 배치 처리
    for batch_start in range(0, len(samples), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(samples))
        batch = samples[batch_start:batch_end]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(samples) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"[배치 {batch_num}/{total_batches}] {batch_start+1}~{batch_end}번 처리중...")

        results = classify_batch(batch)

        if results:
            for r in results:
                idx = batch_start + r.get("id", 1) - 1
                if 0 <= idx < len(samples):
                    label = r.get("분류", "").strip()
                    # 분류값 정규화
                    if label in ["규칙", "원칙", "해당없음"]:
                        gemini_results[idx] = {
                            "gemini_분류": label,
                            "gemini_근거": r.get("근거", "")
                        }
                    else:
                        gemini_results[idx] = {
                            "gemini_분류": "분류오류",
                            "gemini_근거": f"원본:{label}"
                        }

            matched = sum(1 for r in results if r.get("id"))
            print(f"  ✅ {matched}건 분류 완료")
        else:
            print(f"  ❌ 배치 실패, 개별 재시도...")
            # 개별 재시도
            for j, item in enumerate(batch):
                idx = batch_start + j
                single_result = classify_batch([item])
                if single_result:
                    r = single_result[0]
                    label = r.get("분류", "").strip()
                    if label in ["규칙", "원칙", "해당없음"]:
                        gemini_results[idx] = {
                            "gemini_분류": label,
                            "gemini_근거": r.get("근거", "")
                        }
                time.sleep(SLEEP_SEC)

        time.sleep(SLEEP_SEC)

    # 결과 합치기 + 비교
    print(f"\n분류 완료: {len(gemini_results)}건 / {len(samples)}건")

    fieldnames = [
        "법령명", "조문번호", "조문제목", "분류텍스트",
        "정규식_분류", "정규식_근거",
        "gemini_분류", "gemini_근거",
        "일치여부"
    ]

    rows_out = []
    match_count = 0
    from collections import Counter
    gemini_counter = Counter()
    confusion = Counter()  # (정규식, gemini) 쌍

    for i, sample in enumerate(samples):
        gem = gemini_results.get(i, {"gemini_분류": "미분류", "gemini_근거": ""})
        regex_label = sample["분류결과"]
        gemini_label = gem["gemini_분류"]

        is_match = "O" if regex_label == gemini_label else "X"
        if regex_label == gemini_label:
            match_count += 1

        gemini_counter[gemini_label] += 1
        confusion[(regex_label, gemini_label)] += 1

        rows_out.append({
            "법령명": sample["법령명"],
            "조문번호": sample["조문번호"],
            "조문제목": sample["조문제목"],
            "분류텍스트": sample["분류텍스트"],
            "정규식_분류": regex_label,
            "정규식_근거": sample["매칭근거"],
            "gemini_분류": gemini_label,
            "gemini_근거": gem["gemini_근거"],
            "일치여부": is_match,
        })

    # 비교 결과 저장
    with open(COMPARE_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    # Gemini 단독 결과도 저장
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    # 결과 출력
    print(f"\n{'='*50}")
    print(f"비교 결과 요약")
    print(f"{'='*50}")
    print(f"\n전체 일치율: {match_count}/{len(samples)} ({match_count/len(samples)*100:.1f}%)")

    print(f"\nGemini 분류 분포:")
    for label, count in gemini_counter.most_common():
        print(f"  {label}: {count}건 ({count/len(samples)*100:.1f}%)")

    print(f"\n정규식 → Gemini 변환 매트릭스:")
    print(f"  {'':>12} | {'Gemini→규칙':>12} {'Gemini→원칙':>12} {'Gemini→해당없음':>14}")
    print(f"  {'-'*58}")
    for regex_label in ["규칙", "원칙", "해당없음"]:
        r_count = sum(1 for s in samples if s["분류결과"] == regex_label)
        if r_count == 0:
            continue
        vals = []
        for gem_label in ["규칙", "원칙", "해당없음"]:
            c = confusion.get((regex_label, gem_label), 0)
            vals.append(f"{c:>12}")
        print(f"  정규식_{regex_label:>4} | {''.join(vals)}")

    print(f"\n불일치 사례 (최대 10건):")
    mismatches = [r for r in rows_out if r["일치여부"] == "X"]
    for r in mismatches[:10]:
        print(f"  정규식:{r['정규식_분류']} → Gemini:{r['gemini_분류']}")
        print(f"    텍스트: {r['분류텍스트'][:100]}")
        print(f"    Gemini근거: {r['gemini_근거']}")
        print()

    print(f"\n저장 완료: {COMPARE_CSV}")


if __name__ == "__main__":
    main()
