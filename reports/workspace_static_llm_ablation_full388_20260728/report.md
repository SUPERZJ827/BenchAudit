# WorkspaceBench full388 静态 LLM 配对消融

> 项目：**BenchAudit**  
> 数据：388 items / 7,393 rubrics  
> 执行：不运行 benchmark task；仅做确定性静态检查与 DeepSeek 静态语义审计

## 结论

本实验比较的是同一批数据上的 **Rules-only** 与
**DeepSeek-assisted BenchAudit**。历史名称 `BenchCore` 不是另一个系统，
只是旧 runner 标签；本报告不使用它指代当前实现。

Rubric 指标只是在既有证据化复核子集上的条件指标，不是完整人工真值：
现有文件明确记录为双阶段 LLM 复核。未标注 rubric 不被当成 clean。

## 1. 输出文件名：全库确定性扫描参考

已知正类是全库确定性复核得到的
`task_vs_contract_filename`，共
12 个 item。下表为便于
配对而采用严格 reference convention：其余 full388 item 暂按未命中参考
处理。由于新的语义抽取可能发现旧扫描规则覆盖不到的文件名冲突，FP
在这里表示“未进入旧参考集”，**不等价于已经人工证伪**；因此主要看
已知正类召回和两臂差异，Precision/F1 只作 reference-alignment 指标。

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 0 | 5 | 12 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 12 | 48 | 0 | 0.200 | 1.000 | 0.333 |

- Rules-only 候选 item：5
- LLM task-contract 候选 item：57
- Assisted 相对 rules 新增：55
- Assisted 相对 rules 丢失：0
- 另外命中旧确定性扫描中的 task-level placeholder leak：
  6/
  17 items（不计入上表 12 个
  `task_vs_contract_filename` 正类）

## 2. Rubric grounding：reviewed-reference 条件指标

计分子集包含
300 个“较可信真问题”和
100 个“较可信非问题”；
159 个分歧项不参与 P/R/F1。

### 2.1 Attempted-full388 保守口径

本表将 operational unknown 计作“未检出”。它回答整次审计任务实际交付了
多少命中，不是排除 API 故障后的纯模型能力估计。

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 0 | 0 | 300 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 64 | 17 | 236 | 0.790 | 0.213 | 0.336 |

### 2.2 Evaluable-subset 条件口径

仅保留 scanner/verifier 均完成的既有正/负标注：
254/
400
（覆盖率 63.50%）。

| 系统 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Rules-only | 0 | 0 | 186 | 0.000 | 0.000 | 0.000 |
| DeepSeek-assisted BenchAudit | 64 | 17 | 122 | 0.790 | 0.344 | 0.479 |

全 7,393 rubrics 的 operational coverage 为
64.26%；
2642 条 rubric 因 API/响应问题保持
unknown。该覆盖缺口主要由本轮 DeepSeek 余额耗尽造成，补充余额后应只重跑
这些 unknown，不应重跑或改动已完成 verdict。

全量候选与复核负担：

- Rules-only rubric candidates：0
- DeepSeek-assisted rubric candidates：677
- 涉及 item：222
- review burden：9.16%
- 在 operational-evaluable rubrics 中的 review burden：
  14.25%
- Assisted 新增：677
- 尚无明确 reviewed label 的新增候选：
  569（不计作 FP）

## 3. Input/output role confusion

| 指标 | 数量 |
|---|---:|
| LLM 抽取的显式路径 | 259 |
| 映射到 output inventory | 197 |
| 仅命中 input inventory、被本地抑制 | 1 |
| 两边均未命中、形成 mismatch 候选 | 61 |
| 模型响应未通过 schema/grounding 校验的 item | 8 |

被 input inventory 命中的路径只记录为抽取角色混淆，不报告 benchmark
缺陷。

## 4. Review-only 安全门

| 指标 | 数量 |
|---|---:|
| LLM-derived findings | 3384 |
| review-only findings | 3384 |
| 越过 review ceiling | 0 |
| LLM-derived confirmed | 0 |
| operational failures | 2650 |
| 其中明确为 API balance exhausted | 2631 |

验收要求是越权与 confirmed 均为 0。

## 5. API 与复现

`taskcontract` 运行统计显示 0 次本轮 API request，是因为 388 个响应均从
前一轮成功落盘的精确 prompt cache 重放；这不表示文件名 arm 从未调用
LLM。其实际模型响应覆盖是 388/388。

