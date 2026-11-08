# AGENTS.md

## Communication & Language Rules
- Respond and explain in Traditional Chinese (繁體中文).
- Write all code, variable names, and code comments in English.

## Project Role & Engineering Scope

### 1. Core Mission
- **Cloud Platform Engineering & Operations**:
  - Focus on the CMAA cloud infrastructure (AWS EC2 / S3 / Lambda / IAM), web services (React frontend & Express backend), visitor/member authentication systems, transactional atomic credit deduction, payment workflows, and security guardrails.
  - Architect and maintain integration adapters and seams bridging various analysis engines to the cloud platform.

### 2. Scope Boundaries

#### ✅ In-Scope
- **Cloud Integration & Adapters**:
  - Interface refactoring, protocol conversions, and containerized wrappers designed to integrate static engines, dynamic sandboxes, and PDF generators into the cloud platform (e.g., HTTP/Queue API wrappers, S3 streaming I/O, Redis/Celery task queues, Docker/Compose setups).
  - AWS EC2 sandbox instance lifecycle management (startup, shutdown, watchdog timeout protection, socket health checks).
  - AWS Lambda invocations, S3 object lifecycle and path schema governance, and IAM principle of least privilege enforcement.
  - Full-stack business logic, visitor session auth, atomic credit deduction against race conditions/overspending, payment integration, and defensive security measures (Cloudflare Turnstile, rate limiting, IDOR prevention).

#### ❌ Out-of-Scope (Core Engine Algorithm & Internal Functional Optimization)
- **Static Analysis Engine Internals (`CMAA-Astatic`)**:
  - Evaluation rules across the 80 MAST criteria, Androguard decompilation pipelines, and packer/shell signature detection logic.
- **Dynamic Sandbox Exploration & Hooking Internals (`android-detection-system`)**:
  - Frida hooking scripts (`Code.js`) decision rules, UI exploration state machines (`CmdServer.py`), and automated fuzzing heuristics.
- **PDF Generator Internal Layout & Design (`pdf-generator`)**:
  - Security audit report typesetting, styling, font rendering algorithms, and statutory compliance document formatting.

> **Seam Discipline**: Strictly avoid altering the core detection rules, heuristic algorithms, or internal layout engines. However, all architectural adapters, S3/AWS integration, API wrapping, lifecycle orchestration, and cloud hardening required to connect these engines into the platform remain strictly **in-scope**.

