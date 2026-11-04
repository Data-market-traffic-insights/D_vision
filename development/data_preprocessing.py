from pathlib import Path
import unicodedata
import pandas as pd
import numpy as np


# =====================================================
# 1. 폴더 경로 설정
# =====================================================

BASE_DIR = Path(__file__).resolve().parent

# 원본 데이터가 저장된 폴더
SOURCE_DIR = BASE_DIR.parent / "프로젝트 구성요소"

# 전처리 데이터 저장 폴더
DATA_DIR = BASE_DIR / "data"

# 분석 결과 저장 폴더
RESULT_DIR = BASE_DIR / "results"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

print("프로젝트 경로:", BASE_DIR)
print("원본 데이터 경로:", SOURCE_DIR)


# =====================================================
# 2. 대전광역시 상가정보 CSV 자동 검색
# =====================================================

if not SOURCE_DIR.exists():
    raise FileNotFoundError(
        f"원본 데이터 폴더를 찾을 수 없습니다: {SOURCE_DIR}"
    )

csv_files = list(SOURCE_DIR.rglob("*.csv"))

# 한글 파일명을 NFC 방식으로 통일하는 함수
def normalize(text):
    return unicodedata.normalize("NFC", str(text))


# 대전광역시 상가정보 파일 검색
daejeon_files = [
    file for file in csv_files
    if "대전" in normalize(file.name)
    and "상가" in normalize(file.name)
]

if not daejeon_files:
    print("\n발견된 CSV 파일:")

    for file in csv_files:
        print(normalize(file.name))

    raise FileNotFoundError(
        "대전광역시 상가정보 CSV를 찾을 수 없습니다."
    )

csv_path = daejeon_files[0]

print("\n선택된 대전 상가정보 파일:")
print(normalize(csv_path.name))

# =====================================================
# 3. CSV 파일 불러오기
# =====================================================

df = None

for encoding in ["utf-8-sig", "cp949", "euc-kr"]:
    try:
        df = pd.read_csv(
            csv_path,
            encoding=encoding,
            low_memory=False
        )

        print("\nCSV 인코딩:", encoding)
        break

    except UnicodeDecodeError:
        continue

if df is None:
    raise ValueError("CSV 파일을 읽을 수 없습니다.")

print("\n원본 데이터 크기:", df.shape)
print("\n컬럼 목록:")
print(df.columns.tolist())


# =====================================================
# 4. 대전광역시 데이터만 추출
# =====================================================

if "시도명" in df.columns:
    df = df[
        df["시도명"] == "대전광역시"
    ].copy()

print("\n대전광역시 전체 상가 수:", len(df))


# =====================================================
# 5. 필요한 컬럼 확인
# =====================================================

required_columns = [
    "상호명",
    "시군구명",
    "행정동명",
    "상권업종대분류명",
    "상권업종중분류명",
    "경도",
    "위도"
]

missing_columns = [
    col for col in required_columns
    if col not in df.columns
]

if missing_columns:
    raise ValueError(
        f"필수 컬럼이 없습니다: {missing_columns}"
    )


# =====================================================
# 6. 결측치 확인 및 제거
# =====================================================

print("\n결측치 확인:")
print(df[required_columns].isnull().sum())

# 분석에 필수적인 데이터가 없는 행 제거
df = df.dropna(
    subset=[
        "시군구명",
        "행정동명",
        "상권업종대분류명"
    ]
).copy()

# 경도와 위도를 숫자형으로 변환
df["경도"] = pd.to_numeric(
    df["경도"],
    errors="coerce"
)

df["위도"] = pd.to_numeric(
    df["위도"],
    errors="coerce"
)

print("\n전처리 후 상가 수:", len(df))


# =====================================================
# 7. 구별 상가 수 분석
# =====================================================

gu_counts = (
    df.groupby("시군구명")
    .size()
    .reset_index(name="상가수")
    .sort_values("상가수", ascending=False)
)

print("\n========== 구별 상가 수 ==========")
print(gu_counts.to_string(index=False))


