# qwen3.8-flash-next_measure

[日本語](README.md) | **English**

An experiment in tuning launch parameters to improve Qwen3.8-Flash-Next generation throughput (tok/s) with two llama.cpp forks and Strata.
Every measurement used the Japanese user prompt `ブロック崩しゲーム作って` ("Make a Breakout game"). The repository contains configurations, all measurements, requests, responses, logs, and reproduction scripts.

## Measurement environment

Measurement date: 2026-09-28.

| Component | Specification |
| --- | --- |
| OS / execution environment | Windows native |
| GPU | NVIDIA GeForce RTX 5090 (32GB VRAM) |
| CPU | Intel Core i7-14700 |
| RAM | 128GB (64GB × 2, DDR5-5600) |
| Model storage | M.2 SSD |

Both engines used the same two GGUF shards of [ISTA-DASLab GSQ-RCO IQ3_S](https://huggingface.co/ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF).

## Engine names and configuration IDs

**Labels such as G7 and S31 are configuration IDs assigned within this experiment to identify combinations of launch arguments. They are not software versions or official preset names.**

| Name used in this repository | Engine | Configuration IDs |
| --- | --- | --- |
| Unsloth fork | [unslothai/llama.cpp](https://github.com/unslothai/llama.cpp) | U1–U5 |
| GenerelSchwerz fork (abbreviated as Generel) | [GenerelSchwerz/llama.cpp](https://github.com/GenerelSchwerz/llama.cpp) | G1–G7 |
| Strata | [Niko1221/Strata](https://github.com/Niko1221/Strata) | S01–S31 |

Complete launch configurations are recorded in the [llama.cpp configurations](configs/llama_cpp.json) and [Strata configurations](configs/strata.json); source commits are listed in [sources.json](docs/sources.json).
"Unsloth" identifies an engine fork here. The main GGUF weights came from ISTA-DASLab, as listed above.

## Generation throughput by configuration

The following tables list the higher-throughput configurations within each stated measurement group, sorted by throughput, together with their settings.
The fixed-length configuration comparisons summarize the initial 67 requests; the end-of-response table has been updated using the additional recheck with controlled process history.

Throughput is the **average tok/s over the generation interval**, excluding prefill and including thinking tokens. Repeated conditions use the median; conditions measured once use that single observation.
"Direct" input contains only the user prompt. "Harness" input adds the saved DeepSeek Harness system instructions and tool definitions to the same user prompt.

### llama.cpp: fixed-length generation with direct input

The top three configurations for direct input, thinking enabled, temperature=1, and generation stopped at a fixed token limit.
All three used **context=131,072, MTP disabled, 8 generation threads, and 20 prompt-processing threads**.

| Configuration | tok/s ↓ | Output length × runs | KV (K/V) | Expert cache (MiB) | Additional optimizations |
| --- | ---: | --- | --- | ---: | --- |
| G7 | 70.46 | 4,096 tokens × 2 | q4_0 / q4_0 | 21,000 | 6 options listed below enabled |
| G3 | 69.13 | 1,024 tokens × 1 | q8_0 / q8_0 | 20,000 | 6 options listed below enabled |
| G1 | 48.81 | 1,024 tokens × 1 | q8_0 / q8_0 | 18,000 | Disabled |

**Main launch arguments for G7** ([fork and build instructions, Japanese](docs/reproduce.md); complete arguments, including model paths, are under `G7` in [configs/llama_cpp.json](configs/llama_cpp.json)):

```text
--ctx-size 131072 --cache-type-k q4_0 --cache-type-v q4_0
--moe-expert-cache-mib 21000 --threads 8 --threads-batch 20
-ngl all --fit off --load-mode none --lazy-mode on --flash-attn on -b 512 -ub 512
--backend-sampling --decode-overlap --decode-boundary-overlap
--ple-prefetch --phase-aware-workspace --live-context-workspace
```

All three listed configurations used the GenerelSchwerz fork with MTP disabled and VRAM allocated to the expert cache. G3 used q8_0 KV.
The two G7 observations were 70.53 / 70.38 tok/s, before and after a server restart. G7 and G3 used different output lengths, cache budgets, and KV types; the small throughput difference cannot be attributed to KV alone.
The corresponding llama.cpp records are No.18 and 20 / No.11 / No.8. Measurements that reached the end of the response are listed under "Generation throughput through the end of the response."

### Strata: fixed-length generation with Harness input

The top five configurations for Harness input, thinking enabled, greedy decoding, and 2,048 generated tokens, with a server restart before each request.
All rows used **Q2_0 MTP, spec=4, spec-min-p=0.5, KV=int8, and expert-cache=auto**.

| Configuration | tok/s ↓ (runs) | Context | Expert profile | adapt-every | vram-reserve-mib | Free VRAM after generation (GiB) | Notes |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| S24 | 118.04 (3) | 32K | Expanded | 4 | 3,072 | 1.45–1.72 | Maximum context limited to 32K |
| S31 | 117.30 (3) | 256K | Expanded | 1 | 3,072 | 1.39–1.68 | Highest median among 256K configurations |
| S21 | 110.46 (1) | 128K | Expanded | 4 | 2,048 | 0.57 | Reference result with little free VRAM remaining |
| S29 | 109.15 (2) | 128K | Expanded | 4 | 3,072 | 1.51–1.69 | Larger VRAM reserve than S21 |
| S30 | 106.43 (3) | 256K | Original 8,000 entries | 1 | 700 | 4.46–4.49 | No profile expansion |

**Main launch arguments for S31** ([profile preparation, Japanese](docs/reproduce.md), [base arguments](configs/strata-base.json), and [configuration overrides](configs/strata.json)):

```text
--max-context 262144 --kv int8 --spec 4 --spec-min-p 0.5
--expert-profile artifacts/strata/expert-profile-expanded.bin --expert-cache auto
--vram-reserve-mib 3072 --adapt-every 1
```

S31 expands the expert profile, increases the number of GPU-resident expert slots to approximately 9,500, and adapts the cache every round. Shared settings were prefill=2048 and pcie-frac=0.55; the observed CPU worker count was 19.
S30 used the original distributed expert profile and left more free VRAM after generation than S31.
Free VRAM values were collected after the requests listed in the table; they are not the minimum values during generation.
The corresponding Strata records are No.24, 41, and 42 / No.31, 36, and 40 / No.21 / No.29 and 43 / No.30, 34, and 39, in table order.

### Generation throughput through the end of the response

Thinking was enabled, with three requests per cell and a server restart before every request.
Values are the **median (minimum–maximum)** generation throughput in tok/s. Output lengths differ between requests.

| Configuration | Direct input: tok/s | Harness input: tok/s |
| --- | ---: | ---: |
| llama.cpp G7 | **62.32** (61.84–62.34) | **63.50** (62.01–63.56) |
| Strata S31 | **99.25** (97.03–105.78) | **110.40** (91.08–128.05) |

S31 Harness throughput varied substantially, and one request was slower than all three direct-input requests.
S31 also had a higher Harness median when output was capped at the same 2,048 tokens, but repeating identical input changed both throughput and generated content; the cache-only effect could not be isolated.
The [complete recheck report, Japanese](docs/cache_recheck.md) includes output lengths, MTP acceptance, comparisons at the same 2,048-token cap, and paired repeats of the same input.

**Discussion (hypothesis)**

One possible explanation is that the Harness instructions led to earlier code generation, making MTP draft tokens easier to predict correctly.
Strata commits consecutive matching draft tokens together, so accepting more tokens per verification pass can increase throughput ([implementation used](https://github.com/Niko1221/Strata/blob/6c4c8c1dfafc16fa0ea7fc80c12c79f93b9f7eee/src/program/generate.cpp)).

In the recheck with exactly 2,048 generated tokens, two Harness requests moved from brief reasoning to code generation, while all three direct-input requests reached the cap during reasoning.
Median MTP acceptance was 82.18% for Harness input and 63.50% for direct input.
The remaining Harness request also reached the cap during reasoning and had lower throughput and acceptance than the two that moved to code generation.
The throughput difference persisted with equal output counts, so total output length alone cannot explain it.

However, input length, expert placement, and runtime state also differed; the causal effect of MTP was not isolated.
There were only three observations per condition, and statistical significance has not been established.

Harness measurements end when the model finishes emitting its tool calls; tool execution time is excluded.
Every request in this table starts in a fresh process with prompt KV reuse disabled. OS file caches were not purged.
Results with thinking disabled and the recorded checks of generated code remain in the initial [llama.cpp report](docs/llama_cpp.md) and [Strata report](docs/strata.md), both in Japanese.
The reported rates apply to the listed environment and shared prompt. Context capacity, KV, MTP, sampling, and templates differ between engines; the scope of comparisons is described in the [methodology, Japanese](docs/methodology.md).

## Measurement counts

Initial parameter exploration:

| Measurement group | Server configurations | Conditions including input and generation settings | Generation requests |
| --- | ---: | ---: | ---: |
| llama.cpp: Unsloth / GenerelSchwerz | 12 (U1–U5, G1–G7) | 21 | 22 |
| Strata | 31 (S01–S31) | 36 | 45 |
| **Total** | **43** | **57** | **67** |

The search covered MTP, CPU threads, GPU expert caching, KV formats, context capacity, transfer options, cache adaptation, and related parameters.
It was not an exhaustive search of all combinations. AtomicBot was investigated but not executed and is excluded from the measurements.

The cache recheck adds 30 requests using the existing G7/S31 configurations, bringing the total to 97 requests.
It comprises 12 full responses, 12 requests capped at 2,048 tokens in fresh processes, and 6 repeats within the same process.
It compares direct/Harness inputs and cache history without adding new launch configurations.
The [recheck report, Japanese](docs/cache_recheck.md) records its conditions and all 30 requests separately.

## Reproduction

1. Prepare the pinned engine versions and model files using the [reproduction guide, Japanese](docs/reproduce.md). Weights and executables are not included in this repository.
2. Use the locations in [configs/paths.example.json](configs/paths.example.json). To change them, put overrides in `configs/paths.local.json`, which is excluded from Git.
3. Run the commands from the repository root. The scripts use the Python 3.10+ standard library.

```powershell
# Preview launch arguments only; no server or generation is started
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json --dry-run
python scripts/run_benchmarks.py --plan plans/strata-quick.json --dry-run

# Stop other inference servers first; run one engine at a time
python scripts/run_benchmarks.py --plan plans/llama_cpp-quick.json
python scripts/run_benchmarks.py --plan plans/strata-quick.json
```

New results are saved under `runs/`, which is excluded from Git.
The initial 67 requests were measured before path normalization; the published Harness inputs are not token-for-token identical to those original inputs.
The additional 30 requests were measured using the published inputs and can be reproduced with the [dedicated plan and commands, Japanese](docs/reproduce.md#キャッシュ条件を揃えた再測定).

## Repository contents

| Location | Contents |
| --- | --- |
| [docs/reproduce.md](docs/reproduce.md) | Model downloads, builds from pinned sources, and reproduction commands (Japanese) |
| [docs/methodology.md](docs/methodology.md) | Counting units, throughput definitions, comparison conditions, and the effects of anonymization (Japanese) |
| [configs/](configs/) / [plans/](plans/) | Arguments for 43 configurations and the order and restart boundaries of the initial 67 and additional 30 requests |
| [results/llama_cpp/](results/llama_cpp/) / [results/strata/](results/strata/) | CSV, JSONL, saved requests and responses, and startup and measurement logs |
| [docs/cache_recheck.md](docs/cache_recheck.md) / [results/cache-recheck/](results/cache-recheck/) | Comparisons, summaries, and complete records for the 30 additional cache rechecks |
| [fixtures/harness-request.json](fixtures/harness-request.json) | Anonymized Harness input; tools are defined but not executed |
| [artifacts/generated/](artifacts/generated/) | HTML extracted from saved responses, including an uncorrected failure example |
| [scripts/](scripts/) | Request replay, expert-profile expansion, and asset hash comparison |
| [patches/strata-local.patch](patches/strata-local.patch) | Local Strata changes already applied before measurement |
| [docs/sources.json](docs/sources.json) / [docs/assets.json](docs/assets.json) | Source commits, build information, and SHA-256 hashes of models and other assets |
| [results/publication-manifest.json](results/publication-manifest.json) | Hash correspondence between original records and published copies |

Original scripts, configuration templates, and explanatory documents in this repository are available under the [MIT License](LICENSE). See [NOTICE](NOTICE.md) for included third-party material and the terms applicable to models and engines.
