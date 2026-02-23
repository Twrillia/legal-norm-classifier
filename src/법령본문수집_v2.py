# =====================================================
# 법령 본문 수집 스크립트 (로컬 실행용 - Cursor/VS Code)
# 국가법령정보센터 Open API → 조문 단위 CSV 저장
# ✅ 이어하기 기능: 이미 수집한 법령은 자동 스킵
# =====================================================

import csv
import os
import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# ── 설정 ──────────────────────────────────────────────
OC_KEY = "tlswofydzld"
INPUT_CSV = "법령목록.csv"
OUTPUT_DIR = "법령별csv저장"
LOG_FILE = "수집로그.txt"         # 성공/실패 로그 기록
SLEEP_SEC = 1                     # API 호출 간 대기 시간(초)
RETRY_FAILED = False              # True로 바꾸면 이전 실패 법령도 재시도
# ─────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── 이어하기: 이미 수집 완료된 법령 확인 ──────────────────

def get_completed_msts():
    """OUTPUT_DIR에 이미 저장된 CSV 파일명으로부터 완료 목록 생성"""
    completed = set()
    if os.path.exists(OUTPUT_DIR):
        for fname in os.listdir(OUTPUT_DIR):
            if fname.endswith(".csv"):
                completed.add(fname.replace(".csv", ""))
    return completed


def get_failed_msts():
    """로그 파일에서 실패한 MST 목록 읽기"""
    failed = set()
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "❌" in line and "MST=" in line:
                    mst = line.split("MST=")[1].split("]")[0].strip()
                    failed.add(mst)
    return failed


def log(message):
    """콘솔 + 로그 파일 동시 기록"""
    print(message)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")


# ── 유틸 함수 ─────────────────────────────────────────

def remove_tag(text):
    """HTML 태그 제거"""
    if text is None:
        return ""
    return re.sub(r"<.*?>", "", str(text)).strip()


def get_text(element, tag):
    """XML 엘리먼트에서 태그 텍스트 추출 (None 안전)"""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def safe_filename(name):
    """파일명에 쓸 수 없는 문자 제거"""
    return re.sub(r'[\\/*?:"<>|]', "", name)


# ── XML 파싱 ──────────────────────────────────────────

def parse_law_xml(xml_text, law_name):
    """XML 응답을 파싱하여 조문 단위 행 리스트 반환"""
    rows = []
    root = ET.fromstring(xml_text)

    for 조문 in root.iter("조문단위"):
        조문정보 = {
            "법령명": law_name,
            "조문번호": get_text(조문, "조문번호"),
            "조문제목": remove_tag(get_text(조문, "조문제목")),
            "조문내용": remove_tag(get_text(조문, "조문내용")),
            "조문시행일자": get_text(조문, "조문시행일자"),
            "조문변경여부": get_text(조문, "조문변경여부"),
        }

        항_list = list(조문.iter("항"))

        if not 항_list:
            rows.append({
                **조문정보,
                "항내용": "", "호번호": "", "호내용": "", "목내용": ""
            })
            continue

        for 항 in 항_list:
            항내용 = remove_tag(get_text(항, "항내용"))
            호_list = list(항.iter("호"))

            if not 호_list:
                rows.append({
                    **조문정보,
                    "항내용": 항내용,
                    "호번호": "", "호내용": "", "목내용": ""
                })
                continue

            for 호 in 호_list:
                호번호 = get_text(호, "호번호")
                호내용 = remove_tag(get_text(호, "호내용"))
                목_list = list(호.iter("목"))

                if not 목_list:
                    rows.append({
                        **조문정보,
                        "항내용": 항내용,
                        "호번호": 호번호,
                        "호내용": 호내용,
                        "목내용": ""
                    })
                    continue

                for 목 in 목_list:
                    rows.append({
                        **조문정보,
                        "항내용": 항내용,
                        "호번호": 호번호,
                        "호내용": 호내용,
                        "목내용": remove_tag(get_text(목, "목내용"))
                    })

    return rows


# ── CSV 저장 ──────────────────────────────────────────

def save_csv(rows, law_name):
    """행 리스트를 CSV로 저장"""
    if not rows:
        return
    filepath = os.path.join(OUTPUT_DIR, f"{safe_filename(law_name)}.csv")

    fieldnames = [
        "법령명", "조문번호", "조문제목", "조문내용", "조문시행일자",
        "조문변경여부", "항내용", "호번호", "호내용", "목내용"
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


# ── 메인 실행 ─────────────────────────────────────────

def main():
    # 법령 목록 로드 (첫 줄 메타 정보 스킵)
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()  # "총5557건" 스킵
        reader = csv.DictReader(f)
        law_list = list(reader)

    # 이미 완료된 법령 확인
    completed = get_completed_msts()
    failed = get_failed_msts()

    # 스킵 대상 결정
    skip_set = set()
    for row in law_list:
        name = safe_filename(row["법령명"])
        if name in completed:
            if not RETRY_FAILED:
                skip_set.add(row["법령MST"])
            elif row["법령MST"] not in failed:
                skip_set.add(row["법령MST"])

    todo = [r for r in law_list if r["법령MST"] not in skip_set]

    log(f"총 {len(law_list)}개 법령 중 {len(completed)}개 수집 완료 → {len(todo)}개 남음")
    log(f"{'='*50}\n")

    success_count = 0
    fail_count = 0

    for i, row in enumerate(todo):
        mst = row["법령MST"]
        law_name = row["법령명"]

        try:
            url = (
                f"https://www.law.go.kr/DRF/lawService.do"
                f"?OC={OC_KEY}&target=law&MST={mst}&type=XML"
            )
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()

            # API 에러 응답 체크 (XML인데 본문이 에러 메시지인 경우)
            if "<조문단위>" not in resp.text and "<법령" not in resp.text:
                raise ValueError(f"API 응답에 법령 데이터 없음: {resp.text[:200]}")

            rows = parse_law_xml(resp.text, law_name)
            save_csv(rows, law_name)

            success_count += 1
            log(f"[{i+1}/{len(todo)}] ✅ {law_name} ({len(rows)}행) [MST={mst}]")

        except Exception as e:
            fail_count += 1
            log(f"[{i+1}/{len(todo)}] ❌ {law_name} - {e} [MST={mst}]")
            continue

        time.sleep(SLEEP_SEC)

    # 결과 요약
    log(f"\n{'='*50}")
    log(f"이번 실행: {success_count}개 성공 / {fail_count}개 실패")
    log(f"누적 완료: {len(get_completed_msts())}개 / 전체 {len(law_list)}개")
    log(f"저장 위치: {OUTPUT_DIR}/")

    if fail_count > 0:
        log(f"\n💡 실패한 법령 재시도: RETRY_FAILED = True 로 바꾸고 다시 실행")


if __name__ == "__main__":
    main()
