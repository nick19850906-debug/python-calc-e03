#!/usr/bin/env python3
# ==============================================================================
# [프로젝트 명] Mini NPU Simulator (AI 계산기 시뮬레이터)
# [파일 설명] NPU의 핵심 연산인 MAC(Multiply-Accumulate) 및 2D 패턴 유사도 판별 콘솔 앱
# [설계 원칙] 외부 라이브러리(NumPy 등) 배제, 순수 Python 기반 알고리즘 및 인과관계 제어
# ==============================================================================

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# [전역 상수 정의 및 설계 의도]
# ==============================================================================

# [의도] IEEE 754 부동소수점 연산에서 발생하는 미세 오차(예: 0.1 + 0.2 != 0.3)를 보정하기 위한 허용오차 임계값
# [인과관계] 두 필터의 MAC 점수 차이(|Score_A - Score_B|)가 이 값보다 작으면 컴퓨터 오차로 인한 왜곡을 방지하고
#            실질적인 수치적 동점으로 판단하여 "UNDECIDED(판정 불가)"를 반환하도록 유도함.
EPSILON = 1e-9

# [의도] 벤치마크 시 단 1회 측정의 노이즈(OS 스케줄링, 캐시 상태 등)를 상쇄하고 신뢰성 있는 평균 시간을 얻기 위한 반복 횟수
DEFAULT_REPEAT_COUNT = 10


# ==============================================================================
# [1. 데이터 전처리 및 라벨 정규화 모듈]
# ==============================================================================

def normalize_label(label: Any) -> str:
    """
    [함수 의도]
    - 입력된 다양한 형식의 라벨 문자열('+', 'x', 'cross', 'Cross' 등)을 내부 표준 라벨('Cross', 'X')로 정규화(표준화)합니다.

    [인과관계 흐름]
    - [입력] data.json 또는 사용자가 지정한 임의의 라벨 데이터 (None, 문자열 등)
    - [처리] 공백 제거 및 대소문자/특수문자 패턴 매핑
    - [출력] 일관된 표준 라벨 문자열("Cross", "X", 또는 원본 문자열)
    - [영향] 판정 비교식(decision == expected_label)에서 표기 차이로 인한 오판정 버그를 원천 차단함.
    """
    # 1. 방어적 예외 처리: 라벨이 전달되지 않은 경우 UNKNOWN 반환
    if label is None:
        return "UNKNOWN"
    
    # 2. 앞뒤 공백 제거 및 문자열 변환
    s = str(label).strip()
    
    # 3. 십자가(Cross) 형태의 다양한 표현을 'Cross'로 일원화
    if s in ("+", "cross", "Cross", "CROSS"):
        return "Cross"
    
    # 4. 엑스(X) 형태의 다양한 표현을 'X'로 일원화
    if s in ("x", "X"):
        return "X"
    
    # 5. 매핑되지 않은 기타 문자열은 원본 유지
    return s


# ==============================================================================
# [2. NPU 핵심 MAC(Multiply-Accumulate) 연산 엔진]
# ==============================================================================

def calculate_mac_2d(pattern: List[List[float]], filter_grid: List[List[float]]) -> float:
    """
    [함수 의도]
    - 2차원 격자(행렬) 형태의 패턴과 필터 커널 간의 원소별 곱셈 및 누적 덧셈(MAC)을 수행합니다.
    - 외부 라이브러리(NumPy) 없이 하드웨어 NPU의 곱셈-누적 유닛 동작을 순수 2중 루프로 재현합니다.

    [수학적 수식]
    - Score = Σ (Pattern[r][c] * Filter[r][c]) for r in [0..N-1], c in [0..N-1]

    [인과관계 흐름]
    - [입력] N x N 크기의 2차원 float 행렬 2개 (입력 패턴, 가중치 필터)
    - [처리] 2중 for문을 순회하며 동일 좌표의 (패턴 원소 * 필터 원소)를 계산하여 total_score에 누적
    - [출력] 최종 합산된 단일 float 점수 (유사도 수치)
    - [복잡도] N개의 행과 N개의 열을 모두 탐색하므로 정확히 O(N^2) 시간 복잡도를 가짐.
    """
    # [명령어 의도] 누적기(Accumulator) 레지스터 역할을 할 변수를 0.0으로 초기화
    total_score = 0.0
    
    # [인과관계] 2차원 리스트의 행(row) 개수 및 첫 번째 행의 열(col) 개수를 파악하여 루프 범위 결정
    rows = len(pattern)
    cols = len(pattern[0]) if rows > 0 else 0
    
    # [루프 인과관계] 바깥 루프는 각 행(r)을, 안쪽 루프는 각 열(c)을 순차 탐색 (총 rows * cols 회 반복)
    for r in range(rows):
        for c in range(cols):
            # [명령어 의도] Multiply(곱셈: pattern[r][c] * filter_grid[r][c]) 후 Accumulate(누적 덧셈: +=)
            total_score += pattern[r][c] * filter_grid[r][c]
            
    return total_score


