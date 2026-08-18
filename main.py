#!/usr/bin/env python3
"""
Mini NPU Simulator
AI 계산 방식(MAC: Multiply-Accumulate)을 흉내 내는 소형 NPU 시뮬레이터 콘솔 애플리케이션

주요 기능:
1. 사용자 입력 모드 (3x3): 콘솔 입력을 통한 필터/패턴 로드, MAC 연산, 동점(epsilon) 판정 및 성능 측정
2. data.json 분석 모드: 5x5, 13x13, 25x25 필터/패턴 일괄 판정, 라벨 정규화, PASS/FAIL 검증, O(N^2) 성능 분석
3. (보너스) 패턴 생성기 & 1D/2D 메모리 접근 최적화 벤치마크
"""

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

EPSILON = 1e-9
DEFAULT_REPEAT_COUNT = 10


def normalize_label(label: Any) -> str:
    """
    입력된 라벨을 표준 라벨('Cross', 'X')로 정규화(표준화)합니다.
    - '+' / 'cross' / 'Cross' -> 'Cross'
    - 'x' / 'X' -> 'X'
    """
    if label is None:
        return "UNKNOWN"
    
    s = str(label).strip()
    if s in ("+", "cross", "Cross", "CROSS"):
        return "Cross"
    if s in ("x", "X"):
        return "X"
    return s


def calculate_mac_2d(pattern: List[List[float]], filter_grid: List[List[float]]) -> float:
    """
    순수 파이썬 2중 반복문을 사용한 2차원 MAC(Multiply-Accumulate) 연산
    외부 라이브러리(NumPy 등) 없이 위치별 원소를 곱하여 누적 합산합니다.
    """
    total_score = 0.0
    rows = len(pattern)
    cols = len(pattern[0]) if rows > 0 else 0
    for r in range(rows):
        for c in range(cols):
            total_score += pattern[r][c] * filter_grid[r][c]
    return total_score


def calculate_mac_1d(pattern_1d: List[float], filter_1d: List[float]) -> float:
    """
    (보너스 과제) 1차원 Flattening 배열 대상의 단순 루프 MAC 연산
    메모리 연속 접근 최적화 효과를 검증합니다.
    """
    total_score = 0.0
    n = len(pattern_1d)
    for i in range(n):
        total_score += pattern_1d[i] * filter_1d[i]
    return total_score


def flatten_2d_to_1d(grid_2d: List[List[float]]) -> List[float]:
    """2차원 배열을 1차원 배열(길이 N^2)로 변환합니다."""
    return [val for row in grid_2d for val in row]


def decide_prediction(
    score_a: float,
    score_b: float,
    label_a: str = "A",
    label_b: str = "B",
    epsilon: float = EPSILON
) -> Tuple[str, str]:
    """
    두 점수를 비교하여 판정 결과를 반환합니다.
    부동소수점 오차 및 동점 기준: abs(score_a - score_b) < epsilon 이면 판정 불가(UNDECIDED)
    반환값: (판정 라벨, 사유 설명)
    """
    diff = abs(score_a - score_b)
    if diff < epsilon:
        return "UNDECIDED", f"동점 (|{label_a}-{label_b}| = {diff:.2e} < {epsilon})"
    elif score_a > score_b:
        return label_a, f"{label_a} 점수 우세 (차이: {diff:.4f})"
    else:
        return label_b, f"{label_b} 점수 우세 (차이: {diff:.4f})"


def benchmark_mac_2d(
    pattern: List[List[float]],
    filter_grid: List[List[float]],
    iterations: int = DEFAULT_REPEAT_COUNT
) -> float:
    """
    순수 MAC 연산 구간(I/O 제외)에 대해 iterations회 반복 측정한 평균 시간(ms)을 반환합니다.
    """
    # 고정밀 타이머 사용
    start_time = time.perf_counter()
    for _ in range(iterations):
        calculate_mac_2d(pattern, filter_grid)
    end_time = time.perf_counter()
    
    total_elapsed_ms = (end_time - start_time) * 1000.0
    return total_elapsed_ms / iterations


def benchmark_mac_1d(
    pattern_1d: List[float],
    filter_1d: List[float],
    iterations: int = DEFAULT_REPEAT_COUNT
) -> float:
    """
    1차원 배열 MAC 연산 평균 시간(ms) 측정
    """
    start_time = time.perf_counter()
    for _ in range(iterations):
        calculate_mac_1d(pattern_1d, filter_1d)
    end_time = time.perf_counter()
    
    total_elapsed_ms = (end_time - start_time) * 1000.0
    return total_elapsed_ms / iterations


