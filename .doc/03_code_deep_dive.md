# 03. 소스코드(`main.py`) 심층 분석 및 라인별 해설

본 문서는 `main.py`에 작성된 모든 전역 상수, 함수, 조건문, 반복문, 예외 처리 블록의 설계 의도와 내부 동작 메커니즘을 상세히 해설합니다.

---

## 1. 전역 상수 및 라이브러리 임포트 의도

```python
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

EPSILON = 1e-9
DEFAULT_REPEAT_COUNT = 10
```

### 1.1 모듈 임포트 의도
- `json`: `data.json` 데이터셋을 파싱하고 Python 딕셔너리 구조로 변환하기 위해 사용합니다.
- `os`: 실행 위치에 따라 달라질 수 있는 파일 경로를 안전하게 탐색(`os.path.exists`, `os.path.dirname`)하기 위해 사용합니다.
- `sys`: 프로그램 정상/비정상 종료(`sys.exit`) 시 운영체제에 종료 신호를 전달하기 위해 사용합니다.
- `time`: `time.perf_counter()`를 통해 나노초 단위의 고정밀 실행 시간을 측정하기 위해 사용합니다.
- `typing`: 함수의 입력 인자와 반환값에 대한 타입 힌트를 명시하여 코드의 가독성과 타입 안정성을 보장합니다.

### 1.2 전역 상수의 역할과 인과관계
- **`EPSILON = 1e-9` ($10^{-9}$)**
  - **설계 의도**: IEEE 754 부동소수점 표준에 따라 발생하는 미세한 2진수 소수점 연산 오차($0.1 + 0.2 = 0.30000000000000004$)를 상쇄하기 위한 허용오차 임계값입니다.
  - **인과관계**: 두 점수 간의 차이가 $10^{-9}$ 미만이면 실질적으로 동점(Tie)으로 간주하여 `UNDECIDED`(판정 불가)를 반환하도록 제어합니다.
- **`DEFAULT_REPEAT_COUNT = 10`**
  - **설계 의도**: 단 1회의 실행 시간 측정은 운영체제의 컨텍스트 스위칭(Context Switching), CPU 스케줄링 간섭 등으로 인해 측정 오차가 발생할 수 있으므로, 최소 10회 이상 반복 실행한 평균값을 산출하여 측정 신뢰도를 확보합니다.

---

## 2. 핵심 함수별 심층 분석

### 2.1 `normalize_label(label: Any) -> str`
```python
def normalize_label(label: Any) -> str:
    if label is None:
        return "UNKNOWN"
    s = str(label).strip()
    if s in ("+", "cross", "Cross", "CROSS"):
        return "Cross"
    if s in ("x", "X"):
        return "X"
    return s
```
- **[작성 의도]**: 데이터셋(`data.json`)이나 사용자 입력마다 기호(`+`, `x`), 소문자(`cross`), 대문자(`Cross`) 등 라벨 표기가 제각각인 문제를 해결합니다.
- **[동작 원리]**:
  - `label`이 `None`인 경우 `"UNKNOWN"`을 반환하여 에러 방어.
  - 공백을 제거(`strip()`)한 뒤, 십자가 관련 표기(`+`, `cross`, `Cross`, `CROSS`)는 모두 단일 표준인 `"Cross"`로 통합.
  - X 형태 표기(`x`, `X`)는 단일 표준인 `"X"`로 통합.
- **[인과관계]**: 판정 로직(`decide_prediction`)과 검증 로직(`is_pass = decision == expected_label`)에서 문자열 불일치로 인한 오판정을 방지합니다.

---

### 2.2 `calculate_mac_2d(pattern, filter_grid) -> float`
```python
def calculate_mac_2d(pattern: List[List[float]], filter_grid: List[List[float]]) -> float:
    total_score = 0.0
    rows = len(pattern)
    cols = len(pattern[0]) if rows > 0 else 0
    for r in range(rows):
        for c in range(cols):
            total_score += pattern[r][c] * filter_grid[r][c]
    return total_score
```
- **[작성 의도]**: NPU의 하드웨어 곱셈-누적(MAC) 유닛을 순수 파이썬의 2중 for문으로 시뮬레이션합니다.
- **[동작 원리]**:
  - `total_score`를 `0.0`으로 초기화 (누적기 레지스터 역할).
  - 행 크기 `rows`, 열 크기 `cols`를 측정.
  - 바깥쪽 루프(`for r in range(rows)`)와 안쪽 루프(`for c in range(cols)`)를 순회하며 `(r, c)` 좌표의 입력값과 가중치를 곱하고 더함.
