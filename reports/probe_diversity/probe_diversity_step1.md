# 探针多样性 step 1:同模型 temperature 采样能否提升盲点召回?

> 60 题(Pandas+Numpy 各 30),DeepSeek temp=0.7、无缓存、3 轮、gen_slack=0(与 temp=0 baseline 唯一差异=温度+轮数)。取存活/过严信号并集。


## 结果

- **temp=0 baseline(单次)flagged**: 2 题 — [11, 308]
- temp=0.7 round 1 flagged: 0 题 — []
- temp=0.7 round 2 flagged: 0 题 — []
- temp=0.7 round 3 flagged: 0 题 — []
- **temp=0.7 三轮并集 flagged**: 0 题 — []

- **并集比 baseline 新增**: 0 题 — 无
- **baseline 有但并集漏掉**: 2 题 — [11, 308]

## 判读

- 新增题里 triage=priority 的才是**真盲点召回提升**;by_design/ambiguous 是多解任务噪声。
- 若并集 ≈ baseline(新增都是噪声或没有)→ 同模型采样多样性无用,多模型多半也不值得花钱。
- 若并集显著 ⊃ baseline 且新增含 priority → 多样性有效,step 2(多模型)值得验证。

## 结论:同模型 temperature 采样 **不提召回,反而丢信号**

temp=0.7 三轮全 flag **0/60**,而 temp=0 baseline flag 2(含真缺陷 id=11)→ **加温不仅没新增盲点,还丢了 baseline 的**。

**机制诊断**(id=11 在 temp=0.7 重跑 3 次):覆盖完整(equiv 3/3、mutant 4/4,**非质量崩塌**),但**变异全被杀、无一命中时区盲点**;temp=0 那次生成的变异恰好命中(存活)。原因:**对评测器盲点,temp=0 生成的是"最显然"的错法**——"移除时区"任务最显然的错就是"不移除时区",恰好命中盲点;**temp=0.7 把变异发散到别处,偏离了最能揭示盲点的那个显然错法**。

**对 step 2 的启示(重要)**:step 1 证否的是 **temperature 多样性**,不是模型多样性。二者不同:temperature 是在**同一模型**的输出分布里游走(偏离其显然错法→有害);多模型是**不同模型各自的"显然错法"不同**(A 想到"不移除时区",B 可能想到"移除但改 dtype")。所以 step 2 的正确设计是**多个不同模型各在 temp=0 生成其显然变异,取并集**——每个模型贡献它最显然、最可能揭示盲点的探针。step 1 反而**收窄并明确了 step 2**:多模型要用 temp=0,不是加温。