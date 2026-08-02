# BenchAudit Verifier 拓扑预飞结果

> 日期：2026-08-02
>
> 分支：`research/verifier-topology-preflight-20260802`
>
> 最终裁决：`NOT_IDENTIFIABLE_VERIFIER_TOPOLOGY`

## 1. 结论

代理审计与预飞仪器已经实现并通过本地对抗测试，但这台机器由
`find_container_engine()` 实际选择的 Podman 3.4.4 无法实例化冻结的
双网络 proxy 拓扑：proxy 的 internal 接口需要显式静态 IP 作为唯一监听
地址，而 Podman 3.4.4 CNI 在连接第二个 egress 网络时错误地复用了该 requested
IP，最终因跨子网地址分配失败而不能启动容器。

因此五个 live topology 探针均未开始，不能声称 allowlist、direct-egress
blocking、DNS blocking 或 Git fetch 已在该真实容器拓扑上通过。没有改选
Docker、没有使用宿主 Git fetch、没有放宽 authority、没有改用 wildcard 或
host network。

## 2. 已实现的仪器

### 2.1 可审计 CONNECT proxy

`scripts/https_connect_allowlist_proxy.py` 现在具备：

- `--listen` 必填且必须是非 unspecified 的 literal IP；
- 每个 accepted socket 恰好一个终态 disposition；
- 六值闭集：`allowed / forbidden / malformed / upstream_failed /
  client_aborted / handler_error`；
- session start/end 原始记录；
- accept-time 单调 connection sequence；
- JSONL 写入、flush 和序号分配受锁保护；
- parsed-but-forbidden authority 同样进入 authority 集合；
- raw 层保留时间、请求行、状态与错误；
- stable 层只保留 authority 集合与 disposition counts。

本地真实 socket 测试覆盖成功 CONNECT、403、502、400、header 前断开、handler
异常以及 8 个并发连接的无撕裂日志。

### 2.2 五探针 runner

预飞 runner 已实现：

1. canonical authority 经 proxy CONNECT；
2. 清空 proxy 环境后直连 canonical IP；
3. 清空 proxy 环境后直连 `1.1.1.1:443`；
4. verifier 容器自身 DNS；
5. 独立新 proxy session 对 `example.com:443` 的 live 403。

它还实现 exact revision fetch、raw Git blob OID/SHA 校验、双网络/容器 inspect、
镜像 digest 校验以及 candidate `--network none` 回归。由于 topology 在 proxy
启动前失败，这些 live 探针没有执行，不能用单元测试替代。

## 3. 三次预飞与停止点

三份失败 receipt 均保留，没有覆盖：

| 版本 | 首个失败 gate | 含义 | Fetch |
|---|---|---|---:|
| V1 | `network_internal_flag` | parser 不认识 Podman CNI 的 internal 表示 | 未开始 |
| V2 | `command_failed` | Podman 3.4.4 `network connect` 不支持 `--ip` | 未开始 |
| V3 | `command_failed` | static internal IP 被带到 egress 网络，跨子网分配失败 | 未开始 |

V1 之后的只读诊断确认：

```text
Podman --internal:
  bridge.isGateway = false
  bridge.ipMasq     = absent
  dnsname           = absent

Podman normal network:
  bridge.isGateway = true
  bridge.ipMasq     = true
  dnsname           = present
```

V2 只增加了这套 fail-closed parser。V3 只移除了当前 Podman 不支持的 egress
`network connect --ip` 参数。两次都重新运行完整 preflight，没有复用有利子项。

V3 的原始失败为：

```text
error adding ... to CNI network <egress>:
failed to allocate all requested IPs: <internal-network static IP>
```

继续改成容器内动态发现地址、启动 wrapper、wildcard bind 或 Docker 会改变已经
冻结的拓扑语义，因此没有继续写 V4 预飞。

## 4. 实际环境

| 项 | 值 |
|---|---|
| `find_container_engine()` | `/usr/bin/podman` |
| Podman | 3.4.4，rootless |
| Docker | 存在，但未被选择 |
| Pinned image | `alexgshaw/fix-git@sha256:61e431...` |
| Image ID | `b041e51b3fd55...` |

镜像准备分两步：先把已钉住的 Docker-local image 离线导入 Podman，再使用 exact
digest pull 恢复可验证的 RepoDigest 绑定。该网络动作仅是环境准备，不是 benchmark
证据，也没有被当作 verifier fetch。

## 5. 测试

| 范围 | 结果 |
|---|---:|
| Proxy + topology gate + execution 定向 | 24 passed |
| 全量 | 819 passed |
| candidate default network | 精确 `--network none` |

单元测试同时包含两个相反方向：合法 authority 必须可放行，实际启动的 proxy 配置
必须对非 allowlisted authority 产生 403；“永不拒绝”代理不能通过 gate。

## 6. 证据哈希

| Artifact | SHA-256 |
|---|---|
| V1 plan | `7363368ab55ff870b435d88b4598564edd5e83dd00b625851cdf8478917dbb38` |
| V2 plan | `1188621464c012be99779cd34aef17786b560aebb535c58dbc35920cbfa58b84` |
| V3 plan | `2302180fca8843ba86a9c7da9346a89303532ac9ea0ef7dca63e5139056c3147` |
| V1 receipt | `6c0e25f53e87155e5e4ec38ebdda4a672dad595669651cdb63573845c451e542` |
| V2 receipt | `45619ced7f98342f4b7d9077c31431bc41174be1d3498e71af28edd5b5e4d437` |
| V3 receipt | `12df598bb51f64d8bddc5f794beaa689a357159a2318a9eaacbc3e9f53409c18` |
| Proxy script | `cb79e5fa2b7591b30dcfa80c2aa9c47b2a837017a5f30f44a463fadeda8fa84d` |
| Preflight runner | `b16dccd637b31bf1e242ee8e444bdc04954e3b87b19b9e4b964e25a091a64883` |
| Container probe | `02bcc4d92e95c93bb23224f0d4f3da6c2b9c95fec48dd30cf812a1bcfaf62a50` |

## 7. Claim boundary

本结果能证明：当前 Podman 3.4.4 环境不能按预注册方式建立“explicit internal-IP
listener + dual-network proxy”的拓扑。

本结果不能证明：

- 该拓扑在其他 Podman/Docker 版本上不可实现；
- 当前网络隔离不安全；
- proxy live allow/reject 已在容器拓扑通过；
- Git verifier 已可采信；
- APPS 产生了任何 confirmed 结果。

本轮没有 provenance receipt、attestation、finding 或 candidate execution。

## 8. 下一步

不要直接改选 Docker 后重跑。下一步若继续，必须先选择并独立复核一种新的可满足
设计，例如升级并钉住支持 per-network static IP 的 Podman，或冻结一个能在启动时
机械获得 internal IP 且最终仍以 literal IP exec proxy 的可信 launcher。新设计必须
重新解释其精确损失，并从头运行全部五探针。

在此之前，不冻结生产 Git-verifier 协议，也不运行 APPS 双正例。
