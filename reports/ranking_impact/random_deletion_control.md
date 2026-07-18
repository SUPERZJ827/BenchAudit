# 随机删题对照:冠军易主是真信号还是删得多的假象?

> 对每个 subject 删**相同数量**的随机题,bootstrap 2000 次,看真实删题(审计器/第三方)导致的冠军易主是否显著高于等量随机删题。仅用缓存答题,无 LLM 调用。


## 汇总

| 删题依据 | 考察 subject 数 | 真实冠军易主 | 随机删题均值 | 随机 95% 区间 | p 值 | 结论 |
|---|---:|---:|---:|:--:|---:|---|
| 我们审计器检出 | 28 | 9 | 7.55 | [4, 12] | 0.3183 | 不显著(可能只是删得多) |
| 第三方 MMLU-Redux 标注 | 16 | 2 | 3.64 | [1, 6] | 0.9485 | 不显著(可能只是删得多) |

## 逐 subject:我们审计器检出(按随机翻转概率升序)

> `真实翻转`=真实删题是否换冠军;`随机翻转概率`=删同样数量随机题时换冠军的频率。真实翻转=1 且随机概率低,才是审计器**定位到了关键题**,而非删多了。

| subject | 题数 | 删除数 k | 真实翻转 | 随机翻转概率 |
|---|---:|---:|:--:|---:|
| abstract_algebra | 24 | 5 | · | 0.000 |
| computer_security | 16 | 5 | · | 0.000 |
| professional_accounting | 21 | 8 | · | 0.000 |
| international_law | 18 | 6 | · | 0.000 |
| marketing | 18 | 4 | · | 0.000 |
| philosophy | 17 | 3 | ✔ | 0.018 |
| formal_logic | 23 | 11 | · | 0.091 |
| human_sexuality | 27 | 8 | · | 0.122 |
| college_medicine | 27 | 8 | · | 0.137 |
| econometrics | 17 | 4 | · | 0.138 |
| miscellaneous | 19 | 3 | · | 0.165 |
| astronomy | 19 | 4 | ✔ | 0.179 |
| high_school_biology | 20 | 5 | · | 0.189 |
| high_school_macroeconomics | 18 | 5 | · | 0.193 |
| machine_learning | 23 | 8 | · | 0.226 |
| professional_psychology | 19 | 6 | · | 0.234 |
| high_school_psychology | 17 | 5 | ✔ | 0.273 |
| professional_law | 30 | 10 | · | 0.291 |
| human_aging | 24 | 4 | · | 0.343 |
| high_school_european_history | 26 | 10 | ✔ | 0.375 |
| logical_fallacies | 39 | 16 | · | 0.382 |
| high_school_chemistry | 16 | 4 | ✔ | 0.409 |
| security_studies | 15 | 6 | ✔ | 0.422 |
| public_relations | 20 | 7 | · | 0.449 |
| global_facts | 21 | 13 | · | 0.599 |
| college_chemistry | 38 | 23 | ✔ | 0.712 |
| virology | 63 | 52 | ✔ | 0.800 |
| business_ethics | 24 | 14 | ✔ | 0.806 |

## 逐 subject:第三方 MMLU-Redux 标注(按随机翻转概率升序)

> `真实翻转`=真实删题是否换冠军;`随机翻转概率`=删同样数量随机题时换冠军的频率。真实翻转=1 且随机概率低,才是审计器**定位到了关键题**,而非删多了。

| subject | 题数 | 删除数 k | 真实翻转 | 随机翻转概率 |
|---|---:|---:|:--:|---:|
| abstract_algebra | 24 | 8 | · | 0.000 |
| computer_security | 16 | 3 | · | 0.000 |
| professional_accounting | 21 | 5 | · | 0.000 |
| international_law | 18 | 5 | · | 0.000 |
| machine_learning | 23 | 3 | · | 0.019 |
| human_sexuality | 27 | 5 | · | 0.048 |
| formal_logic | 23 | 12 | · | 0.127 |
| high_school_biology | 20 | 3 | · | 0.140 |
| professional_psychology | 19 | 3 | · | 0.153 |
| miscellaneous | 19 | 5 | · | 0.263 |
| logical_fallacies | 39 | 10 | · | 0.270 |
| professional_law | 30 | 13 | · | 0.386 |
| public_relations | 20 | 6 | · | 0.408 |
| global_facts | 21 | 9 | · | 0.447 |
| virology | 63 | 41 | ✔ | 0.670 |
| college_chemistry | 38 | 23 | ✔ | 0.714 |

## 怎么读这张表

- **p < 0.05**:真实删题换冠军的 subject 数,显著多于等量随机删题——排名扰动是**审计器定位到关键缺陷题**的结果,不是删得多的机械假象。
- **某 subject 真实翻转✔但随机概率也高(如 >0.5)**:该 subject 的换冠军对删哪几题不敏感,证据力弱,不应单独拿来当卖点。
- **真实翻转✔且随机概率低**:审计器精准命中了那道扭转排名的缺陷题,是最硬的单点证据。