- **[인과관계]**: 총 $N \times N = N^2$ 번의 곱셈과 덧셈이 순차적으로 발생하므로 시간 복잡도는 정확히 $O(N^2)$가 됩니다.

---

### 2.3 `calculate_mac_1d(pattern_1d, filter_1d) -> float`
```python
def calculate_mac_1d(pattern_1d: List[float], filter_1d: List[float]) -> float:
    total_score = 0.0
    n = len(pattern_1d)
    for i in range(n):
        total_score += pattern_1d[i] * filter_1d[i]
    return total_score
```
- **[작성 의도]**: 1차원 평탄화(Flattened)된 연속 배열을 대상으로 단일 루프로 MAC을 수행하여 메모리 접근 최적화 효과를 검증합니다.
- **[동작 원리]**:
  - 2차원 리스트의 2단계 포인터 역참조(`pat[r][c]`)를 1단계 인덱싱(`pat[i]`)으로 축소.
- **[인과관계]**: Python 바이트코드 수준에서 루프 오버헤드와 인덱싱 단계가 줄어들어 동일한 $N^2$ 연산량 대비 실행 시간이 약 1.5배~2배 단축됩니다.

---

### 2.4 `flatten_2d_to_1d(grid_2d) -> List[float]`
```python
def flatten_2d_to_1d(grid_2d: List[List[float]]) -> List[float]:
    return [val for row in grid_2d for val in row]
```
- **[작성 의도]**: 행렬 형태의 $N \times N$ 2차원 배열을 길이 $N^2$의 1차원 선형 리스트로 고속 변환합니다.
- **[동작 원리]**: 중첩 리스트 컴프리헨션(List Comprehension)을 사용하여 C 레벨에서 빠르게 요소를 평탄화합니다.

---

### 2.5 `decide_prediction(score_a, score_b, label_a, label_b, epsilon) -> Tuple[str, str]`
```python
def decide_prediction(
    score_a: float,
    score_b: float,
    label_a: str = "A",
    label_b: str = "B",
    epsilon: float = EPSILON
) -> Tuple[str, str]:
    diff = abs(score_a - score_b)
    if diff < epsilon:
        return "UNDECIDED", f"동점 (|{label_a}-{label_b}| = {diff:.2e} < {epsilon})"
    elif score_a > score_b:
        return label_a, f"{label_a} 점수 우세 (차이: {diff:.4f})"
    else:
        return label_b, f"{label_b} 점수 우세 (차이: {diff:.4f})"
```
- **[작성 의도]**: 두 필터가 입력 패턴에 대해 획득한 MAC 점수를 비교하여 최종 판정을 내리고 판정 사유를 문자열로 함께 반환합니다.
- **[동작 원리]**:
  - `diff = abs(score_a - score_b)`로 두 점수의 절대 차이를 계산.
  - `diff < epsilon`이면 점수가 동일한 것으로 판단하고 `"UNDECIDED"`(판정 불가) 반환.
  - 그렇지 않은 경우 더 큰 점수를 가진 라벨과 점수 차이를 함께 반환.
- **[인과관계]**: 단순 `score_a == score_b` 비교 시 발생하는 부동소수점 오차 누락 버그를 방지하고, 수치적 동점 상황을 명확히 식별합니다.

---

