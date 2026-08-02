# BenchAudit Verifier 拓扑上游链接更正结果

> 日期：2026-08-02
>
> 分支：`research/verifier-topology-preflight-20260802`
>
> 裁决：`NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`
>
> 状态：本宿主实验线永久收口

## 1. 首先修正旧归因

提交 `131727f` 的双引擎报告将 Docker 的 502 写成“proxy 无法连接 canonical
upstream，因此本宿主不支持冻结拓扑”。这一定性过强。

独立宿主探针得到：

```text
直连 13.35.202.121:443       -> TimeoutError, 6.006s
经 127.0.0.1:17890 访问 HF   -> HTTP 200, 0.463s
```

而当时 audited proxy 的唯一上游代码是裸
`socket.create_connection(canonical_host, 443)`，没有链接宿主代理。两条 502 的正确
reason code 是：

```text
FROZEN_PROXY_HAS_NO_UPSTREAM_CHAIN_ON_HOST_WITHOUT_DIRECT_EGRESS
```

因此原 Docker 运行没有回答“受限出口拓扑能否工作”；它只证明“direct-only proxy 在
无 direct egress 的宿主上失败”。旧产物未修改，机器可读更正见
`docs/experiments/verifier_topology_preflight_docker_20260802/causal_correction_addendum.json`。

## 2. 为什么允许一次更正运行

这不是第四次 Podman 拓扑迭代，也没有换运行时。只增加一跳 nested CONNECT：

```text
verifier -> audited exact-authority proxy
         -> pinned host proxy endpoint
         -> canonical host
```

其余五探针、双网络、literal-IP listen、candidate `--network none` 与所有安全门均未
改变。执行前冻结了：

- Docker 29.4.1 executable/version hash；
- `mihomo-host-17890-v1` 的 systemd service、PID、启动 monotonic timestamp；
- `/usr/bin/mihomo` 版本与 SHA-256；
- systemd unit SHA-256；
- listener inode 与 cgroup；
- 容器内 endpoint 必须由 inspected egress gateway + code-owned port 17890 导出。

宿主代理配置对实验用户不可读，因此本轮显式标为 protocol deviation 且永不
confirmation-eligible。实现提交 `06661d0` 在 live run 前完成；当前工作树与 fresh
clone 均先取得 832 passed。

## 3. 唯一一次运行结果

### 3.1 上游链接仍未建立

Docker 建立的 egress network gateway 为 `10.252.83.1`，因此 proxy 使用冻结端点：

```text
10.252.83.1:17890
```

fetch session 收到两个 downstream CONNECT，authority 均精确为
`huggingface.co:443`。但两次连接 host-proxy endpoint 均在 15 秒超时：

```text
accepted = 2
allowed = 0
upstream_failed = 2
reason = timed out
upstream HTTP response observed = false
```

所以 502 发生在 nested CONNECT 的 TCP 建链之前，不是 mihomo 返回的 HTTP 错误；
exact Git fetch exit 128，blob OID/content 均未取得。不能声称 Git fetch 只使用单一
authority，这个核心问题仍未被测到。

本轮不再尝试 host-gateway alias、修改防火墙、其他宿主地址或第二次运行。

### 3.2 live reject 取得了真阳性

独立 reject session 完整通过：

| 项 | 结果 |
|---|---:|
| downstream authority | `example.com:443` |
| HTTP status | 403 |
| forbidden | 1 |
| allowed | 0 |
| upstream_failed | 0 |
| unparsed/其他 disposition | 0 |

该请求在任何 upstream dial 之前被本地拒绝。这证明当次运行的真实 proxy 实例不是
“永不拒绝”实现，也证明 upstream-chain 改动没有绕过 allowlist 的拒绝分支。

### 3.3 隔离负控继续通过

| 探针 | 结果 | 解释 |
|---|---|---|
| 清空 proxy 环境后直连 12 个 canonical IP | 全部失败 | corroboration only |
| 直连 `1.1.1.1:443` | 失败 | corroboration only |
| verifier 容器 DNS | 失败 | corroboration only |
| candidate argv | 精确 `--network`, `none` | 回归通过 |

这些负控不能弥补 canonical CONNECT/fetch 未完成，但可排除“为了上游链接而给 verifier
或 candidate 打开直连出口”。

## 4. 最终解释

四层结果应分开描述：

1. **原 Docker direct-only 运行**：失败归因已更正；根因是代理没有上游链接而宿主无
   direct egress。
2. **上游链接实现**：单元/对抗测试可工作，包括 200 relay、403/407/502、malformed、
   EOF、timeout、零 direct fallback。
3. **本次真实 Docker 拓扑**：proxy container 到 inspected host gateway 的
   `:17890` TCP 连接超时，故 canonical fetch 仍不可测。
4. **白名单拒绝与隔离负控**：在真实 topology 中通过。

最终 reason code 为：

```text
CONTAINER_TO_PINNED_HOST_PROXY_ENDPOINT_TIMEOUT
```

这不是“Docker 一般不能做受限出口”，也不是“mihomo 拒绝了 HF”；证据只支持“本次
冻结的 container-to-host-proxy endpoint 不可达”。

## 5. 产物哈希

| Artifact | SHA-256 |
|---|---|
| frozen correction plan | `536ca2f69ed3461572a4190851e4c7c69e48a5687455b58aa373470c569982a1` |
| proxy implementation | `b4df52a791dc1203a8ef2bca0ea901cbe784841caed3a0402c8b5cbe9014396b` |
| runner | `5ce81314502f44926286f89606a09437c72778da846d5dc86dfc76fad13e8318` |
| terminal receipt | `663483d7bb123345aa085fdd739830930336a2b9f474b2e6dd3697370bdca291` |
| fetch proxy raw | `54d6ceeffc138e6379e9d8f43235a74dffc6f960ef202b68de0456043307da75` |
| fetch proxy stable | `2d50f353f6ca838dc7f18d500aee797b1a2b3d9fe234c9404a26092e6ed811ac` |
| fetch verifier result | `309b69ae43ea7a4ee66f0cee3f1f50bf24a1052a274a211d7062a57e1fc13622` |
| reject proxy raw | `0725364c9ef20cc3dc47ec50f48aa05c14e1070d8ad3c18cfcacd325b2f3479d` |
| reject proxy stable | `b30ea603656d89caf850a3ca81af3987728832d17f1e1bc3b9f474373f6acc7e` |
| reject verifier result | `3a866fe691ddbbdf5f8a146fa61d060a2e3126bf3a4b903fc2d5c547c389b86c` |

## 6. Claim boundary 与停止纪律

本结果能证明：

- 原 Docker 失败归因确实需要修正；
- 当次真实 proxy 会现场拒绝非白名单 authority；
- upstream-chain 没有打开 verifier/candidate 的直连出口；
- 本次冻结的 container-to-host-proxy endpoint 不可达。

本结果不能证明：

- 完整 Git fetch 只使用 `huggingface.co:443`；
- upstream-linked topology 在其他宿主不可实现；
- V1 网络层信任边界已由 application-layer CONNECT 完整替代；
- production Git verifier 可激活；
- APPS 产生任何 finding。

本轮 API、候选代码、provenance receipt、attestation、finding 均为零。没有第二次
Docker、Podman V4、host network、宿主 Git fetch、authority 扩展、运行时升级或
防火墙调整。本宿主该实验线到此永久收口。
