# DuoPty Documentation Index

Welcome to the DuoPty technical documentation repository. This directory archives the architectural plans, implementation history, and verification walkthroughs for DuoPty.

---

## 📑 Core Documentation

- **[System Architecture](ARCHITECTURE.md)**: Comprehensive design document detailing the 4-stage progressive elimination pipeline, safe deletion engine, concurrency model, and module structure.

---

## 📐 Implementation Plans

- **[Phase 1: Initial Implementation Plan](plans/01_initial_implementation_plan.md)**:
  - Initial specifications, data models, 4-stage pipeline design, and Tkinter GUI architecture.
- **[Phase 2: Deletion Concurrency & Read-Only Fix Plan](plans/02_deletion_concurrency_fix_plan.md)**:
  - Problem analysis and architectural plan to fix Tkinter UI thread starvation ("Not Responding") and Windows read-only file deletion failures.

---

## 🚶 Walkthroughs & Verifications

- **[Phase 1: Initial System Build Walkthrough](walkthroughs/01_initial_walkthrough.md)**:
  - Summary of initial components built, 4-stage pipeline diagram, and initial unit test verification (11 tests).
- **[Phase 2: Deletion Concurrency Fix Walkthrough](walkthroughs/02_deletion_concurrency_fix_walkthrough.md)**:
  - Detailed summary of changes in `duopty/deleter.py` and `duopty/gui.py`, modal progress dialog implementation, and verification (15 tests + batch stress test).

---

## 🤖 Coding Agent Context

- See **[`../AGENTS.md`](../AGENTS.md)** for developer instructions, common commands, and project conventions tailored for Claude Code and coding agents.