def input_grid_interactive(grid_name: str, size: int = 3) -> List[List[float]]:
    """
    사용자로부터 size x size 크기의 숫자 격자를 한 줄씩(공백 구분) 입력받습니다.
    행/열 개수 불일치, 숫자 파싱 실패 시 재입력을 유도합니다.
    """
    print(f"\n{grid_name} ({size}줄 입력, 각 줄에 숫자 {size}개를 공백으로 구분)")
    while True:
        grid: List[List[float]] = []
        is_valid = True
        for row_idx in range(size):
            try:
                line = input(f"[{row_idx + 1}/{size} 행] > ").strip()
                if not line:
                    print(f"입력 오류: 빈 줄입니다. {size}개의 숫자를 공백으로 구분해 입력하세요.")
                    is_valid = False
                    break
                tokens = line.split()
                if len(tokens) != size:
                    print(f"입력 형식 오류: 각 줄에 {size}개의 숫자를 공백으로 구분해 입력하세요. (입력 개수: {len(tokens)})")
                    is_valid = False
                    break
                row_vals = [float(token) for token in tokens]
                grid.append(row_vals)
            except ValueError:
                print("입력 형식 오류: 숫자(정수 또는 실수)만 입력 가능합니다.")
                is_valid = False
                break
        
        if is_valid and len(grid) == size:
            return grid
        
        print(f"-> {grid_name} 입력을 처음부터 다시 시도합니다.")


def generate_pattern(size: int, pattern_type: str = "Cross") -> List[List[float]]:
    """
    (보너스) 크기 N에 대해 이상적인 Cross(십자가) 또는 X 패턴 격자(0.0/1.0)를 생성합니다.
    """
    grid = [[0.0 for _ in range(size)] for _ in range(size)]
    norm_type = normalize_label(pattern_type)
    
    if norm_type == "Cross":
        mid = size // 2
        for i in range(size):
            grid[mid][i] = 1.0
            grid[i][mid] = 1.0
    elif norm_type == "X":
        for i in range(size):
            grid[i][i] = 1.0
            grid[i][size - 1 - i] = 1.0
    return grid


