# ADR 0001: Python for workers and scripts, TypeScript for the web app

- **Status:** Accepted
- **Date:** 2026-11-07

## Context
The project has two kinds of code: a web app, and scheduled pipeline workers that fetch papers, call LLM and TTS services, and write results to Postgres. The initial default was TypeScript throughout, and the worker language was left open.

## Decision
- **Web app:** TypeScript with strict mode, on Next.js.
- **Workers and scripts:** Python, with strict static type checking. This covers the pipeline, evals, data tooling and operational scripts.

## Consequences
- **Library access:** workers can use Python's data, NLP and evaluation libraries directly.
- **Two toolchains:** the repo needs separate dependency management, linting, type checking and tests for each language, and CI must cover both. Tool choices are made when each side is scaffolded.
- **No shared types:** Python and TypeScript cannot share type definitions. Postgres schema and migrations are the contract between them, and code on both sides must be checked against that schema.
- **No shared code:** logic needed on both sides should run in one place and reach the other through the database or an explicit interface, so it does not get implemented twice.
- **Container images:** worker and web images are built separately, and both must build for `linux/amd64` and `linux/arm64`. Python dependencies must have `arm64` support.

## Alternatives considered
- **TypeScript everywhere:** one toolchain and shared types, but without direct access to Python's data and NLP libraries.
- **Python everywhere:** one language, but it replaces Next.js and its ecosystem for the web app.