def calculate_mac_1d(pattern_1d: List[float], filter_1d: List[float]) -> float:
    """
    [함수 의도]
    - (보너스 과제) 1차원 평탄화(Flattened)된 연속 메모리 배열을 대상으로 단일 루프 MAC 연산을 수행합니다.
    - 2차원 리스트 대비 포인터 역참조 단계를 줄여 캐시 지역성(Spatial Locality) 최적화 효과를 검증합니다.

    [인과관계 흐름]
    - [입력] 길이 N^2의 1차원 선형 float 리스트 2개
    - [처리] 단일 for 루프로 연속 인덱스 i를 순회하며 곱셈-누적 수행
    - [출력] 최종 MAC 점수 (2D 연산 결과와 수학적으로 완전히 동일함)
    """
    total_score = 0.0
    n = len(pattern_1d)
    
    # [명령어 의도] 단일 인덱싱(pattern_1d[i])으로 메모리 연속 접근을 유도하여 2단계 참조 오버헤드 제거
    for i in range(n):
        total_score += pattern_1d[i] * filter_1d[i]
        
    return total_score


def flatten_2d_to_1d(grid_2d: List[List[float]]) -> List[float]:
    """
    [함수 의도]
    - N x N 크기의 2차원 배열을 길이 N^2의 1차원 선형 리스트로 고속 변환합니다.

    [인과관계 흐름]
    - [입력] 2차원 리스트 (List[List[float]])
    - [처리] 이중 컴프리헨션을 통해 행 단위로 원소를 순차 전개
    - [출력] 1차원 리스트 (List[float])
    """
    # [명령어 의도] 행(row)을 순회하고 각 행의 원소(val)를 순차 추출하여 단일 리스트로 병합
    return [val for row in grid_2d for val in row]


# ==============================================================================
# [3. 판정 엔진 및 성능 벤치마크 모듈]
# ==============================================================================

def decide_prediction(
    score_a: float,
    score_b: float,
    label_a: str = "A",
    label_b: str = "B",
    epsilon: float = EPSILON
) -> Tuple[str, str]:
    """
    [함수 의도]
    - 두 필터(A, B)가 획득한 MAC 점수를 비교하여 최종 판정 라벨 및 상세 사유를 도출합니다.
    - 부동소수점 오차로 인한 오판정을 방지하기 위해 EPSILON 임계값 기반의 비교 정책을 적용합니다.

    [인과관계 흐름]
    - [입력] 점수 A, 점수 B, 각 라벨 이름, 허용오차(epsilon)
    - [비교 분기]
      1) abs(score_a - score_b) < epsilon -> 실질적 동점으로 간주하여 "UNDECIDED" 판정
      2) score_a > score_b -> 라벨 A 승리
      3) score_b > score_a -> 라벨 B 승리
    - [출력] (판정 라벨 문자열, 판정 근거 설명 문자열)
    """
    # [명령어 의도] 두 부동소수점 점수 사이의 절대 거리(차이)를 계산
    diff = abs(score_a - score_b)
    
    # [분기 1: 동점 처리] 차이가 허용오차 미만인 경우
    if diff < epsilon:
        return "UNDECIDED", f"동점 (|{label_a}-{label_b}| = {diff:.2e} < {epsilon})"
    
    # [분기 2: A 우세]
    elif score_a > score_b:
        return label_a, f"{label_a} 점수 우세 (차이: {diff:.4f})"
    
    # [분기 3: B 우세]
    else:
        return label_b, f"{label_b} 점수 우세 (차이: {diff:.4f})"