def run_mode_1():
    """모드 1: 3x3 사용자 콘솔 입력 처리"""
    print("\n" + "=" * 50)
    print(" [모드 1] 사용자 입력 (3x3) ")
    print("=" * 50)
    print("3x3 크기의 필터 A, 필터 B, 그리고 패턴 데이터를 입력받습니다.")
    
    # 1. 입력 받기
    print("\n#----------------------------------------")
    print("# [1] 필터 입력")
    print("#----------------------------------------")
    filter_a = input_grid_interactive("필터 A", size=3)
    filter_b = input_grid_interactive("필터 B", size=3)
    
    print("\n#----------------------------------------")
    print("# [2] 패턴 입력")
    print("#----------------------------------------")
    pattern = input_grid_interactive("패턴", size=3)
    
    # 2. MAC 점수 계산
    score_a = calculate_mac_2d(pattern, filter_a)
    score_b = calculate_mac_2d(pattern, filter_b)
    
    # 3. 성능 측정 (10회 평균)
    avg_time_a = benchmark_mac_2d(pattern, filter_a, iterations=10)
    avg_time_b = benchmark_mac_2d(pattern, filter_b, iterations=10)
    avg_time = (avg_time_a + avg_time_b) / 2.0
    
    # 4. 판정
    decision, reason = decide_prediction(score_a, score_b, label_a="A", label_b="B", epsilon=EPSILON)
    
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
    """모드 2: JSON 데이터 분석 및 스키마 검증, 성능 분석"""
    print("\n" + "=" * 50)
    print(" [모드 2] data.json 분석 ")
    print("=" * 50)
    
    # 파일 탐색
    target_path = json_filename
    if not os.path.exists(target_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(base_dir, json_filename)
        if os.path.exists(alt_path):
            target_path = alt_path
        else:
            print(f"오류: {json_filename} 파일을 찾을 수 없습니다. 경로를 확인해주세요.")
            return

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
    
    # 1. 필터 로드 현황
    print("\n#---------------------------------------")
    print("# [1] 필터 로드")
    print("#---------------------------------------")
    available_sizes = []
    normalized_filters: Dict[str, Dict[str, List[List[float]]]] = {}
    
    for size_key, f_data in filters_dict.items():
        # size_5, size_13 등
        f_cross = None
        f_x = None
        for k, grid in f_data.items():
            norm_k = normalize_label(k)
            if norm_k == "Cross":
                f_cross = grid
            elif norm_k == "X":
                f_x = grid
        
        if f_cross is not None and f_x is not None:
            normalized_filters[size_key] = {"Cross": f_cross, "X": f_x}
            available_sizes.append(size_key)
            print(f"✓ {size_key:<7} 필터 로드 완료 (Cross, X)")
        else:
            print(f"⚠ {size_key:<7} 필터 구성 불완전 (Cross/X 누락)")

    # 2. 패턴 분석
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
        
        # 키에서 N 추출 (예: size_5_1 -> 5)
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
        
        # 크기 및 구조 검증
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
        
        # 필터 크기 검증
        cross_filter = normalized_filters[filter_size_key]["Cross"]
        x_filter = normalized_filters[filter_size_key]["X"]
        
        # 벤치마크 샘플 등록
        if filter_size_key not in benchmark_data:
            benchmark_data[filter_size_key] = (input_grid, cross_filter)
        
        # MAC 연산 수행
        score_cross = calculate_mac_2d(input_grid, cross_filter)
        score_x = calculate_mac_2d(input_grid, x_filter)
        
        # 판정
        decision, reason = decide_prediction(score_cross, score_x, label_a="Cross", label_b="X", epsilon=EPSILON)
        
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

    # 3. 성능 분석
    print("\n#---------------------------------------")
    print("# [3] 성능 분석 (평균 10회 반복 측정)")
    print("#---------------------------------------")
    print(f"{'크기':<10} {'평균 시간(ms)':<15} {'연산 횟수(N²)':<15}")
    print("-" * 42)
    
    # 3x3 (표준 패턴 생성), 5x5, 13x13, 25x25 측정
    test_sizes = [3, 5, 13, 25]
    for n in test_sizes:
        size_key = f"size_{n}"
        if size_key in benchmark_data:
            pat, flt = benchmark_data[size_key]
        else:
            # 3x3 등 json에 없는 경우 자동 생성 패턴 사용
            pat = generate_pattern(n, "Cross")
            flt = generate_pattern(n, "Cross")
        
        avg_ms = benchmark_mac_2d(pat, flt, iterations=10)
        op_count = n * n
        print(f"{f'{n}×{n}':<10} {avg_ms:<15.5f} {op_count:<15}")

    # 4. 결과 요약
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
    
    print("\n(상세 원인 분석 및 시간 복잡도 설명은 README.md의 '결과 리포트' 섹션을 참조하세요.)")
    print("#---------------------------------------\n")


def run_mode_bonus_optimization(json_filename: str = "data.json"):
    """(보너스 과제) 2D vs 1D Flattening 메모리 접근 최적화 성능 비교"""
    print("\n" + "=" * 50)
    print(" [보너스] 2D 배열 vs 1D Flattening 최적화 비교 ")
    print("=" * 50)
    print("2차원 배열 인덱싱(pat[r][c])과 1차원 연속 메모리 접근(pat[i])의 연산 속도를 비교합니다.\n")
    
    sizes = [3, 5, 13, 25, 50, 100]
    iterations = 100
    
    print(f"{'크기 (N×N)':<12} {'연산 횟수(N²)':<14} {'2D 방식 (ms)':<16} {'1D 방식 (ms)':<16} {'속도 향상비':<10}")
    print("-" * 70)
    
    for n in sizes:
        pat_2d = generate_pattern(n, "Cross")
        flt_2d = generate_pattern(n, "Cross")
        
        pat_1d = flatten_2d_to_1d(pat_2d)
        flt_1d = flatten_2d_to_1d(flt_2d)
        
        t_2d = benchmark_mac_2d(pat_2d, flt_2d, iterations=iterations)
        t_1d = benchmark_mac_1d(pat_1d, flt_1d, iterations=iterations)
        
        speedup = (t_2d / t_1d) if t_1d > 0 else 1.0
        print(f"{f'{n}×{n}':<12} {n*n:<14} {t_2d:<16.5f} {t_1d:<16.5f} {speedup:<10.2f}x")
    print("-" * 70)
    print("※ 1D Flattening 방식은 2단계 인덱싱 오버헤드를 줄여 캐시 효율과 연산 속도를 개선합니다.\n")


def run_mode_bonus_generator():
    """(보너스 과제) 임의 크기 N에 대한 패턴 생성기 및 시각화"""
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


def main_menu():
    """콘솔 메인 메뉴 진입점"""
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