### 2.6 `benchmark_mac_2d(pattern, filter_grid, iterations) -> float`
```python
def benchmark_mac_2d(
    pattern: List[List[float]],
    filter_grid: List[List[float]],
    iterations: int = DEFAULT_REPEAT_COUNT
) -> float:
    start_time = time.perf_counter()
    for _ in range(iterations):
        calculate_mac_2d(pattern, filter_grid)
    end_time = time.perf_counter()
    
    total_elapsed_ms = (end_time - start_time) * 1000.0
    return total_elapsed_ms / iterations
```
- **[작성 의도]**: 콘솔 I/O나 데이터 로딩 시간을 완전히 제외하고, **순수 CPU 산술 연산 구간의 평균 실행 시간(ms)**만을 정밀 측정합니다.
- **[왜 `time.perf_counter()`인가?]**:
  - `time.time()`은 시스템 시계(Wall-clock) 동기화(NTP 등)로 인해 시간이 거꾸로 흐르거나 정밀도가 밀리초 수준에 불과할 수 있습니다.
  - `time.perf_counter()`는 CPU 하드웨어 타이머에 기반한 모노토닉(Monotonic, 절대 줄어들지 않는) 고정밀 타이머로, 마이크로초/나노초 단위의 벤치마크에 필수적입니다.

---

### 2.7 `input_grid_interactive(grid_name, size) -> List[List[float]]`
```python
def input_grid_interactive(grid_name: str, size: int = 3) -> List[List[float]]:
```
- **[작성 의도]**: 사용자로부터 콘솔을 통해 $size \times size$ 크기의 숫자 행렬을 한 행씩 안전하게 입력받습니다.
- **[방어적 프로그래밍 기법]**:
  - `while True` 무한 루프로 감싸 사용자가 올바른 형식을 입력할 때까지 반복.
  - 빈 줄 입력 감지 (`if not line`).
  - 한 행의 토큰 개수가 $size$개와 불일치할 경우 에러 메시지 출력 후 재입력 유도 (`len(tokens) != size`).
  - 문자열이나 특수문자 등 숫자가 아닌 값이 들어오면 `ValueError`를 캐치(`try-except`)하여 비정상 종료를 차단.

---

### 2.8 `generate_pattern(size, pattern_type) -> List[List[float]]`
```python
def generate_pattern(size: int, pattern_type: str = "Cross") -> List[List[float]]:
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
```
- **[작성 의도]**: 임의의 크기 $N$에 대해 수학적으로 이상적인 십자가(Cross) 또는 대각선(X) 패턴의 $N \times N$ 행렬(0.0과 1.0으로 구성)을 자동 생성합니다.
- **[수학적 인덱싱 공식]**:
  - `Cross`: 중앙 인덱스 `mid = size // 2`에 대해 `grid[mid][i] = 1.0` (가로선), `grid[i][mid] = 1.0` (세로선).
  - `X`: 주대각선 `grid[i][i] = 1.0`, 부대각선 `grid[i][size - 1 - i] = 1.0`.

---

### 2.9 `run_mode_2(json_filename)` 분석
- **[작성 의도]**: `data.json`에 정의된 모든 필터와 패턴을 일괄 로드하여 스키마 검증, MAC 점수 계산, 예측 및 PASS/FAIL 판정을 수행하고 종합 리포트를 도출합니다.
- **[주요 처리 단계]**:
  1. **파일 탐색 및 로드**: 상대 경로 및 현재 파일 위치 기반 절대 경로를 이중 탐색하여 `FileNotFoundError` 방지.
  2. **필터 정규화 및 캐싱**: `filters` 섹션에서 `Cross`와 `X` 필터를 추출하여 `normalized_filters` 맵에 등록.
  3. **패턴 검증 루프**:
     - 패턴 키(`size_5_1` 등)에서 $N$을 파싱하고 유효한 필터가 존재하는지 검증.
     - 2차원 리스트의 행 크기와 열 크기가 정확히 $N \times N$인지 검증.
  4. **MAC 점수 계산 및 판정**: `calculate_mac_2d`로 각 필터와의 점수를 구하고 `decide_prediction`으로 예측 라벨 도출.
  5. **PASS/FAIL 판정**: 예측 라벨이 기대값(`expected`)과 완전히 일치하면 PASS, 불일치 또는 동점이면 FAIL로 분류하고 실패 사유를 로그에 기록.
  6. **성능 벤치마크 및 결과 요약**: 10회 반복 측정 평균 시간과 총 통과/실패 통계를 출력.
