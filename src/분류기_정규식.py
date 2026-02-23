# =====================================================
# 법조항 분류기 (정규식 기반)
# 김도균 교수 이론: 확정적 법규범(규칙) vs 법원리(원칙) vs 해당없음
# 분류 단위: 항 (항내용 없으면 조문내용 사용)
# =====================================================

import csv
import os
import re
import random
from collections import Counter

# ── 설정 ──────────────────────────────────────────────
INPUT_DIR = "법령별csv저장"
OUTPUT_CSV = "분류결과_정규식.csv"
SAMPLE_CSV = "샘플300_정규식.csv"
SAMPLE_SIZE = 300
# ─────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════
# 1. 분류 규칙 정의
# ══════════════════════════════════════════════════════

# --- 해당없음 패턴 (우선 판별) ---
NONE_PATTERNS = {
    "장절관제목": re.compile(r"^제\d+장\s|^제\d+절\s|^제\d+관\s"),
    "목적규정": re.compile(r"목적으로\s*한다\s*[.\)]?\s*$"),
    "정의규정": re.compile(r"(용어의\s*뜻|정의[)\s]|다음과\s*같다\s*[.\)]?\s*$)"),
    "정의말한다": re.compile(r"(을|를)\s*말한다\s*[.\)]?\s*$"),
    "기준과같다": re.compile(r"(기준은|요건은|서식은)\s*별표\s*\d+.*같다\s*[.\)]?\s*$"),
    "약칭규정": re.compile(r"이하\s*[\"「].*[\"」]\s*(이|라|라고)\s*(한다|약칭한다)"),
    "부칙": re.compile(r"^부\s*칙|^\(시행일\)|이\s*(영|법|규칙)은.*부터\s*시행한다"),
    "위임근거만": re.compile(r"(필요한\s*사항은|구체적[인]?\s*사항은).*(대통령령|총리령|부령|조례)(으로|에서)\s*(정한다|위임한다)\s*[.\)]?\s*$"),
    "업무분장": re.compile(r"(다음\s*사항을\s*분장|다음\s*사항에\s*관하여.*보좌|업무를\s*수행한다|업무를\s*관장)"),
    "업무나열": re.compile(r"^(제\d+조\()?.*다음\s*각\s*호의\s*업무"),
    "빈내용": re.compile(r"^\s*$"),
    "조문제목만": re.compile(r"^제\d+조의?\d*\(.*\)\s*$"),
    "삭제조항": re.compile(r"삭제\s*[<\[〈]?\s*\d{4}"),
    "적용범위만": re.compile(r"(적용한다|적용된다)\s*[.\)]?\s*$(?!.*하여야)"),
    "약칭지정": re.compile(r"(취급한다|담당한다)\s*[.\)]?\s*$"),
}

# --- 원칙 패턴 ---
PRINCIPLE_PATTERNS = {
    # === 추상적 가치/이념 지향 ===
    "최대한보장": re.compile(r"(최대한|가능한\s*한|충분히)\s*(보장|보호|존중|실현|반영|확보)"),
    "노력의무": re.compile(r"(노력하여야|노력해야|위하여\s*노력|증진에\s*노력|향상에\s*노력|증진을\s*위하여)"),
    "추상적존중": re.compile(r"(존엄|인권|기본권|자유|평등|정의|공정|공익|공공복리|민주)\s*(을|를|의|에|과|와|이)?\s*(보장|보호|존중|실현|증진|확보|옹호|수호)"),
    "이념선언": re.compile(r"(기본이념|기본원칙|기본정신|기본방향|이념에\s*따라|원칙에\s*따라)"),
    "선언적규정": re.compile(r"(권리를\s*가진다|자유를\s*가진다|존엄과\s*가치)"),

    # === 비례원칙/형량 ===
    "비례원칙": re.compile(r"(비례하여|비례의\s*원칙|과잉금지|최소침해|필요최소한|필요한\s*최소한)"),
    "신의성실": re.compile(r"(신의.*성실|신뢰.*보호|공평.*부담|형평)"),
    "일반조항": re.compile(r"(사회통념|사회상규|건전한\s*사회질서|선량한\s*풍속|공서양속)"),

    # === 재량/형량 판단 (NEW) ===
    "고려재량": re.compile(r"(을|를|등을|등의)\s*고려하여\s*(정하|산정|결정|판단|산출|조정)"),
    "적합성판단": re.compile(r"(적합하도록|적정하게|합리적으로|적절하게|균형있게|조화롭게|합목적적|적절한\s*조치|적정한\s*수준|합리적\s*수준)"),
    "종합적판단": re.compile(r"(종합적으로\s*(고려|판단|검토)|제반\s*사정.*고려|여러\s*사정.*참작)"),
    "추상적책무": re.compile(r"(국가는|지방자치단체는|정부는).*(시책을\s*수립|시책을\s*마련|종합적.*추진|적극적으로|방안을\s*강구|대책을\s*수립)"),

    # === 불확정 개념 (NEW) ===
    "정당한사유": re.compile(r"정당한\s*사유\s*(없이|없으면|가\s*없)"),
    "상당한판단": re.compile(r"(상당한\s*이유|상당한\s*기간|현저하게|현저히|중대한\s*사유|부득이한\s*사유)"),
    "필요인정": re.compile(r"필요하다고\s*(인정|판단)(하는|되는)\s*(경우|때)"),
    "공익판단": re.compile(r"(공익을\s*위하여|공공의\s*이익|국민경제|공익상\s*필요)"),

    # === 추상적 기준 위임 (NEW) ===
    "재량위임": re.compile(r"(적절한|적정한|합리적인|필요한)\s*(방법|조치|범위|기준)(으로|을|를)\s*(정하|취하|마련)"),
}