```json
{
  "grounding": {
    "llm": {
      "api_attempts": 10763,
      "api_failures": 2906,
      "api_successes": 7857,
      "base_url": "https://api.deepseek.com",
      "cache_entries": 12161,
      "cache_hits": 0,
      "cache_path": "/tmp/benchaudit-workspace-static-llm-20260728/reports/workspace_static_llm_ablation_full388_20260728/grounding_cache.jsonl",
      "completion_tokens": 6599068,
      "configured_votes": 1,
      "invalid_responses": 55,
      "max_api_attempts": null,
      "max_tokens": 5000,
      "model": "deepseek-v4-flash",
      "observed_token_stop": null,
      "observed_token_stop_semantics": "soft stop after provider-reported usage; not a concurrent hard cap",
      "prompt_tokens": 31306958,
      "singleflight_shared_failures": 0,
      "singleflight_shared_results": 0,
      "singleflight_waits": 0,
      "temperature": 0.0,
      "thinking": null,
      "total_tokens": 37906026,
      "truncated_responses": 10,
      "vote_temperature": 0.3
    },
    "new_items": 388,
    "resumed_items": 0,
    "wall_seconds": 3697.753645314835
  },
  "taskcontract": {
    "llm": {
      "api_attempts": 0,
      "api_failures": 0,
      "api_successes": 0,
      "base_url": "https://api.deepseek.com",
      "cache_entries": 388,
      "cache_hits": 388,
      "cache_path": "/tmp/benchaudit-workspace-static-llm-20260728/reports/workspace_static_llm_ablation_full388_20260728/task_contract_cache.jsonl",
      "completion_tokens": 0,
      "configured_votes": 1,
      "invalid_responses": 0,
      "max_api_attempts": null,
      "max_tokens": 5000,
      "model": "deepseek-v4-flash",
      "observed_token_stop": null,
      "observed_token_stop_semantics": "soft stop after provider-reported usage; not a concurrent hard cap",
      "prompt_tokens": 0,
      "singleflight_shared_failures": 0,
      "singleflight_shared_results": 0,
      "singleflight_waits": 0,
      "temperature": 0.0,
      "thinking": null,
      "total_tokens": 0,
      "truncated_responses": 0,
      "vote_temperature": 0.3
    },
    "new_items": 388,
    "resumed_items": 0,
    "wall_seconds": 0.2507064510136843
  }
}
```

Provenance：

```json
{
  "artifact_view": {
    "copied": 0,
    "files": 3854,
    "hardlinked": 3854,
    "root": "/home/zhoujun/llmdata/after623/.benchaudit_workspace_static_artifact_view_20260728",
    "rows": 388,
    "schema_version": "workspace-artifact-view-v1",
    "source_symlinks": 3854,
    "source_values_changed": false,
    "total_bytes": 1912650383
  },
  "dataset": "/home/zhoujun/llmdata/after623/datasets/workspacebench/full.jsonl",
  "dataset_sha256": "2e3d8fd1f5a741b9e6b73ebab9ce23e26ce054527b4f3477de8fdd950aad9dbe",
  "full388": true,
  "git_head": "3139943b2b2d9ccd4a35c621c787b6bb92710658",
  "items": 388,
  "objective_reference": "/home/zhoujun/llmdata/after623/WorkspaceBench_full388_Claude证据化逐条标注_20260720.md",
  "objective_reference_sha256": "ffd43eb84ad714766bfd8af7d63871f1aee2266a031be471a89a4475604ca684",
  "protocol": "workspace-static-llm-paired-v1-20260728",
  "reviewed_reference": "/home/zhoujun/llmdata/after623/WorkspaceBench_full388_Codex证据化逐条标注_20260720.md",
  "reviewed_reference_sha256": "fa8fbef8497ac2f8f39b21975e28dd88005a5d2541db07cbe162fb04558978cf",
  "rubrics": 7393,
  "workers": 64
}
```

## 6. 解释边界

1. 输出文件名的 12 个参考正类来自全库确定性扫描，但其余 item 没有逐条
   人工 clean 标签；因此已知正类 Recall 可直接解读，Precision/F1 只能
   解读为对该窄参考集的 alignment，新增项需要复核。
2. Rubric grounding 的参考集由旧系统候选触发并由双阶段 LLM 复核，
   存在 selection bias；指标只回答“在已明确复核的候选上，哪一臂覆盖
   更多可信问题且少命中可信非问题”。
3. 全量新增候选没有被自动记成 FP，也不能自动宣称为 TP。
4. LLM 的作用是提高静态语义候选召回；confirmed 仍需要独立 replay、
   约束求解或真实执行。
5. 本轮 rubric arm 不是 100% operational-complete：API 余额耗尽使
   2642 条 rubric 保持 unknown。
   因此必须同时报告 attempted-full388 与 evaluable-subset 两套口径。