# =====================================================
# 8. 행정동별 상가 수 분석
# =====================================================

dong_counts = (
    df.groupby(
        ["시군구명", "행정동명"]
    )
    .size()
    .reset_index(name="상가수")
    .sort_values("상가수", ascending=False)
)

print("\n========== 상가 수 상위 10개 행정동 ==========")
print(dong_counts.head(10).to_string(index=False))


# =====================================================
# 9. 업종별 상가 수 분석
# =====================================================

industry_counts = (
    df.groupby("상권업종대분류명")
    .size()
    .reset_index(name="상가수")
    .sort_values("상가수", ascending=False)
)

print("\n========== 업종별 상가 수 ==========")
print(industry_counts.to_string(index=False))


# =====================================================
# 10. 행정동별 업종 구성 분석
# =====================================================

dong_industry = pd.crosstab(
    [
        df["시군구명"],
        df["행정동명"]
    ],
    df["상권업종대분류명"]
)

# 행정동별 전체 상가 수
dong_industry["전체상가수"] = dong_industry.sum(axis=1)

dong_industry = dong_industry.reset_index()

print("\n행정동별 업종 데이터:")
print(dong_industry.head())


# =====================================================
# 11. 머신러닝용 데이터 생성
# =====================================================

# 업종별 비율을 계산할 데이터
industry_columns = [
    col for col in dong_industry.columns
    if col not in [
        "시군구명",
        "행정동명",
        "전체상가수"
    ]
]

ml_data = dong_industry.copy()

# 업종별 상가 수를 전체 상가 수로 나누어 비율 계산
for col in industry_columns:
    ml_data[col + "_비율"] = (
        ml_data[col] / ml_data["전체상가수"]
    )

# 머신러닝에 사용할 비율 컬럼
ratio_columns = [
    col + "_비율"
    for col in industry_columns
]

# 최종 머신러닝 데이터
ml_features = ml_data[
    [
        "시군구명",
        "행정동명",
        "전체상가수"
    ] + ratio_columns
].copy()

print("\n========== 머신러닝 데이터 ==========")
print(ml_features.head())


# =====================================================
# 12. 업종 다양성 계산
# =====================================================

# Shannon Entropy를 이용한 업종 다양성 계산
ratios = ml_features[ratio_columns].to_numpy()

# log(0) 방지를 위해 0인 값 제외
entropy = -np.sum(
    np.where(
        ratios > 0,
        ratios * np.log(np.clip(ratios, 1e-12, None)),
        0
    ),
    axis=1
)

ml_features["업종다양성"] = entropy

print("\n업종 다양성 계산 완료")


# =====================================================
# 13. CSV 파일 저장
# =====================================================

df.to_csv(
    DATA_DIR / "daejeon_clean.csv",
    index=False,
    encoding="utf-8-sig"
)

gu_counts.to_csv(
    RESULT_DIR / "gu_counts.csv",
    index=False,
    encoding="utf-8-sig"
)

dong_counts.to_csv(
    RESULT_DIR / "dong_counts.csv",
    index=False,
    encoding="utf-8-sig"
)

industry_counts.to_csv(
    RESULT_DIR / "industry_counts.csv",
    index=False,
    encoding="utf-8-sig"
)

dong_industry.to_csv(
    RESULT_DIR / "dong_industry.csv",
    index=False,
    encoding="utf-8-sig"
)

ml_features.to_csv(
    DATA_DIR / "ml_features.csv",
    index=False,
    encoding="utf-8-sig"
)


# =====================================================
# 14. 전처리 완료
# =====================================================

print("\n======================================")
print("대전광역시 상권 데이터 전처리 완료!")
print("======================================")

print("\n생성된 파일:")

print("data/daejeon_clean.csv")
print("data/ml_features.csv")

print("results/gu_counts.csv")
print("results/dong_counts.csv")
print("results/industry_counts.csv")
print("results/dong_industry.csv")

print("\n총 상가 수:", len(df))
print("분석 대상 행정동 수:", len(ml_features))