def benchmark_mac_2d(
    pattern: List[List[float]],
    filter_grid: List[List[float]],
    iterations: int = DEFAULT_REPEAT_COUNT
) -> float:
    """
    [함수 의도]
    - 순수 2D MAC 연산 구간(I/O 및 파일 로드 제외)의 소요 시간(ms)을 고정밀 타이머로 측정합니다.

    [인과관계 흐름]
    - [선택 이유: time.perf_counter] time.time()은 시스템 시간 변경에 영향을 받지만,
      perf_counter는 CPU 클럭 기반의 단조 증가(Monotonic) 타이머로 나노초 단위 측정이 가능함.
    - [처리] iterations회 반복 실행 후 전체 소요 시간을 구해 1회당 평균 ms로 환산.
    """
    start_time = time.perf_counter()
    for _ in range(iterations):
        calculate_mac_2d(pattern, filter_grid)
    end_time = time.perf_counter()
    
    # [단위 변환] 초(second) -> 밀리초(millisecond, * 1000.0)
    total_elapsed_ms = (end_time - start_time) * 1000.0
    return total_elapsed_ms / iterations


def benchmark_mac_1d(
    pattern_1d: List[float],
    filter_1d: List[float],
    iterations: int = DEFAULT_REPEAT_COUNT
) -> float:
    """
    [함수 의도]
    - 1차원 평탄화 배열 대상의 순수 MAC 연산 소요 시간(ms)을 고정밀 측정합니다.
    """
    start_time = time.perf_counter()
    for _ in range(iterations):
        calculate_mac_1d(pattern_1d, filter_1d)
    end_time = time.perf_counter()
    
    total_elapsed_ms = (end_time - start_time) * 1000.0
    return total_elapsed_ms / iterations


# ==============================================================================
# [4. 대화형 입력 처리 및 패턴 생성 유틸리티]
# ==============================================================================

def input_grid_interactive(grid_name: str, size: int = 3) -> List[List[float]]:
    """
    [함수 의도]
    - 콘솔로부터 사용자가 한 줄씩 입력하는 size x size 숫자 격자를 안전하게 파싱합니다.
    - 사용자의 오타(문자 입력, 개수 불일치, 빈 줄 등)에 대해 프로그램이 중단되지 않고 재입력을 유도합니다.

    [인과관계 흐름]
    - [입력 루프] size개의 행이 정상적으로 수집될 때까지 while True 반복
    - [검증 항목]
      1) 빈 줄 감지 -> 에러 안내 후 break -> 재입력
      2) 공백 분리 토큰 개수가 size와 다름 -> 에러 안내 후 break -> 재입력
      3) float 변환 불가(문자 등) -> ValueError 예외 포획 후 재입력
    - [출력] 완전히 검증된 size x size 크기의 float 2차원 리스트
    """
    print(f"\n{grid_name} ({size}줄 입력, 각 줄에 숫자 {size}개를 공백으로 구분)")
    while True:
        grid: List[List[float]] = []
        is_valid = True
        
        for row_idx in range(size):
            try:
                # [명령어 의도] 콘솔 입력을 받고 앞뒤 불필요한 공백 제거
                line = input(f"[{row_idx + 1}/{size} 행] > ").strip()
                
                # 검증 1: 빈 입력 처리
                if not line:
                    print(f"입력 오류: 빈 줄입니다. {size}개의 숫자를 공백으로 구분해 입력하세요.")
                    is_valid = False
                    break
                
                # 검증 2: 공백 기준으로 숫자 분리
                tokens = line.split()
                if len(tokens) != size:
                    print(f"입력 형식 오류: 각 줄에 {size}개의 숫자를 공백으로 구분해 입력하세요. (입력 개수: {len(tokens)})")
                    is_valid = False
                    break
                
                # 검증 3: 문자열 토큰을 float 부동소수점 숫자로 변환
                row_vals = [float(token) for token in tokens]
                grid.append(row_vals)
                
            except ValueError:
                # 숫자가 아닌 문자나 특수기호 입력 시 방어
                print("입력 형식 오류: 숫자(정수 또는 실수)만 입력 가능합니다.")
                is_valid = False
                break
        
        # [성공 판정] size개의 행이 모두 정상 파싱된 경우 격자 반환
        if is_valid and len(grid) == size:
            return grid
        
        # 실패 시 안내 후 루프 재시작
        print(f"-> {grid_name} 입력을 처음부터 다시 시도합니다.")


