# Mini NPU Simulator 문서 인덱스 및 학습 가이드

본 디렉터리(`.doc/`)는 **Mini NPU Simulator(소형 NPU AI 계산기 시뮬레이터)**의 아키텍처, 제어 및 데이터 흐름, 코드 라인별 심층 분석, 실패 케이스 인과관계 분석, 그리고 시간 복잡도/하드웨어 가속 원리를 체계적으로 설명하는 기술 문서 모음입니다.

---

## 📚 문서 목차 (Table of Contents)

| 번호 | 문서 파일명 | 핵심 주제 및 주요 내용 |
| :---: | :--- | :--- |
| **01** | [**01_project_overview.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/01_project_overview.md) | **프로젝트 개요 및 NPU 기초 이론**<br>- NPU(Neural Processing Unit)의 등장 배경 (CPU/GPU 대비 차이)<br>- AI 핵심 연산인 MAC(Multiply-Accumulate, 곱셈-누적)의 원리<br>- 프로젝트 설계 목표 및 외부 라이브러리 배제 제약조건 |
| **02** | [**02_control_and_data_flow.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/02_control_and_data_flow.md) | **제어 흐름(Control Flow) 및 데이터 흐름(Data Flow)**<br>- 전체 프로그램의 상태 전이 다이어그램<br>- 함수 호출 그래프(Call Graph) 및 인과관계 매핑<br>- `data.json` 로드부터 MAC 점수 산출, 판정에 이르는 데이터 파이프라인 |
| **03** | [**03_code_deep_dive.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/03_code_deep_dive.md) | **소스코드 (`main.py`) 심층 분석 및 라인별 해설**<br>- 모든 전역 상수(`EPSILON`, `DEFAULT_REPEAT_COUNT`)의 설계 의도<br>- 함수별 역할, 매개변수, 반환값, 내부 알고리즘 및 방어적 에러 핸들링<br>- 부동소수점 오차 제어와 고정밀 타이머(`time.perf_counter`) 사용 배경 |
| **04** | [**04_data_json_and_failure_analysis.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/04_data_json_and_failure_analysis.md) | **데이터셋 (`data.json`) 구조 및 FAIL 케이스 인과관계 분석**<br>- 필터(Filter) 및 패턴(Pattern)의 2차원 매트릭스 시각화<br>- 6개 테스트 케이스의 수학적 점수 계산 과정<br>- 3건의 실패 원인(수치 동점 2건, 중앙 가중치 지배 오분류 1건) 단계별 추적 |
| **05** | [**05_complexity_and_optimization.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/05_complexity_and_optimization.md) | **$O(N^2)$ 시간 복잡도와 메모리 최적화 이론**<br>- $O(N^2)$ 연산량 증가 곡선의 수학적 증명 및 실측 결과 비교<br>- 2D 리스트 vs 1D Flattening의 캐시 지역성(Spatial Locality) 및 포인터 역참조 오버헤드<br>- 하드웨어 시스톨릭 어레이(Systolic Array)와의 연계 분석 |
| **06** | [**06_usage_and_scenarios.md**](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/06_usage_and_scenarios.md) | **사용자 매뉴얼 및 인터랙티브 실행 시나리오**<br>- 모드 1: 3×3 콘솔 직접 입력 및 실시간 판정<br>- 모드 2: `data.json` 일괄 분석 및 리포트 확인<br>- 모드 3 & 4: 최적화 벤치마크 및 패턴 생성기 활용법<br>- 사용자 입력 검증 및 에러 복구 흐름 |

---

## 🎯 추천 학습 로드맵

1. **기초 개념 이해**: [01_project_overview.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/01_project_overview.md)를 먼저 읽고 AI 가속기와 MAC 연산의 본질을 이해합니다.
2. **시스템 동작 흐름 파악**: [02_control_and_data_flow.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/02_control_and_data_flow.md)의 다이어그램을 통해 프로그램이 어떻게 흘러가는지 전체 그림을 그립니다.
3. **코드 구현 상세 확인**: [03_code_deep_dive.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/03_code_deep_dive.md)와 [main.py](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/main.py)를 대조하며 각 함수와 루프의 설계 의도를 학습합니다.
4. **데이터 및 판정 원리 분석**: [04_data_json_and_failure_analysis.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/04_data_json_and_failure_analysis.md)를 통해 왜 어떤 케이스는 통과하고 어떤 케이스는 실패하는지 수학적 인과관계를 파악합니다.
5. **성능과 하드웨어 지식 확장**: [05_complexity_and_optimization.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/05_complexity_and_optimization.md)를 통해 알고리즘 복잡도와 CPU 캐시, NPU 구조의 연관성을 깊이 있게 이해합니다.
6. **직접 실행 및 테스트**: [06_usage_and_scenarios.md](file:///Users/c1134czi5625/.gemini/antigravity-ide/scratch/mini_npu_simulator/.doc/06_usage_and_scenarios.md)를 참조하여 프로그램을 다양한 방식으로 조작해봅니다.