# --- 규칙 패턴 ---
RULE_PATTERNS = {
    # === 확정적 구성요건 + 법률효과 ===
    "조건부명령": re.compile(r"(하는\s*경우에는?|하는\s*때에는?|하였을\s*때에는?|한\s*경우에는?|한\s*때에는?).*(하여야\s*한다|해야\s*한다|한다\s*[.\)]|아니한다|못한다|아니\s*된다)"),
    "의무부과": re.compile(r"(하여야\s*한다|해야\s*한다|하지\s*못한다|아니\s*된다|금지한다|하여서는\s*아니\s*된다)\s*[.\)]?\s*$"),
    "권한부여": re.compile(r"(할\s*수\s*있다|요청할\s*수\s*있다|명할\s*수\s*있다|처분할\s*수\s*있다)\s*[.\)]?\s*$"),
    "구체적수치": re.compile(r"(\d+일\s*이내|\d+개월|\d+년\s*이내|\d+퍼센트|\d+분의\s*\d+|\d+만원|\d+원\s*이하)"),
    "벌칙": re.compile(r"(\d+년\s*이하의\s*징역|\d+만원\s*이하의\s*벌금|과태료|벌칙|과료|몰수)"),
    "절차규정": re.compile(r"(신청하여야|제출하여야|통보하여야|보고하여야|공고하여야|통지하여야|신고하여야)"),
    "자격요건": re.compile(r"(자격이\s*있다|자격을\s*갖|결격사유|임명한다|위촉한다|해임한다|해촉한다)"),
    "구성규정": re.compile(r"(\d+인\s*이내|\d+명\s*(이내|이상)|위원장\s*\d+인|구성한다|설치한다|둔다)\s*[.\)]?\s*$"),
    "기한규정": re.compile(r"(\d+일\s*(이내에|까지|전에|내에)|\d+개월\s*(이내|전)|\d+년\s*(이내|이상))"),
    "효과확정": re.compile(r"(취소하여야|취소할\s*수|무효로|효력을\s*잃|면제한다|감면한다|부과한다|징수한다)"),
    "준용규정": re.compile(r"(준용한다|적용한다)\s*[.\)]?\s*$"),

    # === 기본값에서 빠지던 확정적 패턴 (NEW) ===
    "의무갖춤": re.compile(r"(갖추어야\s*한다|갖추어야\s*한다|구비하여야)"),
    "간주규정": re.compile(r"(으로\s*본다|것으로\s*본다|간주한다)\s*[.\)]?\s*$"),
    "통지알림": re.compile(r"(알려야\s*한다|알려주어야|고지하여야|통지하여야)"),
    "지급교부": re.compile(r"(지급한다|교부한다|반환한다|환급한다)\s*[.\)]?\s*$"),
    "확인받음": re.compile(r"(확인받아야\s*한다|승인을\s*받아야|허가를\s*받아야|인가를\s*받아야)"),
    "정지정보": re.compile(r"(정지된다|중지된다|중단된다|소멸한다|소멸된다)\s*[.\)]?\s*$"),
    "확정명시": re.compile(r"(에\s*따른다|에\s*의한다|와\s*같다)\s*[.\)]?\s*$"),
    "금지위반": re.compile(r"(거부하지\s*못한다|거절하지\s*못한다|위반하여서는)"),
}


# ══════════════════════════════════════════════════════
# 2. 분류 함수
# ══════════════════════════════════════════════════════

def classify_provision(text, article_title=""):
    """
    법조항 텍스트를 규칙/원칙/해당없음으로 분류
    Returns: (분류결과, 매칭근거)
    """
    if not text or not text.strip():
        return "해당없음", "빈내용"

    combined = text.strip()

    # 1단계: 해당없음 판별 (최우선)
    for name, pattern in NONE_PATTERNS.items():
        if pattern.search(combined):
            return "해당없음", name

    # 조문제목으로 추가 필터링
    if article_title:
        title_lower = article_title.strip()
        if title_lower in ["목적", "정의", "약칭"]:
            return "해당없음", f"제목_{title_lower}"

    # 2단계: 원칙 판별
    principle_matches = []
    for name, pattern in PRINCIPLE_PATTERNS.items():
        if pattern.search(combined):
            principle_matches.append(name)

    # 3단계: 규칙 판별
    rule_matches = []
    for name, pattern in RULE_PATTERNS.items():
        if pattern.search(combined):
            rule_matches.append(name)

    # 4단계: 판정
    if principle_matches and not rule_matches:
        return "원칙", ",".join(principle_matches)
    elif rule_matches and not principle_matches:
        return "규칙", ",".join(rule_matches)
    elif principle_matches and rule_matches:
        # 둘 다 있으면: 원칙의 핵심 패턴이 있으면 원칙 우선
        core_principles = {"이념선언", "추상적존중", "선언적규정", "비례원칙",
                          "노력의무", "추상적책무", "최대한보장", "공익판단"}
        has_core = bool(set(principle_matches) & core_principles)

        if has_core:
            return "원칙", ",".join(principle_matches)
        else:
            # 재량/형량 패턴 + 규칙 패턴이면 규칙 (효과가 확정적이므로)
            return "규칙", ",".join(rule_matches)
    else:
        # 아무것도 매칭 안 되면 텍스트 길이와 구조로 추정
        if len(combined) < 20:
            return "해당없음", "짧은텍스트"
        return "규칙", "기본값_구조추정"