def generate_pattern(size: int, pattern_type: str = "Cross") -> List[List[float]]:
    """
    [함수 의도]
    - (보너스 과제) 임의의 격자 크기 N에 대해 수학적으로 이상적인 Cross(십자가) 또는 X 대각선 패턴을 생성합니다.

    [인과관계 흐름]
    - [기본 초기화] 모든 원소가 0.0인 size x size 격자 생성
    - [Cross 모드] 중앙 인덱스 mid = size // 2를 기준으로 가로선(mid, i)과 세로선(i, mid)을 1.0으로 설정
    - [X 모드] 주대각선(i, i)과 부대각선(i, size - 1 - i)을 1.0으로 설정
    - [출력] 완성된 2차원 패턴 격자 반환
    """
    # 1. 0.0으로 채워진 N x N 2차원 리스트 생성
    grid = [[0.0 for _ in range(size)] for _ in range(size)]
    norm_type = normalize_label(pattern_type)
    
    if norm_type == "Cross":
        # 십자가 패턴: 정중앙 행과 정중앙 열을 1.0으로 설정
        mid = size // 2
        for i in range(size):
            grid[mid][i] = 1.0
            grid[i][mid] = 1.0
            
    elif norm_type == "X":
        # X 대각선 패턴: 좌상->우하 대각선 및 우상->좌하 대각선을 1.0으로 설정
        for i in range(size):
            grid[i][i] = 1.0
            grid[i][size - 1 - i] = 1.0
            
    return grid


# ==============================================================================
# [5. 주요 실행 모드 구현]
# ==============================================================================

def run_mode_1():
    """
    [모드 1 의도]
    - 사용자가 3x3 필터 2개(A, B)와 패턴 1개를 콘솔에서 직접 입력받아 MAC 점수를 산출하고
      승자 판정 및 연산 시간을 실시간으로 피드백합니다.
    """
    print("\n" + "=" * 50)
    print(" [모드 1] 사용자 입력 (3x3) ")
    print("=" * 50)
    print("3x3 크기의 필터 A, 필터 B, 그리고 패턴 데이터를 입력받습니다.")
    
    # 1. 필터 A, 필터 B 사용자 대화형 입력
    print("\n#----------------------------------------")
    print("# [1] 필터 입력")
    print("#----------------------------------------")
    filter_a = input_grid_interactive("필터 A", size=3)
    filter_b = input_grid_interactive("필터 B", size=3)
    
    # 2. 테스트 패턴 사용자 대화형 입력
    print("\n#----------------------------------------")
    print("# [2] 패턴 입력")
    print("#----------------------------------------")
    pattern = input_grid_interactive("패턴", size=3)
    
    # 3. MAC 점수 계산 실행
    score_a = calculate_mac_2d(pattern, filter_a)
    score_b = calculate_mac_2d(pattern, filter_b)
    
    # 4. 연산 성능 벤치마크 (10회 평균 ms)
    avg_time_a = benchmark_mac_2d(pattern, filter_a, iterations=10)
    avg_time_b = benchmark_mac_2d(pattern, filter_b, iterations=10)
    avg_time = (avg_time_a + avg_time_b) / 2.0
    
    # 5. Epsilon 기반 최종 판정 도출
    decision, reason = decide_prediction(score_a, score_b, label_a="A", label_b="B", epsilon=EPSILON)
    
    # 6. 결과 출력
    print("\n#----------------------------------------")
    print("# [3] MAC 결과")
    print("#----------------------------------------")
    print(f"A 점수: {score_a:.6f}")
    print(f"B 점수: {score_b:.6f}")
    print(f"연산 시간(평균/10회): {avg_time:.4f} ms")
    
    if decision == "UNDECIDED":
        print(f"판정: 판정 불가 (|A - B| < {EPSILON})")
    else:
        print(f"판정: {decision} ({reason})")
    print("#----------------------------------------\n")


