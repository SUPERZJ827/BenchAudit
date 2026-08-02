# SVAMP-Platinum 实验环境

## 版本与系统

- Git HEAD：`c6f62ceb5d2a63f1037af09884d03af49979a4bf`
- Git 工作树状态：

```text
M benchcore/llm_client.py
 M configs/llm_deepseek.json
 M scripts/run_direct_llm_baseline.py
 M scripts/run_svamp_pilot.py
 M tests/test_llm_client.py
?? EXPERIMENT_ENV.md
?? SVAMP_ERROR_ANALYSIS.md
?? SVAMP_RESULTS.md
?? logs/
?? pip_freeze.txt
?? scripts/analyze_svamp_results.py
```

- Python：`3.10.12`
- Python executable：`/usr/bin/python`
- 操作系统：`Linux-6.8.0-114-generic-x86_64-with-glibc2.35`
- 主要依赖：

```text
benchaudit: not installed in current interpreter
defusedxml: not installed in current interpreter
pyarrow: not installed in current interpreter
pandas: not installed in current interpreter
openpyxl: not installed in current interpreter
xlrd: not installed in current interpreter
python-docx: not installed in current interpreter
python-pptx: not installed in current interpreter
pdfplumber: not installed in current interpreter
pytest: not installed in current interpreter
requests==2.25.1
```

项目 `.venv`（用于完整测试）的主要依赖：

```text
benchaudit==0.2.0
defusedxml==0.7.1
pyarrow==25.0.0
pandas==2.3.3
openpyxl==3.1.5
xlrd==2.0.2
python-docx==1.2.0
python-pptx==1.0.2
pdfplumber==0.11.10
pytest==9.1.1
requests==2.34.2
```

## LLM 配置

- 配置文件：`configs/llm_deepseek.json`
- 模型：`deepseek-v4-flash`
- Base URL：`https://api.deepseek.com`
- API Key 环境变量名：`DEEPSEEK_API_KEY`（未读取或记录实际值）
- 安全配置快照：

```json
{
  "model": "deepseek-v4-flash",
  "base_url": "https://api.deepseek.com",
  "temperature": 0.0,
  "thinking": "disabled",
  "timeout": 120,
  "max_tokens": 5000,
  "cache_path": "reports/llm_cache.jsonl",
  "dry_run": false
}
```

## 实验命令

单次 LLM 基线：

```bash
python scripts/run_direct_llm_baseline.py \
  --input datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --tag junior_svamp_naive \
  --truth-field metadata.audit_label \
  --truth-clean-value clean \
  --model deepseek \
  --workers 8 \
  --progress-every 10
```

BenchAudit 结构化审计：

```bash
python scripts/run_svamp_pilot.py \
  --input datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --tag junior_svamp_benchaudit \
  --model deepseek \
  --auditors gold,question,quantity,event \
  --mode cascade \
  --workers 8 \
  --progress-every 10 \
  --allow-remote-data-egress
```

## 输入与缓存

- 固定 manifest：`experiments/svamp_platinum_pilot100.manifest.json`
- 数据集：`datasets/svamp_platinum/svamp_platinum_all.jsonl`
- 单次 LLM 缓存：`reports/junior_svamp_naive_direct_llm_cache.jsonl`；存在并使用；100 行、100 个唯一 key、0 个重复 key。
- BenchAudit 缓存：`reports/junior_svamp_benchaudit_cache.jsonl`；存在并使用；662 行、662 个唯一 key、0 个重复 key。

本文件不包含 API Key；生成过程未调用 API、未修改 manifest、报告或缓存。