# ══════════════════════════════════════════════════════
# 3. 항 단위 텍스트 추출
# ══════════════════════════════════════════════════════

def get_classification_text(row):
    """분류에 사용할 텍스트 추출 (항 단위)"""
    hang = row.get("항내용", "").strip()
    jomun = row.get("조문내용", "").strip()

    if hang:
        return hang
    else:
        return jomun


def get_unique_provisions(rows):
    """
    항 단위로 고유한 조항 추출
    같은 조문+항 내에서 호/목으로 분리된 행은 하나로 합침
    """
    seen = set()
    unique = []

    for row in rows:
        text = get_classification_text(row)
        # 고유 키: 법령명 + 조문번호 + 항내용 앞 50자
        key = (row["법령명"], row["조문번호"], text[:50])
        if key not in seen:
            seen.add(key)
            unique.append(row)

    return unique


# ══════════════════════════════════════════════════════
# 4. 전체 법령 처리
# ══════════════════════════════════════════════════════

def process_all_laws():
    """모든 법령 CSV를 읽어서 항 단위로 분류"""
    all_results = []

    files = [f for f in os.listdir(INPUT_DIR) if f.endswith(".csv")]
    print(f"총 {len(files)}개 법령 파일 처리 시작\n")

    for i, fname in enumerate(files):
        filepath = os.path.join(INPUT_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter="\t")
                rows = list(reader)

            unique = get_unique_provisions(rows)

            for row in unique:
                text = get_classification_text(row)
                title = row.get("조문제목", "")
                label, reason = classify_provision(text, title)

                all_results.append({
                    "법령명": row["법령명"],
                    "조문번호": row["조문번호"],
                    "조문제목": title,
                    "분류텍스트": text[:200],  # 저장용 200자 제한
                    "분류결과": label,
                    "매칭근거": reason,
                })

        except Exception as e:
            print(f"  ⚠️ {fname} 처리 실패: {e}")
            continue

        if (i + 1) % 500 == 0:
            print(f"  [{i+1}/{len(files)}] 처리 중... (누적 {len(all_results)}건)")

    print(f"\n총 {len(all_results)}건 분류 완료")
    return all_results


def save_results(results, filepath):
    """분류 결과를 CSV로 저장"""
    fieldnames = ["법령명", "조문번호", "조문제목", "분류텍스트", "분류결과", "매칭근거"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def extract_sample(results, n=300):
    """분류 비율에 맞춰 층화 샘플링"""
    by_label = {}
    for r in results:
        label = r["분류결과"]
        by_label.setdefault(label, []).append(r)

    total = len(results)
    sample = []

    for label, items in by_label.items():
        ratio = len(items) / total
        k = max(1, round(n * ratio))
        k = min(k, len(items))
        sample.extend(random.sample(items, k))

    # 정확히 n개로 맞추기
    random.shuffle(sample)
    if len(sample) > n:
        sample = sample[:n]
    elif len(sample) < n:
        remaining = [r for r in results if r not in sample]
        sample.extend(random.sample(remaining, min(n - len(sample), len(remaining))))

    return sample


# ══════════════════════════════════════════════════════
# 5. 메인 실행
# ══════════════════════════════════════════════════════

def main():
    # 전체 분류
    results = process_all_laws()

    # 결과 저장
    save_results(results, OUTPUT_CSV)
    print(f"\n전체 결과 저장: {OUTPUT_CSV}")

    # 분포 출력
    counter = Counter(r["분류결과"] for r in results)
    print(f"\n분류 분포:")
    for label, count in counter.most_common():
        pct = count / len(results) * 100
        print(f"  {label}: {count}건 ({pct:.1f}%)")

    # 샘플 추출
    sample = extract_sample(results, SAMPLE_SIZE)
    save_results(sample, SAMPLE_CSV)
    print(f"\n샘플 {len(sample)}건 저장: {SAMPLE_CSV}")

    # 샘플 분포
    sample_counter = Counter(r["분류결과"] for r in sample)
    print(f"샘플 분포:")
    for label, count in sample_counter.most_common():
        print(f"  {label}: {count}건")


if __name__ == "__main__":
    main()
