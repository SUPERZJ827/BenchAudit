# Pilot Experiments

## 1. 固定实验集

### MMLU-Redux Pilot 200

- 200 条；
- 排除已经参与开发的原始前 120 条；
- 100 条 `ok`；
- 100 条人工缺陷；
- 按 `metadata.subject` 和 `metadata.error_type` 分层；
- seed：`20260624`。

文件：

```text
mmlu_redux_pilot200.jsonl
mmlu_redux_pilot200.manifest.json
```

人工缺陷分布：

```text
bad_question_clarity: 30
wrong_groundtruth: 24
no_correct_answer: 13
bad_options_clarity: 12
multiple_correct_answers: 12
expert: 9
```

### GSM8K-Platinum Pilot 110

- 110 条；
- `revised`: 10；
- `consensus`: 50；
- `verified`: 50；
- seed：`20260624`。

文件：

```text
gsm8k_platinum_pilot110.jsonl
gsm8k_platinum_pilot110.manifest.json
```

## 2. MMLU-Redux 实验

推荐直接运行一键脚本：

```bash
python scripts/run_mmlu_pilot.py --tag open_match_v1
```

脚本会自动运行下面的 audit 和 compare 命令。

使用原始数据和 manifest，避免依赖 offset：

```bash
source ~/.bashrc

python -m benchcore.cli audit \
  datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl \
  --manifest experiments/mmlu_redux_pilot200.manifest.json \
  --llm-audit \
  --llm-config configs/llm_deepseek.json \
  --llm-cache reports/mmlu_redux_pilot200_llm_cache.jsonl \
  --out reports/mmlu_redux_pilot200_report.json \
  --md reports/mmlu_redux_pilot200_report.md \
  --print-summary
```

计算监督指标：

```bash
python -m benchcore.cli compare \
  datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl \
  --manifest experiments/mmlu_redux_pilot200.manifest.json \
  --report reports/mmlu_redux_pilot200_report.json \
  --truth-field metadata.error_type \
  --clean-value ok \
  --out reports/mmlu_redux_pilot200_comparison.json \
  --md reports/mmlu_redux_pilot200_comparison.md \
  --print-summary
```

## 3. GSM8K-Platinum 实验

当前先运行非 LLM 方法：

```bash
python -m benchcore.cli audit \
  datasets/gsm8k_platinum/gsm8k_platinum_aligned_all.jsonl \
  --manifest experiments/gsm8k_platinum_pilot110.manifest.json \
  --out reports/gsm8k_platinum_pilot110_report.json \
  --md reports/gsm8k_platinum_pilot110_report.md \
  --print-summary
```

后续需要为这 110 条生成至少两个独立 solver 输出，再由
`DifferentialCandidateChecker` 聚合。

监督比较：

```bash
python -m benchcore.cli compare \
  datasets/gsm8k_platinum/gsm8k_platinum_aligned_all.jsonl \
  --manifest experiments/gsm8k_platinum_pilot110.manifest.json \
  --report reports/gsm8k_platinum_pilot110_report.json \
  --truth-field metadata.cleaning_status \
  --clean-value consensus \
  --clean-value verified \
  --out reports/gsm8k_platinum_pilot110_comparison.json \
  --md reports/gsm8k_platinum_pilot110_comparison.md \
  --print-summary
```

## 4. 重新生成实验集

MMLU-Redux：

```bash
python -m benchcore.cli sample \
  datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl \
  --size 200 \
  --seed 20260624 \
  --stratify-field metadata.subject \
  --stratify-field metadata.error_type \
  --label-field metadata.error_type \
  --clean-value ok \
  --defect-fraction 0.5 \
  --exclude-first 120 \
  --sample-out experiments/mmlu_redux_pilot200.jsonl \
  --manifest-out experiments/mmlu_redux_pilot200.manifest.json
```

GSM8K-Platinum：

```bash
python -m benchcore.cli sample \
  datasets/gsm8k_platinum/gsm8k_platinum_aligned_all.jsonl \
  --size 110 \
  --seed 20260624 \
  --stratify-field metadata.cleaning_status \
  --label-field metadata.cleaning_status \
  --clean-value consensus \
  --clean-value verified \
  --defect-fraction 0.090909 \
  --sample-out experiments/gsm8k_platinum_pilot110.jsonl \
  --manifest-out experiments/gsm8k_platinum_pilot110.manifest.json
```
