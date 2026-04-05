# contracts.md - System Contracts and Invariants

## 1. Purpose

This document defines hard contracts for data models, interfaces, invariants,
failure behavior, and test expectations.

---

## 2. Versioning

- Current Version: V1
- Last Updated: {{TODAY}}
- Any contract change requires:
  1. Version bump
  2. Change date
  3. Rationale
  4. Affected modules

---

## 3. Data Contracts

Define tables, schemas, enums, and field-level constraints.

### 3.1 Entity/Table A
- schema
- unique keys
- dedup rules

### 3.2 Entity/Table B
- schema
- status transitions
- retention rules

### 3.3 Enumerated Values
- allowed values
- defaults
- validation rules

---

## 4. Data Flow Contract

Document exact ordered pipeline flow and ownership boundaries.

Invariants:
- [example invariant 1]
- [example invariant 2]

---

## 5. Failure Contracts

For each failure mode, specify mandatory behavior.

FC-01:
- Trigger:
- Required behavior:
- Not acceptable:

FC-02:
- Trigger:
- Required behavior:
- Not acceptable:

---

## 6. Test Specifications

Define minimum test coverage required per module.

Module tests:
- test_x:
- test_y:
