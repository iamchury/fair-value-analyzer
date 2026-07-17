# Fair Value Analyzer

Yahoo Finance 데이터를 이용하여 종목의 EPS, 성장률, PER 및 적정주가를 분석하는 시스템입니다.

## 주요 기능

- Yahoo Finance 주가 데이터 수집
- 분기별 및 연간 EPS 수집
- EPS 성장률 계산
- 목표 PER 기반 적정주가 계산
- 현재가 대비 할인율 및 상승여력 계산
- 종목별 목표가격 테이블 생성
- GitHub Actions 기반 자동 업데이트

## 초기 분석 대상

- SOXL
- SOXX
- MU
- AMAT
- NVDA
- GLW
- COHR
- LITE

## 적정주가 기본 공식

```text
적정주가 = 예상 연간 EPS × 목표 PER
 