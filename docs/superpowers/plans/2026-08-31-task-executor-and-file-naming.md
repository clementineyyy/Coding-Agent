# TaskExecutor + File Naming Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix file naming (use meaningful English names based on code content, not user prompt text) and add Web project standard structure generation.

**Architecture:** New `TaskExecutor` class parses LLM text response code blocks, infers filenames from content analysis, detects Web projects, and generates standard structure. Integrated into `Agent.run()` final text path.

**Tech Stack:** Python 3.13, pytest, FakeLLM

**Spec:** Approved design in brainstorming session (no separate spec doc)

---

### Task 1: Create TaskExecutor class

**Files:**
- Create: `harness/task_executor.py`
- Test: `harness/tests/test_task_executor.py`

**Interfaces:**
- Consumes: `ToolResult` from `harness.registry`
- Produces: `TaskExecutor(workspace: Path)` with methods `extract_code_blocks(text)`, `infer_filename(code, lang)`, `is_web_project(blocks)`, `execute(text)`

- [x] **Step 1: Write tests for code block extraction, filename inference, Web project detection**
- [x] **Step 2: Run tests to verify they fail** (TDD red phase)
- [x] **Step 3: Implement TaskExecutor class with all methods**
- [x] **Step 4: Run tests to verify they pass** (TDD green phase)
- [x] **Step 5: Commit**

### Task 2: Integrate TaskExecutor into Agent

**Files:**
- Modify: `harness/agent.py` (import, init, run loop, system prompt)

**Interfaces:**
- Consumes: `TaskExecutor` from Task 1
- Produces: Files created from LLM text response code blocks

- [x] **Step 1: Add import and `self.task_executor` initialization**
- [x] **Step 2: Add TaskExecutor.execute() call in text-only response path**
- [x] **Step 3: Update system prompt with file naming guidance**
- [x] **Step 4: Run all tests (existing + new) to verify nothing breaks**
- [x] **Step 5: Commit**

### Task 3: Verification and PR

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**
- [ ] **Step 2: Push to `coding-agent` remote**
- [ ] **Step 3: Create PR to main**
- [ ] **Step 4: Auto-publish to PyPI (bump version + tag + release)**