def run_mode_2(json_filename: str = "data.json"):
    """
    [모드 2 의도]
    - data.json 파일로부터 5x5, 13x13, 25x25 크기의 필터와 패턴들을 일괄 로드하여
      스키마 유효성 검증, 라벨 정규화, MAC 점수 계산, PASS/FAIL 판정 및 종합 통계를 출력합니다.
    """
    print("\n" + "=" * 50)
    print(" [모드 2] data.json 분석 ")
    print("=" * 50)
    
    # [인과관계] 현재 작업 디렉터리와 스크립트 파일 위치를 모두 탐색하여 파일 로드 경로 안정성 확보
    target_path = json_filename
    if not os.path.exists(target_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(base_dir, json_filename)
        if os.path.exists(alt_path):
            target_path = alt_path
        else:
            print(f"오류: {json_filename} 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
            return

    # [JSON 파싱 및 예외 처리]
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"오류: JSON 파일 파싱 실패 - {e}")
        return
    except Exception as e:
        print(f"오류: 파일 읽기 중 예외 발생 - {e}")
        return

    filters_dict = data.get("filters", {})
    patterns_dict = data.get("patterns", {})
    
    # --------------------------------------------------------------------------
    # [1] 필터 로드 및 라벨 정규화
    # --------------------------------------------------------------------------
    print("\n#---------------------------------------")
    print("# [1] 필터 로드")
    print("#---------------------------------------")
    available_sizes = []
    normalized_filters: Dict[str, Dict[str, List[List[float]]]] = {}
    
    for size_key, f_data in filters_dict.items():
        f_cross = None
        f_x = None
        for k, grid in f_data.items():
            norm_k = normalize_label(k)
            if norm_k == "Cross":
                f_cross = grid
            elif norm_k == "X":
                f_x = grid
        
        # Cross와 X 필터가 모두 온전히 존재하는지 검증
        if f_cross is not None and f_x is not None:
            normalized_filters[size_key] = {"Cross": f_cross, "X": f_x}
            available_sizes.append(size_key)
            print(f"✓ {size_key:<7} 필터 로드 완료 (Cross, X)")
        else:
            print(f"⚠ {size_key:<7} 필터 구성 불완전 (Cross/X 누락)")

    # --------------------------------------------------------------------------
    # [2] 패턴 일괄 분석 (라벨 정규화, MAC 계산, 판정)
    # --------------------------------------------------------------------------
    print("\n#---------------------------------------")
    print("# [2] 패턴 분석 (라벨 정규화 및 판정)")
    print("#---------------------------------------")
    
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    failed_cases_log: List[Tuple[str, str]] = []
    
    benchmark_data: Dict[str, Tuple[List[List[float]], List[List[float]]]] = {}

    for pattern_key, p_info in patterns_dict.items():
        total_tests += 1
        print(f"--- {pattern_key} ---")
        
        # 패턴 키 검증 (예: size_5_1 -> parts[1] == '5')
        parts = pattern_key.split("_")
        if len(parts) < 3 or parts[0] != "size":
            fail_msg = f"패턴 키 형식 오류 (기대 형식: size_{{N}}_{{idx}}, 실제: {pattern_key})"
            print(f"FAIL: {fail_msg}")
            failed_tests += 1
            failed_cases_log.append((pattern_key, fail_msg))
            continue
        
        try:
            expected_n = int(parts[1])
        except ValueError:
            fail_msg = f"크기 N 파싱 실패 ({parts[1]})"
            print(f"FAIL: {fail_msg}")
            failed_tests += 1
            failed_cases_log.append((pattern_key, fail_msg))
            continue
        
        filter_size_key = f"size_{expected_n}"
        if filter_size_key not in normalized_filters:
            fail_msg = f"필터 누락 (필요 필터: {filter_size_key})"
            print(f"FAIL: {fail_msg}")
            failed_tests += 1
            failed_cases_log.append((pattern_key, fail_msg))
            continue
        
        input_grid = p_info.get("input")
        raw_expected = p_info.get("expected")
        expected_label = normalize_label(raw_expected)
        
        # 2차원 리스트 행/열 차원 정합성 검증
        if not isinstance(input_grid, list) or len(input_grid) != expected_n:
            actual_len = len(input_grid) if isinstance(input_grid, list) else "None"
            fail_msg = f"패턴 행 크기 불일치 (기대: {expected_n}, 실제: {actual_len})"
            print(f"FAIL: {fail_msg}")
            failed_tests += 1
            failed_cases_log.append((pattern_key, fail_msg))
            continue
        
        col_mismatch = False
        for r_idx, row in enumerate(input_grid):
            if not isinstance(row, list) or len(row) != expected_n:
                fail_msg = f"패턴 {r_idx}행 열 크기 불일치"
                print(f"FAIL: {fail_msg}")
                failed_tests += 1
                failed_cases_log.append((pattern_key, fail_msg))
                col_mismatch = True
                break
        if col_mismatch:
            continue
        
        # 필터 추출 및 벤치마크 샘플 등록
        cross_filter = normalized_filters[filter_size_key]["Cross"]
        x_filter = normalized_filters[filter_size_key]["X"]
        
        if filter_size_key not in benchmark_data:
            benchmark_data[filter_size_key] = (input_grid, cross_filter)
        
        # MAC 연산 수행
        score_cross = calculate_mac_2d(input_grid, cross_filter)
        score_x = calculate_mac_2d(input_grid, x_filter)
        
        # 판정 결과 산출
        decision, reason = decide_prediction(score_cross, score_x, label_a="Cross", label_b="X", epsilon=EPSILON)
        
        # PASS/FAIL 검증
        is_pass = (decision == expected_label)
        status_str = "PASS" if is_pass else "FAIL"
        
        if is_pass:
            passed_tests += 1
            extra_info = ""
        else:
            failed_tests += 1
            if decision == "UNDECIDED":
                extra_info = " (동점 규칙 적용)"
                failed_cases_log.append((pattern_key, f"동점(UNDECIDED) 판정 (|Cross-X| < {EPSILON}) - expected: {expected_label}"))
            else:
                extra_info = f" (판정 불일치: {reason})"
                failed_cases_log.append((pattern_key, f"판정 불일치 (판정: {decision}, expected: {expected_label})"))
        
        print(f"Cross 점수: {score_cross:.10f}")
        print(f"X     점수: {score_x:.10f}")
        print(f"판정: {decision:<9} | expected: {expected_label:<5} | {status_str}{extra_info}")

    # --------------------------------------------------------------------------
    # [3] 크기별 성능 분석 측정
    # --------------------------------------------------------------------------
    print("\n#---------------------------------------")
    print("# [3] 성능 분석 (평균 10회 반복 측정)")
    print("#---------------------------------------")
    print(f"{'크기':<10} {'평균 시간(ms)':<15} {'연산 횟수(N²)':<15}")
    print("-" * 42)
    
    test_sizes = [3, 5, 13, 25]
    for n in test_sizes:
        size_key = f"size_{n}"
        if size_key in benchmark_data:
            pat, flt = benchmark_data[size_key]
        else:
            # 3x3과 같이 데이터셋에 없는 크기는 자동 생성 패턴 활용
            pat = generate_pattern(n, "Cross")
            flt = generate_pattern(n, "Cross")
        
        avg_ms = benchmark_mac_2d(pat, flt, iterations=10)
        op_count = n * n
        print(f"{f'{n}×{n}':<10} {avg_ms:<15.5f} {op_count:<15}")

    # --------------------------------------------------------------------------
    # [4] 종합 결과 요약 리포트
    # --------------------------------------------------------------------------
    print("\n#---------------------------------------")
    print("# [4] 결과 요약")
    print("#---------------------------------------")
    print(f"총 테스트: {total_tests}개")
    print(f"통과: {passed_tests}개")
    print(f"실패: {failed_tests}개")
    
    if failed_tests > 0:
        print("\n실패 케이스 목록:")
        for case_id, reason_str in failed_cases_log:
            print(f"- {case_id}: {reason_str}")
    else:
        print("\n모든 케이스가 성공적으로 통과했습니다.")
    
    print("\n(상세 원인 분석 및 시간 복잡도 설명은 .doc/ 폴더의 문서들을 참조하세요.)")
    print("#---------------------------------------\n")


def run_mode_bonus_optimization(json_filename: str = "data.json"):
    """
    [보너스 모드 의도]
    - 2D 리스트 인덱싱 방식과 1D 평탄화(Flattening) 방식의 메모리 접근 속도를 크기별(3x3 ~ 100x100)로
      100회 반복 측정하여 속도 향상 비율(Speedup)을 벤치마크합니다.
    """
    print("\n" + "=" * 50)
    print(" [보너스] 2D 배열 vs 1D Flattening 최적화 비교 ")
    print("=" * 50)
    print("2차원 배열 인덱싱(pat[r][c])과 1차원 연속 메모리 접근(pat[i])의 연산 속도를 비교합니다.\n")
    
    sizes = [3, 5, 13, 25, 50, 100]
    iterations = 100
    
    print(f"{'크기 (N×N)':<12} {'연산 횟수(N²)':<14} {'2D 방식 (ms)':<16} {'1D 방식 (ms)':<16} {'속도 향상비':<10}")
    print("-" * 70)
    
    for n in sizes:
        # 패턴 생성
        pat_2d = generate_pattern(n, "Cross")
        flt_2d = generate_pattern(n, "Cross")
        
        # 1D 평탄화 변환
        pat_1d = flatten_2d_to_1d(pat_2d)
        flt_1d = flatten_2d_to_1d(flt_2d)
        
        # 각각 100회 반복 측정
        t_2d = benchmark_mac_2d(pat_2d, flt_2d, iterations=iterations)
        t_1d = benchmark_mac_1d(pat_1d, flt_1d, iterations=iterations)
        
        speedup = (t_2d / t_1d) if t_1d > 0 else 1.0
        print(f"{f'{n}×{n}':<12} {n*n:<14} {t_2d:<16.5f} {t_1d:<16.5f} {speedup:<10.2f}x")
    print("-" * 70)
    print("※ 1D Flattening 방식은 2단계 인덱싱 오버헤드를 줄여 캐시 효율과 연산 속도를 개선합니다.\n")


def run_mode_bonus_generator():
    """
    [보너스 모드 의도]
    - 사용자가 지정한 크기 N에 대해 십자가(Cross) 또는 엑스(X) 형태의 패턴을 즉석에서 생성하고
      콘솔에 격자 형태로 시각화하여 보여줍니다.
    """
    print("\n" + "=" * 50)
    print(" [보너스] 패턴 생성기 (Cross / X) ")
    print("=" * 50)
    while True:
        try:
            val = input("생성할 격자 크기 N (홀수 권장, 종료는 0) > ").strip()
            if not val:
                continue
            n = int(val)
            if n == 0:
                break
            if n < 1:
                print("1 이상의 정수를 입력하세요.")
                continue
            
            p_type = input("생성할 패턴 타입 (1: Cross, 2: X) [기본: 1] > ").strip()
            label = "X" if p_type == "2" else "Cross"
            grid = generate_pattern(n, label)
            
            print(f"\n--- 생성된 {n}×{n} {label} 패턴 ---")
            for row in grid:
                print(" ".join(f"{int(x)}" for x in row))
            print()
        except ValueError:
            print("올바른 정수를 입력하세요.")
        except (KeyboardInterrupt, EOFError):
            break


# ==============================================================================
# [6. 메인 메뉴 진입점]
# ==============================================================================

def main_menu():
    """
    [메인 진입점 의도]
    - 사용자에게 번호 기반 대화형 메뉴를 제공하고 입력된 번호에 따라 각 실행 모드로 분기합니다.
    - Ctrl+C (KeyboardInterrupt)나 EOF 발생 시 안전하게 프로그램을 종료합니다.
    """
    while True:
        print("\n" + "=" * 35)
        print("     === Mini NPU Simulator ===")
        print("=" * 35)
        print("[모드 선택]")
        print("1. 사용자 입력 (3x3)")
        print("2. data.json 분석")
        print("3. [보너스] 2D vs 1D 최적화 성능 비교")
        print("4. [보너스] 패턴 자동 생성기")
        print("5. 종료")
        print("=" * 35)
        
        try:
            choice = input("선택 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n프로그램을 종료합니다.")
            sys.exit(0)
            
        if choice == "1":
            run_mode_1()
        elif choice == "2":
            run_mode_2("data.json")
        elif choice == "3":
            run_mode_bonus_optimization("data.json")
        elif choice == "4":
            run_mode_bonus_generator()
        elif choice in ("5", "q", "exit"):
            print("Mini NPU Simulator를 종료합니다.")
            break
        else:
            print("잘못된 선택입니다. 1 ~ 5 중 하나를 입력하세요.")


if __name__ == "__main__":
    main_menu()
