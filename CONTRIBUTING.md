# Contributing to QuantDinger

Thanks for your interest in contributing to **QuantDinger**.

QuantDinger is a **local-first, private AI-driven quantitative trading workspace**.
It is built for people who care about:
- data sovereignty
- local execution
- transparent systems
- engineering over hype

This document explains **how to contribute** and **what contribution means here**.

---

## ⚠️ Please Read First

QuantDinger is **not a DAO**.
There is **no token**, **no airdrop**, and **no financial incentive** at this stage.

If you are looking for short-term rewards, promotions, or token speculation,
this project is probably **not a good fit**.

If you are interested in:
- building credible infrastructure
- publishing real work under your name
- shaping an early-stage system with long-term value

you are very welcome here.

---

## 🧭 What Contribution Means

Contributing to QuantDinger means creating **public, verifiable work**.

Your contributions:
- are attributed publicly on GitHub
- can be referenced in your resume or portfolio
- remain valuable to you beyond this project

This is a **builder-first environment**.

---

## 🧑‍💻 Ways to Contribute

### 1) Core Engineering
- Python strategy engine
- execution logic
- AI / LLM agent workflows
- backtesting and data pipelines

Small, focused improvements are preferred.

---

### 2) Strategy & Research
- example strategies
- research notebooks
- execution experiments
- performance analysis

This is a good place to demonstrate how you think.

---

### 3) Documentation & Explanation
- tutorials and setup guides
- architecture explanations
- design rationale

Clear explanations matter as much as good code.

---

### 4) Content & Advocacy
- technical blog posts
- demo videos
- system breakdowns
- honest reviews or critiques

You are not “marketing”.
You are explaining something real.

---

## 🔗 Communication Channels

- **Issues**: bug reports and feature requests
- **Discussions**: questions, ideas, and design conversations
- **Community**: official links are listed in `README.md`

If you plan a large change, please open a discussion first.

---

## 🛠️ Development Setup

This repository contains:

- `backend_api_python/`: Flask backend + strategy runtime
- `quantdinger_vue/`: Vue frontend

### Backend (Python)

```bash
cd backend_api_python
pip install -r requirements.txt
cp env.example .env   # Windows: copy env.example .env
python run.py
```

### Frontend (Vue)

```bash
cd quantdinger_vue
npm install
npm run serve
```

---

## 🌿 Branching & Pull Requests

### Branch naming

- `fix/xxx` — bug fixes
- `feat/xxx` — new features
- `docs/xxx` — documentation
- `chore/xxx` — maintenance

### Pull request guidelines

Please include:

- what changed and why
- how to test
- screenshots/GIFs for UI changes (if applicable)
- backward compatibility notes (if any)

Keep PRs focused and reviewable.

---

## 🧪 Testing & Verification

We do not enforce a single test command yet. Please at least:

- **Backend**: run the API locally and verify affected endpoints
- **Frontend**: run the dev server and verify affected pages/components

Bug fixes should include a minimal regression test when practical.

---

## 🔐 Security

Please do not open public issues for security vulnerabilities.

For security reports, contact the maintainer via the email in README.md and include:

- description of the issue
- steps to reproduce
- impact assessment

---

## 📜 License

By contributing, you agree that your contributions will be licensed
under the project's license (see LICENSE).

---

## 🧠 A Note on the Future

QuantDinger may explore incentive or alignment mechanisms in the future.
Nothing is promised, scheduled, or guaranteed.

What is guaranteed:

- your work will be visible
- your name will be attached to it
- your contribution will remain yours

Build carefully. Build openly. Build things that last.