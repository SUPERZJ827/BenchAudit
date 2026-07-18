# 探针多样性 step 2:模型多样性能否提升盲点召回?

> 60 题(Pandas+Numpy 各 30),每模型 temp=0、gen_slack=0 生成探针,取存活/过严信号并集。仅生成模型不同,执行/裁决一致。


## 各模型 flagged

| 模型 | flagged 题数 | 题 |
|---|---:|---|
| deepseek | 2 | [11, 308] |
| openai__gpt-4o-mini | 2 | [11, 294] |
| qwen__qwen-2.5-72b-instruct | 2 | [294, 308] |
| meta-llama__llama-3.3-70b-instruct | 0 | — |

## 并集 vs DeepSeek 单模型

- DeepSeek 单模型 flagged: **2** — [11, 308]
- 全模型并集 flagged: **3** — [11, 294, 308]
- **并集比 DeepSeek 新增**: 1 题 — 294(priority)

## 结论

- 新增里 triage=priority 才是真盲点召回提升;by_design/ambiguous 是多解噪声。
- **模型多样性有效**:不同模型 temp=0 的显然变异命中了 DeepSeek 漏掉的盲点 → 多模型是执行层召回的真杠杆。

## 人工核实 id=294(新盲点,已确认真实)

不只信 triage=priority,亲自查了存活变异:

- 任务:去除 nan,返回 list of lists,期望**两行** `[[1400,1500,1600],[1800,1700]]`(唯一输出)。
- gpt-4o-mini 生成的存活变异:`[x[i,row] for i,row in enumerate(~np.isnan(x)) if i%2==0]`——加 `if i%2==0` **只返回第一行**,丢掉第二行。
- gold=2 行、probe=1 行,`loose_differs=True`(输出确实不同),但 **`harness.pass=True`**——**评测器接受了丢掉一半输出的错解**。
- 任务唯一输出 → 这是**真的评测器完整性缺陷(over-lenient)**,不是多解。

DeepSeek 的探针里没有这个"丢行"变异,gpt-4o-mini/qwen 有 → **模型异质性揭示了 DeepSeek 想不到的错法**,验证了 step 1 的推断。

## 诚实边界

- 增益绝对值小(60 题 +1 真盲点);但机制被证实,且增益随 benchmark 缺陷密度放大。
- **模型质量差异大**:llama-3.3-70b flag 0(连 id=11 都漏)= 无用探针生成器;增益全来自 gpt-4o-mini + qwen。**多模型要选对模型,不是越多越好**。
- 仍全 review、0 自动 confirmed。